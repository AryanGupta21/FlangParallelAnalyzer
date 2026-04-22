# Build Setup Guide

This project is a Clang/MLIR pass that links against the Flang (LLVM Fortran)
compiler libraries. Before you can build `fpa-tool` or run any tests, you need
to build LLVM with Flang enabled.

This guide covers macOS (Apple Silicon / arm64).  Linux steps are identical
except for Step 1 (use `apt`/`dnf` instead of Homebrew).

---

## What you need to install

| Thing | Why |
|---|---|
| `ninja` | Fast build system — makes LLVM builds ~2× faster than make |
| `llvm` (Homebrew) | Provides `clang`/`clang++` to compile LLVM, plus `FileCheck` for tests |
| LLVM source + Flang | The compiler libraries your pass links against |

---

## Step 1 — Install build tools via Homebrew

```bash
brew install ninja llvm
```

This takes ~2 minutes.

After this, Homebrew's LLVM tools land in `/opt/homebrew/opt/llvm/bin/`.
Add them to your PATH so CMake can find them:

```bash
# Add this to your ~/.zshrc  (or ~/.bashrc)
export PATH="/opt/homebrew/opt/llvm/bin:$PATH"
export LDFLAGS="-L/opt/homebrew/opt/llvm/lib"
export CPPFLAGS="-I/opt/homebrew/opt/llvm/include"
```

Then reload:
```bash
source ~/.zshrc
```

Verify:
```bash
clang --version      # should say "clang version 18/19..."
ninja --version      # should print a version number
FileCheck --version  # should print LLVM version
```

---

## Step 2 — Clone LLVM (pinned to 18.1.0)

We pin to a specific release so the API doesn't change under us.

```bash
# Pick wherever you want the source to live
cd ~/Developer

git clone \
  --branch llvmorg-18.1.0 \
  --depth 1 \
  https://github.com/llvm/llvm-project.git
```

`--depth 1` skips the full git history — the clone will be ~3 GB instead of ~10 GB.

---

## Step 3 — Build LLVM + Flang + MLIR

```bash
cd ~/Developer/llvm-project
mkdir build && cd build

cmake ../llvm \
  -G Ninja \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_C_COMPILER=clang \
  -DCMAKE_CXX_COMPILER=clang++ \
  -DLLVM_ENABLE_PROJECTS="clang;flang;mlir" \
  -DLLVM_TARGETS_TO_BUILD="AArch64" \
  -DLLVM_ENABLE_ASSERTIONS=ON \
  -DLLVM_PARALLEL_LINK_JOBS=2
```

> **What each flag means:**
> - `RelWithDebInfo` — optimised build but with debug symbols (faster than Debug, debuggable)
> - `clang` as compiler — Homebrew clang is faster at building LLVM than Apple's Xcode clang
> - `ENABLE_PROJECTS` — only build what we need (skips ~20 other subprojects)
> - `TARGETS_TO_BUILD=AArch64` — only emit code for Apple Silicon (skips x86, ARM32, etc.)
> - `PARALLEL_LINK_JOBS=2` — linking is RAM-heavy; limit to 2 parallel links to avoid OOM

Then build (go get coffee — this takes 60–90 minutes):

```bash
ninja flang-new mlir-opt FileCheck
```

We only build three targets instead of the whole tree, which saves ~20 minutes.

Verify:
```bash
./bin/flang-new --version   # Flang compiler
./bin/mlir-opt --version    # MLIR optimizer (used by tests)
./bin/FileCheck --version   # test pattern checker
```

---

## Step 4 — Build fpa-tool

```bash
cd ~/Developer/paraloop
mkdir build && cd build

cmake .. \
  -G Ninja \
  -DLLVM_BUILD_DIR=~/Developer/llvm-project/build \
  -DLLVM_SOURCE_DIR=~/Developer/llvm-project
```

> **What these two flags mean:**
> - `LLVM_BUILD_DIR` — where the compiled `.a` libraries and generated headers live
> - `LLVM_SOURCE_DIR` — where the original source headers live (Flang's FIR dialect headers live here)
>
> Both are needed because Flang generates some headers at build time (from TableGen `.td` files)
> and keeps others in the source tree.

Then:
```bash
ninja fpa-tool
```

Verify:
```bash
./bin/fpa-tool --help   # should list --fir-loop-parallel-analysis
```

---

## Step 5 — Run the tests

### LIT tests (hand-crafted FIR, no flang-new needed)

```bash
cd ~/Developer/paraloop

export FPA_TOOL=build/bin/fpa-tool
export FILECHECK=~/Developer/llvm-project/build/bin/FileCheck

bash tests/run_lit.sh
```

Expected output:
```
╔══════════════════════════════════════════════════════════╗
║         FlangParallelAnalyzer — LIT Test Suite           ║
╚══════════════════════════════════════════════════════════╝

  phase2_reads_only          PASS
  phase2_array_write         PASS
  phase2_scalar_rw           PASS
  phase2_nested              PASS

  Results: 4 passed, 0 failed, 0 skipped
```

### Fortran end-to-end tests (requires flang-new)

```bash
export FLANG_BIN=~/Developer/llvm-project/build/bin/flang-new
export FPA_BIN=build/bin/fpa-tool

cd tests && bash run_tests.sh
```

---

## Disk space summary

| Item | Approximate size |
|---|---|
| LLVM source clone (depth 1) | ~3 GB |
| LLVM build tree | ~20–25 GB |
| fpa-tool build | < 100 MB |

You have 50 GB free — comfortably enough.

---

## Troubleshooting

**"ld: library not found for -lFIRDialect"**
Your `LLVM_BUILD_DIR` is wrong — check the path.

**"ninja: error: loading 'build.ninja'"**
Run cmake again from inside the `build/` directory.

**Out of memory during link**
Reduce `LLVM_PARALLEL_LINK_JOBS` from 2 to 1.

**FileCheck: command not found**
Set `FILECHECK=~/Developer/llvm-project/build/bin/FileCheck` explicitly.
