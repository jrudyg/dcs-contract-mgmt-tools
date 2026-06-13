"""
fix_blank_counterparties.py
Fixes 172 blank CounterpartyName + DocType rows in contract-catalog.csv.

Buckets:
  1. Backfill from populated counterpart in another folder (same filename)  -> 117 rows
  2. Parse from filename                                                     -> 47 rows
  3. Flag true internal duplicates (same filename + folder seen twice)       -> 8 rows

Non-destructive: reads contract-catalog.csv, writes contract-catalog-fixed.csv.
Never touches the original until you manually rename/replace.

Run from the Tools folder:
    python fix_blank_counterparties.py
"""

import csv
import re
import os
import shutil
from datetime import datetime

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV  = os.path.join(TOOLS_DIR, "contract-catalog.csv")
OUTPUT_CSV = os.path.join(TOOLS_DIR, "contract-catalog-fixed.csv")

# Folder priority for backfill source (lower = preferred)
PRIORITY = {
    "04 Expired Contracts":   0,
    "03 Archived Contracts":  1,
    "01 Active Contracts":    2,
    "02 Unsigned Contracts":  3,
}


def parse_filename(fn):
    """Extract counterparty name and doc type from filename alone."""
    stem = re.sub(r"\.(pdf|docx?|msg)$", "", fn, flags=re.IGNORECASE)

    # Strip signing/version noise
    for pat in [
        r"\s*[-_]\s*signed.*$",
        r"\s+signed.*$",
        r"\bSigned\b.*$",
        r"\bFINAL\b.*$",
        r"\bREDLINED\b.*$",
        r"\bexecut\w*\b.*$",
        r"\bv\d+\b.*$",
        r"\b20\d{2}[-._]\d{2}[-._]\d{2}\b.*$",
        r"\b\d{2}[._]\d{2}[._]\d{2,4}\b.*$",
        r"\b\d{8,}\b.*$",
    ]:
        stem = re.sub(pat, "", stem, flags=re.IGNORECASE)

    # Strip DCS / Designed Conveyor Systems
    stem = re.sub(r"\bDCS\b\s*[&_\-]?\s*", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"Designed Conveyor Systems\s*(LLC)?\s*[&_\-]?\s*", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"Vendor\s+Mutual\s+", "Mutual ", stem, flags=re.IGNORECASE)
    stem = stem.strip(" -\u2013_")

    # Doc type detection
    doc_type = ""
    if re.search(r"\bMNDA\b|Mutual\s+NDA|Mutual\s+Confidentiality|Mutual\s+Non.?Disclosure", stem, re.IGNORECASE):
        doc_type = "MNDA"
    elif re.search(r"\bNDA\b|Non.?Disclosure|Confidentiality", stem, re.IGNORECASE):
        doc_type = "NDA"
    elif re.search(r"\bMSA\b|Master\s+Services\s+Agreement", stem, re.IGNORECASE):
        doc_type = "MSA"
    elif re.search(r"\bSOW\b|Statement\s+of\s+Work", stem, re.IGNORECASE):
        doc_type = "SOW"
    elif re.search(r"\bAmendment\b", stem, re.IGNORECASE):
        doc_type = "Amendment"
    elif re.search(r"\bLicense\b|EULA", stem, re.IGNORECASE):
        doc_type = "License"
    elif re.search(r"\bSubcontract\b", stem, re.IGNORECASE):
        doc_type = "Subcontract"
    elif re.search(r"\bIPA\b|Integrator\s+Agreement", stem, re.IGNORECASE):
        doc_type = "IPA"

    # Strip doc-type prefix words to isolate counterparty name
    cp = re.sub(r"^(Mutual\s+)?(Confidentiality\s+(and\s+)?)?Non.?Disclosure\s+Agreement\s*[-\u2013]?\s*", "", stem, flags=re.IGNORECASE)
    cp = re.sub(r"^(Mutual\s+)?MNDA\s*[-\u2013_]?\s*", "", cp, flags=re.IGNORECASE)
    cp = re.sub(r"^(Mutual\s+)?NDA\s*[-\u2013_]?\s*", "", cp, flags=re.IGNORECASE)
    cp = re.sub(r"^MSA\s*[-\u2013_]?\s*", "", cp, flags=re.IGNORECASE)
    cp = re.sub(r"^Confidential\s+Information\s+Nondisclosure\s+Agreement\s*[-\u2013]?\s*", "", cp, flags=re.IGNORECASE)
    # Strip trailing date/version noise
    cp = re.sub(r"\s*[-_]\s*(Final|FINAL|v\d+|\d{2}[._]\d{2}|\d{4,}).*$", "", cp, flags=re.IGNORECASE)
    cp = re.sub(r"\s+(and\s+)?NDA$", "", cp, flags=re.IGNORECASE)
    cp = re.sub(r"\s+MNDA$", "", cp, flags=re.IGNORECASE)
    cp = re.sub(r"\s+", " ", cp).strip(" -\u2013_")

    return cp, doc_type


def main():
    print(f"Reading: {INPUT_CSV}")
    with open(INPUT_CSV, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    print(f"  {len(rows)} rows loaded")

    # Build lookup: filename -> best populated row
    lookup = {}
    for r in rows:
        if r["CounterpartyName"].strip() and r["DocType"].strip():
            fn = r["Filename"].strip()
            existing = lookup.get(fn)
            p = PRIORITY.get(r["ContractLocation"], 9)
            if existing is None or p < PRIORITY.get(existing["ContractLocation"], 9):
                lookup[fn] = r

    # Apply fixes
    seen_in_folder = {}
    stats = {"backfilled": 0, "parsed": 0, "dup_flagged": 0, "still_blank": 0}
    out_rows = []

    for r in rows:
        fn  = r["Filename"].strip()
        loc = r["ContractLocation"].strip()
        blank = not r["CounterpartyName"].strip() and not r["DocType"].strip()

        if blank:
            r = dict(r)
            key = (loc, fn)

            if key in seen_in_folder:
                # True internal duplicate
                note = (r["Notes"] + " | DUPLICATE_ROW").strip(" |")
                r["Notes"] = note
                stats["dup_flagged"] += 1

            elif fn in lookup:
                # Backfill from counterpart in another folder
                src = lookup[fn]
                r["CounterpartyName"] = src["CounterpartyName"]
                r["DocType"]          = src["DocType"]
                tag = "BACKFILLED_FROM_" + src["ContractLocation"].replace(" ", "_").upper()
                r["Notes"] = (r["Notes"] + f" | {tag}").strip(" |")
                stats["backfilled"] += 1

            else:
                # Parse from filename
                cp, dt = parse_filename(fn)
                if cp or dt:
                    r["CounterpartyName"] = cp
                    r["DocType"]          = dt
                    r["Notes"] = (r["Notes"] + " | PARSED_FROM_FILENAME").strip(" |")
                    stats["parsed"] += 1
                else:
                    r["Notes"] = (r["Notes"] + " | NEEDS_MANUAL_REVIEW").strip(" |")
                    stats["still_blank"] += 1

            seen_in_folder[key] = True

        out_rows.append(r)

    # Write output
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"\nDone. Written: {OUTPUT_CSV}")
    print(f"  Backfilled from counterpart:  {stats['backfilled']}")
    print(f"  Parsed from filename:         {stats['parsed']}")
    print(f"  Internal duplicates flagged:  {stats['dup_flagged']}")
    print(f"  Still blank (needs review):   {stats['still_blank']}")
    print(f"  Total rows written:           {len(out_rows)}")

    # Spot-check: show all PARSED_FROM_FILENAME rows
    print("\n--- PARSED_FROM_FILENAME (review counterparty quality) ---")
    for r in out_rows:
        if "PARSED_FROM_FILENAME" in r.get("Notes", ""):
            print(f"  {r['Filename'][:55]:55} | {r['CounterpartyName'][:30]:30} | {r['DocType']}")

    print("\n--- DUPLICATE_ROW flags ---")
    for r in out_rows:
        if "DUPLICATE_ROW" in r.get("Notes", ""):
            print(f"  [{r['ContractLocation']}] {r['Filename'][:60]}")


if __name__ == "__main__":
    main()
