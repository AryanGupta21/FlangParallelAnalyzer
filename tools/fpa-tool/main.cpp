// fpa-tool — standalone driver for FlangParallelAnalyzer
//
// Usage:
//   flang-new -fc1 -emit-fir input.f90 -o - | fpa-tool [mlir-opt options...]
//   fpa-tool --fir-loop-parallel-analysis input.fir
//
// This is intentionally modelled after mlir-opt so that any mlir-opt flag
// (e.g. --mlir-print-ir-before-all) works alongside our custom pass.

#include "FlangParallelAnalyzer/LoopParallelAnalysis.h"

#include "flang/Optimizer/Dialect/FIRDialect.h"      // fir::FIROpsDialect
#include "flang/Optimizer/Dialect/FIROps.h"
#include "flang/Optimizer/Support/InitFIR.h"          // fir::support::loadDialects
#include "mlir/Dialect/Arith/IR/Arith.h"
#include "mlir/Dialect/Func/IR/FuncOps.h"
#include "mlir/IR/DialectRegistry.h"
#include "mlir/IR/MLIRContext.h"
#include "mlir/Pass/PassManager.h"
#include "mlir/Pass/PassRegistry.h"
#include "mlir/Tools/mlir-opt/MlirOptMain.h"
#include "llvm/Support/InitLLVM.h"
#include "llvm/Support/raw_ostream.h"

int main(int argc, char **argv) {
  llvm::InitLLVM init(argc, argv);

  // ── Register our analysis pass so --fir-loop-parallel-analysis works ──
  fpa::registerLoopParallelAnalysisPass();

  // ── Dialect registry ─────────────────────────────────────────────────
  mlir::DialectRegistry registry;

  // Core MLIR dialects
  registry.insert<mlir::func::FuncDialect>();
  registry.insert<mlir::arith::ArithDialect>();

  // FIR dialect (Flang's Fortran IR)
  registry.insert<fir::FIROpsDialect>();

  // Load any extension dialects Flang registers
  fir::support::registerNonCodegenDialects(registry);

  // ── Hand off to mlir-opt infrastructure ──────────────────────────────
  // This parses flags, reads input FIR, runs the requested passes,
  // and prints results — exactly like mlir-opt.
  return mlir::asMainReturnCode(
      mlir::MlirOptMain(argc, argv, "fpa-tool\n", registry));
}
