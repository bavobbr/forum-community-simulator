# Event Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the live 24-hour event runtime that polls the forum, runs a decision pipeline, generates replies via Claude, queues them for review, and posts approved replies as alter ego accounts.

**Architecture:** Single Python process (`event.py`) with a Flask review UI in a background thread and a polling loop on the main thread. SQLite (`event.db`) persists all state so the process can restart safely. Seven modules under `src/event/` each own one responsibility.

**Tech Stack:** Python 3.11+, Flask 3.1.0, SQLite (stdlib), BeautifulSoup4, anthropic==0.104.1, requests, python-dotenv

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/persona/models.py` | Modify | Add `auto_approve_minutes` field |
| `src/event/__init__.py` | Create | Package marker |
| `src/event/db.py` | Create | SQLite schema + all queries |
| `src/event/poller.py` | Create | Fetch new posts via `search.php?do=getnew` |
| `src/event/gates.py` | Create | Six-gate decision pipeline |
| `src/event/thread_scraper.py` | Create | Parse thread pages, fetch 5-post context window |
| `src/event/generator.py` | Create | LLM reply generation with thread context |
| `src/event/poster.py` | Create | Post reply to VBulletin via fresh session |
| `src/event/webui.py` | Create | Flask review queue app |
| `event.py` | Create | Entry point, polling loop, auto-approve check |
| `requirements.txt` | Modify | Add `flask==3.1.0` |
| `.env.example` | Modify | Add `ALTER_PASSWORD`, `LIVE_MODE`, `LOOKBACK_HOURS`, `POLL_INTERVAL` |
| `.gitignore` | Modify | Add `event.db` |
| `tests/event/__init__.py` | Create | Package marker |
| `tests/event/test_db.py` | Create | DB layer tests |
| `tests/event/test_poller.py` | Create | Poller tests |
| `tests/event/test_gates.py` | Create | Gate pipeline tests |
| `tests/event/test_thread_scraper.py` | Create | Thread scraper tests |
| `tests/event/test_generator.py` | Create | Generator tests |
| `tests/event/test_poster.py` | Create | Poster tests |
| `tests/event/test_webui.py` | Create | Flask route tests |

---

### Task 1: Add auto_approve_minutes to PersonaProfile

**Files:**
- Modify: `src/persona/models.py`
- Test: `tests/persona/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# In tests/persona/test_models.py, add:
def test_auto_approve_minutes_defaults_to_none():
    p = PersonaProfile.from_alter_ego({
        "user_id": 1, "original_username": "a", "reversed_username": "b",
        "post_count": 1, "last_active": "2023-01-01",
    })
    assert p.auto_approve_minutes is None


def test_auto_approve_minutes_round_trips():
    p = PersonaProfile.from_alter_ego({
        "user_id": 1, "original_username": "a", "reversed_username": "b",
        "post_count": 1, "last_active": "2023-01-01",
    })
    p.auto_approve_minutes = 10
    d = p.to_dict()
    p2 = PersonaProfile.from_dict(d)
    assert p2.auto_approve_minutes == 10
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/persona/test_models.py::test_auto_approve_minutes_defaults_to_none -v
```
Expected: FAIL — `PersonaProfile has no attribute auto_approve_minutes`

- [ ] **Step 3: Add field to PersonaProfile**

In `src/persona/models.py`, after `persona_summary: str = ""` add:

```python
    # Event orchestrator — None means manual approval only
    auto_approve_minutes: int | None = None
```

And in `from_dict`, after `persona_summary=d.get("persona_summary", ""),` add:

```python
            auto_approve_minutes=d.get("auto_approve_minutes", None),
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/persona/ -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/persona/models.py tests/persona/test_models.py
git commit -m "feat: add auto_approve_minutes to PersonaProfile"
```

---

### Task 2: SQLite database layer

**Files:**
- Create: `src/event/__init__.py`
- Create: `src/event/db.py`
- Create: `tests/event/__init__.py`
- Create: `tests/event/test_db.py`

- [ ] **Step 1: Create package markers**

Create `src/event/__init__.py` (empty) and `tests/event/__init__.py` (empty).

- [ ] **Step 2: Write the failing tests**

Create `tests/event/test_db.py`:

```python
import sqlite3
import pytest
from src.event.db import (
    init_db, mark_seen, is_seen,
    get_hourly_count, get_daily_count, increment_rate,
    insert_pending, get_pending, get_pending_by_id,
    update_status, update_reply_text,
    insert_posted, get_pending_auto_approve,
    get_daily_posts_summary,
)


@pytest.fixture
def conn():
    c = init_db(":memory:")
    yield c
    c.close()


def test_seen_posts_roundtrip(conn):
    assert not is_seen(conn, 42)
    mark_seen(conn, 42, 100, 9)
    assert is_seen(conn, 42)


def test_rate_counters(conn):
    assert get_hourly_count(conn, "ejdar", "2026-05-25T14") == 0
    assert get_daily_count(conn, "ejdar", "2026-05-25") == 0
    increment_rate(conn, "ejdar", "2026-05-25T14", "2026-05-25")
    increment_rate(conn, "ejdar", "2026-05-25T14", "2026-05-25")
    assert get_hourly_count(conn, "ejdar", "2026-05-25T14") == 2
    assert get_daily_count(conn, "ejdar", "2026-05-25") == 2


def test_daily_count_spans_hours(conn):
    increment_rate(conn, "ejdar", "2026-05-25T13", "2026-05-25")
    increment_rate(conn, "ejdar", "2026-05-25T14", "2026-05-25")
    assert get_daily_count(conn, "ejdar", "2026-05-25") == 2
    assert get_hourly_count(conn, "ejdar", "2026-05-25T13") == 1
    assert get_hourly_count(conn, "ejdar", "2026-05-25T14") == 1


def test_pending_replies_crud(conn):
    reply_id = insert_pending(conn, 1, 100, 9, "ejdar", "Da is goed", None)
    rows = get_pending(conn)
    assert len(rows) == 1
    assert rows[0]["reply_text"] == "Da is goed"
    assert rows[0]["status"] == "pending"

    update_reply_text(conn, reply_id, "Aangepaste tekst")
    row = get_pending_by_id(conn, reply_id)
    assert row["reply_text"] == "Aangepaste tekst"

    update_status(conn, reply_id, "discarded")
    assert get_pending_by_id(conn, reply_id)["status"] == "discarded"
    assert get_pending(conn) == []  # only returns 'pending' rows


def test_auto_approve_queue(conn):
    insert_pending(conn, 1, 100, 9, "ejdar", "reply", "2026-05-25T10:00:00+00:00")
    insert_pending(conn, 2, 101, 9, "ejdar", "reply2", "2099-01-01T00:00:00+00:00")
    insert_pending(conn, 3, 102, 9, "ejdar", "reply3", None)
    ready = get_pending_auto_approve(conn, now="2026-05-25T12:00:00+00:00")
    assert len(ready) == 1
    assert ready[0]["post_id"] == 1


def test_insert_posted_and_summary(conn):
    insert_posted(conn, "ejdar", 100, 1, "reply", simulated=False)
    insert_posted(conn, "ejdar", 101, 2, "reply2", simulated=True)
    summary = get_daily_posts_summary(conn, "2026-05-25")
    assert summary.get("ejdar", 0) == 2
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/event/test_db.py -v
```
Expected: FAIL — `cannot import name 'init_db'`

- [ ] **Step 4: Implement db.py**

Create `src/event/db.py`:

```python
import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_posts (
    post_id   INTEGER PRIMARY KEY,
    thread_id INTEGER NOT NULL,
    forum_id  INTEGER NOT NULL,
    seen_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pending_replies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id         INTEGER NOT NULL,
    thread_id       INTEGER NOT NULL,
    forum_id        INTEGER NOT NULL,
    alter_username  TEXT NOT NULL,
    reply_text      TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    auto_approve_at TEXT
);

CREATE TABLE IF NOT EXISTS posted_replies (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    alter_username TEXT NOT NULL,
    thread_id      INTEGER NOT NULL,
    post_id        INTEGER NOT NULL,
    reply_text     TEXT NOT NULL,
    posted_at      TEXT NOT NULL,
    simulated      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS rate_counters (
    alter_username TEXT NOT NULL,
    hour_key       TEXT NOT NULL,
    day_key        TEXT NOT NULL,
    hourly_count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (alter_username, hour_key)
);
"""


def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def mark_seen(conn: sqlite3.Connection, post_id: int, thread_id: int, forum_id: int) -> None:
    from datetime import datetime, timezone
    conn.execute(
        "INSERT OR IGNORE INTO seen_posts (post_id, thread_id, forum_id, seen_at) VALUES (?,?,?,?)",
        (post_id, thread_id, forum_id, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def is_seen(conn: sqlite3.Connection, post_id: int) -> bool:
    row = conn.execute("SELECT 1 FROM seen_posts WHERE post_id=?", (post_id,)).fetchone()
    return row is not None


def get_hourly_count(conn: sqlite3.Connection, alter_username: str, hour_key: str) -> int:
    row = conn.execute(
        "SELECT hourly_count FROM rate_counters WHERE alter_username=? AND hour_key=?",
        (alter_username, hour_key),
    ).fetchone()
    return row["hourly_count"] if row else 0


def get_daily_count(conn: sqlite3.Connection, alter_username: str, day_key: str) -> int:
    row = conn.execute(
        "SELECT SUM(hourly_count) AS total FROM rate_counters WHERE alter_username=? AND day_key=?",
        (alter_username, day_key),
    ).fetchone()
    return row["total"] or 0


def increment_rate(conn: sqlite3.Connection, alter_username: str, hour_key: str, day_key: str) -> None:
    conn.execute(
        """INSERT INTO rate_counters (alter_username, hour_key, day_key, hourly_count)
           VALUES (?,?,?,1)
           ON CONFLICT(alter_username, hour_key) DO UPDATE SET hourly_count = hourly_count + 1""",
        (alter_username, hour_key, day_key),
    )
    conn.commit()


def insert_pending(
    conn: sqlite3.Connection,
    post_id: int,
    thread_id: int,
    forum_id: int,
    alter_username: str,
    reply_text: str,
    auto_approve_at: str | None = None,
) -> int:
    from datetime import datetime, timezone
    cur = conn.execute(
        """INSERT INTO pending_replies
           (post_id, thread_id, forum_id, alter_username, reply_text, created_at, auto_approve_at)
           VALUES (?,?,?,?,?,?,?)""",
        (post_id, thread_id, forum_id, alter_username, reply_text,
         datetime.now(timezone.utc).isoformat(), auto_approve_at),
    )
    conn.commit()
    return cur.lastrowid


def get_pending(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM pending_replies WHERE status='pending' ORDER BY created_at"
    ).fetchall()


def get_pending_by_id(conn: sqlite3.Connection, reply_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM pending_replies WHERE id=?", (reply_id,)
    ).fetchone()


def update_status(conn: sqlite3.Connection, reply_id: int, status: str) -> None:
    conn.execute("UPDATE pending_replies SET status=? WHERE id=?", (status, reply_id))
    conn.commit()


def update_reply_text(conn: sqlite3.Connection, reply_id: int, reply_text: str) -> None:
    conn.execute("UPDATE pending_replies SET reply_text=? WHERE id=?", (reply_text, reply_id))
    conn.commit()


def insert_posted(
    conn: sqlite3.Connection,
    alter_username: str,
    thread_id: int,
    post_id: int,
    reply_text: str,
    simulated: bool = False,
) -> None:
    from datetime import datetime, timezone
    conn.execute(
        """INSERT INTO posted_replies
           (alter_username, thread_id, post_id, reply_text, posted_at, simulated)
           VALUES (?,?,?,?,?,?)""",
        (alter_username, thread_id, post_id, reply_text,
         datetime.now(timezone.utc).isoformat(), 1 if simulated else 0),
    )
    conn.commit()


def get_pending_auto_approve(conn: sqlite3.Connection, now: str | None = None) -> list[sqlite3.Row]:
    if now is None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
    return conn.execute(
        """SELECT * FROM pending_replies
           WHERE status='pending' AND auto_approve_at IS NOT NULL AND auto_approve_at <= ?
           ORDER BY auto_approve_at""",
        (now,),
    ).fetchall()


def get_daily_posts_summary(conn: sqlite3.Connection, day_key: str) -> dict[str, int]:
    rows = conn.execute(
        """SELECT alter_username, COUNT(*) AS cnt FROM posted_replies
           WHERE posted_at LIKE ? GROUP BY alter_username""",
        (f"{day_key}%",),
    ).fetchall()
    return {r["alter_username"]: r["cnt"] for r in rows}
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/event/test_db.py -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/event/__init__.py src/event/db.py tests/event/__init__.py tests/event/test_db.py
git commit -m "feat: event db layer — SQLite schema and queries"
```

---

### Task 3: Forum poller

**Files:**
- Create: `src/event/poller.py`
- Create: `tests/event/test_poller.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/event/test_poller.py`:

```python
from unittest.mock import MagicMock
from src.event.poller import fetch_new_posts, parse_post_date
from datetime import datetime, timezone, timedelta


_GETNEW_HTML = """
<table id="post100">
  <tr><td class="thead">
    <a href="forumdisplay.php?f=9">Zwam</a>
    25-05-2026, 10:00
  </td></tr>
  <tr><td class="alt1">
    <a href="showthread.php?t=200"><strong>Testthread</strong></a>
    <div class="alt2"><em>Hallo daar!</em></div>
  </td></tr>
</table>
<table id="post101">
  <tr><td class="thead">
    <a href="forumdisplay.php?f=40">Discretie</a>
    25-05-2026, 10:01
  </td></tr>
  <tr><td class="alt1">
    <a href="showthread.php?t=201"><strong>Privé</strong></a>
    <div class="alt2"><em>Geheim</em></div>
  </td></tr>
</table>
"""


def _make_session(html, logged_in=True):
    session = MagicMock()
    session.get.return_value = html
    indicator = "Log Out" if logged_in else "login"
    session.get.return_value = indicator + html
    return session


def test_fetch_new_posts_filters_excluded_forums():
    session = MagicMock()
    session.get.return_value = "Log Out" + _GETNEW_HTML
    posts = fetch_new_posts(session)
    assert all(p["forum_id"] != 40 for p in posts)
    assert any(p["forum_id"] == 9 for p in posts)


def test_fetch_new_posts_reauths_on_expired_session():
    session = MagicMock()
    session.get.side_effect = ["no session here" + _GETNEW_HTML, "Log Out" + _GETNEW_HTML]
    import os
    with __import__('unittest.mock', fromlist=['patch']).patch.dict(os.environ, {
        'FORUM_USERNAME': 'wokebot', 'FORUM_PASSWORD': 'wokebot123'
    }):
        posts = fetch_new_posts(session)
    session.login.assert_called_once()
    assert len(posts) >= 1


def test_parse_post_date_valid():
    dt = parse_post_date("25-05-2026, 14:30")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 5
    assert dt.day == 25


def test_parse_post_date_invalid():
    assert parse_post_date("") is None
    assert parse_post_date("Today, 10:30") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/event/test_poller.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement poller.py**

Create `src/event/poller.py`:

```python
import os
import logging
from datetime import datetime, timezone, timedelta

from src.persona.scraper import parse_posts_page

_EXCLUDED_FORUM_IDS = {20, 29, 40, 42}


def fetch_new_posts(session) -> list[dict]:
    """Fetch new posts since last visit. Re-authenticates if session expired."""
    html = session.get("search.php?do=getnew")

    if "Log Out" not in html and "User CP" not in html:
        logging.info("Scanner session expired — re-authenticating")
        session.login(os.getenv("FORUM_USERNAME", ""), os.getenv("FORUM_PASSWORD", ""))
        html = session.get("search.php?do=getnew")

    posts = parse_posts_page(html)
    return [p for p in posts if p["forum_id"] not in _EXCLUDED_FORUM_IDS]


def parse_post_date(date_str: str) -> datetime | None:
    """Parse VBulletin date 'DD-MM-YYYY, HH:MM' to timezone-aware datetime (GMT+2)."""
    try:
        dt = datetime.strptime(date_str.strip(), "%d-%m-%Y, %H:%M")
        return dt.replace(tzinfo=timezone(timedelta(hours=2)))
    except (ValueError, AttributeError):
        return None
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/event/test_poller.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/event/poller.py tests/event/test_poller.py
git commit -m "feat: event poller — getnew fetch with re-auth guard"
```

---

### Task 4: Decision pipeline

**Files:**
- Create: `src/event/gates.py`
- Create: `tests/event/test_gates.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/event/test_gates.py`:

```python
import sqlite3
import pytest
from src.event.db import init_db, increment_rate
from src.event.gates import evaluate_post
from src.persona.models import PersonaProfile


def _make_profile(reversed_username="ejdar", forum_name="Zwam", weight=0.8, hourly_cap=3, daily_cap=10):
    p = PersonaProfile.from_alter_ego({
        "user_id": 1, "original_username": "radje", "reversed_username": reversed_username,
        "post_count": 100, "last_active": "2023-01-01",
    })
    p.topic_weights = {forum_name: weight}
    p.hourly_cap = hourly_cap
    p.daily_cap = daily_cap
    return p


def _make_post(forum_id=9, forum_name="Zwam", content="Hallo"):
    return {"post_id": 1, "thread_id": 100, "forum_id": forum_id,
            "forum_name": forum_name, "content": content}


@pytest.fixture
def conn():
    c = init_db(":memory:")
    yield c
    c.close()


def test_excluded_forum_skips_all(conn):
    profile = _make_profile()
    post = _make_post(forum_id=40, forum_name="Discretie")
    assert evaluate_post(post, [profile], conn) == []


def test_low_relevance_skips(conn):
    profile = _make_profile(weight=0.1)
    post = _make_post()
    # weight 0.1 < 0.2 threshold → always skip
    results = [evaluate_post(post, [profile], conn) for _ in range(20)]
    assert all(r == [] for r in results)


def test_mention_bypasses_relevance(conn):
    profile = _make_profile(forum_name="Videogames", weight=0.0)
    post = _make_post(forum_name="Zwam", content="ejdar wat denk jij?")
    # ejdar is mentioned → relevance bypassed; probability bypassed
    # with weight=0.0 for a different forum but mention → must pass
    passed = evaluate_post(post, [profile], conn)
    assert profile in passed


def test_rate_limit_blocks(conn):
    profile = _make_profile(hourly_cap=2)
    post = _make_post()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y-%m-%dT%H")
    day_key = now.strftime("%Y-%m-%d")
    increment_rate(conn, "ejdar", hour_key, day_key)
    increment_rate(conn, "ejdar", hour_key, day_key)
    # hourly_count == hourly_cap → blocked
    result = evaluate_post(post, [profile], conn)
    assert result == []


def test_pile_on_guard_keeps_max_two(conn):
    profiles = [_make_profile(f"user{i}", weight=0.9) for i in range(5)]
    post = _make_post()
    result = evaluate_post(post, profiles, conn)
    assert len(result) <= 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/event/test_gates.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement gates.py**

Create `src/event/gates.py`:

```python
import random
import logging
from datetime import datetime, timezone

from src.persona.models import PersonaProfile
from src.event import db

_EXCLUDED_FORUM_IDS = {20, 29, 40, 42}
_RELEVANCE_THRESHOLD = 0.2
_MAX_RESPONDERS = 2


def evaluate_post(
    post: dict,
    profiles: list[PersonaProfile],
    conn,
) -> list[PersonaProfile]:
    """Return up to 2 profiles that should respond to this post."""
    if post["forum_id"] in _EXCLUDED_FORUM_IDS:
        return []

    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y-%m-%dT%H")
    day_key = now.strftime("%Y-%m-%d")
    forum_name = post.get("forum_name", "")
    content = post.get("content", "")

    passed: list[tuple[PersonaProfile, float]] = []

    for profile in profiles:
        mentioned = profile.reversed_username.lower() in content.lower()

        if not mentioned:
            weight = profile.topic_weights.get(forum_name, 0.0)
            if weight < _RELEVANCE_THRESHOLD:
                continue
            if random.random() >= weight:
                continue
        else:
            weight = profile.topic_weights.get(forum_name, 1.0)

        hourly = db.get_hourly_count(conn, profile.reversed_username, hour_key)
        daily = db.get_daily_count(conn, profile.reversed_username, day_key)
        if hourly >= profile.hourly_cap or daily >= profile.daily_cap:
            logging.debug("Rate limit hit for %s", profile.reversed_username)
            continue

        passed.append((profile, weight))

    passed.sort(key=lambda x: x[1], reverse=True)
    return [p for p, _ in passed[:_MAX_RESPONDERS]]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/event/test_gates.py -v
```
Expected: all PASS (note: probability-based tests use deterministic enough inputs to pass reliably)

- [ ] **Step 5: Commit**

```bash
git add src/event/gates.py tests/event/test_gates.py
git commit -m "feat: event gates — six-gate decision pipeline"
```

---

### Task 5: Thread scraper

**Files:**
- Create: `src/event/thread_scraper.py`
- Create: `tests/event/test_thread_scraper.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/event/test_thread_scraper.py`:

```python
from unittest.mock import MagicMock
from src.event.thread_scraper import parse_thread_page, fetch_thread_context, _preprocess_content
from bs4 import BeautifulSoup


_THREAD_HTML = """
<html><body>
<table id="post10">
  <tr><td class="thead">01-01-2026, 10:00</td></tr>
  <tr><td>
    <div id="postmenu_10"><a href="#">Alice</a></div>
    <div id="post_message_10">Eerste bericht</div>
  </td></tr>
</table>
<table id="post11">
  <tr><td class="thead">01-01-2026, 11:00</td></tr>
  <tr><td>
    <div id="postmenu_11"><a href="#">Bob</a></div>
    <div id="post_message_11">
      <img src="images_shrimpcity/smilies/E13.gif" alt="" title="Wink"/>
      Tweede bericht
    </div>
  </td></tr>
</table>
<table id="post12">
  <tr><td class="thead">01-01-2026, 12:00</td></tr>
  <tr><td>
    <div id="postmenu_12"><a href="#">Carol</a></div>
    <div id="post_message_12">
      <img src="images_shrimpcity/smilies/smile.gif" alt=":)" title="Smile"/>
      Derde bericht
    </div>
  </td></tr>
</table>
</body></html>
"""

_PREV_PAGE_HTML = """
<html><body>
<a href="showthread.php?t=100&amp;page=4">&lt;</a>
<table id="post7">
  <tr><td class="thead">01-01-2026, 09:00</td></tr>
  <tr><td>
    <div id="postmenu_7"><a href="#">Dave</a></div>
    <div id="post_message_7">Vorig bericht</div>
  </td></tr>
</table>
</body></html>
"""


def test_parse_thread_page_returns_posts():
    posts = parse_thread_page(_THREAD_HTML)
    assert len(posts) == 3
    assert posts[0]["post_id"] == 10
    assert posts[0]["author"] == "Alice"
    assert "Eerste bericht" in posts[0]["content"]


def test_preprocess_smilies_use_title():
    posts = parse_thread_page(_THREAD_HTML)
    assert "(Wink)" in posts[1]["content"]
    assert "Tweede bericht" in posts[1]["content"]


def test_preprocess_smilies_with_alt_text():
    # When alt is non-empty and not a smiley path, use alt
    html = """<div id="post_message_1"><img src="other.gif" alt=":D"/> tekst</div>"""
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("div")
    result = _preprocess_content(tag)
    assert ":D" in result


def test_preprocess_image_only_becomes_afbeelding():
    html = """<div id="post_message_1"><img src="uploads/photo.jpg" alt=""/></div>"""
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("div")
    result = _preprocess_content(tag)
    assert result == "[afbeelding]"


def test_fetch_thread_context_target_not_first(monkeypatch):
    session = MagicMock()
    session.get.return_value = _THREAD_HTML
    context = fetch_thread_context(session, post_id=12, n=3)
    assert context[-1]["post_id"] == 12
    assert len(context) == 3


def test_fetch_thread_context_fetches_prev_page_when_target_is_first(monkeypatch):
    session = MagicMock()
    session.get.side_effect = [_THREAD_HTML, _PREV_PAGE_HTML]
    # post 10 is at index 0 — should fetch previous page
    context = fetch_thread_context(session, post_id=10, n=3)
    assert session.get.call_count == 2
    assert context[-1]["post_id"] == 10


def test_fetch_thread_context_returns_empty_if_post_not_found():
    session = MagicMock()
    session.get.return_value = _THREAD_HTML
    context = fetch_thread_context(session, post_id=999)
    assert context == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/event/test_thread_scraper.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement thread_scraper.py**

Create `src/event/thread_scraper.py`:

```python
import re
import logging
from bs4 import BeautifulSoup, Tag

_POST_ID_RE = re.compile(r"^post(\d+)$")
_PAGE_LINK_RE = re.compile(r"page=\d+")


def _preprocess_content(tag: Tag) -> str:
    """Convert post_message div to plain text, handling smilies and images."""
    for img in tag.find_all("img"):
        src = img.get("src", "")
        title = img.get("title", "")
        alt = img.get("alt", "")
        if "smilies" in src:
            img.replace_with(f"({title})" if title else "")
        elif alt:
            img.replace_with(alt)
        else:
            img.replace_with("[afbeelding]")
    return tag.get_text(separator=" ", strip=True)


def parse_thread_page(html: str) -> list[dict]:
    """Parse posts from a showthread.php page."""
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    for table in soup.find_all("table", id=_POST_ID_RE):
        post_id = int(_POST_ID_RE.match(table["id"]).group(1))
        pm = table.find("div", id=f"postmenu_{post_id}")
        author_link = pm.find("a") if pm else None
        author = author_link.get_text(strip=True) if author_link else ""
        msg = table.find("div", id=f"post_message_{post_id}")
        content = _preprocess_content(msg) if msg else ""
        thead = table.find("td", class_="thead")
        date = thead.get_text(separator=" ", strip=True) if thead else ""
        posts.append({"post_id": post_id, "author": author, "content": content, "date": date})
    return posts


def _find_prev_page_url(html: str) -> str | None:
    """Return href of the previous-page pagination link (text '<')."""
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=_PAGE_LINK_RE):
        if a.get_text(strip=True) == "<":
            return a["href"]
    return None


def fetch_thread_context(session, post_id: int, n: int = 5) -> list[dict]:
    """Return up to n posts ending with post_id. Fetches previous page if needed."""
    html = session.get(f"showthread.php?p={post_id}")
    posts = parse_thread_page(html)
    ids = [p["post_id"] for p in posts]

    if post_id not in ids:
        logging.warning("post %d not found in thread page", post_id)
        return []

    idx = ids.index(post_id)

    if idx == 0:
        prev_url = _find_prev_page_url(html)
        if prev_url:
            prev_html = session.get(prev_url)
            prev_posts = parse_thread_page(prev_html)
            combined = prev_posts + [posts[0]]
            return combined[-n:]
        return [posts[0]]

    return posts[max(0, idx - (n - 1)):idx + 1]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/event/test_thread_scraper.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/event/thread_scraper.py tests/event/test_thread_scraper.py
git commit -m "feat: event thread scraper — context fetch with prev-page fallback"
```

---

### Task 6: Reply generator

**Files:**
- Create: `src/event/generator.py`
- Create: `tests/event/test_generator.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/event/test_generator.py`:

```python
from unittest.mock import MagicMock
from src.event.generator import generate_reply
from src.persona.models import PersonaProfile


def _make_profile():
    p = PersonaProfile.from_alter_ego({
        "user_id": 1, "original_username": "radje", "reversed_username": "ejdar",
        "post_count": 100, "last_active": "2023-01-01",
    })
    p.persona_summary = "Direct gamer"
    p.example_posts = ["da klopt nie"]
    return p


_CONTEXT = [
    {"post_id": 10, "author": "Alice", "content": "Wie speelt er nog Zelda?"},
    {"post_id": 11, "author": "Bob", "content": "Ik heb het al uitgespeeld"},
    {"post_id": 12, "author": "Carol", "content": "Is het goed?"},
]
_TRIGGERING = {"post_id": 12, "author": "Carol", "content": "Is het goed?"}


def _make_client(reply_text="Da valt mee"):
    client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=reply_text)]
    msg.stop_reason = "stop"
    client.messages.create.return_value = msg
    return client


def test_generate_reply_calls_api():
    client = _make_client()
    result = generate_reply(client, _make_profile(), _TRIGGERING, _CONTEXT)
    assert result == "Da valt mee"
    client.messages.create.assert_called_once()


def test_generate_reply_includes_context_in_prompt():
    client = _make_client()
    generate_reply(client, _make_profile(), _TRIGGERING, _CONTEXT)
    call_kwargs = client.messages.create.call_args[1]
    user_msg = call_kwargs["messages"][0]["content"]
    assert "Alice" in user_msg
    assert "Wie speelt er nog Zelda?" in user_msg
    assert "Carol" in user_msg
    assert "Is het goed?" in user_msg


def test_generate_reply_prompt_uses_reversed_username():
    client = _make_client()
    generate_reply(client, _make_profile(), _TRIGGERING, _CONTEXT)
    call_kwargs = client.messages.create.call_args[1]
    user_msg = call_kwargs["messages"][0]["content"]
    assert "ejdar" in user_msg


def test_generate_reply_appends_afgekapt_on_max_tokens():
    client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text="Lang antwoord")]
    msg.stop_reason = "max_tokens"
    client.messages.create.return_value = msg
    result = generate_reply(client, _make_profile(), _TRIGGERING, _CONTEXT)
    assert result == "Lang antwoord [afgekapt]"


def test_generate_reply_raises_on_api_error():
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("API down")
    import pytest
    with pytest.raises(RuntimeError):
        generate_reply(client, _make_profile(), _TRIGGERING, _CONTEXT)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/event/test_generator.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement generator.py**

Create `src/event/generator.py`:

```python
import logging
from src.persona.models import PersonaProfile
from src.persona.generator import build_system_prompt

_MODEL = "claude-sonnet-4-6"


def generate_reply(
    client,
    profile: PersonaProfile,
    triggering_post: dict,
    context_posts: list[dict],
) -> str:
    """Generate a reply to triggering_post using context_posts as thread context."""
    system = build_system_prompt(profile)

    context_lines = "\n".join(
        f"{p['author']}: {p['content']}"
        for p in context_posts
        if p["post_id"] != triggering_post["post_id"]
    )

    user_content = (
        f"[Vorige berichten in de thread:]\n{context_lines}\n\n"
        f"[Nieuw bericht van {triggering_post['author']}:]\n"
        f"\"{triggering_post['content']}\"\n\n"
        f"Schrijf een reactie zoals {profile.reversed_username} dat zou doen."
    )

    response = client.messages.create(
        model=_MODEL,
        max_tokens=400,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    reply = response.content[0].text
    if response.stop_reason == "max_tokens":
        reply += " [afgekapt]"
    return reply
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/event/test_generator.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/event/generator.py tests/event/test_generator.py
git commit -m "feat: event generator — reply generation with thread context"
```

---

### Task 7: VBulletin poster

**Files:**
- Create: `src/event/poster.py`
- Create: `tests/event/test_poster.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/event/test_poster.py`:

```python
from unittest.mock import MagicMock, patch
from src.event.poster import post_reply


def _make_form_html(token="abc123", thread_id=21666):
    return f"""
    <form action="newreply.php?do=postreply&t={thread_id}" method="post">
      <input type="hidden" name="securitytoken" value="{token}"/>
      <input type="hidden" name="do" value="postreply"/>
      <input type="hidden" name="t" value="{thread_id}"/>
      <input type="hidden" name="s" value=""/>
      <textarea name="message"></textarea>
      <input type="submit" name="sbutton" value="Submit Reply"/>
    </form>
    """


def test_post_reply_success():
    with patch("src.event.poster.VBulletinSession") as MockSession:
        session = MagicMock()
        MockSession.return_value = session
        session.login.return_value = True
        session.get.return_value = _make_form_html()
        session.post.return_value = "<html>thread content, no errors</html>"

        result = post_reply("ejdar", "password", 21666, "Da is goed :D")

    assert result is True
    session.login.assert_called_once_with("ejdar", "password")
    call_kwargs = session.post.call_args
    posted_data = call_kwargs[0][1]
    assert posted_data["message"] == "Da is goed :D"
    assert posted_data["securitytoken"] == "abc123"
    assert posted_data["wysiwyg"] == "0"


def test_post_reply_returns_false_on_login_failure():
    with patch("src.event.poster.VBulletinSession") as MockSession:
        session = MagicMock()
        MockSession.return_value = session
        session.login.return_value = False
        result = post_reply("ejdar", "wrongpass", 21666, "test")
    assert result is False


def test_post_reply_returns_false_on_error_block():
    with patch("src.event.poster.VBulletinSession") as MockSession:
        session = MagicMock()
        MockSession.return_value = session
        session.login.return_value = True
        session.get.return_value = _make_form_html()
        session.post.return_value = '<div class="blockrow error">U heeft geen toestemming</div>'
        result = post_reply("ejdar", "password", 21666, "test")
    assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/event/test_poster.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement poster.py**

Create `src/event/poster.py`:

```python
import logging
from bs4 import BeautifulSoup
from src.session import VBulletinSession


def post_reply(alter_username: str, password: str, thread_id: int, message: str) -> bool:
    """Login as alter ego and post reply. Returns True on success."""
    session = VBulletinSession()
    if not session.login(alter_username, password):
        logging.warning("Login failed for alter %s", alter_username)
        return False

    html = session.get(f"newreply.php?t={thread_id}&noquote=1")
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", action=lambda a: a and "postreply" in str(a))
    if not form:
        logging.warning("Reply form not found for thread %d", thread_id)
        return False

    data: dict[str, str] = {}
    for inp in form.find_all("input"):
        if inp.get("type") == "hidden" and inp.get("name"):
            data[inp["name"]] = inp.get("value", "")

    data["message"] = message
    data["wysiwyg"] = "0"
    data["sbutton"] = "Submit Reply"

    resp = session.post(f"newreply.php?do=postreply&t={thread_id}", data)
    soup2 = BeautifulSoup(resp, "html.parser")
    if soup2.find("div", class_="blockrow error") or soup2.find("div", class_="error"):
        logging.warning("VBulletin returned error for alter %s thread %d", alter_username, thread_id)
        return False
    return True
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/event/test_poster.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/event/poster.py tests/event/test_poster.py
git commit -m "feat: event poster — fresh-session VBulletin reply posting"
```

---

### Task 8: Flask review queue

**Files:**
- Create: `src/event/webui.py`
- Create: `tests/event/test_webui.py`
- Modify: `requirements.txt` (add flask)

- [ ] **Step 1: Add Flask to requirements**

In `requirements.txt` add:
```
flask==3.1.0
```

Install it:
```bash
pip install flask==3.1.0
```

- [ ] **Step 2: Write the failing tests**

Create `tests/event/test_webui.py`:

```python
import sqlite3
import pytest
from unittest.mock import MagicMock
from src.event.db import init_db, insert_pending
from src.event.webui import create_app
from src.persona.models import PersonaProfile


def _make_profile(reversed_username="ejdar"):
    p = PersonaProfile.from_alter_ego({
        "user_id": 1, "original_username": "radje", "reversed_username": reversed_username,
        "post_count": 100, "last_active": "2023-01-01",
    })
    p.persona_summary = "Direct gamer"
    p.example_posts = []
    return p


@pytest.fixture
def app():
    conn = init_db(":memory:")
    client = MagicMock()
    profiles = [_make_profile()]
    flask_app = create_app(conn, client, profiles, "testpass", live_mode=False)
    flask_app.config["TESTING"] = True
    yield flask_app, conn
    conn.close()


def test_index_shows_pending_replies(app):
    flask_app, conn = app
    insert_pending(conn, 1, 100, 9, "ejdar", "Da is goed")
    with flask_app.test_client() as c:
        resp = c.get("/")
    assert resp.status_code == 200
    assert b"ejdar" in resp.data
    assert b"Da is goed" in resp.data


def test_discard_removes_from_queue(app):
    flask_app, conn = app
    reply_id = insert_pending(conn, 1, 100, 9, "ejdar", "reply")
    with flask_app.test_client() as c:
        resp = c.post(f"/reply/{reply_id}/discard")
    assert resp.status_code == 204
    with flask_app.test_client() as c:
        resp = c.get("/")
    assert b"reply" not in resp.data


def test_edit_updates_reply_text(app):
    flask_app, conn = app
    reply_id = insert_pending(conn, 1, 100, 9, "ejdar", "origineel")
    with flask_app.test_client() as c:
        resp = c.post(f"/reply/{reply_id}/edit", data={"reply_text": "aangepast"})
    assert resp.status_code == 204
    from src.event.db import get_pending_by_id
    row = get_pending_by_id(conn, reply_id)
    assert row["reply_text"] == "aangepast"


def test_status_endpoint(app):
    flask_app, conn = app
    with flask_app.test_client() as c:
        resp = c.get("/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "live_mode" in data
    assert data["live_mode"] is False
    assert "pending_count" in data
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/event/test_webui.py -v
```
Expected: FAIL

- [ ] **Step 4: Implement webui.py**

Create `src/event/webui.py`:

```python
import logging
import os
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template_string

from src.event import db
from src.event import thread_scraper
from src.event import generator as event_generator
from src.event import poster
from src.session import VBulletinSession

_QUEUE_TEMPLATE = """<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="utf-8">
<title>Shrimp Resurrect — Review Queue</title>
<style>
  body { font-family: monospace; max-width: 900px; margin: 40px auto; padding: 0 20px; background: #1a1a1a; color: #ccc; }
  h1 { color: #fff; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 0.8em; }
  .badge-live { background: #c0392b; color: #fff; }
  .badge-sim  { background: #2980b9; color: #fff; }
  .card { border: 1px solid #444; margin: 16px 0; padding: 16px; background: #252525; }
  .card h3 { margin: 0 0 8px; color: #fff; }
  .post-excerpt { background: #333; padding: 8px; margin: 8px 0; color: #aaa; }
  .reply-text { background: #1e3a1e; padding: 8px; margin: 8px 0; color: #9f9; white-space: pre-wrap; }
  .actions { margin-top: 10px; }
  button { margin-right: 8px; padding: 6px 14px; cursor: pointer; }
  textarea { width: 100%; height: 80px; background: #333; color: #ccc; border: 1px solid #555; padding: 6px; }
  .edit-area { display: none; margin-top: 8px; }
  .empty { color: #888; padding: 20px; text-align: center; }
</style>
</head>
<body>
<h1>Shrimp Resurrect
  <span class="badge {% if live_mode %}badge-live{% else %}badge-sim{% endif %}">
    {% if live_mode %}LIVE{% else %}SIMULATIE{% endif %}
  </span>
</h1>
<p><a href="/status" style="color:#888">status JSON</a></p>
{% if not replies %}
  <p class="empty">Geen wachtende reacties.</p>
{% endif %}
{% for r in replies %}
<div class="card">
  <h3>
    <a href="{{ forum_url }}/showthread.php?t={{ r['thread_id'] }}" target="_blank" style="color:#fff">
      Thread #{{ r['thread_id'] }}
    </a>
    &nbsp;&mdash;&nbsp;<strong>{{ r['alter_username'] }}</strong>
    {% if r['auto_approve_at'] %}<small style="color:#888">(auto: {{ r['auto_approve_at'][:16] }})</small>{% endif %}
  </h3>
  <div class="post-excerpt">post #{{ r['post_id'] }}</div>
  <div class="reply-text">{{ r['reply_text'] }}</div>
  <div class="actions">
    <form method="post" action="/reply/{{ r['id'] }}/approve" style="display:inline">
      <button type="submit" style="background:#27ae60;color:#fff">✓ Goedkeuren</button>
    </form>
    <button onclick="toggleEdit({{ r['id'] }})" style="background:#2980b9;color:#fff">✎ Bewerken</button>
    <form method="post" action="/reply/{{ r['id'] }}/discard" style="display:inline">
      <button type="submit" style="background:#c0392b;color:#fff">✗ Verwijderen</button>
    </form>
    <form method="post" action="/reply/{{ r['id'] }}/regenerate" style="display:inline">
      <button type="submit" style="background:#8e44ad;color:#fff">↺ Opnieuw genereren</button>
    </form>
  </div>
  <div class="edit-area" id="edit-{{ r['id'] }}">
    <form method="post" action="/reply/{{ r['id'] }}/edit">
      <textarea name="reply_text">{{ r['reply_text'] }}</textarea>
      <button type="submit" style="background:#27ae60;color:#fff;margin-top:6px">Opslaan &amp; Goedkeuren</button>
    </form>
  </div>
</div>
{% endfor %}
<script>
function toggleEdit(id) {
  var el = document.getElementById('edit-' + id);
  el.style.display = el.style.display === 'none' || el.style.display === '' ? 'block' : 'none';
}
</script>
</body>
</html>"""


def _do_approve(conn, entry: dict, alter_password: str, live_mode: bool) -> bool:
    if live_mode:
        success = poster.post_reply(
            entry["alter_username"], alter_password,
            entry["thread_id"], entry["reply_text"],
        )
        status = "approved" if success else "failed"
    else:
        success = True
        status = "approved"

    db.update_status(conn, entry["id"], status)
    db.insert_posted(
        conn, entry["alter_username"], entry["thread_id"],
        entry["post_id"], entry["reply_text"], simulated=not live_mode,
    )

    if live_mode and success:
        now = datetime.now(timezone.utc)
        db.increment_rate(conn, entry["alter_username"],
                          now.strftime("%Y-%m-%dT%H"), now.strftime("%Y-%m-%d"))
    return success


def create_app(conn, client, profiles, alter_password: str, live_mode: bool) -> Flask:
    app = Flask(__name__)
    profile_map = {p.reversed_username: p for p in profiles}
    forum_url = os.getenv("FORUM_URL", "https://forum.shrimprefuge.be")

    @app.route("/")
    def index():
        pending = [dict(r) for r in db.get_pending(conn)]
        return render_template_string(
            _QUEUE_TEMPLATE, replies=pending, live_mode=live_mode, forum_url=forum_url
        )

    @app.route("/reply/<int:reply_id>/approve", methods=["POST"])
    def approve(reply_id):
        entry = db.get_pending_by_id(conn, reply_id)
        if not entry:
            return "Not found", 404
        _do_approve(conn, dict(entry), alter_password, live_mode)
        return ("", 204) if request.headers.get("X-Requested-With") else \
               ('<meta http-equiv="refresh" content="0;url=/">', 200)

    @app.route("/reply/<int:reply_id>/discard", methods=["POST"])
    def discard(reply_id):
        db.update_status(conn, reply_id, "discarded")
        return ("", 204) if request.headers.get("X-Requested-With") else \
               ('<meta http-equiv="refresh" content="0;url=/">', 200)

    @app.route("/reply/<int:reply_id>/edit", methods=["POST"])
    def edit(reply_id):
        new_text = request.form.get("reply_text", "").strip()
        if not new_text:
            return "reply_text required", 400
        db.update_reply_text(conn, reply_id, new_text)
        entry = db.get_pending_by_id(conn, reply_id)
        if not entry:
            return "Not found", 404
        _do_approve(conn, dict(entry), alter_password, live_mode)
        return ("", 204) if request.headers.get("X-Requested-With") else \
               ('<meta http-equiv="refresh" content="0;url=/">', 200)

    @app.route("/reply/<int:reply_id>/regenerate", methods=["POST"])
    def regenerate(reply_id):
        entry = db.get_pending_by_id(conn, reply_id)
        if not entry:
            return "Not found", 404
        profile = profile_map.get(entry["alter_username"])
        if not profile:
            return "Profile not found", 404
        try:
            scanner = VBulletinSession()
            scanner.login(os.getenv("FORUM_USERNAME", ""), os.getenv("FORUM_PASSWORD", ""))
            context = thread_scraper.fetch_thread_context(scanner, entry["post_id"])
            triggering = next(
                (p for p in context if p["post_id"] == entry["post_id"]),
                {"post_id": entry["post_id"], "author": "?", "content": ""},
            )
            new_text = event_generator.generate_reply(client, profile, triggering, context)
            db.update_reply_text(conn, reply_id, new_text)
        except Exception as exc:
            logging.warning("Regenerate failed for reply %d: %s", reply_id, exc)
            return "Generation failed", 500
        return ("", 204) if request.headers.get("X-Requested-With") else \
               ('<meta http-equiv="refresh" content="0;url=/">', 200)

    @app.route("/status")
    def status():
        day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return jsonify({
            "live_mode": live_mode,
            "pending_count": len(db.get_pending(conn)),
            "posts_today": db.get_daily_posts_summary(conn, day_key),
        })

    return app
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/event/test_webui.py -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/event/webui.py tests/event/test_webui.py requirements.txt
git commit -m "feat: event webui — Flask review queue with approve/edit/discard/regenerate"
```

---

### Task 9: Entry point and polling loop

**Files:**
- Create: `event.py`
- Modify: `.env.example`
- Modify: `.gitignore`

- [ ] **Step 1: Update .env.example**

Add to `.env.example`:

```
ALTER_PASSWORD=your_shared_alter_password_here
LIVE_MODE=false
LOOKBACK_HOURS=48
POLL_INTERVAL=300
```

- [ ] **Step 2: Update .gitignore**

Add `event.db` to `.gitignore`.

- [ ] **Step 3: Create event.py**

Create `event.py`:

```python
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from src.event import db, gates, thread_scraper
from src.event import generator as event_generator
from src.event.poller import fetch_new_posts, parse_post_date
from src.event.webui import create_app, _do_approve
from src.persona.models import PersonaProfile
from src.session import VBulletinSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
load_dotenv()


def _load_profiles(personas_dir: str) -> list[PersonaProfile]:
    profiles = []
    for path in Path(personas_dir).glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            profile = PersonaProfile.from_dict(data)
            if profile.is_approved:
                profiles.append(profile)
        except Exception as exc:
            logging.warning("Could not load %s: %s", path, exc)
    return profiles


def _is_image_only(content: str) -> bool:
    return not content.replace("[afbeelding]", "").strip()


def _poll_once(scanner, profiles, conn, client, alter_password, live_mode, cutoff):
    try:
        new_posts = fetch_new_posts(scanner)
    except Exception as exc:
        logging.error("Poll failed: %s", exc)
        return

    for post in new_posts:
        if db.is_seen(conn, post["post_id"]):
            continue

        post_dt = parse_post_date(post.get("date", ""))
        if post_dt and post_dt < cutoff:
            db.mark_seen(conn, post["post_id"], post["thread_id"], post["forum_id"])
            continue

        respondents = gates.evaluate_post(post, profiles, conn)

        for profile in respondents:
            if _is_image_only(post.get("content", "")):
                continue

            try:
                context = thread_scraper.fetch_thread_context(scanner, post["post_id"])
            except Exception as exc:
                logging.warning("Context fetch failed for post %d: %s", post["post_id"], exc)
                context = []

            triggering = next(
                (p for p in context if p["post_id"] == post["post_id"]),
                {"post_id": post["post_id"], "author": "?", "content": post.get("content", "")},
            )

            try:
                reply_text = event_generator.generate_reply(client, profile, triggering, context)
            except Exception as exc:
                logging.warning("Generation failed for post %d / %s: %s",
                                post["post_id"], profile.reversed_username, exc)
                continue

            auto_approve_at = None
            if profile.auto_approve_minutes is not None:
                auto_approve_at = (
                    datetime.now(timezone.utc) + timedelta(minutes=profile.auto_approve_minutes)
                ).isoformat()

            db.insert_pending(
                conn, post["post_id"], post["thread_id"], post["forum_id"],
                profile.reversed_username, reply_text, auto_approve_at,
            )
            logging.info("Queued reply from %s for post %d", profile.reversed_username, post["post_id"])

        db.mark_seen(conn, post["post_id"], post["thread_id"], post["forum_id"])


def main():
    required_vars = ["ANTHROPIC_API_KEY", "FORUM_USERNAME", "FORUM_PASSWORD", "ALTER_PASSWORD"]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        raise SystemExit(f"Missing env vars: {', '.join(missing)}")

    live_mode = os.getenv("LIVE_MODE", "false").lower() == "true"
    lookback_hours = int(os.getenv("LOOKBACK_HOURS", "48"))
    poll_interval = int(os.getenv("POLL_INTERVAL", "300"))
    alter_password = os.getenv("ALTER_PASSWORD")

    profiles = _load_profiles("personas")
    if not profiles:
        raise SystemExit("No approved personas found in personas/")
    logging.info("Loaded %d approved personas", len(profiles))

    conn = db.init_db("event.db")

    scanner = VBulletinSession()
    if not scanner.login(os.getenv("FORUM_USERNAME"), os.getenv("FORUM_PASSWORD")):
        raise SystemExit("Scanner login failed")
    logging.info("Scanner logged in")

    client = anthropic.Anthropic()

    app = create_app(conn, client, profiles, alter_password, live_mode)
    flask_thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False),
        daemon=True,
    )
    flask_thread.start()
    logging.info("Review queue: http://localhost:5000 [%s]", "LIVE" if live_mode else "SIMULATIE")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    logging.info("Processing posts newer than %s (LOOKBACK_HOURS=%d)", cutoff.isoformat(), lookback_hours)

    while True:
        _poll_once(scanner, profiles, conn, client, alter_password, live_mode, cutoff)

        for entry in db.get_pending_auto_approve(conn):
            logging.info("Auto-approving reply %d for %s", entry["id"], entry["alter_username"])
            _do_approve(conn, dict(entry), alter_password, live_mode)

        time.sleep(poll_interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Shutting down")
```

- [ ] **Step 4: Run full test suite**

```bash
pytest -q
```
Expected: all existing tests pass (event.py has no unit tests — it's a thin coordinator of already-tested components)

- [ ] **Step 5: Smoke-test in simulation mode**

Ensure `.env` has `LIVE_MODE=false` and `ANTHROPIC_API_KEY=your_key_here` (placeholder is fine, personas load without API). Run:

```bash
python event.py
```

Expected output:
```
INFO Loaded N approved personas
INFO Scanner logged in
INFO Review queue: http://localhost:5000 [SIMULATIE]
INFO Processing posts newer than ...
```

Open `http://localhost:5000` — should show empty queue page with SIMULATIE badge. Ctrl+C to stop.

- [ ] **Step 6: Commit**

```bash
git add event.py .env.example .gitignore
git commit -m "feat: event.py — polling loop and entry point"
```

---

## Self-Review Checklist

Run before marking the plan complete:

```bash
pytest -q                          # all tests green
python -c "import src.event.db"    # import check
python -c "import src.event.webui" # import check
```
