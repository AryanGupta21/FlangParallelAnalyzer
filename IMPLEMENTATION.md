# IMPLEMENTATION

## Toolchain and dependencies

| Component | Version | Role |
|-----------|---------|------|
| LLVM / MLIR | 18 | IR infrastructure, pass framework, FIR dialect |
| Flang (`flang-new`) | 18 | Fortran → FIR compiler |
| `libflang-18-dev` | 18 | FIR op headers (`fir::DoLoopOp`, `fir::LoadOp`, …) |
| `libmlir-18-dev` | 18 | `mlir::PassWrapper`, `op.walk`, `dyn_cast` |
| `libclang-cpp-18-dev` | 18 | Transitive dep of MLIR cmake config |
| CMake | ≥ 3.20 | Build system |
| Python 3 | ≥ 3.9 | `report.py`, `run_tests.py` |

---

## Source layout

```
FlangParallelAnalyzer/
├── include/FlangParallelAnalyzer/
│   ├── LoopParallelAnalysis.h   — LoopSafety enum, LoopInfo struct, pass factory
│   └── AccessClassifier.h      — AccessRecord, AccessSummary, AccessClassifier
├── lib/
│   ├── LoopParallelAnalysis.cpp — main pass: all five phases + printer
│   ├── AccessClassifier.cpp    — fir.load / fir.store / array_coor walker
│   └── CMakeLists.txt
├── tools/fpa-tool/
│   ├── main.cpp                — CLI driver (parse → PassManager → exit)
│   └── CMakeLists.txt
├── scripts/
│   ├── build.sh                — one-command dependency + build script
│   ├── run.sh                  — compile a .f90 to FIR and run the tool
│   ├── report.py               — HTML report generator
│   └── run_tests.py            — automated test runner
├── tests/
│   ├── fortran/                — 5 original hand-annotated test cases
│   ├── comprehensive/          — 30 comprehensive test cases (EXPECTED: comments)
│   └── lit/                    — 4 MLIR LIT tests for Phase 2 in isolation
└── CMakeLists.txt
```

---

## CMake build structure

The root `CMakeLists.txt` locates LLVM/MLIR/Flang via `find_package` with
`CMAKE_PREFIX_PATH` pointing at `${LLVM_BUILD_DIR}/lib/cmake/{llvm,mlir,flang}`.
It also calls `link_directories("${LLVM_BUILD_DIR}/lib")` so that FIR libraries
(shipped as pre-built `.a` files by the apt package) can be named directly in
`target_link_libraries` without cmake targets.

**`lib/CMakeLists.txt`** builds the analysis library:
```cmake
add_library(FPALoopAnalysis STATIC
  LoopParallelAnalysis.cpp
  AccessClassifier.cpp
)

target_link_libraries(FPALoopAnalysis PUBLIC
  MLIRPass  MLIRSupport  MLIRFuncDialect  MLIRArithDialect
  FIRDialect  FIRDialectSupport  FIRSupport
)
```

**`tools/fpa-tool/CMakeLists.txt`** builds the CLI:
```cmake
add_executable(fpa-tool main.cpp)

target_link_libraries(fpa-tool PRIVATE
  FPALoopAnalysis
  MLIRPass  MLIRSupport  MLIRParser  MLIRIR
  MLIRAsmParser  MLIRBytecodeReader
  MLIRFuncDialect  MLIRArithDialect  MLIRMathDialect
  FIRDialect  FIRDialectSupport  FIRSupport
)
```

`MlirOptMain` is intentionally avoided — it pulls in `clang-cpp` as a
transitive dependency, which fails to link against apt-installed LLVM 18.

---

## Key MLIR / FIR APIs used

### Pass structure

```cpp
struct LoopParallelAnalysisPass
    : public PassWrapper<LoopParallelAnalysisPass,
                         OperationPass<func::FuncOp>> {
  StringRef getArgument()    const override { return "fir-loop-parallel-analysis"; }
  void runOnOperation() override;
};
```

Registered via `PassRegistration<LoopParallelAnalysisPass>()`. Run by
`pm.addNestedPass<mlir::func::FuncOp>(fpa::createLoopParallelAnalysisPass())`.

### Phase 1 — structural metadata

```cpp
LoopInfo info;
info.loc        = loop.getLoc();
info.lowerBound = getConstantIndex(loop.getLowerBound());
info.upperBound = getConstantIndex(loop.getUpperBound());
info.step       = getConstantIndex(loop.getStep());

// Nesting depth: count ancestor fir.do_loop ops
Operation *parent = loop->getParentOp();
while (parent) {
  if (isa<fir::DoLoopOp>(parent)) ++info.nestDepth;
  parent = parent->getParentOp();
}
```

### Phase 2 — access classification (`AccessClassifier`)

`AccessClassifier::classify(loop)` walks the loop body and builds one
`AccessRecord` per unique base reference:

```cpp
loop.walk([&](Operation *op) {
  if (auto load = dyn_cast<fir::LoadOp>(op))
    record(load.getMemref(), /*read=*/true,  /*write=*/false);
  if (auto store = dyn_cast<fir::StoreOp>(op))
    record(store.getMemref(), /*read=*/false, /*write=*/true);
  if (auto arrLoad = dyn_cast<fir::ArrayLoadOp>(op))
    record(arrLoad.getMemref(), /*read=*/true,  /*write=*/false);
  if (auto arrStore = dyn_cast<fir::ArrayMergeStoreOp>(op))
    record(arrStore.getMemref(), /*read=*/false, /*write=*/true);
});
```

`getBaseRef()` strips `fir::CoordinateOp`, `fir::ArrayCoorOp`, and
`fir::DeclareOp` chains to find the root `fir.ref` value.

`isExternalToLoop()` returns true when the defining op is outside the loop
region (or when the value is a block argument, i.e. a function parameter).

### Phase 3 — index pattern matching

Two recursive helpers trace subscript values back through the def-use chain:

```cpp
// Returns true when val traces back to the loop IV through type conversions
// and the Fortran loop-variable alloca load/store bookkeeping.
static bool isIVDerived(Value val, fir::DoLoopOp loop, unsigned depth = 0);

// Returns true when val is IV + k (k ≠ 0); sets 'offset' to k.
// Handles arith::AddIOp and arith::SubIOp with a constant operand.
static bool isIVPlusOffset(Value val, fir::DoLoopOp loop,
                            int64_t &offset, unsigned depth = 0);
```

Both strip `fir::ConvertOp`, `arith::IndexCastOp`, `arith::ExtSIOp`, and
`arith::TruncIOp` transparently. The Fortran loop-variable bookkeeping pattern
(`fir.store %iv to %alloca` / `fir.load %alloca`) is handled explicitly in
`isIVDerived`.

If an `a(i±k)` subscript is found, the loop is immediately classified UNSAFE
with `"Loop-carried dependency: array accessed at i±k offset"`.

If all external array subscripts are plain IV-derived, the loop is classified
SAFE — after filtering out `fir::AllocaOp`-based read-write scalars (the
Fortran loop-variable bookkeeping allocas, which are not real cross-iteration
dependencies).

### Phase 4 — reduction detection

```cpp
// Pattern: fir.load %acc → arith.addf/mulf → fir.store %acc (same loop body)
loop.walk([&](fir::LoadOp load) {
  Value accRef = AccessClassifier::getBaseRef(load.getMemref());
  Value loaded = load.getResult();
  for (Operation *user : loaded.getUsers()) {
    bool isAdd = isa<arith::AddFOp, arith::AddIOp>(user);
    bool isMul = isa<arith::MulFOp, arith::MulIOp>(user);
    if (!isAdd && !isMul) continue;
    for (Operation *storeUser : user->getResult(0).getUsers())
      if (auto st = dyn_cast<fir::StoreOp>(storeUser))
        if (AccessClassifier::getBaseRef(st.getMemref()) == accRef)
          → REDUCTION
  }
});
```

Only runs on external, non-array, non-alloca read-write scalars (i.e. real
function-argument accumulators). Emits `!$OMP PARALLEL DO REDUCTION(+:<var>)`
or `REDUCTION(*:<var>)` depending on the detected op type.

### Phase 5 — conservative fallback

Any loop still `LoopSafety::Unknown` after Phase 4 is classified SAFE if the
access summary shows no external writes at all, or UNSAFE otherwise. This is
the conservative catch-all for patterns none of the earlier phases could classify
positively.

---

## CLI driver (`tools/fpa-tool/main.cpp`)

```cpp
// Register dialects
mlir::DialectRegistry registry;
registry.insert<mlir::func::FuncDialect, mlir::arith::ArithDialect,
                mlir::math::MathDialect, fir::FIROpsDialect>();
mlir::MLIRContext context(registry);
context.allowUnregisteredDialects(true); // flang emits #dlti and !llvm.ptr

// Parse .fir file
mlir::ParserConfig config(&context);
auto module = mlir::parseSourceFile<mlir::ModuleOp>(argv[1], config);

// Run pass
mlir::PassManager pm(&context);
pm.addNestedPass<mlir::func::FuncOp>(fpa::createLoopParallelAnalysisPass());
pm.run(*module);
```

`allowUnregisteredDialects(true)` is required because Flang emits `#dlti`
attributes and `!llvm.ptr` types that we do not analyse but must not reject.

---

## Output format

```
[FlangParallelAnalyzer] Function: <name>
------------------------------------------------------------
  Loop #N @ <file>:<line>
  Bounds : [lo .. hi step s]  depth=D
  Access : ext-reads=R  ext-writes=W  ext-readwrites=RW  local-writes=L
           [R]  array  — %arg0
           [W]  array  — %arg1
           [RW] scalar — %3
  Status : SAFE | REDUCTION | UNSAFE | UNKNOWN
  Hint   : !$OMP PARALLEL DO            (if SAFE)
           !$OMP PARALLEL DO REDUCTION(+:%4)  (if REDUCTION)
           ! Cannot parallelize         (if UNSAFE)
  Reason : <one-line explanation>
------------------------------------------------------------
```

Source location is recovered from the MLIR `loc(...)` attribute stored on
each `fir.do_loop`, cast to `FileLineColLoc` to extract filename and line number.

---

## How to add a new pattern

1. Add a `LoopSafety` enum value in `LoopParallelAnalysis.h` if needed.
2. Add detection logic in the appropriate phase in `LoopParallelAnalysis.cpp`.
3. Add a Fortran test case under `tests/comprehensive/` with a
   `! EXPECTED: <STATUS>` comment in the header.
4. Verify with `python3 scripts/run_tests.py tests/comprehensive/<new_file>.f90`.
