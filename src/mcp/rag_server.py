import json
import os
import sys
import logging# Ensure the root directory is in sys.path so src module can be resolved 
# when this file is executed directly.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from dotenv import load_dotenv
load_dotenv()

from mcp.server.fastmcp import FastMCP, Context
from src.rag.db import store_posts, search_posts, drop_posts, get_user_post_counts, get_oldest_post_ts
from src.mcp.trace import trace_tool

mcp = FastMCP("Forum RAG MCP")

log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../logs'))
os.makedirs(log_dir, exist_ok=True)
file_handler = logging.FileHandler(os.path.join(log_dir, "mcp_rag_server.log"))
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

logger = logging.getLogger("rag_server")
logger.setLevel(logging.INFO)
logger.handlers = []  # Clear any existing handlers
logger.addHandler(file_handler)
logger.propagate = False  # Prevent logs from bubbling up to root


@mcp.tool()
@trace_tool(logger)
def store_user_posts_in_db(username: str, filepath: str, offset: int = 0, batch_size: int = 100, ctx: Context = None) -> str:
    """Read a JSON file of scraped posts and index them into the vector database.
    
    Args:
        username: The forum username.
        filepath: Absolute path to the scratch JSON file containing the raw posts.
        offset: The starting index to process. Default is 0.
        batch_size: Number of posts to process in this batch. Default is 100. Set to -1 to process all remaining posts.
    """
    try:
        logger.info(f"store_user_posts_in_db called for {username} (filepath: {filepath}, offset: {offset}, batch_size: {batch_size})")
        if ctx:
            ctx.info(f"Reading file {filepath} (offset {offset}, batch_size {batch_size})...")
            
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        posts = data.get("posts", []) if isinstance(data, dict) else data
        
        if not posts:
            return json.dumps({"status": "error", "message": f"No posts found in {filepath}"})
            
        total_posts = len(posts)
        if batch_size == -1:
            batch_size = total_posts - offset
            
        chunk = posts[offset : offset + batch_size]
        
        if not chunk:
            return json.dumps({
                "status": "complete", 
                "processed": 0, 
                "total_processed": total_posts,
                "total_posts": total_posts, 
                "message": "All posts stored."
            })
            
        if ctx:
            ctx.info(f"Storing {len(chunk)} posts (from {offset} to {offset + len(chunk)})...")
        
        def progress(current, total):
            logger.info(f"[{username}] Embedded and stored {current}/{total} posts in current batch...")
            if ctx:
                ctx.report_progress(current, total)
            
        store_posts(username, chunk, progress_callback=progress)
        
        new_offset = offset + len(chunk)
        status = "complete" if new_offset >= total_posts else "processing"
        
        logger.info(f"store_user_posts_in_db finished batch for {username}. Status: {status}, Total processed: {new_offset}/{total_posts}")
        
        return json.dumps({
            "status": status,
            "processed": len(chunk),
            "total_processed": new_offset,
            "total_posts": total_posts,
            "message": f"Stored {len(chunk)} posts. {new_offset}/{total_posts} total."
        })
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

@mcp.tool()
@trace_tool(logger)
def search_user_posts(username: str, query: str, limit: int = 5) -> str:
    """Returns the most relevant historical posts for a user based on a semantic query.
    
    Args:
        username: The forum username.
        query: The topic or text to search for.
        limit: Number of posts to return (default 5).
    """
    try:
        results = search_posts(username, query, limit)
        return json.dumps(results, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
@trace_tool(logger)
def drop_user_posts(username: str) -> str:
    """Drop all stored posts for a user from the vector database.
    
    Args:
        username: The forum username.
    """
    try:
        drop_posts(username)
        return f"Successfully dropped posts for {username}."
    except Exception as e:
        return f"Error dropping posts: {str(e)}"

@mcp.tool()
@trace_tool(logger)
def get_user_doc_counts() -> str:
    """Return a dictionary mapping username to the number of posts stored in the vector database."""
    try:
        counts = get_user_post_counts()
        return json.dumps(counts, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
@trace_tool(logger)
def get_user_oldest_post_ts(username: str) -> str:
    """Return the timestamp of the oldest stored post for a user.
    
    Args:
        username: The forum username.
    """
    try:
        ts = get_oldest_post_ts(username)
        if ts is None:
            return json.dumps({"error": f"No posts found for {username} in the vector database."})
        return json.dumps({"oldest_post_ts": ts})
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
@trace_tool(logger)
def get_server_info() -> str:
    """Returns information about the running server, including the log file location."""
    import os
    return json.dumps({
        "log_file": os.path.abspath(os.path.join(os.path.dirname(__file__), '../../logs/mcp_rag_server.log')),
        "status": "running"
    })

if __name__ == "__main__":
    mcp.run()
