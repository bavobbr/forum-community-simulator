# Stats Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the operator a live per-persona view of hourly/daily reply counts, cap status, and reset timing — on both the existing queue page (summary bar) and a new `/stats` page — while also fixing rate counters so they increment in simulation mode.

**Architecture:** Change `get_daily_count` to a rolling 24h window, fix `_do_approve` to count in simulation, add `get_all_rate_stats` to the DB layer, add a `_build_persona_stats` helper in `webui.py`, wire it into both the existing `/` route and a new `/stats` route.

**Tech Stack:** Python, Flask, SQLite, server-side Jinja2 (`render_template_string`).

---

## File map

| File | Change |
|---|---|
| `src/event/db.py` | Change `get_daily_count` to rolling 24h; add `get_all_rate_stats` |
| `src/event/gates.py` | Update `evaluate_post` call to use rolling cutoff instead of `day_key` |
| `src/event/webui.py` | Fix simulation rate counting; add `_build_persona_stats`, `_STATS_TEMPLATE`, `/stats` route; update `_QUEUE_TEMPLATE` and `/` route with summary bar + auto-refresh |
| `tests/event/test_db.py` | Update 2 existing tests for new signature; add 4 new tests |

---

### Task 1: Rolling 24h daily count in `db.py`

**Files:**
- Modify: `src/event/db.py`
- Test: `tests/event/test_db.py`

- [ ] **Step 1: Update the two existing `get_daily_count` tests to use the new signature**

In `tests/event/test_db.py`, replace `test_rate_counters` and `test_daily_count_spans_hours` with:

```python
def test_rate_counters(conn):
    assert get_hourly_count(conn, "ejdar", "2026-05-25T14") == 0
    assert get_daily_count(conn, "ejdar", "2026-05-25T00") == 0
    increment_rate(conn, "ejdar", "2026-05-25T14", "2026-05-25")
    increment_rate(conn, "ejdar", "2026-05-25T14", "2026-05-25")
    assert get_hourly_count(conn, "ejdar", "2026-05-25T14") == 2
    assert get_daily_count(conn, "ejdar", "2026-05-25T00") == 2


def test_daily_count_spans_hours(conn):
    increment_rate(conn, "ejdar", "2026-05-25T13", "2026-05-25")
    increment_rate(conn, "ejdar", "2026-05-25T14", "2026-05-25")
    assert get_daily_count(conn, "ejdar", "2026-05-25T00") == 2
    assert get_hourly_count(conn, "ejdar", "2026-05-25T13") == 1
    assert get_hourly_count(conn, "ejdar", "2026-05-25T14") == 1
```

Also add a new test below them:

```python
def test_daily_count_excludes_old_hours(conn):
    increment_rate(conn, "ejdar", "2026-05-25T10", "2026-05-25")
    increment_rate(conn, "ejdar", "2026-05-25T14", "2026-05-25")
    # cutoff at T12 → T10 excluded, T14 included
    assert get_daily_count(conn, "ejdar", "2026-05-25T12") == 1
```

- [ ] **Step 2: Run the updated tests to verify they fail**

```bash
pytest tests/event/test_db.py::test_rate_counters tests/event/test_db.py::test_daily_count_spans_hours tests/event/test_db.py::test_daily_count_excludes_old_hours -v
```

Expected: `FAILED` — `get_daily_count` still uses `day_key=` matching, so `"2026-05-25T00"` won't match anything.

- [ ] **Step 3: Update `get_daily_count` in `src/event/db.py`**

Replace the current implementation (lines 73–78):

```python
def get_daily_count(conn: sqlite3.Connection, alter_username: str, cutoff_hour_key: str) -> int:
    row = conn.execute(
        "SELECT SUM(hourly_count) AS total FROM rate_counters WHERE alter_username=? AND hour_key >= ?",
        (alter_username, cutoff_hour_key),
    ).fetchone()
    return row["total"] or 0
```

The parameter was `day_key: str`; it is now `cutoff_hour_key: str`. The SQL changes from `day_key=?` to `hour_key >= ?`. The `day_key` column remains in the schema and in `increment_rate` — no migration needed.

- [ ] **Step 4: Run the updated tests to verify they pass**

```bash
pytest tests/event/test_db.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/event/db.py tests/event/test_db.py
git commit -m "feat: rolling 24h daily count in get_daily_count"
```

---

### Task 2: Update `evaluate_post` to use rolling cutoff

**Files:**
- Modify: `src/event/gates.py`

No new tests needed: the existing gate tests call `increment_rate` with the current `hour_key`, which is always within the last 24h, so the rolling cutoff picks them up correctly.

- [ ] **Step 1: Update `evaluate_post` in `src/event/gates.py`**

Change the import on line 2:

```python
from datetime import datetime, timezone, timedelta
```

Replace lines 39–40 (the `hour_key` / `day_key` block):

```python
    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y-%m-%dT%H")
    cutoff_hour_key = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H")
```

Replace line 63 (the `get_daily_count` call):

```python
        daily = db.get_daily_count(conn, profile.reversed_username, cutoff_hour_key)
```

The variable `day_key` is fully removed; `cutoff_hour_key` replaces it.

- [ ] **Step 2: Run the full test suite**

```bash
pytest -v
```

Expected: all tests `PASSED` — the existing gate tests are unaffected because their `increment_rate` calls use the current hour, which is within the 24h window.

- [ ] **Step 3: Commit**

```bash
git add src/event/gates.py
git commit -m "feat: evaluate_post uses rolling 24h window for daily cap"
```

---

### Task 3: Simulation rate counting + `get_all_rate_stats`

**Files:**
- Modify: `src/event/db.py`
- Modify: `src/event/webui.py`
- Test: `tests/event/test_db.py`

- [ ] **Step 1: Write failing tests for `get_all_rate_stats`**

Add to the imports at the top of `tests/event/test_db.py`:

```python
from src.event.db import (
    init_db, mark_seen, is_seen,
    get_hourly_count, get_daily_count, increment_rate,
    insert_pending, get_pending, get_pending_by_id,
    update_status, update_reply_text,
    insert_posted, get_pending_auto_approve,
    get_daily_posts_summary, get_all_rate_stats,
)
```

Add at the bottom of `tests/event/test_db.py`:

```python
def test_get_all_rate_stats_basic(conn):
    increment_rate(conn, "ejdar", "2026-05-25T14", "2026-05-25")
    increment_rate(conn, "ejdar", "2026-05-25T14", "2026-05-25")
    increment_rate(conn, "ejdar", "2026-05-25T13", "2026-05-25")
    stats = get_all_rate_stats(conn, "2026-05-25T14", "2026-05-25T00")
    assert stats["ejdar"]["hourly"] == 2
    assert stats["ejdar"]["daily"] == 3


def test_get_all_rate_stats_excludes_old(conn):
    increment_rate(conn, "ejdar", "2026-05-25T10", "2026-05-25")
    increment_rate(conn, "ejdar", "2026-05-25T14", "2026-05-25")
    stats = get_all_rate_stats(conn, "2026-05-25T14", "2026-05-25T12")
    assert stats["ejdar"]["hourly"] == 1
    assert stats["ejdar"]["daily"] == 1  # T10 excluded by cutoff


def test_get_all_rate_stats_empty(conn):
    stats = get_all_rate_stats(conn, "2026-05-25T14", "2026-05-25T00")
    assert stats == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/event/test_db.py::test_get_all_rate_stats_basic -v
```

Expected: `FAILED` with `ImportError: cannot import name 'get_all_rate_stats'`

- [ ] **Step 3: Add `get_all_rate_stats` to `src/event/db.py`**

Add at the bottom of `src/event/db.py`:

```python
def get_all_rate_stats(conn: sqlite3.Connection, hour_key: str, cutoff_hour_key: str) -> dict[str, dict]:
    """Return {alter_username: {"hourly": N, "daily": N}} for all alters with any activity."""
    hourly_rows = conn.execute(
        "SELECT alter_username, hourly_count FROM rate_counters WHERE hour_key=?",
        (hour_key,),
    ).fetchall()
    daily_rows = conn.execute(
        "SELECT alter_username, SUM(hourly_count) AS total FROM rate_counters WHERE hour_key >= ? GROUP BY alter_username",
        (cutoff_hour_key,),
    ).fetchall()
    hourly = {r["alter_username"]: r["hourly_count"] for r in hourly_rows}
    daily = {r["alter_username"]: r["total"] for r in daily_rows}
    all_names = set(hourly) | set(daily)
    return {name: {"hourly": hourly.get(name, 0), "daily": daily.get(name, 0)} for name in all_names}
```

- [ ] **Step 4: Run db tests to verify they pass**

```bash
pytest tests/event/test_db.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 5: Fix simulation rate counting in `src/event/webui.py`**

In `_do_approve`, move `increment_rate` (and the `now` computation) outside the `if live_mode:` guard. Only the `time.sleep` stays gated.

Replace the current `if success:` block (lines 100–109):

```python
    if success:
        db.insert_posted(
            conn, entry["alter_username"], entry["thread_id"],
            entry["post_id"], entry["reply_text"], simulated=not live_mode,
        )
        now = datetime.now(timezone.utc)
        db.increment_rate(conn, entry["alter_username"],
                          now.strftime("%Y-%m-%dT%H"), now.strftime("%Y-%m-%d"))
        if live_mode:
            time.sleep(random.uniform(60, 180))
    return success
```

- [ ] **Step 6: Run full test suite**

```bash
pytest -v
```

Expected: all tests `PASSED`.

- [ ] **Step 7: Commit**

```bash
git add src/event/db.py tests/event/test_db.py src/event/webui.py
git commit -m "feat: add get_all_rate_stats; increment rate counters in simulation mode"
```

---

### Task 4: `/stats` page

**Files:**
- Modify: `src/event/webui.py`

No new tests: no Flask test infrastructure exists; verify via `pytest` for regressions only.

- [ ] **Step 1: Add `timedelta` to imports in `src/event/webui.py`**

Change line 5:

```python
from datetime import datetime, timezone, timedelta
```

- [ ] **Step 2: Add `_build_persona_stats` helper above `_do_approve`**

Insert before `_do_approve` (after the `_QUEUE_TEMPLATE` string):

```python
def _build_persona_stats(profiles: list, raw_stats: dict) -> list[dict]:
    order = {"daily": 0, "hourly": 1, "ok": 2}
    result = []
    for profile in profiles:
        counts = raw_stats.get(profile.reversed_username, {"hourly": 0, "daily": 0})
        h_used, d_used = counts["hourly"], counts["daily"]
        if d_used >= profile.daily_cap:
            status, label = "daily", "DAILY CAP"
        elif h_used >= profile.hourly_cap:
            status, label = "hourly", "HOURLY CAP"
        else:
            status, label = "ok", "OK"
        result.append({
            "name": profile.reversed_username,
            "hourly_used": h_used,
            "hourly_cap": profile.hourly_cap,
            "daily_used": d_used,
            "daily_cap": profile.daily_cap,
            "status": status,
            "status_label": label,
        })
    result.sort(key=lambda x: (order[x["status"]], x["name"]))
    return result
```

- [ ] **Step 3: Add `_STATS_TEMPLATE` after `_QUEUE_TEMPLATE`**

Insert after the closing `"""` of `_QUEUE_TEMPLATE`:

```python
_STATS_TEMPLATE = """<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="30">
<title>Shrimp Resurrect — Stats</title>
<style>
  body { font-family: monospace; max-width: 900px; margin: 40px auto; padding: 0 20px; background: #1a1a1a; color: #ccc; }
  h1 { color: #fff; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 0.8em; }
  .badge-live { background: #c0392b; color: #fff; }
  .badge-sim  { background: #2980b9; color: #fff; }
  table { width: 100%; border-collapse: collapse; margin-top: 16px; }
  th { text-align: left; padding: 6px 12px; color: #888; border-bottom: 1px solid #444; }
  td { padding: 6px 12px; border-bottom: 1px solid #2a2a2a; }
  .s-hourly { color: #f39c12; }
  .s-daily  { color: #e74c3c; }
  .status-ok     { background: #1e3a1e; color: #2ecc71; }
  .status-hourly { background: #3a2e1e; color: #f39c12; }
  .status-daily  { background: #3a1e1e; color: #e74c3c; }
</style>
</head>
<body>
<h1>Stats
  <span class="badge {% if live_mode %}badge-live{% else %}badge-sim{% endif %}">
    {% if live_mode %}LIVE{% else %}SIMULATIE{% endif %}
  </span>
  <a href="/" style="font-size:0.55em;color:#888;margin-left:16px">← queue</a>
</h1>
<p style="color:#666">Auto-refresh: 30s &nbsp;&middot;&nbsp; Dagelijkse telling: rolling 24h &nbsp;&middot;&nbsp; Huidig uur reset over: <strong style="color:#ccc">{{ minutes_until_reset }} min</strong></p>
<table>
<tr>
  <th>Alter</th>
  <th>Uurlijks</th>
  <th>Dagelijks (24h)</th>
  <th>Status</th>
</tr>
{% for p in persona_stats %}
<tr>
  <td>{{ p.name }}</td>
  <td {% if p.hourly_used >= p.hourly_cap %}class="s-hourly"{% endif %}>{{ p.hourly_used }} / {{ p.hourly_cap }}</td>
  <td {% if p.daily_used >= p.daily_cap %}class="s-daily"{% endif %}>{{ p.daily_used }} / {{ p.daily_cap }}</td>
  <td><span class="badge status-{{ p.status }}">{{ p.status_label }}</span></td>
</tr>
{% endfor %}
</table>
</body>
</html>"""
```

- [ ] **Step 4: Add `/stats` route inside `create_app`**

Add after the `/status` route (at the end of `create_app`, before `return app`):

```python
    @app.route("/stats")
    def stats_page():
        now = datetime.now(timezone.utc)
        hour_key = now.strftime("%Y-%m-%dT%H")
        cutoff_hour_key = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H")
        minutes_until_reset = 60 - now.minute
        raw_stats = db.get_all_rate_stats(conn, hour_key, cutoff_hour_key)
        persona_stats = _build_persona_stats(profiles, raw_stats)
        return render_template_string(
            _STATS_TEMPLATE,
            persona_stats=persona_stats,
            minutes_until_reset=minutes_until_reset,
            live_mode=live_mode,
        )
```

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```

Expected: all tests `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add src/event/webui.py
git commit -m "feat: add /stats page with per-persona rate cap dashboard"
```

---

### Task 5: Summary bar + auto-refresh on queue page

**Files:**
- Modify: `src/event/webui.py`

- [ ] **Step 1: Add `<meta http-equiv="refresh" content="30">` to `_QUEUE_TEMPLATE`**

Inside the `<head>` block of `_QUEUE_TEMPLATE`, add after `<meta charset="utf-8">`:

```html
<meta http-equiv="refresh" content="30">
```

- [ ] **Step 2: Add pill CSS to `_QUEUE_TEMPLATE`**

Inside the `<style>` block of `_QUEUE_TEMPLATE`, add before the closing `</style>`:

```css
  .persona-bar { margin: 12px 0 20px; }
  .pill { display: inline-block; padding: 3px 8px; border-radius: 3px; margin: 2px; font-size: 0.8em; }
  .pill-ok     { background: #1e3a1e; color: #2ecc71; }
  .pill-hourly { background: #3a2e1e; color: #f39c12; }
  .pill-daily  { background: #3a1e1e; color: #e74c3c; }
```

- [ ] **Step 3: Add summary bar to `_QUEUE_TEMPLATE`**

After the `<p><a href="/status"...` line and before `{% if not replies %}`, insert:

```html
<div class="persona-bar">
{% for p in persona_stats %}
  <span class="pill pill-{{ p.status }}" title="{{ p.hourly_used }}/{{ p.hourly_cap }} uurlijks &middot; {{ p.daily_used }}/{{ p.daily_cap }} dagelijks">{{ p.name }}&nbsp;{{ p.hourly_used }}/{{ p.hourly_cap }}&middot;{{ p.daily_used }}/{{ p.daily_cap }}</span>
{% endfor %}
  <a href="/stats" style="color:#888;margin-left:8px;font-size:0.85em">&rarr; volledig overzicht</a>
</div>
```

- [ ] **Step 4: Update the `/` route to compute and pass `persona_stats`**

Replace the current `index()` function inside `create_app`:

```python
    @app.route("/")
    def index():
        pending = [dict(r) for r in db.get_pending(conn)]
        now = datetime.now(timezone.utc)
        hour_key = now.strftime("%Y-%m-%dT%H")
        cutoff_hour_key = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H")
        raw_stats = db.get_all_rate_stats(conn, hour_key, cutoff_hour_key)
        persona_stats = _build_persona_stats(profiles, raw_stats)
        return render_template_string(
            _QUEUE_TEMPLATE,
            replies=pending,
            live_mode=live_mode,
            forum_url=forum_url,
            persona_stats=persona_stats,
        )
```

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```

Expected: all tests `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add src/event/webui.py
git commit -m "feat: add persona summary bar and auto-refresh to queue page"
```
