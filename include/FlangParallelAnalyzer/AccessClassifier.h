#ifndef FLANG_PARALLEL_ANALYZER_ACCESS_CLASSIFIER_H
#define FLANG_PARALLEL_ANALYZER_ACCESS_CLASSIFIER_H

// AccessClassifier.h — Phase 2
//
// For a given fir.do_loop, walks its body and records every memory
// reference it touches:
//
//   - Is the ref read? written? both?
//   - Is it defined outside the loop (external) or created inside it (local)?
//   - Is it a scalar ref or an array ref?
//
// Phase 3 will consume this output to check *how* arrays are indexed.
// Phase 4 will look at external read-write scalars for reduction patterns.

#include "flang/Optimizer/Dialect/FIROps.h"
#include "mlir/IR/Value.h"
#include "llvm/ADT/DenseMap.h"
#include "llvm/ADT/SmallVector.h"
#include <string>

namespace fpa {

// ── AccessRecord ─────────────────────────────────────────────────────────────
//
// One record per unique base memory reference seen inside the loop.
// "Base" means the root fir.ref<...> after stripping any fir.coordinate_of
// chain — e.g. for  fir.coordinate_of %arr, %i  the base is %arr.

struct AccessRecord {
  mlir::Value baseRef;           // the root fir.ref value

  bool hasRead            = false; // seen in a fir.load
  bool hasWrite           = false; // seen in a fir.store
  bool isExternalToLoop   = false; // defined *outside* the loop
  bool isArrayRef         = false; // base type is fir.ref<!fir.array<...>>

  // Convenience
  bool isReadOnly()  const { return  hasRead && !hasWrite; }
  bool isWriteOnly() const { return !hasRead &&  hasWrite; }
  bool isReadWrite() const { return  hasRead &&  hasWrite; }

  // A short label for printing: "R", "W", or "RW"
  std::string rwLabel() const {
    if (isReadWrite()) return "RW";
    if (hasRead)       return "R";
    if (hasWrite)      return "W";
    return "?";
  }
};

// ── AccessSummary ─────────────────────────────────────────────────────────────
//
// Rolled-up counts computed from the AccessRecord list — this is what
// LoopInfo carries and what the hint emitter queries.

struct AccessSummary {
  unsigned externalReads      = 0; // external refs that are read-only
  unsigned externalWrites     = 0; // external refs that are write-only
  unsigned externalReadWrites = 0; // external refs that are both read & written
  unsigned localWrites        = 0; // writes to loop-local (induction-var, alloca, etc.)

  // true when every external ref is read-only
  bool allExternalRefsReadOnly() const {
    return externalWrites == 0 && externalReadWrites == 0;
  }

  // true when there is at least one external ref that is written
  bool hasAnyExternalWrite() const {
    return externalWrites > 0 || externalReadWrites > 0;
  }
};

// ── AccessClassifier ──────────────────────────────────────────────────────────

class AccessClassifier {
public:
  // Classify all memory ops in the loop body and return per-ref records.
  static llvm::SmallVector<AccessRecord>
  classify(fir::DoLoopOp loop);

  // Roll the per-ref records up into counts.
  static AccessSummary
  summarize(llvm::ArrayRef<AccessRecord> records);

private:
  // Trace val back through any fir.coordinate_of chain to the root ref.
  static mlir::Value getBaseRef(mlir::Value val);

  // True if val's defining op is NOT inside the loop (or is a block arg).
  static bool isExternalToLoop(mlir::Value val, fir::DoLoopOp loop);

  // True if val's type is fir.ref<!fir.array<...>>.
  static bool isArrayType(mlir::Value val);
};

} // namespace fpa

#endif // FLANG_PARALLEL_ANALYZER_ACCESS_CLASSIFIER_H
