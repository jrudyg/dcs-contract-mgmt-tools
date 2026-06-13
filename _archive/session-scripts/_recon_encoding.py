import csv, re, sys
from pathlib import Path

BASE = Path(r"C:\Users\jrudy\OneDrive - Diakonia Group, LLC\Contract Management - SharePoint\Tools")
HTML_PATH = BASE / "index.html"
CSV_PATH  = BASE / "contract-catalog.csv"

out = []
def p(s=""): out.append(s)

# ── 1. index.html ────────────────────────────────────────────────────────────
p("=" * 70)
p("1. index.html")
p("=" * 70)

html_raw = HTML_PATH.read_text(encoding="utf-8-sig")
lines = html_raw.splitlines()

# 1a. <meta charset>
p("\n--- 1a. <meta charset> ---")
for i, ln in enumerate(lines, 1):
    if re.search(r'<meta[^>]+charset', ln, re.I):
        p(f"  Line {i}: {ln.strip()}")

# 1b. Grep for entity/mojibake patterns
p("\n--- 1b. Pattern grep (cap 20 per pattern) ---")
PATTERNS = {
    "&mdash;":  "&mdash;",
    "&hellip;": "&hellip;",
    "Â":        "Â",
    "â€":       "â€",
}
for label, pat in PATTERNS.items():
    hits = [(i+1, ln) for i, ln in enumerate(lines) if pat in ln]
    p(f"\n  [{label}]  {len(hits)} line(s) match")
    for lineno, ln in hits[:20]:
        # Find position and emit 80-char context
        pos = ln.find(pat)
        start = max(0, pos - 20)
        excerpt = ln[start:start+80].strip()
        p(f"    L{lineno:>5}: ...{excerpt}...")

# 1c. Key code locations
p("\n--- 1c. Key render locations ---")

SEARCHES = {
    "(i) empty-cell placeholder": [
        r"['\"]—['\"]",         # em-dash placeholder
        r"['\"]–['\"]",         # en-dash
        r"\.textContent\s*=\s*['\"].*?['\"]",
        r"No\s+date",
        r"placeholder",
        r"mdash",
        r"&mdash",
        r"innerHTML.*?—",
        r"innerText.*?—",
    ],
    "(ii) filename truncation": [
        r"\.slice\(",
        r"\.substring\(",
        r"truncat",
        r"ellipsis",
        r"\.length\s*[>]",
        r"\.\.\.",
        r"substr",
    ],
    "(iii) Showing X of Y": [
        r"Showing",
        r"showing",
        r"total",
        r"of\s+\w+\s+\·",
        r"\xb7",          # middle dot
        r"·",
    ],
    "(iv) COUNTERPARTY sort indicator": [
        r"COUNTERPARTY",
        r"CounterpartyName",
        r"sort.*?indicator",
        r"sortIndicator",
        r"sort_indicator",
        r"↑|↓|▲|▼|&#8593|&#8595|&#8679|&#8681",
    ],
}

for section, patterns in SEARCHES.items():
    found = {}
    for pat in patterns:
        for i, ln in enumerate(lines, 1):
            if re.search(pat, ln):
                if i not in found:
                    found[i] = ln
    p(f"\n  {section}")
    if not found:
        p("    (no matches)")
    else:
        for lineno in sorted(found)[:8]:
            ln = found[lineno]
            # Detect assignment type
            assign = []
            if "textContent" in ln or "innerText" in ln:
                assign.append("textContent/innerText")
            if "innerHTML" in ln or "template literal" in ln or "${" in ln:
                assign.append("innerHTML/template-literal")
            assign_str = ", ".join(assign) if assign else "other/unknown"
            excerpt = ln.strip()[:120]
            p(f"    L{lineno:>5} [{assign_str}]: {excerpt}")

# ── 2. contract-catalog.csv ──────────────────────────────────────────────────
p("\n")
p("=" * 70)
p("2. contract-catalog.csv")
p("=" * 70)

with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    rows = list(reader)

p(f"\n  Total rows (excl header): {len(rows)}")

# 2b. Scan for &mdash;, &hellip;, Â in any field
ENTITY_PATS = ["&mdash;", "&hellip;", "Â"]   # Â = U+00C2
col_counts = {pat: {} for pat in ENTITY_PATS}
sample_rows = {pat: [] for pat in ENTITY_PATS}

for row in rows:
    for col, val in row.items():
        for pat in ENTITY_PATS:
            if pat in val:
                col_counts[pat][col] = col_counts[pat].get(col, 0) + 1
                if len(sample_rows[pat]) < 3:
                    sample_rows[pat].append((col, row.get("VendorFolder",""), row.get("Filename",""), val))

pat_labels = {"&mdash;": "&mdash;", "&hellip;": "&hellip;", "Â": "Â (U+00C2)"}
for pat in ENTITY_PATS:
    label = pat_labels[pat]
    total = sum(col_counts[pat].values())
    p(f"\n  [{label}]  {total} cell(s) affected")
    if col_counts[pat]:
        for col, n in sorted(col_counts[pat].items(), key=lambda x: -x[1]):
            p(f"    Column '{col}': {n} row(s)")
        p("    Samples:")
        for col, vendor, fn, val in sample_rows[pat][:3]:
            excerpt = val[:100].replace("\n", " ")
            p(f"      VendorFolder={vendor!r}  col={col!r}  val={excerpt!r}")

p("\n" + "=" * 70)
p("END RECON")
p("=" * 70)

report = "\n".join(out)
print(report)

# ── 3. Append to CC_REPORT.md ────────────────────────────────────────────────
import datetime
ts = "2026-06-12"
REPORT_PATH = Path(r"C:\Users\jrudy\CCE\01-projects\CRAR\working\logs\CC_REPORT.md")
header = f"\n\n---\n\n## RECON — catalog entity/encoding defects — {ts}\n\n"
with open(REPORT_PATH, "a", encoding="utf-8") as f:
    f.write(header)
    f.write("```\n")
    f.write(report)
    f.write("\n```\n")
print("\n[CC_REPORT.md updated]")
