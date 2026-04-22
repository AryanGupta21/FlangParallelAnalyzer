#!/usr/bin/env bash
# run_lit.sh — Run the LIT (.mlir) test suite
#
# What this does:
#   Feeds each hand-crafted FIR file (.mlir) directly to fpa-tool and
#   checks its output against the // CHECK: patterns using FileCheck.
#   No need for flang-new — tests run against FIR written by hand.
#
# Usage:
#   bash tests/run_lit.sh                   # run all lit tests
#   bash tests/run_lit.sh phase2_scalar_rw  # run one test by name
#
# Requirements:
#   FPA_TOOL   — path to fpa-tool binary   (default: ../build/bin/fpa-tool)
#   FILECHECK  — path to FileCheck binary  (default: FileCheck on PATH)
#
# FileCheck is shipped with LLVM.  If you built LLVM it lives at:
#   /path/to/llvm-project/build/bin/FileCheck

set -euo pipefail

FPA_TOOL="${FPA_TOOL:-../build/bin/fpa-tool}"
FILECHECK="${FILECHECK:-FileCheck}"
LIT_DIR="$(dirname "$0")/lit"
FILTER="${1:-}"   # optional: substring to match test file names

# ── Pre-flight checks ─────────────────────────────────────────────────────

if [ ! -x "$FPA_TOOL" ]; then
  echo "ERROR: fpa-tool not found at '$FPA_TOOL'"
  echo "       Build first: cmake --build ../build"
  echo "       Or set:      FPA_TOOL=/path/to/fpa-tool"
  exit 1
fi

if ! command -v "$FILECHECK" &>/dev/null; then
  echo "ERROR: FileCheck not found."
  echo "       It ships with LLVM: /path/to/llvm-project/build/bin/FileCheck"
  echo "       Set: FILECHECK=/path/to/FileCheck"
  exit 1
fi

# ── Runner ────────────────────────────────────────────────────────────────

PASS=0; FAIL=0; SKIP=0
FAILED_TESTS=()

run_one() {
  local mlir_file="$1"
  local name
  name="$(basename "$mlir_file" .mlir)"

  # Apply filter if provided
  if [[ -n "$FILTER" && "$name" != *"$FILTER"* ]]; then
    SKIP=$((SKIP + 1))
    return
  fi

  printf "  %-40s " "$name"

  # Extract the RUN line from the test file.
  # Format:  // RUN: %fpa-tool --flag %s 2>&1 | %filecheck %s
  run_line=$(grep -m1 '^// RUN:' "$mlir_file" | sed 's|^// RUN: ||')

  if [[ -z "$run_line" ]]; then
    echo "SKIP (no RUN line)"
    SKIP=$((SKIP + 1))
    return
  fi

  # Substitute placeholders
  run_line="${run_line//%fpa-tool/$FPA_TOOL}"
  run_line="${run_line//%filecheck/$FILECHECK}"
  run_line="${run_line//%s/$mlir_file}"

  # Execute and capture output
  if eval "$run_line" > /tmp/fpa_test_out 2>&1; then
    echo "PASS"
    PASS=$((PASS + 1))
  else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    FAILED_TESTS+=("$name")
    # Show the failure details
    echo ""
    echo "  ── FileCheck output ──────────────────────────────────────"
    cat /tmp/fpa_test_out | sed 's/^/  /'
    echo "  ──────────────────────────────────────────────────────────"
  fi
}

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║         FlangParallelAnalyzer — LIT Test Suite           ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

for mlir_file in "$LIT_DIR"/*.mlir; do
  run_one "$mlir_file"
done

echo ""
echo "──────────────────────────────────────────────────────────"
printf "  Results: %d passed, %d failed, %d skipped\n" "$PASS" "$FAIL" "$SKIP"

if [ "${#FAILED_TESTS[@]}" -gt 0 ]; then
  echo ""
  echo "  Failed tests:"
  for t in "${FAILED_TESTS[@]}"; do
    echo "    ✗ $t"
  done
fi

echo "──────────────────────────────────────────────────────────"
echo ""

[ "$FAIL" -eq 0 ]
