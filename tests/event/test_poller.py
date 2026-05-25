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
