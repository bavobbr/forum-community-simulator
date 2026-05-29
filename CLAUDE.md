# Shrimp Resurrect — Claude Context

## What this project does

24-hour AI event on `your-forum.example.com` (VBulletin 3.7, Dutch-language shrimp-keeping forum). The 26 most historically active members who have been inactive for 2+ years are "resurrected" as AI alter egos. Each alter ego has a reversed username (e.g. `ShrimpKing` → `gniKpmirS`), a mirrored avatar, and a persona built from their actual post history. During the event they respond live to forum activity as those members would have.

## Entry points

- `python workbench.py` — Phase 1: scrape posts, build/refine personas interactively, save to `personas/{username}.json`
- `python event.py` — Phase 2: poll forum every N seconds, generate replies, queue for human approval via Flask UI at `http://localhost:5000`
- `python select_accounts.py` — one-off script, already run; produced `config/approved_accounts.json`

## Architecture

```
src/
  llm.py                  # Thin Gemini wrapper (single source of truth for AI calls)
  session.py              # VBulletin HTTP session (login, requests)
  models.py               # Shared data models
  scraper/                # Member list + profile scrapers (used by select_accounts.py)
  persona/
    scraper.py            # PostScraper — fetches post history per user
    analyzer.py           # LLM-based persona analysis (batched)
    generator.py          # LLM reply generation for workbench test posts
    models.py             # PersonaProfile dataclass
  workbench/
    cli.py                # Interactive workbench loop (rich TUI)
  event/
    poller.py             # Fetches new forum posts
    thread_scraper.py     # Fetches thread context for a post
    generator.py          # LLM reply generation for live event
    gates.py              # Decides which alter egos should respond to a post
    poster.py             # Posts approved replies to the forum
    db.py                 # SQLite (event.db) for pending/seen posts
    webui.py              # Flask approval queue UI
config/
  approved_accounts.json  # 25 approved alter egos (input to workbench)
  test_posts.json         # Test posts used during workbench persona evaluation
personas/                 # Generated persona JSON files (gitignored)
  {username}.json         # One file per persona; loaded by event.py
```

## LLM layer (`src/llm.py`)

Provider: Google Gemini (`google-genai` package, `GOOGLE_API_KEY` env var).

Two models, two use cases:
- `MODEL_PRO = "gemini-3.1-pro-preview"` — complex analysis, used in workbench (Phase 1)
- `MODEL_FLASH = "gemini-3.5-flash"` — speed/cost, used for sample reply previews (Phase 1) and live event (Phase 2)

Two functions:
- `call_llm(system, user, max_tokens) -> str` — returns text only, always uses Pro; raises `ValueError` if Gemini truncates the response (`finish_reason == MAX_TOKENS`)
- `call_llm_raw(system, user, max_tokens, model=MODEL_FLASH)` — returns full response object (needed for `finish_reason`); callers that want Pro must pass `model=MODEL_PRO`

SDK pattern:
```python
_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY", ""))
_client.models.generate_content(
    model=MODEL_PRO,
    config=types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens),
    contents=[user],
)
```

Truncation check: `resp.candidates[0].finish_reason.name == "MAX_TOKENS"`

## PersonaProfile (`src/persona/models.py`)

Key fields for AI context:

| Field | Type | Description |
|---|---|---|
| `dialect_markers` | `list[str]` | Characteristic words/phrases from the member's writing |
| `formality` | `str` | Writing register: `casual`, `formal`, etc. |
| `sentence_length` | `str` | Typical sentence length: `short`, `medium`, `long` |
| `typical_post_length` | `int` | Average word count per post (default 50) |
| `topic_weights` | `dict[str, float]` | Per-forum interest weights (0.0–1.0), used by gates |
| `opinion_fingerprint` | `list[str]` | Specific opinions (up to 25); included in system prompt |
| `frequent_interactions` | `dict[str, str]` | username → `"ally"`, `"rival"`, or `"neutral"` |
| `persona_summary` | `str` | 6–10 sentence narrative description of the person |
| `worldview` | `str` | Core values, outlook, and philosophy of life |
| `rhetorical_patterns` | `list[str]` | How the member argues and engages in discussion |
| `interest_tags` | `list[str]` | 10–15 concrete keywords (names, games, teams, brands) that trigger a response even when `topic_weights` are low |
| `example_posts` | `list[str]` | Few-shot examples used in the system prompt |

`worldview` and `rhetorical_patterns` are used by both the analyzer and the generator to give the LLM deeper character context when generating replies to topics the member never directly addressed.

## Persona analyzer (`src/persona/analyzer.py`)

- `analyze_first_batch`: processes all posts fetched by `fetch_all_posts` (full history), max_output_tokens 8192; raises `ValueError` on unparseable JSON
- `refine_with_batch`: uses a **diff schema** — asks Gemini only for what changed (`new_dialect_markers`, `topic_weights_update`, `worldview`, `new_rhetorical_patterns`, etc.) and merges in Python. Never regenerates the full profile. Max output tokens: 8192
- `opinion_fingerprint` cap: 25 items (raised from 15)
- `persona_summary` requested as 6–10 sentences

## Workbench flow (`src/workbench/cli.py`)

Main list: select by number, `b` for bulk initial analysis of all unstarted personas, `q` to quit.

Inside a persona, actions are independent:
- `[l]` — fetch the next page (~100 posts) and refine the profile
- `[s]` — generate sample replies on demand (uses `MODEL_FLASH`, 512 tokens — previews only)
- `[a]` — approve and return to list
- `[e]` — open the raw JSON for manual editing, reload on Enter
- `[x]` — delete the profile file and restart from scratch (available at any stage)
- `[q]` — back to list without saving

The profile summary panel shows `persona_summary`, `worldview`, `opinion_fingerprint` count, `rhetorical_patterns`, writing style, and caps.

Rich markup escaping (`rich.markup.escape`) is applied to all LLM-generated text shown in panels to prevent BBCode tags from being misinterpreted by Rich.

## Forum scraping facts

- VBulletin requires MD5 password hashing (`vb_login_md5password` field), not plain text
- Login success must be verified by GET to `index.php` (POST response is a redirect/splash)
- Post history search init: `search.php?do=finduser&u={id}&pp=100` — returns a `searchid`, cached in `PostScraper._search_ids` (used by `fetch_batch` for incremental loads)
- Post history pages: `search.php?searchid={id}&pp=100&page={n}` — always 100 posts per page
- VBulletin caps any single search at 200 results (2 pages). `fetch_window` uses the advanced search to get one batch of ~200 posts; successive calls walk backward through time using the oldest post's date as the next upper-bound.
- Advanced search POST fields (verified against actual VBulletin 3.7 form submission):
  `do=process`, `searchuser`, `starteronly=0`, `exactname=1`, `showposts=1`, `sortby=lastpost`, `order=descending`, `beforeafter=before`, `searchdate=N` (N = number of days, NOT a Unix timestamp), `forumchoice[]=0`, `childforums=1`, `dosearch=Search Now`, `securitytoken`
- `searchdate=N, beforeafter=before` → posts older than N days ago; `order=descending` → newest-of-those-old first; result: 200 posts walking backward in time each call
- Security token: extracted from `index.php` response after login (`SECURITYTOKEN = '...'` JS variable); stored in `VBulletinSession._security_token`, included in all POST requests
- `parse_post_date_timestamp(date_str)` converts "DD-MM-YYYY, HH:MM" → Unix timestamp (treats display time as UTC; `_TZ_BUFFER_SECONDS = 7200` is subtracted from the window cutoff to ensure overlap covers Belgium's UTC+1/+2 offset)
- `fetch_window(username, before_ts)` returns `(posts, oldest_ts)`. `oldest_ts` stored in `profile.oldest_post_ts`; passed as `before_ts` on next call. Produces ~8 posts of overlap at each day boundary (harmless — `refine_with_batch` only adds new information).
- Verified: 3 batches × 200 posts = 584 unique posts for user 'acku' (20 340 total posts), correctly advancing from May 2026 → Dec 2025 → Apr 2025 → Dec 2024
- Last activity date comes from `search.php?do=finduser&u={id}` (not the profile page)
- Date format on search results: `DD-MM-YYYY, HH:MM` in `<td class="thead">`
- Forum rate-limits searches: 5s minimum between requests; script uses 6s delay
- Members-only forums (Zwam, f=9) require authentication to access
- Excluded forums: Discretie (f=40), Shrimp Refuge HQ (f=20), Forum Games (f=42), Donations (f=29)
- Scanning account: `wokebot` / `wokebot123` (forum scanning only, not an alter ego)
- **New-post polling** uses `search.php?do=getdaily` (last 24h, stateless — not consumed by checking). Flow: `getdaily` → 302 redirect → `search.php?searchid=X` (thread list) → re-fetch with `&pp=100` for up to 100 threads → for each thread: `showthread.php?goto=newpost&t={id}` (redirects to the page with the newest unread post) → `parse_thread_page()`. Post dicts gain `thread_id`, `thread_title`, `forum_id`, `forum_name` from the thread list row.
- Date strings from `showthread` pages can be absolute (`DD-MM-YYYY, HH:MM`) or relative (`Today, HH:MM` / `Yesterday, HH:MM`); `parse_post_date()` handles both, treating all times as UTC+2.

## Environment variables

Required in `.env` (see `.env.example`):
```
GOOGLE_API_KEY=...
FORUM_USERNAME=wokebot
FORUM_PASSWORD=wokebot123
ALTER_PASSWORD=...        # shared password for all alter ego accounts
FORUM_URL=...             # base URL of the VBulletin forum (no trailing slash)
```

Optional:
```
LIVE_MODE=false           # true = actually post replies; false = simulate only
LOOKBACK_HOURS=48         # ignore posts older than this on startup
POLL_INTERVAL=300         # seconds between forum polls
SEARCH_DELAY=6            # seconds between post-history requests
AUTO_APPROVE_MINUTES=10   # minutes before a queued reply auto-approves
REPLIES_PER_CYCLE=3       # max replies generated per poll cycle (see algorithm below)
```

## Event poll algorithm (`event.py` + `src/event/`)

Each poll cycle (every `POLL_INTERVAL` seconds) runs in four phases:

**Phase 1 — Fetch.** `poller.fetch_new_posts(scanner)` calls `search.php?do=getdaily`, resolves the searchid redirect to get a thread list, then fetches `showthread.php?goto=newpost&t={id}` for each thread. Returns a flat `list[dict]` of posts, each with `post_id`, `thread_id`, `thread_title`, `forum_id`, `forum_name`, `author`, `content`, `date`. Excluded forums are filtered out before returning.

**Phase 2 — Evaluate.** For every post not yet in `seen_posts`:
- Skip posts older than `LOOKBACK_HOURS` (mark seen immediately).
- Skip image-only posts (`[afbeelding]` with no text).
- Call `gates.evaluate_post(post, profiles, conn)` → `list[tuple[PersonaProfile, float]]` (at most `_MAX_RESPONDERS = 2` per post to prevent pile-ons).
  - Gate logic per profile:
    1. **Mention bypass**: if the alter's reversed username appears in the content, pass (weight defaults to 1.0).
    2. **Tag bypass**: if any `interest_tag` appears (case-insensitive) in the content, pass.
    3. **Topic weight**: otherwise, skip if `topic_weights[forum] < 0.2`; then stochastic skip with `random() >= weight`.
    4. **Rate cap**: skip if `hourly_count >= hourly_cap` or `daily_count >= daily_cap` (checked in `rate_counters` DB table; only incremented in live mode).
  - Survivors sorted by weight descending; top 2 returned with their weights.

**Phase 3 — Cap & generate.** Collect all `(post, profile, weight)` pairs from the entire cycle. Sort by weight descending. Take the top `REPLIES_PER_CYCLE` (default 3). For each selected pair:
- Fetch thread context via `thread_scraper.fetch_thread_context`.
- Call `event_generator.generate_reply(profile, triggering_post, context)`.
- Insert into `pending_replies` with `auto_approve_at = now + AUTO_APPROVE_MINUTES`.

The cycle cap is the primary anti-spam control: it prevents startup bursts (getdaily returning a day's backlog) and ensures only the highest-relevance interactions happen each cycle. Unselected candidates are still marked seen; old posts do not keep competing with new activity.

**Phase 4 — Mark seen.** All posts evaluated in the cycle are written to `seen_posts`, regardless of whether they generated a reply.

**Auto-approve loop.** After each poll, `db.get_pending_auto_approve` finds replies whose `auto_approve_at` has passed and calls `_do_approve`. In live mode this calls `poster.post_reply()`, increments `rate_counters`, and sleeps 60–180 s to look human.

## Testing

```bash
pytest                    # run all 106 tests
pytest tests/test_llm.py  # LLM wrapper tests
```

`tests/conftest.py` sets `GOOGLE_API_KEY=test-api-key-for-unit-tests` before any import, so the SDK client initialises without a real key.

All domain modules patch at the call site: `patch("src.persona.analyzer.call_llm", ...)` etc. Never patch `_client` directly except in `tests/test_llm.py`.

## Current state (2026-05-25)

All three plans complete:
1. Account selection — 25 approved alter egos in `config/approved_accounts.json`
2. Persona workbench — fully functional, uses `gemini-3.1-pro-preview` for analysis, `gemini-3.5-flash` for sample previews
3. Event orchestrator — fully functional, uses `gemini-3.5-flash`

Poller verified end-to-end: `getdaily` → thread list (18 threads) → 245 posts across 17 forums. Cycle cap + individual rate caps confirmed working.

**Next step:** Set `GOOGLE_API_KEY` in `.env` and run `python workbench.py` to build personas, then `python event.py` for the live event.
