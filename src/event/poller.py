import os
import re
import logging
from datetime import datetime, timezone, timedelta

from src.persona.scraper import parse_posts_page

_EXCLUDED_FORUM_IDS = {20, 29, 40, 42}
_META_REFRESH_RE = re.compile(
    r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+url=["\']?([^"\'>\s]+)', re.IGNORECASE
)


def _follow_meta_refresh(session, html: str) -> str:
    """If the page contains a meta-refresh redirect, follow it and return the target HTML."""
    m = _META_REFRESH_RE.search(html)
    if not m:
        return html
    url = m.group(1)
    logging.debug("getnew: following meta-refresh to %s", url)
    return session.get(url)


def fetch_new_posts(session) -> list[dict]:
    """Fetch new posts since last visit. Re-authenticates if session expired."""
    html = session.get("search.php?do=getnew")

    if "Log Out" not in html and "User CP" not in html:
        logging.info("Scanner session expired — re-authenticating")
        session.login(os.getenv("FORUM_USERNAME", ""), os.getenv("FORUM_PASSWORD", ""))
        html = session.get("search.php?do=getnew")

    html = _follow_meta_refresh(session, html)
    posts = parse_posts_page(html)
    return [p for p in posts if p["forum_id"] not in _EXCLUDED_FORUM_IDS]


def parse_post_date(date_str: str) -> datetime | None:
    """Parse VBulletin date 'DD-MM-YYYY, HH:MM' to timezone-aware datetime (GMT+2)."""
    try:
        dt = datetime.strptime(date_str.strip(), "%d-%m-%Y, %H:%M")
        return dt.replace(tzinfo=timezone(timedelta(hours=2)))
    except (ValueError, AttributeError):
        return None
