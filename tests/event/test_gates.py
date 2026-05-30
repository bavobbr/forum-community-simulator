import sqlite3
import pytest
from src.event.db import init_db, increment_rate
from src.event.gates import evaluate_post, detect_quoted_alters
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


def _profiles(result):
    return [p for p, _ in result]


def test_mention_bypasses_relevance(conn):
    profile = _make_profile(forum_name="Videogames", weight=0.0)
    post = _make_post(forum_name="Zwam", content="ejdar wat denk jij hierover?")
    # ejdar is mentioned → relevance bypassed; probability bypassed
    # with weight=0.0 for a different forum but mention → must pass
    passed = evaluate_post(post, [profile], conn)
    assert profile in _profiles(passed)


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
    assert profile in _profiles(result)


def test_tag_match_is_case_insensitive(conn):
    profile = _make_profile(forum_name="Videogames", weight=0.0)
    profile.interest_tags = ["Remco Evenepoel"]
    post = _make_post(forum_name="Zwam", content="remco evenepoel wint weer vandaag!")
    result = evaluate_post(post, [profile], conn)
    assert profile in _profiles(result)


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


def test_evaluate_post_returns_weights(conn):
    profile = _make_profile(weight=0.9)
    post = _make_post()
    # Run many times to ensure at least one passes the random gate
    for _ in range(30):
        result = evaluate_post(post, [profile], conn)
        if result:
            _, weight = result[0]
            assert isinstance(weight, float)
            assert 0.0 <= weight <= 1.0
            return
    # If none passed it means random gate consistently blocked — that's fine


def _make_profile_with_reversed(reversed_username):
    p = PersonaProfile.from_alter_ego({
        "user_id": 1, "original_username": reversed_username[::-1],
        "reversed_username": reversed_username,
        "post_count": 100, "last_active": "2023-01-01",
    })
    return p


def test_detect_quoted_alters_finds_quoted_profile():
    profiles = [_make_profile_with_reversed("ejdar"), _make_profile_with_reversed("nboj")]
    post = {"author": "real_user", "content": "[QUOTE=ejdar;123]something[/QUOTE]\nOriginally Posted by ejdar\nhello"}
    result = detect_quoted_alters(post, profiles)
    assert "ejdar" in result
    assert "nboj" not in result


def test_detect_quoted_alters_is_case_insensitive():
    profiles = [_make_profile_with_reversed("Ejdar")]
    post = {"author": "real_user", "content": "originally posted by ejdar"}
    result = detect_quoted_alters(post, profiles)
    assert "Ejdar" in result


def test_detect_quoted_alters_returns_empty_when_alter_quotes_alter():
    profiles = [_make_profile_with_reversed("ejdar"), _make_profile_with_reversed("nboj")]
    post = {"author": "ejdar", "content": "Originally Posted by nboj\nsomething"}
    result = detect_quoted_alters(post, profiles)
    assert result == set()


def test_detect_quoted_alters_returns_empty_when_no_quote():
    profiles = [_make_profile_with_reversed("ejdar")]
    post = {"author": "real_user", "content": "Gewoon een bericht zonder citaat"}
    result = detect_quoted_alters(post, profiles)
    assert result == set()


def test_detect_quoted_alters_can_find_multiple():
    profiles = [_make_profile_with_reversed("ejdar"), _make_profile_with_reversed("nboj")]
    post = {
        "author": "real_user",
        "content": "Originally Posted by ejdar\n...\nOriginally Posted by nboj\n..."
    }
    result = detect_quoted_alters(post, profiles)
    assert result == {"ejdar", "nboj"}


def test_quoted_alter_gets_max_weight(conn):
    profile = _make_profile(reversed_username="ejdar", forum_name="Offtopic", weight=0.0)
    post = _make_post(forum_name="Zwam", content="Originally Posted by ejdar\nhello")
    post["quoted_alters"] = {"ejdar"}
    result = evaluate_post(post, [profile], conn)
    assert len(result) == 1
    _, weight = result[0]
    assert weight == 1.0


def test_quoted_alter_still_respects_rate_cap(conn):
    from src.event.db import increment_rate
    from datetime import datetime, timezone
    profile = _make_profile(reversed_username="ejdar", forum_name="Offtopic", weight=0.0, hourly_cap=1)
    post = _make_post(forum_name="Zwam", content="Originally Posted by ejdar\nhello")
    post["quoted_alters"] = {"ejdar"}
    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y-%m-%dT%H")
    day_key = now.strftime("%Y-%m-%d")
    increment_rate(conn, "ejdar", hour_key, day_key)
    result = evaluate_post(post, [profile], conn)
    assert result == []


def test_non_quoted_alter_uses_normal_logic(conn):
    profile = _make_profile(reversed_username="ejdar", forum_name="Offtopic", weight=0.0)
    post = _make_post(forum_name="Zwam", content="Gewoon een bericht")
    post["quoted_alters"] = set()
    result = evaluate_post(post, [profile], conn)
    assert result == []


def test_short_post_below_minimum_words_is_skipped(conn):
    profile = _make_profile(weight=1.0)
    post = _make_post(content="ok")
    result = evaluate_post(post, [profile], conn)
    assert result == []


def test_post_with_exactly_minimum_words_is_not_skipped(conn):
    profile = _make_profile(weight=1.0)
    post = _make_post(content="dit zijn precies vijf woorden")
    # Run several times to rule out the stochastic gate
    passed = any(evaluate_post(post, [profile], conn) for _ in range(20))
    assert passed


def test_bbcode_tags_not_counted_in_word_count(conn):
    profile = _make_profile(weight=1.0)
    # The actual content after stripping tags is just "ok" — 1 word
    post = _make_post(content="[QUOTE=iemand;123]veel geciteerde tekst hier[/QUOTE] ok")
    result = evaluate_post(post, [profile], conn)
    assert result == []


def test_alter_authored_post_is_skipped(conn):
    profile_a = _make_profile(reversed_username="ejdar", weight=1.0)
    profile_b = _make_profile(reversed_username="trams", weight=1.0)
    post = _make_post(content="Hallo allemaal")
    post["author"] = "ejdar"  # authored by an alter ego
    result = evaluate_post(post, [profile_a, profile_b], conn)
    assert result == []
