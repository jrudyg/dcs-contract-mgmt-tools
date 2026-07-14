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
ONEDRIVE    = SHAREPOINT.parent
DEFAULT_CSV = SCRIPT_DIR / "contract-catalog.csv"

# ContractLocation is a LOGICAL label, not always a folder name. "01 Active
# Contracts" has no folder by that name: active files physically live in the
# separately-synced "Salesforce Integration - Active Contracts" library, a
# sibling of the SharePoint root. Always resolve through LOCATION_ROOTS —
# never join SHAREPOINT / ContractLocation directly.
LOCATION_ROOTS = {
    "01 Active Contracts":   ONEDRIVE   / "Salesforce Integration - Active Contracts",
    "02 Unsigned Contracts": SHAREPOINT / "02 Unsigned Contracts",
    "03 Archived Contracts": SHAREPOINT / "03 Archived Contracts",
    "04 Expired Contracts":  SHAREPOINT / "04 Expired Contracts",
}

CONTRACT_ROOTS = list(LOCATION_ROOTS)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".msg"}

SKIP_NAMES = {"__pycache__", ".git", ".DS_Store", "Thumbs.db"}

# Vendor folder prefixes that are template libraries, not actual contracts
TEMPLATE_FOLDER_PREFIXES = ("00 ",)

# Top-level folders inside a ContractLocation that are NOT vendor folders and
# must never be catalogued. "01 Active Contracts - do not use" is a stale copy
# of the old active tree left inside 03 Archived; walking it would add ~396
# bogus rows for files that are duplicates of the live Salesforce library.
EXCLUDED_VENDOR_FOLDERS = {"01 active contracts - do not use"}

# Individual files that are on disk but deliberately have NO catalog row, with the
# reason. Reviewed 2026-07-14 (Phase 3 reconciliation). Without this, any write-mode
# run of this script would silently re-add them and undo the exclusion.
EXCLUDED_FILES: dict[tuple[str, str], str] = {
    ("01 Active Contracts", "ISM/Effective Contracting - ISM 05.14.26.pdf"):
        "training material, not a contract",
    ("01 Active Contracts", "Williams Sonoma/DATUM EULA 06.12.2026 - Clean - audit.pdf"):
        "'- audit' working copy of a catalogued EULA",
    ("01 Active Contracts", "Williams Sonoma/WSI-DCS  EXHIBIT A.2 SOW 26.06.22 CLEAN - audit.pdf"):
        "'- audit' working copy of a catalogued SOW",
    ("03 Archived Contracts", "ACI Licenses/AL Contractor License.pdf"):
        "contractor license certificate, not a contract",
    ("03 Archived Contracts", "Nationwide Services/Nationwide Svcs FL Contractor Lic thru 8-31-26.pdf"):
        "contractor license certificate, not a contract",
}

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

def walk_contracts(root: Path | None = None):
    """Yield (contract_location, fp_key, vendor_folder, abs_path) for every supported file."""
    for loc, loc_dir in LOCATION_ROOTS.items():
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
            # Skip non-vendor folders (e.g. the stale "do not use" active tree)
            if rel_parts and rel_parts[0].lower() in EXCLUDED_VENDOR_FOLDERS:
                continue
            if abs_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            rel = abs_path.relative_to(loc_dir)
            fp_key = _norm_fp(str(rel))
            vendor_folder = rel.parts[0] if len(rel.parts) > 1 else ""
            yield loc, fp_key, vendor_folder, abs_path


# ── Orphan row builder ────────────────────────────────────────────────────────

def make_orphan_row(columns: list, loc: str, fp_key: str, vendor: str, abs_path: Path) -> dict:
    # FileCreatedDate was dropped from the schema (2026-07-14). It was populated
    # from st_ctime, which on a OneDrive-synced library reports the *rehydration*
    # date, not the document date — see "Never Trust Filesystem Dates" in
    # NIGHTLY_CATALOG_JOB.md. Use DateInFilename / EffectiveDate instead.
    row = {col: "" for col in columns}
    row["ContractLocation"] = loc
    row["VendorFolder"]     = vendor
    row["Filename"]         = abs_path.name
    row["FilePath"]         = fp_key
    row["Extension"]        = abs_path.suffix.lower().lstrip(".")
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

    # ── Uniqueness invariant: (ContractLocation, FilePath) ─────────────────────
    # FilePath alone is NOT a key. The same relative path legitimately exists in
    # two locations (e.g. an unsigned draft in 02 and a signed copy in 01), and
    # they are two distinct records. Matching on FilePath alone previously made
    # this script rewrite a row's ContractLocation to whichever copy the disk
    # walk happened to reach last — manufacturing phantom "mismatches" and
    # silently corrupting data. Everything below keys on (loc, fp).
    key_to_indices: dict[tuple[str, str], list[int]] = {}
    for idx in df.index:
        fp = _norm_fp(df.at[idx, "FilePath"])
        if fp:
            key_to_indices.setdefault((df.at[idx, "ContractLocation"], fp), []).append(idx)

    # A real violation: two rows sharing the SAME (location, path).
    n_dup_rows = 0
    for (loc, fp), indices in key_to_indices.items():
        if len(indices) > 1:
            n_dup_rows += 1
            rows_str = ", ".join(f"row {i}" for i in indices)
            print(f"  [DUP-ROW]  Same (ContractLocation, FilePath) in {len(indices)} rows: [{loc}] {fp}")
            print(f"             Rows: {rows_str}")
            print(f"             -> Violates the catalog uniqueness invariant; remove the extra row(s).")
    if n_dup_rows:
        print()

    # Walk disk ────────────────────────────────────────────────────────────────
    print("Walking contract folders on disk...")

    confirmed_indices: set[int] = set()
    updated_indices:   set[int] = set()  # rows already corrected this run
    n_ok = 0
    n_mismatch = 0
    n_orphan   = 0
    n_duplicate = 0
    n_excluded  = 0
    orphan_rows: list[dict] = []

    # Every (location, path) present on disk.
    disk_keys = {(loc, fp_key) for loc, fp_key, _v, _p in walk_contracts()}

    for loc, fp_key, vendor, abs_path in walk_contracts():
        indices = key_to_indices.get((loc, fp_key))

        if indices is not None:
            # Row and file agree on both location and path.
            confirmed_indices.update(indices)
            n_ok += len(indices)
            continue

        # No row for THIS (location, path). Before calling it an orphan, check
        # whether a row holds the same path at a different location AND that
        # row's own file is gone from disk — that is a genuine relocation, so
        # correct the row rather than adding a duplicate one.
        moved_from = [
            (other_loc, idx)
            for (other_loc, other_fp), idxs in key_to_indices.items()
            if other_fp == fp_key and other_loc != loc and (other_loc, other_fp) not in disk_keys
            for idx in idxs
            if idx not in updated_indices and idx not in confirmed_indices
        ]
        if moved_from:
            other_loc, idx = moved_from[0]
            tag = "[DRY RUN] " if args.dry_run else ""
            print(f'  {tag}[MOVED]    Row {idx}: ContractLocation "{other_loc}" -> "{loc}"  |  {fp_key}')
            print(f"             (file is no longer in {other_loc}; it is only in {loc})")
            n_mismatch += 1
            confirmed_indices.add(idx)
            updated_indices.add(idx)
            if not args.dry_run:
                df.at[idx, "ContractLocation"] = loc
            continue

        # A row may hold this path at another location where the file ALSO still
        # exists. That is two distinct records, not a mismatch — never rewrite it.
        same_path_elsewhere = any(
            other_fp == fp_key and other_loc != loc and (other_loc, other_fp) in disk_keys
            for (other_loc, other_fp) in key_to_indices
        )
        if (loc, fp_key) in EXCLUDED_FILES:
            print(f"  [EXCLUDED] {loc}/{fp_key}")
            print(f"             -> {EXCLUDED_FILES[(loc, fp_key)]}")
            n_excluded += 1
            continue

        tag = "[DRY RUN] " if args.dry_run else ""
        note = "  (same path also exists in another location — distinct record, not a duplicate)" \
            if same_path_elsewhere else ""
        print(f"  {tag}[ORPHAN]   {loc}/{fp_key}{note}")
        n_orphan += 1
        if not args.dry_run:
            orphan_rows.append(make_orphan_row(columns, loc, fp_key, vendor, abs_path))

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
        base = LOCATION_ROOTS.get(loc)
        full = (base / Path(PurePosixPath(fp))) if base else None
        if full is None or not full.exists():
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
    print(f"  OK (row matches disk):            {n_ok}")
    print(f"  Relocated (file moved location):  {n_mismatch}  {'(corrected)' if n_mismatch and not args.dry_run else ''}")
    print(f"  Orphan files (added to CSV):      {n_orphan}  {'(added — run scan-contract.py --all to fill metadata)' if n_orphan and not args.dry_run else ''}")
    print(f"  Excluded files (no row, by design): {n_excluded}")
    print(f"  DUP-ROW invariant violations:     {n_dup_rows}  (same ContractLocation+FilePath in 2+ rows)")
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
