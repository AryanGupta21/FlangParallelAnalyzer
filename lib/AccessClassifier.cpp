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

// Walk up the FIR reference chain to find the root memory ref.
//
// Flang lowers array accesses differently depending on the context:
//
//   fir.coordinate_of  — used for derived types / explicit subscripts
//   fir.array_coor     — used for Fortran array element access (most common)
//   fir.declare        — wraps every variable at function entry to attach
//                        metadata; the underlying ref is operand 0.
//
// We must strip all three layers to reach the base fir.ref / block arg.
Value AccessClassifier::getBaseRef(Value val) {
  while (true) {
    if (auto coord = val.getDefiningOp<fir::CoordinateOp>())
      val = coord.getRef();
    else if (auto ac = val.getDefiningOp<fir::ArrayCoorOp>())
      val = ac.getMemref();
    else if (auto decl = val.getDefiningOp<fir::DeclareOp>())
      val = decl.getMemref();
    else
      break;
  }
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

// True when val's type is fir.ref<!fir.array<...>> or fir.box<!fir.array<...>>.
//
// Flang uses two representations:
//   !fir.ref<!fir.array<?xf32>>   — explicit-shape / value dummy
//   !fir.box<!fir.array<?xf32>>   — assumed-shape dummy (Fortran (:) notation)
bool AccessClassifier::isArrayType(Value val) {
  mlir::Type inner;
  if (auto refTy = val.getType().dyn_cast<fir::ReferenceType>())
    inner = refTy.getEleTy();
  else if (auto boxTy = val.getType().dyn_cast<fir::BoxType>())
    inner = boxTy.getEleTy();
  else
    return false;
  return inner.isa<fir::SequenceType>();
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

    // fir.array_merge_store: stores a modified array value back (HLFIR-style).
    // Note: named ArrayMergeStoreOp in FIR 18 (ArrayStoreOp does not exist).
    if (auto arrStore = dyn_cast<fir::ArrayMergeStoreOp>(op))
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
