# DEDUP VERIFY REPORT — Phase 1 (Verification Only)

**Date:** 2026-07-14
**Repo:** `dcs-contract-mgmt-tools`
**Mode:** READ-ONLY — nothing was moved, deleted, renamed, or written outside this report. No catalog edits, no git operations, nightly scanner untouched.
**Scope:** 35 filename groups / 74 catalog rows where one filename appears under 2+ vendor folders.
**Companion data:** `DEDUP_VERIFY_REPORT.csv` (one row per file, with SHA-256).

---

## Headline

**All 74 files exist on disk. None missing.** Of the 35 groups:

| Verdict | Groups | Meaning |
|---|---|---|
| `IDENTICAL` (byte-for-byte) | **30** | Every copy in the group has the same SHA-256 |
| `DIFFERENT` | **5** | Copies differ in content |
| `MISSING` | **0** | — |

But byte-identity alone is the wrong lens for the merge plan. Re-cut by **what the document actually says its counterparty is**, the 35 groups are:

| Class | Groups | Phase 2 action |
|---|---|---|
| **DUPLICATE-ALIAS-PAIR** — same counterparty, two folder names | **25** (24 distinct folder pairs) | Merge folder, delete twin |
| **MISFILE** — a copy sitting in a *different company's* folder | **6** | Delete the wrong-vendor copy. **Do NOT merge the folders** |
| **NAME-COLLISION** — different documents that happen to share a filename | **4** | Keep everything. No dedup |

The 6 misfiles are the reason this phase was worth doing. **A naive "identical hash → merge the two folders" script would have merged five pairs of unrelated companies** (e.g. `Alice and Olivia` into `Industrial Controls Electric`), and would have deleted three legitimately distinct documents in the collision groups.

---

## Three findings that change the Phase 2 plan

### 1. Six wrong-vendor misfiles — delete the copy, do NOT merge the folder

These are byte-identical (or near-identical) copies of one company's contract sitting in an **unrelated company's** folder. The folder pair must *not* be merged; only the stray copy is removed.

| Group (file) | Correct folder | Wrong-vendor folder | What the document says | Likely cause |
|---|---|---|---|---|
| `Mutual NDA- ICE - signed.pdf` | `Industrial Controls Electric (ICE)` | **`Alice and Olivia`** | Industrial Controls Electric | `ICE` matched inside "**al-ICE**-and-Olivia" |
| `Standard MNDA - Dot Foods Inc...pdf` | `DOT Foods` | **`Automation Standard`** | DOT FOODS, INC. | matched on the word "**Standard**" |
| `Form NDA -- iHerb 081518...pdf` | `iHerb` | **`Vertex Form 3D LLC`** | iHerb, LLC | matched on the word "**Form**" |
| `Mutual NDA- Associated Packaging.pdf` | `Associated Packaging` | **`CTM Labeling`** | Associated Packaging, Inc. | wrong-vendor copy |
| `Mutual NDA- Associated Packaging.docx` | `Associated Packaging` | **`CTM Labeling`** | Associated Packaging, Inc. | wrong-vendor copy (byte-different variant) |
| `Designed Conveyor Mutual NDA 28 Sept 2020_Signed.pdf` | **`OTTO` (needs confirmation)** | **`MCI Conveyor Solutions`** | **Clearpath Robotics, Inc.** | neither folder name matches the doc |

Two of these need a human decision, not a script:

- **`Alice and Olivia`** holds exactly one file — the misfiled ICE NDA. Deleting it leaves the folder empty. Alice + Olivia is a real apparel brand; confirm whether DCS actually has a contract with them that is filed elsewhere (or missing) before the folder disappears.
- **`Designed Conveyor Mutual NDA 28 Sept 2020_Signed.pdf`** is an NDA with **Clearpath Robotics, Inc.** — a name that matches *neither* folder. OTTO Motors is Clearpath's product brand, so the `OTTO` folder is probably right and the `MCI Conveyor Solutions` copy is the stray. **Confirm before deleting either copy.** `CTM Labeling` likewise has no NDA of its own once the Associated Packaging copies are removed.

### 2. The two generic-name groups are NOT duplicates — keep every copy

The brief asked whether these are blank templates legitimately reused or stray duplicates. **Neither. They are distinct executed documents that merely share a filename.**

- **`Mutual NDA Template_Feb 2022.docx` (5 folders)** — five *different* SHA-256 hashes. Each is the DCS template already **filled in with its own counterparty**: Allan Fire Protection Systems (AFPS), Big Bay Holdings (BBH), New Age Industrial (NAI), Ox Metalworks (OX), and WSFP (Western States Fire Protection). Not one is blank. **Keep all five.** They should be renamed to vendor-specific filenames so they stop colliding.
- **`Summary.pdf` (3 folders)** — three different hashes. Each is a **DocuSign Certificate of Completion** for a different envelope: Connors and Associates LLC (env `4BE9128B`), McKesson Corporation (env `2CE4B5FF`), and ScanSource Inc. (env `5C7FC003`). All three are correctly filed. **Keep all three.** `Summary.pdf` is just DocuSign's default export name.

### 3. Two catalog `CounterpartyName` values are wrong (independent of dedup)

Found while reading the documents; worth fixing whenever the catalog is next edited:

- **`GENESCO_Journeys/MUTUAL CONFIDENTIALITY AND NONDISCLOSURE AGREEMENT.pdf`** is catalogued as counterparty **`UniFirst`**. The signature page reads **`COUNTERPARTY: GENESCO INC.`**, executed by Matthew N. Johnson, VP & Treasurer. The file is correctly *filed*; only the catalog field is wrong. (The UniFirst copy of the same-named file is the *blank, unexecuted* DCS template — its counterparty block is empty. Same filename, different document, both legitimately where they are.)
- **`McKesson/Summary.pdf`** is catalogued as **`Chief Operating Officer CONNORS AND ASSOCIATES, LLC`** — a value scraped from the *Connors* certificate. Should be McKesson Corporation.

Both look like the scanner grabbing a name from the wrong region of a DocuSign certificate page. Worth a look at the extraction rule before the next full scan.

---

## Path resolution (and a discrepancy to fix)

The catalog's four `ContractLocation` values do **not** all live under the SharePoint root, contrary to what `CLAUDE.md` implies:

| ContractLocation | Resolved on-disk root |
|---|---|
| `01 Active Contracts` (409 rows) | `C:\Users\jrudy\OneDrive - Diakonia Group, LLC\`**`Salesforce Integration - Active Contracts`** |
| `02 Unsigned Contracts` (239 rows) | `…\Contract Management - SharePoint\02 Unsigned Contracts` |
| `03 Archived Contracts` (159 rows) | `…\Contract Management - SharePoint\03 Archived Contracts` |
| `04 Expired Contracts` (9 rows) | `…\Contract Management - SharePoint\04 Expired Contracts` |

`01 Active Contracts` is a **logical label only** — there is no folder by that name at the SharePoint root. The physical root is the separately-synced `Salesforce Integration - Active Contracts` library, per `nightly-catalog-scan.py:37` and `NIGHTLY_CATALOG_JOB.md`. All 409 active paths resolve correctly there.

`CLAUDE.md`'s architecture section still describes the flow as "01 Active / 02 Unsigned / 03 Archived" under one root and says `SHAREPOINT = SCRIPT_DIR.parent`. **`scan-contract.py:32` and `audit-catalog.py:33` both list `"01 Active Contracts"` as a literal folder under that root.** If those two scripts resolve active-contract paths that way, they are pointed at a folder that does not exist — worth verifying before Phase 2 runs anything that writes.

Also on disk: `03 Archived Contracts\01 Active Contracts - do not use\` — a stale archived copy of the old active tree. Out of scope here, but it is a live foot-gun for any recursive scan.

---

## Two more things Phase 2 needs to decide

- **Cross-location conflict:** `DCS TSC NDA 2021.03.21.pdf` is byte-identical in **`02 Unsigned Contracts\Tractor Supply\`** and **`03 Archived Contracts\TSC\`**. This is the only group whose copies sit in *different* ContractLocations, so the merge isn't just a folder rename — somebody has to decide whether this contract is Unsigned or Archived first. (It's a scanned image PDF; no text could be extracted to help.)
- **Mojibake folder name:** the Körber folder is stored on disk as `K<?>RBER SUPPLY CHAIN LLC` — the `ö` is corrupted. Fix the name during the merge rather than propagating it.

---

## Method

- Groups derived from the live `contract-catalog.csv` (816 rows) by filename appearing under 2+ distinct `VendorFolder` values → **35 groups / 74 rows**, matching the brief exactly. (The promised `dedup-worklist-2026-07-14.csv` was not present anywhere on disk; the derivation reproduces its stated shape.)
- SHA-256 computed by streaming each file in binary read-only mode. No writes, no timestamp changes, no OneDrive state change.
- Counterparty read from the document itself: first-page text via `pdfplumber` for PDFs and `python-docx` for `.docx`. For the three DCS-boilerplate NDAs whose first page defers to "the counterparty identified below," the **signature page** was extracted instead — that is how `BMC` was confirmed as **Bespoke Manufacturing Company Inc.** (same entity as the `Bespoke` folder → a true alias pair, not a misfile) and how the GENESCO copy was identified.

---

## Group-by-group results

Full per-file detail — including every SHA-256 — is in `DEDUP_VERIFY_REPORT.csv`. The `Classification`, `KeepFolder`, and `RecommendedAction` columns there carry the proposed Phase 2 disposition for each row.

---

## Folder census — all paired vendor folders

Every file in **both** folders of each pair, so the Phase 2 merge covers the whole folder rather than just the duplicated file. Files marked ⟵ are the ones that triggered the group.

#### Anheuser-Busch ↔ CVL Lighthouse  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\Anheuser-Busch\`** — 1 file(s)
- `CVL T1 Lighthouse NDA DCS.pdf` ⟵ *duplicated file*

**`01 Active Contracts\CVL Lighthouse\`** — 1 file(s)
- `CVL T1 Lighthouse NDA DCS.pdf` ⟵ *duplicated file*

#### EJ Gallo ↔ Winery NC  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\EJ Gallo\`** — 1 file(s)
- `CW2333327 - NDA - Mutual - Winery  NC(FINAL 012020).DOCX - signed.pdf` ⟵ *duplicated file*

**`01 Active Contracts\Winery NC\`** — 1 file(s)
- `CW2333327 - NDA - Mutual - Winery  NC(FINAL 012020).DOCX - signed.pdf` ⟵ *duplicated file*

#### AEO ↔ American Eagle  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\AEO\`** — 1 file(s)
- `DCS - AEO Mutual Confidentiality and Non-Disclosure Agreement (10.27.23.pdf` ⟵ *duplicated file*

**`01 Active Contracts\American Eagle\`** — 1 file(s)
- `DCS - AEO Mutual Confidentiality and Non-Disclosure Agreement (10.27.23.pdf` ⟵ *duplicated file*

#### Tractor Supply ↔ TSC  — _DUPLICATE-ALIAS-PAIR_

**`02 Unsigned Contracts\Tractor Supply\`** — 1 file(s)
- `DCS TSC NDA 2021.03.21.pdf` ⟵ *duplicated file*

**`03 Archived Contracts\TSC\`** — 1 file(s)
- `DCS TSC NDA 2021.03.21.pdf` ⟵ *duplicated file*

#### Advanced Machine Guarding ↔ Advanced Machine Guarding Solutions  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\Advanced Machine Guarding\`** — 1 file(s)
- `DCS Vendor Mutual NDA Advanced Machine Guarding Solutions - signed 3.24.2025.pdf` ⟵ *duplicated file*

**`01 Active Contracts\Advanced Machine Guarding Solutions\`** — 1 file(s)
- `DCS Vendor Mutual NDA Advanced Machine Guarding Solutions - signed 3.24.2025.pdf` ⟵ *duplicated file*

#### Cross Safety Management ↔ Cross Safety Management LLC  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\Cross Safety Management\`** — 1 file(s)
- `DCS Vendor Mutual NDA Cross Safety Management LLC - signed 3.13.2025.pdf` ⟵ *duplicated file*

**`01 Active Contracts\Cross Safety Management LLC\`** — 1 file(s)
- `DCS Vendor Mutual NDA Cross Safety Management LLC - signed 3.13.2025.pdf` ⟵ *duplicated file*

#### MODO 8 ↔ MODO 8 LLC  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\MODO 8\`** — 1 file(s)
- `DCS Vendor Mutual NDA MODO 8 LLC - signed 3.27.2025.pdf` ⟵ *duplicated file*

**`01 Active Contracts\MODO 8 LLC\`** — 1 file(s)
- `DCS Vendor Mutual NDA MODO 8 LLC - signed 3.27.2025.pdf` ⟵ *duplicated file*

#### Applied Technologies Group ↔ Applied Technology Group (ATG)  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\Applied Technologies Group\`** — 1 file(s)
- `DCS Vendor Mutual NDA to ATG Applied Technology Group LLC - signed 8.21.2025.pdf` ⟵ *duplicated file*

**`01 Active Contracts\Applied Technology Group (ATG)\`** — 2 file(s)
- `DCS Vendor Mutual NDA to ATG Applied Technology Group LLC - signed 8.21.2025.pdf` ⟵ *duplicated file*
- `Designed Conveyor Systems Master Service Agreement.pdf`

#### Anderson Striping and Construction ↔ Anderson Stripping  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\Anderson Striping and Construction\`** — 1 file(s)
- `DCS Vendor Mutual NDA to Anderson Striping and Construction - signed 8.14.2025.pdf` ⟵ *duplicated file*

**`01 Active Contracts\Anderson Stripping\`** — 1 file(s)
- `DCS Vendor Mutual NDA to Anderson Striping and Construction - signed 8.14.2025.pdf` ⟵ *duplicated file*

#### FDH Machinery and Pumps Installation ↔ FDH Machinery and Pumps Installations  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\FDH Machinery and Pumps Installation\`** — 1 file(s)
- `DCS Vendor Mutual NDA to FDH Machinery and Pumps Installations 10.28.2024.pdf` ⟵ *duplicated file*

**`01 Active Contracts\FDH Machinery and Pumps Installations\`** — 1 file(s)
- `DCS Vendor Mutual NDA to FDH Machinery and Pumps Installations 10.28.2024.pdf` ⟵ *duplicated file*

#### BBU ↔ Bimbo  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\BBU\`** — 1 file(s)
- `DCS.BBU-MSA (19 DEC 25) signed.pdf` ⟵ *duplicated file*

**`01 Active Contracts\Bimbo\`** — 1 file(s)
- `DCS.BBU-MSA (19 DEC 25) signed.pdf` ⟵ *duplicated file*

#### MCI Conveyor Solutions ↔ OTTO  — _MISFILE_

**`02 Unsigned Contracts\MCI Conveyor Solutions\`** — 1 file(s)
- `Designed Conveyor Mutual NDA  28 Sept 2020_Signed.pdf` ⟵ *duplicated file*

**`02 Unsigned Contracts\OTTO\`** — 1 file(s)
- `Designed Conveyor Mutual NDA  28 Sept 2020_Signed.pdf` ⟵ *duplicated file*

#### FSC ↔ FedEx Supply Chain  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\FSC\`** — 1 file(s)
- `Designed Conveyor Systems- FSC Vendor mNDA 5.7.2025.docx.pdf` ⟵ *duplicated file*

**`01 Active Contracts\FedEx Supply Chain\`** — 1 file(s)
- `Designed Conveyor Systems- FSC Vendor mNDA 5.7.2025.docx.pdf` ⟵ *duplicated file*

#### Postal Service ↔ USPS  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\Postal Service\`** — 1 file(s)
- `Executed Postal Service DCS NDA.pdf` ⟵ *duplicated file*

**`01 Active Contracts\USPS\`** — 3 file(s)
- `Executed 3APCKG-24-B-0005.pdf`
- `Executed Postal Service DCS NDA.pdf` ⟵ *duplicated file*
- `Executed USPS - DCS MNDA 01.29.25.pdf`

#### Vertex Form 3D LLC ↔ iHerb  — _MISFILE_

**`01 Active Contracts\Vertex Form 3D LLC\`** — 3 file(s)
- `DCS Vendor Mutual NDA to Vertex Form 3D LLC - signed 4.3.2025.pdf`
- `Enterprise_License_Agreement_01.14.26 - signed.pdf`
- `Form NDA -- iHerb 081518 (Fully Executed).pdf` ⟵ *duplicated file*

**`01 Active Contracts\iHerb\`** — 1 file(s)
- `Form NDA -- iHerb 081518 (Fully Executed).pdf` ⟵ *duplicated file*

#### KLS ↔ Kenco  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\KLS\`** — 1 file(s)
- `KLS-2022 NDA-DCS-20220120.pdf` ⟵ *duplicated file*

**`01 Active Contracts\Kenco\`** — 2 file(s)
- `KLS-2022 NDA-DCS-20220120.pdf` ⟵ *duplicated file*
- `KLS-2022 NDA.pdf`

#### BMC ↔ Bespoke  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\BMC\`** — 1 file(s)
- `MUTUAL CONFIDENTIALITY AND NONDISCLOSURE AGREEMENT BMC Signed.pdf` ⟵ *duplicated file*

**`01 Active Contracts\Bespoke\`** — 1 file(s)
- `MUTUAL CONFIDENTIALITY AND NONDISCLOSURE AGREEMENT BMC Signed.pdf` ⟵ *duplicated file*

#### GENESCO_Journeys ↔ UniFirst  — _NAME-COLLISION_

**`01 Active Contracts\GENESCO_Journeys\`** — 2 file(s)
- `Genesco JDC GTP Letter Agreement Final 07.10.26 - signed.pdf`
- `MUTUAL CONFIDENTIALITY AND NONDISCLOSURE AGREEMENT.pdf` ⟵ *duplicated file*

**`02 Unsigned Contracts\UniFirst\`** — 1 file(s)
- `MUTUAL CONFIDENTIALITY AND NONDISCLOSURE AGREEMENT.pdf` ⟵ *duplicated file*

#### KSC LLC ↔ KÖRBER SUPPLY CHAIN LLC  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\KSC LLC\`** — 1 file(s)
- `Mutual NDA - Designed Conveyor Systems  - KSC LLC - FINAL - 02.2025.pdf` ⟵ *duplicated file*

**`01 Active Contracts\KÖRBER SUPPLY CHAIN LLC\`** — 1 file(s)
- `Mutual NDA - Designed Conveyor Systems  - KSC LLC - FINAL - 02.2025.pdf` ⟵ *duplicated file*

#### Allan Fire Protection Systems ↔ Big Bay Holdings ↔ New Age Industrial ↔ OX Metalworks ↔ Western States Fire Protection  — _NAME-COLLISION_

**`02 Unsigned Contracts\Allan Fire Protection Systems\`** — 1 file(s)
- `Mutual NDA Template_Feb 2022.docx` ⟵ *duplicated file*

**`02 Unsigned Contracts\Big Bay Holdings\`** — 1 file(s)
- `Mutual NDA Template_Feb 2022.docx` ⟵ *duplicated file*

**`02 Unsigned Contracts\New Age Industrial\`** — 1 file(s)
- `Mutual NDA Template_Feb 2022.docx` ⟵ *duplicated file*

**`02 Unsigned Contracts\OX Metalworks\`** — 2 file(s)
- `Mutual NDA OX Metalworks-2.pdf`
- `Mutual NDA Template_Feb 2022.docx` ⟵ *duplicated file*

**`02 Unsigned Contracts\Western States Fire Protection\`** — 1 file(s)
- `Mutual NDA Template_Feb 2022.docx` ⟵ *duplicated file*

#### Associated Packaging ↔ CTM Labeling  — _MISFILE_

**`02 Unsigned Contracts\Associated Packaging\`** — 2 file(s)
- `Mutual NDA- Associated Packaging.docx` ⟵ *duplicated file*
- `Mutual NDA- Associated Packaging.pdf`

**`02 Unsigned Contracts\CTM Labeling\`** — 3 file(s)
- `Mutual NDA- Associated Packaging.docx` ⟵ *duplicated file*
- `Mutual NDA- Associated Packaging.pdf`
- `Mutual NDA- CTM Labeling.docx`

#### Diversified ↔ Diversified Automation  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\Diversified\`** — 2 file(s)
- `Mutual NDA- DCS_Diversifed_Final.pdf` ⟵ *duplicated file*
- `Mutual NDA- Diversifed_Final_MS_11_15_23.pdf`

**`01 Active Contracts\Diversified Automation\`** — 2 file(s)
- `Mutual NDA- DCS_Diversifed_Final.pdf` ⟵ *duplicated file*
- `Mutual NDA- Diversifed_Final_MS_11_15_23.pdf`

#### Alice and Olivia ↔ Industrial Controls Electric (ICE)  — _MISFILE_

**`01 Active Contracts\Alice and Olivia\`** — 1 file(s)
- `Mutual NDA- ICE - signed.pdf` ⟵ *duplicated file*

**`01 Active Contracts\Industrial Controls Electric (ICE)\`** — 1 file(s)
- `Mutual NDA- ICE - signed.pdf` ⟵ *duplicated file*

#### Walmart ↔ Swisslog  — _NAME-COLLISION_

**`02 Unsigned Contracts\Walmart\`** — 2 file(s)
- `NDA 2.23.18 SA.docx` ⟵ *duplicated file*
- `NDA 2.23.18 SA.pdf`

**`03 Archived Contracts\Swisslog\`** — 2 file(s)
- `NDA 2.23.18 SA Signed.pdf`
- `NDA 2.23.18 SA.docx` ⟵ *duplicated file*

#### QVC ↔ QVC, Inc  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\QVC\`** — 1 file(s)
- `NDA Designed Conveyor Systems, LLC x QVC, Inc signed 9.30.2024.pdf` ⟵ *duplicated file*

**`01 Active Contracts\QVC, Inc\`** — 1 file(s)
- `NDA Designed Conveyor Systems, LLC x QVC, Inc signed 9.30.2024.pdf` ⟵ *duplicated file*

#### Advance Auto ↔ Advance Auto Parts  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\Advance Auto\`** — 1 file(s)
- `Non-Disclosure Agreement (Designed Conveyor Systems, LLC and Advance Auto Parts).pdf` ⟵ *duplicated file*

**`01 Active Contracts\Advance Auto Parts\`** — 1 file(s)
- `Non-Disclosure Agreement (Designed Conveyor Systems, LLC and Advance Auto Parts).pdf` ⟵ *duplicated file*

#### Capacity LLC ↔ Capacity Logistics  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\Capacity LLC\`** — 1 file(s)
- `Non-Disclosure Agreement - Capacity LLC_LD Signed (002).pdf` ⟵ *duplicated file*

**`01 Active Contracts\Capacity Logistics\`** — 1 file(s)
- `Non-Disclosure Agreement - Capacity LLC_LD Signed (002).pdf` ⟵ *duplicated file*

#### OpenMoves ↔ openMove  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\OpenMoves\`** — 1 file(s)
- `OpenMoves Mutual Non-disclosure Agreement-DCS_Signed.pdf` ⟵ *duplicated file*

**`01 Active Contracts\openMove\`** — 1 file(s)
- `OpenMoves Mutual Non-disclosure Agreement-DCS_Signed.pdf` ⟵ *duplicated file*

#### RWSI ↔ Rand Worldwide  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\RWSI\`** — 1 file(s)
- `RWSI - Master Services Agreement_Signed.pdf` ⟵ *duplicated file*

**`01 Active Contracts\Rand Worldwide\`** — 1 file(s)
- `RWSI - Master Services Agreement_Signed.pdf` ⟵ *duplicated file*

#### Ryder ↔ SCS IT  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\Ryder\`** — 1 file(s)
- `SCS IT Mutual NDA Agreement (2025) - signed.pdf` ⟵ *duplicated file*

**`01 Active Contracts\SCS IT\`** — 1 file(s)
- `SCS IT Mutual NDA Agreement (2025) - signed.pdf` ⟵ *duplicated file*

#### Automation Standard ↔ DOT Foods  — _MISFILE_

**`01 Active Contracts\Automation Standard\`** — 3 file(s)
- `Mutual NDA DCS to Automation Standard - signed 8.9.2024.pdf`
- `Softeon_Standard_NDA_Signed.pdf`
- `Standard MNDA - Dot Foods Inc. - 2022.10.19 dcs executed.pdf` ⟵ *duplicated file*

**`01 Active Contracts\DOT Foods\`** — 1 file(s)
- `Standard MNDA - Dot Foods Inc. - 2022.10.19 dcs executed.pdf` ⟵ *duplicated file*

#### Connors Group ↔ McKesson ↔ ScanSource  — _NAME-COLLISION_

**`01 Active Contracts\Connors Group\`** — 2 file(s)
- `Mutual Confidentiality Agreement - Partner - redlines 02.16.26.docx.pdf`
- `Summary.pdf` ⟵ *duplicated file*

**`01 Active Contracts\McKesson\`** — 2 file(s)
- `McKesson_DCS_MNDA_Executed 05.26.26.docx.pdf`
- `Summary.pdf` ⟵ *duplicated file*

**`01 Active Contracts\ScanSource\`** — 6 file(s)
- `DCS_-_MSA_for_Integration_Project__8.14._FINAL_CLEAN.docx.pdf`
- `EXHIBIT_A_-_DATUM_SOW.SCSC_CLEAN_10.1.25.docx.pdf`
- `EXHIBIT_B_-_DATUM_End_User_License_Agreement_FINAL_CLEAN.8.14.25.docx.pdf`
- `EXHIBIT_C_-_Appendix_D._Customer_Service_Addendum.docx.pdf`
- `ScanSource_-_DATUM_Prop_Final_9.19.24_(002).pdf`
- `Summary.pdf` ⟵ *duplicated file*

#### UNI Express ↔ UniUni  — _DUPLICATE-ALIAS-PAIR_

**`01 Active Contracts\UNI Express\`** — 1 file(s)
- `UNI Express  - DCS Mutual NDA - for execution - signed.pdf` ⟵ *duplicated file*

**`01 Active Contracts\UniUni\`** — 2 file(s)
- `UNI Express  - DCS Mutual NDA - for execution - signed.pdf` ⟵ *duplicated file*
- `UniUni - DCS Mutual NDA - signed.pdf`

---

## Out of scope (confirmed untouched)

No files moved or deleted. `contract-catalog.csv` unmodified. No git add/commit/push. The nightly scanner was not registered or run; it remains held pending 05 In-Process convergence.

*Phase 2 (folder merges, twin deletion, catalog update, push) awaits human review of this report.*
