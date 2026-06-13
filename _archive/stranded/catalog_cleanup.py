"""
catalog_cleanup.py
Three targeted cleanup actions on contract-catalog.csv:

1. Remove ISM/Effective Contracting row from catalog (no disk delete)
2. Flag 3 non-contract files for manual review
3. Rename Mosimtec NDA on disk + update catalog FilePath/Filename

Run from the Tools folder:
    python catalog_cleanup.py
"""

import csv
import os
import shutil

TOOLS_DIR    = os.path.dirname(os.path.abspath(__file__))
CATALOG      = os.path.join(TOOLS_DIR, "contract-catalog.csv")
CONTRACTS_ROOT = r"C:\Users\jrudy\OneDrive - Diakonia Group, LLC\Salesforce Integration - Active Contracts"

# Row to remove entirely (match on FilePath)
REMOVE_FILEPATH = "ISM/Effective Contracting - ISM 05.14.26.pdf"

# Rows to flag (match on FilePath)
FLAG_FILEPATHS = {
    "Amazon/A2. 24_7 Support Agreement - Work Order for signature.pdf",
    "ScanSource/EXHIBIT_B_-_DATUM_End_User_License_Agreement_FINAL_CLEAN.8.14.25.docx.pdf",
    "ScanSource/EXHIBIT_C_-_Appendix_D._Customer_Service_Addendum.docx.pdf",
}

# Rename: old FilePath -> new Filename + FilePath
RENAME = {
    "old_filepath": "Mosimtec/Confidential Information Nondisclosure Agreement.pdf",
    "new_filename": "Mosimtec Confidential Information Nondisclosure Agreement.pdf",
    "new_filepath": "Mosimtec/Mosimtec Confidential Information Nondisclosure Agreement.pdf",
}

def main():
    with open(CATALOG, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    print(f"Loaded {len(rows)} rows")

    out_rows = []
    stats = {"removed": 0, "flagged": 0, "renamed": 0}

    for r in rows:
        fp = r["FilePath"].strip()

        # 1. Remove ISM row
        if fp == REMOVE_FILEPATH:
            print(f"  REMOVED: {fp}")
            stats["removed"] += 1
            continue  # skip — don't add to out_rows

        # 2. Flag non-contract files
        if fp in FLAG_FILEPATHS:
            r = dict(r)
            r["Notes"] = (r["Notes"] + " | NON_CONTRACT_FILE_MANUAL_REVIEW").strip(" |")
            print(f"  FLAGGED: {fp}")
            stats["flagged"] += 1

        # 3. Rename Mosimtec NDA
        if fp == RENAME["old_filepath"]:
            r = dict(r)
            r["Filename"] = RENAME["new_filename"]
            r["FilePath"] = RENAME["new_filepath"]
            r["Notes"]    = (r["Notes"] + " | RENAMED_FROM_GENERIC_FILENAME").strip(" |")
            print(f"  CATALOG UPDATED: {RENAME['old_filepath']} -> {RENAME['new_filepath']}")
            stats["renamed"] += 1

        out_rows.append(r)

    # Write updated catalog
    with open(CATALOG, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"\nCatalog updated: {len(out_rows)} rows (was {len(rows)})")
    print(f"  Removed:  {stats['removed']}")
    print(f"  Flagged:  {stats['flagged']}")
    print(f"  Renamed:  {stats['renamed']}")

    # 4. Rename file on disk
    old_disk = os.path.join(CONTRACTS_ROOT, RENAME["old_filepath"].replace("/", os.sep))
    new_disk = os.path.join(CONTRACTS_ROOT, RENAME["new_filepath"].replace("/", os.sep))

    if os.path.exists(old_disk):
        os.rename(old_disk, new_disk)
        print(f"\nDisk rename OK: {RENAME['new_filename']}")
    else:
        print(f"\nWARNING: File not found on disk: {old_disk}")
        print("  Catalog updated but disk rename skipped — verify path manually.")

    print("\nDone.")


if __name__ == "__main__":
    main()
