# Nightly Catalog Scan — Job Brief
**Version:** 1.2
**Created:** 2026-06-30
**Owner:** CAI (maintained at session close)
**Status:** APPROVED — see §Registration for one-time setup command.

---

## Purpose

Unattended nightly job that detects contract files added or modified in the
Salesforce Integration folder, appends new rows to `contract-catalog.csv`,
extracts PDF date metadata, commits, and pushes to dcs-contract-mgmt-tools.
Replaces the manual append workflow run in the 2026-06-29 session.

---

## Paths

| Name | Value |
|------|-------|
| SCAN ROOT | `C:\Users\jrudy\OneDrive - Diakonia Group, LLC\Salesforce Integration - Active Contracts` |
| CATALOG | `C:\Users\jrudy\OneDrive - Diakonia Group, LLC\Contract Management - SharePoint\Tools\contract-catalog.csv` |
| REPO | `C:\Users\jrudy\OneDrive - Diakonia Group, LLC\Contract Management - SharePoint\Tools` (dcs-contract-mgmt-tools) |
| LOG | `C:\Users\jrudy\OneDrive - Diakonia Group, LLC\Contract Management - SharePoint\Tools\DETECT_RUN_LOG.txt` |
| SCRIPT | `C:\Users\jrudy\OneDrive - Diakonia Group, LLC\Contract Management - SharePoint\Tools\nightly-catalog-scan.py` |

---

## Trigger condition

A file qualifies if **either** condition is true:
- `CreationTime >= RUN_DATE - 1 day` (new file)
- `LastWriteTime >= RUN_DATE - 1 day` (modified file)

`RUN_DATE` = the calendar date when the job runs (2:00 AM local).

---

## Exclusions

Skip any file where:
- Filename is `desktop.ini` or extension is `.ini`
- Any path component matches `\.claude` (hidden tool folders)
- Extension is not in `{.pdf, .docx, .doc, .msg}`

---

## Metadata derivation (per new row)

Columns derived the same way as the manual 2026-06-29 session:

| Column | Rule |
|--------|------|
| `ContractLocation` | Always `"01 Active Contracts"` |
| `VendorFolder` | Top-level folder name under SCAN ROOT |
| `Filename` | File's base name |
| `FilePath` | Relative to SCAN ROOT, forward slashes |
| `Extension` | Lowercase, with leading dot |
| `DocType` | Pattern-match against filename (MNDA/NDA/MSA/SOW/EULA/MPA/PO/AMEND/EULA…) |
| `HasSignedKeyword` | `True` if "signed"/"executed"/"fully executed" in filename |
| `SigningStatus` | `"Signed"` if HasSignedKeyword, else blank |
| `IsAmendment` | `True` if "amendment"/"amend"/"change order" in filename |
| `AmendmentNumber` | Numeric suffix after amendment keyword, if present |
| `VersionLabel` | `vN.N` pattern in filename, if present |
| `DateInFilename` | Best-effort parse: MM.DD.YYYY → YYYY.MM.DD → DD.MM.YY → M-D-YY/YYYY |
| `CounterpartyName` | Default to VendorFolder; override with PDF-extracted party name if high confidence |
| `EffectiveDate` | See §PDF Date Extraction |
| `ExpirationDate` | See §PDF Date Extraction |
| `DaysUntilExpiration` | `(ExpirationDate - today).days` if ExpirationDate populated, else blank |
| `Notes` | Trigger tag: `"new (created)"`, `"new (modified)"`, or `"new (created+modified)"` |
| `Status` | **Must never be blank.** `"active"` for executed/signed instruments. Low-confidence rows (ManualReview=True) still receive `"active"` (or the correct operative status) so they render in the dashboard and are visible for review. See §Status Invariant. |
| `SurvivalRunning`, `Stale`, `SurvivalEndDate`, `ManualReview`, `ManualReviewNote` | Blank unless set by PDF extraction confidence rules |

---

## §Never Trust Filesystem Dates

OneDrive rehydration sets `CreationTime` and `LastWriteTime` to the sync date,
not the document's actual date. This means:

- **`FileCreatedDate`** no longer exists — the column was dropped 2026-07-14
  precisely because it encoded a filesystem timestamp. Use `DateInFilename`.
- **`EffectiveDate` / `ExpirationDate`** must be sourced from PDF text content
  only — never from filesystem timestamps, file metadata, or OS stat() values.
- **Deduplication and change detection** use `FilePath` (stable) and content
  hashes if needed — never `CreationTime` or `LastWriteTime` for ordering or
  date population.

`DateInFilename` is the authoritative date signal for file-level dates.
PDF text content is the authoritative date signal for contract-term dates.

---

## §Status Invariant

`contract-catalog.html` defaults to `af.status = 'active'`; any row with a
blank `Status` is silently hidden from the default view and never rendered.

**Rule: every row the script writes must have a non-blank `Status`.**

| Condition | Status written |
|-----------|---------------|
| Filename contains "signed" / "executed" / "fully executed" | `"active"` |
| Filename contains "unsigned" or no signing signal | `"unsigned"` |
| Low-confidence PDF extraction (ManualReview=True) | `"active"` — still rendered; ManualReview flag drives the review queue |
| Audit-trail / non-operative copy (ManualReview=True, not a signed instrument) | `"reference"` |
| Any other new file where type is unclear | `"unsigned"` (conservative; renders in Unsigned filter) |

**Never write `Status = ""`.**

---

## §PDF Date Extraction

> **Filesystem dates are not contract dates.** See §Never Trust Filesystem Dates.
> All date extraction in this section operates on PDF text content only.

For each new non-excluded row, open the PDF with `pdfplumber` and search the
full text for contract term language.

### Target fields
- **EffectiveDate** — look for: `effective as of`, `commencement date`, `dated`,
  `entered into as of`, `entered into effect`, signature date block.
- **ExpirationDate** — look for: explicit end/expiration date; OR compute
  `EffectiveDate + N years/months` when the text states `"for a period of N…"` /
  `"initial term of N…"`.
- **DaysUntilExpiration** — compute from ExpirationDate if populated.

### Confidence handling

| Signal | Action |
|--------|--------|
| **High confidence** — explicit label (`"Effective Date"`, `"expires"`, `"expiration date"`) with a single clear date | Populate cell. Log source phrase to `DETECT_RUN_LOG.txt`. |
| **Low confidence** — inferred, ambiguous, or multiple candidate dates | Populate cell AND set `ManualReview = True`, `ManualReviewNote = "auto-extracted <field> low-confidence: '<source phrase>'"`. Log to `DETECT_RUN_LOG.txt`. |
| **Not found** | Leave cell blank. Append reason to `Notes`: `"effective-date-not-found"`, `"expiration-date-not-found"`, `"perpetual-no-expiration"`, `"term-auto-renew"`. |
| **No text layer** | Leave date cells blank. Append `"no-text-layer"` to `Notes`. (OCR is out of scope until E17 approved.) |

### Log format (DETECT_RUN_LOG.txt)
Append one block per run:

```
===== nightly-catalog-scan — YYYY-MM-DD HH:MM:SS =====
[CIRCUIT BREAKER PASS] N new files detected (threshold 17)
[SKIP] desktop.ini — excluded
[NEW] VendorFolder/Filename.pdf
  DateInFilename   : 2026-06-22
  EffectiveDate    : 2026-06-11  [HIGH]  source: 'entered into effect June 11, 2026 (the "Effective Date")'
  ExpirationDate   : (blank)  reason: term-per-project
[NEW] VendorFolder/Filename2.pdf
  EffectiveDate    : 2026-02-02  [HIGH]  source: 'effective as of the 2nd day of February 2026'
  ExpirationDate   : 2029-02-02  [HIGH]  source: 'three (3) years from the Effective Date'
  DaysUntilExpiration: 949
[COMMIT] abc1234  main  "nightly catalog scan 2026-06-30: +2 new rows"
[PUSH]  50c3a94..abc1234  main -> main
[FIRST AUTONOMOUS PUSH — confirm pipeline end-to-end at https://github.com/jrudyg/dcs-contract-mgmt-tools]
```

---

## §Circuit Breaker

**Abort threshold: > 17 new rows in a single run.**

Rationale: normal nightly delta is 0–3 files. More than 17 in one run indicates
a bulk OneDrive sync event, a date-range miscalculation, or an unexpected batch
upload — all scenarios where silent mass-commit is wrong.

**On trigger — preserve work, halt commit:**
1. Write the full proposed diff (all new rows that would have been appended) to
   `catalog-staged-YYYY-MM-DD.csv` alongside the catalog. This file survives to
   morning for manual review — the work is not discarded.
2. Log a structured block to `DETECT_RUN_LOG.txt`:
   ```
   [CIRCUIT BREAKER TRIPPED] 2026-07-01  N=23 rows detected — threshold 17
   Staged to: catalog-staged-2026-07-01.csv
   Vendors: LogistiQ Manufacturing (3), Williams Sonoma (7), Acme Corp (13)
   Action required: review staged file, then run --force if legitimate.
   ```
3. Do **not** write any rows to `contract-catalog.csv`.
4. Do **not** commit or push.
5. Exit non-zero so Task Scheduler History marks the run as needing attention.

**To override:** after confirming the batch is legitimate, run:
```
python nightly-catalog-scan.py --force
```
`--force` reads the staged file if present (skipping re-scan), applies rows,
commits, and pushes normally.

---

## §Registration

**Run once** in an elevated PowerShell session to register the nightly task.
The task runs at 2:00 AM, starts on next wake if the machine was asleep, and
runs whether or not a user is logged in.

```powershell
$toolsDir  = "C:\Users\jrudy\OneDrive - Diakonia Group, LLC\Contract Management - SharePoint\Tools"
$script    = Join-Path $toolsDir "nightly-catalog-scan.py"
$python    = (Get-Command python -ErrorAction Stop).Source
$pythonw   = Join-Path (Split-Path $python) "pythonw.exe"
$exe       = if (Test-Path $pythonw) { $pythonw } else { $python }
$taskName  = "DCS-NightlyCatalogScan"

$action   = New-ScheduledTaskAction -Execute $exe -Argument "`"$script`""
$trigger  = New-ScheduledTaskTrigger -Daily -At "02:00"
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances  IgnoreNew `
    -Hidden

Register-ScheduledTask `
    -TaskName   $taskName `
    -Action     $action `
    -Trigger    $trigger `
    -Settings   $settings `
    -RunLevel   Highest `
    -Force | Out-Null

Write-Host "Registered: $taskName (daily 02:00, run-on-wake, elevated)"
```

> **Note:** `RunLevel Highest` + no `-User`/`-Password` means the task runs as
> the current user's stored credentials. If the machine is domain-joined or the
> account requires a password for unattended runs, add
> `-User "$env:USERDOMAIN\$env:USERNAME" -Password "…"` or switch to a service
> account. Task Scheduler → `DCS-NightlyCatalogScan` → History tab confirms
> each nightly run result.

---

## Deduplication

A row is skipped if its `FilePath` already appears in the catalog
(case-insensitive match). No existing rows are modified.

---

## Commit & push protocol

1. `git add -- contract-catalog.csv` (explicit path; no other files staged).
2. Confirm only `contract-catalog.csv` is staged before committing. If any
   other tracked file appears staged or modified, abort:
   `[ABORT] unexpected staged/modified files — manual review required`.
3. Commit message: `"nightly catalog scan YYYY-MM-DD: +N new rows"`.
4. **Deploy guard (mandatory before every autonomous push):**
   Read `.github/workflows/azure-static-web-apps-mango-forest-02de1020f.yml`
   and confirm `skip_app_build: true` is present. If the line is missing or
   reads `false`, abort the push and log:
   `[DEPLOY GUARD MISSING — push aborted]`
   then exit non-zero. Do not push under any circumstance until the guard is
   restored manually.
5. `git push origin main` — no force, no tags.
6. On the **first successful autonomous push**, append to log:
   `[FIRST AUTONOMOUS PUSH — confirm pipeline end-to-end at https://github.com/jrudyg/dcs-contract-mgmt-tools]`

---

## Implementation note

`nightly-catalog-scan.py` was built and committed on 2026-06-30.

- **Introducing commit:** `9ba0142` — *Add nightly-catalog-scan.py: autonomous nightly contract catalog scanner*
- Standalone script (not a wrapper of `scan-contract.py`); uses `pdfplumber` for PDF text extraction.
- Implements all v1.2 spec sections: §Circuit Breaker, §Status Invariant, §Never Trust Filesystem Dates, §PDF Date Extraction, §Commit & push protocol.
- Includes 6-digit dotted-date disambiguation (`_resolve_six_digit_dotted`): NN.NN.NN patterns in filenames and PDF text are never silently guessed; ambiguous cases set `ManualReview=True` and emit `[DATE-AMBIGUOUS]` to the log.
- To register as a nightly scheduled task, see §Registration.

---

## Version history

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-06-30 | Initial — drawn from 2026-06-29 manual session |
| 1.1 | 2026-06-30 | **Delta 1:** circuit breaker threshold >50 → **>7**. **Delta 2:** PDF date extraction added to scope (EffectiveDate/ExpirationDate/DaysUntilExpiration, confidence tiers, DETECT_RUN_LOG phrases). **Delta 3:** §Registration command added; first-push flag added to log format. |
| 1.2 | 2026-06-30 | **Delta 1:** circuit breaker threshold **>7 → >17**; trip behavior changed — work is now preserved to `catalog-staged-YYYY-MM-DD.csv` (not discarded); log block includes vendor list. **Delta 2:** §Status Invariant added — Status must never be blank; low-confidence rows still get `"active"`. **Delta 3:** §Never Trust Filesystem Dates added; `FileCreatedDate` rule updated to never use `CreationTime`; §PDF Date Extraction cross-references new section. **Delta 4:** deploy guard made mandatory in §Commit & push protocol — abort + `[DEPLOY GUARD MISSING]` log if `skip_app_build: true` is absent or changed. |
| 1.3 | 2026-06-30 | §Implementation note updated: script delivered at commit `9ba0142`. 6-digit dotted-date disambiguation added to script (NN.NN.NN → ManualReview flag + `[DATE-AMBIGUOUS]` log, never silent guess). |
