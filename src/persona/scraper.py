import calendar
import re
import time
from datetime import datetime
from bs4 import BeautifulSoup
from src.session import VBulletinSession

_POST_ID_PATTERN = re.compile(r"^post(\d+)$")
_FORUM_ID_PATTERN = re.compile(r"f=(\d+)")
_THREAD_ID_PATTERN = re.compile(r"t=(\d+)")
_DATE_PATTERN = re.compile(r"\b(\d{2}-\d{2}-\d{4}),\s*(\d{2}:\d{2})\b")
_SEARCH_ID_PATTERN = re.compile(r"searchid=(\d+)")

# Belgium is UTC+1/+2 (CET/CEST). VBulletin stores UTC datelines but displays
# local time. We parse displayed times as UTC and subtract this buffer to ensure
# date-window boundaries always overlap rather than miss posts.
_TZ_BUFFER_SECONDS = 7200


def parse_post_date_timestamp(date_str: str) -> int | None:
    """Parse 'DD-MM-YYYY, HH:MM' (forum local time) to a Unix timestamp.

    Treats the displayed time as UTC as a pragmatic approximation; callers
    should apply _TZ_BUFFER_SECONDS to the result when using it as a
    VBulletin date-window lower bound.
    """
    try:
        dt = datetime.strptime(date_str, "%d-%m-%Y, %H:%M")
        return int(calendar.timegm(dt.timetuple()))
    except (ValueError, AttributeError):
        return None


def parse_posts_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    posts = []

    for table in soup.find_all("table", id=_POST_ID_PATTERN):
        post_id_match = _POST_ID_PATTERN.match(table["id"])
        post_id = int(post_id_match.group(1))

        thead = table.find("td", class_="thead")
        if not thead:
            continue

        forum_link = thead.find("a", href=_FORUM_ID_PATTERN)
        forum_name = forum_link.get_text(strip=True) if forum_link else ""
        forum_id_match = _FORUM_ID_PATTERN.search(forum_link["href"]) if forum_link else None
        forum_id = int(forum_id_match.group(1)) if forum_id_match else 0

        thead_text = thead.get_text(separator=" ", strip=True)
        date_match = _DATE_PATTERN.search(thead_text)
        post_date = f"{date_match.group(1)}, {date_match.group(2)}" if date_match else ""

        alt1 = table.find("td", class_="alt1")
        if not alt1:
            continue

        thread_link = alt1.find("a", href=_THREAD_ID_PATTERN)
        thread_title = ""
        thread_id = 0
        if thread_link:
            strong = thread_link.find("strong")
            thread_title = strong.get_text(strip=True) if strong else thread_link.get_text(strip=True)
            tid_match = _THREAD_ID_PATTERN.search(thread_link["href"])
            thread_id = int(tid_match.group(1)) if tid_match else 0

        content = ""
        quoted_users: list[str] = []
        content_div = alt1.find("div", class_="alt2")
        if content_div:
            em = content_div.find("em")
            if em:
                post_link = em.find("a")
                if post_link:
                    post_link.decompose()
                for quote_div in em.find_all("div", class_="quote"):
                    thead = quote_div.find("div", class_="thead")
                    if thead:
                        name_tag = thead.find("strong")
                        if name_tag:
                            quoted_users.append(name_tag.get_text(strip=True))
                    quote_div.decompose()
                content = em.get_text(separator=" ", strip=True)

        posts.append({
            "post_id": post_id,
            "thread_id": thread_id,
            "thread_title": thread_title,
            "forum_id": forum_id,
            "forum_name": forum_name,
            "date": post_date,
            "content": content,
            "quoted_users": quoted_users,
        })

    return posts


def parse_search_id(html: str) -> str | None:
    match = _SEARCH_ID_PATTERN.search(html)
    return match.group(1) if match else None


def parse_has_next_page(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    return bool(soup.find("a", title=re.compile(r"Next Page", re.IGNORECASE)))


class PostScraper:
    def __init__(self, session: VBulletinSession, delay: int = 6):
        self.session = session
        self.delay = delay
        self._search_ids: dict[int, str] = {}

    def _ensure_search_id(self, user_id: int) -> str:
        """Initialise search for user if not cached, return searchid."""
        if user_id not in self._search_ids:
            time.sleep(self.delay)
            html = self.session.get(f"search.php?do=finduser&u={user_id}&pp=100")
            search_id = parse_search_id(html)
            if not search_id:
                raise ValueError(f"No searchid for user {user_id} — user may have no posts")
            self._search_ids[user_id] = search_id
        return self._search_ids[user_id]

    def fetch_batch(self, user_id: int, page: int = 1) -> tuple[list[dict], bool]:
        """Fetch one page (100 posts) of a user's post history. Returns (posts, has_more_pages)."""
        search_id = self._ensure_search_id(user_id)
        time.sleep(self.delay)
        html = self.session.get(f"search.php?searchid={search_id}&pp=100&page={page}")
        posts = parse_posts_page(html)
        has_more = parse_has_next_page(html)
        return posts, has_more

    def _search_advanced(self, username: str, before_ts: int | None = None) -> str:
        """POST an advanced search for a user's posts (newest first).

        before_ts is a Unix timestamp upper bound: only posts older than this
        date are returned. None means no upper bound (start from the newest).

        Field names match the actual VBulletin 3.7 form submission:
          searchdate = number of days (not a Unix timestamp)
          beforeafter = "before" → posts older than searchdate days
          sortby = "lastpost" (not "dateline")

        Returns the searchid string. Raises ValueError if none is returned.
        """
        data: dict[str, str] = {
            "do": "process",
            "searchthreadid": "",
            "query": "",
            "titleonly": "0",
            "searchuser": username,
            "starteronly": "0",
            "exactname": "1",
            "prefixchoice[]": "",
            "replyless": "0",
            "replylimit": "0",
            "sortby": "lastpost",
            "order": "descending",
            "showposts": "1",
            "forumchoice[]": "0",
            "childforums": "1",
            "dosearch": "Search Now",
            "securitytoken": self.session.security_token,
        }
        if before_ts is not None:
            # Overlap by 1 day to avoid missing posts at the day boundary.
            days_ago = max(1, (int(time.time()) - before_ts) // 86400 - 1)
            data["searchdate"] = str(days_ago)
            data["beforeafter"] = "before"

        time.sleep(self.delay)
        html = self.session.post("search.php", data=data)
        search_id = parse_search_id(html)
        if not search_id:
            raise ValueError(
                f"No searchid returned from advanced search for {username!r}"
            )
        return search_id

    def fetch_window(
        self,
        username: str,
        before_ts: int | None = None,
    ) -> tuple[list[dict], int | None]:
        """Fetch one batch of ~200 posts (newest first within the window).

        before_ts: Unix timestamp upper bound — only posts older than this are
        returned. Pass None to get the most recent posts with no upper bound.

        Returns (posts, oldest_ts) where oldest_ts is the Unix timestamp of the
        oldest post in this batch (use as before_ts for the next call), or None
        if no posts were returned.
        """
        search_id = self._search_advanced(username, before_ts=before_ts)

        posts: list[dict] = []
        for page in range(1, 100):
            time.sleep(self.delay)
            html = self.session.get(
                f"search.php?searchid={search_id}&pp=100&page={page}"
            )
            batch = parse_posts_page(html)
            posts.extend(batch)
            if not batch or not parse_has_next_page(html):
                break

        if not posts:
            return [], None

        oldest = min(posts, key=lambda p: p["post_id"])
        ts = parse_post_date_timestamp(oldest["date"])
        oldest_ts = (ts - _TZ_BUFFER_SECONDS) if ts is not None else None

        return posts, oldest_ts
