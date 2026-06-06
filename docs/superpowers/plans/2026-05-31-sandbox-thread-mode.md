# Sandbox Thread Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a sandbox operating mode where the bot watches a fixed set of threads and bots reply to every post — triggered specifically by mention/quote, or randomly when no mention is detected.

**Architecture:** A new `sandbox_gates.py` handles evaluation for sandbox mode; `poller.py` gains `fetch_sandbox_posts`; `event.py` branches on `SANDBOX_THREAD_IDS` to pick mode. The rate-cap check is extracted from `gates.py` into a shared helper called by both gate modules.

**Tech Stack:** Python 3.12, SQLite (via `src/event/db.py`), BeautifulSoup, existing VBulletin session layer.

---

### Task 1: Extract `_passes_rate_cap` from `gates.py`

**Files:**
- Modify: `src/event/gates.py`
- Test: `tests/event/test_gates.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/event/test_gates.py` (after the existing imports, add `_passes_rate_cap` to the import line):

```python
from src.event.gates import evaluate_post, detect_quoted_alters, _passes_rate_cap
```

Then add these two tests at the bottom of the file:

```python
def test_passes_rate_cap_true_when_under_limits(conn):
    profile = _make_profile(hourly_cap=3, daily_cap=10)
    assert _passes_rate_cap(profile, conn) is True


def test_passes_rate_cap_false_when_hourly_limit_reached(conn):
    from datetime import datetime, timezone
    profile = _make_profile(hourly_cap=2)
    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y-%m-%dT%H")
    day_key = now.strftime("%Y-%m-%d")
    increment_rate(conn, "ejdar", hour_key, day_key)
    increment_rate(conn, "ejdar", hour_key, day_key)
    assert _passes_rate_cap(profile, conn) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && pytest tests/event/test_gates.py::test_passes_rate_cap_true_when_under_limits tests/event/test_gates.py::test_passes_rate_cap_false_when_hourly_limit_reached -v
```

Expected: `ImportError: cannot import name '_passes_rate_cap'`

- [ ] **Step 3: Extract `_passes_rate_cap` into `gates.py`**

In `src/event/gates.py`, add this function after the constants block (after line 14), before `detect_quoted_alters`:

```python
def _passes_rate_cap(profile: PersonaProfile, conn) -> bool:
    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y-%m-%dT%H")
    cutoff_hour_key = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H")
    hourly = db.get_hourly_count(conn, profile.reversed_username, hour_key)
    daily = db.get_daily_count(conn, profile.reversed_username, cutoff_hour_key)
    return hourly < profile.hourly_cap and daily < profile.daily_cap
```

Then in `evaluate_post`, replace lines 75–79:

```python
        hourly = db.get_hourly_count(conn, profile.reversed_username, hour_key)
        daily = db.get_daily_count(conn, profile.reversed_username, cutoff_hour_key)
        if hourly >= profile.hourly_cap or daily >= profile.daily_cap:
            logging.debug("Rate limit hit for %s", profile.reversed_username)
            continue
```

with:

```python
        if not _passes_rate_cap(profile, conn):
            logging.debug("Rate limit hit for %s", profile.reversed_username)
            continue
```

Also remove the now-unused `hour_key` / `cutoff_hour_key` variables from `evaluate_post` (lines 51–53 — the three lines starting with `now =`, `hour_key =`, `cutoff_hour_key =`).

- [ ] **Step 4: Run all gate tests**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && pytest tests/event/test_gates.py -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/event/gates.py tests/event/test_gates.py
git commit -m "refactor: extract _passes_rate_cap helper from gates.evaluate_post"
```

---

### Task 2: Add `fetch_sandbox_posts` to `poller.py`

**Files:**
- Modify: `src/event/poller.py`
- Test: `tests/event/test_poller.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/event/test_poller.py` (add `fetch_sandbox_posts` to the import line at the top):

```python
from src.event.poller import fetch_new_posts, parse_post_date, parse_new_thread_list, fetch_sandbox_posts
```

Then add at the bottom:

```python
def test_fetch_sandbox_posts_returns_posts_for_watched_thread():
    session = MagicMock()
    session.get.return_value = _POST_HTML_F9
    posts = fetch_sandbox_posts(session, {200})
    assert len(posts) == 1
    assert posts[0]["post_id"] == 100
    assert posts[0]["thread_id"] == 200
    assert posts[0]["forum_id"] == 0
    assert posts[0]["forum_name"] == ""


def test_fetch_sandbox_posts_skips_failed_thread():
    session = MagicMock()
    session.get.side_effect = Exception("network error")
    posts = fetch_sandbox_posts(session, {200})
    assert posts == []


def test_fetch_sandbox_posts_combines_multiple_threads():
    session = MagicMock()
    session.get.return_value = _POST_HTML_F9
    posts = fetch_sandbox_posts(session, {200, 201})
    assert len(posts) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && pytest tests/event/test_poller.py::test_fetch_sandbox_posts_returns_posts_for_watched_thread -v
```

Expected: `ImportError: cannot import name 'fetch_sandbox_posts'`

- [ ] **Step 3: Implement `fetch_sandbox_posts` in `poller.py`**

Add this function at the bottom of `src/event/poller.py` (after `parse_post_date`):

```python
def fetch_sandbox_posts(session, thread_ids: set[int]) -> list[dict]:
    """Fetch current posts from a fixed set of sandbox threads."""
    posts = []
    for thread_id in thread_ids:
        try:
            time.sleep(_FETCH_DELAY)
            html = session.get(f"showthread.php?goto=newpost&t={thread_id}")
            thread_posts = parse_thread_page(html)
            for p in thread_posts:
                p["thread_id"] = thread_id
                p["thread_title"] = ""
                p["forum_id"] = 0
                p["forum_name"] = ""
            posts.extend(thread_posts)
            logging.debug("sandbox thread %d: %d posts", thread_id, len(thread_posts))
        except Exception as exc:
            logging.warning("Failed to fetch sandbox thread %d: %s", thread_id, exc)
    return posts
```

- [ ] **Step 4: Run all poller tests**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && pytest tests/event/test_poller.py -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/event/poller.py tests/event/test_poller.py
git commit -m "feat: add fetch_sandbox_posts to poller"
```

---

### Task 3: Create `sandbox_gates.py`

**Files:**
- Create: `src/event/sandbox_gates.py`
- Create: `tests/event/test_sandbox_gates.py`

- [ ] **Step 1: Write all failing tests**

Create `tests/event/test_sandbox_gates.py`:

```python
import sqlite3
import pytest
from src.event.db import init_db, increment_rate
from src.event.sandbox_gates import evaluate_post_sandbox
from src.persona.models import PersonaProfile
from datetime import datetime, timezone


def _make_profile(reversed_username="ejdar", original_username="radje", hourly_cap=3, daily_cap=10):
    p = PersonaProfile.from_alter_ego({
        "user_id": 1,
        "original_username": original_username,
        "reversed_username": reversed_username,
        "post_count": 100,
        "last_active": "2023-01-01",
    })
    p.hourly_cap = hourly_cap
    p.daily_cap = daily_cap
    return p


def _make_post(author="RealUser", content="Hallo allemaal hoe gaat het?"):
    return {
        "post_id": 1,
        "thread_id": 100,
        "forum_id": 0,
        "forum_name": "",
        "author": author,
        "content": content,
    }


@pytest.fixture
def conn():
    c = init_db(":memory:")
    yield c
    c.close()


def test_author_is_alter_returns_empty(conn):
    profile = _make_profile(reversed_username="ejdar")
    post = _make_post(author="ejdar", content="Hoi dit is mijn eigen bericht")
    assert evaluate_post_sandbox(post, [profile], conn) == []


def test_text_mention_reversed_name_triggers(conn):
    profile = _make_profile(reversed_username="ejdar")
    post = _make_post(content="ejdar wat vind jij hiervan eigenlijk?")
    result = evaluate_post_sandbox(post, [profile], conn)
    assert profile in [p for p, _ in result]


def test_text_mention_original_name_triggers(conn):
    profile = _make_profile(reversed_username="ejdar", original_username="radje")
    post = _make_post(content="radje was hier vroeger altijd actief toch?")
    result = evaluate_post_sandbox(post, [profile], conn)
    assert profile in [p for p, _ in result]


def test_mention_is_case_insensitive(conn):
    profile = _make_profile(reversed_username="EjDaR")
    post = _make_post(content="ejdar hoi hoe gaat het met je?")
    result = evaluate_post_sandbox(post, [profile], conn)
    assert profile in [p for p, _ in result]


def test_max_three_triggered_when_many_mentioned(conn):
    profiles = [_make_profile(reversed_username=f"user{i}", original_username=f"resu{i}") for i in range(5)]
    content = " ".join(f"user{i}" for i in range(5)) + " wat vinden jullie allemaal?"
    post = _make_post(content=content)
    result = evaluate_post_sandbox(post, profiles, conn)
    assert len(result) <= 3


def test_no_mention_returns_random_selection(conn):
    profiles = [_make_profile(reversed_username=f"bot{i}", original_username=f"tob{i}") for i in range(10)]
    post = _make_post(content="Heeft iemand ervaring met nano aquaria opzetten?")
    result = evaluate_post_sandbox(post, profiles, conn, replies_per_post=3)
    assert len(result) == 3
    assert all(w == 1.0 for _, w in result)


def test_no_mention_respects_replies_per_post(conn):
    profiles = [_make_profile(reversed_username=f"bot{i}", original_username=f"tob{i}") for i in range(10)]
    post = _make_post(content="Heeft iemand ervaring met nano aquaria opzetten?")
    result = evaluate_post_sandbox(post, profiles, conn, replies_per_post=1)
    assert len(result) == 1


def test_rate_capped_profile_excluded_from_random(conn):
    capped = _make_profile(reversed_username="capped", original_username="deppac", hourly_cap=1)
    free = _make_profile(reversed_username="free00", original_username="00eerf", hourly_cap=5)
    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y-%m-%dT%H")
    day_key = now.strftime("%Y-%m-%d")
    increment_rate(conn, "capped", hour_key, day_key)
    post = _make_post(content="Heeft iemand ervaring met nano aquaria opzetten?")
    result = evaluate_post_sandbox(post, [capped, free], conn, replies_per_post=3)
    names = [p.reversed_username for p, _ in result]
    assert "capped" not in names
    assert "free00" in names


def test_rate_capped_profile_excluded_even_when_triggered(conn):
    capped = _make_profile(reversed_username="capped", original_username="deppac", hourly_cap=1)
    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y-%m-%dT%H")
    day_key = now.strftime("%Y-%m-%d")
    increment_rate(conn, "capped", hour_key, day_key)
    post = _make_post(content="capped wat vind jij hiervan eigenlijk?")
    result = evaluate_post_sandbox(post, [capped], conn)
    assert result == []


def test_fewer_profiles_than_replies_per_post(conn):
    profiles = [_make_profile(reversed_username="solo0", original_username="0olos")]
    post = _make_post(content="Heeft iemand ervaring met nano aquaria opzetten?")
    result = evaluate_post_sandbox(post, profiles, conn, replies_per_post=3)
    assert len(result) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && pytest tests/event/test_sandbox_gates.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.event.sandbox_gates'`

- [ ] **Step 3: Create `src/event/sandbox_gates.py`**

```python
import random
import logging
import sqlite3

from src.persona.models import PersonaProfile
from src.event.gates import _passes_rate_cap

_MAX_TRIGGERED = 3


def _find_triggered(post: dict, profiles: list[PersonaProfile]) -> list[PersonaProfile]:
    content_lower = post.get("content", "").lower()
    triggered = []
    for profile in profiles:
        if (profile.reversed_username.lower() in content_lower
                or profile.original_username.lower() in content_lower):
            triggered.append(profile)
    return triggered


def evaluate_post_sandbox(
    post: dict,
    profiles: list[PersonaProfile],
    conn: sqlite3.Connection,
    replies_per_post: int = 3,
) -> list[tuple[PersonaProfile, float]]:
    all_reversed = {p.reversed_username for p in profiles}
    if post.get("author", "") in all_reversed:
        return []

    eligible = [p for p in profiles if _passes_rate_cap(p, conn)]

    triggered = _find_triggered(post, eligible)
    if triggered:
        return [(p, 1.0) for p in triggered[:_MAX_TRIGGERED]]

    sample = random.sample(eligible, min(replies_per_post, len(eligible)))
    return [(p, 1.0) for p in sample]
```

- [ ] **Step 4: Run all sandbox gate tests**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && pytest tests/event/test_sandbox_gates.py -v
```

Expected: all pass

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && pytest -v
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/event/sandbox_gates.py tests/event/test_sandbox_gates.py
git commit -m "feat: add sandbox_gates with trigger detection and random selection"
```

---

### Task 4: Wire sandbox mode into `event.py`

**Files:**
- Modify: `event.py`

No new tests needed — sandbox_gates and fetch_sandbox_posts are already tested. This task wires the pieces together in the main loop.

- [ ] **Step 1: Add imports to `event.py`**

At the top of `event.py`, update the existing import block. Change:

```python
from src.event.poller import fetch_new_posts, parse_post_date
```

to:

```python
from src.event.poller import fetch_new_posts, fetch_sandbox_posts, parse_post_date
from src.event import sandbox_gates
```

- [ ] **Step 2: Update `_poll_once` signature**

Change the function signature from:

```python
def _poll_once(scanner, profiles, conn, alter_password, live_mode, cutoff,
               auto_approve_minutes, replies_per_cycle):
```

to:

```python
def _poll_once(scanner, profiles, conn, alter_password, live_mode, cutoff,
               auto_approve_minutes, replies_per_cycle,
               sandbox_thread_ids: set[int] | None = None,
               replies_per_post: int = 3):
```

- [ ] **Step 3: Replace the fetch + evaluate block in `_poll_once`**

Replace this block (lines 41–67 in the original):

```python
    try:
        new_posts = fetch_new_posts(scanner)
    except Exception as exc:
        logging.error("Poll failed: %s", exc)
        return

    # Phase 1: evaluate all unseen posts, collect (post, profile, weight) candidates
    candidates: list[tuple[dict, PersonaProfile, float]] = []
    evaluated_posts: list[dict] = []

    for post in new_posts:
        if db.is_seen(conn, post["post_id"]):
            continue

        post_dt = parse_post_date(post.get("date", ""))
        if post_dt and post_dt < cutoff:
            db.mark_seen(conn, post["post_id"], post["thread_id"], post["forum_id"])
            continue

        evaluated_posts.append(post)

        if _is_image_only(post.get("content", "")):
            continue

        post["quoted_alters"] = gates.detect_quoted_alters(post, profiles)
        for profile, weight in gates.evaluate_post(post, profiles, conn):
            candidates.append((post, profile, weight))
```

with:

```python
    try:
        if sandbox_thread_ids:
            new_posts = fetch_sandbox_posts(scanner, sandbox_thread_ids)
        else:
            new_posts = fetch_new_posts(scanner)
    except Exception as exc:
        logging.error("Poll failed: %s", exc)
        return

    # Phase 1: evaluate all unseen posts, collect (post, profile, weight) candidates
    candidates: list[tuple[dict, PersonaProfile, float]] = []
    evaluated_posts: list[dict] = []

    for post in new_posts:
        if db.is_seen(conn, post["post_id"]):
            continue

        post_dt = parse_post_date(post.get("date", ""))
        if post_dt and post_dt < cutoff:
            db.mark_seen(conn, post["post_id"], post["thread_id"], post["forum_id"])
            continue

        evaluated_posts.append(post)

        if _is_image_only(post.get("content", "")):
            continue

        if sandbox_thread_ids:
            for profile, weight in sandbox_gates.evaluate_post_sandbox(
                post, profiles, conn, replies_per_post
            ):
                candidates.append((post, profile, weight))
        else:
            post["quoted_alters"] = gates.detect_quoted_alters(post, profiles)
            for profile, weight in gates.evaluate_post(post, profiles, conn):
                candidates.append((post, profile, weight))
```

- [ ] **Step 4: Skip the cycle cap in sandbox mode**

Replace the Phase 2 block (the sort + cycle cap selection, lines 69–84 in original):

```python
    # Phase 2: pick the top N most relevant candidates for this cycle
    # Skip duplicate (alter, thread) pairs — one reply per alter per thread per cycle
    candidates.sort(key=lambda x: x[2], reverse=True)
    selected: list[tuple[dict, PersonaProfile, float]] = []
    seen_alter_thread: set[tuple[str, int]] = set()
    for post, profile, weight in candidates:
        key = (profile.reversed_username, post["thread_id"])
        if key in seen_alter_thread:
            continue
        seen_alter_thread.add(key)
        selected.append((post, profile, weight))
        if len(selected) >= replies_per_cycle:
            break
    logging.info(
        "Cycle: %d new posts, %d candidates, %d selected (cap=%d)",
        len(evaluated_posts), len(candidates), len(selected), replies_per_cycle,
    )
```

with:

```python
    # Phase 2: in forum-wide mode, cap by cycle limit; in sandbox mode, use all candidates
    if sandbox_thread_ids:
        selected = candidates
        logging.info(
            "Cycle (sandbox): %d new posts, %d selected",
            len(evaluated_posts), len(selected),
        )
    else:
        candidates.sort(key=lambda x: x[2], reverse=True)
        selected: list[tuple[dict, PersonaProfile, float]] = []
        seen_alter_thread: set[tuple[str, int]] = set()
        for post, profile, weight in candidates:
            key = (profile.reversed_username, post["thread_id"])
            if key in seen_alter_thread:
                continue
            seen_alter_thread.add(key)
            selected.append((post, profile, weight))
            if len(selected) >= replies_per_cycle:
                break
        logging.info(
            "Cycle: %d new posts, %d candidates, %d selected (cap=%d)",
            len(evaluated_posts), len(candidates), len(selected), replies_per_cycle,
        )
```

- [ ] **Step 5: Read `SANDBOX_THREAD_IDS` in `main()`**

In `main()`, after the existing env var reads (after `replies_per_cycle = ...`), add:

```python
    sandbox_raw = os.getenv("SANDBOX_THREAD_IDS", "").strip()
    sandbox_thread_ids: set[int] = (
        {int(x.strip()) for x in sandbox_raw.split(",") if x.strip()}
        if sandbox_raw else set()
    )
    replies_per_post = int(os.getenv("SANDBOX_REPLIES_PER_POST", "3"))

    if sandbox_thread_ids:
        logging.info("SANDBOX MODE: watching threads %s", sandbox_thread_ids)
    else:
        logging.info("FORUM-WIDE MODE")
```

- [ ] **Step 6: Pass new args to `_poll_once`**

Change the `_poll_once` call in the main loop from:

```python
        _poll_once(scanner, profiles, conn, alter_password, live_mode, cutoff,
                   auto_approve_minutes, replies_per_cycle)
```

to:

```python
        _poll_once(scanner, profiles, conn, alter_password, live_mode, cutoff,
                   auto_approve_minutes, replies_per_cycle,
                   sandbox_thread_ids=sandbox_thread_ids,
                   replies_per_post=replies_per_post)
```

- [ ] **Step 7: Run the full test suite**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && pytest -v
```

Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add event.py
git commit -m "feat: wire sandbox mode into event.py poll loop"
```

---

### Task 5: Update `.env.example`

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Add the two new vars**

Append to `.env.example`:

```
SANDBOX_THREAD_IDS=          # comma-separated thread IDs to watch; empty = forum-wide mode
SANDBOX_REPLIES_PER_POST=3   # max random bot replies per unmentioned sandbox post
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add SANDBOX_THREAD_IDS and SANDBOX_REPLIES_PER_POST to .env.example"
```

---

### Task 6: Final check

- [ ] **Step 1: Run the full test suite one last time**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && pytest -v
```

Expected: all pass, no warnings

- [ ] **Step 2: Push**

```bash
git push
```
