#!/usr/bin/env python3
"""
report.py — Performance-engineer-grade parallelism report for FlangParallelAnalyzer.

Three views:
  Overview  — dashboard: coverage stats, failure breakdown, hotspots, quick wins
  Explorer  — file tree grouped by status + source with VS-Code-style inline peek
  Loops     — paginated, filterable data table of every loop with fix suggestions

Usage:
    python3 scripts/report.py                        # all tests
    python3 scripts/report.py tests/fortran/*.f90
    python3 scripts/report.py -o out.html --open
"""

import argparse
import json
import os
import re
import subprocess
import sys
import webbrowser
from pathlib import Path

FLANG    = os.environ.get("FLANG",    "/usr/lib/llvm-18/bin/flang-new")
FPA_TOOL = os.environ.get("FPA_TOOL", "./build/tools/fpa-tool/fpa-tool")

# ── Analysis pipeline ─────────────────────────────────────────────────────────

def analyse(path):
    fir = f"/tmp/fpa_{Path(path).stem}.fir"
    r = subprocess.run([FLANG, "-fc1", "-emit-fir", str(path), "-o", fir],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  flang error: {r.stderr.strip()}", file=sys.stderr)
        return None
    return subprocess.run([FPA_TOOL, fir], capture_output=True, text=True).stdout

def parse_loops(out):
    loops, cur = [], None
    for raw in out.splitlines():
        ln = raw.strip()
        m = re.match(r"Loop #(\d+) @ (.+)", ln)
        if m:
            cur = dict(num=int(m.group(1)), loc=m.group(2),
                       status="UNKNOWN", hint="", reason="", bounds="", depth=0, accesses=[])
            loops.append(cur); continue
        if cur is None: continue
        if ln.startswith("Bounds :"):
            cur["bounds"] = ln[8:].strip()
            d = re.search(r"depth=(\d+)", ln)
            if d: cur["depth"] = int(d.group(1))
        elif ln.startswith("Status :"): cur["status"]  = ln[8:].strip()
        elif ln.startswith("Hint   :"): cur["hint"]    = ln[8:].strip()
        elif ln.startswith("Reason :"): cur["reason"]  = ln[8:].strip()
        elif re.match(r"\[(R|W|RW)\]", ln): cur["accesses"].append(ln)
    return loops

def do_loop_lines(src):
    return [i+1 for i, ln in enumerate(src.splitlines())
            if re.match(r"\s*do\s+\w+\s*=", ln, re.IGNORECASE)]

def build_file_data(fname, source, loops):
    dl = do_loop_lines(source)
    enriched = []
    for i, lp in enumerate(loops):
        lp2 = dict(lp)
        lp2["sourceLine"] = dl[i] if i < len(dl) else None
        enriched.append(lp2)
    return {
        "name":       os.path.basename(str(fname)),
        "path":       str(fname),
        "source":     source,
        "loops":      enriched,
        "nSafe":      sum(1 for l in loops if l["status"] == "SAFE"),
        "nReduction": sum(1 for l in loops if l["status"] == "REDUCTION"),
        "nUnsafe":    sum(1 for l in loops if l["status"] == "UNSAFE"),
    }

# ── HTML template (%%DATA%% and %%STATS%% substituted at build time) ──────────

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FlangPA</title>
<style>
:root{
  --bg:#0b0e13;--surf:#141920;--surf2:#1c2330;--surf3:#232e40;
  --border:#2a3343;--border-l:#1e2840;
  --text:#c9d1d9;--dim:#6e7681;--muted:#3d4450;
  --safe:#3fb950;--safe-bg:rgba(63,185,80,.12);--safe-bd:rgba(63,185,80,.35);
  --redu:#d29922;--redu-bg:rgba(210,153,34,.12);--redu-bd:rgba(210,153,34,.35);
  --unsafe:#f85149;--unsafe-bg:rgba(248,81,73,.12);--unsafe-bd:rgba(248,81,73,.35);
  --amber:#e3b341;
  --mono:"Cascadia Code","JetBrains Mono","Fira Code",Consolas,monospace;
  --ui:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden;background:var(--bg);color:var(--text);
          font-family:var(--ui);font-size:13px;-webkit-font-smoothing:antialiased}
button{font-family:inherit;cursor:pointer}
a{color:inherit;text-decoration:none}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
::-webkit-scrollbar-corner{background:transparent}

/* ── layout ── */
#app{display:grid;grid-template-rows:40px 1fr;height:100vh}
#viewport{overflow:hidden;display:flex;flex-direction:column}
.view{display:none;flex:1;overflow:hidden}
.view.active{display:flex;flex-direction:column;overflow:hidden}

/* ── navbar ── */
#nav{display:flex;align-items:center;gap:0;padding:0 18px;
     background:var(--surf);border-bottom:1px solid var(--border);
     user-select:none;gap:6px}
.nav-logo{font-family:var(--mono);font-size:11px;font-weight:700;
          color:var(--amber);letter-spacing:.1em;margin-right:10px}
.nav-sep{width:1px;height:18px;background:var(--border)}
.nav-tab{padding:0 14px;height:40px;display:flex;align-items:center;
         font-size:11px;font-weight:600;color:var(--dim);
         border-bottom:2px solid transparent;margin-bottom:-1px;
         transition:all .12s;cursor:pointer;gap:6px;white-space:nowrap}
.nav-tab:hover{color:var(--text)}
.nav-tab.active{color:var(--text);border-bottom-color:var(--amber)}
.nav-badge{font-size:9px;background:var(--surf2);border-radius:8px;
           padding:1px 6px;color:var(--muted);font-weight:400}
.nav-search{margin-left:auto;position:relative}
#gsearch{background:var(--bg);border:1px solid var(--border);border-radius:5px;
         color:var(--text);font-family:var(--mono);font-size:11px;
         padding:4px 8px 4px 26px;outline:none;width:220px;transition:border-color .15s}
#gsearch:focus{border-color:var(--amber)}
#gsearch::placeholder{color:var(--muted)}
.nav-search-ico{position:absolute;left:8px;top:50%;transform:translateY(-50%);
                color:var(--muted);font-size:10px;pointer-events:none}
.nav-kb{font-size:10px;color:var(--muted);font-family:var(--mono)}
.nav-kb kbd{background:var(--surf2);border:1px solid var(--border);
            border-radius:3px;padding:0 4px;font-family:inherit}

/* ══════════════════════════════════════════════════════════════
   VIEW 1: OVERVIEW
══════════════════════════════════════════════════════════════ */
#view-overview{overflow-y:auto;padding:24px 28px;gap:20px}
.ov-row{display:grid;gap:14px}
.ov-row-4{grid-template-columns:repeat(4,1fr)}
.ov-row-2{grid-template-columns:1fr 1fr}
.ov-row-3{grid-template-columns:1.4fr 1fr 1fr}

/* stat cards */
.ov-card{background:var(--surf);border:1px solid var(--border);
         border-radius:8px;padding:18px 20px;position:relative;overflow:hidden}
.ov-card::before{content:'';position:absolute;top:0;left:0;right:0;
                 height:2px;background:var(--card-accent,var(--border))}
.ov-card.c-safe{--card-accent:var(--safe)}
.ov-card.c-redu{--card-accent:var(--redu)}
.ov-card.c-unsafe{--card-accent:var(--unsafe)}
.ov-card.c-amber{--card-accent:var(--amber)}
.ov-card-num{font-family:var(--mono);font-size:28px;font-weight:700;
             line-height:1;margin-bottom:4px}
.ov-card.c-safe  .ov-card-num{color:var(--safe)}
.ov-card.c-redu  .ov-card-num{color:var(--redu)}
.ov-card.c-unsafe.ov-card-num{color:var(--unsafe)}
.ov-card.c-unsafe .ov-card-num{color:var(--unsafe)}
.ov-card.c-amber .ov-card-num{color:var(--amber)}
.ov-card-label{font-size:10px;font-weight:700;letter-spacing:.08em;
               text-transform:uppercase;color:var(--dim);margin-bottom:3px}
.ov-card-sub{font-size:11px;color:var(--muted)}

/* coverage bar */
.ov-cov-bar{height:8px;border-radius:4px;background:var(--surf2);
            overflow:hidden;display:flex;margin:8px 0 6px}
.ov-cov-seg{height:100%;transition:width .3s}
.ov-cov-legend{display:flex;gap:14px;font-size:10px;font-family:var(--mono)}
.ov-cov-dot{width:8px;height:8px;border-radius:2px;display:inline-block;
            margin-right:4px;vertical-align:middle}

/* panel */
.ov-panel{background:var(--surf);border:1px solid var(--border);
          border-radius:8px;padding:16px 18px;display:flex;flex-direction:column;gap:0}
.ov-panel-hdr{display:flex;align-items:center;justify-content:space-between;
              margin-bottom:12px}
.ov-panel-title{font-size:11px;font-weight:700;text-transform:uppercase;
                letter-spacing:.07em;color:var(--dim)}
.ov-panel-more{font-size:10px;color:var(--amber);cursor:pointer;font-family:var(--mono)}
.ov-panel-more:hover{text-decoration:underline}

/* category breakdown bars */
.cat-row{display:grid;grid-template-columns:140px 1fr 28px 36px;
         align-items:center;gap:8px;padding:5px 0;
         border-bottom:1px solid var(--border-l)}
.cat-row:last-child{border-bottom:none}
.cat-label{font-size:11px;color:var(--text);white-space:nowrap;overflow:hidden;
           text-overflow:ellipsis}
.cat-track{height:6px;background:var(--surf2);border-radius:3px;overflow:hidden}
.cat-fill{height:100%;border-radius:3px;transition:width .4s}
.cat-n{font-family:var(--mono);font-size:11px;font-weight:700;color:var(--text);
       text-align:right}
.cat-pct{font-family:var(--mono);font-size:10px;color:var(--muted);text-align:right}
.cat-fix{font-size:10px;color:var(--dim);margin-top:2px;grid-column:1/-1;
         padding:3px 6px;background:var(--surf2);border-radius:3px;
         display:none;font-style:italic}
.cat-row:hover .cat-fix{display:block}

/* hotspot rows */
.hs-row{display:flex;align-items:center;gap:8px;padding:6px 0;
        border-bottom:1px solid var(--border-l);cursor:pointer}
.hs-row:last-child{border-bottom:none}
.hs-row:hover .hs-name{color:var(--amber)}
.hs-name{font-family:var(--mono);font-size:11px;flex:1;overflow:hidden;
         text-overflow:ellipsis;white-space:nowrap;transition:color .1s}
.hs-bar{height:4px;border-radius:2px;background:var(--unsafe-bg)}
.hs-bar-inner{height:100%;background:var(--unsafe);border-radius:2px}
.hs-cnt{font-family:var(--mono);font-size:10px;font-weight:700;
        color:var(--unsafe);white-space:nowrap}

/* quick wins */
.qw-grid{display:flex;flex-direction:column;gap:0}
.qw-row{display:flex;align-items:center;gap:8px;padding:5px 0;
        border-bottom:1px solid var(--border-l);cursor:pointer}
.qw-row:last-child{border-bottom:none}
.qw-row:hover .qw-file{color:var(--amber)}
.qw-pill{font-size:9px;font-weight:700;padding:2px 6px;border-radius:4px;
         flex-shrink:0;border:1px solid transparent}
.qw-pill.SAFE{color:var(--safe);background:var(--safe-bg);border-color:var(--safe-bd)}
.qw-pill.REDUCTION{color:var(--redu);background:var(--redu-bg);border-color:var(--redu-bd)}
.qw-file{font-family:var(--mono);font-size:10px;flex:1;overflow:hidden;
         text-overflow:ellipsis;white-space:nowrap;transition:color .1s}
.qw-hint{font-family:var(--mono);font-size:10px;color:var(--dim);
         white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:200px}

/* ══════════════════════════════════════════════════════════════
   VIEW 2: EXPLORER
══════════════════════════════════════════════════════════════ */
#view-explorer{flex-direction:row!important}
#ex-sidebar{width:210px;flex-shrink:0;border-right:1px solid var(--border);
            background:var(--surf);overflow-y:auto;display:flex;flex-direction:column}
#ex-main{flex:1;display:flex;flex-direction:column;overflow:hidden}
#ex-srcbar{border-bottom:1px solid var(--border);background:var(--surf);
           padding:0 16px;display:flex;align-items:center;min-height:32px;
           overflow-x:auto;gap:0}
#ex-srcbar::-webkit-scrollbar{height:0}
.ex-tab{padding:5px 14px;font-family:var(--mono);font-size:11px;color:var(--dim);
        cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px;
        white-space:nowrap;transition:all .12s}
.ex-tab:hover{color:var(--text)}
.ex-tab.active{color:var(--text);border-bottom-color:var(--amber)}
#ex-scroll{flex:1;overflow:auto}
#ex-code{font-family:var(--mono);font-size:12px;line-height:1.72;
         padding:10px 0;min-width:max-content}

/* sidebar groups */
.ex-grp{border-bottom:1px solid var(--border-l)}
.ex-grp-hdr{display:flex;align-items:center;gap:6px;padding:8px 10px;
            font-size:10px;font-weight:700;text-transform:uppercase;
            letter-spacing:.07em;color:var(--dim);cursor:pointer;user-select:none}
.ex-grp-hdr:hover{color:var(--text)}
.ex-chev{font-size:8px;display:inline-block;transition:transform .15s}
.ex-chev.open{transform:rotate(90deg)}
.ex-gcnt{margin-left:auto;background:var(--surf2);border-radius:8px;
         padding:1px 6px;font-size:9px;color:var(--muted);font-weight:400}
.ex-file{display:flex;align-items:center;gap:6px;padding:5px 10px 5px 22px;
         cursor:pointer;font-family:var(--mono);font-size:10px;color:var(--dim);
         border-left:2px solid transparent;transition:all .1s;
         white-space:nowrap;overflow:hidden}
.ex-file:hover{background:var(--surf2);color:var(--text)}
.ex-file.active{background:rgba(227,179,65,.07);border-left-color:var(--amber);
                color:var(--text)}
.ex-fdot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.ex-fname{overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0}
.ex-fct{font-size:9px;color:var(--muted);flex-shrink:0}

/* source lines */
.sln{display:flex;align-items:baseline;padding-right:20px}
.sln:hover{background:rgba(255,255,255,.022)}
.sln.loop-ln{cursor:pointer}
.sln.loop-ln:hover{background:rgba(255,255,255,.04)}
.sln.peek-open{background:rgba(227,179,65,.06)!important}
.gutter{display:flex;align-items:center;width:50px;flex-shrink:0;padding-right:6px}
.lnum{width:32px;text-align:right;color:var(--muted);font-size:11px;user-select:none}
.gdot{width:5px;height:5px;border-radius:50%;flex-shrink:0;margin-left:5px}
.stext{padding-left:6px;white-space:pre}
.sbadge{margin-left:12px;font-size:10px;font-weight:700;padding:1px 8px;
        border-radius:10px;display:inline-flex;align-items:center;gap:3px;
        border:1px solid transparent;white-space:nowrap;flex-shrink:0}

/* peek panel — VS Code style inline expansion */
.peek-panel{background:var(--surf2);border-top:1px solid var(--border);
            border-bottom:2px solid var(--amber);
            padding:14px 16px;font-size:12px}
.peek-top{display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap}
.peek-status{font-family:var(--mono);font-size:10px;font-weight:700;
             padding:3px 9px;border-radius:4px;border:1px solid transparent}
.peek-status.SAFE     {color:var(--safe);background:var(--safe-bg);border-color:var(--safe-bd)}
.peek-status.REDUCTION{color:var(--redu);background:var(--redu-bg);border-color:var(--redu-bd)}
.peek-status.UNSAFE   {color:var(--unsafe);background:var(--unsafe-bg);border-color:var(--unsafe-bd)}
.peek-title{font-family:var(--mono);font-size:11px;font-weight:600;color:var(--text)}
.peek-close{margin-left:auto;font-size:16px;color:var(--muted);cursor:pointer;
            line-height:1;padding:0 4px}
.peek-close:hover{color:var(--text)}
.peek-hint{font-family:var(--mono);font-size:11px;background:rgba(227,179,65,.08);
           border:1px solid rgba(227,179,65,.25);border-radius:4px;
           padding:6px 10px;margin-bottom:8px;color:#f0d080}
.peek-reason{font-size:11px;color:var(--dim);line-height:1.6;margin-bottom:8px}
.peek-fix{font-size:11px;color:var(--amber);
          border-left:2px solid var(--amber);padding-left:8px;margin-bottom:8px;
          font-style:italic}
.peek-row{display:flex;gap:20px;flex-wrap:wrap}
.peek-col{flex:1;min-width:160px}
.peek-col-lbl{font-size:9px;text-transform:uppercase;letter-spacing:.07em;
              color:var(--muted);margin-bottom:6px;font-weight:700}
.peek-mem{display:flex;flex-direction:column;gap:3px}
.peek-acc{display:flex;align-items:center;gap:6px;font-family:var(--mono);
          font-size:10px;color:var(--dim)}
.pacc{font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px}
.pacc.R {color:var(--safe);  background:rgba(63,185,80,.18)}
.pacc.W {color:var(--unsafe);background:rgba(248,81,73,.18)}
.pacc.RW{color:var(--redu);  background:rgba(210,153,34,.18)}
.peek-dep-viz{font-family:var(--mono);font-size:10px;color:var(--dim);
              background:var(--bg);border-radius:4px;padding:8px 10px;
              line-height:1.8;white-space:pre}
.peek-dep-bad{color:var(--unsafe)}
.peek-dep-ok {color:var(--safe)}
.peek-bounds{font-family:var(--mono);font-size:10px;color:var(--dim)}

/* ── reasoning debugger components ── */
.peek-sec-hdr{font-size:9px;text-transform:uppercase;letter-spacing:.07em;
              color:var(--muted);margin-bottom:6px;font-weight:700}
.ph-row{display:grid;grid-template-columns:16px 88px 16px 1fr;
        align-items:center;gap:6px;padding:3px 0;
        border-bottom:1px solid var(--border-l)}
.ph-row:last-child{border-bottom:none}
.ph-num{font-family:var(--mono);font-size:9px;color:var(--muted)}
.ph-name{font-size:11px;color:var(--text)}
.ph-icon{font-size:10px;text-align:center;font-weight:700}
.ph-detail{font-size:10px}
.ph-detail.pass{color:var(--safe)}
.ph-detail.fail{color:var(--unsafe);font-weight:600}
.ph-detail.warn{color:var(--redu)}
.ph-detail.skip{color:var(--muted);font-style:italic}
.issue-row{display:flex;align-items:flex-start;gap:8px;
           padding:4px 0;border-bottom:1px solid var(--border-l)}
.issue-row:last-child{border-bottom:none}
.issue-icon{font-size:11px;flex-shrink:0;margin-top:1px}
.issue-label{font-size:11px;font-weight:600;color:var(--text)}
.issue-detail{font-size:10px;color:var(--dim);margin-top:1px}
.conf-badge{font-family:var(--mono);font-size:10px;font-weight:700;
            padding:3px 8px;border-radius:4px;border:1px solid;
            display:inline-flex;align-items:center;gap:5px;flex-shrink:0}
.conf-bar{display:inline-block;width:46px;height:5px;background:var(--surf3);
          border-radius:3px;overflow:hidden;vertical-align:middle}
.conf-fill{display:block;height:100%;border-radius:3px}
.dep-viz{font-family:var(--mono);font-size:10px;background:var(--bg);
         border-radius:4px;padding:8px 10px;line-height:2;
         border:1px solid var(--border);white-space:pre}

/* fortran syntax */
.fkw {color:#79b8ff}
.fcmt{color:#444d56;font-style:italic}

/* ══════════════════════════════════════════════════════════════
   VIEW 3: LOOPS TABLE
══════════════════════════════════════════════════════════════ */
#view-loops{flex-direction:column!important;overflow:hidden}
#loops-toolbar{display:flex;align-items:center;gap:8px;padding:10px 18px;
               background:var(--surf);border-bottom:1px solid var(--border);
               flex-shrink:0}
.lt-filter{display:flex;gap:3px}
.lt-fbtn{padding:4px 11px;border-radius:4px;border:1px solid var(--border);
         background:transparent;color:var(--dim);font-family:var(--mono);
         font-size:10px;font-weight:700;cursor:pointer;transition:all .12s}
.lt-fbtn:hover{color:var(--text);border-color:var(--dim)}
.lt-fbtn.fa{background:var(--surf2);border-color:var(--dim);color:var(--text)}
.lt-fbtn.fs{background:var(--safe-bg);border-color:var(--safe-bd);color:var(--safe)}
.lt-fbtn.fr{background:var(--redu-bg);border-color:var(--redu-bd);color:var(--redu)}
.lt-fbtn.fu{background:var(--unsafe-bg);border-color:var(--unsafe-bd);color:var(--unsafe)}
.lt-count{font-family:var(--mono);font-size:11px;color:var(--dim);margin-left:6px}
.lt-spacer{flex:1}
.lt-sort{font-family:var(--mono);font-size:10px;color:var(--dim);
         background:transparent;border:1px solid var(--border);
         border-radius:4px;padding:4px 8px;color:var(--dim)}
.lt-sort:focus{outline:none;border-color:var(--amber)}
option{background:var(--surf)}

#loops-scroll{flex:1;overflow-y:auto;overflow-x:hidden}
.loops-table{width:100%;border-collapse:collapse}
.loops-table th{position:sticky;top:0;background:var(--surf);
                border-bottom:1px solid var(--border);padding:8px 14px;
                text-align:left;font-size:10px;font-weight:700;
                text-transform:uppercase;letter-spacing:.07em;color:var(--dim);
                user-select:none;white-space:nowrap;cursor:pointer}
.loops-table th:hover{color:var(--text)}
.loops-table th .sort-arrow{margin-left:4px;opacity:.4}
.loops-table th.sorted .sort-arrow{opacity:1;color:var(--amber)}
.lt-row{border-bottom:1px solid var(--border-l);cursor:pointer;transition:background .1s}
.lt-row:hover>td{background:rgba(255,255,255,.025)}
.lt-row.expanded>td{background:rgba(227,179,65,.04)}
.lt-row td{padding:8px 14px;font-size:11px;vertical-align:middle}
.lt-row td:first-child{font-family:var(--mono);font-size:10px;color:var(--muted);width:36px}
.lt-file{font-family:var(--mono);font-size:11px;color:var(--text)}
.lt-file-line{font-size:9px;color:var(--muted)}
.lt-status{font-family:var(--mono);font-size:9px;font-weight:700;padding:2px 7px;
           border-radius:4px;border:1px solid transparent;white-space:nowrap}
.lt-status.SAFE     {color:var(--safe);background:var(--safe-bg);border-color:var(--safe-bd)}
.lt-status.REDUCTION{color:var(--redu);background:var(--redu-bg);border-color:var(--redu-bd)}
.lt-status.UNSAFE   {color:var(--unsafe);background:var(--unsafe-bg);border-color:var(--unsafe-bd)}
.lt-status.UNKNOWN  {color:var(--dim);background:var(--surf2);border-color:var(--border)}
.lt-cat{font-size:11px;color:var(--dim)}
.lt-hint{font-family:var(--mono);font-size:10px;color:var(--dim);
         max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lt-expand-row td{padding:0!important;background:var(--surf2)!important}
.lt-expand-inner{padding:12px 56px 14px;border-bottom:2px solid var(--amber)}
.lt-exp-reason{font-size:11px;color:var(--dim);line-height:1.6;margin-bottom:8px}
.lt-exp-fix{font-size:11px;color:var(--amber);
            border-left:2px solid var(--amber);padding-left:8px;
            margin-bottom:8px;font-style:italic}
.lt-exp-accs{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.lt-exp-acc{display:flex;align-items:center;gap:4px;font-family:var(--mono);
            font-size:10px;color:var(--dim);background:var(--bg);
            padding:3px 7px;border-radius:4px;border:1px solid var(--border)}
.lt-exp-goto{display:inline-block;margin-top:8px;font-size:10px;
             color:var(--amber);cursor:pointer;font-family:var(--mono)}
.lt-exp-goto:hover{text-decoration:underline}

/* pagination */
#loops-pager{display:flex;align-items:center;gap:6px;padding:10px 18px;
             background:var(--surf);border-top:1px solid var(--border);
             flex-shrink:0;font-size:11px;color:var(--dim)}
.pg-btn{padding:3px 10px;border:1px solid var(--border);border-radius:4px;
        background:transparent;color:var(--dim);font-family:var(--mono);
        font-size:10px;cursor:pointer;transition:all .12s}
.pg-btn:hover:not(:disabled){border-color:var(--amber);color:var(--amber)}
.pg-btn:disabled{opacity:.35;cursor:default}
.pg-num{padding:3px 8px;border:1px solid var(--border);border-radius:4px;
        background:transparent;color:var(--dim);font-family:var(--mono);
        font-size:10px;cursor:pointer}
.pg-num.active{background:var(--amber);border-color:var(--amber);
               color:var(--bg);font-weight:700}
.pg-spacer{flex:1}
.pg-info{font-family:var(--mono);font-size:10px;color:var(--muted)}

/* ── help modal ── */
#helpmod{display:none;position:fixed;inset:0;background:rgba(0,0,0,.65);
         z-index:100;align-items:center;justify-content:center}
#helpmod.open{display:flex}
.hbox{background:var(--surf);border:1px solid var(--border);border-radius:10px;
      padding:22px 26px;width:370px;max-width:95vw}
.htitle{font-weight:700;font-size:13px;margin-bottom:14px}
.hrow{display:flex;justify-content:space-between;align-items:center;
      padding:5px 0;border-bottom:1px solid var(--border-l);font-size:11px}
.hrow:last-of-type{border-bottom:none}
.hrow kbd{background:var(--surf2);border:1px solid var(--border);border-radius:3px;
          padding:1px 6px;font-family:var(--mono);font-size:10px}
.hrow span{color:var(--dim)}
.hclose{margin-top:14px;width:100%;padding:7px;background:var(--surf2);
        border:1px solid var(--border);border-radius:6px;
        color:var(--text);cursor:pointer;font-size:11px}
.hclose:hover{background:var(--border)}
</style>
</head>
<body>
<script>
const DATA  = %%DATA%%;
const STATS = %%STATS%%;
</script>

<div id="app">

<!-- navbar -->
<div id="nav">
  <span class="nav-logo">&#9889;&thinsp;FLANG PA</span>
  <span class="nav-sep"></span>
  <div class="nav-tab active" id="tab-overview" onclick="App.setView('overview')">
    Overview
  </div>
  <div class="nav-tab" id="tab-explorer" onclick="App.setView('explorer')">
    Explorer
    <span class="nav-badge" id="nb-files">0</span>
  </div>
  <div class="nav-tab" id="tab-loops" onclick="App.setView('loops')">
    All Loops
    <span class="nav-badge" id="nb-loops">0</span>
  </div>
  <div class="nav-search">
    <span class="nav-search-ico">&#8981;</span>
    <input id="gsearch" placeholder="Search files, loops, reasons&hellip;"
           autocomplete="off" spellcheck="false">
  </div>
  <span class="nav-sep" style="margin-left:6px"></span>
  <span class="nav-kb"><kbd>?</kbd></span>
</div>

<!-- viewport -->
<div id="viewport">

  <!-- VIEW: OVERVIEW -->
  <div id="view-overview" class="view active" style="overflow-y:auto;padding:22px 26px;gap:18px;flex-direction:column">

    <!-- stat cards -->
    <div class="ov-row ov-row-4" id="ov-cards"></div>

    <!-- coverage bar -->
    <div class="ov-card" id="ov-cov"></div>

    <!-- category breakdown + hotspots -->
    <div class="ov-row ov-row-2" id="ov-mid"></div>

    <!-- quick wins + fix suggestions -->
    <div class="ov-row ov-row-2" id="ov-bot"></div>

  </div>

  <!-- VIEW: EXPLORER -->
  <div id="view-explorer" class="view">
    <div id="ex-sidebar"></div>
    <div id="ex-main">
      <div id="ex-srcbar"></div>
      <div id="ex-scroll"><div id="ex-code"></div></div>
    </div>
  </div>

  <!-- VIEW: LOOPS TABLE -->
  <div id="view-loops" class="view">
    <div id="loops-toolbar">
      <div class="lt-filter" id="lt-filters"></div>
      <span class="lt-count" id="lt-count"></span>
      <span class="lt-spacer"></span>
      <select class="lt-sort" id="lt-sort" onchange="App.loopsSort(this.value)">
        <option value="file">Sort: File</option>
        <option value="status">Sort: Status</option>
        <option value="cat">Sort: Category</option>
        <option value="num">Sort: Loop #</option>
      </select>
    </div>
    <div id="loops-scroll">
      <table class="loops-table">
        <thead>
          <tr>
            <th>#</th>
            <th>File</th>
            <th>Status</th>
            <th>Category</th>
            <th>OMP Hint / Fix</th>
          </tr>
        </thead>
        <tbody id="loops-tbody"></tbody>
      </table>
    </div>
    <div id="loops-pager"></div>
  </div>

</div><!-- viewport -->
</div><!-- app -->

<!-- help modal -->
<div id="helpmod">
  <div class="hbox">
    <div class="htitle">Keyboard Shortcuts</div>
    <div class="hrow"><kbd>1</kbd>       <span>Overview</span></div>
    <div class="hrow"><kbd>2</kbd>       <span>Explorer</span></div>
    <div class="hrow"><kbd>3</kbd>       <span>All Loops</span></div>
    <div class="hrow"><kbd>j</kbd><kbd>k</kbd> <span>Prev / next file (Explorer)</span></div>
    <div class="hrow"><kbd>/</kbd>       <span>Focus search</span></div>
    <div class="hrow"><kbd>f</kbd>       <span>Cycle status filter</span></div>
    <div class="hrow"><kbd>Esc</kbd>     <span>Clear / close</span></div>
    <div class="hrow"><kbd>?</kbd>       <span>Toggle this panel</span></div>
    <button class="hclose" onclick="document.getElementById('helpmod').classList.remove('open')">Close</button>
  </div>
</div>

<script>
'use strict';

// ── helpers ───────────────────────────────────────────────────────────────────
function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') }
function q(id){ return document.getElementById(id) }
const KWRE = /\b(subroutine|function|program|module|use|implicit|none|integer|real|logical|character|external|parameter|do|if|then|else|end|return|call|continue|intent|allocate|print|write|read)\b/gi;
function fhl(raw){
  const ci=raw.indexOf('!');
  const code=ci>=0?raw.slice(0,ci):raw, cmt=ci>=0?raw.slice(ci):'';
  let h=esc(code).replace(KWRE,m=>`<span class="fkw">${m}</span>`);
  if(cmt) h+=`<span class="fcmt">${esc(cmt)}</span>`;
  return h;
}

// ── status meta ───────────────────────────────────────────────────────────────
const SM = {
  SAFE:      {fg:'#3fb950',bg:'rgba(63,185,80,.12)', bd:'rgba(63,185,80,.35)', sym:'&#10003;', label:'SAFE'},
  REDUCTION: {fg:'#d29922',bg:'rgba(210,153,34,.12)',bd:'rgba(210,153,34,.35)',sym:'&#8635;',  label:'REDUCTION'},
  UNSAFE:    {fg:'#f85149',bg:'rgba(248,81,73,.12)', bd:'rgba(248,81,73,.35)', sym:'&#10007;', label:'UNSAFE'},
  UNKNOWN:   {fg:'#6e7681',bg:'rgba(110,118,129,.1)',bd:'rgba(110,118,129,.3)',sym:'?',        label:'UNKNOWN'},
};

// ── loop categorizer ──────────────────────────────────────────────────────────
function catLoop(l){
  if(l.status==='SAFE')
    return {id:'safe',      label:'Independent',         color:SM.SAFE.fg,    fix:l.hint||'!$OMP PARALLEL DO'};
  if(l.status==='REDUCTION')
    return {id:'redu',      label:'Reduction pattern',   color:SM.REDUCTION.fg, fix:l.hint};
  const r=(l.reason+' '+l.hint).toLowerCase();
  if(r.includes('cannot')||r.includes('offset')||r.includes('carried')||r.includes('i-1')||r.includes('i+1'))
    return {id:'lcdep',     label:'Loop-carried dep',    color:'#f85149', fix:'Loop fission, prefix-sum, or serial prefix pass'};
  if(r.includes('in-place')||r.includes('inplace'))
    return {id:'inplace',   label:'In-place update',     color:'#e8854a', fix:'Separate source / destination arrays'};
  if(r.includes('indirect')||r.includes('scatter')||r.includes('gather')||r.includes('unknown subscript'))
    return {id:'indirect',  label:'Indirect access',     color:'#b07af5', fix:'Atomics or inspector-executor pattern'};
  if(r.includes('nested')||r.includes('multi-dim')||r.includes('outer'))
    return {id:'multidim',  label:'Multi-dim nest',      color:'#e8a040', fix:'Parallelize outermost loop only'};
  if(r.includes('external')||r.includes('opaque')||r.includes('call'))
    return {id:'extcall',   label:'Opaque function',     color:'#8b949e', fix:'Mark PURE if side-effect free'};
  return     {id:'inconcl', label:'Inconclusive',        color:'#8b949e', fix:'Manual review required'};
}

// ── frontend reasoning engine (pure JS, no backend changes) ──────────────────

function getPhases(l) {
  const r=(l.reason+' '+l.hint).toLowerCase();
  const hasOffset=r.includes('offset')||r.includes('cannot')||r.includes('i-1')||r.includes('i+1')||r.includes('carried');
  const isInconclusive=r.includes('inconclusive')||r.includes('could not');
  const isReadOnly=r.includes('no external write')||r.includes('read-only');
  const p=(num,name,st,detail)=>({num,name,st,detail});
  const p1=p(1,'Structure',   'pass',(l.bounds||'?')+(l.depth>0?' · depth '+l.depth:''));
  const p2=p(2,'Mem Access',  'pass',`${l.accesses.length} ref${l.accesses.length!==1?'s':''} catalogued`);
  if(l.status==='SAFE'&&!isReadOnly)
    return[p1,p2,p(3,'Index Analysis','pass','All subscripts IV-derived'),p(4,'Reduction','skip','Not needed'),p(5,'Fallback','skip','Not needed')];
  if(l.status==='SAFE'&&isReadOnly)
    return[p1,p2,p(3,'Index Analysis','warn','Unknown subscripts deferred'),p(4,'Reduction','warn','No pattern'),p(5,'Fallback','pass','No ext writes → SAFE')];
  if(l.status==='REDUCTION')
    return[p1,p2,p(3,'Index Analysis','warn','RW scalar — deferred to Ph4'),p(4,'Reduction','pass','load → op → store matched'),p(5,'Fallback','skip','Not needed')];
  if(l.status==='UNSAFE'&&hasOffset)
    return[p1,p2,p(3,'Index Analysis','fail','IV±k offset detected — stopped'),p(4,'Reduction','skip','Skipped after Ph3 UNSAFE'),p(5,'Fallback','skip','Skipped after Ph3 UNSAFE')];
  return[p1,p2,p(3,'Index Analysis','warn','Unknown subscript(s)'),p(4,'Reduction','warn','No pattern'),
    p(5,'Fallback','fail',isInconclusive?'Inconclusive → conservative UNSAFE':'Ext writes present → UNSAFE')];
}

function getConfidence(l) {
  const r=(l.reason+' '+l.hint).toLowerCase();
  const hasOffset=r.includes('offset')||r.includes('cannot')||r.includes('i-1')||r.includes('i+1');
  const isInconclusive=r.includes('inconclusive')||r.includes('could not');
  if(l.status==='UNSAFE'&&hasOffset)    return{level:'HIGH',  pct:95,color:'#3fb950'};
  if(l.status==='SAFE'&&!isInconclusive)return{level:'HIGH',  pct:90,color:'#3fb950'};
  if(l.status==='REDUCTION')            return{level:'HIGH',  pct:88,color:'#3fb950'};
  if(l.status==='UNSAFE'&&isInconclusive)return{level:'LOW',  pct:32,color:'#f85149'};
  return{level:'MED',pct:58,color:'#d29922'};
}

function parseIssues(l) {
  const r=(l.reason+' '+l.hint).toLowerCase();
  const out=[];
  if(r.includes('offset')||r.includes('i-1')||r.includes('i+1')||r.includes('carried')||r.includes('cannot'))
    out.push({icon:'&#10007;',color:'#f85149',label:'Loop-carried dependency',detail:'Subscript i±k detected in Phase 3'});
  if(r.includes('in-place')||r.includes('inplace'))
    out.push({icon:'&#9650;', color:'#d29922',label:'In-place array update',  detail:'Same array is source and destination'});
  if(r.includes('indirect')||r.includes('unknown subscript')||r.includes('non-iv'))
    out.push({icon:'&#9650;', color:'#d29922',label:'Unknown subscript',       detail:'Cannot trace index pattern statically'});
  if(r.includes('nested')||r.includes('multi-dim')||r.includes('outer'))
    out.push({icon:'&#9650;', color:'#d29922',label:'Multi-dimensional nest',  detail:'Outer IV unrecognizable from inner loop'});
  if(r.includes('external')||r.includes('opaque')||r.includes('call'))
    out.push({icon:'&#9650;', color:'#d29922',label:'Opaque function call',    detail:'Side effects unknown to the pass'});
  if(r.includes('inconclusive')||r.includes('could not'))
    out.push({icon:'?',        color:'#6e7681',label:'Analysis inconclusive',   detail:'Phase 5 conservative fallback applied'});
  if(l.status==='SAFE')
    out.push({icon:'&#10003;',color:'#3fb950',label:'Independent element access',detail:'Each iteration touches a unique memory cell'});
  if(l.status==='REDUCTION'&&!out.length)
    out.push({icon:'&#8635;', color:'#d29922',label:'Scalar accumulation pattern',detail:'load → addf/mulf → store chain matched'});
  return out.length?out:[{icon:'?',color:'#6e7681',label:'Reason not parsed',detail:l.reason||'No reason provided'}];
}

function getShortLabel(l) {
  const r=(l.reason+' '+l.hint).toLowerCase();
  if(l.status==='SAFE')return r.includes('no external write')||r.includes('read-only')?'safe · read-only':'safe · independent';
  if(l.status==='REDUCTION')return r.includes('*')||r.includes('mul')?'redu · product':'redu · sum';
  if(r.includes('i-1'))return 'dep · i−1';
  if(r.includes('i+1'))return 'dep · i+1';
  if(r.includes('offset')||r.includes('carried')||r.includes('cannot'))return 'dep · offset';
  if(r.includes('in-place')||r.includes('inplace'))return 'unsafe · in-place';
  if(r.includes('indirect')||r.includes('scatter')||r.includes('gather'))return 'unsafe · indirect';
  if(r.includes('nested')||r.includes('multi'))return 'unsafe · nested';
  if(r.includes('call')||r.includes('external'))return 'unsafe · ext-call';
  if(r.includes('inconclusive')||r.includes('could not'))return 'unsafe · inconclusive';
  return 'unsafe · unknown';
}

function buildDepViz(l) {
  const r=(l.reason+' '+l.hint).toLowerCase();
  if(!r.includes('i-1')&&!r.includes('i+1')&&!r.includes('offset')&&!r.includes('carried'))return null;
  if(r.includes('i+1'))
    return['iter[i]   ',{t:' ──writes──▶ ',d:true},'A[i+1]','\n          ↓ stored value\n','iter[i+1] ',{t:' ──reads───▶ ',d:true},{t:'A[i+1]',bad:true},{t:'  ✗ WAR conflict',bad:true}];
  return['iter[i-1] ',{t:' ──writes──▶ ',d:true},'A[i-1]','\n          ↓ stored value\n','iter[i]   ',{t:' ──reads───▶ ',d:true},{t:'A[i-1]',bad:true},{t:'  ✗ RAW conflict',bad:true}];
}

function renderPhases(l) {
  const ph=getPhases(l);
  const icons={pass:'&#10003;',fail:'&#10007;',warn:'&#9650;',skip:'&mdash;'};
  const cols={pass:'var(--safe)',fail:'var(--unsafe)',warn:'var(--redu)',skip:'var(--muted)'};
  return ph.map(p=>`<div class="ph-row">
    <span class="ph-num">${p.num}</span>
    <span class="ph-name">${p.name}</span>
    <span class="ph-icon" style="color:${cols[p.st]}">${icons[p.st]}</span>
    <span class="ph-detail ${p.st}">${esc(p.detail)}</span>
  </div>`).join('');
}

function renderIssues(l) {
  return parseIssues(l).map(i=>`<div class="issue-row">
    <span class="issue-icon" style="color:${i.color}">${i.icon}</span>
    <div><div class="issue-label">${i.label}</div>
         <div class="issue-detail">${esc(i.detail)}</div></div>
  </div>`).join('');
}

function renderConf(l) {
  const c=getConfidence(l);
  return `<span class="conf-badge" style="color:${c.color};border-color:${c.color}44;background:${c.color}18">
    ${c.level}&thinsp;<span class="conf-bar"><span class="conf-fill" style="width:${c.pct}%;background:${c.color}"></span></span>&thinsp;<span style="color:var(--muted);font-weight:400">${c.pct}%</span>
  </span>`;
}

// ── pre-process data ──────────────────────────────────────────────────────────
const allLoops = DATA.flatMap((f,fi)=>
  f.loops.map(l=>({...l,_fi:fi,_fname:f.name,_path:f.path,_cat:catLoop(l)}))
);
const unsafeLoops = allLoops.filter(l=>l.status==='UNSAFE');
const safeLoops   = allLoops.filter(l=>l.status==='SAFE');
const reduLoops   = allLoops.filter(l=>l.status==='REDUCTION');

// category counts
const catMap={};
unsafeLoops.forEach(l=>{
  const c=l._cat;
  if(!catMap[c.id]) catMap[c.id]={...c,count:0};
  catMap[c.id].count++;
});
const catList=Object.values(catMap).sort((a,b)=>b.count-a.count);

// hotspot files (most unsafe)
const hotspots=DATA.map((f,i)=>({...f,_i:i}))
  .filter(f=>f.nUnsafe>0).sort((a,b)=>b.nUnsafe-a.nUnsafe);

// file groups for explorer sidebar
function fileGroup(f){
  if(f.nUnsafe>0) return 'unsafe';
  if(f.nReduction>0) return 'reduction';
  if(f.nSafe>0) return 'safe';
  return 'unknown';
}

// ── app state ─────────────────────────────────────────────────────────────────
const App = {
  view:'overview',
  exFileIdx:0, exPeekLoop:null,
  ltFilter:'ALL', ltPage:0, ltExpanded:null, ltSort:'file',
  search:'',
  PER_PAGE:20,

  // ── view switching ──────────────────────────────────────────────────────────
  setView(v){
    this.view=v;
    ['overview','explorer','loops'].forEach(id=>{
      const el=q(`view-${id}`);
      el.classList.toggle('active',id===v);
    });
    ['overview','explorer','loops'].forEach(id=>{
      q(`tab-${id}`).classList.toggle('active',id===v);
    });
    if(v==='overview') this.rOverview();
    if(v==='explorer') this.rExplorer();
    if(v==='loops')    this.rLoops();
  },

  // ── overview ────────────────────────────────────────────────────────────────
  rOverview(){
    const s=STATS;
    const total=s.loops, par=s.safe+s.reduction;
    const pct=total?Math.round(par/total*100):0;

    // stat cards
    q('ov-cards').innerHTML=`
      <div class="ov-card c-safe">
        <div class="ov-card-label">Safe to parallelize</div>
        <div class="ov-card-num" style="color:var(--safe)">${s.safe}</div>
        <div class="ov-card-sub">loops ready for !$OMP PARALLEL DO</div>
      </div>
      <div class="ov-card c-redu">
        <div class="ov-card-label">Reduction loops</div>
        <div class="ov-card-num" style="color:var(--redu)">${s.reduction}</div>
        <div class="ov-card-sub">need REDUCTION clause</div>
      </div>
      <div class="ov-card c-unsafe">
        <div class="ov-card-label">Unsafe / blocked</div>
        <div class="ov-card-num" style="color:var(--unsafe)">${s.unsafe}</div>
        <div class="ov-card-sub">require restructuring</div>
      </div>
      <div class="ov-card c-amber">
        <div class="ov-card-label">Parallelizable</div>
        <div class="ov-card-num" style="color:var(--amber)">${pct}%</div>
        <div class="ov-card-sub">${par} of ${total} loops</div>
      </div>`;

    // coverage bar
    const sw=total?s.safe/total*100:0;
    const rw=total?s.reduction/total*100:0;
    const uw=total?s.unsafe/total*100:0;
    q('ov-cov').innerHTML=`
      <div class="ov-panel-hdr"><span class="ov-panel-title">Parallelization Coverage</span></div>
      <div class="ov-cov-bar">
        <div class="ov-cov-seg" style="width:${sw}%;background:var(--safe)"></div>
        <div class="ov-cov-seg" style="width:${rw}%;background:var(--redu)"></div>
        <div class="ov-cov-seg" style="width:${uw}%;background:var(--unsafe)"></div>
      </div>
      <div class="ov-cov-legend">
        <span><span class="ov-cov-dot" style="background:var(--safe)"></span>${s.safe} SAFE</span>
        <span><span class="ov-cov-dot" style="background:var(--redu)"></span>${s.reduction} REDUCTION</span>
        <span><span class="ov-cov-dot" style="background:var(--unsafe)"></span>${s.unsafe} UNSAFE</span>
        <span><span class="ov-cov-dot" style="background:var(--muted)"></span>${total} total loops in ${s.files} files</span>
      </div>`;

    // mid row: why-unsafe + hotspots
    const maxCat=catList[0]?catList[0].count:1;
    const catRows=catList.map(c=>`
      <div class="cat-row">
        <span class="cat-label">${esc(c.label)}</span>
        <div class="cat-track"><div class="cat-fill" style="width:${c.count/maxCat*100}%;background:${c.color}"></div></div>
        <span class="cat-n">${c.count}</span>
        <span class="cat-pct">${Math.round(c.count/unsafeLoops.length*100)}%</span>
        <div class="cat-fix">&#128161; Fix: ${esc(c.fix)}</div>
      </div>`).join('');

    const maxHs=hotspots[0]?hotspots[0].nUnsafe:1;
    const hsRows=hotspots.slice(0,6).map(f=>`
      <div class="hs-row" onclick="App.goExplorer(${f._i})">
        <span class="hs-name">${esc(f.name)}</span>
        <div class="hs-bar" style="width:80px">
          <div class="hs-bar-inner" style="width:${f.nUnsafe/maxHs*100}%"></div>
        </div>
        <span class="hs-cnt">${f.nUnsafe}&#10007;</span>
      </div>`).join('');

    q('ov-mid').innerHTML=`
      <div class="ov-panel" ${!unsafeLoops.length?'style="display:none"':''}>
        <div class="ov-panel-hdr">
          <span class="ov-panel-title">Why Unsafe <span style="font-weight:400;color:var(--muted)">(hover for fix)</span></span>
          <span class="ov-panel-more" onclick="App.setView('loops');App.ltFilter='UNSAFE';App.rLoops()">See all &#8594;</span>
        </div>
        ${catRows||'<div style="color:var(--muted);font-size:11px">No unsafe loops</div>'}
      </div>
      <div class="ov-panel" ${!hotspots.length?'style="display:none"':''}>
        <div class="ov-panel-hdr">
          <span class="ov-panel-title">Hotspot Files</span>
          <span class="ov-panel-more" onclick="App.setView('explorer')">Open &#8594;</span>
        </div>
        ${hsRows||'<div style="color:var(--muted);font-size:11px">No hotspots</div>'}
      </div>`;

    // bottom row: quick wins + fix suggestions
    const wins=[...safeLoops,...reduLoops].slice(0,8);
    const wRows=wins.map(l=>`
      <div class="qw-row" onclick="App.goExplorer(${l._fi},${l.num})">
        <span class="qw-pill ${l.status}">${SM[l.status].sym} ${l.status}</span>
        <span class="qw-file">${esc(l._fname)}</span>
        <span class="qw-hint">${esc(l.hint)}</span>
      </div>`).join('');

    const fixCats=[...new Set(catList.map(c=>c.id))];
    const fRows=catList.slice(0,5).map(c=>`
      <div style="padding:6px 0;border-bottom:1px solid var(--border-l)">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:3px">
          <span style="width:8px;height:8px;border-radius:50%;background:${c.color};
                       display:inline-block;flex-shrink:0"></span>
          <span style="font-size:11px;font-weight:600">${esc(c.label)}</span>
          <span style="font-family:var(--mono);font-size:10px;color:var(--muted);margin-left:auto">${c.count} loops</span>
        </div>
        <div style="font-size:10px;color:var(--amber);padding-left:16px;font-style:italic">&#128161; ${esc(c.fix)}</div>
      </div>`).join('');

    q('ov-bot').innerHTML=`
      <div class="ov-panel">
        <div class="ov-panel-hdr">
          <span class="ov-panel-title">Quick Wins</span>
          <span class="ov-panel-more" onclick="App.setView('loops');App.ltFilter='SAFE';App.rLoops()">All safe &#8594;</span>
        </div>
        ${wRows||'<div style="color:var(--muted);font-size:11px">No parallelizable loops found</div>'}
      </div>
      <div class="ov-panel">
        <div class="ov-panel-hdr"><span class="ov-panel-title">Fix Suggestions</span></div>
        ${fRows||'<div style="color:var(--muted);font-size:11px">No unsafe loops to fix</div>'}
      </div>`;
  },

  goExplorer(fidx, loopNum=null){
    this.exFileIdx=fidx;
    this.exPeekLoop=loopNum;
    this.setView('explorer');
  },

  // ── explorer ─────────────────────────────────────────────────────────────────
  rExplorer(){
    this.rExSidebar();
    this.rExSource();
    if(this.exPeekLoop!==null){
      setTimeout(()=>this.openPeek(this.exPeekLoop),60);
      this.exPeekLoop=null;
    }
  },

  rExSidebar(){
    const groups={safe:[],reduction:[],unsafe:[]};
    DATA.forEach((f,i)=>{ groups[fileGroup(f)].push({...f,_i:i}); });
    const glabels={safe:'SAFE Files',reduction:'Reduction Files',unsafe:'Unsafe Files'};
    const gcolors={safe:'var(--safe)',reduction:'var(--redu)',unsafe:'var(--unsafe)'};
    let html='';
    ['unsafe','reduction','safe'].forEach(gk=>{
      const files=groups[gk]; if(!files.length) return;
      html+=`<div class="ex-grp">
        <div class="ex-grp-hdr" onclick="App.toggleGrp(this)">
          <span class="ex-chev open" style="color:${gcolors[gk]}">&#9654;</span>
          <span style="color:${gcolors[gk]}">${glabels[gk]}</span>
          <span class="ex-gcnt">${files.length}</span>
        </div><div class="ex-gbody">`;
      files.forEach(f=>{
        const active=f._i===this.exFileIdx;
        let dot=SM[gk==='safe'?'SAFE':gk==='reduction'?'REDUCTION':'UNSAFE'].fg;
        const ct=[
          f.nSafe>0      ?`<span style="color:var(--safe)">${f.nSafe}&#10003;</span>`:'',
          f.nReduction>0 ?`<span style="color:var(--redu)">${f.nReduction}&#8635;</span>`:'',
          f.nUnsafe>0    ?`<span style="color:var(--unsafe)">${f.nUnsafe}&#10007;</span>`:'',
        ].filter(Boolean).join('&thinsp;');
        html+=`<div class="ex-file${active?' active':''}" onclick="App.exSelect(${f._i})">
          <div class="ex-fdot" style="background:${dot}"></div>
          <span class="ex-fname">${esc(f.name)}</span>
          <span class="ex-fct">${ct}</span>
        </div>`;
      });
      html+='</div></div>';
    });
    q('ex-sidebar').innerHTML=html||'<div style="padding:20px;color:var(--muted);font-size:11px">No files</div>';
  },

  toggleGrp(hdr){
    const body=hdr.nextElementSibling, chev=hdr.querySelector('.ex-chev');
    const open=chev.classList.contains('open');
    body.style.display=open?'none':'';
    chev.classList.toggle('open',!open);
  },

  exSelect(idx){
    this.exFileIdx=idx; this.exPeekLoop=null;
    this.rExSidebar(); this.rExSource();
  },

  rExSource(){
    const f=DATA[this.exFileIdx];
    q('ex-srcbar').innerHTML=f?`<div class="ex-tab active">${esc(f.name)}</div>`:'';
    if(!f){ q('ex-code').innerHTML='<div style="padding:32px;color:var(--muted)">Select a file</div>'; return; }
    const lmap={};
    f.loops.forEach(lp=>{ if(lp.sourceLine) lmap[lp.sourceLine]=lp; });
    const lines=f.source.split('\n');
    let html='';
    lines.forEach((raw,i)=>{
      const ln=i+1, lp=lmap[ln];
      const id=lp?` id="sl-${lp.num}"`:'';
      const onclick=lp?` onclick="App.togglePeek(${lp.num})"`:'';
      let gdot='<div class="gdot" style="opacity:0"></div>', badge='';
      if(lp){
        const sc=SM[lp.status]||SM.UNKNOWN;
        gdot=`<div class="gdot" style="background:${sc.fg}"></div>`;
        badge=`<span class="sbadge" style="color:${sc.fg};background:${sc.bg};border-color:${sc.bd}">${sc.sym} ${getShortLabel(lp)}</span>`;
      }
      html+=`<div class="sln${lp?' loop-ln':''}"${id}${onclick}>
        <div class="gutter"><span class="lnum">${ln}</span>${gdot}</div>
        <span class="stext">${fhl(raw)}</span>${badge}</div>`;
    });
    q('ex-code').innerHTML=html;
  },

  togglePeek(loopNum){
    if(this.exPeekLoop===loopNum){ this.closePeek(); return; }
    this.closePeek();
    this.openPeek(loopNum);
  },

  openPeek(loopNum){
    this.exPeekLoop=loopNum;
    const f=DATA[this.exFileIdx]; if(!f) return;
    const lp=f.loops.find(l=>l.num===loopNum); if(!lp) return;
    const sc=SM[lp.status]||SM.UNKNOWN;
    const cat=catLoop(lp);

    // dependency flow visualization
    const dvSegs=buildDepViz(lp);
    let dvBlock='';
    if(dvSegs){
      let inner='';
      dvSegs.forEach(s=>{
        if(typeof s==='string') inner+=esc(s);
        else if(s.bad) inner+=`<span style="color:var(--unsafe);font-weight:600">${esc(s.t)}</span>`;
        else if(s.d)   inner+=`<span style="color:var(--dim)">${esc(s.t)}</span>`;
        else           inner+=esc(s.t||'');
      });
      dvBlock=`<div class="peek-sec-hdr" style="margin-top:10px">Dependency Flow</div>
        <div class="dep-viz">${inner}</div>`;
    }

    // memory accesses
    const accRows=(lp.accesses||[]).map(a=>{
      const m=a.match(/^\[(R|W|RW)\]\s*(.+)/);
      if(!m) return `<div class="peek-acc">${esc(a)}</div>`;
      return `<div class="peek-acc"><span class="pacc ${m[1]}">${m[1]}</span>${esc(m[2])}</div>`;
    }).join('');

    const peekHtml=`<div class="peek-panel" id="peek-${loopNum}">
      <div class="peek-top">
        <span class="peek-status ${lp.status}">${sc.sym} ${lp.status}</span>
        <span class="peek-title">Loop #${lp.num} &mdash; ${esc(lp.loc)}</span>
        ${lp.depth>0?`<span style="font-family:var(--mono);font-size:9px;color:var(--muted);background:var(--surf);border:1px solid var(--border);padding:1px 6px;border-radius:3px">depth ${lp.depth}</span>`:''}
        ${renderConf(lp)}
        <span class="peek-close" onclick="App.closePeek()">&#10005;</span>
      </div>
      ${lp.hint?`<div class="peek-hint">${esc(lp.hint)}</div>`:''}
      <div class="peek-row" style="gap:18px;align-items:flex-start;margin-top:4px">
        <div class="peek-col" style="min-width:210px">
          <div class="peek-sec-hdr">Analysis Pipeline</div>
          ${renderPhases(lp)}
        </div>
        <div class="peek-col" style="min-width:190px">
          <div class="peek-sec-hdr">Issues Found</div>
          ${renderIssues(lp)}
          ${dvBlock}
        </div>
        <div class="peek-col" style="min-width:150px">
          ${accRows?`<div class="peek-sec-hdr">Memory Accesses</div>
            <div class="peek-mem">${accRows}</div>`:''}
          ${lp.bounds?`<div class="peek-sec-hdr" style="margin-top:${accRows?'10px':'0'}">Loop Bounds</div>
            <div class="peek-bounds">${esc(lp.bounds)}</div>`:''}
        </div>
      </div>
      ${lp.status!=='SAFE'?`<div class="peek-fix" style="margin-top:10px">&#128161; ${esc(cat.fix)}</div>`:''}
    </div>`;

    // Insert peek after the DO line element
    const slEl=document.getElementById(`sl-${loopNum}`);
    if(!slEl) return;
    slEl.classList.add('peek-open');
    slEl.insertAdjacentHTML('afterend', peekHtml);
    slEl.scrollIntoView({behavior:'smooth', block:'center'});
  },

  closePeek(){
    if(this.exPeekLoop===null) return;
    const old=document.getElementById(`peek-${this.exPeekLoop}`);
    if(old) old.remove();
    const slEl=document.getElementById(`sl-${this.exPeekLoop}`);
    if(slEl) slEl.classList.remove('peek-open');
    this.exPeekLoop=null;
  },

  // ── loops table ──────────────────────────────────────────────────────────────
  loopsData(){
    let ls=allLoops;
    if(this.search){
      const q=this.search.toLowerCase();
      ls=ls.filter(l=>l._fname.toLowerCase().includes(q)||
                      l.reason.toLowerCase().includes(q)||
                      l.hint.toLowerCase().includes(q)||
                      l._cat.label.toLowerCase().includes(q));
    }
    if(this.ltFilter!=='ALL') ls=ls.filter(l=>l.status===this.ltFilter);
    if(this.ltSort==='status') ls=[...ls].sort((a,b)=>a.status.localeCompare(b.status));
    else if(this.ltSort==='cat') ls=[...ls].sort((a,b)=>a._cat.label.localeCompare(b._cat.label));
    else if(this.ltSort==='num') ls=[...ls].sort((a,b)=>a.num-b.num);
    else ls=[...ls].sort((a,b)=>a._fname.localeCompare(b._fname));
    return ls;
  },

  loopsSort(v){ this.ltSort=v; this.ltPage=0; this.ltExpanded=null; this.rLoops(); },

  rLoops(){
    // filter buttons
    const btnDefs=[
      {f:'ALL',cls:'fa',lbl:'All'},
      {f:'SAFE',cls:'fs',lbl:'&#10003; SAFE'},
      {f:'REDUCTION',cls:'fr',lbl:'&#8635; REDU'},
      {f:'UNSAFE',cls:'fu',lbl:'&#10007; UNSAFE'},
    ];
    q('lt-filters').innerHTML=btnDefs.map(b=>`
      <button class="lt-fbtn${this.ltFilter===b.f?' '+b.cls:''}" onclick="App.ltSetFilter('${b.f}')">${b.lbl}</button>
    `).join('');

    const ls=this.loopsData();
    const pages=Math.max(1,Math.ceil(ls.length/this.PER_PAGE));
    if(this.ltPage>=pages) this.ltPage=0;
    const slice=ls.slice(this.ltPage*this.PER_PAGE,(this.ltPage+1)*this.PER_PAGE);

    q('lt-count').textContent=`${ls.length} loop${ls.length!==1?'s':''}`;

    // table rows
    let rows='';
    slice.forEach((l,si)=>{
      const rowIdx=this.ltPage*this.PER_PAGE+si;
      const sc=SM[l.status]||SM.UNKNOWN;
      const exp=this.ltExpanded===rowIdx;
      rows+=`<tr class="lt-row${exp?' expanded':''}" onclick="App.ltToggle(${rowIdx})">
        <td>${l.num}</td>
        <td><div class="lt-file">${esc(l._fname)}</div>
            ${l.sourceLine?`<div class="lt-file-line">line ${l.sourceLine}</div>`:''}</td>
        <td><span class="lt-status ${l.status}">${sc.sym} ${l.status}</span></td>
        <td><span class="lt-cat" style="color:${l._cat.color}">${esc(l._cat.label)}</span></td>
        <td><span class="lt-hint">${esc(l.hint||l._cat.fix)}</span></td>
      </tr>`;
      if(exp){
        const accHtml=(l.accesses||[]).map(a=>{
          const m=a.match(/^\[(R|W|RW)\]\s*(.+)/);
          if(!m) return `<span class="lt-exp-acc">${esc(a)}</span>`;
          return `<span class="lt-exp-acc"><span class="pacc ${m[1]}">${m[1]}</span>${esc(m[2])}</span>`;
        }).join('');
        rows+=`<tr class="lt-expand-row">
          <td colspan="5"><div class="lt-expand-inner">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:10px">
              <div>
                <div class="peek-sec-hdr">Analysis Pipeline</div>
                ${renderPhases(l)}
              </div>
              <div>
                <div class="peek-sec-hdr" style="display:flex;align-items:center;gap:8px">Issues Found ${renderConf(l)}</div>
                ${renderIssues(l)}
              </div>
            </div>
            ${l.status!=='SAFE'?`<div class="lt-exp-fix">&#128161; ${esc(l._cat.fix)}</div>`:''}
            ${accHtml?`<div class="lt-exp-accs">${accHtml}</div>`:''}
            <span class="lt-exp-goto" onclick="event.stopPropagation();App.goExplorer(${l._fi},${l.num})">
              &#8594; Open in Explorer
            </span>
          </div></td>
        </tr>`;
      }
    });
    q('loops-tbody').innerHTML=rows;

    // pagination
    let pager=`<button class="pg-btn" onclick="App.ltPage--,App.rLoops()" ${this.ltPage===0?'disabled':''}>&#8592; Prev</button>`;
    const maxPg=Math.min(pages,7);
    for(let i=0;i<pages&&i<maxPg;i++){
      pager+=`<span class="pg-num${i===this.ltPage?' active':''}" onclick="App.ltPage=${i},App.rLoops()">${i+1}</span>`;
    }
    if(pages>maxPg) pager+=`<span style="color:var(--muted);font-size:10px">…${pages}</span>`;
    pager+=`<button class="pg-btn" onclick="App.ltPage++,App.rLoops()" ${this.ltPage>=pages-1?'disabled':''}>Next &#8594;</button>`;
    pager+=`<span class="pg-spacer"></span>
      <span class="pg-info">${this.ltPage*this.PER_PAGE+1}–${Math.min((this.ltPage+1)*this.PER_PAGE,ls.length)} of ${ls.length}</span>`;
    q('loops-pager').innerHTML=pager;
  },

  ltSetFilter(f){ this.ltFilter=f; this.ltPage=0; this.ltExpanded=null; this.rLoops(); },
  ltToggle(i){ this.ltExpanded=this.ltExpanded===i?null:i; this.rLoops(); },

  // ── keyboard + events ────────────────────────────────────────────────────────
  bind(){
    document.addEventListener('keydown',e=>{
      const inp=document.activeElement.tagName==='INPUT';
      if(e.key==='Escape'){
        if(inp){document.activeElement.blur();this.search='';this.rExSidebar&&this.rExSidebar();}
        q('helpmod').classList.remove('open');
        this.closePeek(); return;
      }
      if(inp) return;
      if(e.key==='1') this.setView('overview');
      if(e.key==='2') this.setView('explorer');
      if(e.key==='3') this.setView('loops');
      if(e.key==='?') q('helpmod').classList.toggle('open');
      if(e.key==='/'){e.preventDefault();q('gsearch').focus();}
      if(e.key==='j'&&this.view==='explorer'){
        e.preventDefault();
        const nxt=Math.min(this.exFileIdx+1,DATA.length-1);
        if(nxt!==this.exFileIdx){this.exFileIdx=nxt;this.exPeekLoop=null;this.rExplorer();}
      }
      if(e.key==='k'&&this.view==='explorer'){
        e.preventDefault();
        const prv=Math.max(this.exFileIdx-1,0);
        if(prv!==this.exFileIdx){this.exFileIdx=prv;this.exPeekLoop=null;this.rExplorer();}
      }
      if(e.key==='f'){
        e.preventDefault();
        const ord=['ALL','SAFE','REDUCTION','UNSAFE'];
        if(this.view==='loops'){this.ltFilter=ord[(ord.indexOf(this.ltFilter)+1)%ord.length];this.ltPage=0;this.rLoops();}
      }
    });
    q('gsearch').addEventListener('input',e=>{
      this.search=e.target.value;
      if(this.view==='loops') this.rLoops();
      else if(this.view==='explorer') this.rExSidebar();
    });
  },

  init(){
    // update nav badges
    q('nb-files').textContent=STATS.files;
    q('nb-loops').textContent=STATS.loops;
    this.rOverview();
    this.bind();
  }
};

document.addEventListener('DOMContentLoaded',()=>App.init());
</script>
</body>
</html>
"""

# ── build ─────────────────────────────────────────────────────────────────────

def build_html(file_data_list, stats):
    data_json  = json.dumps(file_data_list, ensure_ascii=False)
    stats_json = json.dumps(stats)
    return TEMPLATE.replace('%%DATA%%', data_json).replace('%%STATS%%', stats_json)

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Generate IDE-style parallelism report")
    ap.add_argument("files", nargs="*")
    ap.add_argument("-o","--output", default="report.html")
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()

    if not args.files:
        args.files = (sorted(Path("tests/fortran").glob("*.f90")) +
                      sorted(Path("tests/comprehensive").glob("*.f90")))

    file_data_list = []
    stats = {"files":0,"loops":0,"safe":0,"reduction":0,"unsafe":0}

    for f90 in args.files:
        print(f"Analysing {f90} …", file=sys.stderr)
        try: source = open(f90).read()
        except OSError as e: print(f"  cannot read: {e}", file=sys.stderr); continue
        out = analyse(str(f90))
        if out is None: continue
        loops = parse_loops(out)
        print(f"  → {len(loops)} loop(s): "+", ".join(f'#{l["num"]} {l["status"]}' for l in loops), file=sys.stderr)
        fd = build_file_data(f90, source, loops)
        file_data_list.append(fd)
        stats["files"]     += 1
        stats["loops"]     += len(loops)
        stats["safe"]      += fd["nSafe"]
        stats["reduction"] += fd["nReduction"]
        stats["unsafe"]    += fd["nUnsafe"]

    if not file_data_list:
        print("No files analysed.", file=sys.stderr); sys.exit(1)

    html = build_html(file_data_list, stats)
    with open(args.output,"w") as f: f.write(html)
    print(f"\nReport → {args.output}", file=sys.stderr)
    if args.open:
        webbrowser.open(f"file://{os.path.abspath(args.output)}")

if __name__ == "__main__":
    main()
