---
# BUGLOCK Session Protocol
**Session ID:** 20260620-1146
**Project:** DCS Contract Management Tools — anonymizer (server.py / anonymize.py)
**Branch:** main
**Operator:** jrudyg (CC)
**Date:** 2026-06-20

---

## 1. SUCCESS CONDITION

**Condition:** After `/api/detect` on a file staged in `_anon-private/staging/`, the JSON response includes a `path` field giving the file's post-move location, and `POST /api/apply-redactions` using THAT returned path returns HTTP 200 with `ok:true` (review.json located and applied). The detect→apply round-trip no longer depends on the client knowing the file was moved.
**Verify command:** `python /tmp/verify_buglock.py` (creates a fresh staged test docx, runs detect, then apply using the path the detect response returns)
**Expected output:** `DETECT ... has 'path' field: True` with path `05-In-Process/...`, and `APPLY(returned path) http=200 ok=True`

---

## 2. BLAST RADIUS

Files that could be affected:
- [x] C:\Users\jrudy\OneDrive - Diakonia Group, LLC\Contract Management - SharePoint\Tools\server.py  (detect route response + UI JS `currentFilePath`; apply-redactions route consumes the path)
- [x] C:\Users\jrudy\OneDrive - Diakonia Group, LLC\Contract Management - SharePoint\Tools\anonymization\anonymize.py  (`review_path_for` / `_private_stem` keying logic — in radius, NOT edited by this fix)
- [x] Consumers of the same keying: `/api/de-anonymize`, `/api/quarantine/*` routes in server.py (path-derived review lookup — verify not regressed)

---

## 3. SCOPE BOUNDARY

**Permitted files (CC may edit these):**
- C:\Users\jrudy\OneDrive - Diakonia Group, LLC\Contract Management - SharePoint\Tools\server.py

**Iteration budget:** 3
**Budget rationale:** Root cause already pinpointed with a reproduced baseline; the fix is a localized 2-point change in one file (add `path` to the detect JSON; store it in the UI). 3 leaves margin for a UI-wiring miss without inviting scope creep.

---

## 4. BASELINE SNAPSHOT

**Last-known-good commit:** 42b4cf8
**Pre-session verify result:** FAIL (bug present — apply with the path the UI currently stores returns 404)
**Pre-session verify output:**
```
created staged test file: BUGLOCK_RoundTrip_Test.docx
DETECT  http=200  ok=True
  response keys: ['context_notes', 'ok', 'review_path', 'review_triggers', 'spans']
  has 'path' field: False
  review_path: _anon-private/reviews/05-In-Process_BugLock_Test_Co_BUGLOCK_RoundTrip_Test.review.json
APPLY(staging path)  http=404  ->  {"ok": false, "error": "review.json not found: anon-private_staging_BUGLOCK_RoundTrip_Test.review.json"}
APPLY(moved path)    http=200  ->  {"ok": true, "passed": false, "confirmed": 0, "rejected": 1, ...}
```
Root cause (confirmed): `/api/detect` moves a staged file into `05-In-Process\<party_2>\` (server.py ~846-856) and keys review.json to the moved path (line 899), but returns no `path`; the UI stores the pre-move path (`currentFilePath=relPath`, line 1627) and apply (line 1856) re-derives the review key from that stale staging path → mismatch.

---

## 5. ITERATION LOG

### Iteration 1
**Hypothesis:** Detect must return the post-move doc path, and the UI must store that returned path (not the pre-move relPath) so apply re-derives the correct review.json key.
**Change:** server.py — (1) `/api/detect`: compute `rel_doc` from the post-move `abs_path` and add `"path": rel_doc` to the JSON response (near lines 900 / 911); (2) UI `runDetect()`: `currentFilePath = d.path || relPath` (was `currentFilePath = relPath`, line 1627) so apply at line 1856 sends the post-move path.
**Verify result:** PASS
**Verify output:**
```
created staged test file: BUGLOCK_RoundTrip_Test2.docx
DETECT  http=200  ok=True  has 'path' field: True
  returned path: 05-In-Process/BugLock Test Co/BUGLOCK_RoundTrip_Test2.docx
APPLY(returned path)  http=200  ok=True
APPLY(old staging path) http=404  (expected, client no longer uses this)

VERIFY GATE: PASS
```

---

## 6. RESOLUTION

**Status:** RESOLVED
**Final verify output:**
```
DETECT  http=200  ok=True  has 'path' field: True  -> 05-In-Process/BugLock Test Co/BUGLOCK_RoundTrip_Test2.docx
APPLY(returned path)  http=200  ok=True
VERIFY GATE: PASS
```
**Root cause:** Detect relocates a staged file but does not return the new path; the UI keeps the pre-move path, so apply derives the wrong review.json key.
**Files modified:** server.py — `/api/detect` response (added `rel_doc` + `path`), UI `runDetect()` `currentFilePath` assignment.
**Commit hash:** pending USER approval (uncommitted)

---

## 7. POST-MORTEM (optional)

Not required (single-iteration, well-isolated fix).
