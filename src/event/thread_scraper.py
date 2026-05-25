import re
import logging
from bs4 import BeautifulSoup, Tag

_POST_ID_RE = re.compile(r"^post(\d+)$")
_PAGE_LINK_RE = re.compile(r"page=\d+")


def _preprocess_content(tag: Tag) -> str:
    """Convert post_message div to plain text, handling smilies and images."""
    for img in tag.find_all("img"):
        src = img.get("src", "")
        title = img.get("title", "")
        alt = img.get("alt", "")
        if "smilies" in src:
            img.replace_with(f"({title})" if title else "")
        elif alt:
            img.replace_with(alt)
        else:
            img.replace_with("[afbeelding]")
    return tag.get_text(separator=" ", strip=True)


def parse_thread_page(html: str) -> list[dict]:
    """Parse posts from a showthread.php page."""
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    for table in soup.find_all("table", id=_POST_ID_RE):
        post_id = int(_POST_ID_RE.match(table["id"]).group(1))
        pm = table.find("div", id=f"postmenu_{post_id}")
        author_link = pm.find("a") if pm else None
        author = author_link.get_text(strip=True) if author_link else ""
        msg = table.find("div", id=f"post_message_{post_id}")
        content = _preprocess_content(msg) if msg else ""
        thead = table.find("td", class_="thead")
        date = thead.get_text(separator=" ", strip=True) if thead else ""
        posts.append({"post_id": post_id, "author": author, "content": content, "date": date})
    return posts


def _find_prev_page_url(html: str) -> str | None:
    """Return href of the previous-page pagination link (text '<')."""
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=_PAGE_LINK_RE):
        if a.get_text(strip=True) == "<":
            return a["href"]
    return None


def fetch_thread_context(session, post_id: int, n: int = 5) -> list[dict]:
    """Return up to n posts ending with post_id. Fetches previous page if needed."""
    html = session.get(f"showthread.php?p={post_id}")
    posts = parse_thread_page(html)
    ids = [p["post_id"] for p in posts]

    if post_id not in ids:
        logging.warning("post %d not found in thread page", post_id)
        return []

    idx = ids.index(post_id)

    if idx == 0:
        prev_url = _find_prev_page_url(html)
        if prev_url:
            prev_html = session.get(prev_url)
            prev_posts = parse_thread_page(prev_html)
            combined = prev_posts + [posts[0]]
            return combined[-n:]
        return [posts[0]]

    return posts[max(0, idx - (n - 1)):idx + 1]
