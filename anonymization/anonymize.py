#!/usr/bin/env python3
"""
anonymize.py — P3 contract anonymization pipeline

Layers applied in order:
  1. Counterparty redaction  (deterministic map from mapping.json)
  2. PII detection/redaction (Presidio + spaCy en_core_web_lg)
  3. Commercial terms regex  (currency, percentages, payment terms, rates)

Output per file (written to --output-dir, gitignored):
  <stem>.anon.txt   — redacted plain text
  <stem>.audit.json — redaction inventory (--audit flag required)

Usage:
  python anonymize.py --input path/to/file.pdf --audit
  python anonymize.py --input path/to/dir/ --output-dir anonymization/output --audit
  python anonymize.py --input file.pdf --rebuild-map
"""

import argparse
import json
import logging
import pathlib
import re
import time
from typing import Optional

import pdfplumber
from docx import Document
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUDED_COUNTERPARTIES: frozenset[str] = frozenset({
    "(blank)",
    "A. MNDA Template",
    "ACI for Signature",
})

PRESIDIO_ENTITIES: list[str] = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "US_SSN",
    "DATE_TIME",
    "LOCATION",
    "NRP",
    "US_BANK_NUMBER",
    "CREDIT_CARD",
]

# Commercial terms patterns — applied in listed order, IGNORECASE|MULTILINE.
# Note: TERM_DURATION is context-free in this version; false positives are
# acceptable in the pilot and will be tuned in ANON-5.
COMMERCIAL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\$[\d,]+(?:\.\d{1,2})?',  re.MULTILINE), '[AMOUNT]'),
    (re.compile(r'\d+(?:\.\d+)?\s*%',        re.MULTILINE), '[PERCENT]'),
    (re.compile(r'\bnet\s*\d+\b',            re.IGNORECASE | re.MULTILINE), '[PAYMENT_TERM]'),
    (re.compile(r'\$[\d.]+\s*/\s*\w+',       re.MULTILINE), '[RATE]'),
    (re.compile(r'\d+\s*(?:days?|weeks?|months?|years?)',
                re.IGNORECASE | re.MULTILINE), '[TERM_DURATION]'),
]

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({'.pdf', '.docx', '.doc', '.txt'})

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-7s  %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapping: build or load
# ---------------------------------------------------------------------------

def build_mapping(counterparties_path: pathlib.Path, mapping_path: pathlib.Path) -> dict[str, str]:
    """Parse kb/COUNTERPARTIES.md and write a fresh mapping.json."""
    name_pattern = re.compile(r'^\*\*(.+?)\*\*')
    entries: dict[str, str] = {}
    idx = 1
    with open(counterparties_path, encoding='utf-8') as fh:
        for line in fh:
            m = name_pattern.match(line)
            if m:
                name = m.group(1).strip()
                if name not in EXCLUDED_COUNTERPARTIES:
                    entries[name] = f'PARTY-{idx:04d}'
                    idx += 1

    payload = {
        'generated': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'version': 1,
        'excluded': sorted(EXCLUDED_COUNTERPARTIES),
        'entries': entries,
    }
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    with open(mapping_path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    log.info('Built mapping: %d entries → %s', len(entries), mapping_path)
    return entries


def load_mapping(mapping_path: pathlib.Path) -> dict[str, str]:
    """Load an existing mapping.json and return its entries dict."""
    with open(mapping_path, encoding='utf-8') as fh:
        payload = json.load(fh)
    entries: dict[str, str] = payload['entries']
    log.info('Loaded mapping: %d entries from %s', len(entries), mapping_path)
    return entries


def get_mapping(
    mapping_path: pathlib.Path,
    counterparties_path: pathlib.Path,
    rebuild: bool,
) -> dict[str, str]:
    """Return the counterparty mapping, building it if necessary."""
    if rebuild or not mapping_path.exists():
        if not counterparties_path.exists():
            raise FileNotFoundError(
                f'Cannot build mapping: {counterparties_path} not found.'
            )
        return build_mapping(counterparties_path, mapping_path)
    return load_mapping(mapping_path)

# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text(path: pathlib.Path) -> str:
    """Extract plain text from a PDF, DOCX/DOC, or TXT file."""
    suffix = path.suffix.lower()
    if suffix == '.pdf':
        return _extract_pdf(path)
    if suffix in ('.docx', '.doc'):
        return _extract_docx(path)
    if suffix == '.txt':
        return _extract_txt(path)
    raise ValueError(f'Unsupported file type: {suffix}')


def _extract_pdf(path: pathlib.Path) -> str:
    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return '\n'.join(pages)


def _extract_docx(path: pathlib.Path) -> str:
    doc = Document(str(path))
    return '\n'.join(para.text for para in doc.paragraphs)


def _extract_txt(path: pathlib.Path) -> str:
    for enc in ('utf-8-sig', 'utf-8', 'latin-1'):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f'Could not decode {path} with utf-8-sig, utf-8, or latin-1')

# ---------------------------------------------------------------------------
# Layer 1: Counterparty redaction
# ---------------------------------------------------------------------------

def apply_counterparty_layer(
    text: str,
    mapping: dict[str, str],
) -> tuple[str, list[dict]]:
    """Replace all mapped counterparty names with PARTY-XXXX pseudonyms.

    Applies longest-name-first to prevent partial matches from blocking
    longer names (e.g. "ABC" before "ABC Corporation").
    Offsets in the returned redaction list are pre-replacement positions
    relative to the working text at time of match — approximate when
    multiple distinct names appear in the same document.
    """
    redactions: list[dict] = []
    # Sort by descending name length to match longer names first
    ordered = sorted(mapping.items(), key=lambda kv: -len(kv[0]))
    for name, token in ordered:
        pattern = re.compile(re.escape(name), re.IGNORECASE)
        for match in pattern.finditer(text):
            redactions.append({
                'layer': 'counterparty',
                'token': token,
                'char_start': match.start(),
                'char_end': match.end(),
            })
        text = pattern.sub(token, text)
    return text, redactions

# ---------------------------------------------------------------------------
# Layer 2: Presidio PII
# ---------------------------------------------------------------------------

_analyzer_instance: Optional[AnalyzerEngine] = None
_anonymizer_instance: Optional[AnonymizerEngine] = None


def _presidio_engines() -> tuple[AnalyzerEngine, AnonymizerEngine]:
    global _analyzer_instance, _anonymizer_instance
    if _analyzer_instance is None:
        log.info('Initialising Presidio engines (first call)…')
        _analyzer_instance = AnalyzerEngine()
        _anonymizer_instance = AnonymizerEngine()
    return _analyzer_instance, _anonymizer_instance


def apply_presidio_layer(text: str) -> tuple[str, list[dict]]:
    """Detect and replace PII using Presidio + spaCy en_core_web_lg."""
    analyzer, anonymizer = _presidio_engines()
    results = analyzer.analyze(text=text, entities=PRESIDIO_ENTITIES, language='en')

    redactions: list[dict] = [
        {
            'layer': 'presidio',
            'entity_type': r.entity_type,
            'token': f'[{r.entity_type}]',
            'char_start': r.start,
            'char_end': r.end,
            'score': round(r.score, 3),
        }
        for r in results
    ]

    operators = {
        entity: OperatorConfig('replace', {'new_value': f'[{entity}]'})
        for entity in PRESIDIO_ENTITIES
    }
    anonymized = anonymizer.anonymize(
        text=text,
        analyzer_results=results,
        operators=operators,
    )
    return anonymized.text, redactions

# ---------------------------------------------------------------------------
# Layer 3: Commercial terms regex
# ---------------------------------------------------------------------------

def apply_commercial_layer(text: str) -> tuple[str, list[dict]]:
    """Replace currency amounts, percentages, payment terms, and rates."""
    redactions: list[dict] = []
    for pattern, token in COMMERCIAL_PATTERNS:
        for match in pattern.finditer(text):
            redactions.append({
                'layer': 'commercial_regex',
                'token': token,
                'char_start': match.start(),
                'char_end': match.end(),
            })
        text = pattern.sub(token, text)
    return text, redactions

# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def process_file(
    source: pathlib.Path,
    mapping: dict[str, str],
    output_dir: pathlib.Path,
    write_audit: bool,
) -> dict:
    """Run the full anonymization pipeline on one file.

    Returns a summary dict with status, counts, and runtime.
    Never raises — errors are captured in the summary.
    """
    t0 = time.monotonic()
    log.info('Processing: %s', source.name)

    try:
        raw_text = extract_text(source)
    except Exception as exc:
        log.error('Extraction failed — %s: %s', source.name, exc)
        return {
            'file': str(source),
            'status': 'extraction_error',
            'error': str(exc),
        }

    chars_in = len(raw_text)

    try:
        text, cp_reds   = apply_counterparty_layer(raw_text, mapping)
        text, pii_reds  = apply_presidio_layer(text)
        text, com_reds  = apply_commercial_layer(text)
    except Exception as exc:
        log.error('Redaction failed — %s: %s', source.name, exc)
        return {
            'file': str(source),
            'status': 'redaction_error',
            'error': str(exc),
        }

    # Write anonymised output
    stem = source.stem
    anon_path = output_dir / f'{stem}.anon.txt'
    anon_path.write_text(text, encoding='utf-8')

    if write_audit:
        audit_payload = {
            'source_file': source.name,
            'layers_applied': ['counterparty', 'presidio', 'commercial_regex'],
            'redaction_count': {
                'counterparty': len(cp_reds),
                'presidio':     len(pii_reds),
                'commercial_regex': len(com_reds),
            },
            'redactions':       cp_reds,
            'presidio_entities': pii_reds,
            'commercial_terms': com_reds,
        }
        audit_path = output_dir / f'{stem}.audit.json'
        with open(audit_path, 'w', encoding='utf-8') as fh:
            json.dump(audit_payload, fh, indent=2, ensure_ascii=False)

    elapsed = time.monotonic() - t0
    summary = {
        'file': source.name,
        'status': 'ok',
        'chars_in': chars_in,
        'counterparty_redactions': len(cp_reds),
        'presidio_redactions':     len(pii_reds),
        'commercial_redactions':   len(com_reds),
        'runtime_s': round(elapsed, 2),
    }
    log.info(
        '  %-50s  %6d chars | cp=%-3d pii=%-3d com=%-3d | %.1fs',
        source.name,
        chars_in,
        len(cp_reds),
        len(pii_reds),
        len(com_reds),
        elapsed,
    )
    return summary

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='anonymize.py',
        description=(
            'P3 contract anonymization pipeline. '
            'Applies counterparty, PII, and commercial-term redaction in three ordered layers.'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Examples:\n'
            '  python anonymize.py --input contract.pdf --audit\n'
            '  python anonymize.py --input contracts/ --output-dir anonymization/output --audit\n'
            '  python anonymize.py --input contract.pdf --rebuild-map\n'
        ),
    )
    parser.add_argument(
        '--input', required=True, metavar='PATH',
        help='Source file (.pdf/.docx/.doc/.txt) or directory of source files.',
    )
    parser.add_argument(
        '--output-dir', default='anonymization/output', metavar='DIR',
        help='Directory for .anon.txt (and .audit.json) output. (default: anonymization/output)',
    )
    parser.add_argument(
        '--mapping', default='anonymization/mapping.json', metavar='FILE',
        help='Counterparty mapping JSON. Auto-built from kb/COUNTERPARTIES.md if absent. (default: anonymization/mapping.json)',
    )
    parser.add_argument(
        '--counterparties', default='kb/COUNTERPARTIES.md', metavar='FILE',
        help='Source for mapping construction. (default: kb/COUNTERPARTIES.md)',
    )
    parser.add_argument(
        '--audit', action='store_true',
        help='Write a .audit.json redaction log alongside each .anon.txt output.',
    )
    parser.add_argument(
        '--rebuild-map', action='store_true',
        help='Force rebuild of mapping.json from --counterparties source.',
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    output_dir       = pathlib.Path(args.output_dir)
    mapping_path     = pathlib.Path(args.mapping)
    counterparties_p = pathlib.Path(args.counterparties)

    output_dir.mkdir(parents=True, exist_ok=True)

    mapping = get_mapping(mapping_path, counterparties_p, args.rebuild_map)

    input_path = pathlib.Path(args.input)
    if input_path.is_file():
        files = [input_path]
    elif input_path.is_dir():
        files = sorted(
            p for p in input_path.rglob('*')
            if p.suffix.lower() in SUPPORTED_EXTENSIONS
        )
    else:
        parser.error(f'--input path does not exist: {input_path}')

    log.info('Files to process: %d', len(files))

    summaries: list[dict] = []
    for file_path in files:
        summary = process_file(file_path, mapping, output_dir, args.audit)
        summaries.append(summary)

    ok_count    = sum(1 for s in summaries if s.get('status') == 'ok')
    error_count = len(summaries) - ok_count
    log.info('Finished: %d succeeded, %d failed.', ok_count, error_count)

    if error_count:
        for s in summaries:
            if s.get('status') != 'ok':
                log.error('  %s: %s — %s', s['file'], s['status'], s.get('error', ''))


if __name__ == '__main__':
    main()
