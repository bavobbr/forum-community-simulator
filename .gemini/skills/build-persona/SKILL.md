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
2. Analyze the posts and generate a comprehensive Persona JSON object based on this EXACT schema:
```json
{
  "oldest_post_ts": <integer timestamp you read from the scratch file>,
  "dialect_markers": ["lijst van typische dialect-/spreektaalwoorden die deze gebruiker gebruikt"],
  "formality": "very_casual | casual | formal",
  "sentence_length": "short | medium | long",
  "bbcode_habits": ["quote", "bold", "url", ...],
  "punctuation_style": "korte beschrijving van interpunctie en hoofdlettergebruik",
  "topic_weights": {"forumnaam": gewicht_0_tot_1, ...},
  "opinion_fingerprint": ["typisch standpunt 1", "typisch standpunt 2", ...],
  "frequent_interactions": {"username": "ally | rival | neutral", ...},
  "peak_hours": [18, 19, 20],
  "typical_post_length": gemiddeld_aantal_woorden_per_bericht_als_int,
  "daily_cap": gemiddeld_posts_per_dag_als_int,
  "hourly_cap": max_posts_per_uur_als_int,
  "persona_summary": "Uitgebreide beschrijving van de persoonlijkheid in 6-10 zinnen",
  "worldview": "Beschrijving in 3-5 zinnen van hoe deze persoon de wereld ziet",
  "rhetorical_patterns": ["Patroon 1", "Patroon 2"],
  "interest_tags": ["10-15 specifieke concrete onderwerpen"]
}
```
3. Be sure to limit `opinion_fingerprint` to max 25 items. Make them concrete and usable as debate points.
4. Send the complete JSON string back to the orchestrator via `send_message` and exit.

## 2. Orchestration Workflow (Your Job)
1. **Invoke DataCollector**: Provide it the target username and post limit (default 1000 unless specified). Tell it exactly where to save the scratch file. Stop calling tools and wait for its completion message.
2. **Invoke PersonaAnalyzer**: Once the collector finishes, invoke the analyzer and give it the absolute path to the scratch file. Stop calling tools and wait for its response.
3. **Present & Save**: When you receive the final JSON from the analyzer, summarize the linguistic and behavioral findings for the user. Ask the user for confirmation.
4. **Commit**: If the user approves, write the exact JSON payload to `agent_personas/{username}.json` in the workspace.
