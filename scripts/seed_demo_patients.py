"""Seed the 5 DaktariTB demo patients into a Prompt Opinion workspace.

Usage:
    python scripts/seed_demo_patients.py \\
        --workspace WORKSPACE_ID \\
        --cookie-file path/to/cookie.txt

    # or via environment variables
    export DAKTARITB_WORKSPACE=019d9e20-f426-7c9a-a91a-d1753175b113
    export DAKTARITB_COOKIE_FILE=~/po_session.txt
    python scripts/seed_demo_patients.py

Getting your session cookie:
    1. Open https://app.promptopinion.ai in your browser and log in.
    2. Open DevTools (F12).
    3. Application tab -> Cookies -> https://app.promptopinion.ai
    4. Copy the full cookie string (all name=value pairs joined by '; ').
    5. Save it to a file (e.g., ~/po_session.txt).

Getting your workspace ID:
    1. Navigate to your workspace in Prompt Opinion.
    2. The URL contains it: /workspaces/{WORKSPACE_ID}/...
    3. Copy just the UUID portion.

What this script does:
    - Loads demo/daktaritb_sample_bundle.json
    - POSTs it to {PO_HOST}/api/workspaces/{WS}/fhir as a FHIR transaction
    - Prints a summary of created patients and their Po IDs

After success, refresh your Po Patient Data -> List page and you will
see 5 new patients: Wanjiru Kamau, Joseph Otieno, Amina Hassan,
Grace Njeri, Samuel Kiprop.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)


DEFAULT_PO_HOST = "https://app.promptopinion.ai"
DEFAULT_BUNDLE = Path(__file__).resolve().parent.parent / "demo" / "daktaritb_sample_bundle.json"


def load_cookie(cookie_file: Path) -> str:
    """Load a cookie string from a file, trimming whitespace."""
    if not cookie_file.exists():
        print(f"ERROR: cookie file not found: {cookie_file}")
        print("See the script docstring for how to obtain your session cookie.")
        sys.exit(1)
    return cookie_file.read_text().strip()


def upload_bundle(po_host: str, workspace_id: str, cookie: str, bundle_path: Path) -> None:
    if not bundle_path.exists():
        print(f"ERROR: bundle file not found: {bundle_path}")
        sys.exit(1)

    bundle = json.loads(bundle_path.read_text())
    entry_count = len(bundle.get("entry", []))

    url = f"{po_host}/api/workspaces/{workspace_id}/fhir"
    headers = {
        "Content-Type": "application/fhir+json",
        "Accept": "application/fhir+json",
        "Cookie": cookie,
    }

    print(f"Uploading {entry_count} FHIR resources to {url}")
    print("(This creates 5 synthetic patients with their conditions, medications, and observations.)")
    print()

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, headers=headers, content=json.dumps(bundle))

    if resp.status_code == 401 or resp.status_code == 403:
        print(f"ERROR: authentication failed ({resp.status_code}).")
        print("Your session cookie may have expired. Log out and back in, then re-export it.")
        sys.exit(1)

    if resp.status_code >= 400:
        print(f"ERROR: Po returned HTTP {resp.status_code}")
        try:
            body = resp.json()
            print(json.dumps(body, indent=2)[:2000])
        except Exception:
            print(resp.text[:2000])
        sys.exit(1)

    # Success — parse the response bundle
    try:
        response_bundle = resp.json()
    except Exception:
        print("ERROR: couldn't parse response as JSON. Status was", resp.status_code)
        print(resp.text[:1000])
        sys.exit(1)

    created_patients = []
    for entry in response_bundle.get("entry", []):
        response = entry.get("response", {})
        location = response.get("location", "")
        if location.startswith("Patient/"):
            created_patients.append(location.split("/")[1])

    # Fallback: older Po versions may return just the entries
    if not created_patients:
        for entry in response_bundle.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Patient" and resource.get("id"):
                created_patients.append(resource["id"])

    print("=" * 60)
    print(f"SUCCESS: {resp.status_code} — seeded 5 demo patients")
    print("=" * 60)
    print()
    if created_patients:
        print(f"Created {len(created_patients)} Patient resources:")
        for pid in created_patients:
            print(f"  Patient/{pid}")
        print()
    else:
        print("(Po response format did not include patient IDs directly —")
        print(" check your Patient Data -> List page to confirm.)")
        print()

    print("Demo patients ready in your workspace:")
    print()
    print("  Wanjiru Kamau  (1991-06-14)  Nairobi   PLHIV, presumptive TB, CD4 290")
    print("  Joseph Otieno  (1983-11-22)  Kisumu    PLHIV stable on TLD, CD4 720")
    print("  Amina Hassan   (1997-04-03)  Mombasa   HIV-neg, active TB on RHZE")
    print("  Grace Njeri    (1999-09-18)  Nakuru    Newly-dx HIV, pre-ART, CD4 180")
    print("  Samuel Kiprop  (1987-02-11)  Eldoret   Co-infected (HIV+TB), on TLD + RHZE")
    print()
    print("Try the hero demos:")
    print()
    print("  1. Launchpad -> Wanjiru Kamau -> DaktariTB Specialist")
    print("     Prompt: 'Order the TB workup for this patient.'")
    print("     Expected: 4 FHIR ServiceRequests created, LF-LAM included (CD4<350)")
    print()
    print("  2. Launchpad -> Samuel Kiprop -> DaktariTB Specialist")
    print("     Prompt: 'File Samuel's TB notification for NTLD-P.'")
    print("     Expected: TB notification PDF generated, ART adjusted for")
    print("               rifampicin interaction (both tools fire autonomously)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed the DaktariTB demo patients into a Prompt Opinion workspace.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--workspace",
        default=os.environ.get("DAKTARITB_WORKSPACE"),
        help="Prompt Opinion workspace UUID (or set DAKTARITB_WORKSPACE)",
    )
    parser.add_argument(
        "--cookie-file",
        default=os.environ.get("DAKTARITB_COOKIE_FILE"),
        help="Path to a file containing your Po session cookie (or set DAKTARITB_COOKIE_FILE)",
    )
    parser.add_argument(
        "--po-host",
        default=os.environ.get("DAKTARITB_PO_HOST", DEFAULT_PO_HOST),
        help=f"Prompt Opinion host (default {DEFAULT_PO_HOST})",
    )
    parser.add_argument(
        "--bundle",
        default=str(DEFAULT_BUNDLE),
        help=f"Path to the FHIR bundle file (default {DEFAULT_BUNDLE})",
    )
    args = parser.parse_args()

    if not args.workspace:
        print("ERROR: --workspace or DAKTARITB_WORKSPACE is required.")
        print()
        parser.print_help()
        return 1
    if not args.cookie_file:
        print("ERROR: --cookie-file or DAKTARITB_COOKIE_FILE is required.")
        print()
        parser.print_help()
        return 1

    cookie = load_cookie(Path(args.cookie_file))
    upload_bundle(args.po_host, args.workspace, cookie, Path(args.bundle))
    return 0


if __name__ == "__main__":
    sys.exit(main())
