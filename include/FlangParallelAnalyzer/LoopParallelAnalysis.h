#ifndef FLANG_PARALLEL_ANALYZER_LOOP_PARALLEL_ANALYSIS_H
#define FLANG_PARALLEL_ANALYZER_LOOP_PARALLEL_ANALYSIS_H

#include "FlangParallelAnalyzer/AccessClassifier.h"
#include "mlir/Pass/Pass.h"
#include <memory>
#include <optional>

namespace mlir {
class Pass;
} // namespace mlir

namespace fpa {

// ── Safety verdict ───────────────────────────────────────────────────────────

enum class LoopSafety {
  Safe,       // no dependencies found         → !$OMP PARALLEL DO
  Reduction,  // scalar accumulation pattern   → !$OMP PARALLEL DO REDUCTION
  Unsafe,     // loop-carried dep / side-effect
  Unknown,    // analysis incomplete (conservative → treat as Unsafe)
};

// ── LoopInfo — the single source of truth for one loop ───────────────────────
//
// Each phase fills in its own section.  The hint emitter (Phase 5) reads the
// final state and produces the OMP directive string.

struct LoopInfo {
  mlir::Location loc;
  LoopSafety     safety = LoopSafety::Unknown;
  std::string    hint;    // e.g. "!$OMP PARALLEL DO"
  std::string    reason;  // human-readable explanation shown in output

  // ── Phase 1 fields ──────────────────────────────────────────────────
  std::optional<int64_t> lowerBound;
  std::optional<int64_t> upperBound;
  std::optional<int64_t> step;
  unsigned nestDepth   = 0; // 0 = outermost
  unsigned innerLoops  = 0; // direct child fir.do_loop count
  unsigned bodyOpCount = 0; // total ops inside body (complexity proxy)

  // ── Phase 2 fields ──────────────────────────────────────────────────
  // Set by AccessClassifier after walking loads/stores in the loop body.
  std::optional<AccessSummary> accessSummary;

  // The full per-ref records (used by Phase 3 + 4 for deeper analysis).
  llvm::SmallVector<AccessRecord> accessRecords;

  // ── Phase 3 fields (IndexPatternMatcher) ────────────────────────────
  // bool hasOffsetIndex = false;  // a(i±k) detected

  // ── Phase 4 fields (ReductionDetector) ──────────────────────────────
  // std::string reductionVar;
  // std::string reductionOp;   // "+", "*", "max", "min"
};

// ── Pass factory ─────────────────────────────────────────────────────────────

std::unique_ptr<mlir::Pass> createLoopParallelAnalysisPass();

// Called once at startup to register "--fir-loop-parallel-analysis" with
// the MLIR pass registry (needed by fpa-tool's main.cpp).
void registerLoopParallelAnalysisPass();

} // namespace fpa

#endif // FLANG_PARALLEL_ANALYZER_LOOP_PARALLEL_ANALYSIS_H
