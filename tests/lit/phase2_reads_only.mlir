// phase2_reads_only.mlir
//
// Pattern: loop reads from two external refs, writes to a loop-local alloca.
//
// What Phase 2 should detect:
//   ext-reads=2   (both %arg0 and %arg1 are external and read-only)
//   ext-writes=0
//   ext-readwrites=0
//
// Expected hint: read-only externals → promising for parallelism

// RUN: %fpa-tool --fir-loop-parallel-analysis %s 2>&1 | %filecheck %s

// CHECK-LABEL: [FlangParallelAnalyzer] Function: reads_only

// CHECK: Loop #1
// CHECK: ext-reads=2
// CHECK: ext-writes=0
// CHECK: ext-readwrites=0
// CHECK: read-only externals

func.func @reads_only(%arg0: !fir.ref<f32>, %arg1: !fir.ref<f32>) {
  %c1  = arith.constant 1  : index
  %c10 = arith.constant 10 : index

  fir.do_loop %i = %c1 to %c10 step %c1 {
    // Read two external scalars
    %v0 = fir.load %arg0 : !fir.ref<f32>
    %v1 = fir.load %arg1 : !fir.ref<f32>

    // Compute and store into a loop-local alloca — NOT an external write
    %sum  = arith.addf %v0, %v1 : f32
    %local = fir.alloca f32
    fir.store %sum to %local : !fir.ref<f32>
  }

  return
}
