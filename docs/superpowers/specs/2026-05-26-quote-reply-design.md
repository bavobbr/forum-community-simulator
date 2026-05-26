# Quote-Reply Feature Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a real forum user quotes one of our alter egos, that alter replies back with a VBulletin quote block prepended to the LLM-generated reply.

**Architecture:** Enrich each post dict with a `quoted_alters` set before gate evaluation. Gates uses this to bypass topic-weight/random checks and give the quoted alter max priority. `_poll_once` detects the flag when building the LLM prompt and constructing the final reply text.

**Tech Stack:** Python, existing gates/generator/event pipeline.

---

## Detection

A new function `detect_quoted_alters(post, profiles)` in `src/event/gates.py`:

- Builds the set of all reversed usernames from `profiles` (to identify alter-to-alter situations).
- If `post["author"]` is itself an alter (reversed username in that set), returns `set()` immediately — no alter-to-alter replies.
- Otherwise scans `post["content"]` case-insensitively for `"Originally Posted by {profile.reversed_username}"` for each profile.
- Returns the set of reversed usernames that were quoted.

Called in `_poll_once` in `event.py` before `gates.evaluate_post`. Result written to `post["quoted_alters"]`.

## Gate changes

Inside `evaluate_post`, restructure the per-profile loop so the quote check sets `weight = 1.0` and skips topic/random checks, but **falls through** to the existing rate-cap block at the bottom of the loop (which currently lives between the random roll and `passed.append`):

```python
if profile.reversed_username in post.get("quoted_alters", set()):
    weight = 1.0
    # fall through to rate-cap check — do NOT continue here
else:
    # existing mention / tag_match / topic_weight / random roll logic
    ...

# rate-cap check applies to everyone, including quote bypass
hourly = db.get_hourly_count(...)
if hourly >= profile.hourly_cap ...:
    continue

passed.append((profile, weight))
```

Being quoted guarantees max weight and bypasses the relevance gate; it does not bypass the alter's own hourly/daily posting limits.

## Generation & reply construction

In `_poll_once`, when processing a selected candidate where `profile.reversed_username in post["quoted_alters"]`:

**Prompt**: call `event_generator.generate_quote_reply(profile, triggering_post)` — no thread context, different framing:

> "Iemand heeft jou geciteerd en reageert direct op jou. Reageer terug op dit specifieke bericht:"

A new function in `src/event/generator.py` only — the workbench does not need this. It calls `build_system_prompt` from `src/persona/generator.py`, which is already imported. Signature:

```python
def generate_quote_reply(profile: PersonaProfile, triggering_post: dict) -> str
```

**Quote block**: after the LLM returns reply text, code prepends:

```
[QUOTE={post["author"]};{post["post_id"]}]{post["content"]}[/QUOTE]\n
```

The LLM never sees or generates the quote tag. The final reply stored in `pending_replies` is `quote_block + llm_reply`.

## Loop prevention

- Alter-to-alter: blocked in `detect_quoted_alters` — if `post["author"]` is a reversed username, returns `set()`.
- Real-user back-and-forth: left to existing `hourly_cap` / `daily_cap` per alter.

## Files changed

- `src/event/gates.py` — add `detect_quoted_alters`; update `evaluate_post` with quote bypass
- `src/event/gates.py` — add `detect_quoted_alters`; restructure `evaluate_post` loop with quote bypass
- `src/event/generator.py` — add `generate_quote_reply`
- `src/persona/generator.py` — no changes
- `event.py` — call `detect_quoted_alters` per post; route quote candidates through `generate_quote_reply` and prepend quote block
- `tests/event/test_gates.py` — tests for `detect_quoted_alters` and the gate bypass
- `tests/event/test_generator.py` — test for `generate_quote_reply` (mock LLM, verify prompt contains the framing and no context lines)
