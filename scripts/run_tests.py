#!/usr/bin/env python3
"""
run_tests.py — Automated test runner for FlangParallelAnalyzer.

For each .f90 file with a  "! EXPECTED: <STATUS>"  comment the script:
  1. Compiles the file to FIR with flang-new
  2. Runs fpa-tool and captures the output
  3. Parses every "Status : <STATUS>" line from fpa-tool's output
  4. Compares the first loop's status against the expected value
  5. Reports PASS / FAIL and a final summary

Usage:
    python3 scripts/run_tests.py                               # all tests/comprehensive/*.f90
    python3 scripts/run_tests.py tests/comprehensive/01*.f90  # specific file(s)
    python3 scripts/run_tests.py --dir tests/fortran           # original test set
    python3 scripts/run_tests.py -v                            # verbose (show full output)
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────────

FLANG    = os.environ.get("FLANG",    "/usr/lib/llvm-18/bin/flang-new")
FPA_TOOL = os.environ.get("FPA_TOOL", "./build/tools/fpa-tool/fpa-tool")

ANSI = {
    "green":  "\033[32m",
    "red":    "\033[31m",
    "yellow": "\033[33m",
    "cyan":   "\033[36m",
    "bold":   "\033[1m",
    "reset":  "\033[0m",
}

def colour(text: str, *codes: str) -> str:
    if not sys.stdout.isatty():
        return text
    return "".join(ANSI[c] for c in codes) + text + ANSI["reset"]

# ── Helpers ────────────────────────────────────────────────────────────────────

def parse_expected(f90_path: str) -> str | None:
    """
    Read the first '! EXPECTED: <STATUS>' comment from the file.
    Returns the status string (e.g. "SAFE", "UNSAFE", "REDUCTION") or None.
    """
    try:
        with open(f90_path) as fh:
            for line in fh:
                m = re.match(r"\s*!\s*EXPECTED\s*:\s*(\w+)", line)
                if m:
                    return m.group(1).upper()
    except OSError:
        pass
    return None


def parse_hint_expected(f90_path: str) -> str | None:
    """Read the '! HINT: ...' comment (optional)."""
    try:
        with open(f90_path) as fh:
            for line in fh:
                m = re.match(r"\s*!\s*HINT\s*:\s*(.+)", line)
                if m:
                    return m.group(1).strip()
    except OSError:
        pass
    return None


def compile_to_fir(f90_path: str) -> tuple[str | None, str]:
    """Compile f90 → FIR. Returns (fir_path, error_message)."""
    fir = f"/tmp/fpa_test_{Path(f90_path).stem}.fir"
    r = subprocess.run(
        [FLANG, "-fc1", "-emit-fir", f90_path, "-o", fir],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return None, r.stderr.strip()
    return fir, ""


def run_fpa(fir_path: str) -> tuple[str | None, str]:
    """Run fpa-tool on a .fir file. Returns (stdout, stderr)."""
    r = subprocess.run([FPA_TOOL, fir_path], capture_output=True, text=True)
    return r.stdout, r.stderr


def parse_statuses(output: str) -> list[str]:
    """Return every 'Status : ...' value found in fpa-tool output."""
    return [m.group(1).strip()
            for m in re.finditer(r"Status\s*:\s*(\w+)", output)]


def parse_hints(output: str) -> list[str]:
    """Return every 'Hint   : ...' value found in fpa-tool output."""
    return [m.group(1).strip()
            for m in re.finditer(r"Hint\s*:\s*(.+)", output)]

# ── Per-file test logic ────────────────────────────────────────────────────────

class Result:
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


def run_one(f90_path: str, verbose: bool = False) -> tuple[str, str]:
    """
    Run one test.  Returns (Result.*, detail_message).
    """
    expected = parse_expected(f90_path)
    if expected is None:
        return Result.SKIP, "No ! EXPECTED comment found"

    hint_expected = parse_hint_expected(f90_path)

    # Step 1: compile
    fir_path, err = compile_to_fir(f90_path)
    if fir_path is None:
        return Result.ERROR, f"flang-new failed:\n{err}"

    # Step 2: analyse
    stdout, stderr = run_fpa(fir_path)
    if verbose:
        print(colour("  fpa-tool output:", "cyan"))
        for line in stdout.splitlines():
            print("    " + line)
        if stderr.strip():
            print(colour("  fpa-tool stderr:", "yellow"))
            for line in stderr.splitlines():
                print("    " + line)

    statuses = parse_statuses(stdout)
    hints    = parse_hints(stdout)

    if not statuses:
        return Result.ERROR, "fpa-tool produced no Status lines"

    # The primary loop is the first reported status.
    actual = statuses[0]
    actual_hint = hints[0] if hints else ""

    if actual == expected:
        detail = f"Status: {actual}"
        if hint_expected and actual_hint:
            detail += f"  |  Hint: {actual_hint}"
        return Result.PASS, detail
    else:
        return Result.FAIL, (
            f"expected {expected}  got {actual}\n"
            f"    All statuses: {statuses}\n"
            f"    Hint: {actual_hint}"
        )

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Run FlangParallelAnalyzer test suite")
    ap.add_argument("files", nargs="*",
                    help=".f90 files to test (default: tests/comprehensive/*.f90)")
    ap.add_argument("--dir", default=None,
                    help="Directory of .f90 files to test")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="Show full fpa-tool output for every test")
    ap.add_argument("--no-colour", action="store_true",
                    help="Disable ANSI colour codes")
    args = ap.parse_args()

    if args.no_colour:
        global ANSI
        ANSI = {k: "" for k in ANSI}

    # Collect files
    if args.files:
        files = args.files
    elif args.dir:
        files = sorted(Path(args.dir).glob("*.f90"))
    else:
        files = sorted(Path("tests/comprehensive").glob("*.f90"))

    if not files:
        print("No .f90 files found.", file=sys.stderr)
        sys.exit(1)

    # Check tools exist
    for tool, path in [("flang-new", FLANG), ("fpa-tool", FPA_TOOL)]:
        if not Path(path).exists():
            print(colour(f"ERROR: {tool} not found at {path}", "red", "bold"))
            print(f"  Set FLANG= or FPA_TOOL= environment variables to override.",
                  file=sys.stderr)
            sys.exit(1)

    # Run tests
    counts = {Result.PASS: 0, Result.FAIL: 0, Result.ERROR: 0, Result.SKIP: 0}
    failures = []

    col_w = max(len(Path(f).name) for f in files) + 2

    print(colour(f"\n{'File':<{col_w}}  {'Result':<8}  Detail", "bold"))
    print("─" * 80)

    for f90 in files:
        name = Path(f90).name
        result, detail = run_one(str(f90), verbose=args.verbose)
        counts[result] += 1

        if result == Result.PASS:
            tag = colour("PASS", "green", "bold")
        elif result == Result.FAIL:
            tag = colour("FAIL", "red", "bold")
            failures.append((name, detail))
        elif result == Result.ERROR:
            tag = colour("ERR ", "yellow", "bold")
            failures.append((name, detail))
        else:
            tag = colour("SKIP", "cyan")

        # Only show first line of detail inline; rest on verbose failure dump
        first_line = detail.splitlines()[0] if detail else ""
        print(f"{name:<{col_w}}  {tag}      {first_line}")

    # Summary
    total = sum(counts.values())
    print("─" * 80)
    passed_str = colour(f"{counts[Result.PASS]} passed", "green")
    failed_str = colour(f"{counts[Result.FAIL]} failed", "red") if counts[Result.FAIL] else "0 failed"
    error_str  = colour(f"{counts[Result.ERROR]} errors", "yellow") if counts[Result.ERROR] else "0 errors"
    skip_str   = f"{counts[Result.SKIP]} skipped"
    print(f"\nResults: {passed_str}  {failed_str}  {error_str}  {skip_str}  (of {total})\n")

    if failures and not args.verbose:
        print(colour("Failure details:", "bold"))
        for name, detail in failures:
            print(colour(f"  {name}:", "red"))
            for line in detail.splitlines():
                print(f"    {line}")
        print()

    sys.exit(0 if counts[Result.FAIL] == 0 and counts[Result.ERROR] == 0 else 1)


if __name__ == "__main__":
    main()
