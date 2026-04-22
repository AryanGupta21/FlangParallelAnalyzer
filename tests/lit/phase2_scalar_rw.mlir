// phase2_scalar_rw.mlir
//
// Pattern: sum = sum + a(i) * b(i)  — dot-product / reduction loop.
//
//   %arg0 = a(:)  read-only array
//   %arg1 = b(:)  read-only array
//   %arg2 = &sum  scalar that is BOTH read and written in every iteration
//
// What Phase 2 should detect:
//   ext-reads=2        (%arg0, %arg1 — arrays, read-only)
//   ext-writes=0
//   ext-readwrites=1   (%arg2 — scalar, read-write → reduction candidate)
//
// Expected hint: "possible reduction pattern"
// Phase 4 will confirm the +  operator and emit REDUCTION(+:sum).

// RUN: %fpa-tool --fir-loop-parallel-analysis %s 2>&1 | %filecheck %s

// CHECK-LABEL: [FlangParallelAnalyzer] Function: scalar_rw

// CHECK: Loop #1
// CHECK: ext-reads=2
// CHECK: ext-writes=0
// CHECK: ext-readwrites=1
// CHECK: [RW] scalar
// CHECK: possible reduction pattern

func.func @scalar_rw(
    %arg0: !fir.ref<!fir.array<?xf32>>,  // a(:)
    %arg1: !fir.ref<!fir.array<?xf32>>,  // b(:)
    %arg2: !fir.ref<f32>                  // &sum
) {
  %c1  = arith.constant 1 : index
  %c10 = arith.constant 10 : index

  fir.do_loop %i = %c1 to %c10 step %c1 {
    // sum (current value)
    %sum_cur = fir.load %arg2 : !fir.ref<f32>

    // a(i)
    %a_elem = fir.coordinate_of %arg0, %i
                : (!fir.ref<!fir.array<?xf32>>, index) -> !fir.ref<f32>
    %a_val  = fir.load %a_elem : !fir.ref<f32>

    // b(i)
    %b_elem = fir.coordinate_of %arg1, %i
                : (!fir.ref<!fir.array<?xf32>>, index) -> !fir.ref<f32>
    %b_val  = fir.load %b_elem : !fir.ref<f32>

    // sum = sum + a(i)*b(i)
    %prod    = arith.mulf %a_val, %b_val : f32
    %new_sum = arith.addf %sum_cur, %prod : f32
    fir.store %new_sum to %arg2 : !fir.ref<f32>
  }

  return
}
