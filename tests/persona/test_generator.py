from unittest.mock import MagicMock, patch
from src.persona.models import PersonaProfile
from src.persona.generator import generate_replies, build_system_prompt


def _make_profile() -> PersonaProfile:
    p = PersonaProfile.from_alter_ego({
        "user_id": 119,
        "original_username": "radje",
        "reversed_username": "ejdar",
        "post_count": 8432,
        "last_active": "2023-11-04",
    })
    p.persona_summary = "Direct en nuchter gamer. Schrijft in Vlaams dialect, kort en bondig."
    p.dialect_markers = ["ge", "ni", "da"]
    p.formality = "very_casual"
    p.sentence_length = "short"
    p.typical_post_length = "short"
    p.example_posts = [
        "mewgenics is raar genoeg mijn ding ni, klikt ni.",
        "ge zijt echt ne zever man",
    ]
    return p


_TEST_POSTS = [
    {"id": 1, "label": "Politiek debat", "forum": "Zwam", "thread_title": "Politiek algemeen", "post": "Wtf, hoe kunnen ze dit gedaan hebben?"},
    {"id": 2, "label": "Gaming hot take", "forum": "Videogames", "thread_title": "Welke spellekes zijde mee bezig", "post": "Is de nieuwe Zelda goed?"},
]


def _make_mock_resp(text="Typische radje reply", finish_reason="STOP"):
    resp = MagicMock()
    resp.text = text
    resp.candidates[0].finish_reason.name = finish_reason
    return resp


def test_generate_replies_returns_one_per_test_post():
    with patch("src.persona.generator.call_llm_raw", return_value=_make_mock_resp()) as mock_raw:
        results = generate_replies(_make_profile(), _TEST_POSTS)
    assert len(results) == 2
    assert mock_raw.call_count == 2


def test_generate_replies_result_structure():
    with patch("src.persona.generator.call_llm_raw", return_value=_make_mock_resp("Da weet ik nie hoor")):
        results = generate_replies(_make_profile(), _TEST_POSTS)
    for r in results:
        assert "label" in r
        assert "post" in r
        assert "reply" in r
        assert "id" in r
        assert r["reply"] == "Da weet ik nie hoor"


def test_build_system_prompt_includes_persona_info():
    profile = _make_profile()
    prompt = build_system_prompt(profile)
    assert "radje" in prompt
    assert "Direct en nuchter" in prompt
    assert "ge" in prompt
    assert "mewgenics" in prompt
    assert "Nederlands" in prompt or "Dutch" in prompt or "Nederlandstalig" in prompt


def test_generate_replies_api_receives_test_post_content():
    with patch("src.persona.generator.call_llm_raw", return_value=_make_mock_resp()) as mock_raw:
        generate_replies(_make_profile(), _TEST_POSTS[:1])
    _system, user_content, _max = mock_raw.call_args[0]
    assert "Wtf, hoe kunnen ze dit gedaan hebben?" in user_content
    assert "Zwam" in user_content
    assert "Politiek algemeen" in user_content


def test_generate_replies_appends_afgekapt_on_max_tokens():
    with patch("src.persona.generator.call_llm_raw", return_value=_make_mock_resp("Lang antwoord", "MAX_TOKENS")):
        results = generate_replies(_make_profile(), _TEST_POSTS[:1])
    assert results[0]["reply"] == "Lang antwoord [afgekapt]"


def test_build_system_prompt_truncates_examples_to_400_chars():
    profile = _make_profile()
    profile.example_posts = ["x" * 1000]
    prompt = build_system_prompt(profile)
    assert "x" * 401 not in prompt
    assert "x" * 400 in prompt


def test_build_system_prompt_uses_at_most_10_examples():
    profile = _make_profile()
    profile.example_posts = [f"voorbeeld {i}" for i in range(25)]
    prompt = build_system_prompt(profile)
    assert "voorbeeld 10" not in prompt
    assert "voorbeeld 9" in prompt
