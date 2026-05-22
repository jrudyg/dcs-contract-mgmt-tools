"""
1-way sync: Salesforce SoR (SharePoint) → local 01 Active Contracts.
Copy only — never moves or deletes source files.

Requirements (already installed): msal, requests

First-time setup:
  1. In Azure portal, register an App (Accounts in this org, Public client/mobile).
  2. API Permissions → Add → Microsoft Graph → Delegated:
       Files.Read.All  and  Sites.Read.All
  3. Set env var  SOR_CLIENT_ID=<Application (client) ID>
     Or paste it directly into CLIENT_ID below.

Run manually:  python sync-sor.py [--dry-run]
"""

import sys, os, json, shutil, argparse
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
TOOLS    = Path(__file__).resolve().parent
DST_ROOT = TOOLS.parent / "01 Active Contracts"
CACHE_F  = TOOLS / ".sor_token_cache.json"

# ── Config ───────────────────────────────────────────────────────────────────
CLIENT_ID = os.getenv("SOR_CLIENT_ID", "")          # Azure AD Application (client) ID
TENANT_ID = os.getenv("SOR_TENANT_ID", "common")    # "common" works for any M365 tenant
SCOPES    = ["https://graph.microsoft.com/Files.Read.All",
             "https://graph.microsoft.com/Sites.Read.All"]
SOR_HOST  = "diakoniagroupllc.sharepoint.com"
SOR_SITE  = "SalesforceContracts"
SOR_LIB   = "Active Contracts"
GRAPH     = "https://graph.microsoft.com/v1.0"


def log(msg):
    print(msg, flush=True)


def get_token():
    try:
        import msal
    except ImportError:
        log("[ERROR] msal not installed. Run: pip install msal")
        sys.exit(1)

    if not CLIENT_ID:
        log("[ERROR] SOR_CLIENT_ID is not configured.")
        log("")
        log("Setup (one-time):")
        log("  1. Go to https://portal.azure.com → Azure Active Directory → App registrations")
        log("  2. New registration → any name → Accounts in this organizational directory only")
        log("     → Public client/native (set 'Allow public client flows' to Yes)")
        log("  3. API permissions → Add → Microsoft Graph → Delegated:")
        log("       Files.Read.All   Sites.Read.All")
        log("  4. Copy the Application (client) ID and set env var SOR_CLIENT_ID=<id>")
        log("     Or paste it directly into CLIENT_ID in sync-sor.py")
        sys.exit(1)

    cache = msal.SerializableTokenCache()
    if CACHE_F.exists():
        try:
            cache.deserialize(CACHE_F.read_text(encoding="utf-8"))
        except Exception:
            pass

    app = msal.PublicClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        token_cache=cache,
    )

    # Try silent (cached) first
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result:
        # Device code flow — user visits a URL and enters a code
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            log("[ERROR] Could not start device auth: " + json.dumps(flow, indent=2))
            sys.exit(1)
        log("")
        log("── Authentication required ──────────────────────────────────────")
        log(flow["message"])
        log("────────────────────────────────────────────────────────────────")
        log("")
        result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        log("[ERROR] Auth failed: " + result.get("error_description", str(result)))
        sys.exit(1)

    if cache.has_state_changed:
        CACHE_F.write_text(cache.serialize(), encoding="utf-8")
        log("[Auth] Token cached for future runs.")

    return result["access_token"]


def graph_get(token, url):
    import requests
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    if not resp.ok:
        raise RuntimeError(f"Graph API error {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def get_drive_id(token):
    site_resp = graph_get(token, f"{GRAPH}/sites/{SOR_HOST}:/sites/{SOR_SITE}")
    site_id   = site_resp["id"]
    drives    = graph_get(token, f"{GRAPH}/sites/{site_id}/drives")
    for d in drives.get("value", []):
        if d.get("name", "").lower() == SOR_LIB.lower():
            return d["id"]
    available = [d["name"] for d in drives.get("value", [])]
    raise RuntimeError(f"Library '{SOR_LIB}' not found. Available: {available}")


def list_all_files(token, drive_id):
    """Recursively list every file in the drive, returning list of dicts."""
    files = []

    def traverse(item_id, rel_parent=""):
        url = f"{GRAPH}/drives/{drive_id}/items/{item_id}/children"
        while url:
            data = graph_get(token, url)
            for item in data.get("value", []):
                rel = f"{rel_parent}/{item['name']}".lstrip("/")
                if "folder" in item:
                    traverse(item["id"], rel)
                else:
                    files.append({
                        "path":     rel,
                        "size":     item.get("size", 0),
                        "download": item.get("@microsoft.graph.downloadUrl", ""),
                    })
            url = data.get("@odata.nextLink")

    root = graph_get(token, f"{GRAPH}/drives/{drive_id}/root")
    traverse(root["id"])
    return files


def run(dry_run=False):
    import requests as req_lib

    log(f"Connecting to {SOR_HOST}/sites/{SOR_SITE}/{SOR_LIB} …")
    token = get_token()
    log("Authenticated.")

    log("Resolving document library …")
    drive_id = get_drive_id(token)
    log("Library found. Listing files (this may take a moment) …")

    files = list_all_files(token, drive_id)
    log(f"Found {len(files)} files in SoR.")
    log("")

    copied = skipped = errors = 0

    for f in files:
        rel_path = f["path"]
        dst_file = DST_ROOT / rel_path
        src_size = f["size"]

        # Skip if destination already matches size
        if dst_file.exists() and dst_file.stat().st_size == src_size:
            skipped += 1
            continue

        action = "[DRY] Copy" if dry_run else "Copy"
        log(f"  {action}: {rel_path}")

        if not dry_run:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            download_url = f["download"]
            if not download_url:
                log(f"  [SKIP] No download URL for: {rel_path}")
                errors += 1
                continue
            try:
                with req_lib.get(download_url, stream=True, timeout=120) as r:
                    r.raise_for_status()
                    tmp = dst_file.with_suffix(dst_file.suffix + ".tmp")
                    with open(tmp, "wb") as out:
                        shutil.copyfileobj(r.raw, out)
                    tmp.replace(dst_file)
                copied += 1
            except Exception as exc:
                log(f"  [ERROR] {rel_path}: {exc}")
                if dst_file.with_suffix(dst_file.suffix + ".tmp").exists():
                    dst_file.with_suffix(dst_file.suffix + ".tmp").unlink(missing_ok=True)
                errors += 1
        else:
            copied += 1

    log("")
    prefix = "[DRY RUN] " if dry_run else ""
    log(f"{prefix}Sync complete.")
    log(f"  Copied:  {copied}")
    log(f"  Skipped: {skipped}  (already up to date)")
    log(f"  Errors:  {errors}")
    if copied > 0 and not dry_run:
        log("")
        log("Tip: Run 'Scan All' in the scanner to add any new files to the catalog.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="1-way sync: Salesforce SoR → local 01 Active Contracts")
    p.add_argument("--dry-run", action="store_true", help="Preview without copying")
    args = p.parse_args()
    run(dry_run=args.dry_run)
