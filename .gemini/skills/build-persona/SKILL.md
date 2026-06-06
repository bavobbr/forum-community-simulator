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
5. Repeat steps 2-4 until your `total_posts` reaches the target limit, then send a final completion message and exit. Do NOT read the JSON file yourself.

### PersonaAnalyzer
Use `define_subagent` to create this agent with `enable_mcp_tools=True`:
**System Prompt:**
You are the PersonaAnalyzer subagent. You will receive the target username and an absolute path to a scratch JSON file.
1. Call the `format_persona_prompt` MCP tool (on the `forum-community-simulator` server) with the target username and the scratch file path. This tool will extract the raw posts and return a perfectly formatted Dutch prompt.
2. Pass that formatted prompt string exactly as received into your internal model to generate the Persona JSON profile.
3. Send the complete JSON string back to the orchestrator via `send_message` and exit.

## 2. Orchestration Workflow (Your Job)
1. **Invoke DataCollector**: Provide it the target username, post limit (default 1000 unless specified), and the absolute path to save the scratch file (`<appDataDir>\brain\<conversation-id>/scratch/{username}_raw.json`). Stop calling tools and wait for its completion message.
2. **Invoke PersonaAnalyzer**: Once the collector finishes, invoke the analyzer and give it the absolute path to the raw scratch file. Stop calling tools and wait for its response.
3. **Present & Save**: When you receive the final JSON from the analyzer, summarize the linguistic and behavioral findings for the user. Ask the user for confirmation.
4. **Commit**: If the user approves, write the LLM's JSON payload to a temporary file `<appDataDir>\brain\<conversation-id>/scratch/{username}_llm.json`. Then, call the `save_approved_persona` MCP tool, providing the username, the LLM file path, and the raw posts file path.
5. **Handle Missing Identity**: If the MCP tool returns an error saying the user was not found in `approved_accounts.json`, ask the user to provide the `user_id`, `reversed_username`, `post_count`, and `last_active`. Once they provide them, call the tool again with those arguments.
