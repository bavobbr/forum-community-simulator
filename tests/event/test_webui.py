import sqlite3
import pytest
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
    profiles = [_make_profile()]
    flask_app = create_app(conn, profiles, "testpass", live_mode=False)
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
    assert resp.status_code == 302
    with flask_app.test_client() as c:
        resp = c.get("/")
    assert b"reply" not in resp.data


def test_edit_updates_reply_text(app):
    flask_app, conn = app
    reply_id = insert_pending(conn, 1, 100, 9, "ejdar", "origineel")
    with flask_app.test_client() as c:
        resp = c.post(f"/reply/{reply_id}/edit", data={"reply_text": "aangepast"})
    assert resp.status_code == 302
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
