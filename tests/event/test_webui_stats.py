import pytest
from unittest.mock import MagicMock
from src.event.webui import _build_persona_stats


@pytest.fixture
def profiles():
    def make_profile(name, hcap, dcap):
        p = MagicMock()
        p.reversed_username = name
        p.hourly_cap = hcap
        p.daily_cap = dcap
        return p
    return [
        make_profile("ejdar", 3, 10),
        make_profile("trams", 2, 8),
    ]


def test_build_persona_stats_ok(profiles):
    rate_stats = {}
    result = _build_persona_stats(profiles, rate_stats)
    assert len(result) == 2
    row = next(r for r in result if r["name"] == "ejdar")
    assert row["hourly_used"] == 0
    assert row["hourly_cap"] == 3
    assert row["daily_used"] == 0
    assert row["daily_cap"] == 10
    assert row["status"] == "ok"


def test_build_persona_stats_hourly_cap(profiles):
    rate_stats = {"ejdar": {"hourly": 3, "daily": 5}}
    result = _build_persona_stats(profiles, rate_stats)
    row = next(r for r in result if r["name"] == "ejdar")
    assert row["status"] == "hourly"


def test_build_persona_stats_daily_cap(profiles):
    rate_stats = {"ejdar": {"hourly": 1, "daily": 10}}
    result = _build_persona_stats(profiles, rate_stats)
    row = next(r for r in result if r["name"] == "ejdar")
    assert row["status"] == "daily"


def test_build_persona_stats_sort_order(profiles):
    rate_stats = {
        "trams": {"hourly": 2, "daily": 3},  # hourly-capped
        "ejdar": {"hourly": 1, "daily": 10},  # daily-capped
    }
    result = _build_persona_stats(profiles, rate_stats)
    assert result[0]["name"] == "ejdar"   # daily first
    assert result[1]["name"] == "trams"   # hourly second
