"""
scan-contract.py  --  Contract Catalog Scanner
Reads contract files (.pdf, .docx), extracts metadata, and updates contract-catalog.csv.

Usage (from SharePoint root):
  python Tools/scan-contract.py "VendorFolder/filename.pdf"
  python Tools/scan-contract.py --vendor "Disney"
  python Tools/scan-contract.py --location "02 Unsigned Contracts"
  python Tools/scan-contract.py --all [--dry-run]
"""

import argparse
import csv
import re
import shutil
import sys
import time
from pathlib import Path, PurePosixPath

import pandas as pd
from dateutil import parser as dparser
from dateutil.relativedelta import relativedelta

# ── Paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR   = Path(__file__).resolve().parent          # …/Tools
SHAREPOINT   = SCRIPT_DIR.parent                        # …/Contract Management - SharePoint
DEFAULT_CSV  = SCRIPT_DIR / "contract-catalog.csv"

CONTRACT_ROOTS = [
    "01 Active Contracts",
    "02 Unsigned Contracts",
    "03 Archived Contracts",
]

# ── DCS identity ──────────────────────────────────────────────────────────────

DCS_RE = re.compile(
    r"Designed\s+Conveyor\s+Systems(?:,?\s+LLC)?"
    r"|\bDCS\b",
    re.IGNORECASE,
)

# ── Doc-type patterns (order matters; checked against first 500 chars) ────────

DOC_TYPE_PATTERNS = [
    (re.compile(r"MUTUAL\s+NON.?DISCLOSURE",                    re.I), "MNDA"),
    (re.compile(r"MUTUAL\s+CONFIDENTIALITY\s+AND\s+NON.?DISCLOSURE", re.I), "MNDA"),
    (re.compile(r"NON.?DISCLOSURE",                              re.I), "NDA"),
    (re.compile(r"MASTER\s+SERVICES?\s+AGREEMENT",              re.I), "MSA"),
    (re.compile(r"MASTER\s+PURCHASING\s+AGREEMENT",             re.I), "MPA"),
    (re.compile(r"STATEMENT\s+OF\s+WORK",                       re.I), "SOW"),
    (re.compile(r"SUBCONTRACT(?!OR)",                           re.I), "Subcontract"),
    (re.compile(r"CHANGE\s+ORDER",                              re.I), "Change Order"),
    (re.compile(r"NON.?COMPETE|NONCOMPETE",                     re.I), "Non-Compete"),
    (re.compile(r"\bLICENSE\s+AGREEMENT\b",                     re.I), "License"),
    (re.compile(r"\bEXHIBIT\b",                                 re.I), "Exhibit"),
    (re.compile(r"\bAMENDMENT\b",                               re.I), "Amendment"),
    (re.compile(r"\bRETAINER\b",                                re.I), "Retainer"),
]

# ── Signature patterns ────────────────────────────────────────────────────────

SIGNED_KW_RE = re.compile(
    r"/s/"
    r"|DocuSign\s+Envelope\s+ID"
    r"|\belectronically\s+signed\b"
    r"|\bfully\s+executed\b"
    r"|\bexecuted\s+by\b",
    re.IGNORECASE,
)

BY_LINE_RE = re.compile(r"By:\s*\n(.{1,120})", re.IGNORECASE)

PLACEHOLDER_RE = re.compile(
    r"^[\s_\-]*$"
    r"|^NAME$"
    r"|\(VENDOR"
    r"|_{3,}",
    re.IGNORECASE,
)

DATE_FILLED_RE = re.compile(
    r"Date(?:\s+Signed)?:\s*"
    r"(?:\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}"
    r"|\w+ \d{1,2},?\s*\d{4}"
    r"|[A-Z][a-z]+ \d{1,2},?\s*\d{4})",
    re.IGNORECASE,
)

# ── Date patterns ─────────────────────────────────────────────────────────────

_MONTH = (
    r"(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)"
)
DATE_PAT = (
    r"(?:"
    + _MONTH + r"\s+\d{1,2},?\s+\d{4}"          # October 1, 2024
    r"|\d{1,2}\s+" + _MONTH + r"\s+\d{4}"        # 1 October 2024
    r"|\d{4}-\d{2}-\d{2}"                         # 2024-10-01
    r"|\d{1,2}/\d{1,2}/\d{2,4}"                   # 10/1/2024
    r"|\d{1,2}\.\d{1,2}\.\d{4}"                   # 10.1.2024
    r")"
)

EFFECTIVE_DATE_RE = re.compile(
    r"(?:effective\s+(?:as\s+of\s+)?|dated\s+(?:as\s+of\s+)?"
    r"|as\s+of\s+|entered\s+into\s+(?:as\s+of\s+)?)"
    + DATE_PAT,
    re.IGNORECASE,
)

# Handles fill-in-blank templates: "made as of the _30_ day of _April_____, 2020"
_AS_OF_THE_RE = re.compile(
    r"(?:effective|dated|made)\s+as\s+of\s+the\s+|as\s+of\s+the\s+",
    re.IGNORECASE,
)
_DAY_OF_RE = re.compile(
    r"_*(\d{1,2})_*\s+day\s+of\s+_*("
    + _MONTH[3:]          # strip leading "(?:" → becomes capturing group (Month|...)
    + r"_*[_,\s]+_*(\d{4})",
    re.IGNORECASE,
)

# At-will / written-notice termination (no fixed expiration date)
AT_WILL_RE = re.compile(
    r"either\s+party\s+may\s+terminat"
    r"|terminat\s+this\s+agreement\s+at\s+any\s+time"
    r"|upon\s+(?:thirty|sixty|ninety|\d+)\s+days?\s+(?:written\s+)?notice"
    r"|upon\s+written\s+notice\s+to\s+the\s+other",
    re.IGNORECASE,
)

EXPIRATION_TRIGGER_RE = re.compile(
    r"(?:expir(?:es?|ation)|terminat(?:es?|ion\s+date)|through|until|ending\s+on)"
    r"\s+(?:on\s+)?"
    + DATE_PAT,
    re.IGNORECASE,
)

TERM_YEARS_RE = re.compile(
    r"(?:term\s+of\s+|for\s+a\s+(?:period\s+of\s+)?)"
    r"(\w+|\d+)\s*\(?\d*\)?\s*year(?:s)?",
    re.IGNORECASE,
)

WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

# ── Entity suffix for counterparty fallback ───────────────────────────────────

ENTITY_SUFFIX_RE = re.compile(
    r"\b(?:Inc\.?|LLC\.?|Corp\.?|Ltd\.?|L\.P\.?|LLP\.?|Co\.?|plc|GmbH|B\.V\.|S\.A\.?)\b",
    re.IGNORECASE,
)

# Specific: use ", and" (comma + and) as party separator — handles names containing "and"
PARTY_COMMA_AND_RE = re.compile(
    r"(?:by\s+and\s+between|between)\s+"
    r"(.{10,350}?)"
    r",\s+and\s+"
    r"(.{5,300}?)"
    r"(?:,\s*(?:\(|located|having|a\s+\w)|[\(\.\n\"])",
    re.IGNORECASE | re.DOTALL,
)

# Generic fallback: plain "and" separator
PARTY_BLOCK_RE = re.compile(
    r"(?:by\s+and\s+between|between)"
    r"\s+(.{5,200}?)"
    r"\s+and\s+"
    r"(.{5,200}?)"
    r"(?:\s*[\(\.\"]|,\s*(?:each|a\s+.Party.|together))",
    re.IGNORECASE | re.DOTALL,
)

# DCS boilerplate: "DCS and its Affiliates ..., on the one hand, and [COUNTERPARTY]"
DCS_ONE_HAND_RE = re.compile(
    r"(?:Designed\s+Conveyor\s+Systems[^,\n]*|DCS)[^,\n]*"
    r",\s*on\s+the\s+one\s+hand,\s+and\s+"
    r"(.{5,200}?)"
    r"(?:\s*[\(\"\'\.]|\s*,\s*(?:on\s+the\s+other\s+hand|each|together|\"|\'))",
    re.IGNORECASE | re.DOTALL,
)

# "and [ENTITY], on the other hand"
OTHER_HAND_RE = re.compile(
    r"and\s+(.{5,200}?),\s*on\s+the\s+other\s+hand",
    re.IGNORECASE | re.DOTALL,
)

# ── Text extraction ───────────────────────────────────────────────────────────

def _extract_pdf(path: Path) -> tuple[str, bool]:
    import fitz  # PyMuPDF
    try:
        doc = fitz.open(str(path))
    except PermissionError:
        raise
    except Exception as exc:
        raise RuntimeError(f"fitz could not open {path.name}: {exc}") from exc
    pages = [page.get_text() for page in doc]
    full = "\n".join(pages)
    return full, len(full.strip()) < 50


def _extract_docx(path: Path) -> tuple[str, bool]:
    from docx import Document
    try:
        doc = Document(str(path))
    except PermissionError:
        raise
    except Exception as exc:
        raise RuntimeError(f"python-docx could not open {path.name}: {exc}") from exc
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts), False


def extract_text(path: Path) -> tuple[str, bool, str | None]:
    """Returns (text, is_scanned, skip_reason)."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            return (*_extract_pdf(path), None)
        except PermissionError:
            return ("", False, "file locked (PermissionError)")
        except RuntimeError as e:
            return ("", False, str(e))
    elif ext == ".docx":
        try:
            return (*_extract_docx(path), None)
        except PermissionError:
            return ("", False, "file locked (PermissionError)")
        except RuntimeError as e:
            return ("", False, str(e))
    elif ext == ".doc":
        return ("", False, ".doc not supported (legacy binary format)")
    elif ext == ".msg":
        return ("", False, ".msg not supported")
    else:
        return ("", False, f"{ext} not supported")

# ── Extractors ────────────────────────────────────────────────────────────────

def detect_doc_type(text: str) -> str | None:
    header = text[:500]
    for pattern, doc_type in DOC_TYPE_PATTERNS:
        if pattern.search(header):
            return doc_type
    return None


def detect_signing(text: str) -> tuple[str, str]:
    """Returns (has_signed_keyword_str, signing_status_str)."""
    has_kw = bool(SIGNED_KW_RE.search(text))
    filled_blocks = sum(
        1 for m in BY_LINE_RE.finditer(text)
        if m.group(1).strip() and not PLACEHOLDER_RE.search(m.group(1).strip())
    )
    date_filled = bool(DATE_FILLED_RE.search(text))
    is_signed = has_kw or (filled_blocks >= 1 and date_filled)
    return ("True" if has_kw else "False", "Signed" if is_signed else "Unsigned")


def _normalize_date(raw: str) -> str | None:
    try:
        dt = dparser.parse(raw, dayfirst=False)
        # Sanity-check: reject dates before 1990 or after 2050
        if dt.year < 1990 or dt.year > 2050:
            return None
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return None


def _trim_to_entity_name(raw: str) -> str:
    """Trim a party description (possibly with address) down to just the entity name."""
    raw = _clean_entity_name(raw)
    if len(raw) <= 80:
        return raw
    # Cut at description markers that follow the entity name
    m = re.match(
        r"(.{5,}?)(?:,\s*a\s+(?:division|corporation|company|limited|partnership|Delaware|Florida|Tennessee|California|Nevada|New York)|"
        r",\s*located\s+at|,\s*having\s+|,\s*an?\s+\w+\s+(?:company|corp|partnership))",
        raw, re.IGNORECASE,
    )
    if m and len(m.group(1).strip()) >= 3:
        return m.group(1).strip(" ,.")
    # Fallback: stop at first comma
    first = raw.split(",")[0].strip()
    if len(first) >= 3:
        return first
    return raw[:80].strip()


def _clean_entity_name(raw: str) -> str:
    raw = re.sub(r'\s*[\("\'（][^)"\'）]{1,60}[\)"\'）]', "", raw)
    raw = re.sub(r"\s+and\s+its\s+Affiliates.*$", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s+together\s+with.*$", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s+\(collectively.*$", "", raw, flags=re.IGNORECASE)
    return raw.strip(" ,.")


def extract_counterparty(text: str, vendor_folder: str = "") -> str | None:
    # Normalize line breaks for PDF text-flow artifacts before regex matching
    zone = re.sub(r"\s+", " ", text[:2000])

    # Strategy 0: DCS collective definition closure → "(collectively, "DCS")" then next ", and [PARTY]"
    # Handles: DCS...(collectively, "DCS") [address], and 6Sense Insights, Inc., together...
    m_dcs_close = re.search(r'"DCS"\)', zone, re.IGNORECASE)
    if m_dcs_close:
        after = zone[m_dcs_close.end():]
        m_party = re.search(
            r',\s+and\s+(.{3,120}?)'
            r'(?:,\s*(?:together|each|having|on\s+the|with\s+its)|\s*[\(\"\'\n\.])',
            after,
            re.IGNORECASE | re.DOTALL,
        )
        if m_party:
            candidate = _clean_entity_name(m_party.group(1))
            if 3 <= len(candidate) <= 80 and not DCS_RE.search(candidate):
                return candidate

    # Strategy 1: DCS boilerplate "..., on the one hand, and [COUNTERPARTY]"
    m = DCS_ONE_HAND_RE.search(zone)
    if m:
        candidate = _clean_entity_name(m.group(1))
        if 3 <= len(candidate) <= 80:
            return candidate

    # Strategy 2: "and [ENTITY], on the other hand"
    m = OTHER_HAND_RE.search(zone)
    if m:
        candidate = _clean_entity_name(m.group(1))
        if 3 <= len(candidate) <= 80 and not DCS_RE.search(candidate):
            return candidate

    # Strategy 3a: "between X, and Y" with comma separator (handles names containing "and")
    for m in PARTY_COMMA_AND_RE.finditer(zone):
        p1, p2 = m.group(1).strip(), m.group(2).strip()
        if DCS_RE.search(p1) and not DCS_RE.search(p2):
            candidate = _trim_to_entity_name(p2)
            if 3 <= len(candidate) <= 100:
                return candidate
        if DCS_RE.search(p2) and not DCS_RE.search(p1):
            candidate = _trim_to_entity_name(p1)
            if 3 <= len(candidate) <= 100:
                return candidate

    # Strategy 3b: generic "by and between X and Y"
    for m in PARTY_BLOCK_RE.finditer(zone):
        p1, p2 = m.group(1).strip(), m.group(2).strip()
        if DCS_RE.search(p1) and not DCS_RE.search(p2):
            candidate = _trim_to_entity_name(p2)
            if 3 <= len(candidate) <= 100:
                return candidate
        if DCS_RE.search(p2) and not DCS_RE.search(p1):
            candidate = _trim_to_entity_name(p1)
            if 3 <= len(candidate) <= 100:
                return candidate

    # Strategy 4: entity-suffix scan (non-DCS entity near top of doc)
    for em in ENTITY_SUFFIX_RE.finditer(zone):
        start = max(0, em.start() - 60)
        window = zone[start : em.end()]
        nm = re.search(
            r"([A-Z][A-Za-z0-9\s,\.&\-']+?" + ENTITY_SUFFIX_RE.pattern + r")",
            window,
            re.IGNORECASE,
        )
        if nm:
            candidate = _clean_entity_name(nm.group(0))
            if 3 <= len(candidate) <= 80 and not DCS_RE.search(candidate):
                return candidate

    # Strategy 5: VendorFolder fallback
    if vendor_folder and len(vendor_folder.strip()) >= 2:
        return vendor_folder.strip()

    return None


def extract_effective_date(text: str) -> str | None:
    zone = text[:2000]
    date_re = re.compile(DATE_PAT, re.IGNORECASE)

    # Primary: standard date immediately after trigger keyword
    for m in EFFECTIVE_DATE_RE.finditer(zone):
        raw = date_re.search(m.group(0))
        if raw:
            result = _normalize_date(raw.group(0))
            if result:
                return result

    # Fallback: "made as of the _30_ day of _April_____, 2020" template style
    for m in _AS_OF_THE_RE.finditer(zone):
        window = zone[m.end(): m.end() + 80]
        dm = _DAY_OF_RE.search(window)
        if dm:
            raw_date = f"{dm.group(1)} {dm.group(2).strip('_ ')} {dm.group(3)}"
            result = _normalize_date(raw_date)
            if result:
                return result
        # Also try a standard date in the window (e.g. "as of the April 30, 2020")
        raw = date_re.search(window)
        if raw:
            result = _normalize_date(raw.group(0))
            if result:
                return result

    return None


def detect_at_will_termination(text: str) -> bool:
    return bool(AT_WILL_RE.search(text))


def extract_expiration_date(text: str, effective_iso: str | None) -> str | None:
    # Strategy A: explicit expiration date in text
    date_re = re.compile(DATE_PAT, re.IGNORECASE)
    for m in EXPIRATION_TRIGGER_RE.finditer(text):
        raw = date_re.search(m.group(0))
        if raw:
            result = _normalize_date(raw.group(0))
            if result:
                return result

    # Strategy B: N-year term arithmetic
    if effective_iso:
        for m in TERM_YEARS_RE.finditer(text):
            qty_str = m.group(1).lower()
            qty = WORD_TO_NUM.get(qty_str) or (int(qty_str) if qty_str.isdigit() else None)
            if qty and 1 <= qty <= 20:
                try:
                    eff = dparser.parse(effective_iso)
                    exp = eff + relativedelta(years=qty)
                    return exp.strftime("%Y-%m-%d")
                except Exception:
                    pass

    return None

# ── CSV helpers ───────────────────────────────────────────────────────────────

def load_csv(csv_path: Path) -> pd.DataFrame:
    return pd.read_csv(str(csv_path), dtype=str, keep_default_na=False)


def write_csv(df: pd.DataFrame, csv_path: Path, dry_run: bool = False):
    if dry_run:
        return
    tmp = csv_path.with_suffix(".csv.tmp")
    bak = csv_path.with_suffix(".csv.bak")
    df.to_csv(str(tmp), index=False, quoting=csv.QUOTE_ALL)
    shutil.copy2(str(csv_path), str(bak))
    tmp.replace(csv_path)


def _norm_path(p: str) -> str:
    return p.replace("\\", "/").strip()


def rows_for_filepath(df: pd.DataFrame, file_path_key: str) -> list[int]:
    key = _norm_path(file_path_key)
    mask = df["FilePath"].apply(_norm_path) == key
    return df.index[mask].tolist()


def resolve_abs_path(df: pd.DataFrame, row_idx: int, root: Path) -> Path | None:
    loc  = df.at[row_idx, "ContractLocation"]
    fp   = _norm_path(df.at[row_idx, "FilePath"])
    full = root / loc / Path(PurePosixPath(fp))
    return full if full.exists() else None

# ── Target-row builders ───────────────────────────────────────────────────────

def build_target_indices(
    df: pd.DataFrame,
    positional: list[str],
    vendor: str | None,
    location: str | None,
    doc_type: str | None,
    all_rows: bool,
) -> list[int]:
    indices: set[int] = set()

    if positional:
        for key in positional:
            found = rows_for_filepath(df, key)
            if not found:
                print(f"  [WARN] No CSV row for FilePath: {key}")
            indices.update(found)

    if vendor:
        mask = df["VendorFolder"].str.contains(vendor, case=False, na=False)
        vendor_idx = set(df.index[mask].tolist())
        if not vendor_idx:
            print(f"  [WARN] No rows matched --vendor: \"{vendor}\"")
        if location:
            loc_mask = df["ContractLocation"] == location
            loc_idx  = set(df.index[loc_mask].tolist())
            indices.update(vendor_idx & loc_idx)
        else:
            indices.update(vendor_idx)
    elif location and not positional:
        mask = df["ContractLocation"] == location
        loc_idx = set(df.index[mask].tolist())
        if not loc_idx:
            print(f"  [WARN] No rows matched --location: \"{location}\"")
        indices.update(loc_idx)

    if doc_type and not positional and not vendor and not location:
        mask = df["DocType"].str.contains(doc_type, case=False, na=False)
        type_idx = set(df.index[mask].tolist())
        if not type_idx:
            print(f"  [WARN] No rows matched --type: \"{doc_type}\"")
        indices.update(type_idx)

    if all_rows and not positional and not vendor and not location and not doc_type:
        indices.update(df.index.tolist())

    return sorted(indices)

# ── Per-file scan ─────────────────────────────────────────────────────────────

def scan_file(
    df: pd.DataFrame,
    row_indices: list[int],
    abs_path: Path,
    vendor_folder: str,
    dry_run: bool,
) -> dict:
    """Scan one file, update df rows in-place. Returns result dict."""
    result = {
        "path": abs_path,
        "rows": row_indices,
        "changes": [],
        "status": "ok",
        "note": "",
    }

    text, is_scanned, skip_reason = extract_text(abs_path)

    if skip_reason:
        result["status"] = "skipped"
        result["note"]   = skip_reason
        return result

    if is_scanned:
        result["status"] = "scanned_pdf"
        result["note"]   = "image-only PDF, no text extracted"
        # Still apply VendorFolder fallback for CounterpartyName
        text = ""

    # Run extractors
    doc_type   = detect_doc_type(text) if text else None
    has_kw, signing_status = detect_signing(text) if text else ("False", "Unsigned")
    counterparty = extract_counterparty(text, vendor_folder)
    eff_date     = extract_effective_date(text) if text else None
    exp_date     = extract_expiration_date(text, eff_date) if text else None
    if exp_date is None and text and detect_at_will_termination(text):
        exp_date = "upon written notice"

    extracted = {
        "DocType":          doc_type,
        "HasSignedKeyword": has_kw   if text else None,
        "SigningStatus":    signing_status if text else None,
        "CounterpartyName": counterparty,
        "EffectiveDate":    eff_date,
        "ExpirationDate":   exp_date,
    }

    # Write into df rows
    for idx in row_indices:
        for field, value in extracted.items():
            if value is None:
                continue
            old = df.at[idx, field]
            if old != value:
                if not dry_run:
                    df.at[idx, field] = value
                tag = "[DRY RUN] " if dry_run else ""
                result["changes"].append(
                    f"    {tag}Row {idx} [{field}]: \"{old}\" -> \"{value}\""
                )

    return result

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scan contract files and update contract-catalog.csv",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "files",
        nargs="*",
        metavar="FILEPATH",
        help="One or more FilePath keys (e.g. \"Disney/EXHIBIT C.pdf\")",
    )
    parser.add_argument("--vendor",   metavar="NAME",   help="Scan all rows matching VendorFolder (partial, case-insensitive)")
    parser.add_argument("--location", metavar="FOLDER", help="Scan all rows in ContractLocation")
    parser.add_argument("--type",     metavar="TYPE",   help="Scan all rows matching DocType (partial, case-insensitive)")
    parser.add_argument("--all",      action="store_true", help="Scan entire catalog")
    parser.add_argument("--dry-run",  action="store_true", help="Print changes without writing CSV")
    parser.add_argument("--csv",      metavar="PATH",   default=str(DEFAULT_CSV), help="Path to contract-catalog.csv")

    args = parser.parse_args()

    csv_path = Path(args.csv).resolve()
    if not csv_path.exists():
        sys.exit(f"CSV not found: {csv_path}")

    root = SHAREPOINT

    print("scan-contract.py  --  Contract Catalog Scanner")
    print("=" * 54)
    print(f"CSV:  {csv_path}")
    print(f"Root: {root}")
    if args.dry_run:
        print("Mode: DRY RUN (no changes written)")
    print()

    df = load_csv(csv_path)
    print(f"Loaded {len(df)} rows.\n")

    target_indices = build_target_indices(
        df,
        positional=args.files,
        vendor=args.vendor,
        location=args.location,
        doc_type=args.type,
        all_rows=args.all,
    )

    if not target_indices:
        sys.exit("No target rows resolved. Check your arguments.")

    # Deduplicate by FilePath so the same physical file isn't scanned twice
    seen_paths: set[str] = set()
    file_groups: list[tuple[str, list[int]]] = []
    for idx in target_indices:
        key = _norm_path(df.at[idx, "FilePath"])
        if key not in seen_paths:
            seen_paths.add(key)
            group_indices = rows_for_filepath(df, key)
            file_groups.append((key, group_indices))

    print(f"Scanning {len(file_groups)} file(s) across {len(target_indices)} row(s).\n")

    t_start = time.time()
    n_ok = n_skipped = n_scanned = n_missing = n_changed = 0

    for i, (fp_key, row_indices) in enumerate(file_groups, 1):
        vendor_folder = df.at[row_indices[0], "VendorFolder"] if row_indices else ""
        abs_path = resolve_abs_path(df, row_indices[0], root) if row_indices else None

        # Print progress every 10 files on large batches
        if len(file_groups) > 20 and i % 10 == 0:
            elapsed = time.time() - t_start
            print(f"  ... {i}/{len(file_groups)} files ({elapsed:.0f}s elapsed)")

        print(f"Scanning [{i}/{len(file_groups)}]: {fp_key}")

        if abs_path is None:
            print(f"  [NOT FOUND] File does not exist on disk - skipped")
            n_missing += 1
            continue

        result = scan_file(df, row_indices, abs_path, vendor_folder, args.dry_run)

        if result["status"] == "skipped":
            print(f"  [SKIPPED] {result['note']}")
            n_skipped += 1
        elif result["status"] == "scanned_pdf":
            print(f"  [SCANNED PDF] {result['note']}")
            n_scanned += 1
        else:
            n_ok += 1

        if result["changes"]:
            n_changed += len(result["changes"])
            for line in result["changes"]:
                print(line)
        else:
            print("  (no changes)")

    # Write CSV
    if not args.dry_run and n_changed > 0:
        write_csv(df, csv_path, dry_run=False)
        print(f"\nCSV written -> {csv_path}")
        print(f"Backup      -> {csv_path.with_suffix('.csv.bak')}")
    elif args.dry_run:
        print("\n[DRY RUN] CSV not written.")
    else:
        print("\nNo changes - CSV unchanged.")

    elapsed_total = time.time() - t_start
    print("\n" + "=" * 54)
    print(f"Summary: {len(file_groups)} files scanned in {elapsed_total:.1f}s")
    print(f"  OK:          {n_ok}")
    print(f"  Skipped:     {n_skipped}")
    print(f"  Scanned PDF: {n_scanned}")
    print(f"  Not found:   {n_missing}")
    print(f"  Field changes: {n_changed}")
    if args.dry_run:
        print("  [DRY RUN - CSV not written]")


if __name__ == "__main__":
    main()
