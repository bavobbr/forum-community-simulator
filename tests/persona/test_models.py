from src.persona.models import PersonaProfile


def _sample_alter() -> dict:
    return {
        "user_id": 10,
        "original_username": "Trojan",
        "reversed_username": "najorT",
        "post_count": 18123,
        "last_active": "2013-06-07",
    }


def test_from_alter_ego_creates_blank_profile():
    profile = PersonaProfile.from_alter_ego(_sample_alter())
    assert profile.user_id == 10
    assert profile.original_username == "Trojan"
    assert profile.reversed_username == "najorT"
    assert profile.post_count == 18123
    assert profile.last_active == "2013-06-07"
    assert profile.posts_analyzed == 0
    assert profile.is_approved is False
    assert profile.example_posts == []


def test_to_dict_round_trips():
    profile = PersonaProfile.from_alter_ego(_sample_alter())
    profile.posts_analyzed = 100
    profile.is_approved = True
    profile.dialect_markers = ["ge", "da", "ni"]
    profile.example_posts = ["post one", "post two"]
    profile.persona_summary = "Direct, flemish gamer"
    profile.topic_weights = {"Videogames": 0.8}
    profile.frequent_interactions = {"radje": "rival"}
    profile.peak_hours = [18, 19]

    d = profile.to_dict()
    restored = PersonaProfile.from_dict(d)

    assert restored.user_id == 10
    assert restored.posts_analyzed == 100
    assert restored.is_approved is True
    assert restored.dialect_markers == ["ge", "da", "ni"]
    assert restored.example_posts == ["post one", "post two"]
    assert restored.persona_summary == "Direct, flemish gamer"
    assert restored.topic_weights == {"Videogames": 0.8}
    assert restored.frequent_interactions == {"radje": "rival"}
    assert restored.peak_hours == [18, 19]


def test_from_dict_handles_missing_optional_fields():
    minimal = {
        "user_id": 42,
        "original_username": "foo",
        "reversed_username": "oof",
        "post_count": 100,
        "last_active": "2020-01-01",
    }
    profile = PersonaProfile.from_dict(minimal)
    assert profile.daily_cap == 10
    assert profile.hourly_cap == 3
    assert profile.topic_weights == {}
    assert profile.opinion_fingerprint == []
