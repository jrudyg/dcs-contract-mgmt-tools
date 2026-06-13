import csv, shutil
from pathlib import Path

CSV = Path(r"C:\Users\jrudy\OneDrive - Diakonia Group, LLC\Contract Management - SharePoint\Tools\contract-catalog.csv")
BAK = CSV.with_suffix('.csv.bak_batch1')
shutil.copy2(CSV, BAK)

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
        loc = row.get('ContractLocation','').strip()
        fn = row.get('Filename','').strip()
        cp = row.get('CounterpartyName','').strip()

        # EDMCI subcontract -- fix boilerplate CP name and status
        if vf == 'EDMCI' and cp == 'the undersigned Subcontractor':
            row['CounterpartyName'] = 'EDMCI'
            row['Status'] = 'active'
            clear_mr(row)
            fixed['EDMCI'] = fixed.get('EDMCI',0) + 1

        # Fletchline subcontract -- fix boilerplate CP name and status
        elif vf == 'Fletchline' and cp == 'the undersigned Subcontractor':
            row['CounterpartyName'] = 'Fletchline Inc'
            row['Status'] = 'active'
            clear_mr(row)
            fixed['Fletchline'] = fixed.get('Fletchline',0) + 1

        # Trinity Solutions -- remove misrouted blank-CP active row
        elif vf == 'Trinity Solutions' and loc == '01 Active Contracts' and cp == '':
            removed += 1
            continue

        # Trinity Solutions -- clear flag on expired row
        elif vf == 'Trinity Solutions':
            clear_mr(row)
            fixed['Trinity Solutions'] = fixed.get('Trinity Solutions',0) + 1

        # Trinity Controls -- clear flags
        elif vf == 'Trinity Controls':
            clear_mr(row)
            fixed['Trinity Controls'] = fixed.get('Trinity Controls',0) + 1

        # Designed Integrators DMI -- clear flags
        elif vf == 'Designed Integrators(DMI)':
            clear_mr(row)
            fixed['DMI'] = fixed.get('DMI',0) + 1

        # NPI -- clear flags
        elif vf == 'NPI':
            clear_mr(row)
            fixed['NPI'] = fixed.get('NPI',0) + 1

        # EMIT -- clear flags
        elif vf == 'EMIT':
            clear_mr(row)
            fixed['EMIT'] = fixed.get('EMIT',0) + 1

        # CEI -- clear flag, blank non-date expiration
        elif vf == 'CEI':
            if row.get('ExpirationDate','').strip().lower() == 'on notice':
                row['ExpirationDate'] = ''
                row['DaysUntilExpiration'] = ''
            clear_mr(row)
            fixed['CEI'] = fixed.get('CEI',0) + 1

        # Lamb Weston -- clear flag (correctly expired)
        elif vf == 'Lamb Weston':
            clear_mr(row)
            fixed['Lamb Weston'] = fixed.get('Lamb Weston',0) + 1

        # Tevora -- clear flags on all rows
        elif vf == 'Tevora':
            clear_mr(row)
            fixed['Tevora'] = fixed.get('Tevora',0) + 1

        rows.append(row)

with open(CSV, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)

print(f"Rows removed: {removed}")
print(f"Rows fixed by vendor: {fixed}")
print(f"Total rows written: {len(rows)}")
