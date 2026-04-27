# FlangParallelAnalyzer

An MLIR analysis pass for the [Flang](https://flang.llvm.org/) Fortran compiler
that automatically detects parallelizable DO loops and emits OpenMP directives.

---

## What it does

Given a Fortran source file, the tool tells you — **per loop** — whether it is
safe to parallelize, needs a reduction clause, or has a loop-carried dependency
that makes it unsafe.

```
Status : SAFE
Hint   : !$OMP PARALLEL DO
Reason : Independent per-element access: each iteration reads a(i) and
         writes b(i) with no overlap across iterations.
```

---

## How it works — the complete pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Fortran source  (.f90)                                      │
│                                                                 │
│     subroutine scale(a, b, n)                                   │
│       do i = 1, n                                               │
│         b(i) = a(i) * 2.0          ← this loop                 │
│       end do                                                    │
│     end subroutine                                              │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           │  flang-new -fc1 -emit-fir
                           │  (Flang compiler, part of LLVM 18)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. FIR — Fortran Intermediate Representation  (.fir)           │
│                                                                 │
│     This is a text file in MLIR format.  Flang compiles your   │
│     Fortran into this IR before generating machine code.       │
│     It preserves loop structure, array shapes, and variable    │
│     intent — exactly what we need for dependency analysis.     │
│                                                                 │
│     fir.do_loop %iv = %lo to %hi step %c1 {                    │
│       %elem_a = fir.array_coor %arg0(%shape) %idx              │
│       %val    = fir.load %elem_a                               │
│       %result = arith.mulf %val, %cst                          │
│       %elem_b = fir.array_coor %arg1(%shape) %idx              │
│       fir.store %result to %elem_b                             │
│     }                                                          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           │  fpa-tool input.fir
                           │  (our tool — built from this repo)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. MLIR parses the .fir file into an in-memory tree            │
│                                                                 │
│     MLIR is a compiler infrastructure from LLVM.  It knows     │
│     how to read the FIR text format and turn it into C++       │
│     objects we can walk programmatically.  We did NOT write    │
│     a parser — we just tell MLIR which file to load.           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           │  our C++ pass runs
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. FlangParallelAnalyzer pass — five phases                    │
│                                                                 │
│  Phase 1 — Structure                                           │
│    Walk every fir.do_loop.  Record bounds, nesting depth,      │
│    number of inner loops, and total op count.                  │
│                                                                 │
│  Phase 2 — Memory access classification                        │
│    For each loop, walk every fir.load, fir.store, and          │
│    fir.array_coor inside it.  For each memory reference        │
│    record:                                                     │
│      • Is it read, written, or both?                           │
│      • Is it defined outside the loop (external) or inside?   │
│      • Is it an array or a scalar?                             │
│                                                                 │
│  Phase 3 — Index pattern matching                              │
│    Look at the subscript of every array access.  Trace it      │
│    back through type conversions and the Fortran loop-variable │
│    bookkeeping to ask: is this subscript the loop IV?           │
│      • a(i)   — IV-derived  → no cross-iteration conflict      │
│      • a(i-1) — IV ± k      → iteration i reads data written  │
│                                by iteration i-1  → UNSAFE      │
│                                                                 │
│  Phase 4 — Reduction detection                                 │
│    Look for the scalar accumulation pattern:                   │
│      %old = fir.load  %acc                                     │
│      %new = arith.addf %old, <expr>                            │
│             fir.store %new to %acc                             │
│    If found → REDUCTION (safe with OpenMP REDUCTION clause)    │
│                                                                 │
│  Phase 5 — Final conservative verdict                          │
│    Any loop still unclassified:                                │
│      • No external writes → SAFE                               │
│      • Otherwise          → UNSAFE  (conservative)             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. Output                                                      │
│                                                                 │
│  Loop #1 @ trivial_parallel.f90:14                             │
│  Access : [R] array %arg0   [W] array %arg1   [RW] scalar %1   │
│  Status : SAFE                                                  │
│  Hint   : !$OMP PARALLEL DO                                    │
│  Reason : Independent per-element access — no cross-iteration  │
│           dependencies detected.                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Source file map

```
FlangParallelAnalyzer/
│
├── tests/fortran/                   ← Fortran programs used as test inputs
│   ├── trivial_parallel.f90         │  b(i) = a(i)*2.0  →  SAFE
│   ├── reduction.f90                │  total += a(i)*b(i)  →  REDUCTION
│   ├── loop_carried_dep.f90         │  a(i) = a(i)+a(i-1)  →  UNSAFE
│   ├── nested_loops.f90             │  double DO, 2-D array
│   └── function_call.f90            │  a(i) = sqrt(a(i))
│
├── include/FlangParallelAnalyzer/
│   ├── LoopParallelAnalysis.h       ← LoopInfo struct, LoopSafety enum
│   └── AccessClassifier.h          ← AccessRecord, AccessSummary types
│
├── lib/
│   ├── LoopParallelAnalysis.cpp     ← THE MAIN PASS (Phases 1–5)
│   └── AccessClassifier.cpp        ← walks fir.load/store/array_coor
│
├── tools/fpa-tool/
│   └── main.cpp                    ← CLI driver: load .fir → run pass → print
│
├── scripts/
│   └── report.py                   ← Python: runs the tool, generates HTML report
│
└── docs/
    ├── heuristics.md               ← full explanation of dependency assumptions
    └── setup.md                    ← build guide (Codespaces + macOS)
```

---

## Key design decisions

### Why FIR and not the Fortran source text?

Parsing raw Fortran text is notoriously hard (free vs. fixed format, implicit
typing, EQUIVALENCE, etc.).  FIR is already a clean, structured tree — every
array access is an explicit `fir.array_coor` op, every loop is a `fir.do_loop`
node, and variable intent is annotated.  Analysing FIR is precise where text
analysis would be approximate.

### Why MLIR?

MLIR provides the pass infrastructure (`PassWrapper`, `PassManager`),
the IR walker (`op.walk(...)`), and the pattern-matching API
(`dyn_cast<fir::LoadOp>(op)`).  We get all of that for free by building on top
of LLVM 18.

### Why conservative on unknown cases?

A false positive (telling you a loop is safe when it isn't) would produce
**wrong results** at runtime.  A false negative (saying UNSAFE when it is
actually safe) only means a missed optimization.  The tool always chooses the
safe side.

---

## Test results

| Fortran file | Pattern | Verdict | OpenMP hint |
|---|---|---|---|
| `trivial_parallel.f90` | `b(i) = a(i) * 2.0` | **SAFE** | `!$OMP PARALLEL DO` |
| `reduction.f90` | `total = total + a(i)*b(i)` | **REDUCTION** | `!$OMP PARALLEL DO REDUCTION(+:total)` |
| `loop_carried_dep.f90` | `a(i) = a(i) + a(i-1)` | **UNSAFE** | loop-carried dependency |
| `nested_loops.f90` | 2-D matrix update | UNSAFE (conservative) | multi-dim index not traceable |
| `function_call.f90` | `a(i) = sqrt(a(i))` | UNSAFE (conservative) | in-place array update |

---

## Building and running

### GitHub Codespaces (zero setup)

```bash
# Install dependencies
sudo apt-get install -y llvm-18 mlir-18-tools libmlir-18-dev \
    flang-18 libflang-18-dev libclang-cpp-18-dev

# Fix symlink
sudo ln -sf /usr/lib/llvm-18/lib/libclang-cpp.so.18.1 \
            /usr/lib/llvm-18/lib/libclang-cpp.so

# Build
mkdir build && cd build
cmake .. -DLLVM_BUILD_DIR=/usr/lib/llvm-18 -DCMAKE_BUILD_TYPE=Release
make -j$(nproc) fpa-tool
```

### Run on one file

```bash
export PATH="/usr/lib/llvm-18/bin:$PATH"

flang-new -fc1 -emit-fir tests/fortran/trivial_parallel.f90 -o /tmp/out.fir
./build/tools/fpa-tool/fpa-tool /tmp/out.fir
```

### Run all tests + generate HTML report

```bash
python3 scripts/report.py tests/fortran/*.f90 -o report.html
python3 -m http.server 8080   # open the Ports tab in VS Code → port 8080
```

---

## Further reading

- [`docs/heuristics.md`](docs/heuristics.md) — every phase's assumptions and known limitations
- [`docs/setup.md`](docs/setup.md) — full build guide including macOS source build

---

## License

MIT
