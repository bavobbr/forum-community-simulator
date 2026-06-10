import sqlite3
import pytest
from src.event.db import init_db, increment_rate
from src.event.sandbox_gates import evaluate_post_sandbox_random as evaluate_post_sandbox
from src.persona.models import PersonaProfile
from datetime import datetime, timezone


def _make_profile(reversed_username="ejdar", original_username="radje", hourly_cap=3, daily_cap=10):
    p = PersonaProfile.from_alter_ego({
        "user_id": 1,
        "original_username": original_username,
        "reversed_username": reversed_username,
        "post_count": 100,
        "last_active": "2023-01-01",
    })
    p.hourly_cap = hourly_cap
    p.daily_cap = daily_cap
    return p


def _make_post(author="RealUser", content="Hallo allemaal hoe gaat het?"):
    return {
        "post_id": 1,
        "thread_id": 100,
        "forum_id": 0,
        "forum_name": "",
        "author": author,
        "content": content,
    }


@pytest.fixture
def conn():
    c = init_db(":memory:")
    yield c
    c.close()


def test_author_is_alter_returns_empty(conn):
    profile = _make_profile(reversed_username="ejdar")
    post = _make_post(author="ejdar", content="Hoi dit is mijn eigen bericht")
    assert evaluate_post_sandbox(post, [profile], conn) == []





def test_no_mention_returns_random_selection(conn):
    profiles = [_make_profile(reversed_username=f"bot{i}", original_username=f"tob{i}") for i in range(10)]
    post = _make_post(content="Heeft iemand ervaring met nano aquaria opzetten?")
    result = evaluate_post_sandbox(post, profiles, conn, replies_per_post=3)
    assert len(result) == 3
    assert all(w == 1.0 for _, w in result)


def test_no_mention_respects_replies_per_post(conn):
    profiles = [_make_profile(reversed_username=f"bot{i}", original_username=f"tob{i}") for i in range(10)]
    post = _make_post(content="Heeft iemand ervaring met nano aquaria opzetten?")
    result = evaluate_post_sandbox(post, profiles, conn, replies_per_post=1)
    assert len(result) == 1


def test_rate_capped_profile_excluded_from_random(conn):
    capped = _make_profile(reversed_username="capped", original_username="deppac", hourly_cap=1)
    free = _make_profile(reversed_username="free00", original_username="00eerf", hourly_cap=5)
    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y-%m-%dT%H")
    day_key = now.strftime("%Y-%m-%d")
    increment_rate(conn, "capped", hour_key, day_key)
    post = _make_post(content="Heeft iemand ervaring met nano aquaria opzetten?")
    result = evaluate_post_sandbox(post, [capped, free], conn, replies_per_post=3)
    names = [p.reversed_username for p, _ in result]
    assert "capped" not in names
    assert "free00" in names





def test_fewer_profiles_than_replies_per_post(conn):
    profiles = [_make_profile(reversed_username="solo0", original_username="0olos")]
    post = _make_post(content="Heeft iemand ervaring met nano aquaria opzetten?")
    result = evaluate_post_sandbox(post, profiles, conn, replies_per_post=3)
    assert len(result) == 1
