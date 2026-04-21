#ifndef FLANG_PARALLEL_ANALYZER_LOOP_PARALLEL_ANALYSIS_H
#define FLANG_PARALLEL_ANALYZER_LOOP_PARALLEL_ANALYSIS_H

#include "mlir/Pass/Pass.h"
#include <memory>

namespace mlir {
class Pass;
} // namespace mlir

namespace fpa {

// ── Result types ────────────────────────────────────────────────────────────

// Safety verdict for a single loop.
enum class LoopSafety {
  Safe,       // no dependencies found — emit OMP PARALLEL DO
  Reduction,  // scalar accumulation — emit OMP PARALLEL DO REDUCTION
  Unsafe,     // loop-carried dep or unknown side-effect
  Unknown,    // analysis could not determine (conservative → Unsafe)
};

// Everything the analyzer knows about one loop after Phase 1.
// Phases 2-4 will add fields here.
struct LoopInfo {
  mlir::Location loc;
  LoopSafety     safety = LoopSafety::Unknown;
  std::string    hint;         // suggested OMP directive string
  std::string    reason;       // human-readable justification

  // ── Phase 2 fields (AccessClassifier) ─────────────────────────────
  // bool hasExternalScalarWrite = false;
  // bool allArrayWritesUseExactIV = false;

  // ── Phase 3 fields (IndexPatternMatcher) ──────────────────────────
  // bool hasOffsetAccess = false;   // a(i-1) or a(i+1)

  // ── Phase 4 fields (ReductionDetector) ────────────────────────────
  // std::string reductionVar;
  // std::string reductionOp;        // "+", "*", "max", "min"
};

// ── Pass factory ────────────────────────────────────────────────────────────

// Creates the analysis pass.  Register it with the MLIR pass manager as
// "--fir-loop-parallel-analysis".
std::unique_ptr<mlir::Pass> createLoopParallelAnalysisPass();

} // namespace fpa

#endif // FLANG_PARALLEL_ANALYZER_LOOP_PARALLEL_ANALYSIS_H
