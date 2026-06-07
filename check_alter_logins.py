"""
Verify that every alter ego account can log in with the shared ALTER_PASSWORD.

Run from project root:
    python check_alter_logins.py [persona_dir]

persona_dir defaults to "personas"; pass "agent_personas" to check the
MCP-generated profiles instead.

Reads accounts from {persona_dir}/*.json (ground truth for actual registered
names) and ALTER_PASSWORD from .env. Prints OK / FAIL per account and a summary.
"""
import json
import os
import sys
import time

from dotenv import load_dotenv
load_dotenv()

from src.session import VBulletinSession

_DELAY = 3  # seconds between login attempts to avoid rate-limiting
_DEFAULT_PERSONAS_DIR = "personas"


def main() -> None:
    personas_dir = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_PERSONAS_DIR

    alt_password = os.getenv("ALTER_PASSWORD", "")
    if not alt_password:
        print("ERROR: ALTER_PASSWORD not set in .env")
        return

    if not os.path.isdir(personas_dir):
        print(f"ERROR: directory not found: {personas_dir}/")
        return

    persona_files = sorted(f for f in os.listdir(personas_dir) if f.endswith(".json"))
    if not persona_files:
        print(f"No persona files found in {personas_dir}/")
        return

    accounts = []
    for fname in persona_files:
        with open(os.path.join(personas_dir, fname)) as f:
            d = json.load(f)
        accounts.append({
            "original_username": d.get("original_username", fname),
            "reversed_username": d.get("reversed_username", ""),
        })

    print(f"Checking {len(accounts)} alter ego accounts...\n")

    ok: list[str] = []
    fail: list[str] = []
    total = len(accounts)

    for i, account in enumerate(accounts):
        username = account["reversed_username"]
        original = account["original_username"]
        session = VBulletinSession()
        try:
            success = session.login(username, alt_password)
        except Exception as exc:
            print(f"  [{i+1:2}/{total}] {username:25} ({original}) ERROR: {exc}")
            fail.append(username)
        else:
            status = "OK  " if success else "FAIL"
            print(f"  [{i+1:2}/{total}] {username:25} ({original}) {status}")
            (ok if success else fail).append(username)

        if i < total - 1:
            time.sleep(_DELAY)

    print(f"\n{'─'*50}")
    print(f"  OK  : {len(ok)}/{total}")
    if fail:
        print(f"  FAIL: {len(fail)}/{total}")
        for name in fail:
            print(f"    - {name}")
    else:
        print("  All accounts logged in successfully.")


if __name__ == "__main__":
    main()
