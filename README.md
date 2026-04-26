# FlangParallelAnalyzer

An MLIR analysis pass for the [Flang](https://flang.llvm.org/) Fortran compiler that detects parallelizable DO loops and emits OpenMP directives.

The tool works at the **FIR (Fortran Intermediate Representation)** level — the same IR that Flang produces before lowering to LLVM IR — giving it access to array shapes, loop structure, and variable intent annotations.

---

## Sample Output

```
$ fpa-tool trivial_parallel.fir

[FlangParallelAnalyzer] Function: _QPscale
------------------------------------------------------------

  Loop #1 @ trivial_parallel.fir:30
  Bounds : [? .. ? step 1]
  Access : ext-reads=1  ext-writes=1  ext-readwrites=1  local-writes=0
           [R] array — %arg0
           [W] array — %arg1
           [RW] scalar — %1
  Status : SAFE
  Hint   : !$OMP PARALLEL DO
  Reason : Independent per-element access: each iteration reads a(i) and
           writes b(i) with no overlap across iterations.

------------------------------------------------------------
```

```
$ fpa-tool loop_carried_dep.fir

  Loop #1 @ loop_carried_dep.fir:22
  Status : UNSAFE
  Hint   : ! Cannot parallelize
  Reason : Loop-carried dependency: array accessed at i±k offset.
           Iteration i reads data written by a neighbouring iteration.
```

```
$ fpa-tool reduction.fir

  Loop #1 @ reduction.fir:32
  Status : REDUCTION
  Hint   : !$OMP PARALLEL DO REDUCTION(+:%arg3)
  Reason : Scalar accumulation: load → + → store on the same reference.
           Safe to parallelize with the REDUCTION clause.
```

---

## How It Works — Five Phases

| Phase | What it does |
|---|---|
| **1 — Structure** | Extracts loop bounds, nesting depth, body op count from `fir.do_loop` |
| **2 — Access classification** | Walks `fir.load`/`fir.store`/`fir.array_coor` and classifies each base reference as read, write, or read-write; external or loop-local |
| **3 — Index pattern matching** | Checks whether array subscripts are derived from the loop IV (safe) or are IV ± constant (loop-carried dependency) |
| **4 — Reduction detection** | Matches `load → addf/mulf → store` on the same scalar reference |
| **5 — Final verdict** | Conservative fallback: read-only loops → SAFE, anything else unresolved → UNSAFE |

See [`docs/heuristics.md`](docs/heuristics.md) for the full dependency assumptions.

---

## Test Programs

| File | Pattern | Verdict |
|---|---|---|
| `trivial_parallel.f90` | `b(i) = a(i) * 2.0` — separate read/write arrays | **SAFE** `!$OMP PARALLEL DO` |
| `reduction.f90` | `total = total + a(i)*b(i)` — scalar accumulation | **REDUCTION** `!$OMP PARALLEL DO REDUCTION(+:...)` |
| `loop_carried_dep.f90` | `a(i) = a(i) + a(i-1)` — reads previous iteration | **UNSAFE** |
| `nested_loops.f90` | Double DO, 2-D array update | UNSAFE (conservative — outer-loop IV not traceable from inner loop) |
| `function_call.f90` | `a(i) = sqrt(a(i))` — in-place update | UNSAFE (conservative — same array read+written) |

---

## Project Structure

```
FlangParallelAnalyzer/
├── include/FlangParallelAnalyzer/
│   ├── LoopParallelAnalysis.h   # LoopInfo struct, LoopSafety enum, pass factory
│   └── AccessClassifier.h      # AccessRecord, AccessSummary, classifier API
├── lib/
│   ├── LoopParallelAnalysis.cpp # Phases 1–5, MLIR pass definition
│   └── AccessClassifier.cpp    # fir.load/store/array_coor walker
├── tools/fpa-tool/
│   └── main.cpp                # standalone CLI driver (no MlirOptMain)
├── tests/
│   ├── fortran/                # .f90 programs used for end-to-end tests
│   └── lit/                    # MLIR LIT unit tests for Phase 2
└── docs/
    ├── heuristics.md           # dependency assumptions & known limitations
    └── setup.md                # full build guide (macOS & GitHub Codespaces)
```

---

## Building and Running

### GitHub Codespaces (recommended — zero setup)

Open the repo in a Codespace, then:

```bash
# Install LLVM 18 + Flang
sudo apt-get install -y llvm-18 mlir-18-tools libmlir-18-dev \
    flang-18 libflang-18-dev libclang-cpp-18-dev

# Fix missing unversioned symlink
sudo ln -sf /usr/lib/llvm-18/lib/libclang-cpp.so.18.1 \
            /usr/lib/llvm-18/lib/libclang-cpp.so

# Build
mkdir build && cd build
cmake .. -DLLVM_BUILD_DIR=/usr/lib/llvm-18 -DCMAKE_BUILD_TYPE=Release
make -j$(nproc) fpa-tool
```

### Run on a Fortran file

```bash
export PATH="/usr/lib/llvm-18/bin:$PATH"

# Step 1 — emit FIR
flang-new -fc1 -emit-fir tests/fortran/trivial_parallel.f90 -o /tmp/out.fir

# Step 2 — analyse
./build/tools/fpa-tool/fpa-tool /tmp/out.fir
```

### Run all five tests

```bash
for f in tests/fortran/*.f90; do
  echo "=== $(basename $f) ==="
  flang-new -fc1 -emit-fir "$f" -o /tmp/t.fir 2>/dev/null && \
    ./build/tools/fpa-tool/fpa-tool /tmp/t.fir
done
```

---

## Implementation Status

- [x] Phase 1 — structural metadata (bounds, depth, op count)
- [x] Phase 2 — access classification (`fir.array_coor` + `fir.declare` stripping)
- [x] Phase 3 — index pattern matching (IV-derived vs IV±k offset)
- [x] Phase 4 — scalar reduction detection (`load → binop → store`)
- [x] Phase 5 — conservative final verdict
- [x] LIT test suite for Phase 2
- [x] Dependency assumptions document (`docs/heuristics.md`)

---

## License

MIT
