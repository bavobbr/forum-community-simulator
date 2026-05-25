# Event Orchestrator — Design Specification

**Date:** 2026-05-25
**Project:** Shrimp Resurrect — Plan 3
**Forum:** https://forum.shrimprefuge.be/ (VBulletin 3.7, Dutch-language)

---

## Overview

The Event Orchestrator is the live runtime for the 24-hour Shrimp Resurrect event. It polls the forum for new posts, decides which alter egos should respond using a multi-gate pipeline, generates replies via the Claude API, routes them through a review queue, and posts approved replies to the forum as the alter ego accounts.

---

## Architecture

Single Python process (`event.py`). Flask review UI runs in a background thread; the polling loop runs on the main thread. State persists in SQLite (`event.db`) so the process can be restarted without losing pending replies or rate limit counts.

```
event.py
  ├── Flask thread → src/event/webui.py     (review queue, localhost:5000)
  └── Polling loop
        ├── src/event/poller.py             (fetch new posts from forum)
        ├── src/event/gates.py              (decision pipeline)
        ├── src/event/thread_scraper.py     (fetch thread context)
        ├── src/event/generator.py          (LLM reply generation)
        ├── src/event/poster.py             (post reply to VBulletin)
        └── src/event/db.py                 (all SQLite queries)
```

---

## Configuration (`.env` additions)

```
ALTER_PASSWORD=...        # shared password for all 25 alter ego accounts
LIVE_MODE=false           # set to true to actually post replies
LOOKBACK_HOURS=48         # on startup, ignore posts older than this
POLL_INTERVAL=300         # seconds between polls (default: 5 minutes)
```

`LIVE_MODE=false` is the safe default. Nothing touches the forum until explicitly enabled.

---

## State — SQLite Schema

Four tables in `event.db` (gitignored):

```sql
CREATE TABLE seen_posts (
    post_id     INTEGER PRIMARY KEY,
    thread_id   INTEGER NOT NULL,
    forum_id    INTEGER NOT NULL,
    seen_at     TEXT NOT NULL        -- ISO datetime
);

CREATE TABLE pending_replies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id         INTEGER NOT NULL,
    thread_id       INTEGER NOT NULL,
    forum_id        INTEGER NOT NULL,
    alter_username  TEXT NOT NULL,
    reply_text      TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|discarded|failed
    auto_approve_at TEXT                              -- ISO datetime, NULL = manual only
);

CREATE TABLE posted_replies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    alter_username  TEXT NOT NULL,
    thread_id       INTEGER NOT NULL,
    post_id         INTEGER NOT NULL,
    reply_text      TEXT NOT NULL,
    posted_at       TEXT NOT NULL,
    simulated       INTEGER NOT NULL DEFAULT 0   -- 1 when LIVE_MODE=false
);

CREATE TABLE rate_counters (
    alter_username  TEXT NOT NULL,
    hour_key        TEXT NOT NULL,   -- e.g. "2026-05-25T14"
    day_key         TEXT NOT NULL,   -- e.g. "2026-05-25"
    hourly_count    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (alter_username, hour_key)
);
-- daily count = SELECT SUM(hourly_count) WHERE alter_username=? AND day_key=?
```

`seen_posts` is the deduplication guard — if the process restarts, already-processed post IDs are not re-evaluated.

---

## Polling

**Scanner account:** wokebot (existing, read-only forum account).

Every `POLL_INTERVAL` seconds, fetch `search.php?do=getnew`. VBulletin returns all posts since the session's last visit in the standard search results HTML format — the existing `parse_posts_page()` parser handles this without modification. Filter out excluded forum IDs (20, 29, 40, 42) and any `post_id` already in `seen_posts`.

**Session expiry:** wrap each `getnew` call in a re-auth check. If the response contains no "Log Out" indicator, re-login and retry once before failing.

**Startup behaviour:** on first run, split results by age against `now - LOOKBACK_HOURS`:
- Older than cutoff → insert into `seen_posts`, do not process
- Within cutoff → run through the decision pipeline normally

Default `LOOKBACK_HOURS=48` so alters wake up with 2 days of recent forum activity to react to.

---

## Decision Pipeline

Each new post is evaluated independently against every approved persona. Gates run in order; a skip at any gate means this (post, alter) pair produces no reply.

### Gate 1 — Forum exclusion
Skip if `forum_id` is in the excluded set: 20 (Shrimp Refuge HQ), 29 (Donations), 40 (Discretie), 42 (Forum Games).

### Gate 2 — Mention bypass
If the post text contains the alter's `reversed_username` (case-insensitive), skip gates 3 and 4 — the alter is directly addressed and must respond. Gates 5 and 6 still apply.

### Gate 3 — Relevance
Skip if `profile.topic_weights.get(forum_name, 0) < 0.2`. The alter has little historical interest in this forum.

### Gate 4 — Probability roll
`random.random() >= topic_weights[forum_name]` → skip. Higher topic weight = more likely to respond.

### Gate 5 — Rate limit
Skip if `hourly_count >= profile.hourly_cap` or `daily_count >= profile.daily_cap`.

### Gate 6 — Pile-on guard
After all alters are evaluated, if more than 2 passed for the same post, keep only the 2 with the highest `topic_weights[forum_name]`. Prevents multiple alters dogpiling one post in the same poll cycle.

---

## Thread Context

Before generating a reply, fetch the last 5 posts from the thread as conversational context.

**Fetch:** `showthread.php?p={post_id}` — VBulletin serves the page containing that post directly (no redirect). Parse all `<table id="postXXX">` elements on the page. Each post: author from `<div id="postmenu_{id}"> <a>`, content from `<div id="post_message_{id}">`, date from `<td class="thead">`.

**Previous-page fallback:** if the target post is at position 0 on its page, find the `<a>` link with text `<` and `page=\d+` in its href (the previous-page pagination link), fetch that URL, take the last 4 posts from it. At most 2 HTTP requests per context fetch.

**Content pre-processing** (applied to every post in the context):
1. Replace `<img src="...smilies/...">` with `(title)` e.g. `(Wink)` — VBulletin smilies have `alt=""` but a `title` attribute
2. Replace `<img>` with non-empty `alt` text (old-style emoticon images)
3. Replace remaining `<img alt="">` with `[afbeelding]`
4. `get_text(separator=' ', strip=True)` — strip all remaining HTML tags, decode entities

Quoted text (from `[QUOTE]` BBCode) is intentionally kept — it provides useful conversational context. VBulletin renders quotes in thread pages as a `div[style] > table > td.alt2` structure; `get_text()` renders them as `Quote: Originally Posted by X: ...` which the LLM can read.

**Image-only posts:** if a triggering post reduces to only `[afbeelding]` tokens after pre-processing, skip it — the alter cannot meaningfully reply to an unseen image.

---

## Reply Generation

`src/event/generator.py` wraps the existing `build_system_prompt()` and adds thread context.

User message format:
```
[Vorige berichten in de thread:]
{author1}: {content1}
{author2}: {content2}
...

[Nieuw bericht van {triggering_author}:]
"{triggering_content}"

Schrijf een reactie zoals {alter.reversed_username} dat zou doen.
```

System prompt: unchanged `build_system_prompt(profile)` from `src/persona/generator.py`.

On `stop_reason == "max_tokens"`, append ` [afgekapt]`. On API exception, log warning and mark the pending reply as `failed`.

---

## Posting

Each post uses a **fresh session** — no persistent alter session to manage or keep alive.

```python
def post_reply(alter_username, password, thread_id, message):
    session = VBulletinSession()
    session.login(alter_username, password)
    html = session.get(f"newreply.php?t={thread_id}&noquote=1")
    # parse all hidden form fields + securitytoken
    data = {all hidden fields} | {"message": message, "wysiwyg": "0", "sbutton": "Submit Reply"}
    resp = session.post(f"newreply.php?do=postreply&t={thread_id}", data)
    # verify: success if response contains no error block
```

**Verification:** success if the response HTML contains no `div.blockrow.error`. On failure, mark `pending_replies.status = 'failed'` — the review queue surfaces it for manual attention.

**Randomised delay:** after an approved reply is posted, wait 60–180 seconds before the next alter can post. Prevents all alters posting at the same second.

---

## Review Queue Web UI

Flask app on `localhost:5000`. Single page listing all `pending` entries ordered by `created_at`. Localhost only — never exposed externally.

**Each card displays:**
- Thread title (linked to `showthread.php?t={thread_id}`)
- The triggering post (author + plain text excerpt)
- Which alter is responding
- The generated reply (plain text; BBCode shown as-is)
- Auto-approve countdown timer if set

**Routes:**
```
GET  /                      → queue page (pending replies)
POST /reply/<id>/approve    → set status=approved, trigger post
POST /reply/<id>/discard    → set status=discarded
POST /reply/<id>/edit       → update reply_text, then approve
POST /reply/<id>/regenerate → re-call LLM, replace reply_text
GET  /status                → JSON: pending count, posts today per alter, live mode
```

**Auto-approve:** each pending reply has an optional `auto_approve_at` timestamp. The polling loop checks for expired auto-approve timers and promotes them to approved. Timer is configurable per alter via a new `auto_approve_minutes: int | None` field on `PersonaProfile` (default `None` = manual approval only). Set via the workbench JSON editor or directly in `personas/{username}.json`.

---

## Simulation Mode

`LIVE_MODE=false` (default). The full pipeline runs identically — polling, gates, generation, review queue — but `poster.post_reply()` is never called. Approved replies are written to `posted_replies` with `simulated=1`. The review queue shows a "SIMULATIE" badge on simulated posts.

Transition to live: set `LIVE_MODE=true` in `.env` and restart. No code change required.

---

## Entry Point

`event.py`:
1. Validate env vars (`ANTHROPIC_API_KEY`, `FORUM_USERNAME`, `FORUM_PASSWORD`, `ALTER_PASSWORD`)
2. Load all approved persona profiles from `personas/*.json`
3. Initialise SQLite schema (create tables if not exist)
4. Login wokebot scanner session, verify success
5. Start Flask thread (daemon)
6. Run polling loop — Ctrl+C shuts down cleanly

If `LIVE_MODE=false`, alter sessions are never created at startup (login happens per-post only when live).

---

## Key Design Decisions

- **Fresh session per alter post** — no session expiry risk; login overhead is negligible at the posting rate
- **Wokebot re-auth guard** — scanner session re-authenticates automatically on expiry
- **Simulation-first** — `LIVE_MODE=false` is the safe default; full pipeline testable without touching the forum
- **SQLite for state** — survives process restarts; no external dependencies
- **Pile-on guard** — max 2 alters per post per cycle; prevents dogpiling
- **Image-only skip** — triggering posts that are purely images are skipped; context images become `[afbeelding]`
- **Fresh context per reply** — thread page fetched at generation time, never cached
