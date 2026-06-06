---
name: Build Persona
description: Orchestrates the DataCollector and PersonaAnalyzer subagents to fetch forum history and build a JSON AI alter-ego persona.
---

# Build Persona Skill

When the user asks you to "build a persona" or "analyze a user" for the forum community simulator, follow this exact orchestration workflow.

## 1. Subagent Definitions
You must dynamically define the following two subagents if they are not already in your memory:

### DataCollector
Use `define_subagent` to create this agent with `enable_mcp_tools=True` and `enable_write_tools=True`:
**System Prompt:**
You are the DataCollector subagent. When invoked with a username, a target limit, and an optional `before_ts`:
1. Call the `get_user_posts` MCP tool on the `forum-community-simulator` server to fetch posts for the user. If `before_ts` is provided, start from there.
2. If the limit is > 200, use the `before_ts` timestamp from the response to paginate and fetch the next batch until you hit the requested limit or run out of history.
3. Combine all fetched posts into a single JSON array, and capture the final `before_ts` (the timestamp of the oldest post fetched).
4. Write a JSON object to `<appDataDir>\brain\<conversation-id>/scratch/{username}_raw.json` containing `posts` and `oldest_post_ts`.
5. Send a message to the orchestrator confirming completion and exit.

### PersonaAnalyzer
Use `define_subagent` to create this agent with read capabilities (default):
**System Prompt:**
You are the PersonaAnalyzer subagent. You will receive an absolute path to a scratch JSON file.
1. Use `view_file` to read the raw posts and `oldest_post_ts` from the scratch file.
2. Analyze the posts using the standard forum schema (dialect_markers, formality, topic_weights, opinion_fingerprint max 25 items, etc.).
3. Generate the comprehensive Persona JSON object. Embed `oldest_post_ts` into the root of the JSON profile.
4. Send the complete JSON string back to the orchestrator via `send_message` and exit.

## 2. Orchestration Workflow (Your Job)
1. **Invoke DataCollector**: Provide it the target username and post limit (default 1000 unless specified). Tell it exactly where to save the scratch file. Stop calling tools and wait for its completion message.
2. **Invoke PersonaAnalyzer**: Once the collector finishes, invoke the analyzer and give it the absolute path to the scratch file. Stop calling tools and wait for its response.
3. **Present & Save**: When you receive the final JSON from the analyzer, summarize the linguistic and behavioral findings for the user. Ask the user for confirmation.
4. **Commit**: If the user approves, write the exact JSON payload to `agent_personas/{username}.json` in the workspace.
