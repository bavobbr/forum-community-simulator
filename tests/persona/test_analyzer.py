import json
from unittest.mock import MagicMock, patch
from src.persona.models import PersonaProfile
from src.persona.analyzer import analyze_first_batch, refine_with_batch

_SAMPLE_POSTS = [
    {
        "post_id": 1,
        "thread_id": 10,
        "thread_title": "Welke spellekes zijde mee bezig",
        "forum_id": 22,
        "forum_name": "Videogames",
        "date": "09-03-2026, 19:04",
        "content": "mewgenics is raar genoeg mijn ding ni, klikt ni. probeer wss nog eens op dood moment",
    },
    {
        "post_id": 2,
        "thread_id": 20,
        "thread_title": "Politiek",
        "forum_id": 9,
        "forum_name": "Zwam",
        "date": "08-03-2026, 10:00",
        "content": "ge zijt echt ne zever man, da klopt van geen kanten",
    },
]

_MOCK_ANALYSIS_RESPONSE = {
    "dialect_markers": ["ge", "ni", "da", "wss"],
    "formality": "very_casual",
    "sentence_length": "short",
    "bbcode_habits": [],
    "punctuation_style": "weinig hoofdletters, geen punt op het einde",
    "topic_weights": {"Videogames": 0.8, "Zwam": 0.6},
    "opinion_fingerprint": ["sceptisch over hype", "direct in taal"],
    "frequent_interactions": {},
    "peak_hours": [18, 19, 20],
    "typical_post_length": "short",
    "daily_cap": 5,
    "hourly_cap": 2,
    "example_posts": [
        "mewgenics is raar genoeg mijn ding ni, klikt ni.",
        "ge zijt echt ne zever man, da klopt van geen kanten",
    ],
    "persona_summary": "Direct en nuchter gamer uit Vlaanderen. Schrijft in dialect, kort en bondig.",
}


def _make_mock_client(response_dict: dict) -> MagicMock:
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(response_dict))]
    mock_client.messages.create.return_value = mock_message
    return mock_client


def test_analyze_first_batch_returns_profile():
    alter = {
        "user_id": 119,
        "original_username": "radje",
        "reversed_username": "ejdar",
        "post_count": 8432,
        "last_active": "2026-03-09",
    }
    mock_client = _make_mock_client(_MOCK_ANALYSIS_RESPONSE)

    profile = analyze_first_batch(mock_client, alter, _SAMPLE_POSTS)

    assert isinstance(profile, PersonaProfile)
    assert profile.user_id == 119
    assert profile.posts_analyzed == 2
    assert profile.pages_loaded == 1
    assert profile.dialect_markers == ["ge", "ni", "da", "wss"]
    assert profile.formality == "very_casual"
    assert profile.daily_cap == 5
    assert len(profile.example_posts) == 2
    assert "Direct" in profile.persona_summary


def test_analyze_first_batch_calls_api_with_posts():
    alter = {
        "user_id": 119,
        "original_username": "radje",
        "reversed_username": "ejdar",
        "post_count": 8432,
        "last_active": "2026-03-09",
    }
    mock_client = _make_mock_client(_MOCK_ANALYSIS_RESPONSE)

    analyze_first_batch(mock_client, alter, _SAMPLE_POSTS)

    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args[1]
    prompt = call_kwargs["messages"][0]["content"]
    assert "radje" in prompt
    assert "mewgenics" in prompt


def test_refine_with_batch_updates_existing_profile():
    alter = {
        "user_id": 119,
        "original_username": "radje",
        "reversed_username": "ejdar",
        "post_count": 8432,
        "last_active": "2026-03-09",
    }
    existing = PersonaProfile.from_alter_ego(alter)
    existing.posts_analyzed = 100
    existing.pages_loaded = 1
    existing.dialect_markers = ["ge", "ni"]

    updated_response = dict(_MOCK_ANALYSIS_RESPONSE)
    updated_response["dialect_markers"] = ["ge", "ni", "da", "wss", "zever"]
    mock_client = _make_mock_client(updated_response)

    updated = refine_with_batch(mock_client, existing, _SAMPLE_POSTS)

    assert updated.posts_analyzed == 102
    assert updated.pages_loaded == 2
    assert "da" in updated.dialect_markers


def test_analyze_handles_malformed_json_gracefully():
    alter = {
        "user_id": 119,
        "original_username": "radje",
        "reversed_username": "ejdar",
        "post_count": 8432,
        "last_active": "2026-03-09",
    }
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="this is not json {{{")]
    mock_client.messages.create.return_value = mock_message

    # Should not raise; returns blank profile from alter
    profile = analyze_first_batch(mock_client, alter, _SAMPLE_POSTS)
    assert profile.user_id == 119
    assert profile.posts_analyzed == 0  # unchanged on failure
