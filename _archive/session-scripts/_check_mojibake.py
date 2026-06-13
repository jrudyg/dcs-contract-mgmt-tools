from pathlib import Path
content = Path("index.html").read_text(encoding="utf-8-sig")

# Check byte-level for known mojibake patterns by encoding mojibake chars
# Each entry: (description, unicode codepoints of the mojibake string)
checks = [
    ("checkmark âœ\"", [0x00e2, 0x0153, 0x201c]),
    ("cross âœ—", [0x00e2, 0x0153, 0x2014]),
    ("em-dash â€\"", [0x00e2, 0x20ac, 0x201d]),
    ("en-dash â€\"", [0x00e2, 0x20ac, 0x201c]),
    ("down-arrow â†\"", [0x00e2, 0x2020, 0x201c]),
    ("up-arrow â†' (U+2018)", [0x00e2, 0x2020, 0x2018]),
    ("up-arrow â†' (U+0027 apos)", [0x00e2, 0x2020, 0x0027]),
    ("right-arrow â†' (U+2019)", [0x00e2, 0x2020, 0x2019]),
    ("check-green âœ…", [0x00e2, 0x0153, 0x2026]),
    ("up-arrow-2 â¬†", [0x00e2, 0x00ac, 0x2020]),
    ("middot â‹…", [0x00e2, 0x2039, 0x2026]),
    ("bullet â€¢", [0x00e2, 0x20ac, 0x00a2]),
    ("lsquo â€˜", [0x00e2, 0x20ac, 0x02dc]),
    ("rsquo â€™", [0x00e2, 0x20ac, 0x2122]),
    ("ldquo â€œ", [0x00e2, 0x20ac, 0x0153]),
    ("rdquo â€", [0x00e2, 0x20ac, 0x009d]),
    ("hellip â€¦", [0x00e2, 0x20ac, 0x00a6]),
    ("eacute Ã©", [0x00c3, 0x00a9]),
]

total = 0
for name, codepoints in checks:
    pat = "".join(chr(c) for c in codepoints)
    n = content.count(pat)
    if n:
        print(f"  {n}x  {name}")
        total += n
print(f"\nTotal mojibake hits: {total}")
print(f"File length: {len(content)} chars")
