# Dependency Assumptions and Heuristics

This document explains the analysis decisions made by each phase of
FlangParallelAnalyzer and the assumptions on which they rest.

---

## Phase 1 — Structural Metadata

**What it does:** Extracts loop bounds (if constant), nesting depth, direct
child count, and body op count from each `fir.do_loop`.

**Assumptions:**
- Loop bounds that are not compile-time constants are left as `?`; no
  attempt is made to prove them positive or non-empty.  An empty loop is
  trivially parallel but we do not special-case it.
- Nesting depth is measured by counting ancestor `fir.do_loop` ops.  This
  is exact regardless of inlining or restructuring.

---

## Phase 2 — Memory Access Classification

**What it does:** Walks every `fir.load`, `fir.store`, `fir.array_load`, and
`fir.array_merge_store` in the loop body and records, for each unique base
reference, whether it is read, written, or both, and whether it originates
inside or outside the loop.

**Key implementation choices:**

| FIR construct | Handling |
|---|---|
| `fir.coordinate_of` | Stripped by `getBaseRef` to reach the root array ref |
| `fir.array_coor` | Stripped by `getBaseRef` (Flang's primary array-element op) |
| `fir.declare` | Stripped by `getBaseRef` (metadata wrapper added at function entry) |
| `fir.alloca` result | Defined outside the loop but represents a Fortran local variable; classified as **external** at this phase, then filtered in Phase 3 |
| Loop induction variable | Skipped entirely — it is the loop's own region block argument |

**Assumptions:**
- A reference defined by a block argument (`func.func` parameter) is always
  external to the loop.
- A reference defined by an op that is NOT an ancestor of the loop is
  external, even if it is in the same function (e.g. a local `fir.alloca`).
- The Fortran compiler never generates aliased references for distinct
  dummy arguments (`INTENT(IN)` / `INTENT(OUT)` separation is trusted).

---

## Phase 3 — Index Pattern Matching

**What it does:** Inspects the subscript operands of every `fir.array_coor`
inside the loop and classifies each subscript as:

1. **IV-derived** — traces back to the loop induction variable or iter_arg
   through type conversions (`fir.convert`, `arith.index_cast`, `arith.extsi`,
   `arith.trunci`) and Fortran loop-variable alloca loads.
2. **IV ± constant** — the subscript is `i + k` or `i - k` for a nonzero
   compile-time constant `k`, detected via `arith.addi`/`arith.subi` with a
   constant operand.
3. **Unknown** — anything else (e.g. another array's element, an outer-loop
   variable from a multi-dimensional nest).

**Safety decisions from Phase 3:**

| Observation | Verdict |
|---|---|
| Any subscript is IV ± k (k ≠ 0) | **UNSAFE** — iteration i reads/writes a location touched by iteration i±k |
| All subscripts are plain IV AND ext-readwrites = 0 after filtering allocas | **SAFE** |
| Any unknown subscript | Deferred to Phase 4/5 |

**Assumptions:**
- The Fortran loop variable `i` is stored from the iter_arg into a local
  `fir.alloca` at the top of every iteration body.  Any `fir.load` of that
  alloca inside the loop is considered IV-derived.
- `fir.alloca`-backed scalars (the loop variables `i`, `j`, …) are **not**
  cross-iteration dependencies.  They are filtered out before the SAFE
  decision so their RW pattern does not cause a false UNSAFE verdict.
- Only constant offsets are checked.  Non-constant (data-dependent) offsets
  are conservatively classified as Unknown.

---

## Phase 4 — Reduction Detection

**What it does:** Looks for the scalar accumulation pattern on every external
non-alloca scalar that is both read and written:

```
%old = fir.load  %acc
%new = arith.addf %old, <expr>   ! or mulf / addi / muli
       fir.store %new to %acc
```

If this exact load → binary-op → store chain is found on the same reference,
the loop is classified as **REDUCTION** and an OpenMP directive with the
appropriate operator (`+` or `*`) is emitted.

**Assumptions:**
- Only `+` and `*` are currently matched.  `max`, `min`, `.AND.`, `.OR.`
  reductions exist in Fortran but are not yet detected (they would fall
  through to Phase 5 as conservative UNSAFE).
- The accumulator must be a function argument (block argument), not an
  `fir.alloca` local.  A local scalar accumulator that is initialized before
  the loop and read after it looks identical to the loop-variable noise at
  this level of analysis and is left to future work.
- A single-ref check is used: the same `%acc` value must appear in both the
  load's memref and the store's memref (after `getBaseRef` stripping).

---

## Phase 5 — Final Conservative Verdict

Any loop still classified **UNKNOWN** after Phases 3 and 4 receives a
conservative verdict:

- If there are **no external writes at all** → **SAFE** (read-only loop).
- Otherwise → **UNSAFE** with the message *"Analysis inconclusive"*.

**Rationale:** False negatives (missed parallelism opportunities) are
preferable to false positives (incorrect parallel execution that produces
wrong results).  The tool is intended as a hint generator, not a verifier.

---

## Known Limitations

1. **Multi-dimensional array nests:** The inner loop of a doubly-nested loop
   sees the outer loop's induction variable as an "unknown" index (it is not
   the inner loop's IV), so the inner loop is conservatively UNSAFE even when
   it is safe.

2. **Non-constant bounds:** Loop trip counts that come from function arguments
   show as `?` in the output; the analysis still runs but the bounds section
   of the report is uninformative.

3. **`fir.array_load` / `fir.array_merge_store` (HLFIR style):** Classified
   correctly as read/write in Phase 2 but their subscripts are not yet walked
   in Phase 3 (they use a different index representation).  Such loops fall
   through to Phase 5 as conservative UNSAFE.

4. **Aliasing via `EQUIVALENCE` or `POINTER`:** Not analysed.  Fortran
   `POINTER` dummy arguments that alias each other would produce incorrect
   SAFE verdicts.
