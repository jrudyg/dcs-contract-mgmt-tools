import csv, shutil
from pathlib import Path

CSV = Path(r"C:\Users\jrudy\OneDrive - Diakonia Group, LLC\Contract Management - SharePoint\Tools\contract-catalog.csv")
BAK = CSV.with_suffix('.csv.bak_batch2')
shutil.copy2(CSV, BAK)

rows = []
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
        status = row.get('Status','').strip().lower()

        # Ventura Foods -- clear flags on all rows
        if vf == 'Ventura Foods':
            clear_mr(row)
            fixed['Ventura Foods'] = fixed.get('Ventura Foods',0) + 1

        # Dematic -- clear flags; fix unknown-status Amendment row
        elif vf == 'Dematic':
            if status == 'unknown':
                row['Status'] = 'active'
            clear_mr(row)
            fixed['Dematic'] = fixed.get('Dematic',0) + 1

        # ScanSource -- fix exhibit statuses; proposals/summaries -> archived
        elif vf == 'ScanSource':
            if fn.startswith('EXHIBIT_') and status == 'unknown':
                row['Status'] = 'active'
            elif fn in (
                'ScanSource_-_DATUM_Prop_Final_9.19.24_(002).pdf',
                'Summary.pdf'
            ) and status == 'unknown':
                row['Status'] = 'archived'
            elif fn.startswith('EXHIBIT_A_-_DATUM_SOW') and status == 'unknown':
                row['Status'] = 'active'
            clear_mr(row)
            fixed['ScanSource'] = fixed.get('ScanSource',0) + 1

        # Amazon -- clear flag on expired MSA; Work Order -> active
        elif vf == 'Amazon':
            if status == 'unknown':
                row['Status'] = 'active'
            clear_mr(row)
            fixed['Amazon'] = fixed.get('Amazon',0) + 1

        rows.append(row)

with open(CSV, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)

print(f"Rows fixed by vendor: {fixed}")
print(f"Total rows written: {len(rows)}")
