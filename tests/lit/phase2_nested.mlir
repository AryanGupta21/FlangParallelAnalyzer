// phase2_nested.mlir
//
// Pattern: doubly-nested loop over a 2D array.
//
//   do i = 1, n
//     do j = 1, m
//       a(i,j) = a(i,j) * 2.0
//     end do
//   end do
//
// LIT checks:
//   - Two loops are found (outer = Loop #1, inner = Loop #2)
//   - Outer loop reports depth=0, inner reports depth=1
//   - Inner loop has ext-readwrites=1 (a(i,j) is both read and written)

// RUN: %fpa-tool --fir-loop-parallel-analysis %s 2>&1 | %filecheck %s

// CHECK-LABEL: [FlangParallelAnalyzer] Function: nested

// Outer loop
// CHECK: Loop #1
// CHECK: depth=0

// Inner loop
// CHECK: Loop #2
// CHECK: depth=1
// CHECK: ext-readwrites=1

func.func @nested(%arg0: !fir.ref<!fir.array<?x?xf32>>) {
  %c1  = arith.constant 1   : index
  %c4  = arith.constant 4   : index
  %c8  = arith.constant 8   : index
  %c2  = arith.constant 2.0 : f32

  // Outer loop: i = 1 .. 4
  fir.do_loop %i = %c1 to %c4 step %c1 {

    // Inner loop: j = 1 .. 8
    fir.do_loop %j = %c1 to %c8 step %c1 {

      // Read a(i,j) — two-level coordinate_of for a 2D array
      %row    = fir.coordinate_of %arg0, %i
                  : (!fir.ref<!fir.array<?x?xf32>>, index) -> !fir.ref<!fir.array<?xf32>>
      %elem   = fir.coordinate_of %row, %j
                  : (!fir.ref<!fir.array<?xf32>>, index) -> !fir.ref<f32>
      %val    = fir.load %elem : !fir.ref<f32>

      // a(i,j) = val * 2.0
      %scaled = arith.mulf %val, %c2 : f32
      fir.store %scaled to %elem : !fir.ref<f32>
    }
  }

  return
}
