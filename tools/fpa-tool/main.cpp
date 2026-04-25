// fpa-tool — lightweight driver for FlangParallelAnalyzer
//
// Usage:
//   flang-new -fc1 -emit-fir input.f90 -o input.fir
//   fpa-tool input.fir
//
// We intentionally avoid MlirOptMain (which brings in clang-cpp as a
// transitive dep).  A simple parse → pass → done loop is all we need.

#include "FlangParallelAnalyzer/LoopParallelAnalysis.h"

#include "flang/Optimizer/Dialect/FIRDialect.h"
#include "mlir/Dialect/Arith/IR/Arith.h"
#include "mlir/Dialect/Func/IR/FuncOps.h"
#include "mlir/IR/DialectRegistry.h"
#include "mlir/IR/MLIRContext.h"
#include "mlir/IR/OwningOpRef.h"
#include "mlir/Parser/Parser.h"
#include "mlir/Pass/PassManager.h"
#include "llvm/Support/InitLLVM.h"
#include "llvm/Support/raw_ostream.h"

int main(int argc, char **argv) {
  llvm::InitLLVM init(argc, argv);

  if (argc < 2) {
    llvm::errs() << "Usage: fpa-tool <input.fir>\n"
                 << "\n"
                 << "Example:\n"
                 << "  flang-new -fc1 -emit-fir myloop.f90 -o myloop.fir\n"
                 << "  fpa-tool myloop.fir\n";
    return 1;
  }

  // ── Dialect registry ───────────────────────────────────────────────────────
  mlir::DialectRegistry registry;
  registry.insert<mlir::func::FuncDialect>();
  registry.insert<mlir::arith::ArithDialect>();
  registry.insert<fir::FIROpsDialect>();

  mlir::MLIRContext context(registry);
  context.loadAllAvailableDialects();

  // ── Parse input FIR file ───────────────────────────────────────────────────
  mlir::OwningOpRef<mlir::ModuleOp> module =
      mlir::parseSourceFile<mlir::ModuleOp>(argv[1], &context);

  if (!module) {
    llvm::errs() << "fpa-tool: failed to parse '" << argv[1] << "'\n";
    return 1;
  }

  // ── Run analysis pass on every func::FuncOp ────────────────────────────────
  mlir::PassManager pm(&context);
  pm.addNestedPass<mlir::func::FuncOp>(
      fpa::createLoopParallelAnalysisPass());

  if (mlir::failed(pm.run(*module))) {
    llvm::errs() << "fpa-tool: pass failed\n";
    return 1;
  }

  return 0;
}
