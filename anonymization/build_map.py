#!/usr/bin/env python3
"""
build_map.py — ANON-2 counterparty map builder with alias detection.

Reads kb/COUNTERPARTIES.md, assigns PARTY-0001..PARTY-N pseudonyms (sorted
alphabetically, 3 non-entities excluded), and generates alias variants per
counterparty:
  - abbreviation: initials of each word  (e.g. "Williams-Sonoma, Inc" → "WSI")
  - short name:   first word if >4 chars  (e.g. "Williams-Sonoma, Inc" → "Williams")
  - suffix-stripped variants of the full name, plus abbrev/short-name from each

Output: anonymization/mapping.json  (gitignored — local only, never stage/push)
"""

import json
import pathlib
import re
import time

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = pathlib.Path(__file__).parent.parent          # Tools/
COUNTERPARTIES_PATH = BASE_DIR / "kb" / "COUNTERPARTIES.md"
MAPPING_PATH = BASE_DIR / "anonymization" / "mapping.json"

# ---------------------------------------------------------------------------
# Exclusion list
# ---------------------------------------------------------------------------

EXCLUDED: frozenset[str] = frozenset({
    "",
    "(blank)",
    "A. MNDA Template",
    "ACI for Signature",
})

# ---------------------------------------------------------------------------
# Suffix removal
# ---------------------------------------------------------------------------

_SUFFIX_WORDS = [
    "Incorporated", "Corporation", "Limited",
    "Inc", "Corp", "Ltd", "LLC", "L.L.C", "LCC", "LP", "L.P",
    "Company", "Co", "Group",
    "GmbH", "srl", "B.V",
]

# Each pattern: optional comma, whitespace, suffix word, optional period, end-of-string
_SUFFIX_PATTERNS: list[re.Pattern] = [
    re.compile(r',?\s+' + re.escape(w) + r'\.?\s*$', re.IGNORECASE)
    for w in _SUFFIX_WORDS
]

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# Matches: **Name** — N row(s): DocType (count), ...
_LINE_RE = re.compile(
    r'^\*\*(.+?)\*\*\s+—\s+(\d+)\s+row\(s\):\s*(.+)$'
)

# Matches doc-type tokens: Word (count) — handles normal types but skips "(unknown)"
_DOCTYPE_RE = re.compile(r'\b([A-Za-z][A-Za-z0-9\-]*(?:\s[A-Za-z0-9\-]+)*)\s*\((\d+)\)')


def parse_counterparties(path: pathlib.Path) -> list[dict]:
    """Return list of {name, row_count, doc_types} dicts."""
    entries = []
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            m = _LINE_RE.match(line.strip())
            if not m:
                continue
            name = m.group(1).strip()
            row_count = int(m.group(2))
            doc_types: dict[str, int] = {}
            for dt_m in _DOCTYPE_RE.finditer(m.group(3)):
                doc_types[dt_m.group(1).strip()] = int(dt_m.group(2))
            entries.append({'name': name, 'row_count': row_count, 'doc_types': doc_types})
    return entries

# ---------------------------------------------------------------------------
# Alias generation
# ---------------------------------------------------------------------------

def _abbreviation(name: str) -> str:
    """Return uppercase initials of each word (split on whitespace/hyphens/punctuation)."""
    words = re.split(r'[\s\-_/,;:()+&]+', name)
    return ''.join(w[0].upper() for w in words if w and w[0].isalpha())


def _short_name(name: str) -> str:
    """Return first word if longer than 4 chars, else empty string."""
    first = re.split(r'[\s\-_/,;:()+&]+', name)[0].strip('.,;:()')
    return first if len(first) > 4 else ''


def _strip_suffixes(name: str) -> list[str]:
    """Return up to 3 progressively de-suffixed variants of name."""
    variants: list[str] = []
    current = name
    for _ in range(3):
        reduced = current
        for pat in _SUFFIX_PATTERNS:
            reduced = pat.sub('', reduced).strip().rstrip(',').strip()
        if reduced and reduced != current:
            variants.append(reduced)
            current = reduced
        else:
            break
    return variants


def generate_aliases(name: str) -> list[str]:
    """Return sorted list of unique alias variants (min 3 chars, not equal to name)."""
    pool: set[str] = set()

    def _add(candidate: str) -> None:
        candidate = candidate.strip()
        if len(candidate) >= 3 and candidate.lower() != name.lower():
            pool.add(candidate)

    # Direct abbreviation and short name
    _add(_abbreviation(name))
    _add(_short_name(name))

    # Suffix-stripped variants + their abbreviation/short-name
    for sv in _strip_suffixes(name):
        _add(sv)
        _add(_abbreviation(sv))
        _add(_short_name(sv))

    return sorted(pool)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    all_entries = parse_counterparties(COUNTERPARTIES_PATH)

    excluded_entries = [e for e in all_entries if e['name'] in EXCLUDED or not e['name'].strip()]
    active_entries   = [e for e in all_entries if e['name'] not in EXCLUDED and e['name'].strip()]

    # Sort alphabetically, case-insensitive
    active_entries.sort(key=lambda e: e['name'].casefold())

    entries: dict[str, dict] = {}
    total_aliases = 0
    for idx, entry in enumerate(active_entries, start=1):
        name = entry['name']
        aliases = generate_aliases(name)
        total_aliases += len(aliases)
        entries[name] = {
            'pseudonym': f'PARTY-{idx:04d}',
            'aliases': aliases,
            'row_count': entry['row_count'],
            'doc_types': entry['doc_types'],
        }

    payload = {
        'generated': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'version': 2,
        'excluded': sorted(EXCLUDED - {''}),
        'entries': entries,
    }

    MAPPING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MAPPING_PATH, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)

    print(f'Total mapped:         {len(entries)}')
    print(f'Total alias entries:  {total_aliases}')
    print(f'Excluded:             {len(excluded_entries)}  '
          f'({", ".join(repr(e["name"]) for e in excluded_entries)})')
    print(f'Output:               {MAPPING_PATH}')
    print()
    print('First 5 entries:')
    first5 = dict(list(entries.items())[:5])
    print(json.dumps(first5, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
