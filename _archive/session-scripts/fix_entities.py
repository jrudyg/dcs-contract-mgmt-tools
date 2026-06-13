import csv, shutil
from pathlib import Path

BASE = Path(r"C:\Users\jrudy\OneDrive - Diakonia Group, LLC\Contract Management - SharePoint\Tools")
HTML_PATH = BASE / "index.html"
CSV_PATH  = BASE / "contract-catalog.csv"

# ── PART 1 — index.html entity/mojibake fix ──────────────────────────────────
print("=" * 64)
print("PART 1 — index.html fix")
print("=" * 64)

shutil.copy2(HTML_PATH, HTML_PATH.with_suffix('.html.bak_entities'))

content = HTML_PATH.read_text(encoding='utf-8')

replacements = [
    ('&mdash;',              '—'),   # — em-dash
    ('&hellip;',             '…'),   # … ellipsis
    ('Â§',         '§'),   # Â§ -> §
    ('Â·',         '·'),   # Â· -> ·
]

total = 0
for bad, good in replacements:
    n = content.count(bad)
    content = content.replace(bad, good)
    total += n
    print(f"  {n:>3}x  {bad!r:30s} -> {good!r}")

HTML_PATH.write_text(content, encoding='utf-8')
print(f"\nTotal replacements: {total}")

# ── PART 1 VERIFY ────────────────────────────────────────────────────────────
print("\n--- VERIFY ---")
verify = HTML_PATH.read_text(encoding='utf-8')
lines  = verify.splitlines()

checks = {
    '&mdash;':  '&mdash;',
    '&hellip;': '&hellip;',
    'Â':   'Â (U+00C2)',
    'â€':       'â€ (mojibake)',
}
all_clear = True
for pat, label in checks.items():
    hits = [i+1 for i, ln in enumerate(lines) if pat in ln]
    status = "OK" if not hits else f"FAIL — found on lines {hits[:10]}"
    print(f"  [{label}]: {status}")
    if hits:
        all_clear = False

print(f"\nLine 568: {lines[567]}")
print(f"Line 824: {lines[823]}")

print(f"\nVerify result: {'PASS — all clear' if all_clear else 'FAIL — residual patterns remain'}")
VERIFY_PASS = all_clear

# ── PART 2 — contract-catalog.csv stats ─────────────────────────────────────
print("\n")
print("=" * 64)
print("PART 2 — contract-catalog.csv verification")
print("=" * 64)

with open(CSV_PATH, encoding='utf-8-sig', newline='') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

total_rows = len(rows)
mr_y_rows  = [r for r in rows if r.get('ManualReview','').strip().upper() == 'Y']
unk_rows   = [r for r in rows if r.get('Status','').strip().lower() == 'unknown']

print(f"\n  a. Total rows (excl header): {total_rows}")
print(f"  b. ManualReview == 'Y':      {len(mr_y_rows)}")
print(f"  c. Status == 'unknown':      {len(unk_rows)}")

# d. Status distribution
print("\n  d. Status distribution:")
dist = {}
for r in rows:
    s = r.get('Status','').strip() or '(blank)'
    dist[s] = dist.get(s, 0) + 1
for s, n in sorted(dist.items(), key=lambda x: -x[1]):
    print(f"       {s:<20} {n:>4}")

# e. Offending rows
def print_sample(label, sample_rows):
    if not sample_rows:
        return
    print(f"\n  {label} — first 5:")
    for r in sample_rows[:5]:
        cp  = r.get('CounterpartyName','')[:40]
        fn  = r.get('Filename','')[:50]
        st  = r.get('Status','')
        note = r.get('ManualReviewNote','')[:60]
        vf  = r.get('VendorFolder','')[:25]
        print(f"    VF={vf!r:<27} CP={cp!r:<42} Status={st!r:<12} Note={note!r}")

if mr_y_rows or unk_rows:
    print_sample("ManualReview=Y rows", mr_y_rows)
    if unk_rows:
        print_sample("Status=unknown rows", unk_rows)
else:
    print("\n  (e) No offending rows — catalog clean.")

print(f"\n  VERIFY_PASS (index.html): {VERIFY_PASS}")
print("\n" + "=" * 64)
print("END")
print("=" * 64)
