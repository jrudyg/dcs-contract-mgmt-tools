# DEDUP EXECUTION REPORT — Phase 2 complete

**Date:** 2026-07-14
**Repo:** `dcs-contract-mgmt-tools`
**Preceded by:** `DEDUP_VERIFY_REPORT.md` (Phase 1), `DEDUP_MERGE_PLAN.md` (Phase 2 Step 1, human-approved)

**Approvals applied:** MCI = **B2** (stray deleted, folder retained) · **all six folder renames** approved · Step 4 = **dedup-only assertions**.

---

## Result

| | Before | After |
|---|---|---|
| Catalog rows | 816 | **785** (−31) |
| Filename collisions across vendor folders | 35 groups / 74 rows | **2 groups** — both deliberate keeps |
| Duplicate `FilePath` values | — | **0** |
| Vendor folders in `01 Active` | 405 | **380** |

The 2 remaining collisions are intentional: `MUTUAL CONFIDENTIALITY AND NONDISCLOSURE AGREEMENT.pdf` (Genesco's executed copy vs UniFirst's blank template) and `NDA 2.23.18 SA.docx` (Walmart vs Swisslog — different documents, same name). Both were verified in Phase 1 as genuinely distinct documents.

---

## What was done

**25 folder merges** — 19 kept an existing folder name; 6 were renamed to the counterparty's legal name (`Clearpath Robotics (OTTO)`, `Bimbo Bakeries USA (BBU)`, `United States Postal Service (USPS)`, `Bespoke Manufacturing Company (BMC)`, `Korber Supply Chain LLC (KSC)`, and `TSC` → `Tractor Supply` in 03 Archived). `GENESCO_Journeys` merged into `Genesco` (D-E) with both documents kept.

**31 files deleted** — 24 alias twins + 1 TSC cross-location copy (D-C) + 6 misfile strays. Every deletion was verified byte-identical (SHA-256) to a surviving copy, except one noted below. SHA-256 and byte size of all 31 were recorded before deletion.

**3 files relocated** into surviving folders (moves, never copy-then-delete): the UniUni NDA into `UNI Express`, and both Genesco documents into `Genesco`.

**8 collision files renamed** vendor-specific (D-F): five `Mutual NDA Template_Feb 2022.docx` → `Mutual NDA - <Vendor> - Feb 2022.docx`; three `Summary.pdf` → `DocuSign Certificate - <Vendor> - <date>.pdf`.

**26 emptied folders removed.** (`os.rmdir` failed here — OneDrive re-materialized the directory entries faster than they could be removed. PowerShell `Remove-Item` succeeded and the removals held. Worth knowing for future cleanups: **use `Remove-Item`, not Python's `rmdir`, against a synced OneDrive library.**)

**Catalog:** 31 rows deleted, 18 rows rewritten (`VendorFolder` / `FilePath` / `Filename`), 2 `CounterpartyName` corrections, 1 `ManualReview` flag. No other `Status` values touched.

---

## Corrections and judgment calls you should see

**1. My Phase 1 "mojibake" finding was wrong.** I reported the Körber folder as corrupted on disk. It was not — the raw bytes are `K\xc3\x96RBER` = valid UTF-8 `KÖRBER`, both on disk and in the catalog. What I saw was my own console's output encoding mangling the display, twice. The folder was renamed to `Korber Supply Chain LLC (KSC)` as approved, and ASCII is still defensible (it avoids encoding pitfalls across CSV → HTML → Azure), but **it was not fixing corruption, because there was none.** If you'd rather have the `ö` back, say so and I'll rename it.

**2. One deletion was not byte-identical to its survivor.** Stray S-5, `02\CTM Labeling\Mutual NDA- Associated Packaging.docx` (SHA `629dafda…`), differs in bytes from the copy in `Associated Packaging` (SHA `32fa4f31…`), though both documents name **Associated Packaging, Inc.** as counterparty. It may be a distinct *draft* of the same agreement rather than a pure duplicate. It is recoverable from the SharePoint recycle bin (93-day retention) and its hash is recorded. Flagging because it is the only deletion that destroyed a unique byte-stream.

**3. `MCI Conveyor Solutions` retained, empty** (decision B2). The folder holds no files and therefore has **no catalog row**, so the "flag it ManualReview" part of B2 could not be expressed in the catalog — a row must point at a file. The vendor's status is recorded here instead: *MCI Conveyor Solutions is a real vendor whose NDA we do not have on file; the folder is held pending the source document.* If you want this visible in the dashboard, it needs a placeholder-row convention that does not exist today.

**4. The Genesco JDC letter is on disk but uncatalogued.** `Genesco JDC GTP Letter Agreement Final 07.10.26 - signed.pdf` moved correctly into `Genesco`, but it never had a catalog row — it is one of the 68 pre-existing orphans (below). It is not lost; it is simply still uncatalogued, exactly as it was before.

---

## Pre-existing issues carried forward — NOT fixed (out of scope, as agreed)

These predate de-duplication and were left untouched per the approved dedup-only scope. **They are real and still open:**

- **68 orphan files** on disk with no catalog row (38 in 01 Active, 25 in 02 Unsigned, 5 in 03 Archived).
- **3 catalog rows whose file is missing on disk:** `DCS-TA-5611-GSESC-Amendment 1 - FE.pdf`, `GDIT_GSESC_IDIQ_No_00936_Revision_No_1_.pdf`, `McKesson/McKesson_DCS_MNDA_REDLINED 05.26.26.docx.pdf`.
- **14 `ContractLocation` mismatches** (rows filed in 02 whose file physically sits in 03).
- **`CounterpartyName` still polluted with job titles** on 2 rows the brief didn't list: `Connors Group` reads "Chief Operating Officer CONNORS AND ASSOCIATES, LLC" and `ScanSource` reads "Senior EVP & Chief Information Officer ScanSource, Inc". Same DocuSign-certificate extraction bug that produced the McKesson error. The company is right; the title prefix is junk. Worth fixing the extraction rule before the next full scan.

These want their own brief.

---

## Step 0 — the pre-flight fix was the most valuable thing in this phase

`ContractLocation` is a **logical label**. `01 Active Contracts` has no folder by that name; active files live in the separately-synced `Salesforce Integration - Active Contracts` library. All three scripts were joining `SHAREPOINT / ContractLocation` directly.

**`scan-contract.py --prune` deletes any catalog row whose file it cannot resolve. Before this fix, all 409 active rows resolved to a path that cannot exist — a single `--prune` run would have silently wiped every active contract from the catalog.** After the fix, `--prune` correctly flags only the 3 genuinely-missing files.

`sort-contracts.py` had the same bug and *moves files*: a move targeting `01 Active Contracts` would have created a bogus folder under the SharePoint root and moved contracts **out** of the synced library. It now reports 0 unresolvable files.

Fixed by giving all three scripts a shared `LOCATION_ROOTS` dict, documented in `CLAUDE.md` with an explicit "never join `SHAREPOINT / ContractLocation`" warning.

Also excluded `03 Archived Contracts\01 Active Contracts - do not use\` from the audit walk — a stale copy of the old active tree. With paths resolving correctly for the first time, `audit-catalog.py` would otherwise have added **396 junk rows** from a folder named "do not use".

---

## Validation

- ✅ Catalog row count: **785** = 816 − 31.
- ✅ Zero duplicate `FilePath` values.
- ✅ Every catalog row resolves to a real file on disk (except the 3 pre-existing broken rows above).
- ✅ Filename collisions across vendor folders: 35 → 2, both intentional.
- ✅ `skip_app_build: true` gate intact (workflow line 46).
- ✅ Catalog backed up to `contract-catalog.csv.bak_predup` before any write.

## Recovery

All 31 deleted files are in the SharePoint recycle bin (93-day retention), and every one's SHA-256 + byte size was recorded pre-deletion. The pre-change catalog is at `contract-catalog.csv.bak_predup`.
