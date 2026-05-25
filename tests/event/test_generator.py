import pytest
from unittest.mock import MagicMock, patch
from src.event.generator import generate_reply
from src.persona.models import PersonaProfile


def _make_profile():
    p = PersonaProfile.from_alter_ego({
        "user_id": 1, "original_username": "radje", "reversed_username": "ejdar",
        "post_count": 100, "last_active": "2023-01-01",
    })
    p.persona_summary = "Direct gamer"
    p.example_posts = ["da klopt nie"]
    return p


_CONTEXT = [
    {"post_id": 10, "author": "Alice", "content": "Wie speelt er nog Zelda?"},
    {"post_id": 11, "author": "Bob", "content": "Ik heb het al uitgespeeld"},
    {"post_id": 12, "author": "Carol", "content": "Is het goed?"},
]
_TRIGGERING = {"post_id": 12, "author": "Carol", "content": "Is het goed?"}


def _make_mock_resp(text="Da valt mee", finish_reason="STOP"):
    resp = MagicMock()
    resp.text = text
    resp.candidates[0].finish_reason.name = finish_reason
    return resp


def test_generate_reply_calls_api():
    with patch("src.event.generator.call_llm_raw", return_value=_make_mock_resp()) as mock_raw:
        result = generate_reply(_make_profile(), _TRIGGERING, _CONTEXT)
    assert result == "Da valt mee"
    mock_raw.assert_called_once()


def test_generate_reply_includes_context_in_prompt():
    with patch("src.event.generator.call_llm_raw", return_value=_make_mock_resp()) as mock_raw:
        generate_reply(_make_profile(), _TRIGGERING, _CONTEXT)
    _system, user_msg, _max = mock_raw.call_args[0]
    assert "Alice" in user_msg
    assert "Wie speelt er nog Zelda?" in user_msg
    assert "Carol" in user_msg
    assert "Is het goed?" in user_msg


def test_generate_reply_prompt_uses_reversed_username():
    with patch("src.event.generator.call_llm_raw", return_value=_make_mock_resp()) as mock_raw:
        generate_reply(_make_profile(), _TRIGGERING, _CONTEXT)
    _system, user_msg, _max = mock_raw.call_args[0]
    assert "ejdar" in user_msg


def test_generate_reply_appends_afgekapt_on_max_tokens():
    with patch("src.event.generator.call_llm_raw", return_value=_make_mock_resp("Lang antwoord", "MAX_TOKENS")):
        result = generate_reply(_make_profile(), _TRIGGERING, _CONTEXT)
    assert result == "Lang antwoord [afgekapt]"


def test_generate_reply_raises_on_api_error():
    with patch("src.event.generator.call_llm_raw", side_effect=RuntimeError("API down")):
        with pytest.raises(RuntimeError):
            generate_reply(_make_profile(), _TRIGGERING, _CONTEXT)
