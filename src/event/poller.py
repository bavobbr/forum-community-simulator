import os
import logging
from datetime import datetime, timezone, timedelta

from src.persona.scraper import parse_posts_page

_EXCLUDED_FORUM_IDS = {20, 29, 40, 42}


def fetch_new_posts(session) -> list[dict]:
    """Fetch new posts since last visit. Re-authenticates if session expired."""
    html = session.get("search.php?do=getnew")

    if "Log Out" not in html and "User CP" not in html:
        logging.info("Scanner session expired — re-authenticating")
        session.login(os.getenv("FORUM_USERNAME", ""), os.getenv("FORUM_PASSWORD", ""))
        html = session.get("search.php?do=getnew")

    posts = parse_posts_page(html)
    return [p for p in posts if p["forum_id"] not in _EXCLUDED_FORUM_IDS]


def parse_post_date(date_str: str) -> datetime | None:
    """Parse VBulletin date 'DD-MM-YYYY, HH:MM' to timezone-aware datetime (GMT+2)."""
    try:
        dt = datetime.strptime(date_str.strip(), "%d-%m-%Y, %H:%M")
        return dt.replace(tzinfo=timezone(timedelta(hours=2)))
    except (ValueError, AttributeError):
        return None
