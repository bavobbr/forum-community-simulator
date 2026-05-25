from unittest.mock import MagicMock
from src.event.thread_scraper import parse_thread_page, fetch_thread_context, _preprocess_content
from bs4 import BeautifulSoup


_THREAD_HTML = """
<html><body>
<a href="showthread.php?t=200&amp;page=4">&lt;</a>
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
