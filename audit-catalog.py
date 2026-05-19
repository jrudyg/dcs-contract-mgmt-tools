"""
audit-catalog.py  --  Contract Catalog Auditor
Walks the three contract root folders and reconciles against contract-catalog.csv.

Detects and auto-corrects:
  ContractLocation mismatches  -- file is in a different folder than CSV says  -> updates CSV
  Orphan files                 -- on disk but not in CSV                        -> adds skeleton row
  Missing files                -- in CSV but not found on disk                  -> reported only

Usage:
  python Tools\\audit-catalog.py
  python Tools\\audit-catalog.py --dry-run
  python Tools\\audit-catalog.py --csv "path\\to\\contract-catalog.csv"
"""

import argparse
import csv
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path, PurePosixPath

import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────

SCRIPT_DIR  = Path(__file__).resolve().parent
SHAREPOINT  = SCRIPT_DIR.parent
DEFAULT_CSV = SCRIPT_DIR / "contract-catalog.csv"

CONTRACT_ROOTS = [
    "01 Active Contracts",
    "02 Unsigned Contracts",
    "03 Archived Contracts",
]

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".msg"}

SKIP_NAMES = {"__pycache__", ".git", ".DS_Store", "Thumbs.db"}

# Vendor folder prefixes that are template libraries, not actual contracts
TEMPLATE_FOLDER_PREFIXES = ("00 ",)

# ── CSV helpers ────────────────────────────────────────────────────────────────

def load_csv(csv_path: Path) -> pd.DataFrame:
    return pd.read_csv(str(csv_path), dtype=str, keep_default_na=False)


def write_csv(df: pd.DataFrame, csv_path: Path):
    tmp = csv_path.with_suffix(".csv.tmp")
    bak = csv_path.with_suffix(".csv.bak")
    df.to_csv(str(tmp), index=False, quoting=csv.QUOTE_ALL)
    shutil.copy2(str(csv_path), str(bak))
    tmp.replace(csv_path)


def _norm_fp(p: str) -> str:
    return p.replace("\\", "/").strip()


# ── Disk walker ────────────────────────────────────────────────────────────────

def walk_contracts(root: Path):
    """Yield (contract_location, fp_key, vendor_folder, abs_path) for every supported file."""
    for loc in CONTRACT_ROOTS:
        loc_dir = root / loc
        if not loc_dir.exists():
            print(f"  [WARN] ContractLocation folder not found on disk: {loc}")
            continue
        for abs_path in sorted(loc_dir.rglob("*")):
            if not abs_path.is_file():
                continue
            # Skip hidden, system, and temp files
            if any(part.startswith(".") or part in SKIP_NAMES
                   for part in abs_path.parts):
                continue
            # Skip Word/Office lock files (~$ prefix)
            if abs_path.name.startswith("~$"):
                continue
            # Skip template library folders (e.g. "00 Vendor Templates")
            rel_parts = abs_path.relative_to(loc_dir).parts
            if rel_parts and any(rel_parts[0].startswith(p) for p in TEMPLATE_FOLDER_PREFIXES):
                continue
            if abs_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            rel = abs_path.relative_to(loc_dir)
            fp_key = _norm_fp(str(rel))
            vendor_folder = rel.parts[0] if len(rel.parts) > 1 else ""
            yield loc, fp_key, vendor_folder, abs_path


# ── Orphan row builder ────────────────────────────────────────────────────────

def make_orphan_row(columns: list, loc: str, fp_key: str, vendor: str, abs_path: Path) -> dict:
    try:
        created = datetime.fromtimestamp(abs_path.stat().st_ctime).strftime("%Y-%m-%d")
    except Exception:
        created = ""
    row = {col: "" for col in columns}
    row["ContractLocation"] = loc
    row["VendorFolder"]     = vendor
    row["Filename"]         = abs_path.name
    row["FilePath"]         = fp_key
    row["Extension"]        = abs_path.suffix.lower().lstrip(".")
    row["FileCreatedDate"]  = created
    return row


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Audit contract-catalog.csv against files on disk and auto-correct mismatches",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Report without writing CSV")
    parser.add_argument("--csv", metavar="PATH", default=str(DEFAULT_CSV),
                        help="Path to contract-catalog.csv")
    args = parser.parse_args()

    csv_path = Path(args.csv).resolve()
    if not csv_path.exists():
        sys.exit(f"CSV not found: {csv_path}")

    print("audit-catalog.py  --  Contract Catalog Auditor")
    print("=" * 54)
    print(f"CSV:  {csv_path}")
    print(f"Root: {SHAREPOINT}")
    if args.dry_run:
        print("Mode: DRY RUN (no changes written)")
    print()

    df = load_csv(csv_path)
    columns = list(df.columns)
    print(f"Loaded {len(df)} CSV rows.\n")

    # Build lookup: normalized FilePath -> list of row indices
    fp_to_indices: dict[str, list[int]] = {}
    for idx in df.index:
        key = _norm_fp(df.at[idx, "FilePath"])
        if key:
            fp_to_indices.setdefault(key, []).append(idx)

    # Identify FilePaths whose CSV rows span multiple ContractLocations — these are
    # duplicate-row conflicts and must not be auto-corrected.
    conflict_fps: set[str] = set()
    for fp_key, indices in fp_to_indices.items():
        locs = {df.at[idx, "ContractLocation"] for idx in indices}
        if len(locs) > 1:
            conflict_fps.add(fp_key)
            rows_str = ", ".join(f"row {i} ({df.at[i,'ContractLocation']})" for i in indices)
            print(f"  [CONFLICT] Same FilePath in multiple CSV rows: {fp_key}")
            print(f"             Rows: {rows_str}")
            print(f"             -> Review and remove the duplicate CSV row(s) manually.")
    if conflict_fps:
        print()

    # Walk disk ────────────────────────────────────────────────────────────────
    print("Walking contract folders on disk...")

    confirmed_indices: set[int] = set()
    updated_indices:   set[int] = set()  # rows already corrected this run
    n_ok = 0
    n_mismatch = 0
    n_orphan   = 0
    n_duplicate = 0
    orphan_rows: list[dict] = []

    for loc, fp_key, vendor, abs_path in walk_contracts(SHAREPOINT):
        indices = fp_to_indices.get(fp_key)

        if indices is None:
            # File exists on disk but has no CSV row
            tag = "[DRY RUN] " if args.dry_run else ""
            print(f"  {tag}[ORPHAN]   {loc}/{fp_key}")
            n_orphan += 1
            if not args.dry_run:
                orphan_rows.append(make_orphan_row(columns, loc, fp_key, vendor, abs_path))
        else:
            for idx in indices:
                csv_loc = df.at[idx, "ContractLocation"]
                confirmed_indices.add(idx)
                if fp_key in conflict_fps:
                    # Duplicate-row conflict — skip auto-correction, already reported above
                    n_ok += 1
                elif csv_loc == loc:
                    n_ok += 1
                elif idx in updated_indices:
                    # Already corrected; file physically exists in multiple folders
                    print(
                        f"  [DUPLICATE] Row {idx}: file found in both "
                        f'"{df.at[idx, "ContractLocation"]}" and "{loc}"  |  {fp_key}'
                    )
                    n_duplicate += 1
                else:
                    tag = "[DRY RUN] " if args.dry_run else ""
                    print(
                        f"  {tag}[MISMATCH] Row {idx}: "
                        f'ContractLocation "{csv_loc}" -> "{loc}"  |  {fp_key}'
                    )
                    n_mismatch += 1
                    if not args.dry_run:
                        df.at[idx, "ContractLocation"] = loc
                        updated_indices.add(idx)

    # Check for CSV rows whose file was never found on disk ───────────────────
    print("\nChecking for CSV rows with missing files...")
    n_missing = 0
    missing_rows: list[tuple[int, str, str]] = []

    for idx in df.index:
        if idx in confirmed_indices:
            continue
        loc = df.at[idx, "ContractLocation"]
        fp  = _norm_fp(df.at[idx, "FilePath"])
        if not fp:
            continue
        full = SHAREPOINT / loc / Path(PurePosixPath(fp))
        if not full.exists():
            print(f"  [MISSING]  Row {idx}: {loc}/{fp}")
            n_missing += 1
            missing_rows.append((idx, loc, fp))

    # Apply changes ───────────────────────────────────────────────────────────
    any_changes = (n_mismatch > 0 or n_orphan > 0)

    if not args.dry_run and any_changes:
        if orphan_rows:
            new_df = pd.DataFrame(orphan_rows, columns=columns)
            df = pd.concat([df, new_df], ignore_index=True)
        write_csv(df, csv_path)
        print(f"\nCSV written -> {csv_path}")
        print(f"Backup      -> {csv_path.with_suffix('.csv.bak')}")
    elif args.dry_run:
        print("\n[DRY RUN] CSV not written.")
    else:
        print("\nNo changes - CSV unchanged.")

    # Summary ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 54)
    print(f"Audit complete")
    print(f"  OK (file matches CSV location):   {n_ok}")
    print(f"  ContractLocation mismatches:      {n_mismatch}  {'(corrected)' if n_mismatch and not args.dry_run else ''}")
    print(f"  Orphan files (added to CSV):      {n_orphan}  {'(added — run scan-contract.py --all to fill metadata)' if n_orphan and not args.dry_run else ''}")
    print(f"  Duplicate (file in 2+ folders):   {n_duplicate}  (review and remove extra copy)")
    print(f"  Missing files (in CSV, not disk): {n_missing}  (review manually)")
    if args.dry_run:
        print("  [DRY RUN — CSV not written]")

    if missing_rows:
        print("\nMissing file details:")
        for idx, loc, fp in missing_rows[:50]:
            print(f"  Row {idx}: {loc}/{fp}")
        if len(missing_rows) > 50:
            print(f"  ... and {len(missing_rows) - 50} more (see full output)")


if __name__ == "__main__":
    main()
