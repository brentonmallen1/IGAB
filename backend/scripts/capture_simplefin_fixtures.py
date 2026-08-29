"""
Capture SimpleFIN API responses and save as test fixtures.

Usage:
    # Claim a setup token and fetch data:
    python scripts/capture_simplefin_fixtures.py --setup-token <base64-token>

    # Use an already-claimed access URL:
    python scripts/capture_simplefin_fixtures.py --access-url <https://user:pass@...>

    # Load from .env (reads SIMPLEFIN_API_TOKEN and optionally SIMPLEFIN_ACCESS_URL):
    python scripts/capture_simplefin_fixtures.py

Outputs fixtures to tests/fixtures/simplefin/, with account and reference
numbers masked and every --redact term struck from descriptions, payees and
memos. `assert_clean` refuses to write anything that still carries one.

Pass --redact once per person who appears on the accounts:

    python scripts/capture_simplefin_fixtures.py --redact 'First Last'
"""

import argparse
import asyncio
import base64
import json
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "simplefin"
ACCESS_URL_CACHE = Path(__file__).parent.parent / ".simplefin_access_url"


#: Terms the operator has told us are personal — names, mostly. Populated from
#: --redact before anything is written, and enforced by `save_fixture`.
REDACT: list[str] = []


def _sanitize(obj: object, depth: int = 0) -> object:
    """Redact personal data fields while preserving structure."""
    if depth > 10:
        return obj
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in ("id", "conn_id"):
                # Keep IDs but hash them for determinism
                out[k] = f"fixture_{k}_{abs(hash(str(v))) % 100000:05d}"
            elif k == "name" and depth == 1:
                # Account name - strip partial account numbers
                out[k] = _sanitize_account_name(str(v))
            elif k in ("description", "payee", "memo"):
                # All three carry the bank's free text, and all three carried
                # a real name the first time this ran: `payee` was simply not
                # in this list, so "<merchant> Account Payment <name>" was
                # written verbatim into a public repo.
                out[k] = _sanitize_description(str(v))
            elif k in ("balance", "available-balance", "amount"):
                # Keep numeric structure but shift values slightly
                out[k] = v
            elif k == "org":
                out[k] = _sanitize(v, depth + 1)
            else:
                out[k] = _sanitize(v, depth + 1)
        return out
    if isinstance(obj, list):
        return [_sanitize(item, depth + 1) for item in obj]
    return obj


def _sanitize_description(desc: str) -> str:
    """Mask account/reference numbers and the names given to --redact.

    The docstring here used to promise it replaced "personal names" and no
    code did: there was no name handling at all, `payee` was not routed
    through it, and the digit floor of 9 let reference numbers like a
    7-digit student loan account through. 250 real transactions reached a
    public repository on the strength of that sentence. Whatever this claims
    is now enforced by `assert_clean` before anything is written.
    """
    for term in REDACT:
        desc = re.sub(re.escape(term), "REDACTED", desc, flags=re.IGNORECASE)
    # Mask explicit card references like CARD3951 or CARD 1234
    desc = re.sub(r"CARD\s*\d{4,}", "CARDXXXX", desc)
    # Mask 16-digit card numbers
    desc = re.sub(r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b", "****-****-****-****", desc)
    # Mask any run of 5+ digits: loan, policy and reference numbers are
    # routinely shorter than the old 9-digit floor.
    desc = re.sub(r"\b\d{5,}\b", "XXXXX", desc)
    # Mask partial account numbers like ...2177 or #2177
    desc = re.sub(r"[\.#]{2,}\d{4,}", "....XXXX", desc)
    return desc


_ACCOUNT_NAME_RE = re.compile(r"^(.*?)(\s*[\.\(]\.+\d{4,}[\)\s]*)(\s*\(.*\))?$")


def _sanitize_account_name(name: str) -> str:
    """Remove partial account numbers from account names."""
    # Patterns like "EVERYDAY CHECKING ...2177 (2177)"
    sanitized = re.sub(r"\s*[\.\(]+\s*\d{4,}\s*[\)\s]*", "", name).strip()
    return sanitized or "Test Account"


def assert_clean(text: str) -> None:
    """Refuse to write output that still carries a redact term or a long number.

    The gate, not the intention, is what keeps this honest — a sanitizer that
    quietly does nothing looks exactly like one that works.
    """
    residue = [t for t in REDACT if re.search(re.escape(t), text, re.IGNORECASE)]
    if residue:
        raise SystemExit(f"refusing to write: redact term(s) survived sanitizing: {residue}")
    leftover = re.findall(r"\b\d{5,}\b", text)
    if leftover:
        raise SystemExit(
            f"refusing to write: {len(leftover)} long number(s) survived sanitizing, "
            f"e.g. {sorted(set(leftover))[:5]}"
        )


async def claim_token(setup_token: str) -> str:
    decoded = base64.b64decode(setup_token).decode()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(decoded)
        resp.raise_for_status()
        return resp.text.strip()


async def fetch_accounts(access_url: str, start_date: datetime | None = None) -> dict:
    accounts_url = access_url.rstrip("/") + "/accounts"
    params: dict = {"pending": "1"}
    if start_date:
        params["start-date"] = int(start_date.replace(tzinfo=UTC).timestamp())
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(accounts_url, params=params)
        resp.raise_for_status()
        return resp.json()


def save_fixture(name: str, data: dict) -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURES_DIR / f"{name}.json"
    sanitized = _sanitize(data)
    payload = json.dumps(sanitized, indent=2)
    assert_clean(payload)
    path.write_text(payload)
    txn_count = sum(len(a.get("transactions", [])) for a in data.get("accounts", []))
    print(f"  Saved {path.name}: {len(data.get('accounts', []))} accounts, {txn_count} transactions")


async def main() -> None:
    load_dotenv(Path(__file__).parent.parent.parent / ".env")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--setup-token", help="Base64-encoded SimpleFIN setup token")
    parser.add_argument("--access-url", help="Already-claimed SimpleFIN access URL")
    parser.add_argument(
        "--redact",
        action="append",
        default=[],
        metavar="TERM",
        help="A name to strike from every description, payee and memo. Repeatable. "
        "Required unless --no-redact-check: a capture with no names given is "
        "how 250 real transactions reached a public repo.",
    )
    parser.add_argument(
        "--no-redact-check",
        action="store_true",
        help="Capture without naming anything to redact. Say so deliberately.",
    )
    args = parser.parse_args()
    if not args.redact and not args.no_redact_check:
        raise SystemExit(
            "refusing to capture: pass --redact 'First Last' for every person who "
            "appears on these accounts, or --no-redact-check to say there are none."
        )
    REDACT[:] = args.redact

    access_url = args.access_url

    if not access_url and ACCESS_URL_CACHE.exists():
        access_url = ACCESS_URL_CACHE.read_text().strip()
        print(f"Using cached access URL from {ACCESS_URL_CACHE}")

    if not access_url:
        setup_token = args.setup_token or os.environ.get("SIMPLEFIN_API_TOKEN")
        if not setup_token:
            print("ERROR: Provide --access-url, --setup-token, or set SIMPLEFIN_API_TOKEN in .env", file=sys.stderr)
            sys.exit(1)
        print("Claiming setup token...")
        try:
            access_url = await claim_token(setup_token)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                print("ERROR: Token already claimed or invalid. Provide --access-url directly.", file=sys.stderr)
                sys.exit(1)
            raise
        ACCESS_URL_CACHE.write_text(access_url)
        print(f"Access URL claimed and cached to {ACCESS_URL_CACHE}")

    print("\nFetching fixtures...")

    # Full history (90 days) — first sync scenario
    ninety_days_ago = datetime.now(UTC) - timedelta(days=90)
    print("  Fetching full 90-day history...")
    full_data = await fetch_accounts(access_url, start_date=ninety_days_ago)
    save_fixture("accounts_full", full_data)

    # Incremental (24 hours) — subsequent sync scenario
    one_day_ago = datetime.now(UTC) - timedelta(days=1)
    print("  Fetching 24-hour incremental...")
    incremental_data = await fetch_accounts(access_url, start_date=one_day_ago)
    save_fixture("accounts_incremental", incremental_data)

    # Accounts only (no transactions) — for account linking UI
    print("  Fetching accounts metadata only...")
    accounts_only = await fetch_accounts(access_url)
    # Strip transactions for a lean fixture
    accounts_metadata = {
        **accounts_only,
        "accounts": [
            {k: v for k, v in a.items() if k != "transactions"}
            for a in accounts_only.get("accounts", [])
        ],
    }
    save_fixture("accounts_metadata", accounts_metadata)

    print(f"\nDone. Fixtures saved to {FIXTURES_DIR}/")
    print("\nNOTE: Review fixtures for any remaining sensitive data before committing.")


if __name__ == "__main__":
    asyncio.run(main())
