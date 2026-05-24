import hashlib
import os
import requests
from dotenv import load_dotenv

load_dotenv()

class VBulletinSession:
    def __init__(self):
        self.base_url = os.getenv("FORUM_URL", "").rstrip("/")
        self.session = requests.Session()
        self.session.headers["User-Agent"] = (
            "Mozilla/5.0 (compatible; ShrimpResurrect/1.0)"
        )

    def login(self, username: str, password: str) -> bool:
        md5_password = hashlib.md5(password.encode()).hexdigest()
        resp = self.session.post(
            f"{self.base_url}/login.php?do=login",
            data={
                "vb_login_username": username,
                "vb_login_md5password": md5_password,
                "vb_login_md5password_utf": md5_password,
                "cookieuser": "1",
                "do": "login",
                "s": "",
            },
            allow_redirects=True,
        )
        return "Log Out" in resp.text or "User CP" in resp.text

    def get(self, path: str) -> str:
        resp = self.session.get(f"{self.base_url}/{path.lstrip('/')}")
        resp.raise_for_status()
        return resp.text

    def post(self, path: str, data: dict) -> str:
        resp = self.session.post(
            f"{self.base_url}/{path.lstrip('/')}",
            data=data,
            allow_redirects=True,
        )
        resp.raise_for_status()
        return resp.text
