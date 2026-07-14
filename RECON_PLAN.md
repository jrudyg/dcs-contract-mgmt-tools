# RECON PLAN — Phase 3, Step 4

**Date:** 2026-07-14
**Repo:** `dcs-contract-mgmt-tools`
**Status:** ⛔ **PAUSE POINT.** Steps 1–3 are done (below). Nothing in Step 4 has been executed — no file moved, no row added or deleted.
**Per-item detail:** `RECON_PLAN.csv` (one row per uncatalogued file, with proposed action).

---

## Steps 1–3 — done

| Step | Outcome |
|---|---|
| **1 — S-5 restore** | ❌ **BLOCKED — I cannot do this. See below.** |
| **2 — CounterpartyName repairs** | ✅ 9 rows fixed + scanner bug fixed at source + a durability fix |
| **3 — FileCreatedDate drop** | ✅ Column removed (24 → 23), all readers swept |

### Step 1 is blocked and needs you

I deleted those files in Phase 2 with `os.remove`, which on Windows **bypasses the Recycle Bin**. I verified: the local Recycle Bin has 0 matches, and no byte-identical copy (`629dafda…`) exists anywhere on disk. The only surviving copy is in the **SharePoint site recycle bin**, which is web-only — I have no authenticated path to it (the Microsoft 365 connector isn't authenticated, and it wouldn't expose recycle-bin restore anyway).

**To restore it:** SharePoint site → Recycle bin → `Mutual NDA- Associated Packaging.docx`, deleted 2026-07-14 from `02 Unsigned Contracts/CTM Labeling`. Restore it, tell me, and I'll verify the SHA-256, rename it `Mutual NDA - Associated Packaging - draft variant.docx`, file it under `Associated Packaging`, and add the flagged row exactly as the brief specifies.

*(Lesson recorded for future phases: deletions in this repo must use `send2trash` or a quarantine folder, never `os.remove`.)*

### Step 2 — what was actually wrong, and a second bug it exposed

The DocuSign pollution was not a data-entry slip; it was a scanner bug. A **"Certificate Of Completion" page has no "by and between" clause**, so every party-clause strategy in `extract_counterparty()` misses and execution falls through to Strategy 4, an entity-suffix scan with a 60-character lookback — which scoops the signer's job title in with the company name. Fixed at source: certificate pages are now detected and routed straight to the vendor-folder fallback (`scan-contract.py`, `_DOCUSIGN_CERT_RE`). Verified against all three real certificates.

**Then I found the fix wouldn't have held.** Unlike `SigningStatus`, `CounterpartyName` had **no permanence rule** — any `scan-contract.py --all` overwrites it. Your nine hand-curated legal names would have been silently reverted on the next scan, making Step 2 cosmetic. `CounterpartyName` is now **fill-only** (never overwrites a non-blank value), with `--recheck-counterparty` to force re-extraction — mirroring the existing `--recheck-signing` pattern. Documented in `CLAUDE.md`.

Names were read from the documents themselves: `Connors & Associates, LLC` (d/b/a Connors Group), `ScanSource, Inc`, `Clearpath Robotics, Inc.`, `Körber Supply Chain LLC`.

### Step 3 — the column deserved to die

`FileCreatedDate` was populated from `st_ctime`, which on a OneDrive-synced library reports the **rehydration date, not the document date** — the exact failure `NIGHTLY_CATALOG_JOB.md` warns about under "Never Trust Filesystem Dates." Its values were sync artifacts. Dropped from the CSV and from `audit-catalog.py`, `nightly-catalog-scan.py` (4 sites + a dangling variable), `CLAUDE.md`, `kb/DATA_DICTIONARY.md`, and `NIGHTLY_CATALOG_JOB.md`. `index.html`, `server.py`, and `sync-sor.py` never read it. All four scripts compile and dry-run clean.

---

## ⚠️ Before anything else: do not run `audit-catalog.py` without `--dry-run`

The brief's input numbers (68 / 3 / 14) come from `audit-catalog.py`. **Two of the three are artifacts of how that script works, and running it unguarded would corrupt data.**

`audit-catalog.py` matches disk files to rows by `FilePath` **alone, ignoring `ContractLocation`**. When the same relative path exists in two locations, it walks both: the first sets the row OK, the second sees `csv_loc != loc` and — in a non-dry-run — **rewrites `ContractLocation` to whichever location it happened to walk last.** So:

- The **"14 location mismatches" are not mismatches.** Zero rows point at a location where the file does not exist. They are the visible edge of 27 files that physically exist in *two* locations at once.
- The **"68 orphans"** undercounts (it never walks `04 Expired`) and would be blind-added as rows, including duplicate copies.

Left unguarded, that one command would flip 14 rows' location by directory-walk order and add ~68 rows, several of them duplicates. **It should not be run until this plan is executed.**

---

## Ground truth (re-derived from disk, not from audit's counters)

| Category | Count | Proposed |
|---|---|---|
| **A.** Uncatalogued files needing a row | **58** | ADD-ROW |
| **B.** Files physically present in 2+ locations | **27** (26 byte-identical) | Delete the stale copy |
| **C.** Catalog rows whose file is missing | **3** | **All 3 repoint — none deleted** |
| **D.** Non-active rows sitting in `01 Active` | **11** | Refile / reclassify |
| **E.** Uncatalogued files that should NOT get a row | **5** | EXCLUDE, with reason |

### And the finding that reframes Phase 2

**Phase 2 de-duplicated the *catalog*. The *disk* is still full of duplicates.** A content-hash sweep of all four locations finds:

> **36 byte-identical duplicate sets, 83 file instances, 47 redundant copies still on disk.**

Phase 1 derived its 35 groups from catalog rows, so any duplicate whose copies were *uncatalogued* was invisible to it. That's why `SVT` / `SVT Robotics`, `Trinity Controls` / `Trinity Solutions`, `Geek+` / `GeekPlus Robotics`, `Schmalz` / `Schmalz, Inc`, `Camping World` / `GWGS Group`, and `Shipmonk` / `ShipMonk` all survived — they are exactly the alias-pair pattern Phase 2 merged, but the catalog never knew they existed.

**Recommendation: dedup by content hash over the disk, not by filename over the catalog.** That is the axis that actually finds them.

---

## Category B — 27 files in two locations at once (root cause identified)

26 of 27 are **byte-identical**; 21 of those are `01 Active` ↔ `04 Expired`.

**`CONTRACT-RULES.md:129` records: "92 NDAs/MNDAs previously moved to 04 Expired in error were restored to 01 Active."** That restore evidently **copied instead of moved**, leaving a byte-identical twin behind in `04 Expired`. `04 Expired` is now largely a stale shadow of `01 Active` — it holds only 9 catalog rows but far more files.

**Proposed:** delete the `04 Expired` copy, keep `01 Active` (the restore was the deliberate corrective action; the copy left behind is the error). Same logic for `02`↔`03` pairs — keep the copy matching the catalogued location.

**The one exception — needs your call:** `Brock Solutions/Brock_Solutions_NDA_Signed.pdf` exists in `01 Active` (`881d0653`) and `02 Unsigned` (`f7ca9f4d`) with **different bytes**, and **neither copy has a catalog row**. Two different versions of the same NDA, and I can't tell which is authoritative from the documents alone.

---

## Category C — the 3 "missing" rows all resolve to repoints

None should be deleted. Each has a clear successor on disk:

| Missing row (`01 Active`) | Evidence | Proposed |
|---|---|---|
| `DCS-TA-5611-GSESC-Amendment 1 - FE.pdf` (root, no vendor folder) | Same filename now at `GDIT/DCS-TA-5611-GSESC-Amendment 1 - FE.pdf` | **Repoint** row → `GDIT/…` |
| `GDIT_GSESC_IDIQ_No_00936_Revision_No_1_.pdf` (root) | Same filename now at `GDIT/GDIT_GSESC_IDIQ_No_00936_Revision_No_1_.pdf` | **Repoint** row → `GDIT/…` |
| `McKesson/McKesson_DCS_MNDA_REDLINED 05.26.26.docx.pdf` | The redline was superseded: `McKesson/McKesson_DCS_MNDA_Executed 05.26.26.docx.pdf` exists (uncatalogued, MNDA, **Signed**) | **Repoint** row → the Executed file; set `SigningStatus=Signed`, `Status=active` |

The first two are just files that were tidied into a `GDIT/` vendor folder while the rows kept pointing at the library root.

---

## Category D — 11 non-active rows in `01 Active`

**5 expired → propose moving to `04 Expired`:** Henkel (exp 2023-06-15), Joshua Tree Group (2025-03-05), LGEUS (2024-02-25), Regal Beloit (2026-04-06), TE Connectivity (2025-04-13).

**3 DocuSign certificates** (`Connors Group`, `McKesson`, `ScanSource`) carry `Status=archived/Review` but are **e-signature artifacts of active agreements**, not contracts. Moving them would separate them from the contract they evidence. **Propose: keep in place next to their parent contract**, and give them a `DocType=Certificate` so they stop being scored as contracts. Needs your decision.

**Leave alone:** `QVC` (`Status=renewed`, expires 2026-09-30 — genuinely current), `ScanSource_-_DATUM_Prop_Final` (a proposal, correctly archived-in-place). The **McKesson redline** is resolved by Category C.

---

## Category E — 5 files proposed for EXCLUDE (no row)

| File | Reason |
|---|---|
| `01 · ISM/Effective Contracting - ISM 05.14.26.pdf` | Training course material, not a contract |
| `01 · Williams Sonoma/DATUM EULA 06.12.2026 - Clean - audit.pdf` | "- audit" working copy of an already-catalogued EULA |
| `01 · Williams Sonoma/WSI-DCS EXHIBIT A.2 SOW 26.06.22 CLEAN - audit.pdf` | "- audit" working copy |
| `03 · ACI Licenses/AL Contractor License.pdf` | Contractor license certificate, not a contract |
| `03 · Nationwide Services/Nationwide Svcs FL Contractor Lic thru 8-31-26.pdf` | Contractor license certificate |

If you'd rather catalogue licenses as a `DocType=License`, say so — they're a real category, just not contracts.

---

## Category A — 58 rows to add

Full per-item proposals (DocType, counterparty, signing status, effective date) are in **`RECON_PLAN.csv`**. Extraction came from the document text, not the filename.

**9 of the 58 have an unreliable auto-extracted counterparty and need manual entry** — flagged `COUNTERPARTY UNRELIABLE` in the CSV. They fail the same way the DocuSign certs did, but from a different direction: these are letter agreements and subcontracts where the party clause is a signature block, so the extractor grabs `"the undersigned Subcontractor"`, `"Carl Brewer Vice President, Di…"`, `"Mr. Josef Mentzer President &…"`. My Step 2 fix covers certificate pages only; **this is a second, distinct extraction weakness and I have not fixed it** — the safe move is manual entry for those 9 rather than a speculative regex.

Also worth flagging: **`NFI/` is being used as a dumping ground.** It contains a Ventura Foods NDA and a FARO NDA, both byte-identical to copies correctly filed under `Ventura Foods/` and `Faro/`. Those are wrong-vendor misfiles (Phase 2's Category B pattern), not new contracts — they should be deleted, not catalogued.

---

## Decisions needed

1. **Category B keep-rule** — delete the `04 Expired` twin and keep `01 Active`, per the 92-NDA restore history? And what do you want for **Brock Solutions** (two different versions, no row for either)?
2. **Scope** — do you want me to fix the *whole* 47-copy disk duplicate problem in Step 5, or only the 27 cross-location pairs the brief anticipated? (Recommend the whole sweep — the rest will keep resurfacing.)
3. **DocuSign certificates** — keep beside their parent contract with `DocType=Certificate`, or refile?
4. **Licenses** — EXCLUDE, or catalogue as `DocType=License`?
5. **The 9 unreliable counterparties** — do you want to supply the names, or should I add the rows with `CounterpartyName` blank and `ManualReview=True`?

Nothing moves until you answer.
