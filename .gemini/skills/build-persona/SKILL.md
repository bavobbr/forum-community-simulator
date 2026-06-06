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
4. **Important for extending profiles**: If the scratch file `<appDataDir>\brain\<conversation-id>/scratch/{username}_raw.json` already exists, read it first using `view_file`. Combine your newly fetched posts with the existing `posts` array.
5. Write the final JSON object back to the scratch file containing the combined `posts` array and the new `oldest_post_ts`.
6. Send a message to the orchestrator confirming completion and exit.

### PersonaAnalyzer
Use `define_subagent` to create this agent with `enable_mcp_tools=True`:
**System Prompt:**
You are the PersonaAnalyzer subagent. You will receive the target username and an absolute path to a scratch JSON file.
1. Call the `format_persona_prompt` MCP tool (on the `forum-community-simulator` server) with the target username and the scratch file path. This tool will extract the raw posts and return a perfectly formatted Dutch prompt.
2. Pass that formatted prompt string exactly as received into your internal model to generate the Persona JSON profile.
3. Use `view_file` to quickly read the `oldest_post_ts` integer from the scratch JSON file.
4. Make sure to embed the `oldest_post_ts` integer into the root of the generated Persona JSON profile.
5. Send the complete JSON string back to the orchestrator via `send_message` and exit.
## 2. Orchestration Workflow (Your Job)
1. **Invoke DataCollector**: Provide it the target username and post limit (default 1000 unless specified). Tell it exactly where to save the scratch file (`<appDataDir>\brain\<conversation-id>/scratch/{username}_raw.json`). Stop calling tools and wait for its completion message.
2. **Invoke PersonaAnalyzer**: Once the collector finishes, invoke the analyzer and give it the absolute path to the raw scratch file. Stop calling tools and wait for its response.
3. **Present & Save**: When you receive the final JSON from the analyzer, summarize the linguistic and behavioral findings for the user. Ask the user for confirmation.
4. **Commit**: If the user approves, write the LLM's JSON payload to a temporary file `<appDataDir>\brain\<conversation-id>/scratch/{username}_llm.json`. Then, call the `save_approved_persona` MCP tool, providing the username, the LLM file path, and the raw posts file path.
5. **Handle Missing Identity**: If the MCP tool returns an error saying the user was not found in `approved_accounts.json`, ask the user to provide the `user_id`, `reversed_username`, `post_count`, and `last_active`. Once they provide them, call the tool again with those arguments.
