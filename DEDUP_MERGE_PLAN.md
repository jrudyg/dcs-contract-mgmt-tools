# DEDUP MERGE PLAN — Phase 2, Step 1

**Date:** 2026-07-14
**Repo:** `dcs-contract-mgmt-tools`
**Source:** `DEDUP_VERIFY_REPORT.csv` / `.md` (Phase 1), decisions D-A … D-F.
**Status:** ⛔ **PAUSE POINT — nothing below has been executed.** Step 0 (pre-flight) is done and is the only thing written so far. Awaiting "proceed".

---

## ⚠️ Read this first — one locked decision rests on a false premise

**D-B says: "MCI's own three contracts are untouched." MCI Conveyor Solutions does not have three contracts. It has exactly one file, and that file *is* the stray.**

```
02 Unsigned Contracts\MCI Conveyor Solutions\
└── Designed Conveyor Mutual NDA  28 Sept 2020_Signed.pdf   ← the stray (Clearpath Robotics NDA)
```

Deleting the stray per D-B empties the folder completely. So the decision as written is self-contradictory: it protects three contracts that do not exist, and it silently deletes the vendor folder it was trying to preserve.

**Two ways forward — I need you to pick one:**

| Option | Result |
|---|---|
| **B1 — follow D-B literally** | Delete the stray; `MCI Conveyor Solutions` becomes empty and is removed. DCS ends up with **no MCI record at all**. |
| **B2 — treat MCI as a real vendor with a missing contract** | Delete the stray, but **keep the empty folder** and flag it `ManualReview` — "MCI NDA missing; folder held pending source document." |

I have **not** assumed either. Everything else in this plan is independent of the choice; only line M-12 below changes.

*(For contrast, the other five strays are safe: every folder they leave behind still holds its own genuine contracts — `Vertex Form 3D LLC` keeps 2, `Automation Standard` keeps 2, `CTM Labeling` keeps its own `Mutual NDA- CTM Labeling.docx`, `Alice and Olivia` is deliberately removed per D-D with the genuine record preserved in 03 Archived, and `Associated Packaging` is a survivor.)*

---

## Reconciliation

| Quantity | Count |
|---|---|
| Folder merges (24 alias pairs + Genesco per D-E) | **25** |
| Files relocated into survivor folders | **7** |
| Row deletions: 24 alias twins + 1 TSC copy (D-C) + 6 misfile strays | **31** ✅ matches brief |
| Collision files renamed (D-F) | **8** |
| Folders removed after emptying | **25** (26 if option B1) |
| Catalog rows: 816 − 31 | **785** |

---

## Part 1 — Folder merges (25)

Survivor names follow D-A: the document's counterparty legal name, minus commas/periods; an existing folder that already matches is kept as-is; acronym-in-parentheses where it aids recognition.

**Nineteen merges keep an existing folder name** (no rename, lowest risk):

| # | Survivor (kept) | Absorbed → removed | Twin file deleted |
|---|---|---|---|
| M-01 | `Anheuser-Busch` | `CVL Lighthouse` (project-named, not a counterparty) | `CVL T1 Lighthouse NDA DCS.pdf` |
| M-02 | `EJ Gallo` | `Winery NC` (filename-derived, not a counterparty) | `CW2333327 - NDA - Mutual - Winery  NC…pdf` |
| M-03 | `American Eagle` | `AEO` | `DCS - AEO Mutual Confidentiality…pdf` |
| M-04 | `Advanced Machine Guarding Solutions` | `Advanced Machine Guarding` | `DCS Vendor Mutual NDA Advanced Machine Guarding Solutions…pdf` |
| M-05 | `Cross Safety Management LLC` | `Cross Safety Management` | `DCS Vendor Mutual NDA Cross Safety Management LLC…pdf` |
| M-06 | `MODO 8 LLC` | `MODO 8` | `DCS Vendor Mutual NDA MODO 8 LLC…pdf` |
| M-07 | `Applied Technology Group (ATG)` | `Applied Technologies Group` | `DCS Vendor Mutual NDA to ATG…pdf` |
| M-08 | `Anderson Striping and Construction` | `Anderson Stripping` (typo folder) | `DCS Vendor Mutual NDA to Anderson Striping…pdf` |
| M-09 | `FDH Machinery and Pumps Installations` | `FDH Machinery and Pumps Installation` | `DCS Vendor Mutual NDA to FDH…pdf` |
| M-10 | `FedEx Supply Chain` | `FSC` | `Designed Conveyor Systems- FSC Vendor mNDA…pdf` |
| M-11 | `Kenco` (keeps its 2nd file `KLS-2022 NDA.pdf`) | `KLS` | `KLS-2022 NDA-DCS-20220120.pdf` |
| M-13 | `Diversified Automation` | `Diversified` | **2 twins:** `Mutual NDA- DCS_Diversifed_Final.pdf`, `Mutual NDA- Diversifed_Final_MS_11_15_23.pdf` |
| M-14 | `QVC` | `QVC, Inc` (comma is filesystem-unsafe) | `NDA Designed Conveyor Systems, LLC x QVC, Inc…pdf` |
| M-15 | `Advance Auto Parts` | `Advance Auto` | `Non-Disclosure Agreement (…Advance Auto Parts).pdf` |
| M-16 | `Capacity LLC` | `Capacity Logistics` | `Non-Disclosure Agreement - Capacity LLC_LD Signed (002).pdf` |
| M-17 | `OpenMoves` | `openMove` | `OpenMoves Mutual Non-disclosure Agreement-DCS_Signed.pdf` |
| M-18 | `Rand Worldwide` | `RWSI` | `RWSI - Master Services Agreement_Signed.pdf` |
| M-19 | `Ryder` | `SCS IT` (= Ryder Supply Chain Solutions IT) | `SCS IT Mutual NDA Agreement (2025) - signed.pdf` |
| M-20 | `UNI Express` | `UniUni` → **relocate** `UniUni - DCS Mutual NDA - signed.pdf` | `UNI Express  - DCS Mutual NDA - for execution - signed.pdf` |

**Six merges require a folder rename** — neither existing name is the counterparty's legal name. These are the judgment calls; flag any you disagree with:

| # | New survivor name | Absorbed / renamed from | Why |
|---|---|---|---|
| M-12 | `Clearpath Robotics (OTTO)` | rename `OTTO`; delete stray in `MCI Conveyor Solutions` | **D-B.** Doc counterparty is Clearpath Robotics, Inc.; OTTO Motors is its brand. **⚠️ See the MCI question above.** |
| M-21 | `Bimbo Bakeries USA (BBU)` | rename `Bimbo`; remove `BBU` | Doc: "Bimbo Bakeries USA, Inc." Neither existing folder is the legal name. |
| M-22 | `United States Postal Service (USPS)` | rename `USPS` (keeps its 2 other files); remove `Postal Service` | Doc: "United States Postal Service". Both existing names are partial. |
| M-23 | `Bespoke Manufacturing Company (BMC)` | rename `Bespoke`; remove `BMC` | Signature page: "Bespoke Manufacturing Company Inc." Confirms BMC = Bespoke, same entity. |
| M-24 | `Korber Supply Chain LLC (KSC)` | rename `KSC LLC`; remove the mojibake folder | Doc: "Körber Supply Chain LLC". **The existing folder name is corrupted on disk** (`K<?>RBER SUPPLY CHAIN LLC`). ASCII "Korber" avoids re-corrupting it. |
| M-25 | `Genesco` | absorb `GENESCO_Journeys` → **relocate 2 files, delete nothing** | **D-E.** Same legal entity, different documents. Genesco keeps `Genesco DCS MNDA 08.31.23.pdf`; gains `Genesco JDC GTP Letter Agreement Final 07.10.26 - signed.pdf` and `MUTUAL CONFIDENTIALITY AND NONDISCLOSURE AGREEMENT.pdf`. |

**M-26 — Tractor Supply (D-C, cross-location):** rename `03 Archived Contracts\TSC` → `03 Archived Contracts\Tractor Supply`. Delete the `02 Unsigned Contracts\Tractor Supply\DCS TSC NDA 2021.03.21.pdf` copy and remove that now-empty 02 folder. Net: the file lives once, in **03 Archived** under **Tractor Supply**.

### Files relocated into survivors (7)
Whole-folder merges, not just the duplicated file:

| File | From | To |
|---|---|---|
| `UniUni - DCS Mutual NDA - signed.pdf` | `UniUni` | `UNI Express` |
| `Genesco JDC GTP Letter Agreement Final 07.10.26 - signed.pdf` | `GENESCO_Journeys` | `Genesco` |
| `MUTUAL CONFIDENTIALITY AND NONDISCLOSURE AGREEMENT.pdf` | `GENESCO_Journeys` | `Genesco` |

The other four survivors already hold their extra files in place (`Kenco` ×2, `Applied Technology Group (ATG)` ×2, `USPS` ×3 → renamed folder) — those files are untouched, only the folder name changes.

---

## Part 2 — Misfile strays to delete (6)

Wrong-vendor copies. **The folders are NOT merged** — these are unrelated companies.

| # | File deleted | Deleted from | Belongs to | Folder left with |
|---|---|---|---|---|
| S-1 | `Mutual NDA- ICE - signed.pdf` | `01\Alice and Olivia` | Industrial Controls Electric | **0 files → folder removed** (D-D). Genuine A&O record survives in `03 Archived\Alice and Olivia`. |
| S-2 | `Standard MNDA - Dot Foods Inc…pdf` | `01\Automation Standard` | DOT Foods | 2 files (its own) |
| S-3 | `Form NDA -- iHerb 081518…pdf` | `01\Vertex Form 3D LLC` | iHerb | 2 files (its own) |
| S-4 | `Mutual NDA- Associated Packaging.pdf` | `02\CTM Labeling` | Associated Packaging | 1 file (`Mutual NDA- CTM Labeling.docx`) |
| S-5 | `Mutual NDA- Associated Packaging.docx` | `02\CTM Labeling` | Associated Packaging | ↑ same folder |
| S-6 | `Designed Conveyor Mutual NDA  28 Sept 2020_Signed.pdf` | `02\MCI Conveyor Solutions` | Clearpath Robotics | **0 files — ⚠️ see B1/B2 question above** |

In every case the surviving copy is the one in the correct vendor's folder; the deleted copy is byte-identical (S-4, S-6 verified by SHA-256) or a variant of the same counterparty's document (S-5).

---

## Part 3 — Collision renames (8, D-F)

Same filename, entirely different documents. Nothing is deleted; all 8 files keep their current folder and get a vendor-specific name. Pattern: `DocType - Counterparty - Date`.

**`Mutual NDA Template_Feb 2022.docx` ×5** (all in `02 Unsigned Contracts`, each already filled in with its own counterparty — none is blank):

| Folder | New filename |
|---|---|
| `Allan Fire Protection Systems` | `Mutual NDA - Allan Fire Protection Systems - Feb 2022.docx` |
| `Big Bay Holdings` | `Mutual NDA - Big Bay Holdings - Feb 2022.docx` |
| `New Age Industrial` | `Mutual NDA - New Age Industrial - Feb 2022.docx` |
| `OX Metalworks` | `Mutual NDA - Ox Metalworks - Feb 2022.docx` |
| `Western States Fire Protection` | `Mutual NDA - Western States Fire Protection - Feb 2022.docx` |

**`Summary.pdf` ×3** (all in `01 Active Contracts`; each is a DocuSign Certificate of Completion — date = final signature):

| Folder | New filename |
|---|---|
| `Connors Group` | `DocuSign Certificate - Connors and Associates - 2026-02-24.pdf` |
| `McKesson` | `DocuSign Certificate - McKesson - 2026-05-27.pdf` |
| `ScanSource` | `DocuSign Certificate - ScanSource - 2025-10-08.pdf` |

---

## Part 4 — Catalog changes (Step 3 preview)

- **31 row deletions** (25 twins incl. TSC + 6 strays) → **816 → 785 rows**.
- **`VendorFolder` / `FilePath` / `Filename` rewritten** on every row touched by a folder rename, a relocation, or a file rename.
- **CounterpartyName fixes:** `GENESCO_Journeys` NDA row → `GENESCO INC.` (currently wrongly `UniFirst`); `McKesson\Summary.pdf` row → `McKesson Corporation` (currently carries Connors' COO name).
- **ManualReview:** `03 Archived\Alice and Olivia\DCS MNDA Alice and Olivia Fully Executed.pdf` → `ManualReview=True`, note *"Filename says Fully Executed but status=unsigned — verify signature state"*.
- No other `Status` values change.

---

## ⚠️ Step 4 validation will fail as written — and that is not the dedup's fault

The brief asserts *"every on-disk file in governed folders has a catalog row."* **That assertion is false today and this plan does not change it.** Now that path resolution is fixed (Step 0), `audit-catalog.py --dry-run` sees the active library for the first time and reports:

- **68 orphan files** — real contracts on disk with **no catalog row** (38 in 01 Active, 25 in 02 Unsigned, 5 in 03 Archived). Pre-existing drift, entirely separate from de-duplication.
- **3 catalog rows whose file is missing on disk** (`DCS-TA-5611-GSESC-Amendment 1 - FE.pdf`, `GDIT_GSESC_IDIQ…pdf`, `McKesson_DCS_MNDA_REDLINED 05.26.26.docx.pdf`).
- **14 `ContractLocation` mismatches** (rows filed in 02 whose file actually sits in 03).

None of these are caused by the merges, and **none are in this brief's scope.** I propose Step 4 asserts what dedup is actually responsible for — zero duplicate `FilePath` values, every *moved/renamed* row resolves on disk, row count = 785 — and that the 68 + 3 + 14 get their own brief. **Say if you'd rather I fold them in instead.**

---

## Step 0 — already done (pre-flight, the only writes so far)

1. **`CLAUDE.md`** now documents that `01 Active Contracts` is a *logical label* whose physical root is the separately-synced `Salesforce Integration - Active Contracts` library, with a location→root table and an explicit warning never to join `SHAREPOINT / ContractLocation`.
2. **`scan-contract.py`, `audit-catalog.py`, `sort-contracts.py`** all now resolve through a shared `LOCATION_ROOTS` dict.

**This fix was load-bearing, not cosmetic.** `scan-contract.py --prune` deletes any row it cannot resolve on disk. Before the fix, all 409 active rows resolved to a path that *cannot exist* — **a single `--prune` run would have silently wiped every active contract from the catalog.** Verified after the fix: prune now flags only the 3 genuinely-missing files. `sort-contracts.py` had the same bug and *moves files*; it would have created a bogus `01 Active Contracts\` folder under the SharePoint root and moved contracts out of the synced library. It now reports 0 unresolvable files and 0 moves.

I also excluded `03 Archived Contracts\01 Active Contracts - do not use\` from the audit walk — a stale copy of the old active tree. With paths resolving correctly, `audit-catalog.py` would otherwise have added **396 junk rows** from a folder named "do not use".

All three scripts dry-run clean. No catalog written, no files moved, nothing committed.

---

## Decisions needed before I execute

1. **MCI (B1 or B2)** — delete the folder entirely, or keep it flagged as a vendor with a missing contract?
2. **The 6 folder renames** (M-12, M-21 … M-25) — confirm, or tell me to keep the existing names.
3. **Step 4 scope** — assert dedup-only (my recommendation), or fold in the 68 orphans / 3 missing / 14 mismatches?

On "proceed" I execute Parts 1–3 with `git mv`-style moves and renames (never copy-then-delete, per the OneDrive constraint), then Steps 3–4.
