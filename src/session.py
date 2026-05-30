import hashlib
import os
import re
import requests
from dotenv import load_dotenv

load_dotenv()

_TOKEN_RE = re.compile(r"SECURITYTOKEN\s*=\s*['\"]([^'\"]+)['\"]")
_TIMEOUT = 30


class VBulletinSession:
    def __init__(self):
        self.base_url = os.getenv("FORUM_URL", "").rstrip("/")
        self.session = requests.Session()
        self.session.headers["User-Agent"] = (
            "Mozilla/5.0 (compatible; ForumCommunitySimulator/1.0)"
        )
        self._security_token: str = "guest"

    @property
    def security_token(self) -> str:
        return self._security_token

    def login(self, username: str, password: str) -> bool:
        md5_password = hashlib.md5(password.encode()).hexdigest()
        self.session.post(
            f"{self.base_url}/login.php?do=login",
            data={
                "vb_login_username": username,
                "vb_login_password": "",
                "vb_login_md5password": md5_password,
                "vb_login_md5password_utf": md5_password,
                "cookieuser": "1",
                "do": "login",
                "s": "",
                "securitytoken": "guest",
            },
            allow_redirects=True,
        )
        # VBulletin's POST response is a splash page — verify by checking index
        index = self.session.get(f"{self.base_url}/index.php")
        logged_in = "Log Out" in index.text or "User CP" in index.text
        if logged_in:
            m = _TOKEN_RE.search(index.text)
            if m:
                self._security_token = m.group(1)
        return logged_in

    def get(self, path: str) -> str:
        resp = self.session.get(f"{self.base_url}/{path.lstrip('/')}", timeout=_TIMEOUT)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        return resp.text

    def post(self, path: str, data: dict) -> str:
        resp = self.session.post(
            f"{self.base_url}/{path.lstrip('/')}",
            data=data,
            allow_redirects=True,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        resp.encoding = "utf-8"
        return resp.text
