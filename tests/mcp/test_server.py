import json
import datetime
from unittest.mock import patch, MagicMock
import pytest

from src.mcp.server import (
    get_user_posts,
    get_thread_context,
    get_daily_activity,
    post_reply,
    get_top_members,
    get_user_last_active
)

@pytest.fixture
def mock_session():
    with patch("src.mcp.server.get_session") as mock_get_session:
        session = MagicMock()
        mock_get_session.return_value = session
        yield session

def test_get_user_posts(mock_session):
    with patch("src.mcp.server.PostScraper") as MockScraper:
        scraper_instance = MockScraper.return_value
        scraper_instance.fetch_window.return_value = ([{"post_id": 1, "content": "test"}], 12345)
        
        result = get_user_posts(username="accu", limit=1)
        
        MockScraper.assert_called_once_with(mock_session, delay=6)
        scraper_instance.fetch_window.assert_called_once_with("accu", before_ts=None)
        assert json.loads(result) == [{"post_id": 1, "content": "test"}]

def test_get_thread_context(mock_session):
    with patch("src.mcp.server.fetch_thread_context") as mock_fetch:
        mock_fetch.return_value = [{"post_id": 100, "content": "context"}]
        
        result = get_thread_context(post_id=100, n=5)
        
        mock_fetch.assert_called_once_with(mock_session, 100, n=5)
        assert json.loads(result) == [{"post_id": 100, "content": "context"}]

def test_get_daily_activity(mock_session):
    with patch("src.mcp.server.fetch_new_posts") as mock_fetch:
        mock_fetch.return_value = [{"post_id": 200, "content": "daily"}]
        
        result = get_daily_activity()
        
        mock_fetch.assert_called_once_with(mock_session)
        assert json.loads(result) == [{"post_id": 200, "content": "daily"}]

def test_post_reply():
    with patch("src.mcp.server._post_reply") as mock_post:
        mock_post.return_value = True
        
        result = post_reply(username="accu", password="pw", thread_id=1, message="hello")
        
        mock_post.assert_called_once_with("accu", "pw", 1, "hello")
        assert result is True

def test_get_top_members(mock_session):
    with patch("src.mcp.server.parse_memberlist") as mock_parse:
        class DummyMember:
            user_id = 1
            username = "test"
            post_count = 10
            last_active = "01-01-2020"
            
        mock_parse.return_value = [DummyMember()]
        mock_session.get.return_value = "<html></html>"
        
        result = get_top_members()
        
        mock_session.get.assert_called_once_with("memberlist.php?order=DESC&sort=posts&pp=100")
        mock_parse.assert_called_once_with("<html></html>")
        
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["user_id"] == 1
        assert data[0]["username"] == "test"

def test_get_user_last_active_with_date(mock_session):
    with patch("src.mcp.server.parse_last_active") as mock_parse:
        mock_parse.return_value = datetime.date(2026, 6, 6)
        mock_session.get.return_value = "<html></html>"
        
        result = get_user_last_active(user_id=42)
        
        mock_session.get.assert_called_once_with("search.php?do=finduser&u=42")
        mock_parse.assert_called_once_with("<html></html>")
        
        data = json.loads(result)
        assert data["user_id"] == 42
        assert data["last_active"] == "2026-06-06"

def test_get_user_last_active_with_string(mock_session):
    with patch("src.mcp.server.parse_last_active") as mock_parse:
        mock_parse.return_value = "N/A"
        
        result = get_user_last_active(user_id=42)
        
        data = json.loads(result)
        assert data["last_active"] == "N/A"
