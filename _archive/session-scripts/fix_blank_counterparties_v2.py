"""
fix_blank_counterparties_v2.py
Applies manual-corrected counterparty fixes to contract-catalog.csv.
Writes contract-catalog-fixed.csv — does NOT touch original until you rename.

Run from the Tools folder:
    python fix_blank_counterparties_v2.py
    
Then review, and if satisfied:
    copy contract-catalog-fixed.csv contract-catalog.csv
"""

import csv
import re
import os

TOOLS_DIR  = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV  = os.path.join(TOOLS_DIR, "contract-catalog.csv")
OUTPUT_CSV = os.path.join(TOOLS_DIR, "contract-catalog-fixed.csv")

PRIORITY = {
    "04 Expired Contracts":  0,
    "03 Archived Contracts": 1,
    "01 Active Contracts":   2,
    "02 Unsigned Contracts": 3,
}

# Manual corrections: filename -> (CounterpartyName, DocType)
MANUAL_CP = {
    "DCS Action Electric MNDA 052026.pdf":                                          ("Action Electric", "MNDA"),
    "AES Mutual NDA - DCS 02.03.25.pdf":                                            ("AES", "MNDA"),
    "DCS & Agile Non-Disclosure Agreement.pdf":                                     ("Agile", "NDA"),
    "A2. 24_7 Support Agreement - Work Order for signature.pdf":                    ("", ""),
    "Animo Dev and DCS Vendor Mutual NDA 11.09.25 - signed.pdf":                    ("Animo Dev", "MNDA"),
    "DCS_BEUMER_MNDA_09152021_Signed.pdf":                                          ("Beumer", "MNDA"),
    "MNDA DCS_11-16-22 - signed.pdf":                                               ("Conveyor Concepts of Michigan", "MNDA"),
    "DCS-TA-5611-GSESC-Amendment 1 - FE.pdf":                                       ("", "Amendment"),
    "Mutual NDA - DFI and DCS - Final 02.17.25 - signed.pdf":                      ("DFI", "MNDA"),
    "DSC Mutual Nondisclosure Agreement - DJH Signed - signed.pdf":                 ("DJH", "MNDA"),
    "GDIT_GSESC_IDIQ_No_00936_Revision_No_1_.pdf":                                  ("GDIT", ""),
    "G0164333  Designed Conveyor Systems, LLC NDA-Standard Procurement Bilateral.docx.pdf": ("Honeywell Intelligrated", "NDA"),
    "DCS - Intellistore Vendor Mutual NDA Final 02.17.25 - signed.pdf":             ("Intellistore", "MNDA"),
    "Effective Contracting - ISM 05.14.26.pdf":                                     ("", ""),
    "Kaeser - Terms and Conditions - Clean - signed.pdf":                           ("Kaeser", ""),
    "LEGO_Confidentiality  Non-Disclosure Agreement (Mutual) 2025.pdf":             ("LEGO", "MNDA"),
    "M2Studio-DCS Vendor MNDA _signed.pdf":                                         ("M2Studio", "MNDA"),
    "McKesson_DCS_MNDA_REDLINED 05.26.26.docx.pdf":                                 ("McKesson", "MNDA"),
    "FORM Mutual NDA.pdf":                                                           ("Melaleuca", "MNDA"),
    "NDA Mutual (Meyn America) GC.pdf":                                             ("Meyn America", "NDA"),
    "Confidential Information Nondisclosure Agreement.pdf":                         ("Mosimtec", "NDA"),
    "NDA_Muratec_DCS_02132026 - signed.pdf":                                        ("Muratec", "NDA"),
    "New Era - DCS Mutual Non-Disclosure Agreement 05.2026.pdf":                    ("New Era", "MNDA"),
    "NDA (Mutual) - Short Form - 2021.pdf":                                         ("Orvis", "NDA"),
    "Packsize_Designed Conveyor Systems MNDA - FINAL 12.17.24 - signed.pdf":        ("Packsize", "MNDA"),
    "PAR Industries_DCS MNDA Signed.pdf":                                           ("PAR Industries", "MNDA"),
    "RTR NDA (TWO-WAY)_DocuSign Powerform.doc.pdf":                                 ("Rent the Runway", "NDA"),
    "RJW_DCS_NDA_Final - signed.pdf":                                               ("RJW Group", "NDA"),
    "DCS Vendor Mutual NDA to Safety Plus Inc -signed 12.12.2024.pdf":              ("Safety Plus Inc", "MNDA"),
    "EXHIBIT_B_-_DATUM_End_User_License_Agreement_FINAL_CLEAN.8.14.25.docx.pdf":   ("", ""),
    "EXHIBIT_C_-_Appendix_D._Customer_Service_Addendum.docx.pdf":                  ("", ""),
    "DCS Schmalz Vendor Mutual NDA 10.06.25.pdf":                                   ("Schmalz", "MNDA"),
    "Form NDA - v4 08_05_16.pdf":                                                   ("SI Systems", "NDA"),
    "SpanTech DCS Vendor Mutual NDA 03.25.26 - signed.pdf":                        ("SpanTech", "MNDA"),
    "Spring Automation_Standard Intelligrated Mutual NDA (US) 2018.pdf":            ("Spring Automation / Intelligrated", "MNDA"),
    "MNDA DCS to Steele Solutions for DCS Signature - signed 2.6.2025.pdf":        ("Steele Solutions", "MNDA"),
    "2024 MSA Tevora-DCS 2.12.2024_FINAL.pdf":                                      ("Tevora", "MSA"),
    "Confidentiality MNDA Mutual Agreement with LVMH and Tiffany Supplier Code of Conduct updated 1.11.23.pdf": ("Tiffany and Company", "MNDA"),
    "Urbx_NDA_DCS.pdf":                                                             ("Urbx", "NDA"),
}


def parse_filename(fn):
    stem = re.sub(r"\.(pdf|docx?|msg)$", "", fn, flags=re.IGNORECASE)
    for pat in [
        r"\s*[-_]\s*signed.*$", r"\s+signed.*$", r"\bSigned\b.*$",
        r"\bFINAL\b.*$", r"\bREDLINED\b.*$", r"\bexecut\w*\b.*$",
        r"\bv\d+\b.*$", r"\b20\d{2}[-._]\d{2}[-._]\d{2}\b.*$",
        r"\b\d{2}[._]\d{2}[._]\d{2,4}\b.*$", r"\b\d{8,}\b.*$",
    ]:
        stem = re.sub(pat, "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\bDCS\b\s*[&_\-]?\s*", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"Designed Conveyor Systems\s*(LLC)?\s*[&_\-]?\s*", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"Vendor\s+Mutual\s+", "Mutual ", stem, flags=re.IGNORECASE)
    stem = stem.strip(" -\u2013_")

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

    cp = re.sub(r"^(Mutual\s+)?(Confidentiality\s+(and\s+)?)?Non.?Disclosure\s+Agreement\s*[-\u2013]?\s*", "", stem, flags=re.IGNORECASE)
    cp = re.sub(r"^(Mutual\s+)?MNDA\s*[-\u2013_]?\s*", "", cp, flags=re.IGNORECASE)
    cp = re.sub(r"^(Mutual\s+)?NDA\s*[-\u2013_]?\s*", "", cp, flags=re.IGNORECASE)
    cp = re.sub(r"^MSA\s*[-\u2013_]?\s*", "", cp, flags=re.IGNORECASE)
    cp = re.sub(r"^Confidential\s+Information\s+Nondisclosure\s+Agreement\s*[-\u2013]?\s*", "", cp, flags=re.IGNORECASE)
    cp = re.sub(r"\s*[-_]\s*(Final|FINAL|v\d+|\d{2}[._]\d{2}|\d{4,}).*$", "", cp, flags=re.IGNORECASE)
    cp = re.sub(r"\s+(and\s+)?NDA$", "", cp, flags=re.IGNORECASE)
    cp = re.sub(r"\s+MNDA$", "", cp, flags=re.IGNORECASE)
    cp = re.sub(r"\s+", " ", cp).strip(" -\u2013_")
    return cp, doc_type


def main():
    with open(INPUT_CSV, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    print(f"Loaded {len(rows)} rows from {INPUT_CSV}")

    # Build backfill lookup
    lookup = {}
    for r in rows:
        if r["CounterpartyName"].strip() and r["DocType"].strip():
            fn = r["Filename"].strip()
            existing = lookup.get(fn)
            p = PRIORITY.get(r["ContractLocation"], 9)
            if existing is None or p < PRIORITY.get(existing["ContractLocation"], 9):
                lookup[fn] = r

    seen_in_folder = {}
    stats = {"backfilled": 0, "manual": 0, "parsed": 0, "dup_flagged": 0, "still_blank": 0}
    out_rows = []

    for r in rows:
        fn    = r["Filename"].strip()
        loc   = r["ContractLocation"].strip()
        blank = not r["CounterpartyName"].strip() and not r["DocType"].strip()

        if blank:
            r   = dict(r)
            key = (loc, fn)

            if key in seen_in_folder:
                r["Notes"] = (r["Notes"] + " | DUPLICATE_ROW").strip(" |")
                stats["dup_flagged"] += 1

            elif fn in lookup:
                src = lookup[fn]
                r["CounterpartyName"] = src["CounterpartyName"]
                r["DocType"]          = src["DocType"]
                tag = "BACKFILLED_FROM_" + src["ContractLocation"].replace(" ", "_").upper()
                r["Notes"] = (r["Notes"] + f" | {tag}").strip(" |")
                stats["backfilled"] += 1

            elif fn in MANUAL_CP:
                cp, dt = MANUAL_CP[fn]
                r["CounterpartyName"] = cp
                r["DocType"]          = dt
                r["Notes"] = (r["Notes"] + " | PARSED_FROM_FILENAME").strip(" |")
                stats["manual"] += 1

            else:
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

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"\nWritten: {OUTPUT_CSV}")
    print(f"  Backfilled from other folder: {stats['backfilled']}")
    print(f"  Manual corrections applied:   {stats['manual']}")
    print(f"  Auto-parsed from filename:    {stats['parsed']}")
    print(f"  Duplicate rows flagged:       {stats['dup_flagged']}")
    print(f"  Still blank:                  {stats['still_blank']}")
    print(f"  Total rows:                   {len(out_rows)}")

    needs = [r for r in out_rows if "NEEDS_MANUAL_REVIEW" in r.get("Notes", "")]
    if needs:
        print("\nSTILL BLANK — manual review required:")
        for r in needs:
            print(f"  {r['Filename']}")
    else:
        print("\nAll rows resolved. Ready to promote.")


if __name__ == "__main__":
    main()
