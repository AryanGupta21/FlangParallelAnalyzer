// phase2_array_write.mlir
//
// Pattern: b(i) = a(i) * 2.0  — the classic embarrassingly parallel loop.
//   %arg0 = a(:)   read-only array
//   %arg1 = b(:)   write-only array
//
// Via fir.coordinate_of the base refs (%arg0, %arg1) are external to the loop.
//
// What Phase 2 should detect:
//   ext-reads=1    (%arg0 — array, read-only)
//   ext-writes=1   (%arg1 — array, write-only)
//   ext-readwrites=0
//
// Phase 3 will confirm that the write index is exactly the induction variable
// (no offset), making this truly safe.

// RUN: %fpa-tool --fir-loop-parallel-analysis %s 2>&1 | %filecheck %s

// CHECK-LABEL: [FlangParallelAnalyzer] Function: array_write

// CHECK: Loop #1
// CHECK: ext-reads=1
// CHECK: ext-writes=1
// CHECK: ext-readwrites=0
// CHECK: [R]  array
// CHECK: [W]  array

func.func @array_write(
    %arg0: !fir.ref<!fir.array<?xf32>>,   // a(:) — read
    %arg1: !fir.ref<!fir.array<?xf32>>    // b(:) — write
) {
  %c1  = arith.constant 1   : index
  %c10 = arith.constant 10  : index
  %c2  = arith.constant 2.0 : f32

  fir.do_loop %i = %c1 to %c10 step %c1 {
    // a(i) — read via coordinate_of then load
    %a_elem = fir.coordinate_of %arg0, %i
                : (!fir.ref<!fir.array<?xf32>>, index) -> !fir.ref<f32>
    %val    = fir.load %a_elem : !fir.ref<f32>

    // b(i) = val * 2.0 — write via coordinate_of then store
    %scaled = arith.mulf %val, %c2 : f32
    %b_elem = fir.coordinate_of %arg1, %i
                : (!fir.ref<!fir.array<?xf32>>, index) -> !fir.ref<f32>
    fir.store %scaled to %b_elem : !fir.ref<f32>
  }

  return
}
