from unittest.mock import MagicMock, patch
import pytest
import requests
from src.session import VBulletinSession


def _make_session() -> VBulletinSession:
    s = VBulletinSession.__new__(VBulletinSession)
    s.base_url = "https://example.com"
    s.session = MagicMock()
    s._security_token = "guest"
    resp = MagicMock()
    resp.text = "ok"
    resp.raise_for_status = MagicMock()
    s.session.get.return_value = resp
    s.session.post.return_value = resp
    return s


def test_get_passes_timeout_to_requests():
    s = _make_session()
    s.get("index.php")
    _, kwargs = s.session.get.call_args
    assert "timeout" in kwargs


def test_post_passes_timeout_to_requests():
    s = _make_session()
    s.post("login.php", data={})
    _, kwargs = s.session.post.call_args
    assert "timeout" in kwargs


def test_get_raises_on_timeout():
    s = _make_session()
    s.session.get.side_effect = requests.exceptions.Timeout
    with pytest.raises(requests.exceptions.Timeout):
        s.get("slow.php")



def test_post_encodes_form_data_as_latin1():
    s = _make_session()
    s.post("reply.php", data={"message": "scène"})
    _, kwargs = s.session.post.call_args
    body = kwargs.get("data", b"")
    # è in Latin-1 → byte 0xE8 → percent-encoded as %E8
    assert b"%E8" in body or b"%e8" in body
    # not the UTF-8 encoding %C3%A8
    assert b"%C3%A8" not in body and b"%c3%a8" not in body
