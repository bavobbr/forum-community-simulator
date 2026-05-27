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


def test_daily_count_excludes_old_hours(conn):
    increment_rate(conn, "ejdar", "2026-05-25T10", "2026-05-25")
    increment_rate(conn, "ejdar", "2026-05-25T14", "2026-05-25")
    # cutoff at T12 → T10 excluded, T14 included
    assert get_daily_count(conn, "ejdar", "2026-05-25T12") == 1


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
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    insert_posted(conn, "ejdar", 100, 1, "reply", simulated=False)
    insert_posted(conn, "ejdar", 101, 2, "reply2", simulated=True)
    summary = get_daily_posts_summary(conn, today)
    assert summary.get("ejdar", 0) == 2
