# DESIGN

## Problem statement

Manually annotating Fortran DO loops with OpenMP directives is tedious and
error-prone. A missed `!$OMP PARALLEL DO` leaves performance on the table; a
wrong one silently produces incorrect results. This tool automates the
classification step: given a compiled FIR file, it tells you — per loop —
whether it is safe to parallelize, needs a reduction clause, or carries a
dependency that makes parallelism unsafe.

---

## High-level approach

The tool is a static analysis MLIR pass (`fpa::LoopParallelAnalysisPass`) that
operates on **FIR (Fortran Intermediate Representation)** — the MLIR-based IR
emitted by Flang. Analysis runs in five sequential phases inside a single pass:

```
Phase 1 — Structural metadata   (loop bounds, nesting depth, op count)
Phase 2 — Access classification (which refs are read / written / external)
Phase 3 — Index pattern matching (a(i) vs a(i±k) on external arrays)
Phase 4 — Reduction detection   (load → addf/mulf → store on same scalar)
Phase 5 — Conservative verdict  (anything still Unknown → UNSAFE)
```

Each phase reads the `LoopInfo` struct filled by the previous phase and adds to
it. The final state of `LoopInfo` drives the printed hint.

---

## Why FIR instead of Fortran source text?

Parsing Fortran source text directly is notoriously difficult:

- Free vs. fixed format ambiguity
- Implicit typing (variables undeclared by default)
- `EQUIVALENCE` and `COMMON` aliasing
- Continuation lines, hollerith constants, and other archaic syntax

FIR eliminates all of these. By the time Flang emits FIR, every array access has
been lowered to an explicit `fir.array_coor` op, every loop is a `fir.do_loop`
node with explicit bounds, and the Fortran loop-variable bookkeeping (the
`fir.alloca` + `fir.store`/`fir.load` pair used to give the induction variable a
name in user code) is visible and traceable. Analysing FIR is precise where
source-text analysis would be heuristic.

---

## Why MLIR?

MLIR is the compiler infrastructure that Flang is built on. It provides:

- `PassWrapper<P, OperationPass<func::FuncOp>>` — pass registration and
  scheduling, so the tool runs once per function automatically
- `op.walk<WalkOrder::PreOrder>(...)` — a recursive IR visitor with a single call
- `dyn_cast<fir::DoLoopOp>(op)` — typed pattern matching on IR ops without
  hand-rolling a visitor hierarchy
- The FIR dialect itself — `fir::DoLoopOp`, `fir::LoadOp`, `fir::StoreOp`,
  `fir::ArrayCoorOp`, `fir::AllocaOp`, `fir::DeclareOp` — all the type
  definitions and op semantics Phase 2–4 rely on

Building on LLVM 18 / MLIR means inheriting a production-grade IR and toolchain
rather than writing a Fortran analyser from scratch.

---

## Alternatives considered

### Alternative 1 — Source-level text parsing

A Python script that greps for `do` / `enddo` blocks and inspects array subscripts.

Rejected because: implicit typing makes it impossible to know whether two
variable names alias the same memory; continuation lines can split subscript
expressions across physical lines; Fortran's various array syntax forms would
require a near-complete parser to handle reliably.

### Alternative 2 — LLVM IR analysis (after Flang → LLVM lowering)

Analyse the LLVM IR produced after Flang's lowering pipeline rather than FIR.

Rejected because: by LLVM IR the high-level loop structure is partially
destroyed (induction variable normalisation, partial unrolling, memory access
flattening). Recovering the original `do i = 1, n` bounds and the `a(i)` vs
`a(i-1)` distinction from LLVM IR requires reconstructing information that is
still explicit and unambiguous in FIR.

### Alternative 3 — Full polyhedral dependency analysis (isl / Polly)

Use a polyhedral framework to compute exact data-dependence distances.

Rejected for scope: polyhedral analysis requires affine loop bounds and
subscripts. The test suite includes function calls, conditionally-updated
scalars, and non-constant strides that fall outside the polyhedral model. A
conservative heuristic pass that handles the common patterns correctly is more
immediately useful than an exact analyser that rejects a large fraction of real
loops as "non-affine."

---

## Key design decisions

### Conservative on unknowns

Any pattern not positively identified as SAFE or REDUCTION is classified UNSAFE.
A false positive (SAFE when it isn't) produces wrong runtime results. A false
negative (UNSAFE when it is actually safe) wastes an optimization opportunity.
The tool always chooses the safe side.

### Separation of AccessClassifier from the main pass

Memory access classification (`AccessClassifier.cpp`) is factored out from
`LoopParallelAnalysis.cpp` into its own translation unit with a public API
(`classify`, `summarize`, `getBaseRef`, `isExternalToLoop`, `isArrayType`).
This lets Phase 3 and Phase 4 reuse `getBaseRef` and `isExternalToLoop`
without duplicating logic, and makes the classifier independently testable.

### No source-to-source rewriting

The tool emits textual hints (`!$OMP PARALLEL DO`, etc.) but does not modify any
file. The developer reviews the output and applies the annotation manually. This
keeps the tool's scope narrow and eliminates the risk of corrupting source files.

### Avoiding MlirOptMain in the CLI driver

`tools/fpa-tool/main.cpp` deliberately avoids `MlirOptMain` (the standard
`mlir-opt` driver) because that function pulls in `clang-cpp` as a transitive
dependency, which causes linker failures with apt-installed LLVM 18. Instead, a
minimal parse → `PassManager::run` → exit loop is used.

---

## Architecture

```
Fortran source (.f90)
      │
      │  flang-new -fc1 -emit-fir
      ▼
   .fir file  (MLIR text format)
      │
      │  mlir::parseSourceFile<mlir::ModuleOp>(argv[1], config)
      ▼
 In-memory MLIR module
      │
      │  fpa::LoopParallelAnalysisPass  (runs per func::FuncOp)
      │    Phase 1  collectPhase1()      → LoopInfo struct
      │    Phase 2  runPhase2()          → AccessSummary + AccessRecords
      │    Phase 3  runPhase3()          → isIVDerived / isIVPlusOffset
      │    Phase 4  runPhase4()          → reduction pattern match
      │    Phase 5  runPhase5()          → conservative fallback
      ▼
 printLoopInfo() → stdout (one block per loop)
```

---

## Known limitations

- Multi-dimensional subscripts (e.g. `c(i,j)`) are classified UNSAFE
  conservatively — the outer loop's IV appears as an "unknown" index in the
  inner loop's subscript chain
- Function calls inside loops suppress SAFE classification because side effects
  are unknown (no interprocedural analysis)
- Only `+` and `*` reductions are detected; `min`/`max` intrinsics are not yet
  handled
- Pointer aliasing is not resolved
