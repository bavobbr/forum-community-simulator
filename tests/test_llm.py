from unittest.mock import MagicMock, patch
import src.llm as llm_module


def test_call_llm_returns_response_text():
    mock_resp = MagicMock()
    mock_resp.text = "het antwoord"
    with patch.object(llm_module, "_client") as mock_client:
        mock_client.models.generate_content.return_value = mock_resp
        result = llm_module.call_llm("systeem", "gebruiker", 200)
    assert result == "het antwoord"


def test_call_llm_uses_pro_model():
    mock_resp = MagicMock()
    mock_resp.text = "antwoord"
    with patch.object(llm_module, "_client") as mock_client:
        mock_client.models.generate_content.return_value = mock_resp
        llm_module.call_llm("mijn systeem", "mijn vraag", 400)
    call_kwargs = mock_client.models.generate_content.call_args[1]
    assert call_kwargs["model"] == "gemini-3.1-pro-preview"
    assert call_kwargs["contents"] == ["mijn vraag"]


def test_call_llm_raw_returns_response_object():
    mock_resp = MagicMock()
    mock_resp.text = "antwoord"
    with patch.object(llm_module, "_client") as mock_client:
        mock_client.models.generate_content.return_value = mock_resp
        resp = llm_module.call_llm_raw("systeem", "vraag", 400)
    assert resp is mock_resp


def test_call_llm_raw_defaults_to_flash_model():
    mock_resp = MagicMock()
    mock_resp.text = "x"
    with patch.object(llm_module, "_client") as mock_client:
        mock_client.models.generate_content.return_value = mock_resp
        llm_module.call_llm_raw("s", "u", 777)
    call_kwargs = mock_client.models.generate_content.call_args[1]
    assert call_kwargs["model"] == "gemini-3.5-flash"
    assert call_kwargs["config"].max_output_tokens == 777


def test_call_llm_raw_accepts_model_override():
    mock_resp = MagicMock()
    mock_resp.text = "x"
    with patch.object(llm_module, "_client") as mock_client:
        mock_client.models.generate_content.return_value = mock_resp
        llm_module.call_llm_raw("s", "u", 400, model="gemini-3.1-pro-preview")
    call_kwargs = mock_client.models.generate_content.call_args[1]
    assert call_kwargs["model"] == "gemini-3.1-pro-preview"
