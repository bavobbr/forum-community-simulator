# Sandbox Thread Mode — Design Spec

**Date:** 2026-05-31
**Status:** Approved

## Overview

A new operating mode for `event.py` where instead of scanning the whole forum via `getdaily`, the bot watches a fixed set of threads. Users interact directly with the alter egos in those threads. Sandbox mode and forum-wide mode are mutually exclusive.

## Configuration

Two new env vars:

```
SANDBOX_THREAD_IDS=23001,23002   # comma-separated; empty/absent = forum-wide mode
SANDBOX_REPLIES_PER_POST=3       # max random bot replies per unmentioned post (default 3)
```

`event.py` reads `SANDBOX_THREAD_IDS` at startup, splits and converts to `set[int]`. If non-empty, sandbox mode is active for the entire run. A restart is required to change the thread list.

`REPLIES_PER_CYCLE` is read but ignored in sandbox mode.

## Polling

New function in `src/event/poller.py`:

```python
def fetch_sandbox_posts(scanner: VBulletinSession, thread_ids: set[int]) -> list[dict]:
```

For each thread ID, fetches `showthread.php?goto=newpost&t={id}` and parses with the existing `parse_thread_page()`. Returns the same `list[dict]` format as `fetch_new_posts` — fields: `post_id`, `author`, `content`, `thread_id`, `thread_title`, `forum_id`, `forum_name`, `date`.

No `getdaily` call is made in sandbox mode.

## Evaluation — `src/event/sandbox_gates.py`

New module. Single public function:

```python
def evaluate_post_sandbox(
    post: dict,
    profiles: list[PersonaProfile],
    conn: sqlite3.Connection,
    replies_per_post: int = 3,
) -> list[tuple[PersonaProfile, float]]:
```

### Logic

1. **Author skip** — if `post["author"]` matches any `profile.reversed_username`, return `[]`.
2. **Rate cap filter** — build eligible pool: profiles that pass `_passes_rate_cap(profile, conn)`.
3. **Trigger detection** — for each eligible profile, check whether the post content contains:
   - `profile.reversed_username` or `profile.original_username` (case-insensitive text mention)
   - `[QUOTE=reversed_username` or `[QUOTE=original_username` (VBulletin BBCode quote tag)
4. **If triggered profiles found** — from the triggered profiles, keep only those that pass the rate cap. Return up to 3, sorted by order of appearance, each with `weight=1.0`. Cap of 3 prevents abuse when many bots are mentioned. A triggered-but-rate-capped bot is silently skipped.
5. **If no triggered profiles** — `random.sample(eligible, min(replies_per_post, len(eligible)))`, each with `weight=1.0`.

### Rate cap extraction

`gates.py` gets a new internal helper:

```python
def _passes_rate_cap(profile: PersonaProfile, conn: sqlite3.Connection) -> bool:
```

Extracted from the existing rate cap check in `evaluate_post`. Called by both `gates.py` and `sandbox_gates.py`. No logic change.

## Event loop changes (`event.py`)

`_poll_once` branches on mode:

```python
if sandbox_thread_ids:
    posts = poller.fetch_sandbox_posts(scanner, sandbox_thread_ids)
    for post in unseen_posts:
        candidates += sandbox_gates.evaluate_post_sandbox(post, profiles, conn, replies_per_post)
    # queue ALL candidates — no cycle cap
else:
    posts = poller.fetch_new_posts(scanner)
    # existing: gates.evaluate_post + REPLIES_PER_CYCLE cap
```

`LOOKBACK_HOURS` and `seen_posts` apply in both modes.

## `.env.example` additions

```
SANDBOX_THREAD_IDS=          # comma-separated thread IDs; empty = forum-wide mode
SANDBOX_REPLIES_PER_POST=3   # max random bot replies per unmentioned post
```

## Testing

- `tests/event/test_sandbox_gates.py`
  - author skip returns `[]`
  - text mention triggers correct profile
  - quote tag triggers correct profile
  - mention of 4 bots returns at most 3
  - no mention → random selection up to `replies_per_post`
  - rate-capped profile excluded from random pool
  - rate-capped profile excluded even if triggered
- `tests/event/test_poller.py`
  - `fetch_sandbox_posts` with HTML fixture returns correct post list
- Existing tests unchanged

## Out of scope

- Admin UI for managing sandbox threads
- Per-thread persona assignment
- Mixing sandbox and forum-wide mode simultaneously
