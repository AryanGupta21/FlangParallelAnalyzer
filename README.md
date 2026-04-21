# FlangParallelAnalyzer

A Loop Parallelization Hint Detector for Fortran programs, built as an MLIR analysis pass on top of the [Flang](https://flang.llvm.org/) (LLVM) compiler infrastructure.

The tool analyzes Fortran DO loops at the **FIR (Fortran Intermediate Representation)** level and emits parallelization hints such as OpenMP directives.

```
! input: heat.f90
do i = 1, n
  b(i) = a(i) * 2.0
end do

! output
[ParallelAnalyzer] heat.f90:3 — !$OMP PARALLEL DO
  Reason: no loop-carried dependencies detected — safe to parallelize
```

---

## Goals

- Detect parallelizable loops using **heuristic-based analysis** (no full polyhedral theory)
- Emit actionable OpenMP hints: `!$OMP PARALLEL DO`, `!$OMP SIMD`, `REDUCTION`
- Operate as a reusable MLIR pass inside the Flang pipeline
- Keep scope practical: student/research project, incrementally built

---

## Architecture

```
Fortran source
     │  flang-new -fc1 -emit-fir
     ▼
  FIR (fir dialect / MLIR)
     │
     ▼  ← THIS PROJECT
┌────────────────────────────────────────┐
│           FlangParallelAnalyzer        │
│                                        │
│  LoopDetector → AccessClassifier       │
│       → ReductionDetector              │
│       → DependencyChecker             │
│       → HintEmitter                   │
└────────────────────────────────────────┘
     │
     ▼
  Hints (stdout / JSON / annotated source)
```

### Key Heuristics

| Condition | Hint |
|---|---|
| No writes inside loop body | `!$OMP PARALLEL DO` |
| All writes use exact induction var `a(i)` | `!$OMP PARALLEL DO` |
| Scalar accumulation `sum = sum + expr` | `!$OMP PARALLEL DO REDUCTION(+:sum)` |
| Index offset `a(i-1)` or `a(i+1)` | **UNSAFE** — loop-carried dependency |
| Any function call (non-pure) | **UNSAFE** — conservative |
| Nested independent loops | `!$OMP PARALLEL DO COLLAPSE(2)` |

---

## Project Structure

```
FlangParallelAnalyzer/
├── include/FlangParallelAnalyzer/
│   ├── LoopParallelAnalysis.h
│   ├── AccessClassifier.h
│   └── HintEmitter.h
├── lib/
│   ├── LoopParallelAnalysis.cpp    # main MLIR pass
│   ├── AccessClassifier.cpp        # variable read/write tracking
│   ├── ReductionDetector.cpp       # sum/product pattern matching
│   └── HintEmitter.cpp             # OMP directive generation
├── tools/fpa-tool/
│   └── main.cpp                    # standalone driver
├── tests/
│   ├── fortran/                    # .f90 test programs
│   └── lit/                        # LLVM LIT .mlir unit tests
├── scripts/
│   ├── annotate_source.py          # inject hints into .f90 files
│   └── visualize.py                # score visualization
└── docs/
    ├── design.md
    └── heuristics.md
```

---

## Prerequisites

| Tool | Version |
|---|---|
| CMake | ≥ 3.20 |
| Ninja | any recent |
| Clang | ≥ 17 (to build LLVM) |
| LLVM/Flang | `llvmorg-18.1.0` (pinned) |
| Python | ≥ 3.9 (scripts only) |

---

## Build Instructions

### 1. Build LLVM + Flang

```bash
git clone --branch llvmorg-18.1.0 --depth 1 \
  https://github.com/llvm/llvm-project.git

cd llvm-project && mkdir build && cd build

cmake ../llvm \
  -DLLVM_ENABLE_PROJECTS="clang;flang;mlir" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DLLVM_TARGETS_TO_BUILD=X86 \
  -DLLVM_ENABLE_ASSERTIONS=ON \
  -G Ninja

ninja flang-new mlir-opt
```

> Tip: set `CMAKE_C_COMPILER=clang CMAKE_CXX_COMPILER=clang++` and enable `ccache` to cut build time significantly.

### 2. Build FlangParallelAnalyzer

```bash
git clone https://github.com/aryangupta2103/FlangParallelAnalyzer.git
cd FlangParallelAnalyzer && mkdir build && cd build

cmake .. \
  -DMLIR_DIR=/path/to/llvm-project/build/lib/cmake/mlir \
  -DFLANG_DIR=/path/to/llvm-project/build/lib/cmake/flang \
  -G Ninja

ninja
```

### 3. Run on a Fortran file

```bash
flang-new -fc1 -emit-fir tests/fortran/trivial_parallel.f90 -o - | \
  ./build/bin/fpa-tool --fir-loop-parallel-analysis
```

---

## Test Programs

| File | Pattern | Expected Hint |
|---|---|---|
| `trivial_parallel.f90` | `b(i) = a(i) * 2.0` | `!$OMP PARALLEL DO` |
| `reduction.f90` | `sum = sum + a(i)*b(i)` | `REDUCTION(+:sum)` |
| `loop_carried_dep.f90` | `a(i) = a(i) + a(i-1)` | UNSAFE |
| `function_call.f90` | `a(i) = sqrt(a(i))` | UNSAFE (until intrinsic whitelist) |
| `nested_loops.f90` | double independent DO | `COLLAPSE(2)` |

Run all tests:
```bash
cd tests && bash run_tests.sh
```

---

## Development Roadmap

- [x] Project design & README
- [ ] Phase 1 — Skeleton pass: walk `fir.do_loop`, print location
- [ ] Phase 2 — Variable classifier: read/write/read-write tracking
- [ ] Phase 3 — Index pattern matcher: detect `a(i)` vs `a(i±k)`
- [ ] Phase 4 — Reduction detector: scalar accumulation patterns
- [ ] Phase 5 — Hint emitter + JSON output
- [ ] Extension A — Pure intrinsic whitelist (`sqrt`, `sin`, …)
- [ ] Extension B — Parallelizability score (0–100)
- [ ] Extension C — Source annotator script
- [ ] Extension D — Collapse detection for nested loops

---

## Implementation Reference

The analysis pass is implemented in C++ using the [MLIR Pass Infrastructure](https://mlir.llvm.org/docs/PassManagement/).

Core class:
```cpp
struct LoopParallelAnalysisPass
    : public PassWrapper<LoopParallelAnalysisPass,
                         OperationPass<func::FuncOp>> {
  void runOnOperation() override {
    getOperation().walk([&](fir::DoLoopOp loop) {
      analyzeLoop(loop);
    });
  }
};
```

Key FIR operations analyzed:
- `fir.do_loop` — Fortran DO loop
- `fir.array_fetch` / `fir.array_update` — array reads/writes
- `fir.load` / `fir.store` — scalar memory operations
- `fir.call` — function/subroutine calls

---

## Contributing

This is a research/student project. Issues and PRs are welcome.

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/reduction-detector`)
3. Commit with clear messages
4. Open a PR against `main`

---

## License

MIT
