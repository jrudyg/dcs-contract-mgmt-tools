# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Deployment

The dashboard (`index.html` + `contract-catalog.csv`) is served from **Azure Static Web Apps** at `https://mango-forest-02de1020f.7.azurestaticapps.net`. Changes to local files **do not go live until committed and pushed to `main`**, which triggers the GitHub Actions pipeline (`.github/workflows/azure-static-web-apps-mango-forest-02de1020f.yml`). Always push after editing any file that affects the live dashboard.

GitHub remote: `https://github.com/jrudyg/dcs-contract-mgmt-tools.git`

---

## Common Commands

```powershell
# Scan one contract
python scan-contract.py "VendorFolder/filename.pdf"

# Scan all contracts for a vendor
python scan-contract.py --vendor "Terracon"

# Scan entire catalog
python scan-contract.py --all

# Remove catalog rows whose files no longer exist on disk
python scan-contract.py --prune

# Scan + prune in one pass
python scan-contract.py --all --prune

# Preview any command without writing
python scan-contract.py --all --dry-run

# Reconcile disk vs catalog (add orphan files, fix misplaced rows)
python audit-catalog.py
python audit-catalog.py --dry-run

# Move files to correct folders based on SigningStatus
python sort-contracts.py
python sort-contracts.py --dry-run

# Start the web scan UI (normally auto-started at login)
python server.py    # → http://localhost:5000

# Register server.py as a Windows auto-start task
powershell -File install-autostart.ps1
```

---

## Architecture

### Data flow

```
Contract files on disk (01 Active / 02 Unsigned / 03 Archived)
        ↓
  scan-contract.py  ← extracts metadata via PyMuPDF + python-docx
        ↓
contract-catalog.csv  ← single source of truth for all metadata
     ↓           ↓
sort-contracts.py    server.py (Flask, port 5000)
(moves files)        (web UI → spawns scan-contract.py via subprocess + SSE)
        ↓
audit-catalog.py  ← reconciles disk vs CSV; run after any manual reorganization
```

### contract-catalog.csv

The CSV is the system's only database. Written with `QUOTE_ALL` quoting. Every write creates a `.bak` backup first. Columns: `ContractLocation, VendorFolder, Filename, FilePath, Extension, FileCreatedDate, DocType, HasSignedKeyword, SigningStatus, IsAmendment, AmendmentNumber, VersionLabel, DateInFilename, CounterpartyName, EffectiveDate, ExpirationDate, Notes`.

`FilePath` is relative to the `ContractLocation` folder (e.g., `Terracon/Terracon_DCS MNDA 06.02.25 - signed.pdf`).

### scan-contract.py

Core path constants (all relative to `__file__`):
- `SCRIPT_DIR` = `Tools/`
- `SHAREPOINT` = `SCRIPT_DIR.parent` = the SharePoint root
- `DEFAULT_CSV` = `SCRIPT_DIR / "contract-catalog.csv"`

**Signing permanence rule**: Once `SigningStatus` is `Signed` or `Unsigned`, the scanner never overwrites it. Only `Review` is mutable. Use `--recheck-signing` to force re-evaluation (one-time migration use only).

**Signature detection strategy** (in order): DocuSign envelope timestamps → Adobe Sign certificate page → PandaDoc markers → filled `By:` blocks with real names → `/s/` electronic markers. Scanned/image PDFs (<50 chars extracted) are flagged `Review`.

**DocType detection**: Regex against the first 500 characters of the document text.

### server.py

Checks port 5000 on startup and exits silently if already running (prevents duplicate instances). Scan requests stream output line-by-line as Server-Sent Events (SSE). CORS is open (`*`).

### index.html (dashboard)

Fetches `contract-catalog.csv` from the same directory using a cache-busting `?t=Date.now()` query parameter. When opened as a `file://` URL, fetch is blocked by the browser — the dashboard must be accessed via the Azure URL or via `server.py`. The `exportHTML()` admin function embeds the current DATA array into the HTML source for offline use — if a previously exported HTML is opened, the embedded `const DATA` will be stale.

SharePoint file links are built by `spUrl()` using the configurable base URL stored in `#sp-base` (default: `https://diakoniagroupllc.sharepoint.com/sites/ContractManagement/Shared%20Documents`).

---

## Classification Rules

Defined authoritatively in `CONTRACT-RULES.md`. Key points:

| Folder | Condition |
|--------|-----------|
| `01 Active Contracts` | `Signed` + not expired |
| `02 Unsigned Contracts` | `Unsigned` + not expired |
| `03 Archived Contracts` | Human decision only — never auto-moved |

`sort-contracts.py` always skips: files in Archived, files with no `SigningStatus`, VendorFolder starting with `00 ` or containing "template", filenames containing "template" or "redline".

Run `scan-contract.py --prune` after any batch file deletion or reorganization to remove orphaned catalog rows.
