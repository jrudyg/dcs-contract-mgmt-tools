# LEARNINGS.md

Durable lessons from CC sessions — patterns that bit us, fixes that worked, invariants that must hold.

---

## 1 — esc()-wrapped HTML entities double-escape and render literally

**Session:** 2026-06-12 (commit 19fc854)

In index.html, using a JavaScript `esc()` helper (which converts `<`, `>`, `&` → HTML entities) on strings that already contain named entities (e.g. `&amp;`, `&lt;`) causes double-encoding: the `&` in `&amp;` itself gets escaped to `&amp;amp;`, so the browser renders the literal text `&amp;` instead of `&`.

**Fix:** Use literal Unicode characters in the source data or in the template strings — never pass already-entity-encoded strings through `esc()`. If the value is safe to embed directly, embed it directly.

**Test:** Render the dashboard in a real browser and visually confirm special characters display as glyphs, not as entity strings. Code-reading alone is insufficient.

---

## 2 — Rendered-output evidence outranks code-reading conclusions

**Session:** 2026-06-12

Multiple times this session a code-reading pass concluded "fix applied" when the rendered output still showed the bug. Root cause: the fix was applied to the wrong escaping layer, and only browser rendering reveals the true output.

**Rule:** For any HTML/display bug, the verify step must be rendered output (screenshot, `curl`, or browser observation), not a code diff. A passing diff is necessary but not sufficient.

**Corollary:** When CC reports a display fix as complete, the verify gate is: "does the live dashboard show correct glyphs?" — not "does the source look correct?"

---

## 3 — Alias detection is load-bearing for counterparty redaction

**Session:** 2026-06-13 (ANON-2)

Abbreviated names (WSI, DMI) will pass a full-name leak check but remain exposed without an alias pass. A scan that only matches `Williams-Sonoma, Inc` will miss `WSI` appearing elsewhere in the same document or in related documents that use the short form.

**Rule:** Always validate counterparty redaction with abbreviation variants, not full names only. An alias pass (word-boundary aware, case-insensitive, min 3 chars) is required alongside the full-name pass to achieve complete coverage.

**How to apply:** `build_map.py` generates abbreviation, short-name, and suffix-stripped aliases for every counterparty. `anonymize.py` applies them in a second pass after full-name replacement. Run both together — neither alone is sufficient.
