"""
DCS Contract Scanner — local background server.
Auto-started silently at Windows login via install-autostart.ps1.
Scan UI: http://localhost:5000
"""

import socket
import sys
import json
import csv
import re
import shutil
import subprocess
import time
import logging
from datetime import datetime
from pathlib import Path
from flask import Flask, Response, request
from werkzeug.utils import secure_filename

import sys as _sys
_ANON_DIR = Path(__file__).resolve().parent / "anonymization"
if str(_ANON_DIR) not in _sys.path:
    _sys.path.insert(0, str(_ANON_DIR))
from anonymize import (
    detect_file, apply_file, get_mapping,
    _load_decisions_library, _save_decisions_library, _library_key,
    review_path_for, quarantine_path_for, audit_path_for, append_override_entry,
    REVIEWS_DIR, QUARANTINE_DIR, AUDITS_DIR,
)

# C3: module logger (anonymize.py already called logging.basicConfig at import).
log = logging.getLogger("anonymizer-server")

# ── Exit immediately if already running on port 5000 ────────────────────────
_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
_s.settimeout(1)
if _s.connect_ex(("127.0.0.1", 5000)) == 0:
    _s.close()
    sys.exit(0)
_s.close()

# ── Paths ────────────────────────────────────────────────────────────────────
TOOLS       = Path(__file__).resolve().parent
SHAREPOINT  = TOOLS.parent
SCAN_SCRIPT = TOOLS / "scan-contract.py"
SYNC_SCRIPT = TOOLS / "sync-sor.py"
CSV_PATH    = TOOLS / "contract-catalog.csv"

_SP_PREFIX  = re.compile(r'^[A-Za-z]:[/\\].*?Contract Management - SharePoint[/\\]', re.IGNORECASE)
_LOC_PREFIX = re.compile(r'^0[1-3] (?:Active|Unsigned|Archived) Contracts[/\\]', re.IGNORECASE)

def _norm_path(p):
    p = p.strip().strip('"\'').replace('\\', '/')
    p = _SP_PREFIX.sub('', p)
    p = _LOC_PREFIX.sub('', p)
    return p

app = Flask(__name__)

@app.after_request
def _cors(r):
    r.headers["Access-Control-Allow-Origin"]  = "*"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    r.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return r

@app.route("/api/status", methods=["GET"])
def status():
    try:
        with open(MAPPING_PATH, encoding="utf-8") as fh:
            m = json.load(fh)
        entry_count = len(m.get("entries", {}))
    except Exception:
        entry_count = -1
    return json.dumps({
        "ok": True,
        "version": "1.0",
        "mapping_entries": entry_count,
    }), 200, {"Content-Type": "application/json"}

# ── Scan UI ──────────────────────────────────────────────────────────────────
SCAN_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DCS Contract Scanner</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f3f4f6;color:#111827;padding:24px 16px}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:24px;max-width:980px;margin:0 auto 20px}
h1{font-size:20px;font-weight:700;margin-bottom:4px}
h2{font-size:15px;font-weight:600;margin-bottom:12px}
.sub{font-size:13px;color:#6b7280;margin-bottom:20px}
label{font-size:13px;color:#374151;display:block;margin-bottom:4px;font-weight:500}
.hint{font-size:12px;color:#9ca3af;font-weight:400}
.modes{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:16px}
.modes label{display:flex;align-items:center;gap:7px;font-weight:400;cursor:pointer}
textarea,input[type=text],input[type=search],select{
  width:100%;background:#f9fafb;border:1px solid #d1d5db;border-radius:8px;
  padding:9px 12px;font-size:13px;color:#111827;font-family:inherit;outline:none;transition:border-color .15s}
textarea{min-height:70px;resize:vertical;font-family:monospace;font-size:12px;line-height:1.5}
textarea:focus,input:focus,select:focus{border-color:#6366f1}
.row{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:14px}
.chk-label{display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;font-weight:400}
button.primary{background:#6366f1;color:#fff;border:none;border-radius:8px;padding:9px 20px;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap}
button.primary:hover{background:#4f46e5}
button.primary:disabled{background:#a5b4fc;cursor:not-allowed}
button.ghost{background:transparent;border:1px solid #d1d5db;color:#374151;border-radius:8px;padding:8px 14px;font-size:13px;cursor:pointer;white-space:nowrap}
button.ghost:hover{background:#f3f4f6}
#scan-status{font-size:12px;color:#9ca3af}
/* Catalog */
.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center}
.toolbar input[type=search]{flex:1;min-width:180px}
.toolbar select{flex:0 0 auto;width:auto;min-width:150px}
.tbl-wrap{max-height:400px;overflow-y:auto;border:1px solid #e5e7eb;border-radius:8px}
table{width:100%;border-collapse:collapse;font-size:12px}
thead th{position:sticky;top:0;background:#f9fafb;padding:8px 10px;text-align:left;
         font-size:11px;font-weight:600;color:#6b7280;text-transform:uppercase;
         border-bottom:1px solid #e5e7eb;white-space:nowrap}
tbody tr{border-bottom:1px solid #f3f4f6;cursor:pointer;transition:background .1s}
tbody tr:hover{background:#f5f3ff}
tbody tr.sel{background:#ede9fe}
td{padding:7px 10px;vertical-align:middle}
.td-vendor{font-weight:500;color:#111827;max-width:160px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.td-file{max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-family:monospace;font-size:11px;color:#6366f1}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:500}
.b-signed{background:#dcfce7;color:#166534}
.b-unsigned{background:#fee2e2;color:#991b1b}
.b-blank{background:#f3f4f6;color:#6b7280}
.cat-meta{display:flex;align-items:center;gap:8px;margin-bottom:12px;flex-wrap:wrap}
.cat-meta h2{margin:0}
.cat-count{font-size:12px;color:#9ca3af;margin-right:auto}
/* Log */
.log-card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:24px;max-width:980px;margin:0 auto;display:none}
#log{background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px 14px;
     font-family:monospace;font-size:12px;line-height:1.6;max-height:480px;overflow-y:auto;white-space:pre-wrap}
</style>
</head>
<body>

<!-- ── Scan form ── -->
<div class="card">
  <h1>DCS Contract Scanner</h1>
  <p class="sub">Select contracts from the catalog below, then hit Scan.</p>

  <div class="modes">
    <label><input type="radio" name="mode" value="files" checked onchange="modeChange()"> Files</label>
    <label><input type="radio" name="mode" value="vendor" onchange="modeChange()"> By Vendor</label>
    <label><input type="radio" name="mode" value="location" onchange="modeChange()"> By Location</label>
    <label><input type="radio" name="mode" value="type" onchange="modeChange()"> By Type</label>
    <label><input type="radio" name="mode" value="all" onchange="modeChange()"> All Contracts</label>
  </div>

  <div id="in-files">
    <label>Selected files <span class="hint">— click rows in the catalog below, or paste a path directly</span></label>
    <textarea id="files-val" onpaste="setTimeout(()=>this.value=normPaths(this.value),0)" placeholder="Click rows in the catalog below to add files here…"></textarea>
  </div>
  <div id="in-vendor" style="display:none">
    <label>Vendor name <span class="hint">(partial match OK)</span></label>
    <input type="text" id="vendor-val" list="vendor-list" placeholder="Disney, ACI Licenses…">
    <datalist id="vendor-list"></datalist>
  </div>
  <div id="in-location" style="display:none">
    <label>Contract folder</label>
    <select id="location-val">
      <option>01 Active Contracts</option>
      <option>02 Unsigned Contracts</option>
      <option>03 Archived Contracts</option>
    </select>
  </div>
  <div id="in-type" style="display:none">
    <label>Document type <span class="hint">(partial match OK)</span></label>
    <select id="type-val"><option value="">— select —</option></select>
  </div>
  <div id="in-all" style="display:none">
    <p style="font-size:13px;color:#d97706;background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:10px 14px">
      ⚠️ Scans all contracts — may take several minutes.</p>
  </div>

  <div class="row">
    <label class="chk-label"><input type="checkbox" id="dry-run"> Dry run</label>
    <button class="primary" id="scan-btn" onclick="doScan()">🔍 Scan</button>
    <button class="ghost" id="clear-btn" onclick="clearLog()" style="display:none">Clear log</button>
    <span id="scan-status"></span>
  </div>
</div>

<!-- ── Catalog browser ── -->
<div class="card">
  <div class="cat-meta">
    <h2>Contract Catalog</h2>
    <span class="cat-count" id="cat-count">Loading…</span>
    <button class="primary" id="sel-btn" onclick="scanSelected()" style="display:none">
      🔍 Scan Selected (<span id="sel-count">0</span>)
    </button>
    <button class="ghost" onclick="clearSel()">Clear selection</button>
  </div>
  <div class="toolbar">
    <input type="search" id="cat-q" placeholder="Search vendor, filename, type…" oninput="renderCatalog()">
    <select id="cat-loc" onchange="renderCatalog()">
      <option value="">All Locations</option>
      <option>01 Active Contracts</option>
      <option>02 Unsigned Contracts</option>
      <option>03 Archived Contracts</option>
    </select>
    <select id="cat-type" onchange="renderCatalog()">
      <option value="">All Types</option>
    </select>
    <select id="cat-status" onchange="renderCatalog()">
      <option value="">All Statuses</option>
      <option>Signed</option>
      <option>Unsigned</option>
    </select>
  </div>
  <div class="tbl-wrap">
    <table>
      <thead>
        <tr>
          <th style="width:32px"><input type="checkbox" id="sel-all" title="Select all visible" onchange="toggleAll(this.checked)"></th>
          <th>Vendor</th>
          <th>Filename</th>
          <th>Type</th>
          <th>Status</th>
          <th>Effective</th>
          <th>Expires</th>
        </tr>
      </thead>
      <tbody id="cat-body"></tbody>
    </table>
  </div>
  <p id="cat-empty" style="text-align:center;padding:24px;color:#9ca3af;font-size:13px;display:none">No contracts match.</p>
</div>

<!-- ── Output log ── -->
<div class="log-card" id="log-card">
  <h2>Output</h2>
  <div id="log"></div>
</div>

<script>
// ── Path normalizer (handles Windows full paths) ─────────────────────────
function normPaths(raw){
  const SP=/^[A-Za-z]:[/\\].*?Contract Management - SharePoint[/\\]/i;
  const LOC=/^0[1-3] (?:Active|Unsigned|Archived) Contracts[/\\]/i;
  return raw.split(/\r?\n/).map(s=>{
    s=s.trim().replace(/^["']+|["']+$/g,'');
    s=s.replace(SP,'').replace(LOC,'').replace(/\\/g,'/');
    return s;
  }).filter(Boolean).join('\n');
}

// ── Mode toggle ──────────────────────────────────────────────────────────
function modeChange(){
  const m=document.querySelector('input[name=mode]:checked').value;
  ['files','vendor','location','type','all'].forEach(k=>
    document.getElementById('in-'+k).style.display=k===m?'block':'none');
}

// ── Pre-fill from ?file= param (passed by SharePoint dashboard) ──────────
(function(){
  const p=new URLSearchParams(window.location.search).get('file');
  if(p) document.getElementById('files-val').value=normPaths(p);
})();

// ── Load vendor autocomplete ─────────────────────────────────────────────
fetch('/api/vendors').then(r=>r.json()).then(vs=>{
  const dl=document.getElementById('vendor-list');
  vs.forEach(v=>{const o=document.createElement('option');o.value=v;dl.appendChild(o);});
}).catch(()=>{});

// ── Catalog ──────────────────────────────────────────────────────────────
let CATALOG=[], SEL=new Set();

function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

fetch('/api/contracts').then(r=>r.json()).then(data=>{
  CATALOG=data;
  renderCatalog();
  // Populate type dropdowns from unique DocType values
  const types=[...new Set(data.map(r=>r.doctype).filter(Boolean))].sort();
  [document.getElementById('type-val'), document.getElementById('cat-type')].forEach(sel=>{
    types.forEach(t=>{const o=document.createElement('option');o.value=t;o.textContent=t;sel.appendChild(o);});
  });
}).catch(()=>{
  document.getElementById('cat-count').textContent='Could not load catalog';
});

function renderCatalog(){
  const q=(document.getElementById('cat-q').value||'').toLowerCase();
  const loc=document.getElementById('cat-loc').value;
  const type=document.getElementById('cat-type').value;
  const status=document.getElementById('cat-status').value;
  const rows=CATALOG.filter(r=>{
    if(loc&&r.location!==loc) return false;
    if(type&&r.doctype!==type) return false;
    if(status&&r.signed!==status) return false;
    if(q&&!((r.vendor||'').toLowerCase().includes(q)||(r.filename||'').toLowerCase().includes(q)||(r.doctype||'').toLowerCase().includes(q))) return false;
    return true;
  });
  document.getElementById('cat-count').textContent=rows.length+' contracts';
  document.getElementById('cat-empty').style.display=rows.length?'none':'block';
  const tbody=document.getElementById('cat-body');
  tbody.innerHTML='';
  rows.forEach(r=>{
    const isSel=SEL.has(r.filepath);
    const badgeCls=r.signed==='Signed'?'b-signed':r.signed==='Unsigned'?'b-unsigned':'b-blank';
    const tr=document.createElement('tr');
    if(isSel) tr.classList.add('sel');
    tr.dataset.fp=r.filepath;
    tr.innerHTML=
      '<td><input type="checkbox"'+(isSel?' checked':'')+'></td>'+
      '<td class="td-vendor" title="'+esc(r.vendor)+'">'+esc(r.vendor)+'</td>'+
      '<td class="td-file" title="'+esc(r.filename)+'">'+esc(r.filename)+'</td>'+
      '<td>'+esc(r.doctype||'')+'</td>'+
      '<td><span class="badge '+badgeCls+'">'+esc(r.signed||'—')+'</span></td>'+
      '<td style="white-space:nowrap">'+esc(r.effective||'')+'</td>'+
      '<td style="white-space:nowrap">'+esc(r.expiration||'')+'</td>';
    tbody.appendChild(tr);
  });
  updateSelBtn();
}

// Event delegation — one listener for the whole tbody
document.getElementById('cat-body').addEventListener('click',function(e){
  if(e.target.type==='checkbox') return;
  const tr=e.target.closest('tr');
  if(tr) toggleRow(tr);
});
document.getElementById('cat-body').addEventListener('change',function(e){
  if(e.target.type!=='checkbox') return;
  const tr=e.target.closest('tr');
  if(tr) toggleRow(tr,e.target.checked);
});

function toggleRow(tr,force){
  const fp=tr.dataset.fp;
  const on=force!==undefined?force:!SEL.has(fp);
  if(on) SEL.add(fp); else SEL.delete(fp);
  tr.classList.toggle('sel',on);
  const cb=tr.querySelector('input[type=checkbox]');
  if(cb) cb.checked=on;
  syncFilesTextarea();
  updateSelBtn();
}

function toggleAll(on){
  document.querySelectorAll('#cat-body tr').forEach(tr=>{
    const fp=tr.dataset.fp;
    if(on) SEL.add(fp); else SEL.delete(fp);
    tr.classList.toggle('sel',on);
    const cb=tr.querySelector('input[type=checkbox]');
    if(cb) cb.checked=on;
  });
  syncFilesTextarea();
  updateSelBtn();
}

function clearSel(){
  SEL.clear();
  document.querySelectorAll('#cat-body tr').forEach(tr=>{
    tr.classList.remove('sel');
    const cb=tr.querySelector('input[type=checkbox]');
    if(cb) cb.checked=false;
  });
  document.getElementById('sel-all').checked=false;
  syncFilesTextarea();
  updateSelBtn();
}

function syncFilesTextarea(){
  // Keep Files mode textarea in sync with selection
  const mode=document.querySelector('input[name=mode]:checked').value;
  if(mode==='files') document.getElementById('files-val').value=[...SEL].join('\n');
}

function updateSelBtn(){
  document.getElementById('sel-count').textContent=SEL.size;
  document.getElementById('sel-btn').style.display=SEL.size?'inline-block':'none';
  // Auto-switch to Files mode when selection is non-empty
  if(SEL.size){
    document.querySelector('input[name=mode][value=files]').checked=true;
    modeChange();
  }
}

function scanSelected(){
  if(!SEL.size) return;
  document.getElementById('files-val').value=[...SEL].join('\n');
  doScan();
}

// ── Log ──────────────────────────────────────────────────────────────────
function clearLog(){
  document.getElementById('log').textContent='';
  document.getElementById('log-card').style.display='none';
  document.getElementById('clear-btn').style.display='none';
  document.getElementById('scan-status').textContent='';
}

// ── Scan ─────────────────────────────────────────────────────────────────
function doScan(){
  const mode=document.querySelector('input[name=mode]:checked').value;
  const dry=document.getElementById('dry-run').checked;
  const body={mode,dry_run:dry};

  if(mode==='files'){
    const raw=document.getElementById('files-val').value.trim();
    if(!raw){alert('Select contracts from the catalog or paste a file path.');return;}
    body.files=normPaths(raw).split('\n').filter(Boolean);
  } else if(mode==='vendor'){
    const v=document.getElementById('vendor-val').value.trim();
    if(!v){alert('Enter a vendor name.');return;}
    body.vendor=v;
  } else if(mode==='location'){
    body.location=document.getElementById('location-val').value;
  } else if(mode==='type'){
    const t=document.getElementById('type-val').value;
    if(!t){alert('Select a document type.');return;}
    body.doc_type=t;
  }

  const log=document.getElementById('log');
  const btn=document.getElementById('scan-btn');
  const status=document.getElementById('scan-status');
  log.textContent='';
  document.getElementById('log-card').style.display='block';
  document.getElementById('clear-btn').style.display='none';
  btn.disabled=true; btn.textContent='Scanning…'; status.textContent='';

  function done(rc){
    btn.disabled=false; btn.textContent='🔍 Scan';
    document.getElementById('clear-btn').style.display='inline-block';
    log.textContent+='\n'+(rc===0?'── done ──':'── errors (exit '+rc+') ──')+'\n';
    status.textContent=rc===0?'Done':'Errors';
    log.scrollTop=log.scrollHeight;
  }

  fetch('/api/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  .then(resp=>{
    const reader=resp.body.getReader(), dec=new TextDecoder();
    let buf='';
    function read(){return reader.read().then(({done:d,value})=>{
      if(d) return done(0);
      buf+=dec.decode(value,{stream:true});
      const parts=buf.split('\n\n'); buf=parts.pop();
      for(const chunk of parts){
        if(!chunk.startsWith('data: ')) continue;
        const pay=chunk.slice(6);
        try{
          const obj=JSON.parse(pay);
          if(obj&&obj.__done__!==undefined) return done(obj.rc);
          log.textContent+=(typeof obj==='string'?obj:JSON.stringify(obj))+'\n';
        }catch{log.textContent+=pay+'\n';}
        log.scrollTop=log.scrollHeight;
      }
      return read();
    });}
    return read();
  }).catch(()=>{log.textContent+='[ERROR] Server not responding.\n'; done(1);});
}
</script>
</body>
</html>"""


@app.route("/", methods=["GET"])
def index():
    return SCAN_PAGE, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/api/vendors", methods=["GET"])
def vendors():
    seen, seen_set = [], set()
    try:
        with open(CSV_PATH, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                v = row.get("VendorFolder", "").strip()
                if v and v not in seen_set:
                    seen_set.add(v)
                    seen.append(v)
    except FileNotFoundError:
        return "[]", 404, {"Content-Type": "application/json"}
    return json.dumps(sorted(seen, key=str.lower)), 200, {"Content-Type": "application/json"}


@app.route("/api/contracts", methods=["GET"])
def contracts():
    rows = []
    try:
        with open(CSV_PATH, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                rows.append({
                    "vendor":     row.get("VendorFolder", "").strip(),
                    "filename":   row.get("Filename", "").strip(),
                    "filepath":   row.get("FilePath", "").strip(),
                    "location":   row.get("ContractLocation", "").strip(),
                    "doctype":    row.get("DocType", "").strip(),
                    "signed":     row.get("SigningStatus", "").strip(),
                    "effective":  row.get("EffectiveDate", "").strip(),
                    "expiration": row.get("ExpirationDate", "").strip(),
                })
    except FileNotFoundError:
        return "[]", 404, {"Content-Type": "application/json"}
    return json.dumps(rows), 200, {"Content-Type": "application/json"}


@app.route("/api/scan", methods=["POST", "OPTIONS"])
def scan():
    if request.method == "OPTIONS":
        return "", 204

    body     = request.get_json(force=True) or {}
    mode     = body.get("mode", "files")
    files    = body.get("files", [])
    vendor   = body.get("vendor", "")
    location = body.get("location", "")
    doc_type = body.get("doc_type", "")
    dry_run  = body.get("dry_run", False)

    args = [sys.executable, str(SCAN_SCRIPT)]
    if mode == "all":
        args.append("--all")
    elif mode == "vendor" and vendor:
        args += ["--vendor", vendor]
    elif mode == "location" and location:
        args += ["--location", location]
    elif mode == "type" and doc_type:
        args += ["--type", doc_type]
    elif mode == "files" and files:
        args += [_norm_path(f) for f in files]
    else:
        def _err():
            yield f"data: {json.dumps('[ERROR] No valid scan target.')}\n\n"
            yield f"data: {json.dumps({'__done__': True, 'rc': 1})}\n\n"
        return Response(_err(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    if dry_run:
        args.append("--dry-run")

    def generate():
        try:
            proc = subprocess.Popen(
                args,
                cwd=str(SHAREPOINT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
            )
            for line in proc.stdout:
                yield f"data: {json.dumps(line.rstrip())}\n\n"
            proc.wait()
            yield f"data: {json.dumps({'__done__': True, 'rc': proc.returncode})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps(f'[ERROR] {exc}')}\n\n"
            yield f"data: {json.dumps({'__done__': True, 'rc': 1})}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/sync-sor", methods=["POST", "OPTIONS"])
def sync_sor():
    if request.method == "OPTIONS":
        return "", 204

    body     = request.get_json(force=True) or {}
    dry_run  = body.get("dry_run", False)

    args = [sys.executable, str(SYNC_SCRIPT)]
    if dry_run:
        args.append("--dry-run")

    def generate():
        try:
            proc = subprocess.Popen(
                args,
                cwd=str(SHAREPOINT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                bufsize=1,
            )
            for line in proc.stdout:
                yield f"data: {json.dumps(line.rstrip())}\n\n"
            proc.wait()
            yield f"data: {json.dumps({'__done__': True, 'rc': proc.returncode})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps(f'[ERROR] {exc}')}\n\n"
            yield f"data: {json.dumps({'__done__': True, 'rc': 1})}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/create-folder", methods=["POST", "OPTIONS"])
def create_folder():
    if request.method == "OPTIONS":
        return "", 204
    body = request.get_json(force=True) or {}
    location    = body.get("location", "").strip()
    folder_name = body.get("folder_name", "").strip()
    if not location or not folder_name:
        return json.dumps({"ok": False, "message": "location and folder_name are required."}), 400, {"Content-Type": "application/json"}
    if ".." in folder_name or "/" in folder_name or "\\" in folder_name:
        return json.dumps({"ok": False, "message": "Invalid folder name."}), 400, {"Content-Type": "application/json"}
    target = SHAREPOINT / location / folder_name
    try:
        target.mkdir(parents=True, exist_ok=True)
        return json.dumps({"ok": True, "message": f"Created: {location}\\{folder_name}"}), 200, {"Content-Type": "application/json"}
    except Exception as exc:
        return json.dumps({"ok": False, "message": str(exc)}), 500, {"Content-Type": "application/json"}


@app.route("/api/upload-file", methods=["POST", "OPTIONS"])
def upload_file():
    if request.method == "OPTIONS":
        return "", 204
    location      = request.form.get("location", "").strip()
    vendor_folder = request.form.get("vendor_folder", "").strip()
    f             = request.files.get("file")
    if not location or not vendor_folder or not f:
        return json.dumps({"ok": False, "message": "location, vendor_folder, and file are required."}), 400, {"Content-Type": "application/json"}
    filename = secure_filename(f.filename)
    if not filename:
        return json.dumps({"ok": False, "message": "Invalid filename."}), 400, {"Content-Type": "application/json"}
    if ".." in vendor_folder or "/" in vendor_folder or "\\" in vendor_folder:
        return json.dumps({"ok": False, "message": "Invalid vendor folder name."}), 400, {"Content-Type": "application/json"}
    dest_dir = SHAREPOINT / location / vendor_folder
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        f.save(str(dest_dir / filename))
        return json.dumps({"ok": True, "message": f"Uploaded: {location}\\{vendor_folder}\\{filename}"}), 200, {"Content-Type": "application/json"}
    except Exception as exc:
        return json.dumps({"ok": False, "message": str(exc)}), 500, {"Content-Type": "application/json"}


@app.route("/api/upload-for-anon", methods=["POST", "OPTIONS"])
def upload_for_anon():
    """FIX 1: stage a contract uploaded from any location into _anon-private/staging/.
    Returns the relative staged_path that /api/detect accepts."""
    if request.method == "OPTIONS":
        return "", 204
    f = request.files.get("file")
    if not f:
        return json.dumps({"ok": False, "error": "file is required."}), 400, {"Content-Type": "application/json"}
    # BUG 1: take only the basename so a full path doesn't get flattened into one mangled token.
    filename = secure_filename(Path(f.filename).name)
    if not filename:
        return json.dumps({"ok": False, "error": "Invalid filename."}), 400, {"Content-Type": "application/json"}
    ext = Path(filename).suffix.lower()
    if ext not in (".docx", ".pdf"):
        return json.dumps({"ok": False, "error": f"Unsupported file type '{ext}'. Only .docx and .pdf are accepted."}), 400, {"Content-Type": "application/json"}
    staging_dir = SHAREPOINT / "_anon-private" / "staging"
    try:
        staging_dir.mkdir(parents=True, exist_ok=True)
        dest = staging_dir / filename
        f.save(str(dest))
        staged_path = str(dest.relative_to(SHAREPOINT)).replace("\\", "/")
        return json.dumps({"ok": True, "staged_path": staged_path}), 200, {"Content-Type": "application/json"}
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}), 500, {"Content-Type": "application/json"}


@app.route("/api/move-expired", methods=["POST", "OPTIONS"])
def move_expired():
    if request.method == "OPTIONS":
        return "", 204

    SOURCE_LOC = "01 Active Contracts"
    DEST_LOC   = "04 Expired Contracts"
    today      = datetime.now().date()

    moved   = 0
    skipped = 0
    errors  = []

    try:
        with open(CSV_PATH, encoding="utf-8", newline="") as f:
            reader     = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])
            rows       = list(reader)

        for row in rows:
            if row.get("ContractLocation", "").strip() != SOURCE_LOC:
                continue
            exp_str = (row.get("ExpirationDate") or "").strip()[:10]
            if not exp_str:
                skipped += 1
                continue
            try:
                exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            except ValueError:
                skipped += 1
                continue
            if exp_date > today:
                skipped += 1
                continue

            vendor = (row.get("VendorFolder") or "").strip()
            fname  = (row.get("Filename")     or "").strip()
            if not fname:
                skipped += 1
                continue

            src     = SHAREPOINT / SOURCE_LOC / vendor / fname if vendor else SHAREPOINT / SOURCE_LOC / fname
            dst_dir = SHAREPOINT / DEST_LOC / vendor            if vendor else SHAREPOINT / DEST_LOC
            dst     = dst_dir / fname

            if not src.exists():
                errors.append(f"File not found on disk: {(''+vendor+'/') if vendor else ''}{fname}")
                skipped += 1
                continue

            try:
                dst_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                row["ContractLocation"] = DEST_LOC
                moved += 1
            except Exception as exc:
                errors.append(f"{fname}: {exc}")
                skipped += 1

        if moved > 0:
            if CSV_PATH.exists():
                shutil.copy2(str(CSV_PATH), str(CSV_PATH.with_suffix(".csv.bak")))
            with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

        return json.dumps({"ok": True, "moved": moved, "skipped": skipped, "errors": errors}), 200, {"Content-Type": "application/json"}

    except Exception as exc:
        return json.dumps({"ok": False, "moved": 0, "skipped": skipped, "errors": [str(exc)]}), 500, {"Content-Type": "application/json"}


ANON_SCRIPT = TOOLS / "anonymization" / "anonymize.py"
MAPPING_PATH = SHAREPOINT / "_anon-private" / "mapping.json"
COUNTERPARTIES_PATH = TOOLS / "kb" / "COUNTERPARTIES.md"


@app.route("/api/anonymize", methods=["POST", "OPTIONS"])
def anonymize():
    if request.method == "OPTIONS":
        return "", 204

    body = request.get_json(force=True) or {}
    rel_path = (body.get("path") or "").strip().replace("\\", "/")

    if not rel_path:
        def _err():
            yield f"data: {json.dumps('[ERROR] path is required.')}\n\n"
            yield f"data: {json.dumps({'__done__': True, 'rc': 1})}\n\n"
        return Response(_err(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    abs_path = SHAREPOINT / rel_path
    if not abs_path.exists():
        def _err2():
            yield f"data: {json.dumps(f'[ERROR] File not found: {rel_path}')}\n\n"
            yield f"data: {json.dumps({'__done__': True, 'rc': 1})}\n\n"
        return Response(_err2(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    output_dir = str(abs_path.parent)
    args = [
        sys.executable,
        str(ANON_SCRIPT),
        "--input", str(abs_path),
        "--output-dir", output_dir,
        "--audit",
    ]

    def generate():
        try:
            proc = subprocess.Popen(
                args,
                cwd=str(TOOLS),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
            )
            for line in proc.stdout:
                yield f"data: {json.dumps(line.rstrip())}\n\n"
            proc.wait()
            yield f"data: {json.dumps({'__done__': True, 'rc': proc.returncode})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps(f'[ERROR] {exc}')}\n\n"
            yield f"data: {json.dumps({'__done__': True, 'rc': 1})}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/detect", methods=["POST", "OPTIONS"])
def detect():
    if request.method == "OPTIONS":
        return "", 204
    try:
        body = request.get_json(force=True) or {}
        rel_path = (body.get("path") or "").strip().replace("\\", "/")
        if not rel_path:
            return json.dumps({"ok": False, "error": "path is required."}), 400, {"Content-Type": "application/json"}

        abs_path = SHAREPOINT / rel_path
        if not abs_path.exists():
            return json.dumps({"ok": False, "error": f"File not found: {rel_path}"}), 404, {"Content-Type": "application/json"}

        name_map, alias_map = get_mapping(MAPPING_PATH, COUNTERPARTIES_PATH, rebuild=False)

        # B1: extract context from request body
        ctx           = body.get("context") or {}
        contract_type = (ctx.get("contract_type") or "unknown").strip().lower()
        party_2       = (ctx.get("party_2") or "").strip()
        add_parties   = [p.strip() for p in (ctx.get("additional_parties") or []) if p.strip()]

        # FIX 3: freetext context — no whitelist validation; compute advisory flags only.
        _known_types = {"nda", "mnda", "msa", "sow", "po", "amendment", "license", "other"}
        contract_type_recognized = contract_type in _known_types
        _p2l = party_2.lower()
        party_2_in_mapping = bool(party_2) and (
            any(k.lower() == _p2l for k in name_map) or
            any(k.lower() == _p2l for k in alias_map)
        )

        # FIX 2: auto-create a counterparty folder in 05-In-Process derived from party_2.
        # Skip silently when party_2 is blank or sanitizes to empty.
        if party_2:
            folder_name = re.sub(r'[\\/:*?"<>|]', "", party_2).strip().rstrip(". ")
            if folder_name:
                cp_folder = SHAREPOINT / "05-In-Process" / folder_name
                if not cp_folder.exists():
                    cp_folder.mkdir(parents=True, exist_ok=True)
                    log.info("Created 05-In-Process folder: %s", folder_name)

        # Move a staged upload into 05-In-Process\<party_2>\ now that party_2 is known.
        # Files already in their final location are left untouched.
        staging_dir = SHAREPOINT / "_anon-private" / "staging"
        try:
            in_staging = staging_dir.resolve() in abs_path.resolve().parents
        except Exception:
            in_staging = False
        if in_staging:
            move_folder = re.sub(r'[\\/:*?"<>|]', "", party_2).strip().rstrip(". ") if party_2 else ""
            if move_folder:
                dest_dir  = SHAREPOINT / "05-In-Process" / move_folder
                dest_file = dest_dir / abs_path.name
                if dest_file.exists():
                    return json.dumps({"ok": False, "error": f"File already exists in 05-In-Process\\{move_folder}\\{abs_path.name}. Remove it first or rename the upload."}), 409, {"Content-Type": "application/json"}
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(abs_path), str(dest_file))
                log.info("Moved staged file to: %s", dest_file)
                abs_path = dest_file
            else:
                log.warning("Staged file %s has blank party_2 — left in staging.", abs_path.name)

        # Inject party_2 + additional_parties as document-local seeds into alias_map
        # so detect_file's B0.1 binding extraction has pre-seeded names to match against.
        # These are added as name_map entries (not alias_map) so they participate in
        # full-name Layer 1 detection, not just the alias pass.
        ctx_name_map = dict(name_map)
        for extra_name in ([party_2] if party_2 else []) + add_parties:
            if extra_name and extra_name not in ctx_name_map:
                # Generate a provisional token — detect_file will assign the real
                # PARTY-XXXX from mapping.json; this ensures the name is searched.
                # Use a deterministic slot: look up in name_map case-insensitively.
                matched = next(
                    (v for k, v in name_map.items()
                     if k.lower() == extra_name.lower()), None
                )
                if matched:
                    ctx_name_map[extra_name] = matched
                # If not in mapping at all, skip — don't invent tokens.

        spans = detect_file(
            abs_path, ctx_name_map, alias_map, abs_path.parent,
            contract_type=contract_type,
            context=ctx,
        )

        # C2: cross-reference spans against decisions library
        library = _load_decisions_library()
        for span in spans:
            key = _library_key(span["original_text"], span["entity_type"])
            if key in library:
                entry = library[key]
                span["library_decision"] = entry["decision"]   # "confirm" or "reject"
                span["library_count"]    = entry["count"]
                span["library_hit"]      = True
            else:
                span["library_hit"]      = False
                span["library_decision"] = None
                span["library_count"]    = 0

        # W2: review.json now lives in the private zone — return that path.
        review_path = review_path_for(abs_path)
        rel_review = str(review_path.relative_to(SHAREPOINT)).replace("\\", "/")

        # Phase E: surface review_triggers persisted by detect_file into review.json.
        # Backward compat — default to [] if the key is absent.
        review_triggers = []
        try:
            with open(review_path, encoding="utf-8") as fh:
                review_triggers = json.load(fh).get("review_triggers", [])
        except Exception:
            review_triggers = []

        return json.dumps({"ok": True, "review_path": rel_review, "spans": spans, "review_triggers": review_triggers,
                           "context_notes": {"party_2_in_mapping": party_2_in_mapping,
                                             "contract_type_recognized": contract_type_recognized}}), 200, {"Content-Type": "application/json"}
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}), 500, {"Content-Type": "application/json"}


@app.route("/api/apply-redactions", methods=["POST", "OPTIONS"])
def apply_redactions():
    if request.method == "OPTIONS":
        return "", 204
    try:
        body = request.get_json(force=True) or {}
        rel_path = (body.get("path") or "").strip().replace("\\", "/")
        decisions = body.get("decisions") or {}
        if not rel_path:
            return json.dumps({"ok": False, "error": "path is required."}), 400, {"Content-Type": "application/json"}

        abs_path = SHAREPOINT / rel_path
        review_path = review_path_for(abs_path)
        if not review_path.exists():
            return json.dumps({"ok": False, "error": f"review.json not found: {review_path.name}"}), 404, {"Content-Type": "application/json"}

        with open(review_path, encoding="utf-8") as fh:
            review = json.load(fh)
        for span in review.get("spans", []):
            key = str(span["id"])
            if key in decisions:
                span["confirmed"] = bool(decisions[key])
        with open(review_path, "w", encoding="utf-8") as fh:
            json.dump(review, fh, indent=2, ensure_ascii=False)

        result = apply_file(review_path, abs_path.parent)

        # C3: write decisions back to library
        try:
            library = _load_decisions_library()
            today = time.strftime("%Y-%m-%d")
            for span in review.get("spans", []):
                if span.get("confirmed") is None:
                    continue
                key = _library_key(span["original_text"], span["entity_type"])
                decision = "confirm" if span["confirmed"] else "reject"
                if key in library:
                    # Update existing entry — flip decision if overridden
                    library[key]["decision"]  = decision
                    library[key]["count"]    += 1
                    library[key]["last_seen"] = today
                else:
                    library[key] = {
                        "original_text": span["original_text"],
                        "entity_type":   span["entity_type"],
                        "decision":      decision,
                        "count":         1,
                        "last_seen":     today,
                    }
            _save_decisions_library(library)
            log.info("C3: decisions library updated — %d entries", len(library))
        except Exception as exc:
            log.error("C3: library write-back failed: %s", exc)
            # Non-fatal — apply succeeded; library failure must not block response

        # FAIL-2: relay pass vs quarantine. On failure there is no doc-tree path.
        passed = result.get("passed", False)
        resp = {
            "ok":        True,
            "passed":    passed,
            "confirmed": result.get("confirmed"),
            "rejected":  result.get("rejected"),
            "verify":    result.get("verify"),
        }
        if passed:
            resp["anon_path"]  = result.get("anon_path")
            resp["audit_path"] = result.get("audit_path")
        else:
            resp["quarantine_path"] = result.get("quarantine_path")
            resp["hits"]            = result.get("hits", [])
        return json.dumps(resp), 200, {"Content-Type": "application/json"}
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}), 500, {"Content-Type": "application/json"}


@app.route("/api/de-anonymize", methods=["POST", "OPTIONS"])
def de_anonymize():
    if request.method == "OPTIONS":
        return "", 204
    try:
        body = request.get_json(force=True) or {}
        rel_path = (body.get("path") or "").strip().replace("\\", "/")
        if not rel_path:
            return json.dumps({"ok": False, "error": "path is required."}), 400, {"Content-Type": "application/json"}

        abs_path = SHAREPOINT / rel_path
        if not abs_path.exists():
            return json.dumps({"ok": False, "error": f"File not found: {rel_path}"}), 404, {"Content-Type": "application/json"}

        suffix = ".anon.txt"
        if abs_path.name.endswith(suffix):
            stem = abs_path.name[:-len(suffix)]
        else:
            stem = abs_path.stem

        # W2: review.json lives in the private zone keyed by the source's
        # path-context stem, while the .anon.txt carries the sanitized stem.
        # audit.json (also private now, keyed by the OUTPUT stem derivable from
        # this .anon.txt) carries private_stem, which bridges to the review.json.
        audit_path = audit_path_for(abs_path.parent, stem)
        private_stem = None
        if audit_path.exists():
            try:
                with open(audit_path, encoding="utf-8") as fh:
                    private_stem = json.load(fh).get("private_stem")
            except Exception:
                private_stem = None

        review_path = REVIEWS_DIR / ((private_stem or stem) + ".review.json")
        if not review_path.exists():
            return json.dumps({"ok": False, "error": f"review.json not found for {abs_path.name}"}), 404, {"Content-Type": "application/json"}

        with open(review_path, encoding="utf-8") as fh:
            review = json.load(fh)

        reverse_map = {}
        for span in review.get("spans", []):
            if span.get("confirmed") is True:
                token = span["proposed_token"]
                if token not in reverse_map:
                    reverse_map[token] = span["original_text"]

        content = abs_path.read_text(encoding="utf-8")
        replacements = 0
        for token in sorted(reverse_map, key=len, reverse=True):
            original = reverse_map[token]
            count = content.count(token)
            if count:
                content = content.replace(token, original)
                replacements += count

        restored_path = abs_path.parent / (stem + ".restored.txt")
        restored_path.write_text(content, encoding="utf-8")

        return json.dumps({
            "ok": True,
            "restored_path": str(restored_path.relative_to(SHAREPOINT)).replace("\\", "/"),
            "replacements": replacements,
        }), 200, {"Content-Type": "application/json"}
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}), 500, {"Content-Type": "application/json"}


# ── Quarantine decision endpoints (FAIL-2) ───────────────────────────────────
def _safe_stem(stem: str) -> bool:
    """Reject path-traversal / separator characters in a client-supplied stem."""
    return bool(stem) and "/" not in stem and "\\" not in stem and ".." not in stem


@app.route("/api/quarantine/override", methods=["POST", "OPTIONS"])
def quarantine_override():
    if request.method == "OPTIONS":
        return "", 204
    try:
        body   = request.get_json(force=True) or {}
        stem   = (body.get("stem") or "").strip()
        reason = (body.get("reason") or "").strip()
        if not _safe_stem(stem):
            return json.dumps({"ok": False, "error": "valid stem is required."}), 400, {"Content-Type": "application/json"}

        q_path = QUARANTINE_DIR / (stem + ".anon.txt")
        if not q_path.exists():
            return json.dumps({"ok": False, "error": f"quarantine file not found: {stem}.anon.txt"}), 404, {"Content-Type": "application/json"}

        review_path = REVIEWS_DIR / (stem + ".review.json")
        if not review_path.exists():
            return json.dumps({"ok": False, "error": f"review.json not found for stem: {stem}"}), 404, {"Content-Type": "application/json"}
        with open(review_path, encoding="utf-8") as fh:
            review = json.load(fh)

        doc_output_dir = review.get("doc_output_dir")
        if not doc_output_dir:
            return json.dumps({"ok": False, "error": "review.json missing doc_output_dir."}), 500, {"Content-Type": "application/json"}
        doc_dir        = Path(doc_output_dir)
        sanitized_stem = review.get("sanitized_stem") or stem

        # 1-2: promote the quarantined output into the document tree.
        dest = doc_dir / (sanitized_stem + ".anon.txt")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(q_path), str(dest))

        # Minimal audit.json in the private audits zone so the restore tool can
        # still locate the review.json (keyed by the promoted output's stem).
        src_suffix = Path(review.get("source_path") or "").suffix
        audit_min = {
            "source_file":         sanitized_stem + src_suffix,
            "private_stem":        stem,
            "quarantine_override": True,
            "reason":              reason,
        }
        audit_dest = audit_path_for(doc_dir, sanitized_stem)
        audit_dest.parent.mkdir(parents=True, exist_ok=True)
        audit_dest.write_text(
            json.dumps(audit_min, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # 3: log the override in the decisions library.
        append_override_entry({
            "action":    "quarantine_override",
            "stem":      stem,
            "reason":    reason,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        })

        # 4: remove the quarantine file.
        q_path.unlink()

        rel = str(dest.relative_to(SHAREPOINT)).replace("\\", "/")
        log.info("Quarantine override: %s → %s", stem, rel)
        return json.dumps({"ok": True, "status": "promoted", "path": rel}), 200, {"Content-Type": "application/json"}
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}), 500, {"Content-Type": "application/json"}


@app.route("/api/quarantine/discard", methods=["POST", "OPTIONS"])
def quarantine_discard():
    if request.method == "OPTIONS":
        return "", 204
    try:
        body = request.get_json(force=True) or {}
        stem = (body.get("stem") or "").strip()
        if not _safe_stem(stem):
            return json.dumps({"ok": False, "error": "valid stem is required."}), 400, {"Content-Type": "application/json"}
        q_path = QUARANTINE_DIR / (stem + ".anon.txt")
        if q_path.exists():
            q_path.unlink()
        return json.dumps({"ok": True, "status": "discarded"}), 200, {"Content-Type": "application/json"}
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}), 500, {"Content-Type": "application/json"}


@app.route("/api/quarantine/list", methods=["GET"])
def quarantine_list():
    try:
        if not QUARANTINE_DIR.exists():
            return json.dumps({"ok": True, "quarantined": []}), 200, {"Content-Type": "application/json"}
        stems = sorted(
            p.name[:-len(".anon.txt")]
            for p in QUARANTINE_DIR.iterdir()
            if p.is_file() and p.name.endswith(".anon.txt")
        )
        return json.dumps({"ok": True, "quarantined": stems}), 200, {"Content-Type": "application/json"}
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}), 500, {"Content-Type": "application/json"}


# ── Restore UI ──────────────────────────────────────────────────────────────
RESTORE_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DCS Contract Restore</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f3f4f6;color:#111827;padding:24px 16px}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:24px;max-width:980px;margin:0 auto 20px}
h1{font-size:20px;font-weight:700;margin-bottom:4px}
h2{font-size:15px;font-weight:600;margin-bottom:12px}
.sub{font-size:13px;color:#6b7280;margin-bottom:20px}
label{font-size:13px;color:#374151;display:block;margin-bottom:4px;font-weight:500}
.hint{font-size:12px;color:#9ca3af;font-weight:400}
input[type=text],input[type=search],input[type=file],select{
  width:100%;background:#f9fafb;border:1px solid #d1d5db;border-radius:8px;
  padding:9px 12px;font-size:13px;color:#111827;font-family:inherit;outline:none;transition:border-color .15s}
input:focus,select:focus{border-color:#6366f1}
.row{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:14px}
.field{margin-top:14px}
button.primary{background:#6366f1;color:#fff;border:none;border-radius:8px;padding:9px 20px;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap}
button.primary:hover{background:#4f46e5}
button.primary:disabled{background:#a5b4fc;cursor:not-allowed}
button.ghost{background:transparent;border:1px solid #d1d5db;color:#374151;border-radius:8px;padding:8px 14px;font-size:13px;cursor:pointer;white-space:nowrap}
button.ghost:hover{background:#f3f4f6}
.note{font-size:12px;color:#d97706;background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:10px 14px;margin-top:14px}
.result{margin-top:16px;border-radius:8px;padding:14px 16px;font-size:13px;display:none}
.result.ok{background:#dcfce7;border:1px solid #bbf7d0;color:#166534}
.result.err{background:#fee2e2;border:1px solid #fecaca;color:#991b1b}
.result code{font-family:monospace;font-size:12px}
#restore-status{font-size:12px;color:#9ca3af}
</style>
</head>
<body>

<div class="card">
  <h1>DCS Contract Restore</h1>
  <p class="sub">Reverse anonymization using the review map. Writes <code>&lt;stem&gt;.restored.txt</code> next to the .anon.txt.</p>

  <div class="field">
    <label>Path to .anon.txt <span class="hint">— relative to the SharePoint root</span></label>
    <input type="text" id="anon-path" placeholder="e.g. 05-In-Process/Columbia-Okura/file.anon.txt">
  </div>
  <div class="row">
    <button class="primary" id="restore-btn" onclick="doRestore()">Restore Original</button>
    <span id="restore-status"></span>
  </div>

  <div class="result" id="result"></div>
</div>

<script>
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

function doRestore(){
  const path=document.getElementById('anon-path').value.trim();
  const btn=document.getElementById('restore-btn');
  const status=document.getElementById('restore-status');
  const result=document.getElementById('result');
  result.style.display='none';
  if(!path){alert('Enter the relative path to the .anon.txt file.');return;}
  btn.disabled=true; btn.textContent='Restoring…'; status.textContent='';

  fetch('/api/de-anonymize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path})})
  .then(r=>r.json()).then(d=>{
    btn.disabled=false; btn.textContent='Restore Original'; status.textContent='';
    if(!d.ok){
      result.className='result err';
      result.innerHTML='⚠️ '+esc(d.error||'Restore failed.');
      result.style.display='block';
      return;
    }
    result.className='result ok';
    result.innerHTML='✓ Restored <strong>'+d.replacements+'</strong> token'+(d.replacements===1?'':'s')+
                     '.<br>Wrote <code>'+esc(d.restored_path)+'</code>';
    result.style.display='block';
  }).catch(()=>{
    btn.disabled=false; btn.textContent='Restore Original';
    result.className='result err';
    result.innerHTML='⚠️ Server not responding.';
    result.style.display='block';
  });
}
</script>
</body>
</html>"""


@app.route("/restore", methods=["GET"])
def restore_page():
    return RESTORE_PAGE, 200, {"Content-Type": "text/html; charset=utf-8"}


# ── Anonymizer UI ──────────────────────────────────────────────────────────
ANON_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DCS Contract Anonymizer</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f3f4f6;color:#111827;padding:24px 16px}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:24px;max-width:980px;margin:0 auto 20px}
h1{font-size:20px;font-weight:700;margin-bottom:4px}
h2{font-size:15px;font-weight:600;margin-bottom:12px}
.sub{font-size:13px;color:#6b7280;margin-bottom:20px}
label{font-size:13px;color:#374151;display:block;margin-bottom:4px;font-weight:500}
.hint{font-size:12px;color:#9ca3af;font-weight:400}
input[type=text],input[type=search],input[type=file],select{
  width:100%;background:#f9fafb;border:1px solid #d1d5db;border-radius:8px;
  padding:9px 12px;font-size:13px;color:#111827;font-family:inherit;outline:none;transition:border-color .15s}
input:focus,select:focus{border-color:#6366f1}
.row{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:14px}
.field{margin-top:14px}
button.primary{background:#6366f1;color:#fff;border:none;border-radius:8px;padding:9px 20px;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap}
button.primary:hover{background:#4f46e5}
button.primary:disabled{background:#a5b4fc;cursor:not-allowed}
button.ghost{background:transparent;border:1px solid #d1d5db;color:#374151;border-radius:8px;padding:8px 14px;font-size:13px;cursor:pointer;white-space:nowrap}
button.ghost:hover{background:#f3f4f6}
/* Tabs */
.tabs{display:flex;gap:4px;border-bottom:1px solid #e5e7eb;margin-bottom:18px}
.tab{padding:9px 16px;font-size:13px;font-weight:500;color:#6b7280;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px}
.tab:hover{color:#374151}
.tab.active{color:#4f46e5;border-bottom-color:#6366f1}
.panel{display:none}
.panel.active{display:block}
/* In-process list */
.ip-wrap{max-height:340px;overflow-y:auto;border:1px solid #e5e7eb;border-radius:8px}
.ip-row{display:flex;align-items:center;gap:10px;padding:9px 12px;border-bottom:1px solid #f3f4f6;cursor:pointer;font-size:13px;transition:background .1s}
.ip-row:last-child{border-bottom:none}
.ip-row:hover{background:#f5f3ff}
.ip-row.sel{background:#ede9fe}
.ip-icon{flex:0 0 auto;font-size:14px}
.ip-name{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ip-dir{color:#6b7280;font-size:11px;flex:0 0 auto}
#ip-status{font-size:12px;color:#9ca3af}
#anon-status{font-size:12px;color:#9ca3af}
/* Review table */
.review-card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:24px;max-width:980px;margin:0 auto 20px;display:none}
.grp{margin-bottom:20px}
.grp-head{display:flex;align-items:center;gap:10px;margin-bottom:8px;flex-wrap:wrap}
.layer-badge{display:inline-block;padding:3px 10px;border-radius:999px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.02em}
.lb-counterparty{background:#dbeafe;color:#1e40af}
.lb-counterparty_alias{background:#e0e7ff;color:#3730a3}
.lb-presidio{background:#fce7f3;color:#9d174d}
.lb-commercial_regex{background:#dcfce7;color:#166534}
.grp-count{font-size:12px;color:#9ca3af;margin-right:auto}
.grp-actions{display:flex;gap:6px}
.mini{font-size:11px;padding:4px 10px;border-radius:6px;border:1px solid #d1d5db;background:#fff;color:#374151;cursor:pointer}
.mini:hover{background:#f3f4f6}
table.rv{width:100%;border-collapse:collapse;font-size:12px}
table.rv thead th{position:sticky;top:0;background:#f9fafb;padding:7px 10px;text-align:left;font-size:11px;font-weight:600;color:#6b7280;text-transform:uppercase;border-bottom:1px solid #e5e7eb;white-space:nowrap}
table.rv tbody tr{border-bottom:1px solid #f3f4f6}
table.rv td{padding:6px 10px;vertical-align:middle}
.mono{font-family:monospace;font-size:12px}
.tok{display:inline-block;font-family:monospace;font-size:11px;background:#f3f4f6;color:#4f46e5;border-radius:6px;padding:2px 8px}
.orig{max-width:360px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.score-low{color:#d97706;font-weight:600}
.tier-low  { opacity: 0.55; background: #fffbeb; }
.tier-low td { color: #92400e; }
.tier-medium { background: #eff6ff; }
.act{display:flex;gap:8px;white-space:nowrap}
.act label{display:inline-flex;align-items:center;gap:4px;font-weight:400;margin:0;cursor:pointer;font-size:13px}
.bar{position:sticky;bottom:0;background:#fff;border-top:1px solid #e5e7eb;padding:14px 0 0;margin-top:8px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.bar .summary{font-size:13px;color:#374151;font-weight:500;margin-right:auto}
/* Output log */
.log-card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:24px;max-width:980px;margin:0 auto;display:none}
#log{background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px 14px;
     font-family:monospace;font-size:12px;line-height:1.6;max-height:480px;overflow-y:auto;white-space:pre-wrap}
.note{font-size:12px;color:#d97706;background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:10px 14px;margin-top:14px}
.success{background:#dcfce7;border:1px solid #bbf7d0;color:#166534;border-radius:8px;padding:16px 18px;font-size:13px}
.success a{color:#166534;font-weight:600}
.spin{display:inline-block;font-size:12px;color:#6366f1}
/* B1 — Context form */
.ctx-form{background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:16px 18px;margin-top:16px}
.ctx-form h3{font-size:13px;font-weight:600;color:#374151;margin-bottom:12px;display:flex;align-items:center;gap:8px;cursor:pointer;user-select:none}
.ctx-form h3 .toggle-icon{font-size:11px;color:#9ca3af;transition:transform .2s}
.ctx-form h3.collapsed .toggle-icon{transform:rotate(-90deg)}
.ctx-body{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.ctx-body .full{grid-column:1/-1}
.ctx-body label{font-size:12px;color:#6b7280;font-weight:500;margin-bottom:3px}
.ctx-body select,.ctx-body input[type=text],.ctx-body textarea{
  font-size:12px;padding:7px 10px;background:#fff}
.ctx-body textarea{min-height:52px;resize:vertical;font-size:12px}
.ctx-chk{display:flex;align-items:center;gap:6px;font-size:12px;color:#374151;cursor:pointer}
/* C2 — Library sections */
.lib-section{margin-bottom:24px}
.lib-section-head{display:flex;align-items:center;gap:10px;padding:10px 14px;
  background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;
  cursor:pointer;user-select:none;margin-bottom:0}
.lib-section-head h3{font-size:13px;font-weight:600;color:#374151;margin:0;flex:1}
.lib-section-head .lib-count{font-size:12px;color:#9ca3af}
.lib-section-head .lib-toggle{font-size:11px;color:#9ca3af}
.lib-section-body{border:1px solid #e5e7eb;border-top:none;
  border-radius:0 0 8px 8px;overflow:hidden}
.lib-row-hit td{background:#fafaf5}
.lib-prior{font-size:11px;color:#6b7280;font-style:italic}
.lib-prior.confirm{color:#166534}
.lib-prior.reject{color:#991b1b}
/* Phase E — review triggers */
#trigger-panel{margin-top:4px}
.trigger-banner{border-radius:8px;padding:12px 16px;margin-top:14px;font-size:13px;line-height:1.5}
.trigger-banner h4{font-size:13px;font-weight:600;margin-bottom:6px}
.trigger-banner ul{margin:0;padding-left:18px}
.trigger-banner li{margin:2px 0}
.trigger-banner.flag{background:#fffbeb;border:1px solid #fde68a;color:#92400e}
.trigger-banner.stop{background:#fef2f2;border:1px solid #fecaca;color:#991b1b}
tr.trigger-highlight td{background:#fef9c3 !important}
</style>
</head>
<body>

<div class="card">
  <h1>DCS Contract Anonymizer</h1>
  <p class="sub">Detect candidate redactions, review each one, then apply. Output (<code>.anon.txt</code> + <code>.audit.json</code>) is written next to the source file.</p>

  <div class="tabs">
    <div class="tab active" data-tab="select" onclick="switchTab('select')">Select from 05-In-Process</div>
    <div class="tab" data-tab="upload" onclick="switchTab('upload')">Upload a file</div>
  </div>

  <!-- Select panel -->
  <div class="panel active" id="panel-select">
    <div class="row" style="margin-top:0">
      <label style="margin:0">Files in 05-In-Process <span class="hint">— click to select, then Detect</span></label>
      <button class="ghost" onclick="loadInProcess()" style="margin-left:auto">↻ Refresh</button>
    </div>
    <div class="ip-wrap" id="ip-wrap" style="margin-top:8px">
      <p style="padding:18px;text-align:center;color:#9ca3af;font-size:13px" id="ip-empty">Loading…</p>
    </div>
    <div class="row">
      <button class="primary" id="anon-sel-btn" onclick="detectSelected()" disabled>🛡️ Anonymize Selected</button>
      <span id="ip-status"></span>
    </div>
    <p class="note">Folders are shown for navigation context only — select a file to anonymize. Subfolders are not recursed from here; open the folder in SharePoint to anonymize a file inside it, or use Upload.</p>
  </div>

  <!-- Upload panel -->
  <div class="panel" id="panel-upload">
    <div class="field">
      <label>Upload contract (from any location) <span class="hint">(.docx / .pdf) — staged privately, then detected</span></label>
      <input type="file" id="up-file" accept=".docx,.pdf">
    </div>
    <div class="row">
      <button class="primary" id="anon-up-btn" onclick="uploadAndDetect()">⬆️ Upload &amp; Anonymize</button>
      <span id="anon-status"></span>
    </div>
  </div>

  <!-- B1 — Context form (shared between select and upload panels) -->
  <div class="ctx-form" id="ctx-form">
    <h3 id="ctx-toggle" onclick="toggleCtx()">
      Contract Context
      <span class="toggle-icon" id="ctx-icon">▼</span>
      <span style="font-size:11px;color:#9ca3af;font-weight:400;margin-left:4px">(optional — improves detection accuracy)</span>
    </h3>
    <div class="ctx-body" id="ctx-body">
      <div>
        <label>Contract type <span style="font-weight:400;color:#9ca3af">(type or pick — freetext allowed)</span></label>
        <input type="text" id="ctx-type" list="doctype-list" placeholder="e.g. NDA">
        <datalist id="doctype-list">
          <option value="NDA"></option><option value="MNDA"></option><option value="MSA"></option>
          <option value="SOW"></option><option value="PO"></option><option value="Amendment"></option>
          <option value="License"></option><option value="Other"></option>
        </datalist>
      </div>
      <div>
        <label>Counterparty name <span style="font-weight:400;color:#9ca3af">(Party 2 — type or pick, freetext allowed)</span></label>
        <input type="text" id="ctx-party2" list="counterparty-list" placeholder="e.g. Acme Corp">
        <datalist id="counterparty-list"></datalist>
      </div>
      <div class="full">
        <label>Additional parties <span style="font-weight:400;color:#9ca3af">(one per line — subcontractors, affiliates)</span></label>
        <textarea id="ctx-parties" placeholder="e.g. Colmac Coil&#10;Walmart"></textarea>
      </div>
      <div class="full" style="display:flex;gap:20px;flex-wrap:wrap">
        <label class="ctx-chk">
          <input type="checkbox" id="ctx-ignore-jur" checked>
          Ignore governing-law jurisdiction
        </label>
        <label class="ctx-chk">
          <input type="checkbox" id="ctx-ignore-ind" checked>
          Ignore standard industry bodies (OSHA, ISO, ANSI…)
        </label>
      </div>
    </div>
  </div>
</div>

<!-- FIX 3 — freetext context advisory notices -->
<div id="ctx-notes" style="max-width:980px;margin:0 auto"></div>

<!-- Review table (Phase 2) -->
<div class="review-card" id="review-card">
  <h2>Review Redactions</h2>
  <p class="sub" style="margin-bottom:16px">Confirm or reject each detected item. Only confirmed items will be redacted.</p>
  <div id="review-groups"></div>
  <div id="trigger-panel"></div>
  <div class="bar">
    <span class="summary" id="review-summary">0 confirmed · 0 rejected</span>
    <button class="ghost" onclick="cancelReview()">Cancel</button>
    <button class="primary" id="apply-btn" onclick="applyRedactions()">Apply Redactions</button>
  </div>
</div>

<!-- Output log (detect spinner / errors) -->
<div class="log-card" id="log-card">
  <h2>Output</h2>
  <div id="log"></div>
</div>

<script>
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

const LAYER_ORDER=['counterparty','counterparty_alias','presidio','commercial_regex'];
const LAYER_LABEL={counterparty:'Counterparty',counterparty_alias:'Counterparty Alias',presidio:'Presidio PII',commercial_regex:'Commercial'};
let currentFilePath=null;
let SPANS=[];
let TRIGGERS=[];

// ── Tabs ──────────────────────────────────────────────────────────────────
function switchTab(name){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.tab===name));
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active',p.id==='panel-'+name));
}

// ── In-process listing ──────────────────────────────────────────────────────
let IP_SEL=null;
function loadInProcess(){
  const wrap=document.getElementById('ip-wrap');
  wrap.innerHTML='<p id="ip-empty" style="padding:18px;text-align:center;color:#9ca3af;font-size:13px">Loading…</p>';
  IP_SEL=null;
  document.getElementById('anon-sel-btn').disabled=true;
  fetch('/api/list-in-process').then(r=>r.json()).then(d=>{
    if(!d.ok){wrap.innerHTML='<p style="padding:18px;text-align:center;color:#991b1b;font-size:13px">'+esc(d.error||'Could not load.')+'</p>';return;}
    if(!d.entries.length){wrap.innerHTML='<p style="padding:18px;text-align:center;color:#9ca3af;font-size:13px">05-In-Process is empty.</p>';return;}
    wrap.innerHTML='';
    d.entries.forEach(e=>{
      const row=document.createElement('div');
      row.className='ip-row';
      row.dataset.path=e.path;
      row.dataset.dir=e.is_dir?'1':'0';
      row.innerHTML='<span class="ip-icon">'+(e.is_dir?'📁':'📄')+'</span>'+
                    '<span class="ip-name" title="'+esc(e.name)+'">'+esc(e.name)+'</span>'+
                    (e.is_dir?'<span class="ip-dir">folder</span>':'');
      if(!e.is_dir) row.onclick=()=>selectIp(row);
      else row.style.cursor='default';
      wrap.appendChild(row);
    });
  }).catch(()=>{wrap.innerHTML='<p style="padding:18px;text-align:center;color:#991b1b;font-size:13px">Server not responding.</p>';});
}
function selectIp(row){
  document.querySelectorAll('.ip-row').forEach(r=>r.classList.remove('sel'));
  row.classList.add('sel');
  IP_SEL=row.dataset.path;
  document.getElementById('anon-sel-btn').disabled=false;
  // Selecting from the list clears any pending upload selection.
  const uf=document.getElementById('up-file'); if(uf) uf.value='';
  const us=document.getElementById('anon-status'); if(us) us.textContent='';
}
function detectSelected(){
  if(!IP_SEL) return;
  runDetect(IP_SEL,'ip-status');
}
loadInProcess();

// FIX 3: populate the counterparty datalist from /api/vendors (freetext still allowed).
fetch('/api/vendors').then(r=>r.json()).then(vs=>{
  const dl=document.getElementById('counterparty-list');
  if(!dl||!Array.isArray(vs)) return;
  dl.innerHTML=vs.map(v=>'<option value="'+esc(v)+'"></option>').join('');
}).catch(()=>{});

// ── Upload then detect ──────────────────────────────────────────────────────
function uploadAndDetect(){
  const fileInput=document.getElementById('up-file');
  const status=document.getElementById('anon-status');
  if(!fileInput.files.length){alert('Choose a file to upload.');return;}
  const file=fileInput.files[0];
  const btn=document.getElementById('anon-up-btn');
  // Selecting a file via upload clears any 05-In-Process list selection.
  document.querySelectorAll('.ip-row').forEach(r=>r.classList.remove('sel'));
  IP_SEL=null; const _sb=document.getElementById('anon-sel-btn'); if(_sb)_sb.disabled=true;
  btn.disabled=true; btn.textContent='Uploading…'; status.textContent='Uploading…';

  const fd=new FormData();
  fd.append('file',file);

  fetch('/api/upload-for-anon',{method:'POST',body:fd})
  .then(r=>r.json()).then(d=>{
    if(!d.ok){btn.disabled=false;btn.textContent='⬆️ Upload & Anonymize';status.textContent='Upload failed';alert(d.error||'Upload failed.');return;}
    status.textContent='Uploaded ✓';
    runDetect(d.staged_path,'anon-status',()=>{btn.disabled=false;btn.textContent='⬆️ Upload & Anonymize';});
  }).catch(()=>{btn.disabled=false;btn.textContent='⬆️ Upload & Anonymize';status.textContent='Upload error';alert('Upload request failed.');});
}

// ── Context form ──────────────────────────────────────────────────────────
function toggleCtx(){
  const body=document.getElementById('ctx-body');
  const toggle=document.getElementById('ctx-toggle');
  const icon=document.getElementById('ctx-icon');
  const collapsed=toggle.classList.toggle('collapsed');
  body.style.display=collapsed?'none':'grid';
  icon.textContent=collapsed?'▶':'▼';
}

function getContext(){
  return {
    contract_type: document.getElementById('ctx-type').value,
    party_2:       document.getElementById('ctx-party2').value.trim(),
    additional_parties: document.getElementById('ctx-parties').value
      .split(/\r?\n/).map(s=>s.trim()).filter(Boolean),
    ignore_jurisdiction:    document.getElementById('ctx-ignore-jur').checked,
    ignore_industry_bodies: document.getElementById('ctx-ignore-ind').checked,
  };
}

// ── FIX 3: freetext context advisory notices ────────────────────────────────
function renderContextNotes(notes){
  const el=document.getElementById('ctx-notes');
  if(!el) return;
  el.innerHTML='';
  if(!notes) return;
  const p2=document.getElementById('ctx-party2').value.trim();
  const ct=document.getElementById('ctx-type').value.trim();
  let html='';
  if(notes.party_2_in_mapping===false && p2){
    html+='<div class="note">⚠️ '+esc(p2)+' is not in the counterparty map — detection will use '+
          'text matching only. Consider adding to COUNTERPARTIES.md after this run.</div>';
  }
  if(notes.contract_type_recognized===false && ct){
    html+='<div class="note">⚠️ \''+esc(ct)+'\' is not a recognized document type — '+
          'using \'Other\' detection weights.</div>';
  }
  el.innerHTML=html;
}

// ── Phase 1: detect (synchronous JSON) ──────────────────────────────────────
function runDetect(relPath,statusId,onDone){
  const log=document.getElementById('log');
  const status=document.getElementById(statusId);
  const selBtn=document.getElementById('anon-sel-btn');
  const _cn=document.getElementById('ctx-notes'); if(_cn) _cn.innerHTML='';
  document.getElementById('review-card').style.display='none';
  log.innerHTML='<span class="spin">⏳ Detecting…</span>';
  document.getElementById('log-card').style.display='block';
  if(selBtn) selBtn.disabled=true;
  if(status) status.textContent='Detecting…';

  fetch('/api/detect',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({path:relPath, context:getContext()})})
  .then(r=>r.json()).then(d=>{
    if(selBtn) selBtn.disabled=(IP_SEL===null);
    if(status) status.textContent=d.ok?'Detected':'Error';
    if(onDone) onDone();
    if(!d.ok){
      log.textContent='[ERROR] '+(d.error||'Detection failed.');
      return;
    }
    document.getElementById('log-card').style.display='none';
    currentFilePath=relPath;
    SPANS=d.spans||[];
    TRIGGERS=d.review_triggers||[];
    renderContextNotes(d.context_notes);
    renderReview();
  }).catch(()=>{
    if(selBtn) selBtn.disabled=(IP_SEL===null);
    if(status) status.textContent='Error';
    if(onDone) onDone();
    log.textContent='[ERROR] Server not responding.';
  });
}

// ── Phase 2: review table ───────────────────────────────────────────────────
function defaultConfirm(s){
  if(s.score_tier==='low') return false;     // pre-rejected
  if(s.score_tier==='medium') return false;  // pre-confirmed off — requires explicit decision
  return true;                               // pre-confirmed on
}

function renderReview(){
  const card=document.getElementById('review-card');
  const groups=document.getElementById('review-groups');
  groups.innerHTML='';
  // Reset trigger panel + apply button before re-render
  document.getElementById('trigger-panel').innerHTML='';
  const applyBtn=document.getElementById('apply-btn');
  applyBtn.disabled=false; applyBtn.textContent='Apply Redactions';

  if(!SPANS.length){
    groups.innerHTML='<p style="padding:18px;text-align:center;color:#9ca3af;font-size:13px">No redaction candidates detected.</p>';
    card.style.display='block';
    renderTriggers();
    updateSummary();
    return;
  }

  // Seed default decisions — library hits use prior decision as default
  SPANS.forEach(s=>{
    if(s._dec===undefined){
      if(s.library_hit && s.library_decision==='confirm') s._dec=true;
      else if(s.library_hit && s.library_decision==='reject') s._dec=false;
      else s._dec=defaultConfirm(s);
    }
  });

  const libSpans=SPANS.filter(s=>s.library_hit);
  const newSpans=SPANS.filter(s=>!s.library_hit);

  // ── Section 1: Library matches (collapsed by default) ──────────────
  if(libSpans.length){
    const sec=document.createElement('div');
    sec.className='lib-section';
    const headId='lib-head-'+Date.now();
    const bodyId='lib-body-'+Date.now();
    sec.innerHTML=
      '<div class="lib-section-head" onclick="toggleLibSection(\''+bodyId+'\',\''+headId+'\')">'+
        '<h3>📚 Library matches</h3>'+
        '<span class="lib-count">'+libSpans.length+' item'+(libSpans.length===1?'':'s')+
          ' — auto-decided from prior sessions</span>'+
        '<span class="lib-toggle" id="'+headId+'">▶ (collapsed)</span>'+
      '</div>'+
      '<div id="'+bodyId+'" style="display:none">'+
        _renderSpanTable(libSpans, true)+
      '</div>';
    groups.appendChild(sec);
  }

  // ── Section 2: New detections (expanded) ───────────────────────────
  if(newSpans.length){
    const sec=document.createElement('div');
    sec.className='lib-section';
    if(libSpans.length){
      sec.innerHTML='<div class="lib-section-head" style="cursor:default;margin-bottom:8px">'+
        '<h3>🔍 New detections</h3>'+
        '<span class="lib-count">'+newSpans.length+' item'+(newSpans.length===1?'':'s')+
          ' — review required</span>'+
      '</div>';
    }
    // Group new spans by layer
    const grpDiv=document.createElement('div');
    LAYER_ORDER.forEach(layer=>{
      const items=newSpans.filter(s=>s.layer===layer);
      if(!items.length) return;
      const grp=document.createElement('div');
      grp.className='grp';
      grp.innerHTML=
        '<div class="grp-head">'+
          '<span class="layer-badge lb-'+layer+'">'+esc(LAYER_LABEL[layer]||layer)+'</span>'+
          '<span class="grp-count">'+items.length+' item'+(items.length===1?'':'s')+'</span>'+
          '<div class="grp-actions">'+
            '<button class="mini" onclick="bulk_ids('+JSON.stringify(items.map(s=>s.id))+',true)">Confirm all</button>'+
            '<button class="mini" onclick="bulk_ids('+JSON.stringify(items.map(s=>s.id))+',false)">Reject all</button>'+
          '</div>'+
        '</div>'+
        _renderSpanTable(items, false);
      grpDiv.appendChild(grp);
    });
    sec.appendChild(grpDiv);
    groups.appendChild(sec);
  }

  card.style.display='block';
  renderTriggers();
  updateSummary();
}

// ── Phase E: review triggers panel ──────────────────────────────────────────
function renderTriggers(){
  const panel=document.getElementById('trigger-panel');
  const applyBtn=document.getElementById('apply-btn');
  panel.innerHTML='';
  // Clear any prior highlights
  document.querySelectorAll('tr.trigger-highlight').forEach(tr=>tr.classList.remove('trigger-highlight'));
  if(!TRIGGERS.length) return;

  const stops=TRIGGERS.filter(t=>t.severity==='HARD_STOP');
  const flags=TRIGGERS.filter(t=>t.severity==='FLAG');
  const highlights=TRIGGERS.filter(t=>t.severity==='HIGHLIGHT');

  // HIGHLIGHT severity: highlight the referenced rows (no banner on its own)
  highlights.forEach(t=>(t.span_indices||[]).forEach(id=>{
    const tr=document.querySelector('tr[data-span-id="'+id+'"]');
    if(tr) tr.classList.add('trigger-highlight');
  }));

  if(stops.length){
    // HARD_STOP — red banner, Apply disabled
    panel.innerHTML='<div class="trigger-banner stop">'+
      '<h4>⛔ Cannot apply — hard stop conditions present.</h4>'+
      '<ul>'+stops.map(t=>'<li>'+esc(t.message)+'</li>').join('')+'</ul>'+
    '</div>';
    applyBtn.disabled=true;
    applyBtn.textContent='Apply Redactions';
  }else if(flags.length){
    // FLAG — yellow banner, Apply enabled but relabelled
    panel.innerHTML='<div class="trigger-banner flag">'+
      '<h4>⚠️ Review flags</h4>'+
      '<ul>'+flags.map(t=>'<li>'+esc(t.message)+'</li>').join('')+'</ul>'+
    '</div>';
    applyBtn.disabled=false;
    applyBtn.textContent='Apply with flags';
  }
  // HIGHLIGHT-only or empty: no banner (rows already highlighted above)
}

function toggleLibSection(bodyId, headId){
  const body=document.getElementById(bodyId);
  const head=document.getElementById(headId);
  const collapsed=body.style.display==='none';
  body.style.display=collapsed?'block':'none';
  head.textContent=collapsed?'▼ (expanded)':'▶ (collapsed)';
}

function _renderSpanTable(items, showLibPrior){
  const showScore=items.some(s=>s.layer==='presidio');
  let rows='';
  items.forEach(s=>{
    const full=s.original_text||'';
    const orig=esc(full);
    const truncated=full.length>60?esc(full.slice(0,60))+'…':orig;
    const tier=s.score_tier;
    const rowCls=tier==='low'?' class="tier-low"':(tier==='medium'?' class="tier-medium"':
      (s.library_hit?' class="lib-row-hit"':''));
    const scoreNum=(typeof s.score==='number'?s.score.toFixed(2):'—');
    let scoreInner;
    if(tier==='low') scoreInner='<span style="color:#d97706">'+scoreNum+'</span><div style="font-size:10px;color:#9ca3af">⚠️ low confidence</div>';
    else if(tier==='medium') scoreInner='<span style="color:#2563eb">'+scoreNum+'</span>';
    else scoreInner='<span>'+scoreNum+'</span>';
    const scoreCell=showScore?'<td>'+scoreInner+'</td>':'';
    const priorCell=showLibPrior?
      '<td><span class="lib-prior '+(s.library_decision||'')+'">'
        +(s.library_decision==='confirm'?'✓ confirmed':s.library_decision==='reject'?'✗ rejected':'—')
        +' (×'+s.library_count+')</span></td>':'';
    rows+='<tr'+rowCls+' data-span-id="'+s.id+'">'+
      '<td class="mono">'+s.id+'</td>'+
      '<td class="orig mono" title="'+orig+'">'+truncated+'</td>'+
      '<td><span class="tok">'+esc(s.proposed_token||'')+'</span></td>'+
      scoreCell+priorCell+
      '<td><div class="act">'+
        '<label><input type="radio" name="dec-'+s.id+'" value="1"'+(s._dec?' checked':'')+
          ' onchange="setDec('+s.id+',true)"> ✓</label>'+
        '<label><input type="radio" name="dec-'+s.id+'" value="0"'+(!s._dec?' checked':'')+
          ' onchange="setDec('+s.id+',false)"> ✗</label>'+
      '</div></td>'+
    '</tr>';
  });
  const headers='<th style="width:40px">#</th><th>Original text</th><th>Proposed token</th>'+
    (showScore?'<th style="width:60px">Score</th>':'')+
    (showLibPrior?'<th style="width:120px">Prior decision</th>':'')+
    '<th style="width:90px">Action</th>';
  return '<table class="rv"><thead><tr>'+headers+'</tr></thead><tbody>'+rows+'</tbody></table>';
}

function setDec(id,val){
  const s=SPANS.find(x=>x.id===id);
  if(s){ s._dec=val; updateSummary(); }
}

function bulk_ids(ids,val){
  ids.forEach(id=>{
    const s=SPANS.find(x=>x.id===id);
    if(!s) return;
    s._dec=val;
    document.getElementsByName('dec-'+id).forEach(r=>{r.checked=(r.value==='1')===val;});
  });
  updateSummary();
}

function updateSummary(){
  const conf=SPANS.filter(s=>s._dec).length;
  const rej=SPANS.length-conf;
  document.getElementById('review-summary').textContent=conf+' confirmed · '+rej+' rejected';
}

function cancelReview(){
  document.getElementById('review-card').style.display='none';
  SPANS=[]; currentFilePath=null;
}

// ── Apply ───────────────────────────────────────────────────────────────────
function applyRedactions(){
  if(!currentFilePath) return;
  const decisions={};
  SPANS.forEach(s=>{ decisions[String(s.id)]=!!s._dec; });
  const btn=document.getElementById('apply-btn');
  btn.disabled=true; btn.textContent='Applying…';

  fetch('/api/apply-redactions',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({path:currentFilePath,decisions})})
  .then(r=>r.json()).then(d=>{
    btn.disabled=false; btn.textContent='Apply Redactions';
    if(!d.ok){ alert('Apply failed: '+(d.error||'unknown error')); return; }
    const card=document.getElementById('review-card');
    if(d.passed===false){
      const hits=(d.hits||[]).map(h=>'• <strong>'+esc(h.check)+'</strong>: '+esc(h.matched_text)).join('<br>');
      card.innerHTML=
        '<h2>Quarantined — Not Shippable</h2>'+
        '<div class="note">⚠️ Verification failed — the redacted output was withheld from the '+
          'document tree and quarantined in the private zone:<br>'+
          '<span class="mono">'+esc(d.quarantine_path||'')+'</span>'+
          (hits?('<br><br>Findings:<br>'+hits):'')+
        '</div>';
      card.style.display='block';
      SPANS=[]; currentFilePath=null;
      return;
    }
    card.innerHTML=
      '<h2>Redactions Applied</h2>'+
      '<div class="success">'+
        '✓ <strong>'+d.confirmed+'</strong> redaction'+(d.confirmed===1?'':'s')+' applied · '+
        '<strong>'+d.rejected+'</strong> rejected.<br><br>'+
        'Output written next to the source file:<br>'+
        '<span class="mono">'+esc(d.anon_path)+'</span><br>'+
        '<span class="mono">'+esc(d.audit_path)+'</span><br><br>'+
        'Need the original back? <a href="/restore">Open the Restore tool →</a>'+
      '</div>';
    card.style.display='block';
    SPANS=[]; currentFilePath=null;
  }).catch(()=>{
    btn.disabled=false; btn.textContent='Apply Redactions';
    alert('Apply request failed — server not responding.');
  });
}
</script>
</body>
</html>"""


@app.route("/anonymize", methods=["GET"])
def anonymize_page():
    return ANON_PAGE, 200, {"Content-Type": "text/html; charset=utf-8"}
@app.route("/api/list-in-process", methods=["GET"])
def list_in_process():
    """Return files and subfolders inside 05-In-Process, skipping _-prefixed entries."""
    root = SHAREPOINT / "05-In-Process"
    if not root.exists():
        return json.dumps({"ok": False, "error": "05-In-Process folder not found."}), 404, {"Content-Type": "application/json"}
    entries = []
    try:
        for item in sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            nm = item.name
            if nm.startswith("_") or nm.startswith("~$") or nm.lower() == "desktop.ini":
                continue
            try:
                import stat as _stat
                attrs = item.stat().st_file_attributes
                if attrs & (_stat.FILE_ATTRIBUTE_HIDDEN | _stat.FILE_ATTRIBUTE_SYSTEM):
                    continue
            except (AttributeError, OSError):
                pass
            entries.append({
                "name":   item.name,
                "path":   str(item.relative_to(SHAREPOINT)).replace("\\", "/"),
                "is_dir": item.is_dir(),
            })
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}), 500, {"Content-Type": "application/json"}
    return json.dumps({"ok": True, "entries": entries}), 200, {"Content-Type": "application/json"}


@app.route("/api/save-catalog", methods=["POST", "OPTIONS"])
def save_catalog():
    if request.method == "OPTIONS":
        return "", 204

    body     = request.get_json(force=True) or {}
    csv_text = body.get("csv", "")
    msg      = body.get("message") or f"Dashboard catalog update {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    if not csv_text.strip():
        return json.dumps({"ok": False, "output": "No CSV data received."}), 400, {"Content-Type": "application/json"}

    try:
        # Backup then overwrite
        if CSV_PATH.exists():
            shutil.copy2(str(CSV_PATH), str(CSV_PATH.with_suffix(".csv.bak")))
        CSV_PATH.write_text(csv_text, encoding="utf-8", newline="")

        # Stage
        r = subprocess.run(["git", "add", "contract-catalog.csv"],
                           cwd=str(TOOLS), capture_output=True, text=True)
        if r.returncode != 0:
            return json.dumps({"ok": False, "output": r.stderr}), 500, {"Content-Type": "application/json"}

        # Commit
        r = subprocess.run(["git", "commit", "-m", msg],
                           cwd=str(TOOLS), capture_output=True, text=True)
        if r.returncode != 0:
            nothing = "nothing to commit" in (r.stdout + r.stderr).lower()
            return json.dumps({"ok": nothing, "output": "No changes — catalog already up to date." if nothing else r.stderr}), \
                   200 if nothing else 500, {"Content-Type": "application/json"}

        # Push
        r = subprocess.run(["git", "push", "origin", "main"],
                           cwd=str(TOOLS), capture_output=True, text=True)
        ok = r.returncode == 0
        return json.dumps({"ok": ok, "output": (r.stdout + r.stderr).strip()}), \
               200 if ok else 500, {"Content-Type": "application/json"}

    except Exception as exc:
        return json.dumps({"ok": False, "output": str(exc)}), 500, {"Content-Type": "application/json"}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
