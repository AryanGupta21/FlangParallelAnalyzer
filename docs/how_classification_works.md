# How the Tool Classifies Loops

This document explains — in plain terms — exactly how FlangParallelAnalyzer
looks at a Fortran DO loop and decides whether it is **SAFE**, **REDUCTION**,
or **UNSAFE**.

---

## The Big Picture

The tool never looks at the `.f90` source text directly.  Instead it reads
the **FIR** (Fortran Intermediate Representation) that Flang produces —
a structured, typed tree where every array access, load, store, and loop is
an explicit node.  That makes the analysis precise: there is no guessing about
implicit types or source formatting.

The decision is made in **five sequential phases**.  Each phase either reaches
a verdict and stops, or passes the loop to the next phase.

```
Loop enters
    │
    ▼
Phase 1 — Structural metadata      (never verdicts, just gathers facts)
    │
    ▼
Phase 2 — Memory access catalogue  (what is read? what is written?)
    │
    ▼
Phase 3 — Index pattern check      ──► UNSAFE  (if offset subscript found)
    │                               ──► SAFE    (if all IV, no ext writes)
    ▼
Phase 4 — Reduction detection      ──► REDUCTION (if scalar acc pattern found)
    │
    ▼
Phase 5 — Conservative fallback    ──► SAFE    (if nothing is written)
                                   ──► UNSAFE  (everything else)
```

---

## Phase 1 — Structural Metadata

**What it collects:**
- Loop bounds (lower, upper, step) — constant values if available, `?` if
  they come from function arguments
- Nesting depth — how many outer `fir.do_loop` ops wrap this one
- Number of direct child loops
- Total count of IR ops in the body

**What it decides:** Nothing.  This phase only gathers data used for the
output report (the `Bounds :` line).

---

## Phase 2 — Memory Access Catalogue

The tool walks every **load**, **store**, and **array element access** inside
the loop body and builds a table:

| Reference | Direction | Origin |
|---|---|---|
| `%arg0` (array a) | Read | External (function argument) |
| `%arg1` (array b) | Write | External (function argument) |
| `%i_alloca` (loop var i) | Read+Write | Internal alloca — filtered out |

**Key decisions made here:**

- `fir.array_coor` ops (array element accesses) are stripped back to their
  root array reference via `getBaseRef()`.  This peels off index wrappers
  so we compare arrays, not individual element addresses.
- A reference is **external** if it is defined outside the loop (e.g. a
  function argument or an allocation done before the loop).
- The loop induction variable itself and its backing `fir.alloca` are
  **filtered out** — they change every iteration by design and are not
  cross-iteration dependencies.

---

## Phase 3 — Index Pattern Check

This is the core of the dependency analysis.  For every array access inside
the loop, the tool looks at the **subscript** — the value used as the index —
and asks: *what is this index derived from?*

### Case A — IV-derived subscript  →  no conflict
```fortran
b(i) = a(i) * 2.0
```
The subscript is `i`, which is the loop induction variable.
Iteration 5 accesses `a(5)` and `b(5)`.  Iteration 6 accesses `a(6)` and
`b(6)`.  They never touch the same memory cell.

The tool traces the subscript SSA value back through type conversions
(`fir.convert`, `arith.index_cast`) and the Fortran loop-variable bookkeeping
(`fir.store i → alloca`, `fir.load alloca`) until it reaches the loop's
induction variable.  If it does, the subscript is **IV-derived**.

### Case B — IV ± constant  →  UNSAFE immediately
```fortran
a(i) = a(i) + a(i-1)
```
The subscript `i-1` is detected as `arith.subi(i, 1)` — the induction
variable minus a nonzero constant.  This means iteration 5 reads `a(4)`,
which iteration 4 writes.  **Loop-carried dependency confirmed → UNSAFE.**

The tool checks for `arith.addi` and `arith.subi` where one operand traces
back to the IV and the other is a compile-time constant.  Any nonzero
constant offset triggers UNSAFE.

### Case C — Unknown subscript  →  deferred to Phase 4/5
```fortran
b(idx(i)) = a(i)     ! subscript of b is a(idx(i)), not the IV
```
The subscript of `b` comes from loading another array.  The tool cannot
prove it is either IV-derived or a constant offset, so it calls this
**unknown** and moves on.

### SAFE verdict from Phase 3
After checking all subscripts:
- If **any** subscript is IV ± k (k ≠ 0) → **UNSAFE** (stop here)
- If **all** subscripts are IV-derived AND there are no external
  read-write references left (after filtering loop-variable allocas) → **SAFE**
- Otherwise → fall through to Phase 4

---

## Phase 4 — Reduction Detection

A reduction is a scalar variable that accumulates a value across all
iterations.  The tool looks for this exact three-step pattern on any
external scalar that is both read and written:

```
Step 1:  %old  = fir.load  %accumulator
Step 2:  %new  = arith.addf %old, <any expression>   ← or addi / mulf / muli
Step 3:          fir.store  %new  to %accumulator
```

If all three steps are found on the same `%accumulator` reference, the loop
is a **REDUCTION**.

The operator detected in Step 2 determines the OpenMP clause:
- `arith.addf` or `arith.addi` → `REDUCTION(+:var)`
- `arith.mulf` or `arith.muli` → `REDUCTION(*:var)`

**What Phase 4 does NOT catch:**
- Chained reductions like `s = s + f(x(i)) + g(y(i))` — the two `addf` ops
  mean the final store's source is not directly the result of operating on
  the loaded value.
- `max`, `min`, `.AND.`, `.OR.` reductions — different op patterns, not yet
  implemented.
- A local variable accumulator (backed by `fir.alloca`) — the tool only
  checks function-argument scalars.

---

## Phase 5 — Conservative Fallback

Any loop that made it through Phases 3 and 4 without a verdict gets a
final conservative decision:

- **No external writes at all** → **SAFE**
  (The loop is read-only.  Reading in parallel is always safe.)

- **Anything else** → **UNSAFE**
  ("I couldn't prove it safe, so I won't risk it.")

This is intentionally pessimistic.  A false negative (saying UNSAFE when
the loop is actually safe) only means a missed speedup.  A false positive
(saying SAFE when the loop has a hidden dependency) would produce
**silently wrong results** — which is far worse.

---

## How Each Verdict Is Reached — Concrete Examples

### Example 1 — SAFE
```fortran
do i = 1, n
  b(i) = a(i) * 2.0
end do
```
- Phase 2: `a` → Read/External, `b` → Write/External
- Phase 3: subscript of `a(i)` is the IV → IV-derived ✓
           subscript of `b(i)` is the IV → IV-derived ✓
           No offset found.  No external read-writes remaining.
- **Verdict: SAFE** (Phase 3)

---

### Example 2 — UNSAFE (offset subscript)
```fortran
do i = 2, n
  a(i) = a(i) + a(i-1)
end do
```
- Phase 2: `a` → Read+Write/External
- Phase 3: subscript of the second `a(i-1)` → `arith.subi(i, 1)` → IV − 1
           Nonzero constant offset detected immediately.
- **Verdict: UNSAFE** (Phase 3)

---

### Example 3 — REDUCTION
```fortran
do i = 1, n
  total = total + a(i) * b(i)
end do
```
- Phase 2: `a` → Read/External, `b` → Read/External, `total` → Read+Write/External (scalar)
- Phase 3: `a(i)` and `b(i)` are IV-derived.  `total` is a scalar (not an array) —
           no subscript to check.  External RW scalar present → not SAFE yet.
- Phase 4: Finds `fir.load %total → arith.addf → fir.store %total` chain. ✓
- **Verdict: REDUCTION** (Phase 4)

---

### Example 4 — UNSAFE (conservative fallback)
```fortran
do i = 1, n
  b(idx(i)) = a(i)
end do
```
- Phase 2: `a` → Read/External, `b` → Write/External, `idx` → Read/External
- Phase 3: subscript of `b(idx(i))` traces to a load from `idx` → **unknown**.
           Not IV ± k, so not immediately UNSAFE.
           External write present, so not immediately SAFE.
- Phase 4: No scalar accumulator pattern.
- Phase 5: External writes exist → **UNSAFE** (conservative).

---

## Summary

| What the tool sees | Verdict | Phase |
|---|---|---|
| All array subscripts trace to the loop IV, no external RW scalars | **SAFE** | 3 |
| Any subscript is `IV ± nonzero_constant` | **UNSAFE** | 3 |
| Scalar with `load → add/mul → store` chain | **REDUCTION** | 4 |
| No external writes at all | **SAFE** | 5 |
| Anything else (unknown subscript, opaque call, complex control flow) | **UNSAFE** | 5 |

The tool always chooses the **safe side** when in doubt.
