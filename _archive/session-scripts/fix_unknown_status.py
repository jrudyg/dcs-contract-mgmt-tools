import csv, shutil
from pathlib import Path
from datetime import date

CSV = Path(r"C:\Users\jrudy\OneDrive - Diakonia Group, LLC\Contract Management - SharePoint\Tools\contract-catalog.csv")
BAK = CSV.with_suffix('.csv.bak2')

shutil.copy2(CSV, BAK)
print(f"Backup: {BAK}")

rows = []
evergreen_fixed = 0
manual_flagged = 0

with open(CSV, encoding='utf-8-sig', newline='') as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        if row.get('Status','').strip().lower() == 'unknown':
            dt = row.get('DocType','').strip()
            ss = row.get('SigningStatus','').strip()
            loc = row.get('ContractLocation','').strip()
            if dt in ('MNDA','NDA') and ss == 'Signed' and loc == '01 Active Contracts':
                row['Status'] = 'active'
                evergreen_fixed += 1
            else:
                if row.get('ManualReview','').strip().upper() != 'Y':
                    row['ManualReview'] = 'Y'
                    row['ManualReviewNote'] = (row.get('ManualReviewNote','').strip() + ' | Status=unknown-needs-review').strip(' |')
                    manual_flagged += 1
        rows.append(row)

with open(CSV, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)

print(f"Evergreen fixed (Status->active): {evergreen_fixed}")
print(f"Manual review flagged: {manual_flagged}")
print(f"Total rows written: {len(rows)}")

# Verify
remaining_unknown = sum(1 for r in rows if r.get('Status','').strip().lower() == 'unknown' and r.get('ManualReview','').strip().upper() != 'Y')
print(f"Remaining unflagged unknowns: {remaining_unknown} (should be 0)")
