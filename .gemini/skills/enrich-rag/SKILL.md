---
name: Enrich RAG
description: Orchestrates the DataCollector subagent to fetch historical forum posts and directly store them in the RAG vector database, paginating backwards from the oldest known post.
---

# Enrich RAG Skill

When the user asks you to "enrich the RAG database", "add more data for user X", or similar requests that indicate extending the historical context of a user without modifying their persona profile, follow this exact orchestration workflow.

## 1. Subagent Definition

You must dynamically define the `DataCollector` subagent if it is not already in your memory.

### DataCollector
Use `define_subagent` to create this agent with `enable_mcp_tools=True`:
**System Prompt:**
You are the DataCollector subagent. When invoked with a username, a target limit, an absolute path to save the scratch file, and an optional `initial_before_ts`:
1. Call the `get_user_posts` MCP tool on the `forum-community-simulator` server with `limit=200`, the `output_filepath`, and pass the `initial_before_ts` into the `before_ts` argument for your first call.
2. The tool will return a JSON string like `{"status": "success", "fetched_posts": 200, "total_posts": 200, "oldest_post_ts": 12345}`.
3. Send a message to the orchestrator with your progress (e.g. "Fetched 200 posts so far...").
4. If the `total_posts` is less than your target limit, call the tool again with `limit=200`, the same `output_filepath`, and set `before_ts` to the `oldest_post_ts` returned from the previous call. The tool will automatically append the new posts to the file.
5. Repeat steps 2-4 until your `total_posts` reaches the target limit.
6. Once all posts are collected, call the `store_user_posts_in_db` MCP tool on the `forum-rag-mcp` server, passing the username and the `output_filepath`.
7. Send a final completion message to the orchestrator and exit. Do NOT read the JSON file yourself.

## 2. Orchestration Workflow (Your Job)

1. **Find Starting Point**: Call the `get_user_oldest_post_ts` tool on the `forum-rag-mcp` server for the target username. Parse the returned JSON to extract the `oldest_post_ts`. If it returns an error that no posts are found, proceed with `initial_before_ts=None`.
2. **Invoke DataCollector**: Provide it the target username, post limit (default 1000 unless specified), the absolute path to save the scratch file (`<appDataDir>\brain\<conversation-id>/scratch/{username}_rag_raw.json`), and the `initial_before_ts` obtained from step 1.
3. **Wait & Notify**: Stop calling tools and wait for the `DataCollector`'s completion message. Once it finishes, inform the user that the RAG database has been successfully enriched. Do NOT invoke any persona analysis subagents and do NOT update the `agent_personas/` folder.
