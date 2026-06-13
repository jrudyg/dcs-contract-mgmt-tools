# anonymization/PLAN.md

**P3 Anonymization Pipeline — Design Document**
Version: 1.0 | Date: 2026-06-12 | Status: APPROVED FOR IMPLEMENTATION

---

## 1. Purpose

Produce AI-safe versions of DCS contracts for use in model training, analysis, and
process mining. All real counterparty names, PII, and commercially sensitive terms are
removed while document structure is preserved for downstream NLP.

---

## 2. Source of Truth

| Item | Path |
|------|------|
| Input catalog | `contract-catalog.csv` (812 rows, utf-8-sig) |
| Counterparty source map | `kb/COUNTERPARTIES.md` (540 distinct values) |
| Scope | PDFs and DOCX in `01 Active Contracts/`, `02 Unsigned Contracts/` |

---

## 3. Pipeline Architecture

```
Source file (PDF / DOCX)
        ↓
[Step 1] Text extraction          (PyMuPDF / python-docx)
        ↓
[Step 2] Structure tokenization   (identify structural vs. content spans)
        ↓
[Step 3] Counterparty redaction   (deterministic map — Layer 1)
        ↓
[Step 4] PII detection/redaction  (Presidio + en_core_web_lg — Layer 2)
        ↓
[Step 5] Commercial terms redact  (regex engine — Layer 3)
        ↓
[Step 6] Structure reassembly     (splice structural spans back untouched)
        ↓
anonymization/output/             [name].anon.txt + [name].audit.json
```

---

## 4. Layer 1 — Counterparty Redaction

### 4.1 Mapping construction

- Parse all distinct `CounterpartyName` values from `kb/COUNTERPARTIES.md`
- **Exclude from pseudonym assignment** (do not redact — skip entirely):
  - `(blank)` — no name present; no substitution possible
  - `A. MNDA Template` — template artifact, not a real counterparty
  - `ACI for Signature` — workflow artifact, not a real counterparty
- Sort remaining 537 entries alphabetically (case-insensitive)
- Assign stable pseudonyms: `PARTY-0001`, `PARTY-0002`, … `PARTY-0537`
- Save mapping locally to `anonymization/mapping.json` — **GITIGNORED, NEVER STAGED**

### 4.2 mapping.json schema

```json
{
  "generated": "<ISO-8601 timestamp>",
  "version": 1,
  "excluded": ["(blank)", "A. MNDA Template", "ACI for Signature"],
  "entries": {
    "A-Line Striping": "PARTY-0001",
    "ABC Company":     "PARTY-0002"
  }
}
```

### 4.3 Mapping permanence rule

Once generated, `mapping.json` is **immutable** for a pipeline run. A new run with
`--rebuild-map` regenerates from scratch; without the flag it reloads the existing file.
This prevents pseudonym drift across incremental runs.

### 4.4 Redaction pass

- For each contract file, look up `CounterpartyName` → pseudonym via mapping
- Apply whole-word, case-insensitive regex replacement throughout extracted content spans
- Also replace the `VendorFolder` name (which typically equals the counterparty) using the same map
- Detect common abbreviations in the first 300 characters and add them as aliases for this file's replacement pass

---

## 5. Layer 2 — PII Detection (Presidio + spaCy)

### 5.1 Components

| Component | Version | Role |
|-----------|---------|------|
| `presidio-analyzer` | ≥2.2 | NER-based PII detection |
| `presidio-anonymizer` | ≥2.2 | Token replacement |
| `spacy` | ≥3.7 | NER model host |
| `en_core_web_lg` | ≥3.7 | Large English NER model |

### 5.2 Targeted entity types

| Entity type | Replacement token | Confidence threshold |
|-------------|------------------|----------------------|
| PERSON | `[PERSON]` | 0.75 |
| EMAIL_ADDRESS | `[EMAIL]` | 0.85 |
| PHONE_NUMBER | `[PHONE]` | 0.80 |
| US_SSN | `[SSN]` | 0.90 |
| DATE_TIME | `[DATE]` | 0.70 |
| LOCATION (non-city) | `[LOCATION]` | 0.75 |
| NRP | `[NRP]` | 0.80 |
| US_BANK_NUMBER | `[BANK_ACCT]` | 0.90 |
| CREDIT_CARD | `[CC]` | 0.90 |

### 5.3 Scope constraints

- Do **not** redact: LLC, Inc., Corp., LP, Ltd. when appearing without a preceding name
- Do **not** redact: city and state names used in governing-law or notice-address clauses
- PERSON threshold set at 0.75 to reduce false positives in signature-block boilerplate
  (`By:`, `Name:`, `Title:` labels are structural and never reach this layer)

### 5.4 Layer ordering

Layer 1 (counterparty) runs **before** Presidio. Real company names are replaced with
`PARTY-XXXX` tokens before Presidio analyzes the text, so pseudonym tokens are never
misclassified as PII and never double-redacted.

---

## 6. Layer 3 — Commercial Terms Regex

Applied after the Presidio pass. All patterns use Python `re` with `IGNORECASE | MULTILINE`.

| Pattern | Replacement | Example matches |
|---------|-------------|-----------------|
| `\$[\d,]+(\.\d{1,2})?` | `[AMOUNT]` | $125,000 · $4,500.00 |
| `\d+(\.\d+)?\s*%` | `[PERCENT]` | 3.5% · 15% |
| `\bnet\s*\d+\b` | `[PAYMENT_TERM]` | net 30 · net 45 |
| `\$[\d.]+\s*/\s*\w+` | `[RATE]` | $45/hr · $0.25/mile |
| `\d+\s*(days?|weeks?|months?|years?)` (payment/term context) | `[TERM_DURATION]` | 30 days · 12 months |
| ABA routing number `\b\d{9}\b` (context-gated) | `[BANK_ROUTING]` | 021000021 |

Context-gating for `[TERM_DURATION]`: only fire within 150 characters of payment/fee/term
keywords to avoid redacting innocent numeric durations (e.g., "the 30-year warranty").

---

## 7. Layer 4 — Structure Preservation

Structure tokenization runs before any redaction (Step 2). The following span types are
marked **structural** and bypass all three redaction layers:

| Pattern | Example |
|---------|---------|
| `^(\d+\.)+\d*\s+[A-Z]` | `1.2.3 Definitions` |
| `^#+\s` | `## ARTICLE II` |
| All-caps lines ≥3 words, ≥80% uppercase chars | `INDEMNIFICATION AND INSURANCE` |
| `\bEXHIBIT\s+[A-Z]\b` / `\bSCHEDULE\s+\d+\b` | `EXHIBIT A` |
| Signature block **labels** (not values) | `By:` `Name:` `Title:` `Date:` |

Structural spans pass through to output unchanged. Only content spans enter Layers 1–3.

---

## 8. Output Format

Two files per source contract, written to `anonymization/output/` (gitignored):

### `[VendorFolder]_[filename].anon.txt`

Plain UTF-8 text. Fully redacted, structure-preserved document.

### `[VendorFolder]_[filename].audit.json`

```json
{
  "source_file": "VendorFolder/filename.pdf",
  "counterparty_pseudonym": "PARTY-0001",
  "layers_applied": ["counterparty", "presidio", "commercial_regex"],
  "redaction_count": {
    "counterparty": 14,
    "presidio": 3,
    "commercial_regex": 8
  },
  "redactions": [
    {
      "layer": "counterparty",
      "token": "PARTY-0001",
      "char_start": 142,
      "char_end": 158,
      "occurrence": 1
    }
  ],
  "presidio_entities": [
    { "entity_type": "PERSON", "token": "[PERSON]", "char_start": 890, "char_end": 904, "score": 0.88 }
  ],
  "commercial_terms": [
    { "pattern": "AMOUNT", "token": "[AMOUNT]", "char_start": 1200, "char_end": 1209 }
  ]
}
```

**Audit.json never contains the original counterparty name.** The `counterparty_pseudonym`
field stores the PARTY-XXXX token only. Reverse lookup requires `mapping.json`.

---

## 9. Exclusions (files not processed)

| Condition | Reason |
|-----------|--------|
| `ContractLocation = 03 Archived Contracts` | Out of P3 scope |
| `SigningStatus = Review` | Incomplete metadata; extraction unreliable |
| `CounterpartyName` in excluded set | No valid pseudonym available |
| `IsAmendment = True` | Processed with parent contract only |
| Scanned/image PDFs (<50 chars extracted) | scan-contract.py flags as Review; excluded by above |

---

## 10. Toolchain

```
pip install pymupdf python-docx presidio-analyzer presidio-anonymizer spacy
python -m spacy download en_core_web_lg
```

| Library | Min version | Purpose |
|---------|-------------|---------|
| `PyMuPDF` (fitz) | 1.23 | PDF text extraction |
| `python-docx` | 1.0 | DOCX text extraction |
| `presidio-analyzer` | 2.2 | PII detection engine |
| `presidio-anonymizer` | 2.2 | PII replacement |
| `spacy` | 3.7 | NER model host |
| `en_core_web_lg` | 3.7.x | Large English NER |
| `re` (stdlib) | — | Commercial terms regex |

---

## 11. File Layout

```
anonymization/
  PLAN.md              ← this file (committed to git)
  mapping.json         ← GITIGNORED — local only, never push
  output/              ← GITIGNORED — all .anon.txt and .audit.json files
  samples/             ← GITIGNORED — smoke-test source files
```

---

## 12. Implementation Sequence

| Phase | Deliverable | Status |
|-------|-------------|--------|
| ANON-1 | anonymize.py: full pipeline (all 3 layers), 3-file pilot | COMPLETE (6247756) |
| ANON-2 | build_map.py: 537 pseudonyms + 687 aliases; alias pass integrated | COMPLETE (832a88e) |
| ANON-3 | Full corpus run + audit rollup | NOT STARTED |

---

## 13. Plan Confidence

**Confidence: 97%**

The design is deterministic, the toolchain is mature, and every layer has a known
failure mode with a mitigation:

| Risk | Mitigation |
|------|------------|
| en_core_web_lg false negatives on legal boilerplate (e.g., signature names) | Confidence threshold at 0.75; audit.json enables spot-check |
| PDF text extraction failures (scanned/image PDFs) | Excluded by SigningStatus=Review rule |
| Counterparty name variants not in COUNTERPARTIES.md | Alias detection pass in Layer 1 (first 300 chars) |
| mapping.json accidentally staged | `anonymization/mapping.json` is gitignored; pre-commit check in ANON-2 |

Residual 3% uncertainty: Presidio's recall on legal-specific PII patterns (e.g., custom
clause-embedded SSNs, unusual phone formats). This is an implementation tuning risk, not
a design risk — addressable during ANON-4 smoke testing.

**Confidence ≥ 95%: PROCEED.**
