from unittest.mock import MagicMock
from src.event.poller import fetch_new_posts, parse_post_date, parse_new_thread_list
from datetime import datetime, timezone, timedelta


# Thread list HTML returned by search.php?searchid=...
_THREAD_LIST_HTML = """
<table id="threadslist">
<tr id="threadbits_200">
  <td class="alt1">
    <a href="showthread.php?t=200" id="thread_title_200"><strong>Testthread</strong></a>
    <a href="showthread.php?goto=newpost&t=200" id="thread_gotonew_200">Go to new</a>
  </td>
  <td><a href="forumdisplay.php?f=9">Zwam</a></td>
</tr>
<tr id="threadbits_201">
  <td class="alt1">
    <a href="showthread.php?t=201" id="thread_title_201"><strong>Privé</strong></a>
    <a href="showthread.php?goto=newpost&t=201" id="thread_gotonew_201">Go to new</a>
  </td>
  <td><a href="forumdisplay.php?f=40">Discretie</a></td>
</tr>
<tr id="threadbits_23585">
  <td class="alt1">
    <a href="showthread.php?t=23585" id="thread_title_23585"><strong>Over dit experiment</strong></a>
    <a href="showthread.php?goto=newpost&t=23585" id="thread_gotonew_23585">Go to new</a>
  </td>
  <td><a href="forumdisplay.php?f=9">Zwam</a></td>
</tr>
</table>
"""

_POST_HTML_EXPERIMENT = """
<table id="post102">
  <tr><td class="thead">25-05-2026, 11:00</td></tr>
  <tr><td>
    <div id="postmenu_102"><a>SomeUser</a></div>
    <div id="post_message_102">Over dit experiment</div>
  </td></tr>
</table>
"""

# Post HTML returned by showthread.php?goto=newpost&t=200 (forum 9 — Zwam)
_POST_HTML_F9 = """
<table id="post100">
  <tr><td class="thead">25-05-2026, 10:00</td></tr>
  <tr><td>
    <div id="postmenu_100"><a>TestUser</a></div>
    <div id="post_message_100">Hallo daar!</div>
  </td></tr>
</table>
"""

# Post HTML returned by showthread.php?goto=newpost&t=201 (forum 40 — excluded)
_POST_HTML_F40 = """
<table id="post101">
  <tr><td class="thead">25-05-2026, 10:01</td></tr>
  <tr><td>
    <div id="postmenu_101"><a>OtherUser</a></div>
    <div id="post_message_101">Geheim</div>
  </td></tr>
</table>
"""


def _session_for_thread_list(logged_in=True):
    """Return a mock session that serves the thread list and per-thread HTML."""
    session = MagicMock()

    def _get(url):
        if "do=getdaily" in url:
            prefix = "Log Out" if logged_in else "no session here"
            return prefix + _THREAD_LIST_HTML
        if "goto=newpost" in url and "t=200" in url:
            return _POST_HTML_F9
        if "goto=newpost" in url and "t=201" in url:
            return _POST_HTML_F40
        if "goto=newpost" in url and "t=23585" in url:
            return _POST_HTML_EXPERIMENT
        return ""

    session.get.side_effect = _get
    return session


def test_fetch_new_posts_filters_excluded_threads():
    session = _session_for_thread_list()
    posts = fetch_new_posts(session)
    assert all(p["thread_id"] != 23585 for p in posts)


def test_fetch_new_posts_filters_excluded_forums():
    session = _session_for_thread_list()
    posts = fetch_new_posts(session)
    assert all(p["forum_id"] != 40 for p in posts)
    assert any(p["forum_id"] == 9 for p in posts)


def test_fetch_new_posts_reauths_on_expired_session():
    session = MagicMock()
    call_count = [0]

    def _get(url):
        call_count[0] += 1
        if "do=getdaily" in url and call_count[0] == 1:
            return "no session here" + _THREAD_LIST_HTML
        if "do=getdaily" in url:
            return "Log Out" + _THREAD_LIST_HTML
        if "goto=newpost" in url and "t=200" in url:
            return _POST_HTML_F9
        if "goto=newpost" in url and "t=201" in url:
            return _POST_HTML_F40
        return ""

    session.get.side_effect = _get

    import os
    with __import__('unittest.mock', fromlist=['patch']).patch.dict(os.environ, {
        'FORUM_USERNAME': 'wokebot', 'FORUM_PASSWORD': 'wokebot123'
    }):
        posts = fetch_new_posts(session)

    session.login.assert_called_once()
    assert len(posts) >= 1


def test_parse_new_thread_list():
    threads = parse_new_thread_list(_THREAD_LIST_HTML)
    assert len(threads) == 3
    assert threads[0]["thread_id"] == 200
    assert threads[0]["thread_title"] == "Testthread"
    assert threads[0]["forum_id"] == 9
    assert threads[0]["forum_name"] == "Zwam"
    assert threads[1]["thread_id"] == 201
    assert threads[1]["forum_id"] == 40
    assert threads[2]["thread_id"] == 23585


def test_parse_new_thread_list_empty():
    assert parse_new_thread_list("<html></html>") == []


def test_parse_post_date_valid():
    dt = parse_post_date("25-05-2026, 14:30")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 5
    assert dt.day == 25


def test_parse_post_date_today():
    dt = parse_post_date("Today, 10:30")
    assert dt is not None
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone(timedelta(hours=2)))
    assert dt.hour == 10
    assert dt.minute == 30
    assert dt.date() == now.date()


def test_parse_post_date_yesterday():
    dt = parse_post_date("Yesterday, 23:59")
    assert dt is not None
    from datetime import datetime, timezone, timedelta
    yesterday = (datetime.now(timezone(timedelta(hours=2))) - timedelta(days=1)).date()
    assert dt.hour == 23
    assert dt.minute == 59
    assert dt.date() == yesterday


def test_parse_post_date_invalid():
    assert parse_post_date("") is None
    assert parse_post_date("baddate") is None
