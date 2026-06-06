# MCP Server Integration

This directory contains a standalone **Model Context Protocol (MCP)** server that exposes the underlying forum scraping and posting logic as a semantic API.

This allows any external LLM-powered agent (e.g., Claude Desktop, Cursor, etc.) to safely interact with the vBulletin 3.7 forum without needing to understand the underlying web scraping mechanics, password hashing, or pagination limits.

## Setup & Configuration

Ensure your `.env` file is present in the root of the repository. The MCP server will automatically load the credentials from `.env` on startup via `load_dotenv()`.

Required variables:
- `FORUM_USERNAME` (scanning account)
- `FORUM_PASSWORD`

## Running the Server

To connect the server to an MCP-compatible client like Claude Desktop, add the following to your MCP configuration JSON (adjust paths according to your environment):

```json
"mcpServers": {
  "forum-simulator": {
    "command": "python",
    "args": [
      "-m",
      "src.mcp.server"
    ],
    "cwd": "/path/to/forum-community-simulator"
  }
}
```

## Available Tools (Mutations / Parameterized Queries)

- **`get_user_posts(username, limit, before_ts)`**: Uses advanced search to fetch historical posts for a given user. Handles pagination and limit capping automatically.
- **`format_persona_prompt(username, filepath)`**: Reads a scratch JSON file of raw posts and builds the highly constrained, pre-formatted Dutch prompt string required for Persona analysis.
- **`save_approved_persona(username, llm_file, raw_posts_file, ...)`**: Hydrates an LLM-generated behavioral profile with explicit identity fields from `approved_accounts.json` and automatically-selected example posts, saving the final payload to `agent_personas/`.
- **`get_thread_context(post_id, n)`**: Fetches the most recent posts inside a thread leading up to a specific post.
- **`get_daily_activity()`**: Uses `search.php?do=getdaily` to fetch the latest unread posts across the forum.
- **`post_reply(username, password, thread_id, message)`**: Authenticates as the provided alter-ego and posts a reply.

## Available Resources (Read-Only State)

- **`forum://memberlist/top100`**: Returns the top 100 members from the `memberlist.php` scraper.
- **`forum://user/{id}/last_active`**: Returns the last active date of a user using the profile scraper.
