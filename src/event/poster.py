import logging
from bs4 import BeautifulSoup
from src.session import VBulletinSession


def post_reply(alter_username: str, password: str, thread_id: int, message: str) -> bool:
    """Login as alter ego and post reply. Returns True on success."""
    session = VBulletinSession()
    if not session.login(alter_username, password):
        logging.warning("Login failed for alter %s", alter_username)
        return False

    html = session.get(f"newreply.php?t={thread_id}&noquote=1")
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", action=lambda a: a and "postreply" in str(a))
    if not form:
        logging.warning("Reply form not found for thread %d", thread_id)
        return False

    data: dict[str, str] = {}
    for inp in form.find_all("input"):
        if inp.get("type") == "hidden" and inp.get("name"):
            data[inp["name"]] = inp.get("value", "")

    data["message"] = message
    data["wysiwyg"] = "0"
    data["sbutton"] = "Submit Reply"

    resp = session.post(f"newreply.php?do=postreply&t={thread_id}", data)
    soup2 = BeautifulSoup(resp, "html.parser")
    if soup2.find("div", class_="blockrow error") or soup2.find("div", class_="error"):
        logging.warning("VBulletin returned error for alter %s thread %d", alter_username, thread_id)
        return False
    return True
