#!/usr/bin/env python3
"""
report.py — Generate an HTML parallelism report from FlangParallelAnalyzer.

For each .f90 file it:
  1. Compiles to FIR with flang-new
  2. Runs fpa-tool and captures the analysis output
  3. Maps results back to the original Fortran source lines
  4. Produces a self-contained HTML page (no external dependencies)

Usage:
    python3 scripts/report.py tests/fortran/*.f90
    python3 scripts/report.py tests/fortran/*.f90 -o report.html --open
"""

import argparse
import os
import re
import subprocess
import sys
import webbrowser
from html import escape
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

FLANG    = os.environ.get("FLANG",    "/usr/lib/llvm-18/bin/flang-new")
FPA_TOOL = os.environ.get("FPA_TOOL", "./build/tools/fpa-tool/fpa-tool")

STATUS_META = {
    "SAFE":      ("✓ SAFE",      "#28a745", "#d4f0db"),
    "REDUCTION": ("↺ REDUCTION", "#856404", "#fff3cd"),
    "UNSAFE":    ("✗ UNSAFE",    "#dc3545", "#fde8e8"),
    "UNKNOWN":   ("? UNKNOWN",   "#6c757d", "#e9ecef"),
}

# ── Step 1: run the analysis ──────────────────────────────────────────────────

def analyse(f90_path: str):
    """Compile f90_path to FIR then run fpa-tool. Returns stdout or None."""
    fir = f"/tmp/fpa_{Path(f90_path).stem}.fir"
    r = subprocess.run(
        [FLANG, "-fc1", "-emit-fir", f90_path, "-o", fir],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"  flang error: {r.stderr.strip()}", file=sys.stderr)
        return None
    r = subprocess.run([FPA_TOOL, fir], capture_output=True, text=True)
    return r.stdout

# ── Step 2: parse fpa-tool text output ───────────────────────────────────────

def parse_loops(output: str) -> list[dict]:
    """Return a list of loop-info dicts from fpa-tool stdout."""
    loops, cur = [], None
    for raw in output.splitlines():
        line = raw.strip()

        m = re.match(r"Loop #(\d+) @ (.+)", line)
        if m:
            cur = dict(num=int(m.group(1)), loc=m.group(2),
                       status="UNKNOWN", hint="", reason="",
                       bounds="", depth=0, accesses=[])
            loops.append(cur)
            continue

        if cur is None:
            continue

        if line.startswith("Bounds :"):
            cur["bounds"] = line[8:].strip()
            d = re.search(r"depth=(\d+)", line)
            if d:
                cur["depth"] = int(d.group(1))
        elif line.startswith("Status :"):
            cur["status"] = line[8:].strip()
        elif line.startswith("Hint   :"):
            cur["hint"] = line[8:].strip()
        elif line.startswith("Reason :"):
            cur["reason"] = line[8:].strip()
        elif re.match(r"\[(R|W|RW)\]", line):
            cur["accesses"].append(line)

    return loops

# ── Step 3: map loops → Fortran source lines ──────────────────────────────────

def do_loop_lines(source: str) -> list[int]:
    """Return 1-based line numbers of Fortran DO loop headers."""
    result = []
    for i, line in enumerate(source.splitlines(), 1):
        if re.match(r"\s*do\s+\w+\s*=", line, re.IGNORECASE):
            result.append(i)
    return result

# ── Step 4: render HTML ───────────────────────────────────────────────────────

def render_source(source: str, loop_at_line: dict[int, dict]) -> str:
    """Return an HTML <pre> block with annotated DO loop lines."""
    lines_html = []
    for lineno, line in enumerate(source.splitlines(), 1):
        esc = escape(line)
        if lineno in loop_at_line:
            lp = loop_at_line[lineno]
            label, color, bg = STATUS_META.get(lp["status"], STATUS_META["UNKNOWN"])
            lines_html.append(
                f'<span class="src-loop" style="background:{bg}">'
                f'<span class="ln">{lineno:3}</span>  {esc}'
                f'  <span class="badge" style="background:{color}">{label}</span>'
                f'</span>'
            )
        else:
            lines_html.append(
                f'<span class="src-plain">'
                f'<span class="ln">{lineno:3}</span>  {esc}'
                f'</span>'
            )
    return "\n".join(lines_html)


def render_loop_card(lp: dict) -> str:
    label, color, bg = STATUS_META.get(lp["status"], STATUS_META["UNKNOWN"])
    depth_tag = (f'<span class="depth-pill">depth {lp["depth"]}</span>'
                 if lp["depth"] > 0 else "")
    acc_items = "".join(f"<li><code>{escape(a)}</code></li>"
                        for a in lp["accesses"])
    acc_block = f'<ul class="acc-list">{acc_items}</ul>' if acc_items else ""
    hint_block = (f'<div class="hint-box"><code>{escape(lp["hint"])}</code></div>'
                  if lp["hint"] else "")
    return f"""
<div class="loop-card" style="border-left:4px solid {color};background:{bg}">
  <div class="card-header">
    <span class="status-pill" style="background:{color}">{label}</span>
    <span class="loop-num">Loop #{lp['num']}</span>
    {depth_tag}
    <code class="loc">{escape(lp['loc'])}</code>
  </div>
  {hint_block}
  <p class="reason">{escape(lp['reason'])}</p>
  {acc_block}
</div>"""


def render_file_section(fname: str, source: str, loops: list[dict]) -> str:
    do_lines  = do_loop_lines(source)
    loop_map  = {do_lines[i]: lp for i, lp in enumerate(loops) if i < len(do_lines)}
    src_html  = render_source(source, loop_map)
    cards     = "".join(render_loop_card(lp) for lp in loops)
    no_loops  = '<p class="no-loops">No DO loops detected.</p>' if not loops else ""
    n_safe    = sum(1 for l in loops if l["status"] == "SAFE")
    n_red     = sum(1 for l in loops if l["status"] == "REDUCTION")
    n_unsafe  = sum(1 for l in loops if l["status"] == "UNSAFE")
    summary   = (f'<span class="sum safe">{n_safe} safe</span>'
                 f'<span class="sum red">{n_red} reduction</span>'
                 f'<span class="sum unsafe">{n_unsafe} unsafe</span>')
    return f"""
<section class="file-sec">
  <div class="file-header">
    <span class="file-icon">📄</span>
    <span class="file-name">{escape(os.path.basename(fname))}</span>
    <div class="summary-pills">{summary}</div>
  </div>
  <div class="grid">
    <div class="panel left-panel">
      <div class="panel-label">Fortran Source</div>
      <pre class="source">{src_html}</pre>
    </div>
    <div class="panel right-panel">
      <div class="panel-label">Analysis</div>
      {cards}{no_loops}
    </div>
  </div>
</section>"""


CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       background: #f0f2f5; color: #24292e; }
header { background: linear-gradient(135deg,#1a1a2e,#16213e);
         color: white; padding: 28px 40px; }
header h1 { font-size: 1.5rem; font-weight: 700; }
header p  { color: #8892a4; margin-top: 6px; font-size: .875rem; }

.legend { display:flex; gap:20px; padding:14px 40px; background:white;
          border-bottom:1px solid #e1e4e8; flex-wrap:wrap; }
.leg { display:flex; align-items:center; gap:6px; font-size:.82rem; }
.leg-dot { width:10px; height:10px; border-radius:50%; }

.file-sec { margin:24px 40px; background:white; border-radius:10px;
            box-shadow:0 1px 4px rgba(0,0,0,.1); overflow:hidden; }
.file-header { display:flex; align-items:center; gap:10px; padding:14px 20px;
               border-bottom:1px solid #e1e4e8; }
.file-icon { font-size:1.1rem; }
.file-name { font-weight:600; font-size:.95rem; flex:1; }
.summary-pills { display:flex; gap:6px; }
.sum { font-size:.72rem; font-weight:700; padding:2px 9px;
       border-radius:10px; color:white; }
.sum.safe   { background:#28a745; }
.sum.red    { background:#856404; }
.sum.unsafe { background:#dc3545; }

.grid { display:grid; grid-template-columns:1fr 1fr; }
.panel { padding:16px 20px; }
.left-panel { border-right:1px solid #e1e4e8; }
.panel-label { font-size:.72rem; text-transform:uppercase; letter-spacing:.06em;
               color:#6a737d; margin-bottom:10px; font-weight:600; }

.source { font-family:"SF Mono",Consolas,monospace; font-size:.8rem;
          line-height:1.65; overflow-x:auto; }
.source span { display:block; white-space:pre; }
.src-loop { border-radius:3px; }
.ln { color:#bbb; user-select:none; }
.badge { display:inline-block; color:white; font-size:.68rem; font-weight:700;
         padding:1px 7px; border-radius:10px; margin-left:8px;
         vertical-align:middle; }

.loop-card { border-radius:7px; padding:12px 14px; margin-bottom:10px; }
.card-header { display:flex; align-items:center; gap:8px; flex-wrap:wrap;
               margin-bottom:8px; }
.status-pill { color:white; font-size:.72rem; font-weight:700;
               padding:2px 9px; border-radius:10px; }
.loop-num { font-weight:600; font-size:.88rem; }
.depth-pill { font-size:.68rem; color:#6a737d; background:#e1e4e8;
              padding:1px 6px; border-radius:8px; }
.loc { font-size:.72rem; color:#6a737d; }
.hint-box { background:rgba(0,0,0,.07); border-radius:4px; padding:6px 10px;
            font-size:.8rem; margin-bottom:8px; }
.reason { font-size:.82rem; color:#444; line-height:1.5; margin-bottom:6px; }
.acc-list { font-size:.75rem; color:#555; padding-left:16px; }
.acc-list li { margin:2px 0; }
.no-loops { color:#6a737d; font-style:italic; font-size:.85rem; padding:8px 0; }

@media(max-width:860px){
  .grid { grid-template-columns:1fr; }
  .left-panel { border-right:none; border-bottom:1px solid #e1e4e8; }
  .file-sec,.legend { margin:12px 16px; }
}
"""

def build_html(sections: str, stats: dict | None = None) -> str:
    stat_line = ""
    if stats:
        stat_line = (
            f'<p style="margin-top:10px;font-size:.85rem;color:#8892a4">'
            f'{stats["files"]} files &nbsp;·&nbsp; '
            f'{stats["loops"]} loops analysed &nbsp;·&nbsp; '
            f'<span style="color:#6fcf7c">{stats["safe"]} SAFE</span> &nbsp;·&nbsp; '
            f'<span style="color:#f2c94c">{stats["reduction"]} REDUCTION</span> &nbsp;·&nbsp; '
            f'<span style="color:#eb5757">{stats["unsafe"]} UNSAFE</span>'
            f'</p>'
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FlangParallelAnalyzer — Parallelism Report</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>⚡ FlangParallelAnalyzer — Loop Parallelism Report</h1>
  <p>Automatic OpenMP hint generation for Fortran DO loops via FIR analysis (LLVM 18 / Flang)</p>
  {stat_line}
</header>
<div class="legend">
  <div class="leg"><div class="leg-dot" style="background:#28a745"></div>
    <strong>SAFE</strong> — safe to parallelize with <code>!$OMP PARALLEL DO</code></div>
  <div class="leg"><div class="leg-dot" style="background:#856404"></div>
    <strong>REDUCTION</strong> — parallel with OpenMP REDUCTION clause</div>
  <div class="leg"><div class="leg-dot" style="background:#dc3545"></div>
    <strong>UNSAFE</strong> — loop-carried dependency detected</div>
  <div class="leg"><div class="leg-dot" style="background:#6c757d"></div>
    <strong>UNKNOWN</strong> — analysis inconclusive (conservative)</div>
</div>
{sections}
</body>
</html>"""

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Generate HTML parallelism report")
    ap.add_argument("files", nargs="*",
                    help=".f90 Fortran source files (default: all tests/fortran + tests/comprehensive)")
    ap.add_argument("-o", "--output", default="report.html",
                    help="Output HTML file (default: report.html)")
    ap.add_argument("--open", action="store_true",
                    help="Open the report in the default browser when done")
    args = ap.parse_args()

    # Default: include both the original tests and the comprehensive suite
    if not args.files:
        from pathlib import Path
        args.files = (
            sorted(Path("tests/fortran").glob("*.f90")) +
            sorted(Path("tests/comprehensive").glob("*.f90"))
        )

    sections = []
    stats = {"files": 0, "loops": 0, "safe": 0, "reduction": 0, "unsafe": 0}

    for f90 in args.files:
        print(f"Analysing {f90} …", file=sys.stderr)
        try:
            source = open(f90).read()
        except OSError as e:
            print(f"  Cannot read file: {e}", file=sys.stderr)
            continue

        output = analyse(f90)
        if output is None:
            continue

        loops = parse_loops(output)
        print(f"  → {len(loops)} loop(s): "
              + ", ".join(f'#{l["num"]} {l["status"]}' for l in loops),
              file=sys.stderr)
        sections.append(render_file_section(f90, source, loops))

        stats["files"] += 1
        stats["loops"] += len(loops)
        stats["safe"]      += sum(1 for l in loops if l["status"] == "SAFE")
        stats["reduction"] += sum(1 for l in loops if l["status"] == "REDUCTION")
        stats["unsafe"]    += sum(1 for l in loops if l["status"] == "UNSAFE")

    if not sections:
        print("No files analysed successfully.", file=sys.stderr)
        sys.exit(1)

    html = build_html("\n".join(sections), stats=stats)
    out  = args.output
    with open(out, "w") as f:
        f.write(html)

    print(f"\nReport → {out}", file=sys.stderr)
    if args.open:
        webbrowser.open(f"file://{os.path.abspath(out)}")


if __name__ == "__main__":
    main()
