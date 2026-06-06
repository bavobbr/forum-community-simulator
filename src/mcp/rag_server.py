import json
from mcp.server.fastmcp import FastMCP
from src.rag.db import store_posts, search_posts, drop_posts, get_user_post_counts

mcp = FastMCP("Forum RAG MCP")

@mcp.tool()
def store_user_posts_in_db(username: str, filepath: str) -> str:
    """Read a JSON file of scraped posts and index them into the vector database.
    
    Args:
        username: The forum username.
        filepath: Absolute path to the scratch JSON file containing the raw posts.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        posts = data.get("posts", []) if isinstance(data, dict) else data
        
        if not posts:
            return f"Error: No posts found in {filepath}"
            
        store_posts(username, posts)
        return f"Successfully stored {len(posts)} posts for {username} in the vector database."
    except Exception as e:
        return f"Error storing posts: {str(e)}"

@mcp.tool()
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
def get_user_doc_counts() -> str:
    """Return a dictionary mapping username to the number of posts stored in the vector database."""
    try:
        counts = get_user_post_counts()
        return json.dumps(counts, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

if __name__ == "__main__":
    mcp.run()
