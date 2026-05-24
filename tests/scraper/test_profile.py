from pathlib import Path
from datetime import date
from src.scraper.profile import parse_last_active

FIXTURE = Path("tests/fixtures/search_user_119.html").read_text(encoding="utf-8")

def test_parse_returns_date():
    result = parse_last_active(FIXTURE)
    assert isinstance(result, date)

def test_radje_last_active_is_in_the_past():
    result = parse_last_active(FIXTURE)
    assert result < date.today()

def test_radje_last_active_year_and_month():
    # radje's most recent post was 09-03-2026 (9 March 2026)
    result = parse_last_active(FIXTURE)
    assert result.year == 2026
    assert result.month == 3
    assert result.day == 9

def test_parse_invalid_html_returns_none():
    result = parse_last_active("<html><body>no date here</body></html>")
    assert result is None
