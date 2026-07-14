# RECON EXECUTION REPORT — Phase 3

**Date:** 2026-07-14
**Repo:** `dcs-contract-mgmt-tools`
**Preceded by:** `RECON_PLAN.md` (Step 4, human-approved), `DEDUP_EXECUTION_REPORT.md` (Phase 2)

**Approvals applied:** full disk-wide dedup sweep · keep `01 Active`, delete the twin · certificates stay in place as `DocType=Certificate` · unreliable counterparties added blank with `ManualReview=True`.

---

## Result

| | Before Phase 3 | After |
|---|---|---|
| Catalog rows | 785 | **827** |
| Catalog columns | 24 | **23** (`FileCreatedDate` dropped) |
| Byte-identical duplicate sets on disk | **36** | **2** (both deliberately deferred) |
| Redundant duplicate copies on disk | 47 | **2** |
| Uncatalogued files | 73 | **0** (50 rows added, 5 logged exclusions, rest were duplicates) |
| Catalog rows pointing at a missing file | 3 | **0** |
| `scan-contract.py --prune` orphan count | 3 | **0** |

**Every governed file on disk now has a catalog row or a logged exclusion. Every catalog row resolves to a real file. No duplicate `FilePath` values.**

---

## What was done

**Steps 1–3** (pre-approved): `FileCreatedDate` dropped from the schema and swept out of `audit-catalog.py`, `nightly-catalog-scan.py` (4 sites + a dangling variable), `CLAUDE.md`, `kb/DATA_DICTIONARY.md`, `NIGHTLY_CATALOG_JOB.md`. Nine `CounterpartyName` values repaired from the documents themselves. Two scanner bugs fixed (below). **Step 1 (S-5 restore) remains blocked — see Open Items.**

**Step 5 — disk-wide dedup:** 34 of 36 duplicate sets auto-resolved, **45 redundant copies removed**. 2 sets deferred (below).

**Quarantine, not deletion.** Learning from Phase 2, nothing was `os.remove`d. All 45 copies were **moved** to `_quarantine-2026-07-14-dedup/`, preserving their location/vendor path, with a manifest recording each file's SHA-256, size, and which surviving copy supersedes it. Everything is recoverable without touching a recycle bin. **Delete that folder once you're satisfied.**

**Catalog reconciliation:** 8 rows dropped (their file was a duplicate copy), 14 rows repointed to the surviving copy, 50 rows added for previously-uncatalogued files, 5 files excluded with a logged reason, 3 certificates tagged `DocType=Certificate`, 31 folders emptied by the sweep removed.

**The 3 "missing" rows were all repoints, not deletions** — exactly as the plan predicted. Two GDIT files had been tidied into a `GDIT/` vendor folder while their rows still pointed at the library root. The third, the McKesson redline, had been superseded by `McKesson_DCS_MNDA_Executed 05.26.26.docx.pdf`, which was sitting on disk uncatalogued; that row now points at the executed version with `SigningStatus=Signed`.

---

## The two scanner bugs behind Step 2

**1. DocuSign certificate pages poisoned `CounterpartyName`.** A "Certificate Of Completion" page has no "by and between" clause, so every party-clause strategy in `extract_counterparty()` missed and execution fell through to Strategy 4 — an entity-suffix scan with a 60-character lookback that swept the signer's **job title** in with the company (`"Chief Operating Officer CONNORS AND ASSOCIATES, LLC"`). Certificate pages are now detected (`_DOCUSIGN_CERT_RE`) and routed straight to the vendor-folder fallback.

**2. The fix would not have held.** Unlike `SigningStatus`, `CounterpartyName` had **no permanence rule** — any `scan-contract.py --all` overwrote it. The nine curated legal names would have been silently reverted on the next scan, making Step 2 cosmetic. `CounterpartyName` is now **fill-only**, with `--recheck-counterparty` to force re-extraction, mirroring the existing `--recheck-signing` pattern.

**A third weakness remains unfixed, deliberately.** Signature-block documents (letter agreements, subcontracts) fail the same way from a different direction — the extractor returns `"the undersigned Subcontractor"`, `"Mr. Josef Mentzer President &…"`. Rather than guess with a speculative regex, the **9 affected rows were added with `CounterpartyName` blank and `ManualReview=True`.** The fill-only rule means whatever you enter will not be overwritten. They are the rows to work through next.

---

## Root causes found (both were structural, not clerical)

**The 04 Expired shadow.** `CONTRACT-RULES.md:129` records that 92 NDAs were "restored" from `04 Expired` to `01 Active`. **That restore copied instead of moving**, leaving a byte-identical twin behind in `04 Expired` — 21 of the 27 cross-location duplicates. `04 Expired` had become a stale shadow of `01 Active`. It is now clean, though it still contains **~100 empty vendor folders** left by that same operation (untouched — they hold nothing, and removing them is a filing decision, not a data one).

**Phase 2 deduplicated the catalog, not the disk.** Phase 1 derived its 35 groups from catalog rows, so any duplicate whose copies were *uncatalogued* was invisible to it. That is why `SVT`/`SVT Robotics`, `Trinity Controls`/`Trinity Solutions`, `Geek+`/`GeekPlus Robotics`, `Schmalz`/`Schmalz, Inc`, `Hunter Douglas`/`Hunter-Douglas`, `BATO`/`Bridgestone`, `AAFES`/`Army & Air Force Exchange Service`, `MHS`/`Fortna`, `Camping World`/`GWGS Group` and `ShipMonk`/`Shipmonk` all survived it. **Dedup must run on content hashes over the disk, not filenames over the catalog.** That is how this phase found them, and it is the check worth keeping.

**Every survivor was chosen by reading the counterparty out of the document**, not from the folder or filename — recorded per-set in `RECON_DEDUP_DECISIONS.csv`. That is what caught `NFI/` being used as a dumping ground (it held a Ventura Foods NDA and a FARO NDA, both byte-identical to correctly-filed copies) and `Mosimtec/` holding a Walt Disney NDA.

---

## ⚠️ `audit-catalog.py` is still unsafe to run unguarded

It matches disk files to rows by `FilePath` **ignoring `ContractLocation`**. When the same relative path existed in two locations it would rewrite the row's location to **whichever it walked last** — the "14 location mismatches" in the brief were this artifact, not real mismatches. The duplicates that triggered it are now gone, so the immediate hazard is resolved, **but the flawed matching logic is still in the script.** It should be keyed on `(ContractLocation, FilePath)` before anyone runs it in write mode. I did not change it — it was outside the approved scope and deserves its own review.

---

## Open items — nothing here was guessed at

**1. S-5 restore (Step 1) — BLOCKED, needs you.** I deleted it in Phase 2 with `os.remove`, which bypasses the Windows Recycle Bin. Verified: 0 local matches, and no byte-identical copy (`629dafda…`) anywhere on disk. The only copy is in the **SharePoint site recycle bin** (web-only; I have no authenticated path to it). Restore `Mutual NDA- Associated Packaging.docx` (deleted 2026-07-14 from `02 Unsigned Contracts/CTM Labeling`), tell me, and I'll verify the hash, rename, refile and add the flagged row.

**2. Two duplicate sets deferred — deleting either copy destroys evidence I cannot reconstruct:**
- `DJH/DSC Mutual Nondisclosure Agreement - DJH Signed - signed.pdf` **vs** `Steel King/SteeleKing-DSC MNDA Signed.pdf` — byte-identical, two unrelated companies, and the document yields **no counterparty at all**. Picking a survivor would be a coin flip.
- `Amazon/…Doral- 27157 Amazon SNJ5- Subcontract Agreement…` **vs** `Doral Corp/…` (same file) — does a subcontract file under the end client (Amazon) or the subcontractor (Doral)? The document only says "the undersigned Subcontractor". **This is a filing-convention decision, not a data one.**

**3. `Brock Solutions/Brock_Solutions_NDA_Signed.pdf`** exists in `01 Active` (`881d0653`) and `02 Unsigned` (`f7ca9f4d`) with **different bytes**, and now has a row for each. Two versions of the same NDA; I could not tell which is authoritative. Both rows are live and flagged for you.

**4. Five expired contracts still sit in `01 Active`** (Henkel, Joshua Tree Group, LGEUS, Regal Beloit, TE Connectivity — all `Status=expired`). Moving them is a **physical relocation**, and the brief is explicit that every physical move waits for approval — this one was never explicitly approved, so **I did not move them.** `sort-contracts.py --dry-run` confirms exactly these 5 as "Would move: 5". Say the word and it's one command.

**5. The 3 DocuSign certificates** are tagged `DocType=Certificate` and left beside their parent contracts as approved, but their `Status` still reads `archived`/`Review`. I did not change `Status` — the brief forbade Status changes beyond rows explicitly listed. They will keep showing as non-active rows in `01 Active` until you decide.

**6. Nine rows need a counterparty typed in** — `ManualReview=True`, `CounterpartyName` blank. Filter the dashboard on `ManualReview` to find them.

---

## Validation

- ✅ Rows: 785 → **827**. Columns: 24 → **23**.
- ✅ Zero duplicate `FilePath` values.
- ✅ Every catalog row resolves to a real file on disk (was 3 broken).
- ✅ Every governed file on disk has a row or a logged exclusion.
- ✅ Byte-identical duplicate sets: 36 → **2** (both deliberately deferred).
- ✅ `scan-contract.py --prune` orphans: 3 → **0**. `sort-contracts.py`: 0 errors, 0 unresolvable.
- ✅ `skip_app_build: true` gate intact (workflow line 46).
- ✅ Catalog backed up to `contract-catalog.csv.bak_prerecon` before any write.

## Recovery

All 45 removed copies are in `_quarantine-2026-07-14-dedup/`, path-preserved, with SHA-256, size, and superseding survivor recorded in the manifest. Nothing was permanently deleted in this phase.
