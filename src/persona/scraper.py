import re
import time
from bs4 import BeautifulSoup
from src.session import VBulletinSession

_POST_ID_PATTERN = re.compile(r"^post(\d+)$")
_FORUM_ID_PATTERN = re.compile(r"f=(\d+)")
_THREAD_ID_PATTERN = re.compile(r"t=(\d+)")
_DATE_PATTERN = re.compile(r"\b(\d{2}-\d{2}-\d{4}),\s*(\d{2}:\d{2})\b")
_SEARCH_ID_PATTERN = re.compile(r"searchid=(\d+)")


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
        content_div = alt1.find("div", class_="alt2")
        if content_div:
            em = content_div.find("em")
            if em:
                post_link = em.find("a")
                if post_link:
                    post_link.decompose()
                content = em.get_text(separator=" ", strip=True)

        posts.append({
            "post_id": post_id,
            "thread_id": thread_id,
            "thread_title": thread_title,
            "forum_id": forum_id,
            "forum_name": forum_name,
            "date": post_date,
            "content": content,
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

    def fetch_batch(self, user_id: int, page: int = 1) -> tuple[list[dict], bool]:
        """Fetch one page of posts. Returns (posts, has_more_pages).
        Page 1 initialises the search and caches the searchid for subsequent pages."""
        time.sleep(self.delay)

        if page == 1:
            html = self.session.get(f"search.php?do=finduser&u={user_id}&pp=100")
            search_id = parse_search_id(html)
            if not search_id:
                raise ValueError(f"No searchid in page 1 response for user {user_id} — user may have no posts")
            self._search_ids[user_id] = search_id
        else:
            search_id = self._search_ids.get(user_id)
            if not search_id:
                raise ValueError(f"No searchid for user {user_id}. Call page=1 first.")
            html = self.session.get(f"search.php?searchid={search_id}&pp=100&page={page}")

        posts = parse_posts_page(html)
        has_more = parse_has_next_page(html)
        return posts, has_more
