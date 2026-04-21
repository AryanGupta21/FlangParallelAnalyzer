#!/usr/bin/env bash
# run_tests.sh — run all Fortran test programs through fpa-tool
#
# Usage:
#   cd tests && bash run_tests.sh
#
# Requires:
#   FLANG_BIN  — path to flang-new binary  (default: flang-new on PATH)
#   FPA_BIN    — path to fpa-tool binary   (default: ../build/bin/fpa-tool)

set -euo pipefail

FLANG_BIN="${FLANG_BIN:-flang-new}"
FPA_BIN="${FPA_BIN:-../build/bin/fpa-tool}"
FORTRAN_DIR="$(dirname "$0")/fortran"

# ── Checks ────────────────────────────────────────────────────────────────

if ! command -v "$FLANG_BIN" &>/dev/null; then
  echo "ERROR: flang-new not found. Set FLANG_BIN=/path/to/flang-new"
  exit 1
fi

if [ ! -x "$FPA_BIN" ]; then
  echo "ERROR: fpa-tool not found at $FPA_BIN"
  echo "       Build first:  cmake --build ../build"
  echo "       Or set:       FPA_BIN=/path/to/fpa-tool"
  exit 1
fi

# ── Run ───────────────────────────────────────────────────────────────────

PASS=0
FAIL=0

run_test() {
  local f90="$1"
  local name
  name="$(basename "$f90" .f90)"

  echo ""
  echo "════════════════════════════════════════════════════════════"
  echo "  TEST: $name"
  echo "════════════════════════════════════════════════════════════"

  # Lower Fortran → FIR, pipe straight into fpa-tool
  if "$FLANG_BIN" -fc1 -emit-fir "$f90" -o - 2>/dev/null \
       | "$FPA_BIN" --fir-loop-parallel-analysis -; then
    PASS=$((PASS + 1))
  else
    echo "  [FAILED] fpa-tool exited with error"
    FAIL=$((FAIL + 1))
  fi
}

for f90 in "$FORTRAN_DIR"/*.f90; do
  run_test "$f90"
done

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  Results: $PASS passed, $FAIL failed"
echo "════════════════════════════════════════════════════════════"

[ "$FAIL" -eq 0 ]
