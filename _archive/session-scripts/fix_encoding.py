import shutil
from pathlib import Path

HTML = Path(r"C:\Users\jrudy\OneDrive - Diakonia Group, LLC\Contract Management - SharePoint\Tools\index.html")
BAK = HTML.with_suffix('.html.bak_encoding')
shutil.copy2(HTML, BAK)

content = HTML.read_text(encoding='utf-8-sig')

# All patterns expressed as explicit unicode escapes to avoid encoding ambiguity.
# Values verified against index.html via _check_mojibake.py (76 total hits).
replacements = [
    # U+2713 ✓ checkmark: UTF-8 E2 9C 93 read as cp1252 -> â(U+00E2) œ(U+0153) "(U+201C)
    ('âœ“', '&#10003;'),
    # U+2717 ✗ cross: UTF-8 E2 9C 97 read as cp1252 -> â(U+00E2) œ(U+0153) —(U+2014)
    ('âœ—', '&#10007;'),
    # U+2014 — em-dash: UTF-8 E2 80 94 read as cp1252 -> â(U+00E2) €(U+20AC) "(U+201D)
    ('â€”', '&mdash;'),
    # U+2013 – en-dash: UTF-8 E2 80 93 read as cp1252 -> â(U+00E2) €(U+20AC) "(U+201C)
    ('â€“', '&mdash;'),
    # U+2193 ↓ down-arrow: UTF-8 E2 86 93 read as cp1252 -> â(U+00E2) †(U+2020) "(U+201C)
    ('â†“', '&#8595;'),
    # U+2191 ↑ up-arrow: UTF-8 E2 86 91 read as cp1252 -> â(U+00E2) †(U+2020) '(U+2018)
    ('â†‘', '&#8593;'),
    # U+2192 → right-arrow: UTF-8 E2 86 92 read as cp1252 -> â(U+00E2) †(U+2020) '(U+2019)
    ('â†’', '&#8594;'),
    # U+2705 ✅ green check: UTF-8 E2 9C 85 read as cp1252 -> â(U+00E2) œ(U+0153) …(U+2026)
    ('âœ…', '&#9989;'),
    # U+2B06 ⬆ up-arrow filled: UTF-8 E2 AC 86 read as cp1252 -> â(U+00E2) ¬(U+00AC) †(U+2020)
    ('â¬†', '&#11014;'),
    # U+22C5 ⋅ middle dot: UTF-8 E2 8B 85 read as cp1252 -> â(U+00E2) ‹(U+2039) …(U+2026)
    ('â‹…', '&middot;'),
    # U+2022 • bullet: UTF-8 E2 80 A2 read as cp1252 -> â(U+00E2) €(U+20AC) ¢(U+00A2)
    ('â€¢', '&bull;'),
    # U+2018 ' lsquo: UTF-8 E2 80 98 read as cp1252 -> â(U+00E2) €(U+20AC) ˜(U+02DC)
    ('â€˜', '&lsquo;'),
    # U+2019 ' rsquo: UTF-8 E2 80 99 read as cp1252 -> â(U+00E2) €(U+20AC) ™(U+2122)
    ('â€™', '&rsquo;'),
    # U+201C " ldquo: UTF-8 E2 80 9C read as cp1252 -> â(U+00E2) €(U+20AC) œ(U+0153)
    ('â€œ', '&ldquo;'),
    # U+201D " rdquo: UTF-8 E2 80 9D read as cp1252 -> â(U+00E2) €(U+20AC) [U+009D ctrl]
    ('â€', '&rdquo;'),
    # U+2026 … ellipsis: UTF-8 E2 80 A6 read as cp1252 -> â(U+00E2) €(U+20AC) ¦(U+00A6)
    ('â€¦', '&hellip;'),
    # U+00E9 é eacute: UTF-8 C3 A9 read as cp1252 -> Ã(U+00C3) ©(U+00A9)
    ('Ã©', '&eacute;'),
]

count = 0
for bad, good in replacements:
    n = content.count(bad)
    if n:
        content = content.replace(bad, good)
        count += n
        print(f"  Replaced {n}x: U+{ord(bad[0]):04X}... -> {good}")

HTML.write_text(content, encoding='utf-8')
print(f"Total replacements: {count}")
print("Done.")
