"""
DCS Contract Scanner — local background server.
Auto-started silently at Windows login via install-autostart.ps1.
Scan UI: http://localhost:5000
"""

import socket
import sys
import json
import csv
import subprocess
from pathlib import Path
from flask import Flask, Response, request

# ── Exit immediately if already running on port 5000 ────────────────────────
_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
_s.settimeout(1)
if _s.connect_ex(("127.0.0.1", 5000)) == 0:
    _s.close()
    sys.exit(0)
_s.close()

# ── Paths ────────────────────────────────────────────────────────────────────
TOOLS      = Path(__file__).resolve().parent
SHAREPOINT = TOOLS.parent
SCAN_SCRIPT = TOOLS / "scan-contract.py"
CSV_PATH    = TOOLS / "contract-catalog.csv"

app = Flask(__name__)

# ── CORS (allows calls from any origin, including file://) ──────────────────
@app.after_request
def _cors(r):
    r.headers["Access-Control-Allow-Origin"]  = "*"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    r.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return r

# ── Scan UI page ─────────────────────────────────────────────────────────────
SCAN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DCS Contract Scanner</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f3f4f6;color:#111827;min-height:100vh;padding:32px 16px}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:28px;max-width:760px;margin:0 auto 20px}
h1{font-size:20px;font-weight:700;margin-bottom:4px}
.sub{font-size:13px;color:#6b7280;margin-bottom:24px}
label{font-size:13px;color:#374151;display:block;margin-bottom:4px;font-weight:500}
.hint{font-size:12px;color:#9ca3af;margin-bottom:8px}
.modes{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:20px}
.modes label{display:flex;align-items:center;gap:7px;font-weight:400;cursor:pointer}
textarea,input[type=text],select{
  width:100%;background:#f9fafb;border:1px solid #d1d5db;border-radius:8px;
  padding:9px 12px;font-size:13px;color:#111827;font-family:inherit;outline:none;transition:border-color .15s}
textarea{min-height:80px;resize:vertical;font-family:monospace;font-size:12px;line-height:1.5}
textarea:focus,input:focus,select:focus{border-color:#6366f1}
.row{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-top:16px}
.chk{display:flex;align-items:center;gap:7px;font-size:13px;color:#374151;cursor:pointer;font-weight:400}
button.primary{background:#6366f1;color:#fff;border:none;border-radius:8px;padding:9px 22px;font-size:13px;font-weight:600;cursor:pointer;transition:background .15s}
button.primary:hover{background:#4f46e5}
button.primary:disabled{background:#a5b4fc;cursor:not-allowed}
button.ghost{background:transparent;border:1px solid #d1d5db;color:#374151;border-radius:8px;padding:9px 16px;font-size:13px;cursor:pointer}
button.ghost:hover{background:#f3f4f6}
#status{font-size:12px;color:#9ca3af}
.log-card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:24px;max-width:760px;margin:0 auto;display:none}
.log-card h2{font-size:15px;font-weight:600;margin-bottom:12px}
#log{background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px 14px;font-family:monospace;font-size:12px;line-height:1.6;max-height:480px;overflow-y:auto;white-space:pre-wrap;color:#111827}
</style>
</head>
<body>
<div class="card">
  <h1>DCS Contract Scanner</h1>
  <p class="sub">Extracts signing status, document type, parties, and dates — updates contract-catalog.csv.</p>

  <div class="modes">
    <label><input type="radio" name="mode" value="files" checked onchange="modeChange()"> Files</label>
    <label><input type="radio" name="mode" value="vendor" onchange="modeChange()"> By Vendor</label>
    <label><input type="radio" name="mode" value="location" onchange="modeChange()"> By Location</label>
    <label><input type="radio" name="mode" value="all" onchange="modeChange()"> All Contracts</label>
  </div>

  <div id="in-files">
    <label>File paths <span class="hint">(one per line, relative to SharePoint root)</span></label>
    <textarea id="files-val" placeholder="Disney/Disney-PSA-11.14.2025.pdf&#10;6sense/6sense-dcs-MNDA-10.31.2024.pdf"></textarea>
  </div>

  <div id="in-vendor" style="display:none">
    <label>Vendor name <span class="hint">(partial match OK)</span></label>
    <input type="text" id="vendor-val" list="vendor-list" placeholder="Disney, ACI Licenses, Nationwide…">
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

  <div id="in-all" style="display:none">
    <p style="font-size:13px;color:#d97706;background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:10px 14px">
      ⚠️ Scans all contracts in the catalog — may take several minutes.
    </p>
  </div>

  <div class="row">
    <label class="chk"><input type="checkbox" id="dry-run"> Dry run (preview only, don't save)</label>
    <button class="primary" id="scan-btn" onclick="scan()">🔍 Scan</button>
    <button class="ghost" id="clear-btn" onclick="clearLog()" style="display:none">Clear</button>
    <span id="status"></span>
  </div>
</div>

<div class="log-card" id="log-card">
  <h2>Output</h2>
  <div id="log"></div>
</div>

<script>
function modeChange(){
  const m=document.querySelector('input[name=mode]:checked').value;
  ['files','vendor','location','all'].forEach(k=>{
    document.getElementById('in-'+k).style.display=k===m?'block':'none';
  });
}

// Load vendor list
fetch('/api/vendors').then(r=>r.json()).then(vs=>{
  const dl=document.getElementById('vendor-list');
  vs.forEach(v=>{const o=document.createElement('option');o.value=v;dl.appendChild(o);});
}).catch(()=>{});

function clearLog(){
  document.getElementById('log').textContent='';
  document.getElementById('log-card').style.display='none';
  document.getElementById('clear-btn').style.display='none';
  document.getElementById('status').textContent='';
}

function scan(){
  const mode=document.querySelector('input[name=mode]:checked').value;
  const dry_run=document.getElementById('dry-run').checked;
  const body={mode,dry_run};

  if(mode==='files'){
    const raw=document.getElementById('files-val').value.trim();
    if(!raw){alert('Enter at least one file path.');return;}
    body.files=raw.split(/\\r?\\n/).map(s=>s.trim()).filter(Boolean);
  } else if(mode==='vendor'){
    const v=document.getElementById('vendor-val').value.trim();
    if(!v){alert('Enter a vendor name.');return;}
    body.vendor=v;
  } else if(mode==='location'){
    body.location=document.getElementById('location-val').value;
  }

  const log=document.getElementById('log');
  const logCard=document.getElementById('log-card');
  const btn=document.getElementById('scan-btn');
  const status=document.getElementById('status');

  log.textContent='';
  logCard.style.display='block';
  document.getElementById('clear-btn').style.display='none';
  btn.disabled=true;
  btn.textContent='Scanning…';
  status.textContent='';

  function done(rc){
    btn.disabled=false;
    btn.textContent='🔍 Scan';
    document.getElementById('clear-btn').style.display='inline-block';
    log.textContent+='\\n'+(rc===0?'-- done --':'-- finished with errors (exit '+rc+') --')+'\\n';
    status.textContent=rc===0?'Done':'Errors';
    log.scrollTop=log.scrollHeight;
  }

  fetch('/api/scan',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)
  }).then(resp=>{
    const reader=resp.body.getReader();
    const dec=new TextDecoder();
    let buf='';
    function read(){
      return reader.read().then(({done:d,value})=>{
        if(d)return done(0);
        buf+=dec.decode(value,{stream:true});
        const parts=buf.split('\\n\\n');
        buf=parts.pop();
        for(const chunk of parts){
          if(!chunk.startsWith('data: '))continue;
          const pay=chunk.slice(6);
          try{
            const obj=JSON.parse(pay);
            if(obj&&obj.__done__!==undefined)return done(obj.rc);
            log.textContent+=(typeof obj==='string'?obj:JSON.stringify(obj))+'\\n';
          }catch{log.textContent+=pay+'\\n';}
          log.scrollTop=log.scrollHeight;
        }
        return read();
      });
    }
    return read();
  }).catch(()=>{
    log.textContent+='[ERROR] Server not responding.\\n';
    done(1);
  });
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
        return json.dumps({"error": "contract-catalog.csv not found"}), 404, {"Content-Type": "application/json"}
    return json.dumps(sorted(seen, key=str.lower)), 200, {"Content-Type": "application/json"}


@app.route("/api/scan", methods=["POST", "OPTIONS"])
def scan():
    if request.method == "OPTIONS":
        return "", 204

    body     = request.get_json(force=True) or {}
    mode     = body.get("mode", "files")
    files    = body.get("files", [])
    vendor   = body.get("vendor", "")
    location = body.get("location", "")
    dry_run  = body.get("dry_run", False)

    args = [sys.executable, str(SCAN_SCRIPT)]
    if mode == "all":
        args.append("--all")
    elif mode == "vendor" and vendor:
        args += ["--vendor", vendor]
    elif mode == "location" and location:
        args += ["--location", location]
    elif mode == "files" and files:
        args += files
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
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            for line in proc.stdout:
                yield f"data: {json.dumps(line.rstrip())}\n\n"
            proc.wait()
            yield f"data: {json.dumps({'__done__': True, 'rc': proc.returncode})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps(f'[ERROR] {exc}')}\n\n"
            yield f"data: {json.dumps({'__done__': True, 'rc': 1})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
