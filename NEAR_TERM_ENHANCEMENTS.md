# NEAR-TERM ENHANCEMENTS — Contract Management Tools
**Version:** 1.7
**Created:** 2026-06-12
**Updated:** 2026-06-18
**Owner:** CAI (maintained at session close)
**Canonical path:** `...\Contract Management - SharePoint\Tools\NEAR_TERM_ENHANCEMENTS.md`
**Note:** Not committed to git unless USER directs — keep out of Azure SWA deploy until reviewed.

---

## ARCHITECTURE (declared 2026-06-12)

```
CRAR (orchestrator)
  └── anonymize.py pipeline → anonymized contract text
        └── SharePoint Knowledge Base (UIX + repository)
              ├── MS365 Copilot (retrieval consumer)
              └── SharePoint MCP (P5) ← serves all 3 Claude surfaces
```

**Execution surfaces:**

| Surface | Role |
|---------|------|
| **Claude Desktop (CAI)** | Orchestration, analysis, prompt authoring — direct SharePoint MCP retrieval |
| **Claude Cowork** | Autonomous document/file work — SharePoint file ops, KB maintenance, anonymized output deposit |
| **Claude Code (CC)** | Python execution, git, pipeline runs — anonymize.py, build_map.py, catalog ops |

**Key decisions:**
- CRAR is the analysis orchestrator — anonymized output feeds CRAR agents
- SharePoint is the durable knowledge store AND the user-facing interface
- MS365 Copilot is the retrieval consumer — SharePoint must be Copilot-indexed
- Cowork is the natural agent for SharePoint file deposit after CRAR analysis (no human relay)
- SharePoint MCP (P5) is a shared dependency for all 3 Claude surfaces — not CAI-only
- anonymize.py output format must be CRAR-ingestible (plain text + audit.json sidecar)

---

## TOP PRIORITIES (USER-declared 2026-06-12)

| # | Priority | Description | Status |
|---|----------|-------------|--------|
| P1 | SharePoint as Knowledge Base | SharePoint as durable knowledge store — structure, retrieval, currency. Must be Copilot-indexed. | OPEN |
| P2 | Second Brain | SharePoint + catalog + reference files as queryable second brain — consumed by Copilot, CRAR, and all 3 Claude surfaces via SharePoint MCP | OPEN |
| P3 | Anonymization Pipeline | anonymize.py → CRAR-ingestible output → SharePoint deposit via Cowork. ANON-2 complete (alias detection). | IN PROGRESS |
| P4 | In-Process Pipeline | `in-process.html` — MSAL.js OAuth against Azure AD | BLOCKED — awaiting Azure AD Tenant ID + Client ID |
| P5 | SharePoint MCP | M365 MCP connector — already installed, needs reconnect in Claude.ai Settings → Integrations. Shared dependency for all 3 Claude surfaces. | USER ACTION — reconnect |

---

## PRE-IMPORT SECURITY CERTIFICATION GATE (blocking — applies to E14, E15, E17, and all future code-importing items)

No external code, library, or model weights enter the pipeline until certified
clean by this gate. Certification is file-backed and CAI-verified. CC's "looks
safe" summary is NOT certification — same standard as evidence-over-claims for
completion. A failed or skipped certification is a HARD BLOCK, not a warning.

1. **Source provenance** — pin to the official publisher. Verify the PyPI package
   is genuine, not a typosquat. Pin exact version + hash. No floating versions.
2. **No arbitrary code execution on load** — model loads must not deserialize
   untrusted pickles. HuggingFace `trust_remote_code=True` must be OFF. Prefer
   `safetensors` weights over raw pickle.
3. **Static review before install** — read package source / release diff for:
   non-official network calls, subprocess/eval/exec, out-of-path filesystem
   writes, obfuscated strings. CC performs; CAI certifies with file-backed evidence.
4. **Offline / data-residency check** — confirm the component does not phone home
   or transmit document text externally. Non-negotiable: a model that exfiltrates
   text defeats the pipeline's purpose. Verify no telemetry.
5. **Dependency-tree audit** — transitive dependencies get the same scrutiny as
   the top-level package. One trojaned sub-dependency = the same breach.
6. **Sandbox-first** — first run in an isolated environment against test data,
   never real contracts, until certified clean.

---

## ENHANCEMENT BACKLOG

### E1 — Learning Loop Hardening
**Status:** PARTIALLY COMPLETE — CLAUDE.md session protocol live (8008ed0); kb\LEARNINGS.md at 3 entries. Full enforcement in place.

### E2 — Catalog rendering defects
**Status:** COMPLETE — entities (19fc854), mojibake (fed7fa8). Verified. Deployed.

### E3 — Status=unknown fix script
**Status:** COMPLETE — unknown=0, ManualReview=Y=0 confirmed. CSV clean at 812 rows.

### E4 — 22-vendor manual review queue
**Status:** COMPLETE — ManualReview=Y=0 confirmed.

### E5 — Teams status-change notifications
**Status:** OPEN — not started.

### E6 — CONTRACT-RULES.md: NDA evergreen policy (flagged 2026-06-13)
**What:** NDA/MNDA evergreen policy established in prior sessions (92 NDAs moved Expired→Active) is not documented in CONTRACT-RULES.md. Policy needs exact wording confirmed by USER before adding.
**Status:** OPEN — needs USER confirmation of policy wording.

### E7 — server.py status determination (flagged 2026-06-13)
**What:** CLAUDE.md references server.py (Flask, port 5000, SSE scan UI) as a common command, but architecture is now static Azure SWA. Determine if server.py is: (A) still used for local scan ops, (B) fully replaced and should archive, or (C) occasionally used. Answer determines CLAUDE.md cleanup.
**Status:** OPEN — needs USER input.

### E8 — PLAN.md §12 stale implementation sequence (flagged 2026-06-13)
**What:** PLAN.md §12 lists ANON-2 through ANON-6 as sequential phases, but implementation leapfrogged the plan — anonymize.py was built with all 3 layers in ANON-1, not spread across ANON-3 through ANON-5. §12 needs updating to reflect actual implementation.
**Status:** OPEN — low risk, documentation only.

### E9 — __pycache__/ missing from .gitignore (flagged 2026-06-13)
**Status:** OPEN — trivial fix, bundle with next CC commit.

### E10 — scan-contract.py → anonymize.py integration (flagged 2026-06-13)
**What:** Post-scan trigger to auto-anonymize newly scanned contracts. Currently separate manual workflows.
**Status:** OPEN — needs scoping. ~55% confidence.

### E11 — audit-catalog.py → kb/ auto-refresh (flagged 2026-06-13)
**What:** After scan/audit runs, auto-regenerate COUNTERPARTIES.md and DATA_DICTIONARY.md so KB stays current with catalog changes.
**Status:** OPEN — clear value, needs scoping. ~70% confidence.

### E12 — CRAR ingest format validation (flagged 2026-06-13)
**What:** Verify anonymize.py output (.anon.txt + audit.json) is compatible with CRAR agent input expectations. Knowledge gap — need CRAR project instructions to assess.
**Status:** OPEN — ~45% confidence. Requires CRAR session.

---

### E13 — Party-name conflict resolution card (AIA, upload path)
**What:** On the upload path, when a typed party_2 fuzzy-matches an existing
05-In-Process folder, apply AIA before creating a folder: ALERT (similar folder
exists), INFORM (show candidate folder names + file counts, plus canonical
mapping name if matched), ASK (menu-card: use existing / use canonical / proceed
as typed). Exact match or zero match -> proceed silently. User retains freetext
and final authority. Prevents folder proliferation at entry so no corrective
rename/merge tooling is needed.
**Realizes:** prevention-by-design — corrects the freetext-folder proliferation risk before it can form.
**Scope:** /api/resolve-party endpoint + conflict card in ANON_PAGE upload panel.
Does NOT touch detect_file(), anonymize.py, or the select-from-list path.
**Status:** OPEN — deferred, not built. Phase H lock held. [VALUE] 2.02.

### E14 — GLiNER as native Presidio recognizer (false-negative reduction)
**What:** Register Presidio's native `GLiNERRecognizer` (model
`urchade/gliner_multi_pii-v1`, Apache-2.0, `map_location="cpu"`) as a second
recognizer in the existing AnalyzerEngine. Treat Presidio-vs-GLiNER PERSON
disagreement as a Phase E review signal. Directly serves Design Principle #1
(error asymmetry — a missed name is a breach). spaCy en_core_web_lg is the
weakest link; GLiNER strengthens it.
**Realizes:** Phase F "optional second detector" slot — stronger than the
scrubadub option originally noted.
**Verified:** native `presidio_analyzer.predefined_recognizers.GLiNERRecognizer`
— first-class integration, not a custom build. CPU-capable; no GPU required.
**Gate:** PRE-IMPORT SECURITY CERTIFICATION GATE + host-resource check (model
size / cold-start on the pythonw scheduled-task host; mitigated by existing
lazy-singleton _presidio_engines()).
**Status:** OPEN — ~70% confidence. Highest-value OSS graft. Recommended FIRST of E14–E17. [VALUE] 2.02.

### E15 — Formatted .docx -> .docx output (apply-phase write-back)
**What:** Current shippable output is flat .anon.txt — tables, headers,
numbering, signature structure destroyed; redacted contract no longer usable
AS a contract. Add a write_docx() apply path behind --output-format docx that
replays confirmed spans onto the original document's runs.
**Realizes:** ANON_IMPL_SPEC_v2_2.md Phase F (python-docx write-back — currently
fenced out of scope).
**RISK FLAG (do not ship on optimism):** the cited Java repo
(Lostefra/DocxAnonymizer-core) is NOT Python — unusable as an import. The Python
path is python-docx run manipulation, whose hard cases are (a) a name split
across multiple runs and (b) parties in tables / headers / footers
(python-docx-replace does not handle tables in header/footer/body). These are
exactly where redaction LEAKAGE would hide. MUST NOT ship without the verify
gate running the D1 leakage scan against the OUTPUT docx's extracted text,
including tables and headers — not just the .txt.
**Gate:** PRE-IMPORT SECURITY CERTIFICATION GATE (if python-docx-replace or any
new lib is used) + output-docx verify gate above.
**Status:** OPEN — ~70% confidence (downgraded from proposal's 80% on
run-split/table-header leakage risk). Biggest usability win, highest leakage
risk. [VALUE] 1.39.

### E16 — Presidio entity_mapping for PII reversibility (closes documented D3 gap)
**What:** D3 documents that PII tokens ([PERSON], [DATE_TIME]) are not uniquely
reversible — identical token strings can't map back to distinct originals, so
roundtrip is scoped to PARTY-#### only. Presidio >=2.2 returns a per-instance
entity_mapping from anonymize() and ships a DeanonymizeEngine. Adopt to make
repeated PII instances individually reversible; extend D3 roundtrip to PII.
Counterparty mapping stays as-is (deliberate external dictionary).
**Realizes:** D3 hardening — documented limitation -> full coverage.
**Verified:** native Presidio API — already a dependency, no new package.
**Residency:** entity_mapping reverse data is reversal-capable -> MUST live in
_anon-private\, never in shippable output. Enforce in code path.
**Dependency:** implement AFTER E15 (apply path goes docx-aware) so the apply
path is refactored once, not twice.
**Status:** OPEN — ~60% confidence. Recommended after E15. [VALUE] 1.55.

### E17 — OCR / scanned-PDF support (conditional)
**What:** E4 currently only FLAGS short extraction (probable image PDF). If
scanned contracts are real in the corpus, add OCR so they are anonymizable, not
just flagged.
**Gate:** corpus image-PDF audit (CAI) decides go/no-go BEFORE any scoping +
PRE-IMPORT SECURITY CERTIFICATION GATE on the OCR engine.
**Status:** OPEN — ~40% confidence. ADOPT ONLY IF corpus audit shows real volume.
Lowest priority. [VALUE] 0.77.

---

### E18 — Single canonical catalog architecture
**What:** Collapse the two-file split (`contract-catalog.csv` + `in-process-catalog.csv`/`in-process-detail.json`)
into one canonical `contract-catalog.csv` covering signed / unsigned / archived / expired / in-process. Add
**PartyID** as the canonical entity key. Implement get-or-create entity resolution at 05-In-Process intake
(match VendorFolder, fallback fuzzy on CounterpartyName + aliases; USER confirms ambiguous matches).
`mapping.json` becomes a derived projection of the catalog's PartyID — not a separate source of truth.
**Add:** `05-In-Process` as a ContractLocation value + an in-process Status value.
**GATE:** dedupe CounterpartyName BEFORE assigning PartyIDs — proven necessary by the PARTY-0114 / PARTY-0539
duplicate found this session (H2). Without dedupe-first, the same real-world entity gets two PartyIDs.
**Rationale shift:** the original two-file split (isolate anonymization from active contracts) is superseded —
the **anonymization boundary**, not file separation, is what provides protection.
**Status:** OPEN — MULTI-SESSION. Architecture change; scope before build.

### E19 — Short-token / stopword detection tightening
**What:** Live detect on the Columbia Machine doc (H2) produced 2 counterparty false positives:
PARTY-0418 ("Sick" → SICK sensor brand) and PARTY-0088 (short common-word token). Both were caught by the
human-review gate (fails safe), but they suggest a short-token / stopword filter in the counterparty
detection layer (min-length and/or stopword screen on short ALL-CAPS / common-word aliases).
**Status:** OPEN — non-blocking. Detection-quality improvement; review gate already contains the risk.

### E20 — Bare-token alias ambiguity (global map limitation)
**What:** The defined-party term "Columbia" could not be added as a PARTY-0114 alias because the alias map is
**global** — it would mis-bind Columbia-Okura (PARTY-0538) documents. This surfaces a real gap: entities whose
doc-defined term collides with another entity's name root need a **doc-scoped** (not global) alias mechanism.
`extract_defined_term_bindings()` already provides doc-local aliases for parenthetical defined terms; the gap is
bare-token terms with no parenthetical definition.
**Status:** OPEN — non-blocking. PARTY-0114 has adequate coverage via "Columbia Machine" / "CMI".

---

## OSS LANDSCAPE — EXPLICITLY REJECTED (do not re-litigate)

Source: ANON_OSS_INTEGRATION_PROPOSAL_v1_0.md (GitHub survey, 2026-06-17).

| Candidate | Reason |
|-----------|--------|
| ARX (k-anonymity / l-diversity / t-closeness) | Formal re-identification-risk scoring; overkill for name substitution. Revisit only if statistical residual-risk certification is ever required. |
| Neosync / Greenmask / PIMO / kodex | Database-column anonymizers — wrong domain. |
| masquerade / token-proxy / pasteguard | "Don't leak to the LLM" proxies; reverse-map already covers the reversibility pattern. Not document output. |
| ContextSafe / svan-b (as replacements) | Cross-doc consistency differentiator already met by global mapping.json. Borrow docx technique only (E15). |

---

## GATING CHECKS CARRIED FORWARD (post-corpus)

| Check | Gates | Owner |
|-------|-------|-------|
| Host-resource check (model size / cold-start on pythonw host) | E14 (GLiNER) | CAI/CC |
| Corpus image-PDF audit (count of scanned/image-only PDFs) | E17 (OCR) | CAI |
| Pre-import security certification | E14, E15, E17 | CC executes, CAI certifies |

---

## ANON PIPELINE PROGRESS

| Phase | Commit | Status |
|-------|--------|--------|
| ANON-1 Phase 0 (stranded cleanup) | 4e3e8db | ✅ |
| ANON-1 Phase A (PLAN.md) | 8d857a1 | ✅ |
| ANON-1 Phase B-E (anonymize.py + pilot) | 6247756 | ✅ |
| ANON-2 (build_map.py + alias detection) | 832a88e | ✅ |
| ANON-3 (full corpus run + audit rollup) | not started | — |

---

## VERSION HISTORY

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-06-12 | Initial |
| 1.1 | 2026-06-12 | P3 scope, E2 root cause, E3/E4 flagged |
| 1.2 | 2026-06-12 | Architecture declared. E2/E3/E4 closed. ANON progress table. P5 added. |
| 1.3 | 2026-06-12 | Execution surfaces declared. Cowork role defined. P5 scope updated. |
| 1.4 | 2026-06-13 | ANON-2 complete (832a88e). E6–E12 added from mid-session audit. ANON progress updated. E8/E9 queued for next CC batch. |
| 1.6 | 2026-06-17 | E13 status corrected: deferred, not built (Phase H lock held). Spec Current State table updated via companion edit to ANON_IMPL_SPEC_v2_2.md. |
| 1.7 | 2026-06-18 | H2 PASS closed out. E18 (single canonical catalog, PartyID key, dedupe-first gate — multi-session), E19 (short-token/stopword detection tightening), E20 (bare-token alias ambiguity / global-map limitation) appended from H2 findings. NOTE: requested as E14–E16 but those IDs were already occupied (GLiNER / docx / PII-reversibility) — renumbered to E18–E20 per USER to preserve existing entries. |
| 1.5 | 2026-06-17 | E13 (party-name conflict card, this-session scope) + E14–E17 from GitHub OSS landscape review, re-ranked by evidence-verified [VALUE]: GLiNER (E14) first — native Presidio recognizer, CPU-capable; docx write-back (E15) downgraded 80%->70% on run-split / table-header leakage risk + Java ref unusable. E16 (PII reversibility) sequenced after E15 apply-path refactor. PRE-IMPORT SECURITY CERTIFICATION GATE added (blocking — no external code/weights without file-backed CAI certification). §4 reject list + gating-checks table recorded. Presidio confirmed already in production. |
