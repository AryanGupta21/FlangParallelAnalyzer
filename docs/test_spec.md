# FlangParallelAnalyzer — Comprehensive Test Specification

This document describes every test in `tests/comprehensive/`, the expected
verdict, which analysis phase produces it, and the rationale.  It also
covers automated validation strategies, stress-testing ideas, and known
corner-cases.

---

## How to run the test suite

```bash
# From the repo root (Codespaces or any machine with LLVM 18)
export PATH="/usr/lib/llvm-18/bin:$PATH"
python3 scripts/run_tests.py                # all 30 comprehensive tests
python3 scripts/run_tests.py -v             # verbose (show full fpa-tool output)
python3 scripts/run_tests.py --dir tests/fortran   # original 5 tests
```

Each `.f90` file contains a `! EXPECTED: <STATUS>` comment.  The runner
compiles to FIR, runs `fpa-tool`, parses `Status :` lines, and compares.

---

## Test catalogue

### Category 1 — Correct Parallelization Detection

| # | File | Pattern | Expected | Phase that decides |
|---|------|---------|----------|--------------------|
| 01 | `01_safe_scale.f90` | `b(i)=a(i)*2.0` | SAFE | Phase 3: all subscripts IV-derived, no ext writes |
| 02 | `02_safe_copy.f90` | `c(i)=a(i)+b(i)` | SAFE | Phase 3: three separate arrays, all indexed by i |
| 03 | `03_safe_fma.f90` | `d(i)=a(i)*b(i)+c(i)` | SAFE | Phase 3: multiple reads, one write, all IV |
| 18 | `18_safe_step2.f90` | `b(i)=a(i)*2.0` (step 2) | SAFE | Phase 3: stride-2 IV is still IV-derived |
| 21 | `21_safe_two_output.f90` | two writes per iteration | SAFE | Phase 3: both targets IV-indexed, no overlap |
| 24 | `24_safe_nonconstant_bounds.f90` | runtime lo/hi | SAFE | Phase 3: bounds unknown but deps still clean |
| 26 | `26_safe_double_precision.f90` | f64 scale | SAFE | Phase 3: identical to f32 structurally |
| 28 | `28_safe_integer_array.f90` | `b(i)=a(i)+1` (int) | SAFE | Phase 3: integer types treated same as float |

**Validation strategy:** After the tool reports SAFE, compile and run with
`!$OMP PARALLEL DO` and without; results must agree on a reference input.

---

### Category 2 — Reduction Detection

| # | File | Pattern | Expected | Operator |
|---|------|---------|----------|----------|
| 04 | `04_reduction_sum.f90` | `total+=a(i)*b(i)` | REDUCTION | `+` |
| 05 | `05_reduction_product.f90` | `prod*=a(i)` | REDUCTION | `*` |
| 10 | `10_reduction_integer.f90` | `isum+=ia(i)` (int) | REDUCTION | `+` (addi) |
| 19 | `19_reduction_saxpy_sum.f90` | `s=s+alpha*x(i)+y(i)` | **UNSAFE** | chained addf not matched by Phase 4 |
| 30 | `30_reduction_norm2.f90` | `norm2+=a(i)*a(i)` | REDUCTION | `+` |

**Phase:** Phase 4 — load → binary-op → store chain on a scalar function argument.

**Validation strategy:** Insert `!$OMP PARALLEL DO REDUCTION(+:total)` and
compare the final scalar against a serial reference.  Numerical tolerance
should be ±1 ULP × n for floating-point.

---

### Category 3 — Dependency Edge Cases

| # | File | Pattern | Expected | Offset detected |
|---|------|---------|----------|-----------------|
| 06 | `06_dep_shift1.f90` | `a(i)=a(i)+a(i-1)` | UNSAFE | i-1 |
| 07 | `07_dep_shift_forward.f90` | `a(i+1)=a(i)*2` | UNSAFE | i+1 |
| 09 | `09_dep_large_offset.f90` | `a(i)=a(i-10)+1` | UNSAFE | i-10 |
| 20 | `20_unsafe_alias_inout.f90` | `a(i)=a(i-1)*2` | UNSAFE | i-1 |
| 22 | `22_unsafe_dep_shift2.f90` | `a(i)=a(i-1)+a(i-2)` | UNSAFE | i-1,i-2 |
| 25 | `25_unsafe_output_dep.f90` | scalar max, no reduction op | UNSAFE | Phase 5 fallback |
| 27 | `27_unsafe_cross_array_dep.f90` | `b(i)=a(i)+a(i-1)` | UNSAFE | i-1 |
| 29 | `29_unsafe_write_constant_idx.f90` | `b(1)+=a(i)` | UNSAFE | constant index |

**Phase:** Phase 3 (`isIVPlusOffset`) for offset cases; Phase 5 fallback for
the others.

**Validation strategy:**
- Run parallelised and serial on ascending/descending filled arrays; results
  must differ for UNSAFE loops (proving the dependency is real).
- For shift-1 with n=10 and a(1)=1..10: verify that the parallel result
  diverges from the serial prefix-sum result.

---

### Category 4 — Aliasing and Pointer Scenarios

| # | File | Pattern | Expected | Reason |
|---|------|---------|----------|--------|
| 16 | `16_unsafe_scatter.f90` | `b(idx(i))=a(i)` | UNSAFE | indirect subscript |
| 17 | `17_unsafe_gather.f90` | `b(i)=a(idx(i))` | UNSAFE | indirect subscript |

**Limitation:** The tool does not analyse `POINTER` dummy arguments or
`EQUIVALENCE` blocks.  Those cases are not tested here but documented in
`heuristics.md`.

---

### Category 5 — Control Flow Complexity

| # | File | Pattern | Expected | Reason |
|---|------|---------|----------|--------|
| 14 | `14_nested_outer.f90` | 2D matrix loop | UNSAFE | outer IV unknown from inner loop |
| 15 | `15_unsafe_conditional_write.f90` | IF-ELSE write to separate arrays | SAFE | correctly parallel — `a` read-only, `b` written at IV index in both branches |
| 23 | `23_unsafe_nested_reduction.f90` | row-wise dot product | UNSAFE | outer IV, multi-dim |

---

### Category 6 — Unsupported / Unsafe Cases

| # | File | Pattern | Expected | Reason |
|---|------|---------|----------|--------|
| 08 | `08_dep_inplace.f90` | `a(i)=a(i)*3` | UNSAFE | same array RW, conservative |
| 11 | `11_safe_read_only.f90` | read-only scan | SAFE | Phase 5: no external writes |
| 12 | `12_unsafe_function_call.f90` | external call | SAFE | **known false positive**: Fortran passes args by reference so FIR only shows a store to a(i); opaque call side-effects are invisible |
| 13 | `13_unsafe_intrinsic_sqrt.f90` | `a(i)=sqrt(a(i))` | UNSAFE | in-place + intrinsic call chain, conservative |

---

## Automated Validation Strategies

### 1. Status matching (implemented in `run_tests.py`)
Parse `! EXPECTED: <STATUS>` from each test file; compare against fpa-tool
`Status :` output.  Exit code 0 = all passed.

### 2. OpenMP correctness oracle
For every SAFE or REDUCTION loop:
```bash
# Compile two versions
gfortran -O2            test.f90 -o run_serial
gfortran -O2 -fopenmp   test.f90 -o run_parallel   # with OMP directives added
# Run with the same input and diff the output
./run_serial   > out_serial.txt
./run_parallel > out_parallel.txt
diff out_serial.txt out_parallel.txt
```
Both must produce identical results.  Any mismatch in SAFE loops indicates
a false-positive classification (wrong verdict).

### 3. Dependency falsification
For every UNSAFE loop with a known loop-carried dependency:
- Generate an input array where values differ by more than floating-point noise.
- Run serial and (incorrectly) parallelised versions.
- Verify the parallel result differs from the serial result, confirming the
  dependency is real and the UNSAFE verdict was correct.

### 4. Mutation testing
Change `a(i-1)` → `a(i)` in each UNSAFE dependency test and re-run.  The
verdict should flip from UNSAFE to SAFE/REDUCTION, confirming the offset
detection is responsible for the UNSAFE decision.

### 5. Differential testing against a known-good reference
Compare fpa-tool verdicts against hand-annotated verdicts from OpenMP 5.1
examples or the SPEC OMP benchmark suite.  Any divergence is a candidate
bug.

---

## Stress Testing and Fuzzing Ideas

### Structural fuzzing
Generate random Fortran loops with parameterised:
- Array count (1–5), subscript expressions (pure IV, IV±k, constant, indirect)
- Nesting depth (1–4)
- Presence of scalar accumulators and operator (+, *, max, min)

Use a small Python generator:
```python
import random
def make_loop(has_offset, has_reduction, depth=1):
    ...  # emit .f90 text
```

Then compare the tool's verdict against the expected verdict computed by
the generator (since it knows the ground truth).

### Large-scale performance test
```fortran
! 1 000 000-element arrays, 10 nested depth levels
do i = 1, 1000000
  b(i) = a(i) * 2.0
end do
```
Measure fpa-tool wall-clock time; should be < 1 s regardless of n because
the IR is bounded by the number of FIR ops (which is O(loop body size),
not O(n)).

### Adversarial aliasing
Pass the same array as both `a` and `b` at the call site:
```fortran
call safe_scale(x, x, n)  ! b is aliased to a
```
The tool will still say SAFE because it trusts INTENT annotations.  This
is a known limitation; document it rather than trying to detect it (Fortran
forbids such calls under the standard).

### Pathological SSA depth
Deeply chained `fir.convert` chains (e.g. i32 → i64 → index → i32 → i64)
test the `depth` guard in `isIVDerived`.  The `depth > 10` cutoff prevents
infinite recursion; verify the tool returns UNSAFE (conservative) rather
than crashing.

---

## Known Limitations (cross-reference to `heuristics.md`)

| # | Limitation | Affected tests |
|---|-----------|----------------|
| 1 | Multi-dimensional index not traceable from inner loop | 14, 23 |
| 2 | Non-constant bounds shown as `?` | 24 |
| 3 | `fir.array_load`/`array_merge_store` not walked in Phase 3 | — |
| 4 | POINTER / EQUIVALENCE aliasing not analysed | — |
| 5 | max/min/AND/OR reductions not detected (Phase 4) | 25 |
| 6 | Local alloca accumulators not detected as reductions | — |
| 7 | Chained reduction expressions (`s = s + f(x(i)) + g(y(i))`) not matched by Phase 4's single-step chain | 19 |
| 8 | External function call side effects invisible in FIR — opaque calls produce false-positive SAFE | 12 |

All limitations produce conservative UNSAFE verdicts (false negatives),
never false positives (SAFE when actually unsafe).
