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
  echo ""
  echo "  ERROR: fpa-tool not found at '$FPA_TOOL'"
  echo ""
  echo "  fpa-tool needs to be compiled before tests can run."
  echo "  It links against LLVM/Flang, which must also be built first."
  echo ""
  echo "  Full step-by-step instructions:"
  echo "    → docs/setup.md"
  echo ""
  echo "  Short version:"
  echo "    1. brew install ninja llvm"
  echo "    2. git clone --branch llvmorg-18.1.0 --depth 1 \\"
  echo "         https://github.com/llvm/llvm-project.git"
  echo "    3. cd llvm-project/build && cmake ../llvm -G Ninja \\"
  echo "         -DLLVM_ENABLE_PROJECTS='clang;flang;mlir' \\"
  echo "         -DLLVM_TARGETS_TO_BUILD=AArch64 \\"
  echo "         -DCMAKE_BUILD_TYPE=RelWithDebInfo"
  echo "       ninja flang-new mlir-opt FileCheck"
  echo "    4. cd paraloop && mkdir build && cd build"
  echo "       cmake .. -DLLVM_BUILD_DIR=~/Developer/llvm-project/build \\"
  echo "                -DLLVM_SOURCE_DIR=~/Developer/llvm-project"
  echo "       ninja fpa-tool"
  echo "    5. FPA_TOOL=build/bin/fpa-tool bash tests/run_lit.sh"
  echo ""
  exit 1
fi

if ! command -v "$FILECHECK" &>/dev/null; then
  echo ""
  echo "  ERROR: FileCheck not found."
  echo ""
  echo "  FileCheck ships with LLVM. After building LLVM (see docs/setup.md):"
  echo "    export FILECHECK=~/Developer/llvm-project/build/bin/FileCheck"
  echo ""
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
