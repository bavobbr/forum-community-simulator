import pytest
from unittest.mock import MagicMock, patch
from src.event.webui import create_app


@pytest.fixture
def app():
    import sqlite3
    from src.event.db import init_db
    conn = init_db(":memory:")

    p = MagicMock()
    p.reversed_username = "ejdar"
    p.hourly_cap = 3
    p.daily_cap = 10
    p.is_approved = True

    with patch.dict("os.environ", {"FORUM_URL": "http://forum.test"}):
        flask_app = create_app(conn, [p], "pass", False)
    flask_app.testing = True
    return flask_app


def test_queue_page_has_persona_bar(app):
    with app.test_client() as client:
        resp = client.get("/")
        html = resp.data.decode()
        assert resp.status_code == 200
        assert "ejdar" in html
        assert "persona-bar" in html


def test_queue_page_has_auto_refresh(app):
    with app.test_client() as client:
        resp = client.get("/")
        html = resp.data.decode()
        assert 'http-equiv="refresh"' in html
        assert 'content="30"' in html


def test_queue_page_has_stats_link(app):
    with app.test_client() as client:
        resp = client.get("/")
        html = resp.data.decode()
        assert 'href="/stats"' in html
