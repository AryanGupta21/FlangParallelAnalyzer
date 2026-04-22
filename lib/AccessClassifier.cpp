// AccessClassifier.cpp — Phase 2
//
// Walks the body of a fir.do_loop and classifies every memory reference
// it touches as read, write, or read-write, and as external or local.
//
// Memory access patterns in Flang FIR
// ─────────────────────────────────────
//
// Scalar read:
//   %val = fir.load %scalar_ref : !fir.ref<f32>
//
// Scalar write:
//   fir.store %val to %scalar_ref : !fir.ref<f32>
//
// Array element read (the common lowering):
//   %elem_ref = fir.coordinate_of %arr_ref, %idx
//                 : (!fir.ref<!fir.array<?xf32>>, index) -> !fir.ref<f32>
//   %val = fir.load %elem_ref : !fir.ref<f32>
//
// Array element write:
//   %elem_ref = fir.coordinate_of %arr_ref, %idx ...
//   fir.store %val to %elem_ref : !fir.ref<f32>
//
// getBaseRef() strips the fir.coordinate_of chain so that array and scalar
// accesses are both recorded under their root fir.ref.

#include "FlangParallelAnalyzer/AccessClassifier.h"

#include "flang/Optimizer/Dialect/FIROps.h"
#include "flang/Optimizer/Dialect/FIRType.h"
#include "mlir/IR/Operation.h"
#include "mlir/IR/Value.h"
#include "llvm/ADT/DenseMap.h"
#include "llvm/Support/raw_ostream.h"

using namespace mlir;

namespace fpa {

// ── Private helpers ──────────────────────────────────────────────────────────

// Walk up a chain of fir.coordinate_of ops to find the root memory ref.
//
// Example:
//   %root  = ... : !fir.ref<!fir.array<?xf32>>
//   %elem1 = fir.coordinate_of %root, %i   → base = %root
//   %elem2 = fir.coordinate_of %elem1, %j  → base = %root  (multi-dim)
//
// If val is not produced by fir.coordinate_of it is returned as-is.
Value AccessClassifier::getBaseRef(Value val) {
  while (auto coord = val.getDefiningOp<fir::CoordinateOp>())
    val = coord.getRef();
  return val;
}

// A value is external to the loop when either:
//   (a) it is a block argument (function parameter, loop IV is handled
//       separately — the IV itself is the loop's region argument), or
//   (b) its defining op lives outside the loop region.
bool AccessClassifier::isExternalToLoop(Value val, fir::DoLoopOp loop) {
  Operation *defOp = val.getDefiningOp();
  if (!defOp)
    return true; // block argument → always external
  return !loop->isAncestor(defOp);
}

// True when val's type is fir.ref<!fir.array<...>>.
bool AccessClassifier::isArrayType(Value val) {
  auto refTy = val.getType().dyn_cast<fir::ReferenceType>();
  if (!refTy)
    return false;
  return refTy.getEleTy().isa<fir::SequenceType>();
}

// ── Public API ───────────────────────────────────────────────────────────────

llvm::SmallVector<AccessRecord>
AccessClassifier::classify(fir::DoLoopOp loop) {
  // Map from base-ref Value → its accumulated AccessRecord.
  llvm::DenseMap<Value, AccessRecord> table;

  // Helper: look up (or insert) the record for a base ref and update it.
  auto record = [&](Value rawRef, bool isRead, bool isWrite) {
    Value base = getBaseRef(rawRef);

    // Skip the loop induction variable itself — it is not a memory ref.
    if (base == loop.getInductionVar())
      return;

    AccessRecord &rec = table[base];
    rec.baseRef           = base;
    rec.hasRead          |= isRead;
    rec.hasWrite         |= isWrite;
    rec.isExternalToLoop  = isExternalToLoop(base, loop);
    rec.isArrayRef        = isArrayType(base);
  };

  // Walk every op nested inside the loop body (but NOT the loop op itself).
  loop.walk([&](Operation *op) {
    if (op == loop.getOperation())
      return;

    // Scalar / array-element READ
    if (auto load = dyn_cast<fir::LoadOp>(op))
      record(load.getMemref(), /*read=*/true, /*write=*/false);

    // Scalar / array-element WRITE
    if (auto store = dyn_cast<fir::StoreOp>(op))
      record(store.getMemref(), /*read=*/false, /*write=*/true);

    // fir.array_load: loads an array section into a value (HLFIR-style).
    // Treat as a read of the underlying box/ref.
    if (auto arrLoad = dyn_cast<fir::ArrayLoadOp>(op))
      record(arrLoad.getMemref(), /*read=*/true, /*write=*/false);

    // fir.array_store: stores a modified array value back (HLFIR-style).
    if (auto arrStore = dyn_cast<fir::ArrayStoreOp>(op))
      record(arrStore.getMemref(), /*read=*/false, /*write=*/true);
  });

  // Flatten the map into a vector.
  llvm::SmallVector<AccessRecord> result;
  result.reserve(table.size());
  for (auto &kv : table)
    result.push_back(kv.second);
  return result;
}

AccessSummary
AccessClassifier::summarize(llvm::ArrayRef<AccessRecord> records) {
  AccessSummary s;
  for (const AccessRecord &rec : records) {
    if (!rec.isExternalToLoop) {
      if (rec.hasWrite)
        ++s.localWrites;
      continue;
    }
    // External ref —
    if (rec.isReadWrite())     ++s.externalReadWrites;
    else if (rec.isWriteOnly()) ++s.externalWrites;
    else if (rec.isReadOnly())  ++s.externalReads;
  }
  return s;
}

} // namespace fpa
