"""
sort-contracts.py  --  Contract File Sorter
Reads contract-catalog.csv, applies signing rules, and moves files
to their correct ContractLocation folder.

Classification rules:
  SigningStatus == "Signed"   -> "01 Active Contracts"
  SigningStatus == "Unsigned" -> "02 Unsigned Contracts"
  SigningStatus empty/unknown -> skip (run scan-contract.py first)
  ContractLocation == "03 Archived Contracts" -> never moved automatically

Usage:
  python Tools\sort-contracts.py
  python Tools\sort-contracts.py --dry-run
  python Tools\sort-contracts.py --vendor "Disney"
  python Tools\sort-contracts.py --location "02 Unsigned Contracts"
  python Tools\sort-contracts.py --csv "path\to\contract-catalog.csv"
"""

import argparse
import csv
import shutil
import sys
from datetime import date
from pathlib import Path, PurePosixPath

import pandas as pd

TODAY = date.today().isoformat()

# ── Paths ──────────────────────────────────────────────────────────────────────

SCRIPT_DIR   = Path(__file__).resolve().parent
SHAREPOINT   = SCRIPT_DIR.parent
DEFAULT_CSV  = SCRIPT_DIR / "contract-catalog.csv"

ACTIVE_LOC   = "01 Active Contracts"
UNSIGNED_LOC = "02 Unsigned Contracts"
ARCHIVE_LOC  = "03 Archived Contracts"

# VendorFolder names or prefixes that are template libraries — never auto-move
TEMPLATE_VENDOR_FRAGMENTS = ("template", "00 ")

# Filename substrings that disqualify a file from auto-moving
SKIP_FILENAME_FRAGMENTS = ("template", "redline")


def _is_template(vendor_folder: str, filename: str) -> bool:
    vf = vendor_folder.lower()
    fn = filename.lower()
    return (
        any(vf.startswith(p) or p in vf for p in TEMPLATE_VENDOR_FRAGMENTS)
        or any(p in fn for p in SKIP_FILENAME_FRAGMENTS)
    )

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


# ── Classification ─────────────────────────────────────────────────────────────

def target_location(signing_status: str) -> str | None:
    """Map SigningStatus -> correct ContractLocation, or None to skip."""
    s = signing_status.strip()
    if s == "Signed":
        return ACTIVE_LOC
    if s == "Unsigned":
        return UNSIGNED_LOC
    return None


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Move contract files to correct folders based on signing status",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Report moves without touching files or writing CSV")
    parser.add_argument("--vendor", metavar="NAME",
                        help="Only sort rows where VendorFolder contains NAME (case-insensitive)")
    parser.add_argument("--location", metavar="LOC",
                        help="Only sort rows currently in this ContractLocation")
    parser.add_argument("--csv", metavar="PATH", default=str(DEFAULT_CSV),
                        help="Path to contract-catalog.csv")
    args = parser.parse_args()

    csv_path = Path(args.csv).resolve()
    if not csv_path.exists():
        sys.exit(f"CSV not found: {csv_path}")

    print("sort-contracts.py  --  Contract File Sorter")
    print("=" * 54)
    print(f"CSV:  {csv_path}")
    print(f"Root: {SHAREPOINT}")
    if args.dry_run:
        print("Mode: DRY RUN (no changes written)")
    print()

    df = load_csv(csv_path)
    print(f"Loaded {len(df)} CSV rows.\n")

    # Apply optional filters
    mask = pd.Series([True] * len(df), index=df.index)
    if args.vendor:
        mask &= df["VendorFolder"].str.contains(args.vendor, case=False, na=False)
    if args.location:
        mask &= df["ContractLocation"] == args.location

    selected = df[mask]
    print(f"Rows selected: {len(selected)}\n")

    n_ok       = 0
    n_moved    = 0
    n_archived = 0
    n_skipped  = 0
    n_expired  = 0
    n_no_file  = 0
    n_error    = 0

    for idx in selected.index:
        current_loc = df.at[idx, "ContractLocation"]
        fp_raw      = _norm_fp(df.at[idx, "FilePath"])
        signing     = df.at[idx, "SigningStatus"]

        if not fp_raw:
            n_skipped += 1
            continue

        # Never auto-move to/from Archived — manual decision only
        if current_loc == ARCHIVE_LOC:
            n_archived += 1
            continue

        # Never auto-move template files — signing keywords appear in boilerplate
        vendor   = df.at[idx, "VendorFolder"]
        filename = df.at[idx, "Filename"] or Path(fp_raw).name
        if _is_template(vendor, filename):
            n_skipped += 1
            continue

        # Expired contracts need human review before archiving — never auto-move
        exp = df.at[idx, "ExpirationDate"].strip()
        if exp and exp not in ("upon written notice",) and exp <= TODAY:
            tag = "[DRY RUN] " if args.dry_run else ""
            print(f"  {tag}[REVIEW] Row {idx}: expired {exp} — needs human review before archiving")
            print(f"           {vendor}/{filename}")
            n_expired += 1
            continue

        tgt = target_location(signing)
        if tgt is None:
            # SigningStatus not populated — run scan-contract.py first
            n_skipped += 1
            continue

        if tgt == current_loc:
            n_ok += 1
            continue

        # File needs to move
        src = SHAREPOINT / current_loc / Path(PurePosixPath(fp_raw))
        dst = SHAREPOINT / tgt         / Path(PurePosixPath(fp_raw))

        if not src.exists():
            print(f"  [NOT FOUND]  Row {idx}: {current_loc}/{fp_raw}")
            n_no_file += 1
            continue

        tag = "[DRY RUN] " if args.dry_run else ""
        print(
            f"  {tag}[MOVE]  Row {idx}  {current_loc} -> {tgt}\n"
            f"           {vendor}/{filename}"
        )

        if not args.dry_run:
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                df.at[idx, "ContractLocation"] = tgt
                n_moved += 1
            except PermissionError as e:
                print(f"    [ERROR] Permission denied: {e}")
                n_error += 1
            except Exception as e:
                print(f"    [ERROR] {e}")
                n_error += 1
        else:
            n_moved += 1

    # Write CSV if anything changed
    if not args.dry_run and n_moved > 0:
        write_csv(df, csv_path)
        print(f"\nCSV written -> {csv_path}")
        print(f"Backup      -> {csv_path.with_suffix('.csv.bak')}")
    elif args.dry_run:
        print("\n[DRY RUN] No files moved, CSV not written.")
    else:
        print("\nNo moves needed — all files already in correct locations.")

    # Summary
    print("\n" + "=" * 54)
    print(f"Sort complete")
    print(f"  Already correct:             {n_ok}")
    if args.dry_run:
        print(f"  Would move:                  {n_moved}")
    else:
        print(f"  Moved (files + CSV updated): {n_moved}")
    print(f"  Archived (skipped):          {n_archived}  (manual decisions only)")
    print(f"  Expired (flagged for review):{n_expired}  (human must decide before archiving)")
    print(f"  No SigningStatus (skipped):  {n_skipped}  (run scan-contract.py first)")
    print(f"  Not found on disk:           {n_no_file}")
    print(f"  Errors:                      {n_error}")
    if args.dry_run:
        print("  [DRY RUN — no changes made]")


if __name__ == "__main__":
    main()
