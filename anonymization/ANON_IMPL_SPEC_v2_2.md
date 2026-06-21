# Anonymizer Implementation Spec
**Version:** 2.2
**Date:** 2026-06-15
**Status:** DRAFT — pending USER review
**Replaces:** v2.1 (audit fixes: filename anonymization B0.7, roundtrip scoped D3, score-floor display-not-drop A2, pre-apply backup+lock D0, structure ordering constraint B0.3, PLAN threshold reconcile G2; #6 multi-machine private-folder residency DEFERRED)
**Scope:** P3 Anonymization Pipeline — completion to production-ready, verification-gated state
**Out of scope:** P1 SharePoint KB, P2 Second Brain, P4 In-Process Pipeline, P5 SharePoint MCP, E10, E12

---

## Design Principles

1. **Error asymmetry governs everything.** A false negative (sensitive data survives) is a confidentiality breach. A false positive (over-redaction) only reduces document usefulness. The system biases toward over-redaction and forces human review on anything that could be a missed identity.
2. **Automated confirmation is earned, not default.** A span is auto-confirmed only when verification is clean AND confidence is high. Ambiguous detections and suspected misses always route to a human.
3. **Context up front reduces work downstream.** The user knows the parties and document type before detection runs. Capturing that in the UI makes detection precise instead of guessing.
4. **Decisions compound.** Every confirm/reject is written to a global decisions library so the same call is never made twice.
5. **Verify the output, not just the process.** Every apply run is followed by an automated leakage scan and roundtrip check before the output is considered shippable.
6. **Data residency by sensitivity.** Tooling and non-sensitive reference → GitHub (diff/version/deploy). Documents and anonymized output → SharePoint (Copilot/MCP retrieval). Anything that reverses anonymization (mapping.json, decisions_library.json, review/verify sidecars) → a private folder outside every git tree, never committed, never Copilot-indexed.
   - **6a. Web-research carve-out (USER-approved 2026-06-21).** Bare counterparty/organization NAMES IN ISOLATION may be researched on the public web to resolve entity-identity questions (is X an abbreviation / subsidiary / brand of Y). Permitted ONLY when: (a) the query contains the org name alone — no contract text, no commercial terms, no PII, no DCS context; (b) the purpose is entity resolution, not contract analysis; (c) results are treated as inference and flagged as such unless the source is authoritative. Does NOT relax Principle #6: no contract text, PII, or commercial terms ever leave the boundary un-anonymized.

---

## Current State

| Item | Status |
|------|--------|
| anonymize.py — detect/apply split | ✅ Built (e188afe, 11d42fc) |
| server.py — 4 new routes + /restore | ✅ Built |
| ANON_PAGE — two-phase review UI | ✅ Built |
| A0 — Storage segregation (_anon-private\) | ✅ Built + verified |
| A1 — Three detection bug fixes | ✅ Built + verified |
| A2 — Score floor (display, not drop) | ✅ Built + verified |
| B0.1–B0.7 — Context-aware detection | ✅ Built + verified |
| B1 — Context form (UI + /api/detect body) | ✅ Built + verified |
| B2.1 — TERM_DURATION context-gated | ✅ Built + verified |
| B2.2 — Non-$ amount formats | ✅ Built + verified |
| C1 — Decisions library store | ✅ Built + verified |
| C2 — Library applied in review (two-section UI) | ✅ Built + verified |
| C3 — Library write-back on Apply | ✅ Built + verified |
| D0 — Pre-apply backup + corpus lock | ✅ Built + verified |
| D1 — Leakage scan | ✅ Built + verified |
| D2 — Counterparty dictionary sweep | ✅ Built + verified |
| D3 — Roundtrip check (counterparty tokens) | ✅ Built + verified |
| D4 — Orphan token scan | ✅ Built + verified |
| D5 — Verification report (.verify.json) | ✅ Built + verified |
| Quarantine flow (override/discard/list) | ✅ Built + verified |
| Alias map rebuilt (660 aliases) | ✅ Built + verified |
| End-to-end: Colmac detect→apply→de-anon | ✅ Passed |
| E — Mandatory human-review triggers (E1–E4) | ✅ Built + verified |
| F — rapidfuzz wired into D1/D2 | ✅ Built + verified |
| G1 — __pycache__ in .gitignore | ✅ Built |
| G2 — PLAN.md §5.2 + §8 + §11 reconcile | ✅ Built (6fb93b5) |
| B0.6a — DATE_TIME NDA down-tier | ✅ Built + verified (2026-06-21) |
| G3 — CONTRACT-RULES.md NDA evergreen | ⛔ Blocked (USER wording pending) |
| G4 — audit-catalog.py kb/ auto-refresh | 🔲 Open (unscoped) |
| H1 — Pre-run audit (3 eligible files, mapping verified) | ✅ Complete |
| H0a — secure_filename() path-mangling fix | ✅ Built + committed |
| H0b — _short_name() word-count guard + COMMON_WORDS +40 | ✅ Built + committed |
| H0c — 05-In-Process\<party_2>\ auto-create on detect | ✅ Built + committed |
| H0d — Staged-file move into party folder before detect_file() | ✅ Built + committed |
| H0e — Freetext combobox for party_2 + contract_type | ✅ Built + committed |
| H0f — COUNTERPARTIES_MANUAL.json + merge_manual() in build_map.py | ✅ Built + committed |
| H0g — GET /api/status health-check route | ✅ Built + committed |
| H2 — Detect-only run (Columbia Machine Inc proposal) | ✅ PASS — PARTY-0114 bound 5 cp/alias spans (2 full-name + 3 "Columbia Machine"), live /api/detect, no Okura collision. PARTY-0539 dup merged into PARTY-0114. |
| H3 — Audit rollup -> AUDIT_ROLLUP.md | ❌ Not started |
| H4 — Spot-check (5 files) | ❌ Not started |
| H5 — Bulk apply (verification-gated) | ❌ Not started |

---

## PHASE A0 — Storage Segregation (sequences first)

Move sensitive artifacts outside any git working tree before the corpus run accumulates them. Decision: Option B now; Option C (anonymized output deposited into the Copilot-indexed document tree) deferred until Phase D verification is live and green.

### A0.1 — Create private folder
`Contract Management - SharePoint\_anon-private\` — outside `Tools\` (the git tree), outside any repo. Holds reversal-capable artifacts.

### A0.2 — Relocate mapping + library
Move `mapping.json` and `decisions_library.json` to `_anon-private\`. Point `anonymize.py` at them via absolute-path config constants (not relative to `Tools\`). Pipeline reads/writes there.

### A0.3 — Sidecar placement
`.review.json` and `.verify.json` stay next to the source document (in the SharePoint *document* tree, not `Tools\`). They are transient working files; the document tree is already the confidential zone. They are NOT committed and NOT deposited anywhere Copilot indexes.

### A0.4 — Harden Tools\.gitignore (belt-and-suspenders)
Even though A0.2 moves the files out of reach, explicitly ignore in `Tools\.gitignore`:
```
mapping.json
decisions_library.json
*.review.json
*.verify.json
__pycache__/
```

### A0.5 — Failure mode
If `_anon-private\` is missing/renamed, the pipeline fails LOUD at startup (FileNotFoundError on mapping load) — not silent. Acceptable: a broken run is recoverable; a silent leak is not.

**Exit gate:** `git status` in `Tools\` shows no sensitive artifacts as tracked or untracked-pending. Pipeline runs reading mapping from `_anon-private\`. A deliberate `git add -A` stages nothing sensitive.

**Deferred (Option C, gated on Phase D):** depositing verified-clean `.anon.txt` into the SharePoint document tree for Copilot/MCP retrieval. Only after leakage scan + dictionary sweep pass — indexing an unverified output could surface a missed name.

---

## PHASE A — Bug Fixes + Score Floor (current session)

### A1 — Three bug fixes (already prompted)
1. Alias pass runs on `cp_redacted`, not `raw_text`
2. `ALIAS_STOPWORDS` filter
3. Remove `TERM_DURATION` from `COMMERCIAL_PATTERNS`

### A2 — Presidio score floor (display vs. auto-confirm)
**Decision:** the floor governs *auto-confirm*, not *display*. Dropping low-score detections entirely would bias toward under-redaction (Principle 1 violation) — a 0.30 PERSON hit could be a real name silently removed before review.

- Detections with `score < 0.35` are **still shown** in the review table, **pre-rejected by default**, visually muted.
- Detections `0.35 ≤ score < 0.60` (PERSON especially) are shown, **pre-confirmed off** — require explicit human decision (Phase E).
- Only `score ≥ 0.60` is eligible for auto-confirm in bulk flows.
- The offset-1243 noise (0.05 SSN/BANK) appears pre-rejected and muted rather than vanishing — the reviewer sees what was caught and why it was dropped.

**Rationale:** preserves error asymmetry. Nothing is silently dropped at detect; the human always sees the full catch list. The floor only changes the *default*, never *visibility*.

**Exit gate:** offset-1243 triple-hit appears pre-rejected/muted (not absent); PHONE_NUMBER 0.40 appears pre-confirmed-off for decision.

---

## PHASE B0 — Context-Aware Detection (the "how Claude does it" layer)

This phase ports the techniques an attentive human uses. Ordered low→high complexity.

### B0.1 — Defined-term binding extraction
Parse the first 1,000 characters for defined-term bindings:
- `("DCS")`, `(the "Company")`, `(hereinafter "Supplier")`, `(\u201cBuyer\u201d)`
- Pattern: `\(\s*(?:the\s+|hereinafter\s+)?["\u201c]([A-Z][A-Za-z0-9 &]{1,40})["\u201d]\s*\)`

For each binding, determine which party it labels (nearest preceding capitalized name within 60 chars) and add the abbreviation as a **document-local alias** bound to that party's token. Document-local aliases override the global alias map and are immune to the stopword filter (they are explicitly declared in the document).

**Why:** This is how "DCS" gets caught and bound to the same token as "Designed Conveyor Systems" — without the generic-word collision that broke the global alias pass.

### B0.2 — Role-label do-not-redact list
Defined terms that are role labels (BUYER, SELLER, COMPANY, SUPPLIER, CONTRACTOR, CLIENT, VENDOR, PURCHASER) are structural, not identities. Extract them from the binding pass and add to the per-document do-not-redact set so they survive in the output (they carry meaning without revealing identity).

### B0.3 — Simplified structure detection
Two rules replace the five-pattern STRUCTURAL_PATTERNS approach:
1. Lines where >80% of alphabetic characters are uppercase → structural
2. Lines matching `^\s*(\d+\.)+\s` → structural

Structural span char-ranges are excluded from all three detection layers entirely (not shown in review table). Plus the signature-label set (`By:`, `Name:`, `Title:`, `Date:`, `Signature:`) as line-start matches.

**Ordering constraint (resolves B0.2/B0.3 conflict):** counterparty + defined-term detection (B0.1, Layer 1) runs BEFORE structure exclusion. A line that is just an all-caps counterparty name (e.g. `DESIGNED CONVEYOR SYSTEMS` in a signature block) must be redacted, not skipped as structural. Sequence: detect counterparty/alias spans first → then compute structural ranges → then EXCLUDE any structural range that does NOT already contain a counterparty span. A structural line containing a counterparty match stays in play for that match.

**Why:** Covers ~95% of section headers, article titles, and exhibit labels with two rules. Errs toward leaving structure alone — but never lets an all-caps company name hide behind the uppercase rule.

### B0.4 — Signature-block zone suppression
Detect signature-block zones: any region where `By:` / `Name:` / `Title:` / `Date:` appear within 10 lines of each other. Within those zones, redact only PERSON entities — suppress LOCATION, NRP, DATE_TIME (they are boilerplate labels, not sensitive).

### B0.5 — Commercial context tagging
For each commercial span, search ±200 chars for clause-context keywords and tag with `context_type`:
- payment / invoice / due / net → `payment`
- liability / indemnif / cap / exceed → `liability_cap`
- insurance / coverage / policy → `insurance`
- else → `other`

Expose `context_type` in the review table so insurance-standard amounts can be bulk-rejected. Does not change detection — only annotation for review efficiency.

### B0.6 — Contract-type detection tuning
Contract type (from context form, see B1) seeds detection weight only:
- NDA → lighter commercial scanning (NDAs rarely contain pricing)
- SOW / PO → full commercial scanning
- MSA → full all layers

Contract type does NOT key the decisions library (see Phase C).

#### B0.6a — DATE_TIME down-tiering for NDA contract types (2026-06-21)
**Finding:** corpus RECON (02 Unsigned + 03 Archived, n=180 docx) showed the NDA population is 98% NDA documents. Presidio layer-isolated FP analysis: 44 of 54 Presidio spans (81%) are DATE_TIME, all ≥0.60 confidence, all body-text false positives (signing dates, effective dates, term dates). Floor tightening cannot reduce them — they sit in the high-confidence band. Fix: recognizer down-tiering.

**Rule:** when `contract_type` is in `CONTRACT_TYPE_SUPPRESS_DATE_TIME` (same gate as B0.6), `DATE_TIME` is excluded from the active Presidio entity list for that detect run. DATE_TIME remains active for SOW/MSA/PO where payment-due and milestone dates are genuinely sensitive.

**Implementation:** `CONTRACT_TYPE_SUPPRESS_DATE_TIME` constant added to `anonymize.py` (mirrors `CONTRACT_TYPE_SKIP_COMMERCIAL`). `detect_file()` builds `_active_entities` at runtime — DATE_TIME filtered out for NDA contract types. Log line: `B0.6a contract_type=<x> → DATE_TIME excluded from Presidio entities`.

**Corpus eval scope finding (recorded here):** the 02 Unsigned + 03 Archived `.docx` corpus is NDA-homogeneous. SOW/MSA FP signal requires either (a) PDF detect path (235 uncounted PDFs in same folders) or (b) scoping 01 Active Contracts. Next corpus-eval phase must extend to one of these to measure DATE_TIME behavior on commercial doc types. See NEAR_TERM_ENHANCEMENTS.md for queued scope extension.

### B0.7 — Filename anonymization
**The output filename itself leaks.** Source is `New Supplier Packet - Rev 3_ WALMART -DCS - Colmac Reviewed 060226.docx` — counterparty names survive in `.anon.txt` / `.audit.json` / `.review.json` filenames and in the `source_file` field of audit.json.

Rule:
- The `.anon.txt` and its sidecars get a **sanitized output stem**: replace any counterparty name, document-local alias, or confirmed-redact original_text occurring in the filename with its token. `WALMART` → `PARTY-####`, `DCS` → its token, `Colmac` → its token.
- The `source_file` field in audit.json stores the **sanitized** name, not the original. (The original→sanitized mapping lives only in the review.json kept in the private/document zone, never in shippable output.)
- Apply the same filename sanitization pass used for content: run the counterparty + alias map against the filename string.
- If sanitization leaves the stem empty or collision-prone, fall back to a hash-based stem (e.g. `anon_<8charhash>`).

**Why:** a filename is metadata that travels with the file. An anonymized document named after its counterparties is not anonymized.

**Exit gate:** output files for the Colmac doc contain no real counterparty name in their filenames; audit.json `source_file` is sanitized.

---

## PHASE B1 — Context Form (UI)

Add a context form to the `/anonymize` Phase 1, shown before Detect runs. Posted to `/api/detect` in the request body.

**Fields:**
1. **Contract type** — dropdown: NDA / MSA / SOW / PO / Amendment / Other
2. **Party 2 (counterparty)** — text, pre-filled from folder name if detectable, editable
3. **Additional parties** — textarea, one name per line (subcontractors, affiliates named in doc)
4. **Ignore governing-law jurisdiction** — single checkbox
5. **Ignore standard industry bodies / public agencies** — single checkbox (OSHA, ISO, ANSI, UL, NFPA, EPA, etc. — maintained as a built-in list)

Party 1 is always "Designed Conveyor Systems" — implicit, not shown as a field.

**Request body to /api/detect:**
```json
{
  "path": "05-In-Process/Vendor/file.docx",
  "context": {
    "contract_type": "MSA",
    "party_2": "Columbia-Okura",
    "additional_parties": ["Colmac", "Walmart"],
    "ignore_jurisdiction": true,
    "ignore_industry_bodies": true
  }
}
```

`detect_file()` uses context to:
- Seed document-local aliases with party_2 + additional_parties
- Add jurisdiction terms and industry-body list to the per-document do-not-redact set when checkboxes are on
- Apply contract-type detection weighting (B0.6)

---

## PHASE B2 — Detection Quality (carryover from v1.0)

### B2.1 — TERM_DURATION context-gated reintroduction
Reintroduce TERM_DURATION (removed in A1) with bidirectional 150-char context gate on payment/fee/term/invoice/due/net/billing keywords. Only fires near commercial context; warranty-duration language excluded.

### B2.2 — Non-$ amount formats
Add patterns requiring comma or decimal to avoid bare-integer + currency-code false positives:
```python
(re.compile(r'\d[\d,]*\.\d{2}\s*(?:USD|EUR|GBP|CAD)\b', re.IGNORECASE), '[AMOUNT]'),
(re.compile(r'(?:USD|EUR|GBP|CAD)\s*\d[\d,]*\.\d{2}', re.IGNORECASE), '[AMOUNT]'),
```

---

## PHASE C — Decisions Library

A global library of past confirm/reject decisions that pre-populates the review.

### C1 — Library store
File: `anonymization/decisions_library.json` (gitignored — may contain original strings).
Schema:
```json
{
  "version": 1,
  "updated": "2026-06-15T...",
  "decisions": {
    "OSHA|NRP": {"original_text": "OSHA", "entity_type": "NRP", "decision": "reject", "count": 7, "last_seen": "2026-06-15"},
    "Walmart|PARTY": {"original_text": "Walmart", "entity_type": "counterparty", "decision": "confirm", "count": 12, "last_seen": "2026-06-15"}
  }
}
```
**Key:** `f"{original_text}|{entity_type_class}"` — GLOBAL, not contract-type scoped. A name is a name everywhere; a non-sensitive term is non-sensitive everywhere.

### C2 — Library applied in review
`/api/detect` cross-references each detected span against the library. The review UI presents two sections:

**Section 1 — Library matches** (collapsed by default)
Header: "These were auto-decided from N previous decisions — confirm or override."
Rows: original text · entity type · prior decision · library count. Each row flippable.

**Section 2 — New detections** (expanded)
Standard review table for spans with no library match.

### C3 — Library write-back
On Apply, every decision (both sections, including overrides) is written back to the library: increment count, update last_seen, flip decision if overridden. New `/api/apply-redactions` behavior — no schema change to review.json.

---

## PHASE D — Output Verification (runs automatically after every Apply)

The verification layer. Apply does not report success until these pass.

### D0 — Pre-apply safety (backup + lock)
Before apply writes any output:
- **Backup:** if `.anon.txt` / `.audit.json` / `.verify.json` already exist for this stem, copy each to `<name>.bak` before overwrite (mirrors the catalog `.csv.bak` pattern). A bad apply never destroys a prior good output.
- **Single-writer lock:** the bulk corpus run (H5) asserts a lock file `_anon-private\.corpus-run.lock` at start, removed at end. If present, interactive `/anonymize` apply and any concurrent corpus invocation refuse to write and report "corpus run in progress." Prevents CAI/CC/Cowork write collisions per the multi-agent same-file rule. Interactive single-file applies do not lock (one file, one writer).

### D1 — Leakage scan (apply-phase correctness)
For every confirmed-redact span, grep the produced `.anon.txt` for its `original_text` (exact + fuzzy via rapidfuzz, ratio ≥ 90). **Zero hits required.** Any hit = a redaction that didn't land (offset bug, encoding mismatch). **HARD STOP** — `.anon.txt` is marked NOT SHIPPABLE.

### D2 — Counterparty dictionary sweep (detect-phase miss)
Independent of the review map: scan `.anon.txt` against the full mapping.json counterparty name list (exact + fuzzy ratio ≥ 92). Any surviving real counterparty name = detection missed it entirely. **HARD STOP + flag for human review.**

### D3 — Roundtrip check (silent corruption) — counterparty tokens only
**Constraint:** PII tokens are NOT uniquely reversible. Multiple `[PERSON]` / `[DATE_TIME]` tokens are identical strings, so a token→original reverse map cannot know which original belongs to which position. A naive "de-anonymize and diff exact" fails on any document with 2+ same-type PII entities. So roundtrip is scoped to what IS uniquely reversible:

- **Counterparty/alias tokens** (`PARTY-####`) are uniquely numbered → fully reversible. Roundtrip restores these and diffs.
- **PII and commercial tokens** are verified by *position*, not by restoration: confirm that each confirmed PII/commercial span's char-range in the original now contains the expected token in the output, and that no two distinct originals collapsed to the same offset.
- Diff is computed on the counterparty-restored text vs. original with PII/commercial regions masked identically on both sides.

Mismatch in the counterparty roundtrip = token collision or lost span. **HARD STOP.**
Positional mismatch on PII/commercial = offset drift. **HARD STOP.**

**Why scoped:** the original "de-anonymize, diff exact" was unrunnable — it would always fail on repeated PII tokens. This verifies reversibility where it exists and positional integrity where it doesn't.

### D4 — Orphan token scan
Grep `.anon.txt` for any `PARTY-\d{4}` or `\[[A-Z_]+\]` token with no corresponding confirmed span in the review map. Catches accidental token injection. **WARN** (not hard stop — surfaces for review).

### D5 — Verification report
Every apply writes `<stem>.verify.json`:
```json
{
  "leakage_scan": {"pass": true, "hits": []},
  "dictionary_sweep": {"pass": true, "survivors": []},
  "roundtrip": {"pass": true, "diff_chars": 0},
  "orphan_tokens": {"pass": true, "orphans": []},
  "shippable": true
}
```
`shippable: false` if any HARD STOP fails. UI shows verification result; `.anon.txt` is not offered for download/use unless `shippable: true`.

---

## PHASE E — Mandatory Human-Review Triggers

Conditions that override auto-confirmation and force explicit human decision. Applied in both interactive (`/anonymize`) and bulk (corpus) flows.

| Trigger | Action |
|---------|--------|
| Leakage scan finds surviving counterparty name (D2) | HARD STOP — cannot ship |
| Roundtrip diff fails (D3) | HARD STOP — cannot ship |
| File produces 0 counterparty redactions but catalog row has a real CounterpartyName | Flag — do not auto-confirm; route to manual review |
| Presidio PERSON entity score 0.35–0.60 | Present for explicit decision; never auto-confirm |
| Commercial span tagged `liability_cap` | Default confirm but highlight (high sensitivity) |
| Extraction yields < 50 chars | Skip — flag as probable scanned/image PDF |

---

## PHASE F — Tooling Additions

| Tool | Use | When |
|------|-----|------|
| `rapidfuzz` | Fuzzy matching in leakage scan + dictionary sweep (catches "Wal-Mart" vs "Walmart") | Phase D — add now |
| `scrubadub` | Optional second PII detector; disagreement with Presidio = review signal | Optional, post-corpus |
| `python-docx` write-back | Future: redact into formatted .docx instead of flat .txt | Out of scope — noted |

Add to toolchain: `pip install rapidfuzz`

---

## PHASE G — Housekeeping

- **G1 (E9):** add `__pycache__/` to .gitignore
- **G2 (E8):** update PLAN.md §12 to reflect actual implementation (detect/review/apply/restore + verification). **Also reconcile two stale sections:** §5.2 specifies per-entity Presidio thresholds (PERSON 0.75 etc.) but implementation uses a flat 0.35 display-floor with auto-confirm at 0.60 (A2) — update §5.2 to match. §8 audit schema differs from the shipped audit.json schema — update §8 to the as-built schema. Note the threshold *philosophy* change: PLAN.md assumed drop-below-threshold; implementation surfaces-but-pre-rejects.
- **G3 (E6):** CONTRACT-RULES.md NDA evergreen policy — **blocked on USER confirming exact wording**
- **G4 (E11):** audit-catalog.py → kb/ auto-refresh — run only when CounterpartyName values change (pre/post CSV hash compare). Flag OPEN until scoped.

---

## PHASE H — Corpus Run (ANON-3)

**Prerequisite:** A, B0, B1, B2, C, D, E complete and verified.

### H1 — Pre-run audit
Count eligible files (01+02, not Review, mapped counterparty, not amendment). Verify mapping.json covers all counterparty names. **Unmapped names = fail loudly, fix mapping first** (silent add risks pseudonym drift).

### H2 — Detect-only run
`anonymize.py --detect-only` across eligible files → `.review.json` per file. No output yet. Capture to `DETECT_RUN_LOG.txt`.

### H3 — Audit rollup → `AUDIT_ROLLUP.md`
- Files processed / errors
- Spans by layer
- Files with 0 counterparty spans but real CounterpartyName (Phase E trigger)
- Presidio entities score < 0.60 appearing > 20 times across corpus (review candidates)
- Files with 0 commercial terms (possible extraction/regex gap)

### H4 — Spot-check (5 files)
Selected from rollup OUTLIERS (not random): 0-counterparty files, >50-commercial files, 1 each of NDA/MSA/SOW/PO. Full detect→review→apply→verify cycle on each.

### H5 — Bulk apply (verification-gated)
Auto-confirm spans + apply for all eligible files. **Every file runs Phase D verification.** Any file failing a HARD STOP or hitting a Phase E trigger is pulled from the auto-confirm batch and routed to a manual-review queue. Clean files ship; flagged files wait for human decision.

---

## Execution Order

```
A0 (storage segregation) → A1 (bugs) → A2 (score floor: display vs auto-confirm) → restart → verify detect clean
  → B0.1–B0.3 (defined terms, role labels, structure w/ ordering constraint) → verify
  → B1 (context form UI) → B0.4–B0.7 (sig zone, commercial tags, type tuning, filename anonymization)
  → B2 (TERM_DURATION gated, amount formats)
  → C (decisions library) → D0 (backup+lock) → D (verification) → E (review triggers) → F (rapidfuzz)
  → A3/A4 equivalent: full e2e test (detect→review→apply→verify→restore) on Colmac
  → G1+G2+G4 (housekeeping commit); G3 after USER wording
  → H (corpus run)
```

---

## Files Changed

| File | Phases |
|------|--------|
| `_anon-private\` (new folder, outside git) | A0.1 |
| `anonymization/anonymize.py` | A0.2, A1, A2, B0.1–B0.7, B2, D0, D (verify functions) |
| `server.py` | B1 (context form in ANON_PAGE + /api/detect body), C2 (library sections in review UI), C3 (write-back) |
| `_anon-private\mapping.json` | A0.2 (relocated, gitignored) |
| `_anon-private\decisions_library.json` | A0.2 + C1 (relocated, gitignored, generated) |
| `<document tree>\<stem>.verify.json` | D5 (generated per file, sidecar) |
| `.gitignore` | A0.4, G1 |
| `anonymization/PLAN.md` | G2 |
| `kb/CONTRACT-RULES.md` | G3 (blocked) |
| `requirements` / pip | F (rapidfuzz) |

---

## Verification Self-Check (applied to this spec)

- **Correctness:** error asymmetry drives the design; score floor surfaces-not-drops (A2); roundtrip scoped to what's actually reversible (D3). ✓
- **Completeness:** detection, context, library, verification, review triggers, corpus, filename leak (B0.7), backup+lock (D0). ✓
- **Relevancy:** every phase traces to an observed failure — including the two reopened in audit (filename leak you flagged this session; review gate). ✓
- **Recency:** reflects current shipped state + three pending bug fixes. ✓
- **Realism:** B0 techniques are real manual-anonymization moves; roundtrip now runnable; tooling lightweight. ✓
- **Conciseness:** phases ordered low→high complexity; out-of-scope and deferred items explicitly fenced. ✓

## Deferred (multi-machine — revisit after single-machine proven)

- **Private-folder residency (audit #6):** `_anon-private\` currently sits under the OneDrive-synced SharePoint path, so mapping.json (the reverse-identity key) syncs to cloud/other machines. Whether to move it truly local (e.g. `C:\anon-private\`, sync-excluded) is bound up with the multi-machine topology decision in `DEFER_anonymizer-multimachine-topology.md`. Held until single-machine operation is proven, per USER direction.

---

*ANON_IMPL_SPEC_v2_2.md | DCS Contract Management | 2026-06-15*
