import os
import json
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

from src.session import VBulletinSession
from src.persona.scraper import PostScraper
from src.event.poller import fetch_new_posts
from src.event.thread_scraper import fetch_thread_context
from src.event.poster import post_reply as _post_reply
from src.scraper.memberlist import parse_memberlist
from src.scraper.profile import parse_last_active

load_dotenv()

mcp = FastMCP("Forum Simulator MCP")

_session = None


def get_session() -> VBulletinSession:
    """Singleton session bound to the scanner account."""
    global _session
    if _session is None:
        _session = VBulletinSession()
        username = os.getenv("FORUM_USERNAME")
        password = os.getenv("FORUM_PASSWORD")
        if not username or not password:
            raise RuntimeError("FORUM_USERNAME and FORUM_PASSWORD missing from .env")
        if not _session.login(username, password):
            raise RuntimeError("Failed to login to forum with scanner account")
    return _session


@mcp.tool()
def get_user_posts(username: str, limit: int = 100, before_ts: int | None = None) -> str:
    """Fetch recent forum posts by a specific user.
    
    Args:
        username: The forum username to search for.
        limit: Number of posts to return (default 100). Max 200 per VBulletin limits.
        before_ts: Optional Unix timestamp upper bound (only fetch posts older than this).
    """
    session = get_session()
    scraper = PostScraper(session, delay=6)
    
    posts, oldest_ts = scraper.fetch_window(username, before_ts=before_ts)
    return json.dumps(posts[:limit])


@mcp.tool()
def get_thread_context(post_id: int, n: int = 5) -> str:
    """Fetch the most recent posts inside a thread, leading up to a specific post.
    
    Args:
        post_id: The ID of the post to get context for.
        n: Number of preceding posts to include (default 5).
    """
    session = get_session()
    posts = fetch_thread_context(session, post_id, n=n)
    return json.dumps(posts)


@mcp.tool()
def get_daily_activity() -> str:
    """Fetch the latest posts and active threads across the entire forum from the last 24h."""
    session = get_session()
    posts = fetch_new_posts(session)
    return json.dumps(posts)


@mcp.tool()
def post_reply(username: str, password: str, thread_id: int, message: str) -> bool:
    """Post a reply to a thread acting as a specific forum member.
    
    Args:
        username: The username of the alter-ego to post as.
        password: The password for the alter-ego account.
        thread_id: The ID of the thread to reply to.
        message: The message body to post.
    """
    return _post_reply(username, password, thread_id, message)


@mcp.resource("forum://memberlist/top100")
def get_top_members() -> str:
    """Returns the top 100 members from the forum by post count."""
    session = get_session()
    html = session.get("memberlist.php?order=DESC&sort=posts&pp=100")
    members = parse_memberlist(html)
    return json.dumps([{"user_id": m.user_id, "username": m.username, "post_count": m.post_count, "last_active": m.last_active} for m in members])


@mcp.resource("forum://user/{user_id}/last_active")
def get_user_last_active(user_id: int) -> str:
    """Returns the last active date of a user."""
    session = get_session()
    html = session.get(f"search.php?do=finduser&u={user_id}")
    date = parse_last_active(html)
    date_str = date.isoformat() if hasattr(date, 'isoformat') else str(date)
    return json.dumps({"user_id": user_id, "last_active": date_str})


if __name__ == "__main__":
    mcp.run()
