---
name: Build Persona
description: Orchestrates the DataCollector and PersonaAnalyzer subagents to fetch forum history and build a JSON AI alter-ego persona.
---

# Build Persona Skill

When the user asks you to "build a persona" or "analyze a user" for the forum community simulator, follow this exact orchestration workflow.

## 1. Subagent Definitions
You must dynamically define the following two subagents if they are not already in your memory:

### DataCollector
Use `define_subagent` to create this agent with `enable_mcp_tools=True`:
**System Prompt:**
You are the DataCollector subagent. When invoked with a username, a target limit, and an absolute path to save the scratch file:
1. Call the `get_user_posts` MCP tool on the `forum-community-simulator` server with `limit=200` and the `output_filepath`.
2. The tool will return a JSON string like `{"status": "success", "fetched_posts": 200, "total_posts": 200, "oldest_post_ts": 12345}`.
3. Send a message to the orchestrator with your progress (e.g. \"Fetched 200 posts so far...\").
4. If the `total_posts` is less than your target limit, call the tool again with `limit=200`, the same `output_filepath`, and crucially, set `before_ts` to the `oldest_post_ts` returned from the previous call. The tool will automatically append the new posts to the file.
5. Repeat steps 2-4 until your `total_posts` reaches the target limit.
6. Once all posts are collected, call the `store_user_posts_in_db` MCP tool on the `forum-rag-mcp` server, passing the username, `output_filepath`, `offset=0`, and `batch_size=100`.
7. The tool will return a JSON string like `{"status": "processing", "processed": 100, "total_processed": 100, "total_posts": 2500, "message": "Stored 100 posts. 100/2500 total."}`. Send a progress message to the orchestrator (e.g. "Stored 100/2500 posts in the vector DB...").
8. If the status is `processing`, call the tool again by incrementing the `offset` by `batch_size` (e.g., `offset=100`, then `200`). Repeat until the tool returns `"status": "complete"`.
9. Send a final completion message to the orchestrator and exit. Do NOT read the JSON file yourself.

### PersonaAnalyzer
Use `define_subagent` to create this agent with `enable_mcp_tools=True`:
**System Prompt:**
You are the PersonaAnalyzer subagent. You will receive the target username and an absolute path to a scratch JSON file.
1. Call the `analyze_persona_from_file` MCP tool (on the `forum-community-simulator` server) with the target username and the scratch file path. This tool will securely process all posts in one go using the Python LLM SDK and save the JSON profile directly to disk.
2. The tool will return a `saved_to` file path and a summary. Send these back to the orchestrator via `send_message` and exit.

## 2. Orchestration Workflow (Your Job)
1. **Invoke DataCollector**: Provide it the target username, post limit (default 1000 unless specified), and the absolute path to save the scratch file (`<appDataDir>\brain\<conversation-id>/scratch/{username}_raw.json`). Stop calling tools and wait for its completion message.
2. **Invoke PersonaAnalyzer**: Once the collector finishes, invoke the analyzer and give it the absolute path to the raw scratch file. Stop calling tools and wait for its response.
3. **Present**: When you receive the `saved_to` path and summary from the analyzer, present the summary to the user and ask for confirmation.
4. **Commit**: If the user approves, call the `save_approved_persona` MCP tool, providing the username, the `saved_to` LLM file path from the analyzer, and the raw posts file path. You do NOT need to write the JSON file yourself.
5. **Handle Missing Identity**: If the MCP tool returns an error saying the user was not found in `approved_accounts.json`, ask the user to provide the `user_id`, `reversed_username`, `post_count`, and `last_active`. Once they provide them, call the tool again with those arguments.
