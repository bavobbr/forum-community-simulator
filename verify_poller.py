"""
Verify that fetch_new_posts correctly retrieves posts from search.php?do=getnew.

Run from project root:
    python verify_poller.py
"""
import os
import re
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv()

from src.session import VBulletinSession
from src.persona.scraper import parse_posts_page
from src.event.poller import fetch_new_posts, parse_post_date, _follow_meta_refresh

_META_REFRESH_RE = re.compile(
    r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+url=["\']?([^"\'>\s]+)', re.IGNORECASE
)


def main() -> None:
    session = VBulletinSession()
    print(f"Logging in as {os.getenv('FORUM_USERNAME', 'wokebot')} ...")
    if not session.login(os.getenv("FORUM_USERNAME", ""), os.getenv("FORUM_PASSWORD", "")):
        print("LOGIN FAILED — check FORUM_USERNAME/FORUM_PASSWORD in .env")
        return
    print("Login OK\n")

    # Step 1: raw fetch — check what VBulletin returns before any redirect handling
    print("Fetching search.php?do=getnew (raw) ...")
    raw_html = session.get("search.php?do=getnew")

    has_post_rows = bool(re.search(r'<table[^>]+id="post\d+', raw_html))
    has_meta_refresh = bool(_META_REFRESH_RE.search(raw_html))
    searchid_match = re.search(r'searchid=(\d+)', raw_html)

    print(f"  Response size     : {len(raw_html):,} chars")
    print(f"  Post rows present : {has_post_rows}")
    print(f"  Meta-refresh      : {has_meta_refresh}")
    print(f"  Searchid in page  : {searchid_match.group(1) if searchid_match else 'no'}")

    if not has_post_rows and not has_meta_refresh and not searchid_match:
        print("\nUnexpected response — first 1000 chars:")
        print(raw_html[:1000])
        return

    # Step 2: use fetch_new_posts (which now handles meta-refresh)
    print("\nCalling fetch_new_posts (with meta-refresh handling) ...")
    posts = fetch_new_posts(session)
    print(f"  Posts returned    : {len(posts)}")

    if not posts:
        print("  No posts — forum may be quiet or all posts are in excluded forums.")
        return

    # Step 3: show breakdown
    cutoff_48h = datetime.now(timezone.utc) - timedelta(hours=48)
    recent = [p for p in posts if (d := parse_post_date(p.get("date", ""))) and d >= cutoff_48h]

    print(f"  Within last 48h   : {len(recent)}/{len(posts)}")
    print()

    forums: dict[str, int] = {}
    for p in posts:
        forums[p.get("forum_name", "?")] = forums.get(p.get("forum_name", "?"), 0) + 1
    print("  Posts by forum:")
    for forum, count in sorted(forums.items(), key=lambda x: -x[1]):
        print(f"    {forum:30} {count}")

    print()
    print("  Most recent 10 posts:")
    for p in sorted(posts, key=lambda x: x["post_id"], reverse=True)[:10]:
        print(f"    [{p['date']}] {p['forum_name']:20} | {p['thread_title'][:45]}")


if __name__ == "__main__":
    main()
