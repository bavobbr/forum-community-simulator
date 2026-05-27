# Stats Dashboard Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the operator a live view of how many replies each alter ego has sent (hourly and rolling-24h), which alters are rate-capped, and when they can post again — both on the existing queue page and on a dedicated `/stats` page.

**Architecture:** Extend `db.py` with a rolling-24h daily count and a stats-fetching helper. Fix simulation rate counting in `_do_approve`. Add a compact summary bar to the queue page and a full `/stats` route, both auto-refreshing every 30s.

**Tech Stack:** Python, Flask, SQLite, server-side Jinja2 templates (no JS frameworks).

---

## Data layer

### Rolling 24h daily count

`get_daily_count` changes signature from `(conn, alter_username, day_key: str)` to `(conn, alter_username, cutoff_hour_key: str)`. The query changes from:

```sql
WHERE alter_username=? AND day_key=?
```

to:

```sql
WHERE alter_username=? AND hour_key >= ?
```

The `cutoff_hour_key` passed by callers is `(now - timedelta(hours=24)).strftime("%Y-%m-%dT%H")`. The `day_key` column in `rate_counters` is left in place — no schema migration needed.

### `evaluate_post` update

In `src/event/gates.py`, replace:

```python
day_key = now.strftime("%Y-%m-%d")
```

with:

```python
from datetime import timedelta  # already has datetime, timezone
cutoff_hour_key = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H")
```

Pass `cutoff_hour_key` to `get_daily_count` instead of `day_key`.

### Simulation rate counting

In `src/event/webui.py`, `_do_approve` currently only calls `increment_rate` in live mode. Move it outside the `if live_mode:` guard — only the `time.sleep` stays gated on live mode:

```python
if success:
    db.insert_posted(...)
    now = datetime.now(timezone.utc)
    db.increment_rate(conn, entry["alter_username"],
                      now.strftime("%Y-%m-%dT%H"), now.strftime("%Y-%m-%d"))
    if live_mode:
        time.sleep(random.uniform(60, 180))
```

### New DB helper

```python
def get_all_rate_stats(conn, hour_key: str, cutoff_hour_key: str) -> dict[str, dict]:
    """Return {alter_username: {"hourly": N, "daily": N}} for all alters with activity."""
    hourly_rows = conn.execute(
        "SELECT alter_username, hourly_count FROM rate_counters WHERE hour_key=?",
        (hour_key,),
    ).fetchall()
    daily_rows = conn.execute(
        """SELECT alter_username, SUM(hourly_count) AS total
           FROM rate_counters WHERE hour_key >= ? GROUP BY alter_username""",
        (cutoff_hour_key,),
    ).fetchall()
    hourly = {r["alter_username"]: r["hourly_count"] for r in hourly_rows}
    daily = {r["alter_username"]: r["total"] for r in daily_rows}
    all_names = set(hourly) | set(daily)
    return {name: {"hourly": hourly.get(name, 0), "daily": daily.get(name, 0)}
            for name in all_names}
```

---

## Queue page summary bar

A compact strip inserted at the top of the existing `_QUEUE_TEMPLATE`, above the pending replies. Each persona appears as a pill: `name hourly/hcap · daily/dcap`. Sorted: daily-capped first, then hourly-capped, then OK alphabetically. A `→ stats` link on the right opens `/stats`.

Color coding:
- **Red** — daily cap reached (`daily_used >= daily_cap`)
- **Yellow** — hourly cap reached (`hourly_used >= hourly_cap`)
- **Green** — OK

Auto-refresh via `<meta http-equiv="refresh" content="30">` added to the `<head>` of the queue page.

The bar data is computed in the `/` route handler and passed to the template as `persona_stats` — a list of dicts with keys `name`, `hourly_used`, `hourly_cap`, `daily_used`, `daily_cap`, `status` (`"ok"`, `"hourly"`, `"daily"`).

---

## `/stats` page

A dedicated route returning a full-page table, one row per loaded persona (all profiles, not just those with activity). Columns:

| Column | Source |
|---|---|
| Alter | `profile.reversed_username` |
| Hourly | `hourly_used / profile.hourly_cap` |
| Daily (rolling 24h) | `daily_used / profile.daily_cap` |
| Hour resets in | `60 - now.minute` minutes (same for all) |
| Status | `OK` / `HOURLY CAP` / `DAILY CAP` |

Sorted the same as the summary bar (daily-capped → hourly-capped → OK).

Auto-refreshes every 30s. Link back to `/` (queue).

The route handler calls `get_all_rate_stats` with the current `hour_key` and `cutoff_hour_key`, merges with all loaded profiles (profiles with no activity get 0 counts), and passes the result to a new `_STATS_TEMPLATE`.

---

## Files changed

- `src/event/db.py` — change `get_daily_count` signature (rolling); add `get_all_rate_stats`
- `src/event/gates.py` — update `evaluate_post` to compute `cutoff_hour_key` and pass to `get_daily_count`; add `timedelta` to imports
- `src/event/webui.py` — fix simulation rate counting; add summary bar to queue template; add `/stats` route and `_STATS_TEMPLATE`
- `tests/event/test_db.py` — update `get_daily_count` tests for new signature; add tests for `get_all_rate_stats`
- `tests/event/test_gates.py` — no changes needed: gate tests call `increment_rate` with the current `hour_key`, which always falls within the rolling 24h window, so `evaluate_post` still sees the counts correctly
