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

*Last updated: 2026-05-20*
