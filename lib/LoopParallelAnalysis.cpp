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
#include "flang/Optimizer/Dialect/FIRType.h"
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

// ── Phase 3 — index-pattern matching ─────────────────────────────────────────
//
// Walks every fir.array_coor inside the loop and inspects its coordinate
// operands.  Two questions per coordinate:
//   (a) Is it derived purely from the loop IV / iter_args?  → independent
//   (b) Is it IV ± nonzero constant?                        → loop-carried dep

// Returns true when 'val' traces back to the loop IV or iter_args through
// type conversions and Fortran loop-variable alloca loads.
static bool isIVDerived(Value val, fir::DoLoopOp loop, unsigned depth = 0) {
  if (depth > 10) return false;

  if (val == loop.getInductionVar()) return true;
  for (Value a : loop.getRegionIterArgs())
    if (val == a) return true;

  Operation *def = val.getDefiningOp();
  if (!def || !loop->isAncestor(def)) return false;

  // Type conversions — transparent for our purposes
  if (auto c = dyn_cast<fir::ConvertOp>(def))
    return isIVDerived(c.getValue(), loop, depth + 1);
  if (auto c = dyn_cast<arith::IndexCastOp>(def))
    return isIVDerived(c.getIn(), loop, depth + 1);
  if (auto c = dyn_cast<arith::ExtSIOp>(def))
    return isIVDerived(c.getIn(), loop, depth + 1);
  if (auto c = dyn_cast<arith::TruncIOp>(def))
    return isIVDerived(c.getIn(), loop, depth + 1);

  // Fortran loop variable: the compiler stores the iter_arg into an alloca
  // at the start of every iteration so user code can reference it by name.
  //   fir.store %iter_arg to %loop_var_alloca  ← inside loop
  //   fir.load  %loop_var_alloca               ← this is what we see
  if (auto ld = dyn_cast<fir::LoadOp>(def)) {
    for (Operation *u : ld.getMemref().getUsers())
      if (auto st = dyn_cast<fir::StoreOp>(u))
        if (loop->isAncestor(st) &&
            isIVDerived(st.getValue(), loop, depth + 1))
          return true;
  }
  return false;
}

// Returns true when 'val' is IV + k (k ≠ 0) and sets 'offset' to k.
static bool isIVPlusOffset(Value val, fir::DoLoopOp loop, int64_t &offset,
                            unsigned depth = 0) {
  if (depth > 10) return false;

  Operation *def = val.getDefiningOp();
  if (!def || !loop->isAncestor(def)) return false;

  // Strip conversions
  if (auto c = dyn_cast<fir::ConvertOp>(def))
    return isIVPlusOffset(c.getValue(), loop, offset, depth + 1);
  if (auto c = dyn_cast<arith::IndexCastOp>(def))
    return isIVPlusOffset(c.getIn(), loop, offset, depth + 1);
  if (auto c = dyn_cast<arith::ExtSIOp>(def))
    return isIVPlusOffset(c.getIn(), loop, offset, depth + 1);
  if (auto c = dyn_cast<arith::TruncIOp>(def))
    return isIVPlusOffset(c.getIn(), loop, offset, depth + 1);

  // addi %base, %const  /  addi %const, %base
  if (auto add = dyn_cast<arith::AddIOp>(def)) {
    auto tryConst = [&](Value base, Value cst) -> bool {
      if (auto c = cst.getDefiningOp<arith::ConstantOp>())
        if (auto ia = c.getValue().dyn_cast<IntegerAttr>())
          if (isIVDerived(base, loop, depth + 1)) {
            offset = ia.getInt();
            return offset != 0;
          }
      return false;
    };
    if (tryConst(add.getLhs(), add.getRhs())) return true;
    if (tryConst(add.getRhs(), add.getLhs())) return true;
  }

  // subi %base, %const  (i.e.  i - k)
  if (auto sub = dyn_cast<arith::SubIOp>(def))
    if (auto c = sub.getRhs().getDefiningOp<arith::ConstantOp>())
      if (auto ia = c.getValue().dyn_cast<IntegerAttr>())
        if (isIVDerived(sub.getLhs(), loop, depth + 1)) {
          offset = -ia.getInt();
          return offset != 0;
        }

  return false;
}

static void runPhase3(LoopInfo &info, fir::DoLoopOp loop) {
  bool hasOffsetIdx  = false;   // a(i±k), k≠0
  bool hasUnknownIdx = false;   // index we cannot classify

  loop.walk([&](fir::ArrayCoorOp ac) {
    Value base = AccessClassifier::getBaseRef(ac.getMemref());
    if (!AccessClassifier::isExternalToLoop(base, loop)) return;

    // Iterate over operands of fir.array_coor, skipping the memref itself
    // and any shape/slice typed operands (fir.shape, fir.slice, etc.).
    // What remains are the integer coordinate subscripts.
    for (Value operand : ac.getOperands()) {
      if (operand == ac.getMemref()) continue;
      mlir::Type ty = operand.getType();
      if (ty.isa<fir::ShapeType>() || ty.isa<fir::ShapeShiftType>() ||
          ty.isa<fir::SliceType>())
        continue;

      int64_t off = 0;
      if (isIVDerived(operand, loop)) {
        // clean IV subscript — this dimension is independent
      } else if (isIVPlusOffset(operand, loop, off)) {
        hasOffsetIdx = true;
        std::string tag = off > 0
            ? "(i+" + std::to_string(off) + ")"
            : "(i"  + std::to_string(off) + ")";
        if (info.reason.find("offset") == std::string::npos)
          info.reason += " Offset subscript a" + tag + " detected.";
      } else {
        hasUnknownIdx = true; // e.g. outer-loop var used in inner loop
      }
    }
  });

  // ── UNSAFE: loop-carried dependency via offset subscript ──────────────────
  if (hasOffsetIdx) {
    info.safety = LoopSafety::Unsafe;
    info.hint   = "! Cannot parallelize";
    info.reason = "Loop-carried dependency: array accessed at i±k offset. "
                  "Iteration i reads data written by a neighbouring iteration.";
    return;
  }

  if (hasUnknownIdx) return; // leave for Phase 4/5

  // ── All array subscripts are plain IV — check for independence ─────────────
  // The Fortran loop-variable alloca (stores i, j, … per iteration) shows up
  // as [RW] scalar in Phase 2 but is NOT a cross-iteration dependency.
  // Filter it out before making the SAFE decision.
  int realExtRW = 0;
  for (const auto &rec : info.accessRecords) {
    if (!rec.isExternalToLoop || !rec.isReadWrite()) continue;
    Operation *defOp = rec.baseRef.getDefiningOp();
    if (defOp && isa<fir::AllocaOp>(defOp)) continue; // skip i/j bookkeeping
    ++realExtRW;
  }

  if (!info.accessSummary) return;
  const AccessSummary &s = *info.accessSummary;

  if (s.externalWrites > 0 && realExtRW == 0) {
    info.safety = LoopSafety::Safe;
    info.hint   = "!$OMP PARALLEL DO";
    info.reason = "Independent per-element access: each iteration reads a(i) and "
                  "writes b(i) with no overlap across iterations.";
  }
  // realExtRW > 0 means a genuine scalar or non-alloca ref is RW → Phase 4
}

// ── Phase 4 — reduction detection ────────────────────────────────────────────
//
// Looks for the scalar accumulation pattern inside the loop body:
//   %old = fir.load  %acc
//   %new = arith.addf/mulf/... %old, <other>
//   fir.store %new to %acc
// where %acc is an external scalar that is NOT an alloca (i.e. a real
// function argument used as an output accumulator).

static void runPhase4(LoopInfo &info, fir::DoLoopOp loop) {
  if (info.safety != LoopSafety::Unknown) return; // already decided

  for (const auto &rec : info.accessRecords) {
    if (!rec.isExternalToLoop || !rec.isReadWrite() || rec.isArrayRef) continue;
    // Skip Fortran loop-variable bookkeeping allocas
    if (rec.baseRef.getDefiningOp() &&
        isa<fir::AllocaOp>(rec.baseRef.getDefiningOp())) continue;

    Value accRef = rec.baseRef;
    bool      found     = false;
    StringRef opName    = "?";

    // Walk every load of accRef inside the loop and check the use chain
    loop.walk([&](fir::LoadOp load) {
      if (found) return;
      if (AccessClassifier::getBaseRef(load.getMemref()) != accRef) return;

      Value loaded = load.getResult();
      for (Operation *user : loaded.getUsers()) {
        bool isAdd = isa<arith::AddFOp, arith::AddIOp>(user);
        bool isMul = isa<arith::MulFOp, arith::MulIOp>(user);
        if (!isAdd && !isMul) continue;

        Value result = user->getResult(0);
        for (Operation *ru : result.getUsers()) {
          if (auto st = dyn_cast<fir::StoreOp>(ru))
            if (AccessClassifier::getBaseRef(st.getMemref()) == accRef) {
              found  = true;
              opName = (isAdd ? "+" : "*");
            }
        }
      }
    });

    if (found) {
      std::string varStr;
      llvm::raw_string_ostream vs(varStr);
      accRef.printAsOperand(vs, mlir::OpPrintingFlags{});

      info.safety = LoopSafety::Reduction;
      info.hint   = "!$OMP PARALLEL DO REDUCTION(" + opName.str() +
                    ":" + varStr + ")";
      info.reason = "Scalar accumulation: load → " + opName.str() +
                    " → store on the same reference. "
                    "Safe to parallelize with the REDUCTION clause.";
      return;
    }
  }
}

// ── Phase 5 — final verdict ───────────────────────────────────────────────────
//
// Any loop still UNKNOWN after Phases 3/4 gets a conservative verdict.

static void runPhase5(LoopInfo &info) {
  if (info.safety != LoopSafety::Unknown) return;

  if (info.accessSummary) {
    const auto &s = *info.accessSummary;
    if (s.externalWrites == 0 && s.externalReadWrites == 0) {
      // Purely read-only — no way to have a write-write or RAW dep
      info.safety = LoopSafety::Safe;
      info.hint   = "!$OMP PARALLEL DO  ! (read-only externals)";
      info.reason = "No external writes detected. Conservative verdict: SAFE.";
      return;
    }
  }
  // Cannot classify — treat as unsafe
  info.safety = LoopSafety::Unsafe;
  info.hint   = "! Parallelizability could not be determined";
  info.reason = "Analysis inconclusive (complex index or unknown pattern). "
                "Conservative assumption: not safe to parallelize.";
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
