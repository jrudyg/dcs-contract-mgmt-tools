# NEAR-TERM ENHANCEMENTS — Contract Management Tools
**Version:** 1.1
**Created:** 2026-06-12
**Updated:** 2026-06-12
**Owner:** CAI (maintained at session close)
**Canonical path:** `...\Contract Management - SharePoint\Tools\NEAR_TERM_ENHANCEMENTS.md`
**Note:** Not committed to git unless USER directs — keep out of Azure SWA deploy until reviewed.

---

## TOP PRIORITIES (USER-declared 2026-06-12)

| # | Priority | Description | Status |
|---|----------|-------------|--------|
| P1 | SharePoint as Knowledge Base | Perfect the Contract Management SharePoint as the durable knowledge base — structure, retrieval, currency of contract data and reference material | OPEN |
| P2 | Second Brain | SharePoint + catalog + reference files functioning as a queryable second brain for Contract Management — institutional memory that survives sessions | OPEN |
| P3 | Anonymization Project | Redact/anonymize contract documents to (a) make them safe for AI processing and sharing, (b) comply with customer confidentiality obligations. Scope: counterparty identities, commercial terms (pricing, rates), PII, customer-specific obligations. Must preserve clause structure so analysis remains valid post-anonymization. | OPEN — needs scoping session |
| P4 | In-Process Pipeline | `in-process.html` contract pipeline page — MSAL.js OAuth against Azure AD | BLOCKED — awaiting Azure AD Tenant ID + Client ID from Azure Portal |

---

## ENHANCEMENT BACKLOG

### E1 — Learning Loop Hardening (added 2026-06-12)
**What:** Systematize the session-learning cycle for the Contract Management workstream, mirroring the CCE [LEARN]/[HANDOFF] discipline: capture session learnings → route to durable reference files on SharePoint → enforce via session-open reads, not documentation alone.
**Why:** The model does not learn between sessions; the system must. Externalized learning (reference files + enforcement triggers) is the only mechanism that compounds.
**Components:**
- Designate canonical reference files in this repo (rules, domain knowledge, session log) and a session-open read protocol
- [LEARN] pass at every session close — route items here, to CONTRACT-RULES.md, or to CLAUDE.md
- Anti-pattern capture: when a session repeats a known mistake, the documentation failed — add an enforcement trigger
**Status:** OPEN

### E2 — Catalog rendering defects (carried from current session)
**What:** Literal `&mdash;`/`&hellip;` entities and UTF-8 mojibake in `index.html`.
**Finding (2026-06-12 RECON):** Entities pass through `esc()` before `innerHTML` → double-escaped → render literally. Residual mojibake at L568 (Â§) and L824 (Â·). CSV is clean (812 rows, 0 entity hits). Fix: replace all entities with literal Unicode chars.
**Status:** IN PROGRESS — fix CC prompt issued, awaiting execution + verify
**[LEARN] candidate:** CC marked the entities "intentional — correct"; user-facing screenshot proved otherwise. Rendered-output evidence outranks code-reading conclusions.

### E3 — Status=unknown fix script
**What:** Execute `fix_unknown_status.py` via CC (~60 auto-correct, ~43 ManualReview=Y); confirm results.
**Status:** OPEN — CC recap (2026-06-12) states "All ManualReview flags cleared and pushed" — UNVERIFIED, requires file-backed confirmation

### E4 — 22-vendor manual review queue
**What:** Resolve ManualReview=Y rows; build a manual-review resolution tool.
**Status:** OPEN — possibly resolved per CC recap; verify against CSV

### E5 — Teams status-change notifications
**What:** Notify on contract status changes via Teams. (Outlook email threading deferred to Phase 2.)
**Status:** OPEN

---

## VERSION HISTORY

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-06-12 | Initial — P1–P4 priorities captured from USER; E1 learning-loop item added per USER direction; E2–E5 carried from active backlog |
| 1.1 | 2026-06-12 | P3 scope defined (AI-safe redaction + customer confidentiality compliance). E2 RECON findings + esc() root cause. E3/E4 flagged for verification per CC recap claim. |
