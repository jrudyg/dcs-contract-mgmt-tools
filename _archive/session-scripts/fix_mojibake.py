import re, shutil, ftfy
from pathlib import Path

BASE = Path(r"C:\Users\jrudy\OneDrive - Diakonia Group, LLC\Contract Management - SharePoint\Tools")
HTML_PATH = BASE / "index.html"
BAK_PATH  = HTML_PATH.with_suffix('.html.bak_mojibake')

shutil.copy2(HTML_PATH, BAK_PATH)
print(f"ftfy version: {ftfy.__version__}")
print(f"Backup: {BAK_PATH}")

before_text = HTML_PATH.read_text(encoding='utf-8')
before_lines = before_text.splitlines()

# Apply ftfy
fixed_text = ftfy.fix_text(before_text)

# Replace any residual U+FFFD runs inside comment separator lines with '='
# These are lines like: // ────── or // ══════
def fix_replacement_chars(text):
    count = 0
    out = []
    for ln in text.splitlines(keepends=True):
        if '�' in ln and re.search(r'//\s*.*�', ln):
            new_ln = ln.replace('�', '=')
            out.append(new_ln)
            count += 1
        else:
            out.append(ln)
    return ''.join(out), count

fixed_text, fffd_subs = fix_replacement_chars(fixed_text)

# Count changed lines and build sample diff
after_lines = fixed_text.splitlines()
changed = [(i+1, before_lines[i], after_lines[i])
           for i in range(min(len(before_lines), len(after_lines)))
           if before_lines[i] != after_lines[i]]

print(f"\nLines changed: {len(changed)}")
if fffd_subs:
    print(f"U+FFFD separator lines patched: {fffd_subs}")

print("\nSample diff (up to 10 lines):")
for lineno, b, a in changed[:10]:
    b_show = b.strip()[:90]
    a_show = a.strip()[:90]
    print(f"  L{lineno:>5}  BEFORE: {b_show}")
    print(f"         AFTER:  {a_show}")
    print()

# Safety assertions
assert '&mdash;' not in fixed_text, "FAIL: &mdash; still present"
assert '<meta charset' in fixed_text, "FAIL: <meta charset missing"
print("Safety assertions: PASS")

HTML_PATH.write_text(fixed_text, encoding='utf-8')
print(f"Wrote {len(fixed_text)} chars to index.html")

# ── VERIFY ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("VERIFY")
print("=" * 60)

verify_text  = HTML_PATH.read_text(encoding='utf-8')
verify_lines = verify_text.splitlines()

must_be_zero = {
    'â€': 'â€ (mojibake)',
    'â"': 'â" (box mojibake)',
    'â•': 'â• (box mojibake)',
    'ðŸ': 'ðŸ (emoji mojibake)',
    'â‰¤': 'â‰¤ (≤ mojibake)',
    'Â':  'Â (U+00C2 mojibake)',
}
must_have = {
    '≤':  '≤ (U+2264)',
    '🌙': '🌙 (moon emoji)',
    '─':  '─ (box-drawing)',
}

all_pass = True
print("\nMust-be-zero patterns:")
for pat, label in must_be_zero.items():
    hits = [i+1 for i, ln in enumerate(verify_lines) if pat in ln]
    ok = not hits
    if not ok:
        all_pass = False
    print(f"  {'OK' if ok else 'FAIL':4}  [{label}]  {len(hits)} hit(s){' — lines: '+str(hits[:5]) if hits else ''}")

print("\nMust-have patterns (proves repair, not deletion):")
for pat, label in must_have.items():
    hits = [i+1 for i, ln in enumerate(verify_lines) if pat in ln]
    ok = bool(hits)
    if not ok:
        all_pass = False
    print(f"  {'OK' if ok else 'FAIL':4}  [{label}]  {len(hits)} hit(s)")

# Print specific named lines
print("\nNamed line samples:")
for i, ln in enumerate(verify_lines, 1):
    if 'Expiring' in ln and ('stat' in ln.lower() or 'label' in ln.lower() or 'expir' in ln.lower()):
        print(f"  L{i} (Expiring stat): {ln.strip()[:120]}")
        break

for i, ln in enumerate(verify_lines, 1):
    if 'theme' in ln.lower() and ('btn' in ln.lower() or 'button' in ln.lower()):
        print(f"  L{i} (theme-btn):     {ln.strip()[:120]}")
        break

print(f"\nOverall verify: {'PASS' if all_pass else 'FAIL'}")
import sys
sys.exit(0 if all_pass else 1)
