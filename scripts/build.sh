#!/usr/bin/env bash
# build.sh — Install dependencies and build fpa-tool
# Run from the repo root: bash scripts/build.sh
set -euo pipefail

echo "==> Installing LLVM 18 / Flang 18 dependencies..."
sudo apt-get update -qq
sudo apt-get install -y \
    llvm-18 \
    mlir-18-tools \
    libmlir-18-dev \
    flang-18 \
    libflang-18-dev \
    libclang-cpp-18-dev

echo "==> Fixing libclang-cpp symlink (required by MLIR cmake config)..."
sudo ln -sf \
    /usr/lib/llvm-18/lib/libclang-cpp.so.18.1 \
    /usr/lib/llvm-18/lib/libclang-cpp.so

echo "==> Configuring with CMake..."
mkdir -p build && cd build
cmake .. \
    -DLLVM_BUILD_DIR=/usr/lib/llvm-18 \
    -DCMAKE_BUILD_TYPE=Release

echo "==> Building fpa-tool..."
make -j"$(nproc)" fpa-tool

echo ""
echo "Build complete."
echo "Binary: build/tools/fpa-tool/fpa-tool"
echo ""
echo "Quick test:"
echo "  export PATH=\"/usr/lib/llvm-18/bin:\$PATH\""
echo "  bash scripts/run.sh tests/fortran/trivial_parallel.f90"
