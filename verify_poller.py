"""
Verify that fetch_new_posts correctly retrieves posts via the getnew thread list.

Run from project root:
    python verify_poller.py

NOTE: VBulletin updates "last visit" on each getnew call, so a second run right
after the first will return 0 threads until new posts appear on the forum.
"""
import logging
import os
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")

from src.session import VBulletinSession
from src.event.poller import (
    fetch_new_posts, parse_post_date, parse_new_thread_list,
    _resolve_search_page, _META_REFRESH_RE, _SEARCHID_RE,
)
from src.event.thread_scraper import parse_thread_page


def main() -> None:
    session = VBulletinSession()
    print(f"Logging in as {os.getenv('FORUM_USERNAME', 'wokebot')} ...")
    if not session.login(os.getenv("FORUM_USERNAME", ""), os.getenv("FORUM_PASSWORD", "")):
        print("LOGIN FAILED — check FORUM_USERNAME/FORUM_PASSWORD in .env")
        return
    print("Login OK\n")

    # Component test: verify a known thread page parses correctly
    print("Component test: fetching one thread page directly ...")
    test_html = session.get("showthread.php?t=17209")
    test_posts = parse_thread_page(test_html)
    print(f"  showthread.php?t=17209 → {len(test_posts)} posts parsed")
    if test_posts:
        p = test_posts[-1]
        print(f"  Last post: #{p['post_id']} by {p['author']} | {p['content'][:60]}")

    # Full end-to-end test — getdaily is stateless so no re-login needed
    print("\nCalling fetch_new_posts (getdaily — last 24h) ...")
    posts = fetch_new_posts(session)
    print(f"\n  Posts returned    : {len(posts)}")

    if not posts:
        print("  0 posts — either forum is quiet or last-visit was already up-to-date.")
        print("  (Run again after new posts appear on the forum to verify end-to-end.)")
        return

    cutoff_48h = datetime.now(timezone.utc) - timedelta(hours=48)
    recent = [p for p in posts if (d := parse_post_date(p.get("date", ""))) and d >= cutoff_48h]
    print(f"  Within last 48h   : {len(recent)}/{len(posts)}")

    forums: dict[str, int] = {}
    for p in posts:
        forums[p.get("forum_name", "?")] = forums.get(p.get("forum_name", "?"), 0) + 1
    print("\n  Posts by forum:")
    for forum, count in sorted(forums.items(), key=lambda x: -x[1]):
        print(f"    {forum:30} {count}")

    print("\n  Most recent 10 posts:")
    for p in sorted(posts, key=lambda x: x["post_id"], reverse=True)[:10]:
        print(f"    [{p['date']}] {p['forum_name']:20} | {p['thread_title'][:40]}")
        print(f"      by {p['author']:20} : {p['content'][:80]}")


if __name__ == "__main__":
    main()
