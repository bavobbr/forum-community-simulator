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


def get_daily_count(conn: sqlite3.Connection, alter_username: str, cutoff_hour_key: str) -> int:
    row = conn.execute(
        "SELECT SUM(hourly_count) AS total FROM rate_counters WHERE alter_username=? AND hour_key >= ?",
        (alter_username, cutoff_hour_key),
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
