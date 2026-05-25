from unittest.mock import MagicMock, patch
from src.event.poster import post_reply


def _make_form_html(token="abc123", thread_id=21666):
    return f"""
    <form action="newreply.php?do=postreply&t={thread_id}" method="post">
      <input type="hidden" name="securitytoken" value="{token}"/>
      <input type="hidden" name="do" value="postreply"/>
      <input type="hidden" name="t" value="{thread_id}"/>
      <input type="hidden" name="s" value=""/>
      <textarea name="message"></textarea>
      <input type="submit" name="sbutton" value="Submit Reply"/>
    </form>
    """


def test_post_reply_success():
    with patch("src.event.poster.VBulletinSession") as MockSession:
        session = MagicMock()
        MockSession.return_value = session
        session.login.return_value = True
        session.get.return_value = _make_form_html()
        session.post.return_value = "<html>thread content, no errors</html>"

        result = post_reply("ejdar", "password", 21666, "Da is goed :D")

    assert result is True
    session.login.assert_called_once_with("ejdar", "password")
    call_kwargs = session.post.call_args
    posted_data = call_kwargs[0][1]
    assert posted_data["message"] == "Da is goed :D"
    assert posted_data["securitytoken"] == "abc123"
    assert posted_data["wysiwyg"] == "0"


def test_post_reply_returns_false_on_login_failure():
    with patch("src.event.poster.VBulletinSession") as MockSession:
        session = MagicMock()
        MockSession.return_value = session
        session.login.return_value = False
        result = post_reply("ejdar", "wrongpass", 21666, "test")
    assert result is False


def test_post_reply_returns_false_on_error_block():
    with patch("src.event.poster.VBulletinSession") as MockSession:
        session = MagicMock()
        MockSession.return_value = session
        session.login.return_value = True
        session.get.return_value = _make_form_html()
        session.post.return_value = '<div class="blockrow error">U heeft geen toestemming</div>'
        result = post_reply("ejdar", "password", 21666, "test")
    assert result is False
