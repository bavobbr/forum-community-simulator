"""
Standalone test: fetch the 500 most recent posts by 'acku' using date-windowed
advanced search. Run from the project root:

    python test_fetch_posts.py

Verifies that each batch returns posts genuinely older than the previous one.
Results are saved to test_fetch_posts_results.json for inspection.
"""
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from src.session import VBulletinSession
from src.persona.scraper import PostScraper, parse_post_date_timestamp

load_dotenv()

TARGET_USERNAME = "acku"
TARGET_POSTS = 500
DELAY = 6  # seconds between every forum request


def main() -> None:
    # --- Login ---
    session = VBulletinSession()
    username = os.getenv("FORUM_USERNAME", "wokebot")
    password = os.getenv("FORUM_PASSWORD", "wokebot123")
    print(f"Logging in as {username} ...")
    ok = session.login(username, password)
    if not ok:
        print("LOGIN FAILED — check FORUM_USERNAME/FORUM_PASSWORD in .env")
        return
    print(f"Login OK  |  security token: {session.security_token[:40]}...")

    scraper = PostScraper(session, delay=DELAY)

    all_posts: dict[int, dict] = {}
    before_ts: int | None = None
    batch_num = 0
    prev_oldest_id: int | None = None

    print(f"\nFetching up to {TARGET_POSTS} posts for '{TARGET_USERNAME}' in batches\n")

    while len(all_posts) < TARGET_POSTS:
        batch_num += 1
        print(f"{'='*60}")
        print(f"Batch {batch_num}  (before_ts={before_ts})")

        try:
            posts, oldest_ts = scraper.fetch_window(TARGET_USERNAME, before_ts=before_ts)
        except ValueError as exc:
            print(f"  ERROR: {exc}")
            break

        if not posts:
            print("  No posts returned — done.")
            break

        by_id = sorted(posts, key=lambda p: p["post_id"])
        newest, oldest = by_id[-1], by_id[0]

        print(f"  Posts this batch : {len(posts)}")
        print(f"  Newest post      : id={newest['post_id']}  date={newest['date']}")
        print(f"  Oldest post      : id={oldest['post_id']}  date={oldest['date']}")

        # Verify advancement: the OLDEST post in this batch must be older
        # (lower post_id) than the oldest post in the previous batch.
        # A small overlap at the newest end is expected and harmless.
        if prev_oldest_id is not None:
            overlap = sum(1 for p in posts if p["post_id"] >= prev_oldest_id)
            if oldest["post_id"] >= prev_oldest_id:
                print(f"  STUCK: oldest id ({oldest['post_id']}) >= prev batch oldest ({prev_oldest_id})")
                print("         Date filter may not be working — breaking.")
                break
            else:
                print(f"  OK: advancing — oldest {oldest['post_id']} < prev {prev_oldest_id} ✓  (overlap: {overlap} posts)")

        prev_oldest_id = oldest["post_id"]

        for post in posts:
            all_posts[post["post_id"]] = post

        print(f"  Unique posts so far: {len(all_posts)}")
        print(f"  Next before_ts: {oldest_ts}")

        if oldest_ts is None:
            print("  No older cutoff available — stopping.")
            break

        before_ts = oldest_ts

    print(f"\n{'='*60}")
    print(f"DONE: {len(all_posts)} unique posts fetched in {batch_num} batch(es)")

    if all_posts:
        by_id = sorted(all_posts.values(), key=lambda p: p["post_id"])
        print(f"Overall date range: {by_id[0]['date']}  →  {by_id[-1]['date']}")
        print(f"Post-id range:      {by_id[0]['post_id']}  →  {by_id[-1]['post_id']}")

    out = Path("test_fetch_posts_results.json")
    out.write_text(
        json.dumps(sorted(all_posts.values(), key=lambda p: p["post_id"]),
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nFull results saved to {out}")


if __name__ == "__main__":
    main()
