import os
import json
import time
from mcp.server.fastmcp import FastMCP, Context
from dotenv import load_dotenv

from src.session import VBulletinSession
from src.persona.scraper import PostScraper
from src.event.poller import fetch_new_posts
from src.event.thread_scraper import fetch_thread_context
from src.event.poster import post_reply as _post_reply
from src.scraper.memberlist import parse_memberlist
from src.scraper.profile import parse_last_active
from src.persona.analyzer import _format_posts, _SCHEMA_DESCRIPTION, _apply_analysis, _select_examples
from src.persona.models import PersonaProfile

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
def get_user_posts(username: str, limit: int = 100, before_ts: int | None = None, output_filepath: str | None = None, ctx: Context = None) -> str:
    """Fetch recent forum posts by a specific user.
    
    Args:
        username: The forum username to search for.
        limit: Number of posts to return (default 100).
        before_ts: Optional Unix timestamp upper bound (only fetch posts older than this).
        output_filepath: Optional absolute path to save the JSON output directly to disk.
    """
    session = get_session()
    
    log_filename = f"scrape_{username}_{int(time.time())}.log"
    
    def on_progress(post_id: int, current: int, total: int):
        if ctx and (current % 25 == 0 or current == total):
            ctx.info(f"Scraping {username}: {current}/{total} full posts fetched...")
            if hasattr(ctx, "report_progress"):
                ctx.report_progress(current, total)
        
        try:
            with open(log_filename, "a", encoding="utf-8") as f:
                f.write(f"Read post_id: {post_id}\n")
        except Exception:
            pass
                
    scraper = PostScraper(session, delay=6, progress_cb=on_progress)
    
    all_posts = []
    current_before_ts = before_ts
    
    while len(all_posts) < limit:
        window_posts, oldest_ts = scraper.fetch_window(username, before_ts=current_before_ts)
        if not window_posts:
            break
            
        all_posts.extend(window_posts)
        current_before_ts = oldest_ts
        
        if oldest_ts is None:
            break
            
    all_posts = all_posts[:limit]
    
    if output_filepath:
        import os
        
        existing_posts = []
        if os.path.exists(output_filepath):
            try:
                with open(output_filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    existing_posts = data.get("posts", []) if isinstance(data, dict) else data
            except Exception:
                pass
                
        combined_posts = existing_posts + all_posts
        
        final_obj = {
            "posts": combined_posts,
            "oldest_post_ts": current_before_ts
        }
        
        os.makedirs(os.path.dirname(output_filepath) or ".", exist_ok=True)
        
        json_str = json.dumps(final_obj, ensure_ascii=False, indent=2)
        clean_str = json_str.encode('utf-8', 'replace').decode('utf-8')
        with open(output_filepath, 'w', encoding='utf-8') as f:
            f.write(clean_str)
            
        return json.dumps({
            "status": "success",
            "fetched_posts": len(all_posts),
            "total_posts": len(combined_posts),
            "oldest_post_ts": current_before_ts,
            "saved_to": output_filepath
        })
    else:
        return json.dumps({
            "posts": all_posts,
            "oldest_post_ts": current_before_ts
        })


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
def analyze_persona_from_file(username: str, filepath: str) -> str:
    """Reads a scratch JSON file of posts and builds the AI persona using the internal Python LLM SDK.
    
    Args:
        username: The forum username being analyzed.
        filepath: Absolute path to the scratch JSON file containing the raw posts.
    """
    from src.persona.analyzer import analyze_first_batch
    import json
    from pathlib import Path
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    posts = data.get("posts", []) if isinstance(data, dict) else data
    
    alter = None
    approved_accounts_path = Path("config/approved_accounts.json")
    if approved_accounts_path.exists():
        try:
            with open(approved_accounts_path, 'r', encoding='utf-8') as f:
                accounts = json.load(f)
                for a in accounts:
                    if a.get("original_username", "").lower() == username.lower():
                        alter = a
                        break
        except Exception:
            pass
            
    if not alter:
        alter = {
            "user_id": 0,
            "original_username": username,
            "reversed_username": username[::-1],
            "post_count": len(posts),
            "last_active": ""
        }
        
    # Analyze ALL posts in one single batch (utilizing the large context window of Gemini 1.5 Pro)
    profile = analyze_first_batch(alter, posts)
    
    out_path = filepath.replace("_raw.json", "_llm.json")
    if "_raw.json" not in filepath:
        out_path = filepath + ".llm.json"
        
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2))
    
    return json.dumps({
        "status": "success",
        "saved_to": out_path,
        "persona_summary": profile.persona_summary
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def save_approved_persona(username: str, llm_file: str, raw_posts_file: str, user_id: int | None = None, reversed_username: str | None = None, post_count: int | None = None, last_active: str | None = None) -> str:
    """Hydrates an LLM persona profile with identity fields and saves it to the agent_personas/ folder.
    
    Args:
        username: The forum username being analyzed.
        llm_file: Absolute path to the JSON file generated by the PersonaAnalyzer subagent.
        raw_posts_file: Absolute path to the raw posts JSON file from DataCollector.
        user_id: Optional. The user's numeric forum ID.
        reversed_username: Optional. The reversed version of the username.
        post_count: Optional. The user's total post count.
        last_active: Optional. The user's last active date as an ISO string.
    """
    import re
    from pathlib import Path
    
    alter = None
    approved_accounts_path = Path("config/approved_accounts.json")
    if approved_accounts_path.exists():
        try:
            with open(approved_accounts_path, 'r', encoding='utf-8') as f:
                accounts = json.load(f)
                for a in accounts:
                    if a.get("original_username", "").lower() == username.lower():
                        alter = a
                        break
        except Exception:
            pass
            
    if not alter:
        if user_id is None or reversed_username is None or post_count is None or last_active is None:
            return (f"Error: User '{username}' not found in config/approved_accounts.json. "
                    f"Please ask the user to provide user_id, reversed_username, post_count, and last_active, "
                    f"and call this tool again with those arguments.")
        alter = {
            "user_id": user_id,
            "original_username": username,
            "reversed_username": reversed_username,
            "post_count": post_count,
            "last_active": last_active
        }
        
    profile = PersonaProfile.from_alter_ego(alter)
    
    with open(llm_file, 'r', encoding='utf-8') as f:
        llm_data = json.load(f)
        
    _apply_analysis(profile, llm_data)
    
    with open(raw_posts_file, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
        
    posts = raw_data.get("posts", []) if isinstance(raw_data, dict) else raw_data
    oldest_ts = raw_data.get("oldest_post_ts", 0) if isinstance(raw_data, dict) else 0
    
    profile.posts_analyzed = len(posts)
    profile.pages_loaded = 1
    profile.oldest_post_ts = oldest_ts
    profile.example_posts = _select_examples(posts)
    profile.is_approved = True
    
    save_dir = Path(os.getenv("PERSONAS_DIR", "agent_personas"))
    save_dir.mkdir(exist_ok=True)
    
    safe_name = re.sub(r'[^\w\-]', '_', username)
    save_path = save_dir / f"{safe_name}.json"
    
    json_str = json.dumps(profile.to_dict(), ensure_ascii=False, indent=2)
    clean_str = json_str.encode('utf-8', 'replace').decode('utf-8')
    with open(save_path, 'w', encoding='utf-8') as f:
        f.write(clean_str)
        
    return f"Success: Fully hydrated persona saved to {save_path}"


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


@mcp.tool()
def simulate_chat_turn(username: str, message: str, rag_context: list | str | None = None, ctx: Context = None) -> str:
    """Simulates a chat turn by generating a reply as the persona.
    
    CRITICAL INSTRUCTION FOR AI AGENTS: 
    Do NOT call this tool directly without first calling `search_user_posts` from `forum-rag-mcp` to get historical context. 
    You MUST pass the raw JSON string output from `search_user_posts` into the `rag_context` argument.
    
    Args:
        username: The forum username of the persona.
        message: The chat message from the user.
        rag_context: REQUIRED historical posts retrieved from RAG. Can be a JSON string or parsed list.
    """
    import json
    import re
    import logging
    from pathlib import Path
    from src.persona.models import PersonaProfile
    from src.persona.generator import generate_chat_reply

    safe_name = re.sub(r'[^\w\-]', '_', username)
    profile_path = Path(os.getenv("PERSONAS_DIR", "agent_personas")) / f"{safe_name}.json"
    
    if not profile_path.exists():
        msg = f"Error: Persona profile not found at {profile_path}"
        if ctx: ctx.info(msg)
        return msg
        
    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        profile = PersonaProfile.from_dict(data)
    except Exception as e:
        msg = f"Error loading persona profile: {e}"
        if ctx: ctx.info(msg)
        return msg

    context_list = []
    if rag_context:
        if isinstance(rag_context, list):
            context_list = rag_context
        elif isinstance(rag_context, str):
            try:
                parsed = json.loads(rag_context)
                if isinstance(parsed, list):
                    context_list = parsed
                elif isinstance(parsed, dict) and "documents" in parsed:
                    context_list = [{"content": doc} for doc in parsed.get("documents", [])]
            except Exception as e:
                msg = f"Error parsing rag_context: {e}"
                if ctx: ctx.info(msg)
                return msg

    reply = generate_chat_reply(profile, message, rag_context=context_list)
    
    log_msg = (
        f"\n=== SIMULATE CHAT TURN ===\n"
        f"Username: {username}\n"
        f"Message: {message}\n"
        f"RAG Context Items: {len(context_list)}\n"
        f"Generated Reply: {reply}\n"
        f"==========================\n"
    )
    logging.info(log_msg)
    if ctx:
        ctx.info(log_msg)

    return reply



if __name__ == "__main__":
    mcp.run()
