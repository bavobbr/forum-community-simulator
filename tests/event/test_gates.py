import sqlite3
import pytest
from src.event.db import init_db, increment_rate
from src.event.gates import evaluate_post
from src.persona.models import PersonaProfile


def _make_profile(reversed_username="ejdar", forum_name="Zwam", weight=0.8, hourly_cap=3, daily_cap=10):
    p = PersonaProfile.from_alter_ego({
        "user_id": 1, "original_username": "radje", "reversed_username": reversed_username,
        "post_count": 100, "last_active": "2023-01-01",
    })
    p.topic_weights = {forum_name: weight}
    p.hourly_cap = hourly_cap
    p.daily_cap = daily_cap
    return p


def _make_post(forum_id=9, forum_name="Zwam", content="Hallo"):
    return {"post_id": 1, "thread_id": 100, "forum_id": forum_id,
            "forum_name": forum_name, "content": content}


@pytest.fixture
def conn():
    c = init_db(":memory:")
    yield c
    c.close()


def test_excluded_forum_skips_all(conn):
    profile = _make_profile()
    post = _make_post(forum_id=40, forum_name="Discretie")
    assert evaluate_post(post, [profile], conn) == []


def test_low_relevance_skips(conn):
    profile = _make_profile(weight=0.1)
    post = _make_post()
    # weight 0.1 < 0.2 threshold → always skip
    results = [evaluate_post(post, [profile], conn) for _ in range(20)]
    assert all(r == [] for r in results)


def test_mention_bypasses_relevance(conn):
    profile = _make_profile(forum_name="Videogames", weight=0.0)
    post = _make_post(forum_name="Zwam", content="ejdar wat denk jij?")
    # ejdar is mentioned → relevance bypassed; probability bypassed
    # with weight=0.0 for a different forum but mention → must pass
    passed = evaluate_post(post, [profile], conn)
    assert profile in passed


def test_rate_limit_blocks(conn):
    profile = _make_profile(hourly_cap=2)
    post = _make_post()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y-%m-%dT%H")
    day_key = now.strftime("%Y-%m-%d")
    increment_rate(conn, "ejdar", hour_key, day_key)
    increment_rate(conn, "ejdar", hour_key, day_key)
    # hourly_count == hourly_cap → blocked
    result = evaluate_post(post, [profile], conn)
    assert result == []


def test_pile_on_guard_keeps_max_two(conn):
    profiles = [_make_profile(f"user{i}", weight=0.9) for i in range(5)]
    post = _make_post()
    result = evaluate_post(post, profiles, conn)
    assert len(result) <= 2


def test_tag_match_bypasses_topic_weight(conn):
    profile = _make_profile(forum_name="Videogames", weight=0.0)
    profile.interest_tags = ["wielrennen", "Remco Evenepoel"]
    post = _make_post(forum_name="Zwam", content="De Tour de France was fantastisch, wielrennen op zijn best!")
    result = evaluate_post(post, [profile], conn)
    assert profile in result


def test_tag_match_is_case_insensitive(conn):
    profile = _make_profile(forum_name="Videogames", weight=0.0)
    profile.interest_tags = ["Remco Evenepoel"]
    post = _make_post(forum_name="Zwam", content="remco evenepoel wint weer!")
    result = evaluate_post(post, [profile], conn)
    assert profile in result


def test_tag_match_respects_rate_limit(conn):
    from src.event.db import increment_rate
    from datetime import datetime, timezone
    profile = _make_profile(forum_name="Videogames", weight=0.0, hourly_cap=1)
    profile.interest_tags = ["wielrennen"]
    post = _make_post(forum_name="Zwam", content="wielrennen is geweldig")
    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y-%m-%dT%H")
    day_key = now.strftime("%Y-%m-%d")
    increment_rate(conn, "ejdar", hour_key, day_key)
    result = evaluate_post(post, [profile], conn)
    assert result == []


def test_no_tags_still_requires_topic_weight(conn):
    profile = _make_profile(forum_name="Videogames", weight=0.0)
    profile.interest_tags = []
    post = _make_post(forum_name="Zwam", content="wielrennen is geweldig")
    result = evaluate_post(post, [profile], conn)
    assert result == []
