from pathlib import Path
from unittest.mock import MagicMock, patch
from src.persona.scraper import (
    parse_posts_page,
    parse_search_id,
    parse_has_next_page,
    parse_post_date_timestamp,
    _extract_post_content,
    PostScraper,
)

FIXTURE = (Path(__file__).parent.parent / "fixtures" / "search_user_119.html").read_text(
    encoding="latin-1"
)


def test_parse_posts_page_returns_correct_count():
    posts = parse_posts_page(FIXTURE)
    assert len(posts) == 25  # default pp=25 in fixture


def test_parse_posts_page_post_structure():
    posts = parse_posts_page(FIXTURE)
    first = posts[0]
    assert first["post_id"] == 1743241
    assert first["thread_id"] == 12769
    assert first["thread_title"] == "Welke spellekes zijde mee bezig"
    assert first["forum_id"] == 22
    assert first["forum_name"] == "Videogames"
    assert "mewgenics" in first["content"]
    assert first["date"] == "09-03-2026, 19:04"


def test_parse_posts_page_content_has_substance():
    posts = parse_posts_page(FIXTURE)
    for post in posts:
        assert len(post["content"]) > 2, f"Post {post['post_id']} has too little content"


def test_parse_search_id_extracts_id():
    search_id = parse_search_id(FIXTURE)
    assert search_id == "11065652"


def test_parse_has_next_page_true_when_multiple_pages():
    assert parse_has_next_page(FIXTURE) is True


def test_parse_has_next_page_false_on_single_page():
    single_page_html = "<html><body><div>Results 1 to 5 of 5</div></body></html>"
    assert parse_has_next_page(single_page_html) is False


_QUOTE_POST_HTML = """
<table id="post999">
  <tr><td class="thead">
    <a href="forumdisplay.php?f=9">Zwam</a>
    09-03-2026, 12:00
  </td></tr>
  <tr><td class="alt1">
    <a href="showthread.php?t=100"><strong>Testthread</strong></a>
    <div class="alt2"><em>
      <div class="quote">
        <div class="thead">Origineel geplaatst door <strong>Bert</strong></div>
        <div class="alt2">dit is Bert zijn tekst</div>
      </div>
      Mijn eigen reactie hier.
    </em></div>
  </td></tr>
</table>
"""


def test_parse_posts_page_strips_quote_divs():
    posts = parse_posts_page(_QUOTE_POST_HTML)
    assert len(posts) == 1
    assert "Bert zijn tekst" not in posts[0]["content"]
    assert "Mijn eigen reactie hier" in posts[0]["content"]


def test_parse_posts_page_extracts_quoted_username():
    posts = parse_posts_page(_QUOTE_POST_HTML)
    assert posts[0]["quoted_users"] == ["Bert"]


def test_parse_posts_page_no_quoted_users_without_quotes():
    posts = parse_posts_page(FIXTURE)
    assert all(p["quoted_users"] == [] for p in posts)


# --- parse_post_date_timestamp ---

def test_parse_post_date_timestamp_returns_int():
    ts = parse_post_date_timestamp("09-03-2026, 19:04")
    assert isinstance(ts, int)
    assert ts > 0


def test_parse_post_date_timestamp_correct_value():
    # 09-03-2026 19:04 treated as UTC
    ts = parse_post_date_timestamp("09-03-2026, 19:04")
    assert ts == 1773083040


def test_parse_post_date_timestamp_invalid_returns_none():
    assert parse_post_date_timestamp("not-a-date") is None
    assert parse_post_date_timestamp("") is None


# --- PostScraper.fetch_window ---

def _make_post(post_id: int, date: str = "01-01-2024, 10:00") -> dict:
    return {
        "post_id": post_id,
        "thread_id": 1,
        "thread_title": "Thread",
        "forum_id": 1,
        "forum_name": "Forum",
        "date": date,
        "content": "content",
        "quoted_users": [],
    }


def _make_scraper(session_mock: MagicMock) -> PostScraper:
    scraper = PostScraper.__new__(PostScraper)
    scraper.session = session_mock
    scraper.delay = 0
    scraper._search_ids = {}
    scraper.progress_cb = None
    return scraper


def test_fetch_window_returns_posts_and_oldest_ts():
    """Returns the posts and a non-None oldest_ts for a non-empty window."""
    session = MagicMock()
    session.security_token = "tok"

    posts_page = [_make_post(i, "01-01-2024, 12:00") for i in range(1, 51)]

    with (
        patch("src.persona.scraper.parse_search_id", return_value="sid1"),
        patch("src.persona.scraper.parse_posts_page", return_value=posts_page),
        patch("src.persona.scraper.parse_has_next_page", return_value=False),
        patch("src.persona.scraper.time.sleep"),
    ):
        scraper = _make_scraper(session)
        posts, oldest_ts = scraper.fetch_window("TestUser")

    assert len(posts) == 50
    assert oldest_ts is not None
    assert isinstance(oldest_ts, int)


def test_fetch_window_oldest_ts_uses_min_post_id():
    """oldest_ts is derived from the post with the lowest post_id (chronologically oldest)."""
    session = MagicMock()
    session.security_token = "tok"

    # Post 1 is oldest (date further in the past)
    posts_page = [
        _make_post(1, "01-01-2020, 10:00"),
        _make_post(2, "01-01-2024, 10:00"),
    ]

    with (
        patch("src.persona.scraper.parse_search_id", return_value="sid1"),
        patch("src.persona.scraper.parse_posts_page", return_value=posts_page),
        patch("src.persona.scraper.parse_has_next_page", return_value=False),
        patch("src.persona.scraper.time.sleep"),
    ):
        scraper = _make_scraper(session)
        _, oldest_ts = scraper.fetch_window("TestUser")

    from src.persona.scraper import parse_post_date_timestamp, _TZ_BUFFER_SECONDS
    expected = parse_post_date_timestamp("01-01-2020, 10:00") - _TZ_BUFFER_SECONDS
    assert oldest_ts == expected


def test_fetch_window_empty_returns_none_ts():
    """Returns ([], None) when no posts are found."""
    session = MagicMock()
    session.security_token = "tok"

    with (
        patch("src.persona.scraper.parse_search_id", return_value="sid1"),
        patch("src.persona.scraper.parse_posts_page", return_value=[]),
        patch("src.persona.scraper.parse_has_next_page", return_value=False),
        patch("src.persona.scraper.time.sleep"),
    ):
        scraper = _make_scraper(session)
        posts, oldest_ts = scraper.fetch_window("TestUser")

    assert posts == []
    assert oldest_ts is None


def test_fetch_window_raises_when_no_searchid():
    """Raises ValueError if the advanced search returns no searchid."""
    import pytest
    session = MagicMock()
    session.security_token = "tok"

    with (
        patch("src.persona.scraper.parse_search_id", return_value=None),
        patch("src.persona.scraper.time.sleep"),
    ):
        scraper = _make_scraper(session)
        with pytest.raises(ValueError, match="No searchid"):
            scraper.fetch_window("GhostUser")


# --- full-content enrichment ---

_SHOWTHREAD_HTML = """
<table id="post42">
  <tr><td class="thead">01-01-2024, 10:00</td></tr>
  <tr><td>
    <div id="postmenu_42"><a href="#">Alice</a></div>
    <div id="post_message_42">This is the full untruncated post content.</div>
  </td></tr>
</table>
"""


def test_extract_post_content_returns_full_text():
    content = _extract_post_content(_SHOWTHREAD_HTML, 42)
    assert content == "This is the full untruncated post content."


def test_extract_post_content_returns_none_when_post_not_found():
    assert _extract_post_content(_SHOWTHREAD_HTML, 99) is None


def test_extract_post_content_converts_smilies_to_alt_code():
    html = '<div id="post_message_1"><img src="smilies/smile.gif" alt=":)" title="Smile"/> tekst</div>'
    assert _extract_post_content(html, 1) == ":) tekst"


def test_extract_post_content_smilie_without_alt_is_removed():
    html = '<div id="post_message_1"><img src="smilies/unknown.gif" alt="" title="Wut"/> tekst</div>'
    assert _extract_post_content(html, 1) == "tekst"


def test_extract_post_content_unknown_image_becomes_afbeelding():
    html = '<div id="post_message_1"><img src="uploads/photo.jpg" alt=""/></div>'
    assert _extract_post_content(html, 1) == "[afbeelding]"


def test_enrich_replaces_truncated_content():
    post = {**_make_post(42), "content": "truncated..."}
    session = MagicMock()
    session.get.return_value = _SHOWTHREAD_HTML
    scraper = _make_scraper(session)
    result = scraper._enrich_with_full_content([post])
    assert result[0]["content"] == "This is the full untruncated post content."


def test_enrich_fetches_showthread_url():
    session = MagicMock()
    session.get.return_value = _SHOWTHREAD_HTML
    scraper = _make_scraper(session)
    scraper._enrich_with_full_content([_make_post(42)])
    session.get.assert_called_once_with("showthread.php?p=42")


def test_enrich_no_delay_between_fetches():
    posts = [_make_post(i) for i in range(1, 6)]
    session = MagicMock()
    session.get.return_value = _SHOWTHREAD_HTML
    scraper = _make_scraper(session)
    with patch("src.persona.scraper.time.sleep") as mock_sleep:
        scraper._enrich_with_full_content(posts)
    mock_sleep.assert_not_called()


def test_enrich_falls_back_on_missing_post_id():
    post = {**_make_post(99), "content": "original truncated"}
    session = MagicMock()
    session.get.return_value = _SHOWTHREAD_HTML  # only has post 42
    scraper = _make_scraper(session)
    result = scraper._enrich_with_full_content([post])
    assert result[0]["content"] == "original truncated"


def test_enrich_falls_back_on_exception():
    post = {**_make_post(42), "content": "original truncated"}
    session = MagicMock()
    session.get.side_effect = Exception("network error")
    scraper = _make_scraper(session)
    result = scraper._enrich_with_full_content([post])
    assert result[0]["content"] == "original truncated"


def test_fetch_window_calls_enrich_with_full_content():
    session = MagicMock()
    session.security_token = "tok"
    posts_page = [_make_post(42)]

    with (
        patch("src.persona.scraper.parse_search_id", return_value="sid1"),
        patch("src.persona.scraper.parse_posts_page", return_value=posts_page),
        patch("src.persona.scraper.parse_has_next_page", return_value=False),
        patch("src.persona.scraper.time.sleep"),
    ):
        scraper = _make_scraper(session)
        scraper._enrich_with_full_content = MagicMock(side_effect=lambda p: p)
        scraper.fetch_window("TestUser")

    scraper._enrich_with_full_content.assert_called_once_with(posts_page)


def test_enrich_logs_progress_every_25_posts(caplog):
    import logging
    posts = [_make_post(i) for i in range(1, 51)]  # 50 posts
    session = MagicMock()
    session.get.return_value = _SHOWTHREAD_HTML
    scraper = _make_scraper(session)
    with caplog.at_level(logging.INFO, logger="src.persona.scraper"):
        scraper._enrich_with_full_content(posts)
    progress_msgs = [r.message for r in caplog.records if "full content" in r.message]
    assert any("25/50" in m for m in progress_msgs)
    assert any("50/50" in m for m in progress_msgs)


def test_enrich_logs_final_count_when_not_multiple_of_25(caplog):
    import logging
    posts = [_make_post(i) for i in range(1, 11)]  # 10 posts — less than one batch
    session = MagicMock()
    session.get.return_value = _SHOWTHREAD_HTML
    scraper = _make_scraper(session)
    with caplog.at_level(logging.INFO, logger="src.persona.scraper"):
        scraper._enrich_with_full_content(posts)
    progress_msgs = [r.message for r in caplog.records if "full content" in r.message]
    assert any("10/10" in m for m in progress_msgs)


def test_fetch_batch_calls_enrich_with_full_content():
    session = MagicMock()
    posts_page = [_make_post(42)]

    with (
        patch("src.persona.scraper.parse_posts_page", return_value=posts_page),
        patch("src.persona.scraper.parse_has_next_page", return_value=False),
        patch("src.persona.scraper.time.sleep"),
    ):
        scraper = _make_scraper(session)
        scraper._search_ids = {1: "sid1"}
        scraper._enrich_with_full_content = MagicMock(side_effect=lambda p: p)
        scraper.fetch_batch(1, page=1)

    scraper._enrich_with_full_content.assert_called_once_with(posts_page)
