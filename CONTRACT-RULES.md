# Contract Classification Rules
*Designed Conveyor Systems — Contract Management System*

---

## Folder Classification

| Folder | Rule |
|---|---|
| `01 Active Contracts` | SigningStatus = `Signed` AND not expired/terminated |
| `02 Unsigned Contracts` | SigningStatus = `Unsigned` AND not expired/terminated |
| `03 Archived Contracts` | **Never auto-moved.** Human decision only. Expired/terminated contracts are flagged `Review` first. |

---

## SigningStatus Values

### `Signed`
All three conditions must be true:
1. At least 1 signature block attributed to **DCS / Designed Conveyor Systems**
2. At least 1 signature block attributed to the **counterparty** (any non-DCS party)
3. Total = 2 or more confirmed signatures

Signature evidence accepted:
- Filled `By:` block with a real name (not blank, underscores, or placeholder text)
- DocuSign signer record (detected from DocuSign Envelope / audit trail page)
- Adobe Sign signer record (detected from certificate page)

Party attribution:
- DCS block: company name near the block contains "Designed Conveyor Systems" or "DCS"
- Counterparty block: any block not attributed to DCS
- Scanner reads the document only — does not use CSV data for attribution

### `Unsigned`
- Document text is readable
- Fewer than 2 attributed signatures found (missing DCS, counterparty, or both)

### `Review`
Flagged when the scanner cannot make a reliable determination. Triggers:
- Scanned or image-based PDF (text extraction returns < 50 chars)
- Signature area detected but unreadable (embedded graphic signature block)
- Contract is expired or terminated (ExpirationDate < today)
- Effective date or expiration date cannot be resolved from the document
- Any date-based condition that cannot be calculated

`Review` is the only status the scanner may overwrite — it can be resolved to `Signed` or `Unsigned` by re-scan or human correction.

### Permanence Rule
- `Signed` — permanent; scanner will never overwrite
- `Unsigned` — permanent; scanner will never overwrite
- `Review` — temporary; scanner or human may update to `Signed` or `Unsigned`

---

## Expiration / Termination Detection

Expiration is calculated from the document, not the CSV:
1. Read `EffectiveDate` from the document (trigger phrases: "effective as of", "dated as of", "entered into as of")
2. Read the term or termination clause (e.g., "term of 2 years", "expires on", "through", "termination date")
3. Calculate `ExpirationDate` = EffectiveDate + term, or explicit date found
4. If `ExpirationDate < today` → flag SigningStatus as `Review` for human review before archiving

### EffectiveDate Fallback
If no effective date is found in the body of the document:
- Look at date fields in signature blocks
- Use the **oldest date** found across all signature blocks as the effective date

---

## Sorting / Auto-Move Rules

The sort tool (`sort-contracts.py`) moves files based on SigningStatus and expiration:
- `Signed` + not expired → `01 Active Contracts`
- `Unsigned` + not expired → `02 Unsigned Contracts`
- `Review` → no auto-move; human resolves first
- `03 Archived Contracts` → never touched by sort tool

### Files the Sort Tool Always Skips
- Files in `03 Archived Contracts`
- Files with no `SigningStatus` (scan first)
- Files with no `FilePath`
- VendorFolder starts with `00 ` or contains the word `template`
- Filename contains `template` or `redline`

---

## Catalog Maintenance — Orphan Pruning

The scanner does not automatically remove catalog rows when a file is missing from disk (it may be a cloud-only OneDrive file not yet synced). To explicitly clean up rows whose files no longer exist on disk, run:

```
python Tools/scan-contract.py --prune
```

`--prune` can be combined with `--all` to scan and prune in a single pass, and with `--dry-run` to preview removals before committing them.

**Rule:** Run `--prune` any time contracts are deleted, moved out of the managed folders, or after a batch reorganisation. The catalog must only contain rows whose file exists at the recorded `ContractLocation/FilePath`.

---

## Deferred / Future Enhancements

- **DocType-based sorting** — Exhibits, Amendments, SOWs may need different rules (e.g., stay with parent contract). Not yet implemented.
- **Two-format signature detection** — improve graphic signature block detection beyond "flag for review"
- **Auto-archive workflow** — tooling to present `Review` items to a human for archive confirmation

---

## Non-Expiring Documents — Classification Policy
**Established:** 2026-06-21
**Applies to:** All contract types with no expiration date in contract-catalog.csv

### Rule
Contracts with no stated expiration date are classified as one of:

| Classification | Meaning | Examples |
|---------------|---------|---------|
| **On-Notice** | Active and terminable by either party with written notice per contract terms | NDAs, MNDAs, MSAs, evergreen service agreements |
| **N/A** | Expiration concept not applicable to this document type | One-time licenses, certifications, permits, single-transaction POs |

### Operational rules
- Non-expiring documents are NEVER moved to "04 Expired Contracts" by the expiration archiving workflow.
- Non-expiring documents are NOT subject to expiration-date-based status changes.
- Termination or archiving of On-Notice and N/A documents requires an explicit manual action — see NEAR_TERM_ENHANCEMENTS.md E22 for the planned catalog workflow.
- The ExpirationDate field in contract-catalog.csv is left blank for these documents. A blank ExpirationDate is the system signal for On-Notice or N/A classification.
- SigningStatus for On-Notice documents = "Signed". SigningStatus for N/A documents = as applicable.

### Prior action
92 NDAs/MNDAs previously moved to "04 Expired Contracts" in error were restored to "01 Active Contracts" per this policy.

**Correction (2026-07-14):** that restore **copied instead of moving**, leaving a byte-identical twin of each contract behind in `04 Expired Contracts`. `04` had become a stale shadow of `01`. This was found by hashing the disk during Phase 3 reconciliation and has been cleaned up. It is the reason the conventions below exist.

---

## Conventions (established 2026-07-14)

These were learned the hard way across the Phase 1–4 catalog cleanup. They are load-bearing; breaking one of them has already cost real data.

### Folder naming

Name a vendor folder after **the counterparty's legal name as it appears in the signed document** — not the filename, not an acronym someone typed, not the project name. Drop commas and periods (they are awkward in paths). An acronym in parentheses is fine where it aids recognition: `Applied Technology Group (ATG)`, `United States Postal Service (USPS)`.

Use **ASCII for folder names** — a bare `ö` in a path survives Windows but keeps getting mangled somewhere along the CSV → HTML → Azure chain. **Data fields carry full Unicode**, so `CounterpartyName` is `Körber Supply Chain LLC` while the folder is `Korber Supply Chain LLC (KSC)`.

Read the document before you name the folder. Folders named from filenames produced `Winery NC` (a filename fragment) and `CVL Lighthouse` (a project name), and folders named from guesswork put an Industrial Controls Electric NDA under `Alice and Olivia` — because "ICE" matches inside "al-**ICE**-and-Olivia".

### Subcontracts

A subcontract files under **the counterparty DCS actually signed with**, never the end client. The Doral subcontract for an Amazon site belongs under `Doral Corp`, not `Amazon`. Client↔contract linkage is future catalog functionality, not something to encode in the folder tree.

### Deletion

**Deletions never destroy.** Move the file to a dated quarantine folder, preserve its `ContractLocation/VendorFolder/` path inside it, and record SHA-256 + byte size in that folder's `MANIFEST.json`.

Do **not** use `os.remove` on this library — on Windows it bypasses the Recycle Bin entirely, and the only remaining copy then lives in the SharePoint *site* recycle bin, which is web-only and cannot be reached from a script. We lost a document that way once and could not get it back without a human going to the web UI.

### CounterpartyName is fill-only

The scanner **never overwrites a non-blank `CounterpartyName`**. Extraction is heuristic, and this is the field humans most often correct by hand to the legal name on the document. Curated values are permanent. `scan-contract.py --recheck-counterparty` forces re-extraction and will clobber them — migration use only.

### Whole-file SHA-256 is NOT a reliable identity test for Office files here

**SharePoint rewrites Office documents on copy-in.** Copy a `.docx` into a synced library and SharePoint injects/refreshes its `customXml` parts (content-type and column metadata, sensitivity labels). The file's bytes and SHA-256 change **while the document itself is untouched** — `word/document.xml` stays CRC-identical.

Demonstrated 2026-07-14: copying `Mutual NDA- Associated Packaging.docx` (33,431 bytes, `32fa4f31…`) into a folder inside the synced library produced a 34,169-byte file hashing `f66ffd6c…`. Same contract, +738 bytes of metadata, completely different hash.

Consequences:

- **Two byte-different `.docx` copies may be the same document.** Before concluding that two Office files differ, compare `word/document.xml` (and the other `word/` parts), not the whole-file hash. A whole-file hash difference confined to `customXml/` is metadata, not content.
- **`move` is safe; `copy` is not.** `shutil.move` within a drive is a rename — the bytes are untouched (all 47 quarantined files still match their recorded hashes). A copy creates a new file, which SharePoint then processes and rewrites.
- PDFs are not affected — this is an Office-format (OOXML) behaviour.

This is why deletions must quarantine by **moving**, and why a hash recorded before a copy will not match after one.

### Catalog uniqueness invariant

**The key is `(ContractLocation, FilePath)`. `FilePath` alone is NOT a key.**

The same relative path legitimately exists in two locations — an unsigned draft in `02` and the signed copy in `01` are two distinct records pointing at two different files. Every tool that reconciles rows against disk must match on the pair. Matching on `FilePath` alone previously caused `audit-catalog.py` to rewrite a row's `ContractLocation` to whichever copy the directory walk happened to reach last, and would have caused `scan-contract.py` to write one file's metadata into a row describing a different file.

---

*Last updated: 2026-07-14*
