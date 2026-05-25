from unittest.mock import MagicMock
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


def _make_client(reply_text="Da valt mee"):
    client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=reply_text)]
    msg.stop_reason = "stop"
    client.messages.create.return_value = msg
    return client


def test_generate_reply_calls_api():
    client = _make_client()
    result = generate_reply(client, _make_profile(), _TRIGGERING, _CONTEXT)
    assert result == "Da valt mee"
    client.messages.create.assert_called_once()


def test_generate_reply_includes_context_in_prompt():
    client = _make_client()
    generate_reply(client, _make_profile(), _TRIGGERING, _CONTEXT)
    call_kwargs = client.messages.create.call_args[1]
    user_msg = call_kwargs["messages"][0]["content"]
    assert "Alice" in user_msg
    assert "Wie speelt er nog Zelda?" in user_msg
    assert "Carol" in user_msg
    assert "Is het goed?" in user_msg


def test_generate_reply_prompt_uses_reversed_username():
    client = _make_client()
    generate_reply(client, _make_profile(), _TRIGGERING, _CONTEXT)
    call_kwargs = client.messages.create.call_args[1]
    user_msg = call_kwargs["messages"][0]["content"]
    assert "ejdar" in user_msg


def test_generate_reply_appends_afgekapt_on_max_tokens():
    client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text="Lang antwoord")]
    msg.stop_reason = "max_tokens"
    client.messages.create.return_value = msg
    result = generate_reply(client, _make_profile(), _TRIGGERING, _CONTEXT)
    assert result == "Lang antwoord [afgekapt]"


def test_generate_reply_raises_on_api_error():
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("API down")
    import pytest
    with pytest.raises(RuntimeError):
        generate_reply(client, _make_profile(), _TRIGGERING, _CONTEXT)
