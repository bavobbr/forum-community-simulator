from unittest.mock import MagicMock
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


def test_generate_replies_returns_one_per_test_post():
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="Typische radje reply")]
    mock_client.messages.create.return_value = mock_message

    results = generate_replies(mock_client, _make_profile(), _TEST_POSTS)

    assert len(results) == 2
    assert mock_client.messages.create.call_count == 2


def test_generate_replies_result_structure():
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="Da weet ik nie hoor")]
    mock_client.messages.create.return_value = mock_message

    results = generate_replies(mock_client, _make_profile(), _TEST_POSTS)

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
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="reply")]
    mock_client.messages.create.return_value = mock_message

    generate_replies(mock_client, _make_profile(), _TEST_POSTS[:1])

    call_kwargs = mock_client.messages.create.call_args[1]
    user_content = call_kwargs["messages"][0]["content"]
    assert "Wtf, hoe kunnen ze dit gedaan hebben?" in user_content
    assert "Zwam" in user_content
    assert "Politiek algemeen" in user_content
