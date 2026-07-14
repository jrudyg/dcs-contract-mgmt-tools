"""
nightly-catalog-scan.py  —  Autonomous Nightly Contract Catalog Scanner
Spec: NIGHTLY_CATALOG_JOB.md v1.2 (dcs-contract-mgmt-tools)

Scans Salesforce Integration - Active Contracts for files created or modified
in the past day, derives catalog metadata, extracts PDF dates, appends new rows
to contract-catalog.csv, commits, and pushes to dcs-contract-mgmt-tools.

Never uses filesystem timestamps for date population (§Never Trust Filesystem Dates).
Every written row has a non-blank Status (§Status Invariant).
Circuit breaker > 17 preserves work to catalog-staged-YYYY-MM-DD.csv.

Usage:
  python nightly-catalog-scan.py                        # normal nightly run
  python nightly-catalog-scan.py --dry-run              # preview only — no writes
  python nightly-catalog-scan.py --force                # override circuit breaker
  python nightly-catalog-scan.py --cutoff YYYY-MM-DD   # override scan cutoff
"""

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    sys.exit("pdfplumber is required: pip install pdfplumber")

# ── Paths (per spec §Paths) ───────────────────────────────────────────────────

SCAN_ROOT = Path(
    r"C:\Users\jrudy\OneDrive - Diakonia Group, LLC"
    r"\Salesforce Integration - Active Contracts"
)
CATALOG = Path(
    r"C:\Users\jrudy\OneDrive - Diakonia Group, LLC"
    r"\Contract Management - SharePoint\Tools\contract-catalog.csv"
)
REPO_DIR      = CATALOG.parent
LOG_FILE      = REPO_DIR / "DETECT_RUN_LOG.txt"
WORKFLOW_FILE = (
    REPO_DIR / ".github" / "workflows"
    / "azure-static-web-apps-mango-forest-02de1020f.yml"
)
FIRST_PUSH_FLAG = REPO_DIR / ".nightly-first-push"

_TODAY_YEAR: int = date.today().year   # set once at load; used for 6-digit date disambiguation

CIRCUIT_BREAKER = 17          # §Circuit Breaker
SUPPORTED_EXT   = {".pdf", ".docx", ".doc", ".msg"}

COLUMNS = [
    "ContractLocation", "VendorFolder", "Filename", "FilePath", "Extension",
    "DocType", "HasSignedKeyword", "SigningStatus",
    "IsAmendment", "AmendmentNumber", "VersionLabel", "DateInFilename",
    "CounterpartyName", "EffectiveDate", "ExpirationDate", "DaysUntilExpiration",
    "Notes", "Status", "SurvivalRunning", "Stale", "SurvivalEndDate",
    "ManualReview", "ManualReviewNote",
]


# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════

_log_buf: list[str] = []


def log(msg: str) -> None:
    _log_buf.append(msg)
    print(msg)


def flush_log(dry: bool) -> None:
    """Write buffered log lines to DETECT_RUN_LOG.txt (skipped in dry-run)."""
    if dry:
        return
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write("\n".join(_log_buf) + "\n")


# ══════════════════════════════════════════════════════════════════════════════
# DOC-TYPE PATTERNS  (matched against filename)
# ══════════════════════════════════════════════════════════════════════════════

_DOC_PATTERNS = [
    (re.compile(r"MUTUAL\s+NON.?DISCLOSURE",                          re.I), "MNDA"),
    (re.compile(r"MUTUAL\s+CONFIDENTIALITY\s+AND\s+NON.?DISCLOSURE",  re.I), "MNDA"),
    (re.compile(r"NON.?DISCLOSURE",                                    re.I), "NDA"),
    (re.compile(r"MASTER\s+(?:SERVICES?|SUBCONTRACT(?:OR)?)\s+AGREEMENT", re.I), "MSA"),
    (re.compile(r"PROFESSIONAL\s+SERVICES?\s+AGREEMENT",              re.I), "PSA"),
    (re.compile(r"MASTER\s+PURCHASING\s+AGREEMENT",                   re.I), "MPA"),
    (re.compile(r"\bSTATEMENT\s+OF\s+WORK\b|\bSOW\b",               re.I), "SOW"),
    (re.compile(r"\bEND.USER\s+LICENSE\s+AGREEMENT\b|\bEULA\b",      re.I), "EULA"),
    (re.compile(r"\bPURCHASE\s+ORDER\b|\bPROCUREMENT\s+ORDER\b",    re.I), "PO"),
    (re.compile(r"SUBCONTRACT(?!OR)",                                  re.I), "Subcontract"),
    (re.compile(r"CHANGE\s+ORDER",                                     re.I), "Change Order"),
    (re.compile(r"\bAMENDMENT\b",                                      re.I), "Amendment"),
    (re.compile(r"\bEXHIBIT\b",                                        re.I), "Exhibit"),
]


def detect_doc_type(name: str) -> str:
    for pat, dt in _DOC_PATTERNS:
        if pat.search(name):
            return dt
    return ""


# ══════════════════════════════════════════════════════════════════════════════
# DATE-IN-FILENAME PARSING  (§Never Trust Filesystem Dates — filename only)
# ══════════════════════════════════════════════════════════════════════════════

def _resolve_six_digit_dotted(raw: str) -> tuple[str, str]:
    """
    Disambiguate a NN.NN.NN dotted date string per spec disambiguation rules.
    Returns (date_str, ambiguity_note).
    date_str is "" when disambiguation fails or both interpretations are plausible.
    ambiguity_note is "" when the result is silently unambiguous.

    Rules (in order):
      a. Only one interpretation is a valid calendar date → use it silently.
      b. Both valid but one is current/recent (≥ _TODAY_YEAR-1) and the other
         is clearly stale (≤ _TODAY_YEAR-4) → prefer recent, ManualReview=True.
      c. Both valid and both plausible → leave date blank, ManualReview=True.
    """
    parts = raw.split(".")
    if len(parts) != 3:
        return "", ""
    try:
        a, b, c = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return "", ""

    d_ymd = None   # YY.MM.DD
    d_dmy = None   # DD.MM.YY
    try:
        d_ymd = date(2000 + a, b, c)
    except ValueError:
        pass
    try:
        d_dmy = date(2000 + c, b, a)
    except ValueError:
        pass

    ymd_str = d_ymd.strftime("%Y-%m-%d") if d_ymd else ""
    dmy_str = d_dmy.strftime("%Y-%m-%d") if d_dmy else ""

    # Rule a: exactly one interpretation is a valid calendar date
    if d_ymd and not d_dmy:
        return ymd_str, ""
    if d_dmy and not d_ymd:
        return dmy_str, ""
    if not d_ymd and not d_dmy:
        return "", ""

    # Both valid — Rule b: one is recent, the other clearly stale
    ymd_recent = d_ymd.year >= _TODAY_YEAR - 1
    dmy_recent = d_dmy.year >= _TODAY_YEAR - 1
    ymd_stale  = d_ymd.year <= _TODAY_YEAR - 4
    dmy_stale  = d_dmy.year <= _TODAY_YEAR - 4

    if ymd_recent and dmy_stale:
        return ymd_str, (
            f"ambiguous 6-digit date '{raw}': "
            f"YY.MM.DD={ymd_str} vs DD.MM.YY={dmy_str} "
            f"— preferred recent reading, manual review recommended"
        )
    if dmy_recent and ymd_stale:
        return dmy_str, (
            f"ambiguous 6-digit date '{raw}': "
            f"DD.MM.YY={dmy_str} vs YY.MM.DD={ymd_str} "
            f"— preferred recent reading, manual review recommended"
        )

    # Rule c: both valid and plausible — do not guess, leave blank
    return "", (
        f"ambiguous 6-digit date '{raw}': "
        f"YY.MM.DD={ymd_str} vs DD.MM.YY={dmy_str} "
        f"— manual disambiguation required"
    )


def parse_date_in_filename(name: str) -> tuple[str, str]:
    """
    Returns (date_str, ambiguity_note).
    date_str is "" if no date found or disambiguation failed.
    ambiguity_note is "" when unambiguous; non-empty when ManualReview is needed.
    Priority: MM.DD.YYYY → YYYY.MM.DD → NN.NN.NN (disambiguated) → M-D-YY/YYYY
    Never uses filesystem timestamps (§Never Trust Filesystem Dates).
    """
    # MM.DD.YYYY or MM/DD/YYYY  (4-digit year — unambiguous)
    m = re.search(r"\b(\d{2})[./](\d{2})[./](\d{4})\b", name)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2))).strftime("%Y-%m-%d"), ""
        except ValueError:
            pass

    # YYYY.MM.DD  (4-digit year first — unambiguous)
    m = re.search(r"\b(\d{4})[.](\d{2})[.](\d{2})\b", name)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%Y-%m-%d"), ""
        except ValueError:
            pass

    # NN.NN.NN — 6-digit dotted: apply disambiguation rules (never silent-guess)
    m = re.search(r"\b(\d{2})[.](\d{2})[.](\d{2})\b", name)
    if m:
        date_str, ambiguity_note = _resolve_six_digit_dotted(m.group(0))
        if date_str or ambiguity_note:
            return date_str, ambiguity_note

    # M-D-YY or M-D-YYYY  (hyphen separator, month/day order unambiguous)
    m = re.search(r"\b(\d{1,2})-(\d{1,2})-(\d{2,4})\b", name)
    if m:
        try:
            yr = int(m.group(3))
            if yr < 100:
                yr += 2000
            return datetime(yr, int(m.group(1)), int(m.group(2))).strftime("%Y-%m-%d"), ""
        except ValueError:
            pass

    return "", ""


# ══════════════════════════════════════════════════════════════════════════════
# PDF DATE EXTRACTION  (§PDF Date Extraction)
# ══════════════════════════════════════════════════════════════════════════════

_MONTH_FULL = (
    r"(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)"
)
_MONTH_ABR = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
_DATE_PAT = (
    r"(?:"
    + _MONTH_FULL + r"\s+\d{1,2},?\s+\d{4}"
    + r"|\d{1,2}\s+" + _MONTH_FULL + r"\s+\d{4}"
    + r"|\d{1,2}\s+" + _MONTH_ABR + r"[a-z]*\s+\d{4}"
    + r"|\d{4}-\d{2}-\d{2}"
    + r"|\d{1,2}/\d{1,2}/\d{2,4}"
    + r"|\d{1,2}\.\d{1,2}\.\d{4}"
    + r"|\d{2}\.\d{2}\.\d{2}"        # 6-digit dotted (e.g. 26.06.22) — disambiguated at parse time
    + r")"
)

# HIGH: explicit effective-date labels
_EFF_HIGH_RE = re.compile(
    r"(?:"
    r"effective\s+(?:as\s+of\s+)?"
    r"|entered\s+into\s+(?:as\s+of\s+|effect\s+)?"
    r"|made\s+(?:and\s+entered\s+into\s+)?(?:as\s+of\s+)?"
    r"|is\s+made\s+(?:and\s+entered\s+into\s+)?as\s+of\s+"
    r"|dated\s+(?:as\s+of\s+)?"
    r"|commencement\s+date\s*[:\s]+"
    r")"
    r"(?:the\s+)?" + _DATE_PAT,
    re.IGNORECASE,
)

# HIGH: ordinal "effective as of the 2nd day of February 2026"
_ORDINAL_EFF_RE = re.compile(
    r"(?:effective|dated|made|entered\s+into)\s+(?:as\s+of\s+)?the\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+day\s+of\s+"
    r"(" + _MONTH_FULL[3:] + r"[,\s]+(\d{4})",  # strip leading "(?:"
    re.IGNORECASE,
)

# LOW: bare "as of [date]" without explicit label
_AS_OF_LOW_RE = re.compile(r"\bas\s+of\s+" + _DATE_PAT, re.IGNORECASE)

# LOW fallback: signature block "Date: ..."
_SIG_DATE_RE = re.compile(
    r"(?:^|\n)(?:Date(?:\s+Signed)?|Dated?)\s*[:\s]\s*(" + _DATE_PAT + r")",
    re.IGNORECASE,
)

# HIGH: explicit expiration language
_EXP_HIGH_RE = re.compile(
    r"(?:expir(?:es?|ation(?:\s+date)?)|terminat(?:es?|ion\s+date)|"
    r"\bthrough\b|\buntil\b|ending\s+on)"
    r"\s+(?:on\s+)?" + _DATE_PAT,
    re.IGNORECASE,
)

# Perpetual / at-will signals (→ perpetual-no-expiration)
_PERPETUAL_RE = re.compile(
    r"perpetual\s+(?:non-exclusive\s+)?(?:\w+[-\s]){0,3}license"
    r"|shall\s+remain\s+in\s+full\s+force.{0,80}?until.{0,80}?terminat"
    r"|either\s+party\s+may\s+terminat"
    r"|terminat\w*\s+this\s+agreement\s+at\s+any\s+time"
    r"|upon\s+(?:thirty|sixty|ninety|\d+)\s+days?\s+(?:prior\s+)?(?:written\s+)?notice"
    r"|upon\s+written\s+notice\s+to\s+the\s+other",
    re.IGNORECASE,
)

# Term duration for computed ExpirationDate
_TERM_YEARS_RE = re.compile(
    r"(?:term\s+of\s+(?:this\s+agreement\s+)?(?:shall\s+be\s+)?|"
    r"for\s+a\s+(?:period\s+of\s+)?)"
    r"(\w+|\d+)\s*(?:\(\d+\)\s*)?year(?:s)?",
    re.IGNORECASE,
)
_TERM_MONTHS_RE = re.compile(
    r"(?:term\s+of\s+(?:this\s+agreement\s+)?(?:shall\s+be\s+)?|"
    r"for\s+a\s+(?:period\s+of\s+)?)"
    r"(\w+|\d+)\s*(?:\(\d+\)\s*)?month(?:s)?",
    re.IGNORECASE,
)
_WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _parse_date_str(s: str) -> date | None:
    """Parse a clearly-formatted date string (ISO, month-name, M/D/Y). Not for 6-digit dotted."""
    s = s.strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    try:
        from dateutil import parser as dp
        return dp.parse(s, dayfirst=False).date()
    except Exception:
        return None


def _parse_date_with_ambiguity(s: str) -> tuple[date | None, str]:
    """
    Like _parse_date_str but handles NN.NN.NN with full disambiguation.
    Returns (parsed_date, ambiguity_note). ambiguity_note is "" when unambiguous.
    """
    s = s.strip()
    if re.match(r"^\d{2}\.\d{2}\.\d{2}$", s):
        date_str, ambig = _resolve_six_digit_dotted(s)
        if date_str:
            try:
                return date.fromisoformat(date_str), ambig
            except ValueError:
                pass
        return None, ambig
    return _parse_date_str(s), ""


def _snippet(text: str, m: re.Match, chars: int = 120) -> str:
    start = max(0, m.start() - 10)
    end   = min(len(text), m.end() + 10)
    return text[start:end].replace("\n", " ").strip()[:chars]


class DateResult:
    __slots__ = ("value", "confidence", "source", "ambiguity")

    def __init__(self, value: str, confidence: str, source: str, ambiguity: str = ""):
        self.value      = value       # "2026-06-11" or ""
        self.confidence = confidence  # "HIGH" | "LOW" | "NOT_FOUND"
        self.source     = source      # source phrase or reason string
        self.ambiguity  = ambiguity   # non-empty when 6-digit date disambiguation fired


def _extract_effective(text: str) -> DateResult:
    # 1. Ordinal pattern (HIGH): "effective as of the 2nd day of February 2026"
    m = _ORDINAL_EFF_RE.search(text)
    if m:
        try:
            from dateutil import parser as dp
            # group(1)=day, rest of match captures month+year
            raw = m.group(0)
            d = dp.parse(raw, dayfirst=False).date()
            return DateResult(d.strftime("%Y-%m-%d"), "HIGH", _snippet(text, m))
        except Exception:
            pass

    # 2. Labeled patterns (HIGH; downgrade to LOW if date itself is 6-digit ambiguous)
    for m in _EFF_HIGH_RE.finditer(text):
        dp_match = re.search(_DATE_PAT, m.group(0), re.IGNORECASE)
        if dp_match:
            d, ambig = _parse_date_with_ambiguity(dp_match.group(0))
            if d:
                conf = "LOW" if ambig else "HIGH"
                return DateResult(d.strftime("%Y-%m-%d"), conf, _snippet(text, m), ambig)

    # 3. Bare "as of [date]" — LOW (single candidate only)
    candidates = list(_AS_OF_LOW_RE.finditer(text))
    if len(candidates) == 1:
        dp_match = re.search(_DATE_PAT, candidates[0].group(0), re.IGNORECASE)
        if dp_match:
            d, ambig = _parse_date_with_ambiguity(dp_match.group(0))
            if d:
                return DateResult(d.strftime("%Y-%m-%d"), "LOW", _snippet(text, candidates[0]), ambig)
    elif len(candidates) > 1:
        return DateResult("", "NOT_FOUND", "effective-date-not-found (multiple as-of candidates)")

    # 4. Signature date block — LOW fallback
    sig_matches = list(_SIG_DATE_RE.finditer(text))
    if len(sig_matches) == 1:
        d, ambig = _parse_date_with_ambiguity(sig_matches[0].group(1))
        if d:
            return DateResult(d.strftime("%Y-%m-%d"), "LOW", _snippet(text, sig_matches[0]), ambig)

    return DateResult("", "NOT_FOUND", "effective-date-not-found")


def _extract_expiration(text: str, eff_result: DateResult) -> DateResult:
    # Perpetual / at-will → no expiration
    if _PERPETUAL_RE.search(text):
        return DateResult("", "NOT_FOUND", "perpetual-no-expiration")

    # Explicit expiration date (HIGH; downgrade to LOW if date itself is 6-digit ambiguous)
    exp_matches = list(_EXP_HIGH_RE.finditer(text))
    if len(exp_matches) == 1:
        dp_match = re.search(_DATE_PAT, exp_matches[0].group(0), re.IGNORECASE)
        if dp_match:
            d, ambig = _parse_date_with_ambiguity(dp_match.group(0))
            if d:
                conf = "LOW" if ambig else "HIGH"
                return DateResult(d.strftime("%Y-%m-%d"), conf, _snippet(text, exp_matches[0]), ambig)
    elif len(exp_matches) > 1:
        return DateResult("", "NOT_FOUND", "expiration-date-not-found (multiple candidates)")

    # Compute from term duration (HIGH if effective date known)
    if eff_result.value:
        eff_d = _parse_date_str(eff_result.value)
        if eff_d:
            try:
                from dateutil.relativedelta import relativedelta
            except ImportError:
                relativedelta = None

            ym = _TERM_YEARS_RE.search(text)
            mm = _TERM_MONTHS_RE.search(text)
            n_years = n_months = None
            src = ""
            if ym:
                raw = ym.group(1).lower()
                n_years = _WORD_TO_NUM.get(raw) or (int(raw) if raw.isdigit() else None)
                src = _snippet(text, ym)
            elif mm:
                raw = mm.group(1).lower()
                n_months = _WORD_TO_NUM.get(raw) or (int(raw) if raw.isdigit() else None)
                src = _snippet(text, mm)

            if relativedelta and n_years:
                return DateResult(
                    (eff_d + relativedelta(years=n_years)).strftime("%Y-%m-%d"),
                    "HIGH", src,
                )
            if relativedelta and n_months:
                return DateResult(
                    (eff_d + relativedelta(months=n_months)).strftime("%Y-%m-%d"),
                    "HIGH", src,
                )

    return DateResult("", "NOT_FOUND", "expiration-date-not-found")


def extract_dates_from_pdf(path: Path) -> tuple[DateResult, DateResult]:
    """
    Returns (effective_result, expiration_result).
    Source: PDF text via pdfplumber only. Never filesystem timestamps.
    """
    no_text = DateResult("", "NOT_FOUND", "no-text-layer")
    try:
        with pdfplumber.open(str(path)) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
        text = "\n".join(pages)
    except Exception as e:
        return (
            DateResult("", "NOT_FOUND", f"no-text-layer (open failed: {e})"),
            DateResult("", "NOT_FOUND", f"no-text-layer (open failed: {e})"),
        )

    if len(text.strip()) < 50:
        return no_text, no_text

    eff = _extract_effective(text)
    exp = _extract_expiration(text, eff)
    return eff, exp


# ══════════════════════════════════════════════════════════════════════════════
# STATUS DERIVATION  (§Status Invariant — never blank)
# ══════════════════════════════════════════════════════════════════════════════

def derive_status(name: str, is_audit: bool) -> str:
    if is_audit:
        return "reference"
    nl = name.lower()
    if re.search(r"\b(?:signed|executed|fully\s+executed)\b", nl):
        return "active"
    if re.search(r"\bunsigned\b", nl):
        return "unsigned"
    return "unsigned"   # conservative fallback; renders under Unsigned filter


# ══════════════════════════════════════════════════════════════════════════════
# FILE SCANNING
# ══════════════════════════════════════════════════════════════════════════════

def is_excluded(path: Path) -> tuple[bool, str]:
    if path.name.lower() == "desktop.ini" or path.suffix.lower() == ".ini":
        return True, "desktop.ini / .ini excluded"
    if any(part.startswith(".claude") for part in path.parts):
        return True, ".claude path excluded"
    if path.suffix.lower() not in SUPPORTED_EXT:
        return True, f"extension {path.suffix!r} not supported"
    return False, ""


def scan_candidates(cutoff: datetime) -> list[dict]:
    """
    Walk SCAN_ROOT. Return info dict for each file where
    CreationTime >= cutoff OR LastWriteTime >= cutoff.
    Trigger detection uses filesystem times ONLY for scan qualification —
    never for date population (§Never Trust Filesystem Dates).
    """
    if not SCAN_ROOT.exists():
        raise FileNotFoundError(f"SCAN ROOT not found: {SCAN_ROOT}")

    results = []
    for f in sorted(SCAN_ROOT.rglob("*")):
        if not f.is_file():
            continue
        exc, reason = is_excluded(f)
        if exc:
            log(f"[SKIP] {f.name} — {reason}")
            continue
        try:
            st = f.stat()
        except OSError:
            log(f"[SKIP] {f.name} — stat() failed")
            continue

        ctime = datetime.fromtimestamp(st.st_ctime)
        mtime = datetime.fromtimestamp(st.st_mtime)
        created_new  = ctime >= cutoff
        modified_new = mtime >= cutoff
        if not (created_new or modified_new):
            continue

        rel   = f.relative_to(SCAN_ROOT)
        parts = rel.parts
        vendor = parts[0] if len(parts) > 1 else ""
        fp_key = "/".join(parts)
        trigger = (
            "new (created+modified)" if created_new and modified_new else
            "new (created)"          if created_new else
            "new (modified)"
        )
        results.append({
            "abs_path": f,
            "rel_path": fp_key,
            "vendor":   vendor,
            "trigger":  trigger,
        })
    return results


# ══════════════════════════════════════════════════════════════════════════════
# CSV HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _parse_csv_row(line: str) -> list[str]:
    result, cur, in_q = [], "", False
    i = 0
    while i < len(line):
        c = line[i]
        if c == '"':
            if in_q and i + 1 < len(line) and line[i + 1] == '"':
                cur += '"'; i += 1
            else:
                in_q = not in_q
        elif c == ',' and not in_q:
            result.append(cur); cur = ""
        else:
            cur += c
        i += 1
    result.append(cur)
    return result


def _q(s: str) -> str:
    return '"' + str(s).replace('"', '""') + '"'


def build_csv_line(row: dict) -> str:
    return ",".join(_q(row.get(c, "")) for c in COLUMNS)


def read_catalog() -> tuple[str, list[str], set[tuple[str, str]]]:
    """Returns (header, data_lines, existing_keys).

    existing_keys is keyed on (ContractLocation, FilePath) — the catalog
    uniqueness invariant. FilePath ALONE is not a key: the same relative path
    legitimately exists in two locations (e.g. an unsigned draft in 02 and the
    signed copy in 01). Keying on FilePath alone made this scanner skip a
    genuinely new 01 Active file as "already catalogued" whenever that path
    existed under any other location.
    """
    raw = CATALOG.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    lines = [l for l in raw.decode("utf-8").split("\r\n") if l]
    if not lines:
        raise ValueError("catalog is empty")
    header = lines[0]
    data   = lines[1:]
    existing = set()
    for l in data:
        cells = _parse_csv_row(l)
        if len(cells) >= 4:
            existing.add((cells[0], cells[3].lower()))   # (ContractLocation, FilePath)
    return header, data, existing


def write_catalog(header: str, data: list[str], new_lines: list[str]) -> None:
    import shutil
    shutil.copy2(str(CATALOG), str(CATALOG.with_suffix(".csv.bak")))
    content = "\r\n".join([header] + data + new_lines) + "\r\n"
    CATALOG.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))


def write_staged(new_lines: list[str], run_date: date) -> Path:
    staged = REPO_DIR / f"catalog-staged-{run_date.strftime('%Y-%m-%d')}.csv"
    header = ",".join(_q(c) for c in COLUMNS)
    content = "\r\n".join([header] + new_lines) + "\r\n"
    staged.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
    return staged


# ══════════════════════════════════════════════════════════════════════════════
# ROW BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_row(
    f_info: dict,
    eff: DateResult,
    exp: DateResult,
    today: date,
) -> tuple[dict, list[str]]:
    """
    Returns (row_dict, log_lines_for_this_file).
    All date fields sourced from filename parse or PDF text — never filesystem.
    """
    name     = f_info["abs_path"].name
    rel_path = f_info["rel_path"]
    vendor   = f_info["vendor"]
    trigger  = f_info["trigger"]
    ext      = f_info["abs_path"].suffix.lower()

    date_in_fn, fn_ambiguity = parse_date_in_filename(name)

    doc_type = detect_doc_type(name)
    nl = name.lower()

    has_signed_kw = re.search(r"\b(?:signed|executed|fully\s+executed)\b", nl)
    has_signed    = "True" if has_signed_kw else "False"
    signing_status = "Signed" if has_signed_kw else ""

    is_amendment = "False"
    amend_num    = ""
    if re.search(r"\b(?:amendment|amend|change\s+order)\b", nl):
        is_amendment = "True"
        m = re.search(r"(?:amendment|amend|change\s+order)\s*#?\s*(\d+)", nl)
        if m:
            amend_num = m.group(1)

    ver_label = ""
    m = re.search(r"\bv(\d+(?:\.\d+)+)\b", name, re.IGNORECASE)
    if m:
        ver_label = "v" + m.group(1)

    is_audit = bool(re.search(r"\baudit\b", nl))

    # ── Notes ────────────────────────────────────────────────────────────────
    note_parts: list[str] = [trigger]
    if not date_in_fn:
        note_parts.append("created-date-unverified")
    if eff.confidence == "NOT_FOUND":
        note_parts.append(eff.source)
    if exp.confidence == "NOT_FOUND" and exp.source not in note_parts:
        note_parts.append(exp.source)
    notes = "; ".join(dict.fromkeys(note_parts))   # dedupe, preserve order

    # Collect all date-ambiguity notes for this file (filename + PDF sides)
    all_ambiguities: list[str] = [
        a for a in [fn_ambiguity, eff.ambiguity, exp.ambiguity] if a
    ]

    # ── DaysUntilExpiration ───────────────────────────────────────────────────
    days_str = ""
    if exp.value:
        try:
            exp_d = date.fromisoformat(exp.value)
            days_str = str((exp_d - today).days)
        except ValueError:
            pass

    # ── ManualReview / ManualReviewNote ───────────────────────────────────────
    manual_review      = ""
    mr_note_parts: list[str] = []
    # 6-digit filename date ambiguity
    if fn_ambiguity:
        manual_review = "True"
        mr_note_parts.append(fn_ambiguity)
    # Low-confidence PDF extraction (includes 6-digit ambiguity downgraded to LOW)
    if eff.confidence == "LOW":
        manual_review = "True"
        if eff.ambiguity:
            mr_note_parts.append(eff.ambiguity)
        else:
            mr_note_parts.append(f"auto-extracted effective-date low-confidence: '{eff.source}'")
    if exp.confidence == "LOW":
        manual_review = "True"
        if exp.ambiguity:
            mr_note_parts.append(exp.ambiguity)
        else:
            mr_note_parts.append(f"auto-extracted expiration-date low-confidence: '{exp.source}'")
    if is_audit:
        manual_review = "True"
        mr_note_parts.append("audit-trail copy — not the executed instrument")
    manual_review_note = "; ".join(mr_note_parts)

    # ── Status — never blank (§Status Invariant) ─────────────────────────────
    status = derive_status(name, is_audit)
    # Low-confidence rows still get the correct operative status (not blank)
    if manual_review == "True" and not is_audit and status not in ("active", "unsigned"):
        status = "active"

    row = {
        "ContractLocation":    "01 Active Contracts",
        "VendorFolder":        vendor,
        "Filename":            name,
        "FilePath":            rel_path,
        "Extension":           ext,
        "DocType":             doc_type,
        "HasSignedKeyword":    has_signed,
        "SigningStatus":       signing_status,
        "IsAmendment":         is_amendment,
        "AmendmentNumber":     amend_num,
        "VersionLabel":        ver_label,
        "DateInFilename":      date_in_fn,
        "CounterpartyName":    vendor,
        "EffectiveDate":       eff.value,
        "ExpirationDate":      exp.value,
        "DaysUntilExpiration": days_str,
        "Notes":               notes,
        "Status":              status,
        "SurvivalRunning":     "",
        "Stale":               "",
        "SurvivalEndDate":     "",
        "ManualReview":        manual_review,
        "ManualReviewNote":    manual_review_note,
    }

    # Per-file log block
    file_log: list[str] = [f"[NEW] {rel_path}"]
    file_log.append(f"  DateInFilename   : {date_in_fn or '(none)'}")
    for ambig in all_ambiguities:
        file_log.append(f"[DATE-AMBIGUOUS] {ambig}")
    if eff.value:
        file_log.append(f"  EffectiveDate    : {eff.value}  [{eff.confidence}]  source: '{eff.source}'")
    else:
        file_log.append(f"  EffectiveDate    : (blank)  reason: {eff.source}")
    if exp.value:
        file_log.append(f"  ExpirationDate   : {exp.value}  [{exp.confidence}]  source: '{exp.source}'")
    else:
        file_log.append(f"  ExpirationDate   : (blank)  reason: {exp.source}")
    if days_str:
        file_log.append(f"  DaysUntilExpiration: {days_str}")
    file_log.append(f"  Status           : {status}")
    if manual_review:
        file_log.append(f"  ManualReview     : True")
    if manual_review_note:
        file_log.append(f"  ManualReviewNote : {manual_review_note}")

    return row, file_log


# ══════════════════════════════════════════════════════════════════════════════
# GIT / DEPLOY GUARD
# ══════════════════════════════════════════════════════════════════════════════

def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(REPO_DIR)] + list(args),
        capture_output=True, text=True,
    )


def check_deploy_guard() -> bool:
    """Confirm skip_app_build: true is present in the Actions workflow."""
    if not WORKFLOW_FILE.exists():
        return False
    content = WORKFLOW_FILE.read_text(encoding="utf-8")
    return bool(re.search(r"^\s*skip_app_build\s*:\s*true\b", content, re.MULTILINE))


def commit_and_push(n_rows: int, run_date: date, dry: bool) -> bool:
    if dry:
        log(f"[DRY-RUN] Would stage: git add -- contract-catalog.csv")
        log(f"[DRY-RUN] Would commit: 'nightly catalog scan {run_date}: +{n_rows} new rows'")
        log(f"[DRY-RUN] Would check deploy guard then: git push origin main")
        return True

    # Stage only the catalog
    r = _git("add", "--", "contract-catalog.csv")
    if r.returncode != 0:
        log(f"[ERROR] git add failed: {r.stderr.strip()}")
        return False

    # Guard: nothing else staged
    r2 = _git("diff", "--cached", "--name-only")
    staged_files = [l for l in r2.stdout.splitlines() if l.strip()]
    if staged_files != ["contract-catalog.csv"]:
        _git("restore", "--staged", ".")
        log(f"[ABORT] unexpected staged files {staged_files} — manual review required")
        return False

    # Commit
    msg = f"nightly catalog scan {run_date}: +{n_rows} new rows"
    r = _git("commit", "-m", msg)
    if r.returncode != 0:
        log(f"[ERROR] git commit failed: {r.stderr.strip()}")
        return False
    sha = _git("rev-parse", "--short", "HEAD").stdout.strip()
    log(f"[COMMIT] {sha}  main  \"{msg}\"")

    # Deploy guard (§Commit & push protocol — mandatory before every push)
    if not check_deploy_guard():
        log("[DEPLOY GUARD MISSING — push aborted]")
        return False

    # Push
    r = _git("push", "origin", "main")
    if r.returncode != 0:
        log(f"[ERROR] git push failed: {r.stderr.strip()}")
        return False
    ff = re.search(r"(\w+)\.\.(\w+)", r.stderr + r.stdout)
    log(f"[PUSH]  {ff.group(0) if ff else '?'}  main -> main")

    # First autonomous push sentinel
    if not FIRST_PUSH_FLAG.exists():
        log(
            "[FIRST AUTONOMOUS PUSH — confirm pipeline end-to-end at "
            "https://github.com/jrudyg/dcs-contract-mgmt-tools]"
        )
        FIRST_PUSH_FLAG.touch()

    return True


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Nightly contract catalog scanner — spec NIGHTLY_CATALOG_JOB.md v1.2"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only — no writes, no commits, no log entries")
    parser.add_argument("--force",   action="store_true",
                        help="Override circuit breaker; read staged file if present")
    parser.add_argument("--cutoff",  default=None, metavar="YYYY-MM-DD",
                        help="Override scan cutoff (default: yesterday midnight local)")
    args = parser.parse_args()

    dry   = args.dry_run
    force = args.force
    today = datetime.now().date()

    if args.cutoff:
        cutoff = datetime.strptime(args.cutoff, "%Y-%m-%d")
    else:
        cutoff = datetime(today.year, today.month, today.day) - timedelta(days=1)

    run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log(f"===== nightly-catalog-scan — {run_ts} =====")
    if dry:
        log("[DRY-RUN MODE — no files will be written or committed]")

    # ── Read existing catalog ─────────────────────────────────────────────────
    try:
        header, data_lines, existing_paths = read_catalog()
    except Exception as e:
        log(f"[ERROR] Cannot read catalog: {e}")
        flush_log(dry)
        sys.exit(1)

    # ── --force: look for a staged file from today or yesterday ───────────────
    using_staged: Path | None = None
    if force:
        for candidate in [
            REPO_DIR / f"catalog-staged-{today.strftime('%Y-%m-%d')}.csv",
            REPO_DIR / f"catalog-staged-{(today - timedelta(days=1)).strftime('%Y-%m-%d')}.csv",
        ]:
            if candidate.exists():
                using_staged = candidate
                break

    if using_staged:
        log(f"[FORCE] Reading from staged file: {using_staged.name}")
        raw = using_staged.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        # skip staged header line
        new_csv_lines = [l for l in raw.decode("utf-8").split("\r\n") if l][1:]
        n_commit = len(new_csv_lines)
        log(f"  {n_commit} row(s) loaded from staged file.")

    else:
        # ── Normal scan ───────────────────────────────────────────────────────
        log(f"  Cutoff : {cutoff.strftime('%Y-%m-%d %H:%M:%S')} local")
        log(f"  Scan   : {SCAN_ROOT}")

        try:
            candidates = scan_candidates(cutoff)
        except FileNotFoundError as e:
            log(f"[ERROR] {e}")
            flush_log(dry)
            sys.exit(1)

        # Dedupe on (ContractLocation, FilePath) — this scanner only ever writes
        # rows for "01 Active Contracts", so that is the location to test.
        new_files = [c for c in candidates
                     if ("01 Active Contracts", c["rel_path"].lower()) not in existing_paths]
        n_new = len(new_files)

        log(
            f"[CIRCUIT BREAKER {'PASS' if n_new <= CIRCUIT_BREAKER else 'CHECK'}] "
            f"{n_new} new file(s) detected (threshold {CIRCUIT_BREAKER})"
        )

        # ── Circuit breaker ───────────────────────────────────────────────────
        if n_new > CIRCUIT_BREAKER and not force:
            # Build minimal rows for staged file (full PDF extraction skipped)
            proposed: list[str] = []
            vendor_counts: dict[str, int] = defaultdict(int)
            for f_info in new_files:
                name   = f_info["abs_path"].name
                vendor = f_info["vendor"]
                vendor_counts[vendor] += 1
                nl     = name.lower()
                d_fn, _ = parse_date_in_filename(name)   # ambiguity not surfaced in staged-only rows
                is_aud  = bool(re.search(r"\baudit\b", nl))
                row = {c: "" for c in COLUMNS}
                row.update({
                    "ContractLocation": "01 Active Contracts",
                    "VendorFolder":     vendor,
                    "Filename":         name,
                    "FilePath":         f_info["rel_path"],
                    "Extension":        f_info["abs_path"].suffix.lower(),
                    "DateInFilename":   d_fn,
                    "DocType":          detect_doc_type(name),
                    "HasSignedKeyword": "True" if re.search(r"\b(?:signed|executed)\b", nl) else "False",
                    "SigningStatus":    "Signed" if re.search(r"\b(?:signed|executed)\b", nl) else "",
                    "CounterpartyName": vendor,
                    "Notes":            f_info["trigger"] + "; circuit-breaker-staged",
                    "Status":           derive_status(name, is_aud),
                })
                proposed.append(build_csv_line(row))

            if not dry:
                sf = write_staged(proposed, today)
            else:
                sf = REPO_DIR / f"catalog-staged-{today.strftime('%Y-%m-%d')}.csv"

            vendor_list = ", ".join(f"{v} ({c})" for v, c in sorted(vendor_counts.items()))
            log(f"[CIRCUIT BREAKER TRIPPED] {today}  N={n_new} rows detected — threshold {CIRCUIT_BREAKER}")
            log(f"  Staged to: {sf.name}")
            log(f"  Vendors: {vendor_list}")
            log(f"  Action required: review staged file, then run --force if legitimate.")
            flush_log(dry)
            sys.exit(1)

        # ── Full build with PDF extraction ────────────────────────────────────
        new_csv_lines: list[str] = []
        for f_info in new_files:
            ext = f_info["abs_path"].suffix.lower()
            if ext == ".pdf":
                eff_r, exp_r = extract_dates_from_pdf(f_info["abs_path"])
            else:
                skip_msg = f"pdf-extraction-skipped (non-pdf: {ext})"
                eff_r = DateResult("", "NOT_FOUND", skip_msg)
                exp_r = DateResult("", "NOT_FOUND", skip_msg)

            row, file_log_lines = build_row(f_info, eff_r, exp_r, today)
            for line in file_log_lines:
                log(line)
            new_csv_lines.append(build_csv_line(row))

        n_commit = len(new_csv_lines)

    # ── Nothing to do ─────────────────────────────────────────────────────────
    if n_commit == 0:
        log("[DONE] No new files — nothing to commit.")
        flush_log(dry)
        return

    if dry:
        log(f"\n[DRY-RUN SUMMARY] Would append {n_commit} row(s) to {CATALOG.name}")
        flush_log(dry)
        return

    # ── Write + commit + push ─────────────────────────────────────────────────
    write_catalog(header, data_lines, new_csv_lines)
    ok = commit_and_push(n_commit, today, dry)

    if not ok:
        flush_log(dry)
        sys.exit(1)

    # Clean up staged file after successful --force apply
    if using_staged and using_staged.exists():
        using_staged.unlink()
        log(f"[CLEANUP] Removed staged file: {using_staged.name}")

    log(f"[DONE] {n_commit} row(s) committed and pushed.")
    flush_log(dry)


if __name__ == "__main__":
    main()
