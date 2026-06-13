import csv, shutil
from pathlib import Path

CSV = Path(r"C:\Users\jrudy\OneDrive - Diakonia Group, LLC\Contract Management - SharePoint\Tools\contract-catalog.csv")
BAK = CSV.with_suffix('.csv.bak_batch3')
shutil.copy2(CSV, BAK)

# Vendors to set active and clear flag
SET_ACTIVE = {
    'Action Electric', 'AES', 'Agile', 'Alba Manufacturing',
    'Army & Air Force Exchange Service', 'A-LIGN', 'BATO', 'Beumer',
    'Conveyor Concepts of Michigan', 'DJH', 'Kaeser', 'Melaleuca',
    'Meyn', 'New Era', 'Orvis', 'PAR Industries LLC', 'Rehan Qazi',
    'Rent the Runway', 'Ross Stores, Inc', 'Schmalz', 'Steele Solutions',
    'Tiffany and Company', 'Tompkins Robotics', 'Urbx', 'USPS',
    'Vertex Form 3D LLC', 'Diversified Automation',
}

rows = []
removed = 0
fixed = {}

def clear_mr(row):
    row['ManualReview'] = ''
    row['ManualReviewNote'] = ''

with open(CSV, encoding='utf-8-sig', newline='') as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        vf = row.get('VendorFolder','').strip()
        fn = row.get('Filename','').strip()
        mr = row.get('ManualReview','').strip().upper()

        if mr != 'Y':
            rows.append(row)
            continue

        # Remove duplicate rows
        if vf == 'Bridgestone':
            removed += 1
            fixed['Bridgestone_removed'] = fixed.get('Bridgestone_removed',0) + 1
            continue

        if vf == 'Schmalz, Inc':
            removed += 1
            fixed['SchmalzInc_removed'] = fixed.get('SchmalzInc_removed',0) + 1
            continue

        # DocuSign certificates -- archive
        if vf in ('Connors Group', 'McKesson') and fn == 'Summary.pdf':
            row['Status'] = 'archived'
            clear_mr(row)
            fixed['summary_archived'] = fixed.get('summary_archived',0) + 1

        # McKesson redline draft -- unsigned
        elif vf == 'McKesson' and 'REDLINED' in fn.upper():
            row['Status'] = 'unsigned'
            clear_mr(row)
            fixed['McKesson_redline'] = fixed.get('McKesson_redline',0) + 1

        # Root-level amendment -- active + note
        elif vf == '(root)':
            row['Status'] = 'active'
            row['Notes'] = 'Needs vendor folder -- GSESC Amendment filed in root 2026-05-12'
            clear_mr(row)
            fixed['root_amendment'] = fixed.get('root_amendment',0) + 1

        # Standard set-active vendors
        elif vf in SET_ACTIVE:
            row['Status'] = 'active'
            clear_mr(row)
            fixed[vf] = fixed.get(vf,0) + 1

        else:
            # Catch-all -- clear flag, leave status
            clear_mr(row)
            fixed['other_cleared'] = fixed.get('other_cleared',0) + 1

        rows.append(row)

with open(CSV, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)

print(f"Rows removed: {removed}")
print(f"Actions by vendor:")
for k,v in sorted(fixed.items()):
    print(f"  {k}: {v}")
print(f"Total rows written: {len(rows)}")

# Verify
with open(CSV, encoding='utf-8-sig', newline='') as f:
    verify = list(csv.DictReader(f))
remaining = [r for r in verify if r.get('ManualReview','').strip().upper() == 'Y']
print(f"Remaining ManualReview=Y: {len(remaining)} (should be 0)")
