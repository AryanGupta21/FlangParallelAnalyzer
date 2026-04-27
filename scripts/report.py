#!/usr/bin/env python3
"""
report.py — IDE-style parallelism report for FlangParallelAnalyzer.

Three-panel fixed layout (no page scroll):
  sidebar | source viewer | loop inspector

Usage:
    python3 scripts/report.py                        # all tests
    python3 scripts/report.py tests/fortran/*.f90    # specific files
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

def analyse(f90_path):
    fir = f"/tmp/fpa_{Path(f90_path).stem}.fir"
    r = subprocess.run([FLANG, "-fc1", "-emit-fir", str(f90_path), "-o", fir],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  flang error: {r.stderr.strip()}", file=sys.stderr)
        return None
    r = subprocess.run([FPA_TOOL, fir], capture_output=True, text=True)
    return r.stdout

def parse_loops(output):
    loops, cur = [], None
    for raw in output.splitlines():
        line = raw.strip()
        m = re.match(r"Loop #(\d+) @ (.+)", line)
        if m:
            cur = dict(num=int(m.group(1)), loc=m.group(2),
                       status="UNKNOWN", hint="", reason="", bounds="", depth=0, accesses=[])
            loops.append(cur)
            continue
        if cur is None:
            continue
        if line.startswith("Bounds :"):
            cur["bounds"] = line[8:].strip()
            d = re.search(r"depth=(\d+)", line)
            if d: cur["depth"] = int(d.group(1))
        elif line.startswith("Status :"):  cur["status"] = line[8:].strip()
        elif line.startswith("Hint   :"): cur["hint"]   = line[8:].strip()
        elif line.startswith("Reason :"): cur["reason"] = line[8:].strip()
        elif re.match(r"\[(R|W|RW)\]", line): cur["accesses"].append(line)
    return loops

def do_loop_lines(source):
    result = []
    for i, line in enumerate(source.splitlines(), 1):
        if re.match(r"\s*do\s+\w+\s*=", line, re.IGNORECASE):
            result.append(i)
    return result

def build_file_data(fname, source, loops):
    dl = do_loop_lines(source)
    enriched = []
    for i, lp in enumerate(loops):
        lp2 = dict(lp)
        lp2["sourceLine"] = dl[i] if i < len(dl) else None
        enriched.append(lp2)
    return {
        "name":        os.path.basename(str(fname)),
        "path":        str(fname),
        "source":      source,
        "loops":       enriched,
        "nSafe":       sum(1 for l in loops if l["status"] == "SAFE"),
        "nReduction":  sum(1 for l in loops if l["status"] == "REDUCTION"),
        "nUnsafe":     sum(1 for l in loops if l["status"] == "UNSAFE"),
    }

# ── HTML template (%%DATA%% and %%STATS%% are replaced at build time) ─────────

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FlangPA — Loop Parallelism</title>
<style>
:root{
  --bg:#0d1117;--surf:#161b22;--surf2:#1c2128;
  --border:#30363d;--border-l:#21262d;
  --text:#cdd9e5;--dim:#768390;--muted:#444c56;
  --safe:#57ab5a;--safe-bg:rgba(87,171,90,.13);--safe-bd:rgba(87,171,90,.4);
  --redu:#daaa3f;--redu-bg:rgba(218,170,63,.13);--redu-bd:rgba(218,170,63,.4);
  --unsafe:#e5534b;--unsafe-bg:rgba(229,83,75,.13);--unsafe-bd:rgba(229,83,75,.4);
  --accent:#539bf5;
  --mono:"Cascadia Code","JetBrains Mono","Fira Code","SF Mono",Consolas,monospace;
  --ui:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden;background:var(--bg);color:var(--text);
          font-family:var(--ui);font-size:13px;-webkit-font-smoothing:antialiased}

/* ── layout ── */
#app{display:grid;grid-template-rows:42px 1fr 22px;height:100vh}
#workspace{display:grid;grid-template-columns:220px 1fr 320px;
           overflow:hidden;min-height:0}

/* ── titlebar ── */
#titlebar{display:flex;align-items:center;gap:10px;padding:0 14px;
          background:var(--surf);border-bottom:1px solid var(--border);
          user-select:none;overflow:hidden}
.tbar-logo{font-family:var(--mono);font-size:11px;font-weight:700;
           color:var(--accent);letter-spacing:.1em;white-space:nowrap}
.tbar-sep{width:1px;height:18px;background:var(--border);flex-shrink:0}
#search-wrap{position:relative;flex:1;max-width:260px}
#search{width:100%;background:var(--bg);border:1px solid var(--border);
        border-radius:5px;color:var(--text);font-family:var(--mono);
        font-size:11px;padding:4px 8px 4px 26px;outline:none;
        transition:border-color .15s}
#search:focus{border-color:var(--accent)}
#search::placeholder{color:var(--muted)}
.search-ico{position:absolute;left:8px;top:50%;transform:translateY(-50%);
            color:var(--muted);font-size:10px;pointer-events:none}
.filter-grp{display:flex;gap:2px}
.fbtn{padding:3px 9px;border-radius:4px;border:1px solid var(--border);
      background:transparent;color:var(--dim);font-family:var(--mono);
      font-size:10px;font-weight:700;cursor:pointer;transition:all .12s;
      letter-spacing:.04em}
.fbtn:hover{border-color:var(--dim);color:var(--text)}
.fbtn.fa {background:var(--surf2);border-color:var(--dim);color:var(--text)}
.fbtn.fs {background:var(--safe-bg);border-color:var(--safe-bd);color:var(--safe)}
.fbtn.fr {background:var(--redu-bg);border-color:var(--redu-bd);color:var(--redu)}
.fbtn.fu {background:var(--unsafe-bg);border-color:var(--unsafe-bd);color:var(--unsafe)}
.stat-row{display:flex;gap:10px;margin-left:auto}
.spill{font-family:var(--mono);font-size:10px;display:flex;align-items:center;gap:4px}
.sdot{width:6px;height:6px;border-radius:50%}
.kb-tip{font-size:10px;color:var(--muted);font-family:var(--mono);white-space:nowrap}
.kb-tip kbd{background:var(--surf2);border:1px solid var(--border);
             border-radius:3px;padding:0 4px;font-family:inherit}

/* ── sidebar ── */
#sidebar{overflow-y:auto;overflow-x:hidden;border-right:1px solid var(--border);
         background:var(--surf)}
#sidebar::-webkit-scrollbar{width:3px}
#sidebar::-webkit-scrollbar-thumb{background:var(--border)}
.grp-head{display:flex;align-items:center;gap:5px;padding:7px 10px;
          font-size:10px;font-weight:700;color:var(--dim);
          letter-spacing:.08em;text-transform:uppercase;
          cursor:pointer;user-select:none}
.grp-head:hover{color:var(--text)}
.chev{transition:transform .15s;font-size:8px;display:inline-block}
.chev.open{transform:rotate(90deg)}
.gcnt{margin-left:auto;background:var(--surf2);border-radius:8px;
      padding:1px 6px;font-size:9px;color:var(--muted)}
.fitem{display:flex;align-items:center;gap:6px;padding:5px 10px 5px 20px;
       cursor:pointer;font-family:var(--mono);font-size:11px;color:var(--dim);
       border-left:2px solid transparent;transition:all .1s;
       white-space:nowrap;overflow:hidden}
.fitem:hover{background:var(--surf2);color:var(--text)}
.fitem.active{background:rgba(83,155,245,.08);border-left-color:var(--accent);
              color:var(--text)}
.fdot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.fname-txt{overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0}
.fcnt{font-size:9px;color:var(--muted);flex-shrink:0;display:flex;gap:3px}
.fcnt span{font-weight:700}

/* ── source panel ── */
#source-panel{display:flex;flex-direction:column;overflow:hidden;background:var(--bg)}
#src-tabbar{display:flex;align-items:center;border-bottom:1px solid var(--border);
            background:var(--surf);padding:0 14px;min-height:33px;
            overflow-x:auto;gap:0}
#src-tabbar::-webkit-scrollbar{height:0}
.stab{padding:6px 14px;font-family:var(--mono);font-size:11px;color:var(--dim);
      cursor:pointer;white-space:nowrap;border-bottom:2px solid transparent;
      margin-bottom:-1px;transition:all .12s}
.stab:hover{color:var(--text)}
.stab.active{color:var(--text);border-bottom-color:var(--accent)}
#src-scroll{flex:1;overflow:auto}
#src-scroll::-webkit-scrollbar{width:6px;height:6px}
#src-scroll::-webkit-scrollbar-track{background:transparent}
#src-scroll::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
#src-scroll::-webkit-scrollbar-corner{background:transparent}
#src-code{font-family:var(--mono);font-size:12px;line-height:1.72;
          padding:10px 0;min-width:max-content}
.sline{display:flex;align-items:baseline;padding-right:24px}
.sline:hover{background:rgba(255,255,255,.025)}
.sline.loopln{cursor:pointer}
.sline.loopln:hover{background:rgba(255,255,255,.045)}
.sline.hl{background:rgba(83,155,245,.1)!important;
          outline:1px solid rgba(83,155,245,.25)}
.gutter{display:flex;align-items:center;width:52px;
        flex-shrink:0;padding-right:8px;gap:2px}
.ln{width:34px;text-align:right;color:var(--muted);font-size:11px;
    user-select:none;flex-shrink:0}
.gdot{width:5px;height:5px;border-radius:50%;flex-shrink:0;margin-left:3px}
.stext{padding-left:6px;white-space:pre}
.sbadge{margin-left:14px;font-size:10px;font-weight:700;padding:1px 8px;
        border-radius:10px;display:inline-flex;align-items:center;gap:3px;
        border:1px solid transparent;white-space:nowrap;flex-shrink:0}

/* fortran syntax */
.fkw{color:#6cb6ff}
.fcmt{color:#545d68;font-style:italic}
.fnum{color:#f69d50}
.fempty{padding:32px;color:var(--muted);font-size:12px;text-align:center}

/* ── details panel ── */
#details{overflow-y:auto;overflow-x:hidden;border-left:1px solid var(--border);
         background:var(--surf)}
#details::-webkit-scrollbar{width:3px}
#details::-webkit-scrollbar-thumb{background:var(--border)}
.dhead{padding:9px 12px;border-bottom:1px solid var(--border-l);
       font-size:10px;font-weight:700;color:var(--dim);letter-spacing:.08em;
       text-transform:uppercase;position:sticky;top:0;
       background:var(--surf);z-index:1;
       display:flex;align-items:center;justify-content:space-between}
.dbadge{background:var(--surf2);border-radius:8px;padding:1px 7px;
        font-size:9px;color:var(--muted);font-weight:400;letter-spacing:0}
.lcard{padding:10px 12px;border-bottom:1px solid var(--border-l);
       cursor:pointer;transition:background .1s;
       border-left:3px solid var(--border)}
.lcard:hover{background:var(--surf2)}
.lcard.sel{background:rgba(83,155,245,.07);border-left-color:var(--accent)}
.lcard.cSAFE{border-left-color:var(--safe)}
.lcard.cREDUCTION{border-left-color:var(--redu)}
.lcard.cUNSAFE{border-left-color:var(--unsafe)}
.lcard-top{display:flex;align-items:center;gap:6px;margin-bottom:5px;
           flex-wrap:wrap}
.lstatus{font-family:var(--mono);font-size:9px;font-weight:700;
         padding:2px 7px;border-radius:4px;letter-spacing:.06em;
         border:1px solid transparent}
.lstatus.SAFE{color:var(--safe);background:var(--safe-bg);border-color:var(--safe-bd)}
.lstatus.REDUCTION{color:var(--redu);background:var(--redu-bg);border-color:var(--redu-bd)}
.lstatus.UNSAFE{color:var(--unsafe);background:var(--unsafe-bg);border-color:var(--unsafe-bd)}
.lstatus.UNKNOWN{color:var(--dim);background:var(--surf2);border-color:var(--border)}
.lnum{font-family:var(--mono);font-size:11px;font-weight:600;color:var(--text)}
.lloc{font-family:var(--mono);font-size:9px;color:var(--muted);
      margin-left:auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
      max-width:120px}
.ldepth{font-family:var(--mono);font-size:9px;color:var(--muted);
        background:var(--surf2);border:1px solid var(--border);
        padding:1px 5px;border-radius:3px}
.lhint{font-family:var(--mono);font-size:10px;
       background:rgba(83,155,245,.08);border:1px solid rgba(83,155,245,.2);
       border-radius:4px;padding:5px 8px;margin-bottom:5px;color:#96d0ff;
       word-break:break-all}
.lreason{font-size:11px;color:var(--dim);line-height:1.55;margin-bottom:5px}
.lbounds{font-family:var(--mono);font-size:10px;color:var(--muted);
         margin-bottom:5px}
.lbounds-lbl{font-size:9px;text-transform:uppercase;letter-spacing:.06em;
             color:var(--muted);margin-right:4px}
.lacc-lbl{font-size:9px;text-transform:uppercase;letter-spacing:.06em;
          color:var(--muted);margin-bottom:3px;margin-top:4px}
.arow{display:flex;align-items:center;gap:5px;
      font-family:var(--mono);font-size:10px;color:var(--dim);padding:2px 0}
.abadge{font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;
        flex-shrink:0;letter-spacing:.04em}
.abadge.R {color:var(--safe);  background:rgba(87,171,90,.18)}
.abadge.W {color:var(--unsafe);background:rgba(229,83,75,.18)}
.abadge.RW{color:var(--redu);  background:rgba(218,170,63,.18)}
.dempty{padding:32px 16px;text-align:center;color:var(--muted);font-size:11px}
.dempty .arr{font-size:22px;display:block;margin-bottom:8px;opacity:.3}
.dnoloop{padding:20px 14px;color:var(--muted);font-style:italic;
         font-size:11px;text-align:center}

/* ── statusbar ── */
#statusbar{display:flex;align-items:center;gap:10px;padding:0 14px;
           background:var(--accent);color:rgba(255,255,255,.9);
           font-family:var(--mono);font-size:10px;user-select:none}
.sbi{display:flex;align-items:center;gap:4px}
.sbsep{opacity:.35}
.sbkeys{margin-left:auto;opacity:.7}
.sbkeys kbd{background:rgba(255,255,255,.2);border-radius:2px;padding:0 3px}

/* ── help modal ── */
#helpmod{display:none;position:fixed;inset:0;background:rgba(0,0,0,.65);
         z-index:100;align-items:center;justify-content:center}
#helpmod.open{display:flex}
.hbox{background:var(--surf);border:1px solid var(--border);
      border-radius:10px;padding:22px 26px;width:370px;max-width:95vw}
.htitle{font-weight:700;font-size:13px;margin-bottom:14px}
.hrow{display:flex;justify-content:space-between;align-items:center;
      padding:5px 0;border-bottom:1px solid var(--border-l);font-size:11px}
.hrow:last-of-type{border-bottom:none}
.hrow kbd{background:var(--surf2);border:1px solid var(--border);
          border-radius:3px;padding:1px 6px;font-family:var(--mono);font-size:10px}
.hrow span{color:var(--dim)}
.hclose{margin-top:14px;width:100%;padding:7px;
        background:var(--surf2);border:1px solid var(--border);
        border-radius:6px;color:var(--text);cursor:pointer;font-size:11px}
.hclose:hover{background:var(--border)}
</style>
</head>
<body>

<script>
const DATA  = %%DATA%%;
const STATS = %%STATS%%;
</script>

<div id="app">

  <!-- titlebar -->
  <div id="titlebar">
    <div class="tbar-logo">&#9889; FLANG&thinsp;PA</div>
    <div class="tbar-sep"></div>
    <div id="search-wrap">
      <span class="search-ico">&#8981;</span>
      <input id="search" type="text" placeholder="Search files, loops, reasons&hellip;"
             autocomplete="off" spellcheck="false">
    </div>
    <div class="filter-grp">
      <button class="fbtn fa" data-f="ALL">ALL</button>
      <button class="fbtn"    data-f="SAFE">&#10003;&thinsp;SAFE</button>
      <button class="fbtn"    data-f="REDUCTION">&#8635;&thinsp;REDU</button>
      <button class="fbtn"    data-f="UNSAFE">&#10007;&thinsp;UNSAFE</button>
    </div>
    <div class="stat-row" id="stat-row"></div>
    <div class="tbar-sep"></div>
    <div class="kb-tip"><kbd>?</kbd> help</div>
  </div>

  <!-- three-panel workspace -->
  <div id="workspace">
    <div id="sidebar"></div>
    <div id="source-panel">
      <div id="src-tabbar"></div>
      <div id="src-scroll"><div id="src-code"></div></div>
    </div>
    <div id="details"></div>
  </div>

  <!-- statusbar -->
  <div id="statusbar"></div>

</div>

<!-- help modal -->
<div id="helpmod">
  <div class="hbox">
    <div class="htitle">Keyboard Shortcuts</div>
    <div class="hrow"><kbd>j</kbd>       <span>Next loop</span></div>
    <div class="hrow"><kbd>k</kbd>       <span>Previous loop</span></div>
    <div class="hrow"><kbd>/</kbd>       <span>Focus search</span></div>
    <div class="hrow"><kbd>f</kbd>       <span>Cycle status filter</span></div>
    <div class="hrow"><kbd>1</kbd>&ndash;<kbd>9</kbd> <span>Jump to file by position</span></div>
    <div class="hrow"><kbd>Esc</kbd>     <span>Clear search / close</span></div>
    <div class="hrow"><kbd>?</kbd>       <span>Toggle this panel</span></div>
    <button class="hclose" id="hclose">Close</button>
  </div>
</div>

<script>
'use strict';

// ── constants ─────────────────────────────────────────────────────────────────
const SC = {
  SAFE:      {fg:'#57ab5a', bg:'rgba(87,171,90,.13)',  bd:'rgba(87,171,90,.4)',  sym:'&#10003;'},
  REDUCTION: {fg:'#daaa3f', bg:'rgba(218,170,63,.13)', bd:'rgba(218,170,63,.4)', sym:'&#8635;'},
  UNSAFE:    {fg:'#e5534b', bg:'rgba(229,83,75,.13)',  bd:'rgba(229,83,75,.4)',  sym:'&#10007;'},
  UNKNOWN:   {fg:'#768390', bg:'rgba(118,131,144,.12)',bd:'rgba(118,131,144,.3)',sym:'?'},
};
const KWRE = /\\b(subroutine|function|program|module|use|implicit|none|integer|real|logical|character|external|parameter|do|if|then|else|end|return|call|continue|intent|allocate|deallocate|print|write|read)\\b/gi;

// ── helpers ───────────────────────────────────────────────────────────────────
function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') }

function fthl(raw){
  const ci = raw.indexOf('!');
  const code = ci>=0 ? raw.slice(0,ci) : raw;
  const cmt  = ci>=0 ? raw.slice(ci)  : '';
  let h = esc(code).replace(KWRE, m => `<span class="fkw">${m}</span>`);
  if(cmt) h += `<span class="fcmt">${esc(cmt)}</span>`;
  return h;
}

function q(id){ return document.getElementById(id) }

// ── state ─────────────────────────────────────────────────────────────────────
const App = {
  files: DATA,
  stats: STATS,
  activeIdx: 0,
  activeKey: null,   // "fileIdx:loopNum"
  filter: 'ALL',
  search: '',

  // filtered file list preserving original indices
  ff(){
    const sq = this.search.toLowerCase();
    return this.files
      .map((f,i) => ({...f, _i:i}))
      .filter(f => {
        if(sq && !f.name.toLowerCase().includes(sq) &&
           !f.loops.some(l => l.reason.toLowerCase().includes(sq) || l.hint.toLowerCase().includes(sq)))
          return false;
        if(this.filter !== 'ALL' && !f.loops.some(l => l.status === this.filter))
          return false;
        return true;
      });
  },

  vloops(idx){
    const f = this.files[idx];
    if(!f) return [];
    return this.filter==='ALL' ? f.loops : f.loops.filter(l=>l.status===this.filter);
  },

  // ── actions ──────────────────────────────────────────────────────────────────
  selectFile(idx){
    this.activeIdx = idx;
    this.activeKey = null;
    this.rSidebar(); this.rTabs(); this.rSource(); this.rDetails(); this.rStatus();
  },

  selectLoop(fidx, lnum){
    const needRerender = fidx !== this.activeIdx;
    this.activeIdx = fidx;
    this.activeKey = `${fidx}:${lnum}`;
    if(needRerender){ this.rSidebar(); this.rTabs(); this.rSource(); }
    this.rDetails();
    this.scrollToLoop(fidx, lnum);
    this.rStatus();
  },

  nextLoop(){
    const ls = this.vloops(this.activeIdx);
    if(!ls.length) return;
    if(!this.activeKey){ this.selectLoop(this.activeIdx, ls[0].num); return; }
    const cur = parseInt(this.activeKey.split(':')[1]);
    const i   = ls.findIndex(l=>l.num===cur);
    this.selectLoop(this.activeIdx, ls[(i+1)%ls.length].num);
  },

  prevLoop(){
    const ls = this.vloops(this.activeIdx);
    if(!ls.length) return;
    if(!this.activeKey){ this.selectLoop(this.activeIdx, ls[ls.length-1].num); return; }
    const cur = parseInt(this.activeKey.split(':')[1]);
    const i   = ls.findIndex(l=>l.num===cur);
    this.selectLoop(this.activeIdx, ls[(i-1+ls.length)%ls.length].num);
  },

  setFilter(f){
    this.filter = f;
    this.activeKey = null;
    // re-validate activeIdx
    const vis = this.ff();
    if(!vis.find(x=>x._i===this.activeIdx) && vis.length) this.activeIdx = vis[0]._i;
    this.rAll();
  },

  // ── render ────────────────────────────────────────────────────────────────────
  rAll(){
    this.rTbar(); this.rSidebar(); this.rTabs();
    this.rSource(); this.rDetails(); this.rStatus();
  },

  rTbar(){
    document.querySelectorAll('.fbtn').forEach(b=>{
      const f = b.dataset.f;
      b.className = 'fbtn ' + (f===this.filter ? (f==='ALL'?'fa':f==='SAFE'?'fs':f==='REDUCTION'?'fr':'fu') : '');
    });
    const s = this.stats;
    q('stat-row').innerHTML =
      `<div class="spill"><div class="sdot" style="background:#57ab5a"></div>${s.safe}</div>` +
      `<div class="spill"><div class="sdot" style="background:#daaa3f"></div>${s.reduction}</div>` +
      `<div class="spill"><div class="sdot" style="background:#e5534b"></div>${s.unsafe}</div>`;
  },

  rSidebar(){
    const vis = this.ff();
    if(!vis.length){
      q('sidebar').innerHTML = '<div style="padding:24px 12px;text-align:center;color:var(--muted);font-size:11px">No files match</div>';
      return;
    }
    // group by parent dir
    const groups = {};
    vis.forEach(f=>{
      const parts = f.path.replace(/\\\\/g,'/').split('/');
      const dir = parts.length>1 ? parts[parts.length-2] : '.';
      (groups[dir]=groups[dir]||[]).push(f);
    });
    let html='';
    Object.entries(groups).forEach(([dir,files])=>{
      html += `<div>
        <div class="grp-head" onclick="App.toggleGrp(this)">
          <span class="chev open">&#9654;</span>
          <span>${esc(dir)}</span>
          <span class="gcnt">${files.length}</span>
        </div>
        <div class="grp-body">`;
      files.forEach(f=>{
        const active = f._i===this.activeIdx;
        let dot='#768390';
        if(f.nUnsafe>0) dot=SC.UNSAFE.fg;
        else if(f.nReduction>0) dot=SC.REDU;
        else if(f.nSafe>0) dot=SC.SAFE.fg;
        // pick dominant dot correctly
        if(f.nReduction>0&&f.nUnsafe===0) dot=SC.REDUCTION.fg;
        const cntParts=[
          f.nSafe>0      ? `<span style="color:#57ab5a">${f.nSafe}&#10003;</span>`:'',
          f.nReduction>0 ? `<span style="color:#daaa3f">${f.nReduction}&#8635;</span>`:'',
          f.nUnsafe>0    ? `<span style="color:#e5534b">${f.nUnsafe}&#10007;</span>`:'',
        ].filter(Boolean);
        html += `<div class="fitem${active?' active':''}" onclick="App.selectFile(${f._i})" title="${esc(f.path)}">
          <div class="fdot" style="background:${dot}"></div>
          <span class="fname-txt">${esc(f.name)}</span>
          <span class="fcnt">${cntParts.join('')||'&mdash;'}</span>
        </div>`;
      });
      html += '</div></div>';
    });
    q('sidebar').innerHTML = html;
  },

  toggleGrp(header){
    const body   = header.nextElementSibling;
    const chev   = header.querySelector('.chev');
    const isOpen = chev.classList.contains('open');
    body.style.display = isOpen ? 'none' : '';
    chev.classList.toggle('open', !isOpen);
  },

  rTabs(){
    const f = this.files[this.activeIdx];
    q('src-tabbar').innerHTML = f ? `<div class="stab active">${esc(f.name)}</div>` : '';
  },

  rSource(){
    const f = this.files[this.activeIdx];
    if(!f){ q('src-code').innerHTML='<div class="fempty">Select a file from the sidebar</div>'; return; }
    const lineMap={};
    f.loops.forEach(lp=>{ if(lp.sourceLine) lineMap[lp.sourceLine]=lp; });
    const lines = f.source.split('\\n');
    let html='';
    lines.forEach((raw,i)=>{
      const ln=i+1, lp=lineMap[ln];
      const isLoop=!!lp;
      const selKey = lp ? `${this.activeIdx}:${lp.num}` : null;
      const isHl   = selKey===this.activeKey;
      let gdot='', badge='';
      if(lp){
        const sc=SC[lp.status]||SC.UNKNOWN;
        gdot =`<div class="gdot" style="background:${sc.fg}"></div>`;
        badge=`<span class="sbadge" style="color:${sc.fg};background:${sc.bg};border-color:${sc.bd}">${sc.sym} ${lp.status}</span>`;
      } else {
        gdot='<div class="gdot" style="opacity:0"></div>';
      }
      const idAttr   = lp  ? ` id="sl-${lp.num}"` : '';
      const onclick  = lp  ? ` onclick="App.selectLoop(${this.activeIdx},${lp.num})"` : '';
      html+=`<div class="sline${isLoop?' loopln':''}${isHl?' hl':''}"${idAttr}${onclick}>` +
            `<div class="gutter"><span class="ln">${ln}</span>${gdot}</div>` +
            `<span class="stext">${fthl(raw)}</span>${badge}</div>`;
    });
    q('src-code').innerHTML = html;
  },

  rDetails(){
    const f = this.files[this.activeIdx];
    if(!f){
      q('details').innerHTML='<div class="dempty"><span class="arr">&#8592;</span>Select a file</div>';
      return;
    }
    const ls = this.vloops(this.activeIdx);
    let html=`<div class="dhead">Loop Inspector<span class="dbadge">${ls.length} loop${ls.length!==1?'s':''}</span></div>`;
    if(!ls.length){
      html+='<div class="dnoloop">No loops match filter</div>';
    } else {
      ls.forEach(lp=>{
        const key=`${this.activeIdx}:${lp.num}`;
        const sel=this.activeKey===key;
        const sc=SC[lp.status]||SC.UNKNOWN;
        const depth= lp.depth>0 ? `<span class="ldepth">depth&thinsp;${lp.depth}</span>`:'';
        const hint = lp.hint   ? `<div class="lhint">${esc(lp.hint)}</div>`:'';
        const rsn  = lp.reason ? `<div class="lreason">${esc(lp.reason)}</div>`:'';
        const bnd  = lp.bounds ? `<div class="lbounds"><span class="lbounds-lbl">bounds</span>${esc(lp.bounds)}</div>`:'';
        let accs='';
        if(lp.accesses.length){
          const rows=lp.accesses.map(a=>{
            const m=a.match(/^\\[(R|W|RW)\\]\\s*(.+)/);
            if(!m) return `<div class="arow"><span class="abadge RW">?</span>${esc(a)}</div>`;
            return `<div class="arow"><span class="abadge ${m[1]}">${m[1]}</span>${esc(m[2])}</div>`;
          }).join('');
          accs=`<div class="lacc-lbl">Memory</div>${rows}`;
        }
        html+=`<div class="lcard c${lp.status}${sel?' sel':''}" id="lc-${lp.num}"
                    onclick="App.selectLoop(${this.activeIdx},${lp.num})">
          <div class="lcard-top">
            <span class="lstatus ${lp.status}">${sc.sym} ${lp.status}</span>
            <span class="lnum">Loop #${lp.num}</span>${depth}
            <span class="lloc" title="${esc(lp.loc)}">${esc(lp.loc)}</span>
          </div>
          ${hint}${bnd}${rsn}${accs}
        </div>`;
      });
    }
    q('details').innerHTML=html;
  },

  rStatus(){
    const f = this.files[this.activeIdx];
    const nm = f ? esc(f.name) : '&mdash;';
    const s  = this.stats;
    q('statusbar').innerHTML=
      `<span class="sbi">${s.files} files</span><span class="sbsep">|</span>` +
      `<span class="sbi">${s.loops} loops</span><span class="sbsep">|</span>` +
      `<span class="sbi" style="color:#a8f5aa">&#10003; ${s.safe}</span><span class="sbsep">|</span>` +
      `<span class="sbi" style="color:#f5dfa8">&#8635; ${s.reduction}</span><span class="sbsep">|</span>` +
      `<span class="sbi" style="color:#f5a8a8">&#10007; ${s.unsafe}</span><span class="sbsep">|</span>` +
      `<span class="sbi">${nm}</span>` +
      `<span class="sbkeys"><kbd>j</kbd>/<kbd>k</kbd> loops &nbsp;<kbd>/</kbd> search &nbsp;<kbd>?</kbd> help</span>`;
  },

  scrollToLoop(fidx, lnum){
    const f=this.files[fidx]; if(!f) return;
    const lp=f.loops.find(l=>l.num===lnum); if(!lp||!lp.sourceLine) return;
    setTimeout(()=>{
      const sl=document.getElementById(`sl-${lnum}`);
      if(sl) sl.scrollIntoView({behavior:'smooth',block:'center'});
      // re-apply highlight
      document.querySelectorAll('.sline.hl').forEach(e=>e.classList.remove('hl'));
      if(sl) sl.classList.add('hl');
      const card=document.getElementById(`lc-${lnum}`);
      if(card) card.scrollIntoView({behavior:'smooth',block:'nearest'});
    },0);
  },

  // ── keyboard + events ────────────────────────────────────────────────────────
  bind(){
    document.addEventListener('keydown',e=>{
      const inp=document.activeElement.tagName==='INPUT';
      if(e.key==='Escape'){
        if(inp){document.activeElement.blur();this.search='';this.rSidebar();}
        q('helpmod').classList.remove('open'); return;
      }
      if(inp) return;
      if(e.key==='j'){e.preventDefault();this.nextLoop();}
      if(e.key==='k'){e.preventDefault();this.prevLoop();}
      if(e.key==='/'){e.preventDefault();q('search').focus();}
      if(e.key==='f'){e.preventDefault();
        const order=['ALL','SAFE','REDUCTION','UNSAFE'];
        this.setFilter(order[(order.indexOf(this.filter)+1)%order.length]);
      }
      if(e.key==='?') q('helpmod').classList.toggle('open');
      if(e.key>='1'&&e.key<='9'){
        const fi=this.ff()[parseInt(e.key)-1]; if(fi) this.selectFile(fi._i);
      }
    });
    q('search').addEventListener('input',e=>{this.search=e.target.value;this.rSidebar();});
    document.querySelectorAll('.fbtn').forEach(b=>
      b.addEventListener('click',()=>this.setFilter(b.dataset.f)));
    q('hclose').addEventListener('click',()=>q('helpmod').classList.remove('open'));
    q('helpmod').addEventListener('click',e=>{if(e.target===e.currentTarget)e.currentTarget.classList.remove('open');});
  },

  init(){ this.rAll(); this.bind(); }
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
    ap.add_argument("files", nargs="*",
                    help=".f90 files (default: tests/fortran + tests/comprehensive)")
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
        try:
            source = open(f90).read()
        except OSError as e:
            print(f"  cannot read: {e}", file=sys.stderr); continue
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
