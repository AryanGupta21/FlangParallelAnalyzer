# lit.cfg.py — LLVM Integrated Tester configuration
#
# What is LIT?
# ─────────────
# LIT (LLVM Integrated Tester) is the standard test runner used across the
# whole LLVM project. Each .mlir test file contains special comments:
#
#   // RUN: fpa-tool --fir-loop-parallel-analysis %s 2>&1 | FileCheck %s
#   // CHECK: Loop #1
#   // CHECK: ext-reads=1
#
# When you run `llvm-lit tests/lit/`, LIT:
#   1. Finds every .mlir file in this directory
#   2. Executes the RUN line (replacing %s with the file path)
#   3. Pipes the output through FileCheck, which looks for CHECK patterns
#   4. Reports PASS / FAIL per file
#
# How to run:
#   llvm-lit tests/lit/
#   llvm-lit tests/lit/phase2_reads_only.mlir   # single test
#   llvm-lit -v tests/lit/                       # verbose (shows output on fail)
#
# Environment variables:
#   FPA_TOOL    — path to the fpa-tool binary   (default: looks on PATH)
#   FILECHECK   — path to FileCheck binary       (default: looks on PATH)

import os
import lit.formats

# ── Basic config ──────────────────────────────────────────────────────────────
config.name        = 'FlangParallelAnalyzer'
config.test_format = lit.formats.ShTest(execute_external=True)
config.suffixes    = ['.mlir']

# ── Tool substitutions ────────────────────────────────────────────────────────
# %fpa-tool  → the fpa-tool binary
# %filecheck → FileCheck (comes with LLVM)

fpa_tool_bin  = os.environ.get('FPA_TOOL',   'fpa-tool')
filecheck_bin = os.environ.get('FILECHECK',  'FileCheck')

config.substitutions.append(('%fpa-tool',  fpa_tool_bin))
config.substitutions.append(('%filecheck', filecheck_bin))

# ── Source / exec root ────────────────────────────────────────────────────────
config.test_source_root = os.path.dirname(__file__)
config.test_exec_root   = os.path.join(
    os.environ.get('FPA_BUILD_DIR', os.path.dirname(__file__)),
    'test-output'
)
