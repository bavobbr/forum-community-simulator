import json
import pytest
from unittest.mock import patch
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
    "typical_post_length": 30,
    "daily_cap": 5,
    "hourly_cap": 2,
    "example_posts": [
        "mewgenics is raar genoeg mijn ding ni, klikt ni.",
        "ge zijt echt ne zever man, da klopt van geen kanten",
    ],
    "persona_summary": "Direct en nuchter gamer uit Vlaanderen. Schrijft in dialect, kort en bondig.",
}

_MOCK_REFINE_RESPONSE = {
    "new_dialect_markers": ["da", "wss", "zever"],
    "new_opinion_fingerprint": ["vindt hype altijd overdreven"],
    "topic_weights_update": {"Videogames": 0.9},
    "new_example_posts": [],
    "frequent_interactions_update": {},
    "persona_summary": "",
    "typical_post_length": None,
}

_ALTER = {
    "user_id": 119,
    "original_username": "radje",
    "reversed_username": "ejdar",
    "post_count": 8432,
    "last_active": "2026-03-09",
}


def test_analyze_first_batch_returns_profile():
    with patch("src.persona.analyzer.call_llm", return_value=json.dumps(_MOCK_ANALYSIS_RESPONSE)):
        profile = analyze_first_batch(_ALTER, _SAMPLE_POSTS)
    assert isinstance(profile, PersonaProfile)
    assert profile.user_id == 119
    assert profile.posts_analyzed == 2
    assert profile.pages_loaded == 0
    assert profile.dialect_markers == ["ge", "ni", "da", "wss"]
    assert profile.formality == "very_casual"
    assert profile.daily_cap == 5
    assert len(profile.example_posts) == 2
    assert "Direct" in profile.persona_summary


def test_analyze_first_batch_calls_api_with_posts():
    with patch("src.persona.analyzer.call_llm", return_value=json.dumps(_MOCK_ANALYSIS_RESPONSE)) as mock_llm:
        analyze_first_batch(_ALTER, _SAMPLE_POSTS)
    mock_llm.assert_called_once()
    _system, user_prompt, _max = mock_llm.call_args[0]
    assert "radje" in user_prompt
    assert "mewgenics" in user_prompt


def test_refine_with_batch_updates_existing_profile():
    existing = PersonaProfile.from_alter_ego(_ALTER)
    existing.posts_analyzed = 100
    existing.pages_loaded = 1
    existing.dialect_markers = ["ge", "ni"]
    existing.opinion_fingerprint = ["sceptisch over hype"]
    with patch("src.persona.analyzer.call_llm", return_value=json.dumps(_MOCK_REFINE_RESPONSE)):
        updated = refine_with_batch(existing, _SAMPLE_POSTS)
    assert updated.posts_analyzed == 102
    assert updated.pages_loaded == 2
    assert "da" in updated.dialect_markers
    assert "ge" in updated.dialect_markers  # existing preserved
    assert "vindt hype altijd overdreven" in updated.opinion_fingerprint
    assert "sceptisch over hype" in updated.opinion_fingerprint  # existing preserved


def test_analyze_raises_on_malformed_json():
    with patch("src.persona.analyzer.call_llm", return_value="this is not json {{{"):
        with pytest.raises(ValueError, match="JSON"):
            analyze_first_batch(_ALTER, _SAMPLE_POSTS)


def test_analyze_first_batch_populates_interest_tags():
    response = dict(_MOCK_ANALYSIS_RESPONSE)
    response["interest_tags"] = ["PlayStation", "Nintendo Switch", "Elden Ring"]
    with patch("src.persona.analyzer.call_llm", return_value=json.dumps(response)):
        profile = analyze_first_batch(_ALTER, _SAMPLE_POSTS)
    assert profile.interest_tags == ["PlayStation", "Nintendo Switch", "Elden Ring"]
