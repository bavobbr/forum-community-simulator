import json
import pytest
from unittest.mock import patch
from src.persona.models import PersonaProfile
from src.persona.analyzer import analyze_first_batch, refine_with_batch, _select_examples

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


def test_refine_merges_new_interest_tags():
    existing = PersonaProfile.from_alter_ego(_ALTER)
    existing.posts_analyzed = 100
    existing.pages_loaded = 1
    existing.interest_tags = ["PlayStation"]
    response = dict(_MOCK_REFINE_RESPONSE)
    response["new_interest_tags"] = ["Nintendo Switch", "PlayStation"]  # PlayStation is a duplicate
    with patch("src.persona.analyzer.call_llm", return_value=json.dumps(response)):
        updated = refine_with_batch(existing, _SAMPLE_POSTS)
    assert "Nintendo Switch" in updated.interest_tags
    assert updated.interest_tags.count("PlayStation") == 1  # no duplicate


def test_refine_includes_existing_tags_in_prompt():
    existing = PersonaProfile.from_alter_ego(_ALTER)
    existing.posts_analyzed = 100
    existing.pages_loaded = 1
    existing.interest_tags = ["wielrennen", "Remco Evenepoel"]
    response = dict(_MOCK_REFINE_RESPONSE)
    response["new_interest_tags"] = []
    with patch("src.persona.analyzer.call_llm", return_value=json.dumps(response)) as mock_llm:
        refine_with_batch(existing, _SAMPLE_POSTS)
    _, user_prompt, _ = mock_llm.call_args[0]
    assert "wielrennen" in user_prompt


# --- _select_examples ---

_LONG_POSTS = [
    {"post_id": i, "thread_id": 1, "thread_title": "Zwam talk", "forum_id": 9,
     "forum_name": "Zwam", "date": "01-01-2024, 10:00", "quoted_users": [],
     "content": f"post nummer {i} " * 30}
    for i in range(1, 21)
]
_SHORT_POST = {"post_id": 99, "forum_name": "Zwam", "content": "ok"}


def test_select_examples_returns_up_to_n():
    result = _select_examples(_LONG_POSTS, n=5)
    assert len(result) == 5


def test_select_examples_returns_all_when_fewer_than_n():
    result = _select_examples(_LONG_POSTS[:3], n=10)
    assert len(result) == 3


def test_select_examples_filters_posts_shorter_than_20_chars():
    result = _select_examples([_SHORT_POST], n=10)
    assert result == []


def test_select_examples_truncates_content_to_max_chars():
    long = [{"post_id": 1, "forum_name": "Zwam", "content": "x" * 1000}]
    result = _select_examples(long, n=1, max_chars=400)
    assert result == ["x" * 400]


def test_select_examples_returns_empty_for_empty_input():
    assert _select_examples([], n=10) == []


def test_select_examples_spreads_across_posts():
    posts = [{"post_id": i, "forum_name": "Zwam", "content": f"bericht {i} " * 10} for i in range(1, 101)]
    result = _select_examples(posts, n=10)
    ids = [int(r.split()[1]) for r in result]
    assert max(ids) - min(ids) > 50  # spread across the 100 posts


# --- example_posts no longer come from Gemini ---

def test_analyze_first_batch_example_posts_come_from_posts_not_gemini():
    response = dict(_MOCK_ANALYSIS_RESPONSE)
    response["example_posts"] = ["GEMINI FABRICATED THIS"]
    with patch("src.persona.analyzer.call_llm", return_value=json.dumps(response)):
        profile = analyze_first_batch(_ALTER, _SAMPLE_POSTS)
    assert "GEMINI FABRICATED THIS" not in profile.example_posts
    assert any("mewgenics" in ex for ex in profile.example_posts)


def test_analyze_first_batch_schema_does_not_request_example_posts():
    with patch("src.persona.analyzer.call_llm", return_value=json.dumps(_MOCK_ANALYSIS_RESPONSE)) as mock_llm:
        analyze_first_batch(_ALTER, _SAMPLE_POSTS)
    _, user_prompt, _ = mock_llm.call_args[0]
    assert "example_posts" not in user_prompt


def test_refine_fills_up_examples_when_profile_has_fewer_than_10():
    existing = PersonaProfile.from_alter_ego(_ALTER)
    existing.posts_analyzed = 2
    existing.pages_loaded = 1
    existing.example_posts = ["één voorbeeld"]  # only 1
    with patch("src.persona.analyzer.call_llm", return_value=json.dumps(_MOCK_REFINE_RESPONSE)):
        updated = refine_with_batch(existing, _LONG_POSTS)
    assert len(updated.example_posts) > 1


def test_refine_does_not_add_examples_when_profile_already_has_10():
    existing = PersonaProfile.from_alter_ego(_ALTER)
    existing.posts_analyzed = 200
    existing.pages_loaded = 1
    existing.example_posts = [f"voorbeeld {i}" for i in range(10)]
    with patch("src.persona.analyzer.call_llm", return_value=json.dumps(_MOCK_REFINE_RESPONSE)):
        updated = refine_with_batch(existing, _LONG_POSTS)
    assert len(updated.example_posts) == 10
    assert updated.example_posts[0] == "voorbeeld 0"  # originals preserved
