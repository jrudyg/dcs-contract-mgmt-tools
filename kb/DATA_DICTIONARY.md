# DATA_DICTIONARY.md

Generated from contract-catalog.csv — 812 data rows (excludes header).

## Column Reference

### ContractLocation
- Type: categorical
- Null/blank: 0
- Distinct values (4):
  - `01 Active Contracts`: 405
  - `02 Unsigned Contracts`: 239
  - `03 Archived Contracts`: 159
  - `04 Expired Contracts`: 9

### VendorFolder
- Type: free-text string
- Null/blank: 0
- Populated: 812

### Filename
- Type: free-text string
- Null/blank: 0
- Populated: 812

### FilePath
- Type: free-text string
- Null/blank: 0
- Populated: 812

### Extension
- Type: categorical
- Null/blank: 0
- Distinct values (4):
  - `.pdf`: 611
  - `.docx`: 165
  - `.doc`: 30
  - `.msg`: 6

### FileCreatedDate — REMOVED 2026-07-14
Dropped from the schema (24 → 23 columns). The column was populated from the
filesystem `st_ctime`, which on a OneDrive-synced library reports the
*rehydration* date, not the document date — so its values were the sync date,
not a contract fact. Use `DateInFilename` (filename parse) or `EffectiveDate`
(document text) instead. See "Never Trust Filesystem Dates" in
`NIGHTLY_CATALOG_JOB.md`.

### DocType
- Type: categorical
- Null/blank: 6
- Distinct values (13):
  - `MNDA`: 558
  - `NDA`: 181
  - `Other`: 24
  - `MSA`: 17
  - `License`: 8
  - `Subcontract`: 5
  - `Amendment`: 3
  - `IPA`: 3
  - `SOW`: 2
  - `EULA`: 2
  - `Other-T&C`: 1
  - `PSA`: 1
  - `PO`: 1

### HasSignedKeyword
- Type: categorical
- Null/blank: 63
- Distinct values (2):
  - `True`: 426
  - `False`: 323

### SigningStatus
- Type: categorical
- Null/blank: 0
- Distinct values (3):
  - `Unsigned`: 397
  - `Signed`: 352
  - `Review`: 63

### IsAmendment
- Type: categorical
- Null/blank: 63
- Distinct values (2):
  - `False`: 747
  - `True`: 2

### AmendmentNumber
- Type: integer (derived/computed)
- Null/blank: 810

### VersionLabel
- Type: free-text string
- Null/blank: 774
- Populated: 38

### DateInFilename
- Type: free-text string
- Null/blank: 658
- Populated: 154

### CounterpartyName
- Type: free-text string
- Null/blank: 5
- Populated: 807

### EffectiveDate
- Type: date (ISO 8601 YYYY-MM-DD)
- Null/blank: 191
- Populated: 621
- Range: 2015-04-06 to 2026-05-19

### ExpirationDate
- Type: date (ISO 8601 YYYY-MM-DD)
- Null/blank: 591
- Populated: 221
- Range: 2019-04-06 to on notice

### DaysUntilExpiration
- Type: integer (derived/computed)
- Null/blank: 547
- Range: -2610 to 2143

### Notes
- Type: free-text string
- Null/blank: 719
- Populated: 93

### Status
- Type: categorical
- Null/blank: 0
- Distinct values (5):
  - `unsigned`: 398
  - `active`: 393
  - `expired`: 15
  - `archived`: 4
  - `renewed`: 2

### SurvivalRunning
- Type: categorical
- Null/blank: 795
- Distinct values (1):
  - `Y`: 17

### Stale
- Type: categorical
- Null/blank: 505
- Distinct values (1):
  - `Y`: 307

### SurvivalEndDate
- Type: date (ISO 8601 YYYY-MM-DD)
- Null/blank: 795
- Populated: 17
- Range: 2027-02-11 to perpetual

### ManualReview
- Type: categorical
- Null/blank: 812
- Distinct values (0):

### ManualReviewNote
- Type: free-text string
- Null/blank: 812
- Populated: 0
