import csv, shutil
from pathlib import Path

CSV = Path(r"C:\Users\jrudy\OneDrive - Diakonia Group, LLC\Contract Management - SharePoint\Tools\contract-catalog.csv")
BAK = CSV.with_suffix('.csv.bak_nfi')
shutil.copy2(CSV, BAK)

rows = []
removed = 0
cleared = 0

with open(CSV, encoding='utf-8-sig', newline='') as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        loc = row.get('ContractLocation','').strip()
        vf = row.get('VendorFolder','').strip()
        fn = row.get('Filename','').strip()

        # Remove misrouted Ventura Foods file from NFI folder
        if loc == '04 Expired Contracts' and vf == 'NFI' and 'VENTURA' in fn.upper():
            removed += 1
            continue

        # Clear ManualReview on legitimate NFI row
        if vf == 'NFI' and row.get('ManualReview','').strip() == 'MANUAL_REVIEW':
            row['ManualReview'] = ''
            row['ManualReviewNote'] = ''
            cleared += 1

        rows.append(row)

with open(CSV, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)

print(f"Rows removed: {removed}")
print(f"ManualReview cleared: {cleared}")
print(f"Total rows written: {len(rows)}")
