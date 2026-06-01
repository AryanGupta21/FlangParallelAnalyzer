#!/usr/bin/env bash
# run.sh — Compile a Fortran source file to FIR and run FlangParallelAnalyzer
#
# Usage:
#   bash scripts/run.sh <path/to/file.f90>
#
# Examples:
#   bash scripts/run.sh tests/fortran/trivial_parallel.f90
#   bash scripts/run.sh tests/comprehensive/04_reduction_sum.f90

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <fortran-file.f90>"
    echo ""
    echo "Examples:"
    echo "  $0 tests/fortran/trivial_parallel.f90"
    echo "  $0 tests/comprehensive/04_reduction_sum.f90"
    exit 1
fi

FORTRAN_FILE="$1"
FIR_OUT="/tmp/fpa_$(basename "${FORTRAN_FILE%.f90}").fir"
FPA_TOOL="./build/tools/fpa-tool/fpa-tool"

# Add flang-new to PATH if not already there
export PATH="/usr/lib/llvm-18/bin:$PATH"

if [[ ! -f "$FPA_TOOL" ]]; then
    echo "ERROR: fpa-tool not found at $FPA_TOOL"
    echo "Run: bash scripts/build.sh"
    exit 1
fi

if [[ ! -f "$FORTRAN_FILE" ]]; then
    echo "ERROR: File not found: $FORTRAN_FILE"
    exit 1
fi

echo "==> Compiling: $FORTRAN_FILE"
flang-new -fc1 -emit-fir "$FORTRAN_FILE" -o "$FIR_OUT"
echo "    FIR output: $FIR_OUT"
echo ""

echo "==> Running FlangParallelAnalyzer..."
echo ""
"$FPA_TOOL" "$FIR_OUT"
