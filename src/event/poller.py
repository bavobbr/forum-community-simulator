import os
import re
import time
import logging
from datetime import datetime, timezone, timedelta

from bs4 import BeautifulSoup

from src.event.thread_scraper import parse_thread_page

_EXCLUDED_FORUM_IDS = {20, 29, 40, 42}
_EXCLUDED_THREAD_IDS = {23585}  # experiment meta-thread — bots must never post here
_META_REFRESH_RE = re.compile(
    r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+url=["\']?([^"\'>\s]+)', re.IGNORECASE
)
_SEARCHID_RE = re.compile(r'searchid=(\d+)')
_THREAD_TITLE_ID_RE = re.compile(r"^thread_title_(\d+)$")
_FORUM_LINK_RE = re.compile(r"forumdisplay\.php\?f=(\d+)")
_FETCH_DELAY = 2  # seconds between thread page fetches


_THREAD_LIST_RE = re.compile(r'id="thread_title_\d+')


def _resolve_search_page(session, html: str) -> str:
    """Return the thread list HTML (pp=100) for a getnew search page.

    Handles three VBulletin response patterns:
    - Already on a thread list page (requests followed a 302 redirect): re-fetch
      the same searchid with pp=100 to ensure we get up to 100 threads.
    - Landing page with a searchid link: fetch the thread list.
    - Meta-refresh redirect (rare): follow and re-enter.
    """
    m = _SEARCHID_RE.search(html)
    if m:
        url = f"search.php?searchid={m.group(1)}&pp=100"
        # Skip re-fetch if we already have the full list (same searchid, pp already 100)
        if _THREAD_LIST_RE.search(html) and "pp=100" in html:
            logging.debug("getnew: already on full thread list (pp=100)")
            return html
        logging.debug("getdaily: fetching thread list via %s", url)
        return session.get(url)
    m = _META_REFRESH_RE.search(html)
    if m:
        logging.debug("getnew: following meta-refresh to %s", m.group(1))
        return session.get(m.group(1))
    return html


def parse_new_thread_list(html: str) -> list[dict]:
    """Extract thread metadata from a VBulletin getnew thread list page."""
    soup = BeautifulSoup(html, "html.parser")
    threads = []
    for a in soup.find_all("a", id=_THREAD_TITLE_ID_RE):
        m = _THREAD_TITLE_ID_RE.match(a["id"])
        thread_id = int(m.group(1))
        strong = a.find("strong")
        thread_title = (strong or a).get_text(strip=True)

        row = a.find_parent("tr")
        forum_id = 0
        forum_name = ""
        if row:
            forum_link = row.find("a", href=_FORUM_LINK_RE)
            if forum_link:
                fm = _FORUM_LINK_RE.search(forum_link["href"])
                forum_id = int(fm.group(1)) if fm else 0
                forum_name = forum_link.get_text(strip=True)

        threads.append({
            "thread_id": thread_id,
            "thread_title": thread_title,
            "forum_id": forum_id,
            "forum_name": forum_name,
        })
    return threads


def fetch_new_posts(session) -> list[dict]:
    """Fetch new posts since last visit. Re-authenticates if session expired."""
    html = session.get("search.php?do=getdaily")

    if "Log Out" not in html and "User CP" not in html:
        logging.info("Scanner session expired — re-authenticating")
        session.login(os.getenv("FORUM_USERNAME", ""), os.getenv("FORUM_PASSWORD", ""))
        html = session.get("search.php?do=getdaily")

    html = _resolve_search_page(session, html)
    threads = parse_new_thread_list(html)
    logging.info("getdaily: %d threads in list", len(threads))

    threads = [t for t in threads if t["forum_id"] not in _EXCLUDED_FORUM_IDS]
    threads = [t for t in threads if t["thread_id"] not in _EXCLUDED_THREAD_IDS]

    posts = []
    for thread in threads:
        try:
            time.sleep(_FETCH_DELAY)
            thread_html = session.get(f"showthread.php?goto=newpost&t={thread['thread_id']}")
            thread_posts = parse_thread_page(thread_html)
            for p in thread_posts:
                p["thread_id"] = thread["thread_id"]
                p["thread_title"] = thread["thread_title"]
                p["forum_id"] = thread["forum_id"]
                p["forum_name"] = thread["forum_name"]
            posts.extend(thread_posts)
            logging.debug("thread %d (%s): %d posts", thread["thread_id"], thread["thread_title"], len(thread_posts))
        except Exception as exc:
            logging.warning("Failed to fetch thread %d: %s", thread["thread_id"], exc)

    return posts


def parse_post_date(date_str: str) -> datetime | None:
    """Parse a VBulletin post date to a timezone-aware datetime (UTC+2).

    Handles:
    - 'DD-MM-YYYY, HH:MM' (absolute)
    - 'Today, HH:MM' / 'Yesterday, HH:MM' (VBulletin relative labels)
    """
    s = date_str.strip()
    tz = timezone(timedelta(hours=2))
    now = datetime.now(tz)
    for label, delta in (("Today", timedelta(0)), ("Yesterday", timedelta(days=1))):
        if s.startswith(label + ","):
            try:
                t = datetime.strptime(s[len(label) + 1:].strip(), "%H:%M")
                base = (now - delta).replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
                return base
            except ValueError:
                return None
    try:
        dt = datetime.strptime(s, "%d-%m-%Y, %H:%M")
        return dt.replace(tzinfo=tz)
    except (ValueError, AttributeError):
        return None
