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
from datetime import datetime
from pathlib import Path
from flask import Flask, Response, request
from werkzeug.utils import secure_filename

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
