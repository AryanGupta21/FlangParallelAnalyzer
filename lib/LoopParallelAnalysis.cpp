// LoopParallelAnalysis.cpp
//
// Phase 1 — skeleton pass.
//
// Walks every fir.do_loop inside a func::FuncOp, collects basic loop
// metadata (location, constant bounds), and emits a placeholder hint.
// Phases 2-4 will fill in dependency / reduction analysis; Phase 5
// will replace the placeholder output with real OMP directives.

#include "FlangParallelAnalyzer/LoopParallelAnalysis.h"

#include "flang/Optimizer/Dialect/FIROps.h"        // fir::DoLoopOp
#include "mlir/Dialect/Arith/IR/Arith.h"           // arith::ConstantIndexOp
#include "mlir/Dialect/Func/IR/FuncOps.h"          // func::FuncOp
#include "mlir/IR/BuiltinOps.h"
#include "mlir/IR/Location.h"
#include "mlir/IR/Visitors.h"
#include "mlir/Pass/Pass.h"
#include "llvm/Support/raw_ostream.h"

using namespace mlir;

namespace fpa {

// ── Helpers ─────────────────────────────────────────────────────────────────

// Returns the integer value of a constant index Value, or std::nullopt.
static std::optional<int64_t> getConstantIndex(Value v) {
  if (!v)
    return std::nullopt;
  if (auto cst = v.getDefiningOp<arith::ConstantIndexOp>())
    return cst.value();
  // Also handle arith.constant with IntegerAttr
  if (auto cst = v.getDefiningOp<arith::ConstantOp>()) {
    if (auto intAttr = cst.getValue().dyn_cast<IntegerAttr>())
      return intAttr.getInt();
  }
  return std::nullopt;
}

// Pretty-prints a Location as "file:line" when possible, otherwise "<unknown>".
static std::string locationString(Location loc) {
  std::string buf;
  llvm::raw_string_ostream os(buf);

  if (auto fileLoc = loc.dyn_cast<FileLineColLoc>()) {
    os << fileLoc.getFilename().str() << ":" << fileLoc.getLine();
  } else if (auto namedLoc = loc.dyn_cast<NameLoc>()) {
    os << namedLoc.getName().str();
  } else {
    os << "<unknown>";
  }
  return os.str();
}

// Counts direct fir.do_loop children (non-recursive) — used to detect
// the outermost loop of a nest.
static unsigned countDirectChildLoops(fir::DoLoopOp loop) {
  unsigned count = 0;
  for (Operation &op : loop.getBody()->getOperations()) {
    if (isa<fir::DoLoopOp>(op))
      ++count;
  }
  return count;
}

// ── Pass ────────────────────────────────────────────────────────────────────

namespace {

struct LoopParallelAnalysisPass
    : public PassWrapper<LoopParallelAnalysisPass,
                         OperationPass<func::FuncOp>> {

  MLIR_DEFINE_EXPLICIT_INTERNAL_INLINE_TYPE_ID(LoopParallelAnalysisPass)

  StringRef getArgument()    const override { return "fir-loop-parallel-analysis"; }
  StringRef getDescription() const override {
    return "Detect parallelizable Fortran DO loops and emit OpenMP hints";
  }

  void runOnOperation() override {
    func::FuncOp func = getOperation();
    llvm::outs() << "\n[FlangParallelAnalyzer] Function: "
                 << func.getName() << "\n";
    llvm::outs() << std::string(60, '-') << "\n";

    unsigned loopCount = 0;

    // Walk in pre-order so outer loops are visited before inner ones.
    func.walk<WalkOrder::PreOrder>([&](fir::DoLoopOp loop) {
      ++loopCount;
      LoopInfo info = collectLoopInfo(loop);
      printLoopInfo(info, loopCount);
    });

    if (loopCount == 0)
      llvm::outs() << "  (no DO loops found)\n";

    llvm::outs() << std::string(60, '-') << "\n\n";
  }

private:
  // ── Phase 1: collect basic structural metadata ─────────────────────────

  LoopInfo collectLoopInfo(fir::DoLoopOp loop) {
    LoopInfo info;
    info.loc = loop.getLoc();

    // ── Bounds ──────────────────────────────────────────────────────────
    // Store as strings for display; Phases 2-3 will use the Values directly.
    std::optional<int64_t> lb   = getConstantIndex(loop.getLowerBound());
    std::optional<int64_t> ub   = getConstantIndex(loop.getUpperBound());
    std::optional<int64_t> step = getConstantIndex(loop.getStep());

    // ── Nesting depth ───────────────────────────────────────────────────
    unsigned nestDepth = 0;
    Operation *parent  = loop->getParentOp();
    while (parent) {
      if (isa<fir::DoLoopOp>(parent))
        ++nestDepth;
      parent = parent->getParentOp();
    }

    unsigned innerLoops = countDirectChildLoops(loop);

    // ── Body op count (rough complexity proxy) ──────────────────────────
    unsigned bodyOps = 0;
    loop.getBody()->walk([&](Operation *) { ++bodyOps; });

    // ── Build reason string ──────────────────────────────────────────────
    std::string reasonBuf;
    llvm::raw_string_ostream rs(reasonBuf);

    rs << "Phase 1 (skeleton) — bounds: [";
    if (lb)   rs << *lb;   else rs << "?";
    rs << " .. ";
    if (ub)   rs << *ub;   else rs << "?";
    rs << " step ";
    if (step) rs << *step; else rs << "?";
    rs << "]";

    if (nestDepth > 0)
      rs << ", nest depth: " << nestDepth;
    if (innerLoops > 0)
      rs << ", direct inner loops: " << innerLoops;
    rs << ", body ops: " << bodyOps;

    // Placeholder safety — Phases 2-4 will compute this properly.
    info.safety = LoopSafety::Unknown;
    info.hint   = "!$OMP PARALLEL DO  ! (unverified — analysis pending)";
    info.reason = rs.str();

    return info;
  }

  // ── Printer ─────────────────────────────────────────────────────────────

  void printLoopInfo(const LoopInfo &info, unsigned idx) {
    llvm::outs() << "\n  Loop #" << idx
                 << " @ " << locationString(info.loc) << "\n";

    llvm::outs() << "  Hint   : " << info.hint   << "\n";
    llvm::outs() << "  Status : " << safetyLabel(info.safety) << "\n";
    llvm::outs() << "  Detail : " << info.reason << "\n";
  }

  static StringRef safetyLabel(LoopSafety s) {
    switch (s) {
    case LoopSafety::Safe:      return "SAFE";
    case LoopSafety::Reduction: return "REDUCTION";
    case LoopSafety::Unsafe:    return "UNSAFE";
    case LoopSafety::Unknown:   return "UNKNOWN (Phase 1 — full analysis pending)";
    }
    return "UNKNOWN";
  }
};

} // namespace

// ── Pass registration ────────────────────────────────────────────────────────

std::unique_ptr<mlir::Pass> createLoopParallelAnalysisPass() {
  return std::make_unique<LoopParallelAnalysisPass>();
}

void registerLoopParallelAnalysisPass() {
  PassRegistration<LoopParallelAnalysisPass>();
}

} // namespace fpa
