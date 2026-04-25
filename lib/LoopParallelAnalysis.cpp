// LoopParallelAnalysis.cpp
//
// The main MLIR pass.  Each phase adds analysis on top of the previous one.
//
//  Phase 1 — structural metadata (loop bounds, nesting depth, op count)
//  Phase 2 — access classification (which refs are read / written / external)
//  Phase 3 — index pattern matching       [stub: wired in, not yet filled]
//  Phase 4 — reduction detection          [stub: wired in, not yet filled]
//  Phase 5 — final hint emission          [stub: wired in, not yet filled]

#include "FlangParallelAnalyzer/LoopParallelAnalysis.h"
#include "FlangParallelAnalyzer/AccessClassifier.h"

#include "flang/Optimizer/Dialect/FIROps.h"
#include "mlir/Dialect/Arith/IR/Arith.h"
#include "mlir/Dialect/Func/IR/FuncOps.h"
#include "mlir/IR/BuiltinOps.h"
#include "mlir/IR/Location.h"
#include "mlir/IR/Visitors.h"
#include "mlir/Pass/Pass.h"
#include "llvm/Support/raw_ostream.h"

using namespace mlir;

namespace fpa {

// ── Utilities ────────────────────────────────────────────────────────────────

static std::optional<int64_t> getConstantIndex(Value v) {
  if (!v) return std::nullopt;
  if (auto c = v.getDefiningOp<arith::ConstantIndexOp>())
    return c.value();
  if (auto c = v.getDefiningOp<arith::ConstantOp>())
    if (auto ia = c.getValue().dyn_cast<IntegerAttr>())
      return ia.getInt();
  return std::nullopt;
}

static std::string locationString(std::optional<mlir::Location> locOpt) {
  if (!locOpt)
    return "<unknown>";
  mlir::Location loc = *locOpt;
  std::string buf;
  llvm::raw_string_ostream os(buf);
  if (auto fl = loc.dyn_cast<FileLineColLoc>())
    os << fl.getFilename().str() << ":" << fl.getLine();
  else if (auto nl = loc.dyn_cast<NameLoc>())
    os << nl.getName().str();
  else
    os << "<unknown>";
  return os.str();
}

static StringRef safetyLabel(LoopSafety s) {
  switch (s) {
  case LoopSafety::Safe:      return "SAFE";
  case LoopSafety::Reduction: return "REDUCTION";
  case LoopSafety::Unsafe:    return "UNSAFE";
  case LoopSafety::Unknown:   return "UNKNOWN";
  }
  return "UNKNOWN";
}

// ── Phase 1 — structural metadata ────────────────────────────────────────────

static LoopInfo collectPhase1(fir::DoLoopOp loop) {
  LoopInfo info;
  info.loc        = std::optional<mlir::Location>(loop.getLoc());
  info.lowerBound = getConstantIndex(loop.getLowerBound());
  info.upperBound = getConstantIndex(loop.getUpperBound());
  info.step       = getConstantIndex(loop.getStep());

  // Nesting depth: count ancestor fir.do_loop ops.
  Operation *parent = loop->getParentOp();
  while (parent) {
    if (isa<fir::DoLoopOp>(parent))
      ++info.nestDepth;
    parent = parent->getParentOp();
  }

  // Direct child loops.
  for (Operation &op : loop.getBody()->getOperations())
    if (isa<fir::DoLoopOp>(op))
      ++info.innerLoops;

  // Body op count (rough complexity proxy).
  loop.getBody()->walk([&](Operation *) { ++info.bodyOpCount; });

  info.safety = LoopSafety::Unknown;
  info.hint   = "!$OMP PARALLEL DO  ! (analysis in progress)";
  info.reason = "Phase 1 only";
  return info;
}

// ── Phase 2 — access classification ──────────────────────────────────────────

static void runPhase2(LoopInfo &info, fir::DoLoopOp loop) {
  info.accessRecords = AccessClassifier::classify(loop);
  AccessSummary s    = AccessClassifier::summarize(info.accessRecords);
  info.accessSummary = s;

  // Update hint and reason based on what we now know.
  // We still cannot call a loop Safe (that needs Phase 3 index analysis),
  // but we can flag it as Unsafe when external writes exist without
  // any possible justification.

  if (s.allExternalRefsReadOnly()) {
    // Nothing is written to external memory → trivially parallel
    // (Phase 3 will confirm; stay UNKNOWN to be safe until then).
    info.hint   = "!$OMP PARALLEL DO  ! (read-only externals — confirming in Phase 3)";
    info.reason = "All external refs are read-only; no write dependencies possible.";
  } else if (s.externalReadWrites > 0 && s.externalWrites == 0) {
    // External refs are both read and written — could be a reduction.
    // Phase 4 will check the pattern more carefully.
    info.hint   = "!$OMP PARALLEL DO REDUCTION(...)  ! (candidate — confirming in Phase 4)";
    info.reason = "External read-write ref(s) detected; possible reduction pattern.";
  } else if (s.externalWrites > 0) {
    // Something is written to an external ref. Without index analysis
    // we cannot rule out a loop-carried dependency.
    info.hint   = "!$OMP PARALLEL DO  ! (external write — index check pending Phase 3)";
    info.reason = "External write detected; awaiting index-pattern check.";
  }
}

// ── Phase 3 stub ─────────────────────────────────────────────────────────────
// Will detect a(i-1) / a(i+1) style accesses.

static void runPhase3(LoopInfo & /*info*/, fir::DoLoopOp /*loop*/) {
  // TODO(Phase 3): walk fir.coordinate_of indices and check for IV offsets.
}

// ── Phase 4 stub ─────────────────────────────────────────────────────────────
// Will match  load → binary-op → store-same-ref  reduction patterns.

static void runPhase4(LoopInfo & /*info*/, fir::DoLoopOp /*loop*/) {
  // TODO(Phase 4): detect scalar accumulation.
}

// ── Phase 5 stub ─────────────────────────────────────────────────────────────
// Will produce the final, authoritative OMP directive string + JSON output.

static void runPhase5(LoopInfo & /*info*/) {
  // TODO(Phase 5): replace placeholder hints with definitive directives.
}

// ── Printer ──────────────────────────────────────────────────────────────────

static void printLoopInfo(const LoopInfo &info, unsigned idx) {
  llvm::outs() << "\n  Loop #" << idx
               << " @ " << locationString(info.loc) << "\n";

  // ── Bounds ──
  llvm::outs() << "  Bounds : [";
  if (info.lowerBound) llvm::outs() << *info.lowerBound; else llvm::outs() << "?";
  llvm::outs() << " .. ";
  if (info.upperBound) llvm::outs() << *info.upperBound; else llvm::outs() << "?";
  llvm::outs() << " step ";
  if (info.step)       llvm::outs() << *info.step;       else llvm::outs() << "?";
  llvm::outs() << "]";
  if (info.nestDepth > 0)
    llvm::outs() << "  depth=" << info.nestDepth;
  llvm::outs() << "\n";

  // ── Phase 2: access summary ──
  if (info.accessSummary) {
    const AccessSummary &s = *info.accessSummary;
    llvm::outs() << "  Access : "
                 << "ext-reads="      << s.externalReads      << "  "
                 << "ext-writes="     << s.externalWrites      << "  "
                 << "ext-readwrites=" << s.externalReadWrites  << "  "
                 << "local-writes="   << s.localWrites         << "\n";

    // Per-ref detail (one line each, indented)
    for (const AccessRecord &rec : info.accessRecords) {
      if (!rec.isExternalToLoop) continue; // skip loop-local refs
      llvm::outs() << "           [" << rec.rwLabel() << "] "
                   << (rec.isArrayRef ? "array" : "scalar")
                   << " — ";
      // Print the Value's brief representation
      std::string valStr;
      llvm::raw_string_ostream vs(valStr);
      // printAsOperand(stream, bool) removed in LLVM 18 — use OpPrintingFlags
      rec.baseRef.printAsOperand(vs, mlir::OpPrintingFlags{});
      llvm::outs() << vs.str() << "\n";
    }
  }

  // ── Hint & verdict ──
  llvm::outs() << "  Status : " << safetyLabel(info.safety) << "\n";
  llvm::outs() << "  Hint   : " << info.hint   << "\n";
  llvm::outs() << "  Reason : " << info.reason << "\n";
}

// ── Pass ─────────────────────────────────────────────────────────────────────

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
                 << func.getName() << "\n"
                 << std::string(60, '-') << "\n";

    unsigned idx = 0;

    func.walk<WalkOrder::PreOrder>([&](fir::DoLoopOp loop) {
      ++idx;

      // Run each phase in order.  Later phases overwrite/extend the
      // fields set by earlier ones.
      LoopInfo info = collectPhase1(loop);
      runPhase2(info, loop);
      runPhase3(info, loop);  // stub
      runPhase4(info, loop);  // stub
      runPhase5(info);        // stub

      printLoopInfo(info, idx);
    });

    if (idx == 0)
      llvm::outs() << "  (no DO loops found)\n";

    llvm::outs() << std::string(60, '-') << "\n\n";
  }
};

} // namespace

// ── Registration ─────────────────────────────────────────────────────────────

std::unique_ptr<mlir::Pass> createLoopParallelAnalysisPass() {
  return std::make_unique<LoopParallelAnalysisPass>();
}

void registerLoopParallelAnalysisPass() {
  PassRegistration<LoopParallelAnalysisPass>();
}

} // namespace fpa
