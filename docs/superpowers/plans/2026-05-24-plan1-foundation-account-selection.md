# Shrimp Resurrect — Plan 1: Foundation & Account Selection

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the project foundation and an interactive account selection tool that scrapes the top 100 forum members, filters to those inactive 2+ years, and produces an approved list of alter egos with reversed usernames saved to `config/approved_accounts.json`.

**Architecture:** A Python CLI tool that authenticates with VBulletin via HTTP session, scrapes the memberlist and per-user profile pages, then presents an interactive terminal UI for the forum owner to approve/skip/manually add accounts. All HTTP calls go through a single session module so tests can use saved HTML fixtures instead of live network calls.

**Tech Stack:** Python 3.11+, `requests`, `beautifulsoup4`, `rich` (terminal UI), `python-dotenv`, `pytest`, `freezegun` (date mocking)

---

## File Map

```
forum-community-simulator/
├── config/
│   └── approved_accounts.json    # Output — gitignored, created by this plan
├── src/
│   ├── session.py                # Authenticated VBulletin HTTP session
│   ├── scraper/
│   │   ├── __init__.py
│   │   ├── memberlist.py         # Scrape top N members by post count
│   │   └── profile.py            # Scrape last activity date per user ID
│   ├── selection/
│   │   ├── __init__.py
│   │   ├── pipeline.py           # Filter inactive members, reverse usernames
│   │   └── cli.py                # Rich interactive approval UI
│   └── models.py                 # Member and AlterEgo dataclasses
├── tests/
│   ├── fixtures/
│   │   ├── memberlist.html       # Saved real HTML from memberlist page
│   │   └── profile_119.html      # Saved real HTML from member profile page
│   ├── scraper/
│   │   ├── test_memberlist.py
│   │   └── test_profile.py
│   └── selection/
│       └── test_pipeline.py
├── .env.example
├── .gitignore
├── requirements.txt
└── select_accounts.py            # Entry point: python select_accounts.py
```

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `src/__init__.py`, `src/scraper/__init__.py`, `src/selection/__init__.py`
- Create: `tests/__init__.py`, `tests/fixtures/` (empty dir), `tests/scraper/__init__.py`, `tests/selection/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```
requests==2.32.3
beautifulsoup4==4.12.3
rich==13.7.1
python-dotenv==1.0.1
freezegun==1.5.1
pytest==8.2.2
pytest-cov==5.0.0
```

- [ ] **Step 2: Create .env.example**

```
FORUM_URL=https://your-forum.example.com
FORUM_USERNAME=wokebot
FORUM_PASSWORD=wokebot123
INACTIVITY_YEARS=2
```

- [ ] **Step 3: Create .gitignore**

```
.env
config/approved_accounts.json
config/credentials.json
__pycache__/
*.pyc
.pytest_cache/
.coverage
htmlcov/
```

- [ ] **Step 4: Create all empty `__init__.py` files and the fixtures directory**

```bash
mkdir -p src/scraper src/selection tests/fixtures tests/scraper tests/selection
touch src/__init__.py src/scraper/__init__.py src/selection/__init__.py
touch tests/__init__.py tests/scraper/__init__.py tests/selection/__init__.py
```

- [ ] **Step 5: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .env.example .gitignore src/ tests/
git commit -m "feat: project scaffolding"
```

---

### Task 2: Data models

**Files:**
- Create: `src/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_models.py
from src.models import Member, AlterEgo
from datetime import date

def test_member_fields():
    m = Member(user_id=119, username="radje", post_count=8432, last_active=date(2023, 11, 4))
    assert m.user_id == 119
    assert m.username == "radje"

def test_alter_ego_reversed_username():
    m = Member(user_id=119, username="radje", post_count=8432, last_active=date(2023, 11, 4))
    a = AlterEgo.from_member(m)
    assert a.reversed_username == "ejdar"

def test_alter_ego_reversed_username_palindrome():
    m = Member(user_id=1, username="aba", post_count=100, last_active=date(2020, 1, 1))
    a = AlterEgo.from_member(m)
    assert a.reversed_username == "aba"

def test_alter_ego_to_dict():
    m = Member(user_id=119, username="radje", post_count=8432, last_active=date(2023, 11, 4))
    a = AlterEgo.from_member(m)
    d = a.to_dict()
    assert d["user_id"] == 119
    assert d["original_username"] == "radje"
    assert d["reversed_username"] == "ejdar"
    assert d["post_count"] == 8432
    assert d["last_active"] == "2023-11-04"
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_models.py -v
```

Expected: ImportError — `src.models` does not exist.

- [ ] **Step 3: Implement models**

```python
# src/models.py
from dataclasses import dataclass
from datetime import date

@dataclass
class Member:
    user_id: int
    username: str
    post_count: int
    last_active: date | None

@dataclass
class AlterEgo:
    user_id: int
    original_username: str
    reversed_username: str
    post_count: int
    last_active: date

    @classmethod
    def from_member(cls, member: Member) -> "AlterEgo":
        return cls(
            user_id=member.user_id,
            original_username=member.username,
            reversed_username=member.username[::-1],
            post_count=member.post_count,
            last_active=member.last_active,
        )

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "original_username": self.original_username,
            "reversed_username": self.reversed_username,
            "post_count": self.post_count,
            "last_active": self.last_active.isoformat(),
        }
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_models.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: Member and AlterEgo data models"
```

---

### Task 3: Capture HTML fixtures from live forum

These fixture files are used by all scraper tests. They are committed to the repo so tests never hit the network.

**Files:**
- Create: `tests/fixtures/memberlist.html`
- Create: `tests/fixtures/profile_119.html`

- [ ] **Step 1: Create .env file from .env.example**

```bash
cp .env.example .env
# Edit .env and fill in real credentials
```

- [ ] **Step 2: Write a one-off capture script**

```python
# capture_fixtures.py  (delete after use, do not commit)
import requests
import os
from dotenv import load_dotenv

load_dotenv()

s = requests.Session()
s.post(
    f"{os.getenv('FORUM_URL')}/login.php?do=login",
    data={
        "vb_login_username": os.getenv("FORUM_USERNAME"),
        "vb_login_password": os.getenv("FORUM_PASSWORD"),
        "cookieuser": "1",
        "do": "login",
    },
)

r = s.get(f"{os.getenv('FORUM_URL')}/memberlist.php?order=DESC&sort=posts&pp=100")
with open("tests/fixtures/memberlist.html", "w", encoding="utf-8") as f:
    f.write(r.text)

r = s.get(f"{os.getenv('FORUM_URL')}/member.php?u=119")
with open("tests/fixtures/profile_119.html", "w", encoding="utf-8") as f:
    f.write(r.text)

print("Fixtures saved.")
```

- [ ] **Step 3: Run the capture script**

```bash
python capture_fixtures.py
```

Expected: two HTML files appear in `tests/fixtures/`. Open them in a browser or text editor and verify they contain the memberlist table and radje's profile page with a "Last Activity" date.

- [ ] **Step 4: Delete the capture script**

```bash
rm capture_fixtures.py
```

- [ ] **Step 5: Commit the fixtures**

```bash
git add tests/fixtures/
git commit -m "test: add HTML fixtures for scraper tests"
```

---

### Task 4: Memberlist scraper

**Files:**
- Create: `src/scraper/memberlist.py`
- Create: `tests/scraper/test_memberlist.py`

- [ ] **Step 1: Inspect the fixture to find the CSS selectors**

Open `tests/fixtures/memberlist.html` in a text editor. Find the HTML pattern for each member row. Look for:
- The `<a>` tag whose `href` contains `member.php?u=` — this gives the user ID and username
- The `<td>` cell that contains the post count (a number with commas)

Note the exact tag names and class names you find. You will use them in the parser below.

- [ ] **Step 2: Write failing tests**

```python
# tests/scraper/test_memberlist.py
from pathlib import Path
from src.scraper.memberlist import parse_memberlist

FIXTURE = Path("tests/fixtures/memberlist.html").read_text(encoding="utf-8")

def test_parse_returns_list_of_members():
    members = parse_memberlist(FIXTURE)
    assert isinstance(members, list)
    assert len(members) > 0

def test_parse_member_fields():
    members = parse_memberlist(FIXTURE)
    first = members[0]
    assert isinstance(first.user_id, int)
    assert isinstance(first.username, str)
    assert len(first.username) > 0
    assert isinstance(first.post_count, int)
    assert first.post_count > 0

def test_parse_members_sorted_by_post_count_descending():
    members = parse_memberlist(FIXTURE)
    counts = [m.post_count for m in members]
    assert counts == sorted(counts, reverse=True)

def test_radje_present():
    # radje (user ID 119) is the top member — verify he appears
    members = parse_memberlist(FIXTURE)
    usernames = [m.username.lower() for m in members]
    assert "radje" in usernames

def test_radje_user_id():
    members = parse_memberlist(FIXTURE)
    radje = next(m for m in members if m.username.lower() == "radje")
    assert radje.user_id == 119
```

- [ ] **Step 3: Run to verify they fail**

```bash
pytest tests/scraper/test_memberlist.py -v
```

Expected: ImportError — `src.scraper.memberlist` does not exist.

- [ ] **Step 4: Implement the parser**

Open `tests/fixtures/memberlist.html` and identify the exact selectors, then fill in the parser. The structure below is correct for VBulletin 3.7 — adjust the CSS selectors if the fixture shows different class names.

```python
# src/scraper/memberlist.py
from bs4 import BeautifulSoup
from src.models import Member

def parse_memberlist(html: str) -> list[Member]:
    soup = BeautifulSoup(html, "html.parser")
    members = []

    for row in soup.select("table tr"):
        link = row.find("a", href=lambda h: h and "member.php?u=" in h)
        if not link:
            continue
        href = link["href"]
        try:
            user_id = int(href.split("u=")[1].split("&")[0])
        except (IndexError, ValueError):
            continue

        username = link.get_text(strip=True)
        if not username:
            continue

        # Post count is the first numeric cell with commas after the username cell
        cells = row.find_all("td")
        post_count = None
        for cell in cells:
            text = cell.get_text(strip=True).replace(",", "").replace(".", "")
            if text.isdigit() and int(text) > 0:
                post_count = int(text)
                break

        if post_count is None:
            continue

        members.append(Member(user_id=user_id, username=username, post_count=post_count, last_active=None))

    return sorted(members, key=lambda m: m.post_count, reverse=True)
```

- [ ] **Step 5: Run the tests**

```bash
pytest tests/scraper/test_memberlist.py -v
```

Expected: all 5 tests PASS. If any fail because the fixture HTML uses different selectors, adjust the `select()` call and cell detection logic to match what you observed in Step 1.

- [ ] **Step 6: Commit**

```bash
git add src/scraper/memberlist.py tests/scraper/test_memberlist.py
git commit -m "feat: memberlist scraper"
```

---

### Task 5: Profile scraper

**Files:**
- Create: `src/scraper/profile.py`
- Create: `tests/scraper/test_profile.py`

- [ ] **Step 1: Inspect the profile fixture**

Open `tests/fixtures/profile_119.html`. Find the "Last Activity" date. Note its exact format (e.g., `04-11-2023` or `November 4, 2023`) and the HTML element that contains it.

- [ ] **Step 2: Write failing tests**

```python
# tests/scraper/test_profile.py
from pathlib import Path
from datetime import date
from src.scraper.profile import parse_last_active

FIXTURE = Path("tests/fixtures/profile_119.html").read_text(encoding="utf-8")

def test_parse_returns_date():
    result = parse_last_active(FIXTURE)
    assert isinstance(result, date)

def test_radje_last_active_is_in_the_past():
    # radje is an inactive member — their last active date must be before today
    from datetime import date
    result = parse_last_active(FIXTURE)
    assert result < date.today()

def test_parse_invalid_html_returns_none():
    result = parse_last_active("<html><body>no date here</body></html>")
    assert result is None
```

- [ ] **Step 3: Run to verify they fail**

```bash
pytest tests/scraper/test_profile.py -v
```

Expected: ImportError.

- [ ] **Step 4: Implement the parser**

VBulletin 3.7 profile pages contain "Last Activity" in a `<td>` whose text starts with that phrase. The date format is typically `MM-DD-YYYY`. Adjust the format string if your fixture shows a different format.

```python
# src/scraper/profile.py
from bs4 import BeautifulSoup
from datetime import date, datetime

def parse_last_active(html: str) -> date | None:
    soup = BeautifulSoup(html, "html.parser")
    for td in soup.find_all("td"):
        text = td.get_text(separator=" ", strip=True)
        if "Last Activity" in text or "Last Visit" in text:
            # Extract the date portion — typically "MM-DD-YYYY" after the label
            parts = text.split()
            for part in parts:
                for fmt in ("%m-%d-%Y", "%d-%m-%Y", "%Y-%m-%d"):
                    try:
                        return datetime.strptime(part, fmt).date()
                    except ValueError:
                        continue
    return None
```

- [ ] **Step 5: Run the tests**

```bash
pytest tests/scraper/test_profile.py -v
```

Expected: all 3 tests PASS. If `test_radje_last_active_year` fails, open the fixture and check the exact format of the date, then adjust the `fmt` list in the parser.

- [ ] **Step 6: Commit**

```bash
git add src/scraper/profile.py tests/scraper/test_profile.py
git commit -m "feat: profile last-activity scraper"
```

---

### Task 6: VBulletin session

**Files:**
- Create: `src/session.py`

No unit tests for this module — it wraps live HTTP. It is exercised by the end-to-end run in Task 8.

- [ ] **Step 1: Implement the session**

```python
# src/session.py
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
        resp = self.session.post(
            f"{self.base_url}/login.php?do=login",
            data={
                "vb_login_username": username,
                "vb_login_password": password,
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
```

- [ ] **Step 2: Commit**

```bash
git add src/session.py
git commit -m "feat: authenticated VBulletin HTTP session"
```

---

### Task 7: Account selection pipeline

**Files:**
- Create: `src/selection/pipeline.py`
- Create: `tests/selection/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/selection/test_pipeline.py
from datetime import date
from freezegun import freeze_time
from src.models import Member
from src.selection.pipeline import filter_inactive, build_proposal

@freeze_time("2026-05-24")
def test_filter_inactive_excludes_recent_members():
    members = [
        Member(user_id=1, username="active", post_count=1000, last_active=date(2025, 1, 1)),
        Member(user_id=2, username="gone", post_count=800, last_active=date(2023, 1, 1)),
    ]
    result = filter_inactive(members, min_inactive_years=2)
    assert len(result) == 1
    assert result[0].username == "gone"

@freeze_time("2026-05-24")
def test_filter_inactive_boundary():
    # Exactly 2 years ago today should be excluded (not inactive enough)
    members = [
        Member(user_id=1, username="boundary", post_count=500, last_active=date(2024, 5, 24)),
    ]
    result = filter_inactive(members, min_inactive_years=2)
    assert len(result) == 0

@freeze_time("2026-05-24")
def test_filter_inactive_none_last_active():
    # Members with no last_active date are skipped
    members = [
        Member(user_id=1, username="unknown", post_count=500, last_active=None),
    ]
    result = filter_inactive(members, min_inactive_years=2)
    assert len(result) == 0

def test_build_proposal_returns_alter_egos():
    members = [
        Member(user_id=119, username="radje", post_count=8432, last_active=date(2023, 11, 4)),
        Member(user_id=50, username="test", post_count=1000, last_active=date(2022, 3, 1)),
    ]
    proposal = build_proposal(members, limit=20)
    assert len(proposal) == 2
    assert proposal[0].original_username == "radje"
    assert proposal[0].reversed_username == "ejdar"

def test_build_proposal_respects_limit():
    members = [
        Member(user_id=i, username=f"user{i}", post_count=1000 - i, last_active=date(2020, 1, 1))
        for i in range(30)
    ]
    proposal = build_proposal(members, limit=20)
    assert len(proposal) == 20
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/selection/test_pipeline.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# src/selection/pipeline.py
from datetime import date, timedelta
from src.models import Member, AlterEgo

def filter_inactive(members: list[Member], min_inactive_years: int) -> list[Member]:
    cutoff = date.today().replace(year=date.today().year - min_inactive_years)
    return [
        m for m in members
        if m.last_active is not None and m.last_active < cutoff
    ]

def build_proposal(members: list[Member], limit: int = 20) -> list[AlterEgo]:
    sorted_members = sorted(members, key=lambda m: m.post_count, reverse=True)
    return [AlterEgo.from_member(m) for m in sorted_members[:limit]]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/selection/test_pipeline.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/selection/pipeline.py tests/selection/test_pipeline.py
git commit -m "feat: account selection pipeline with inactivity filter"
```

---

### Task 7: Interactive approval CLI

**Files:**
- Create: `src/selection/cli.py`
- Create: `select_accounts.py`
- Create: `config/` directory (empty, gitignored content)

- [ ] **Step 1: Create the config directory placeholder**

```bash
mkdir -p config
echo "approved_accounts.json" >> config/.gitignore
git add config/.gitignore
```

- [ ] **Step 2: Implement the CLI**

```python
# src/selection/cli.py
import json
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
from src.models import AlterEgo

console = Console()

def run_approval_ui(proposal: list[AlterEgo]) -> list[AlterEgo]:
    approved = []
    console.print("\n[bold cyan]Shrimp Resurrect — Account Selection[/bold cyan]\n")
    console.print(f"Proposed alter egos ({len(proposal)} candidates). For each: [green]y[/green]=approve, [red]n[/red]=skip, [yellow]q[/yellow]=quit.\n")

    for i, alter in enumerate(proposal, 1):
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_row("[dim]#[/dim]", f"[bold]{i}/{len(proposal)}[/bold]")
        table.add_row("[dim]Original[/dim]", alter.original_username)
        table.add_row("[dim]Alter ego[/dim]", f"[cyan]{alter.reversed_username}[/cyan]")
        table.add_row("[dim]Posts[/dim]", f"{alter.post_count:,}")
        table.add_row("[dim]Last active[/dim]", alter.last_active.isoformat())
        console.print(table)

        choice = Prompt.ask("Include?", choices=["y", "n", "q"], default="y")
        if choice == "q":
            break
        if choice == "y":
            approved.append(alter)
        console.print()

    # Allow manual additions
    while True:
        add = Prompt.ask("\nAdd a member manually? Enter username (or press Enter to skip)", default="")
        if not add:
            break
        uid = Prompt.ask("  User ID")
        posts = Prompt.ask("  Post count", default="0")
        last = Prompt.ask("  Last active (YYYY-MM-DD)")
        try:
            from datetime import date
            from src.models import Member
            m = Member(
                user_id=int(uid),
                username=add.strip(),
                post_count=int(posts),
                last_active=date.fromisoformat(last),
            )
            from src.models import AlterEgo as AE
            approved.append(AE.from_member(m))
            console.print(f"[green]Added {add} → {add[::-1]}[/green]")
        except (ValueError, Exception) as e:
            console.print(f"[red]Error: {e}[/red]")

    return approved


def save_approved(approved: list[AlterEgo], path: str = "config/approved_accounts.json") -> None:
    data = [a.to_dict() for a in approved]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    console.print(f"\n[green]Saved {len(approved)} accounts to {path}[/green]")
```

- [ ] **Step 3: Implement the entry point**

```python
# select_accounts.py
import os
from dotenv import load_dotenv
from src.session import VBulletinSession
from src.scraper.memberlist import parse_memberlist
from src.scraper.profile import parse_last_active
from src.selection.pipeline import filter_inactive, build_proposal
from src.selection.cli import run_approval_ui, save_approved
from rich.console import Console

load_dotenv()

console = Console()

def main():
    username = os.getenv("FORUM_USERNAME")
    password = os.getenv("FORUM_PASSWORD")
    inactivity_years = int(os.getenv("INACTIVITY_YEARS", "2"))

    console.print("[bold]Logging in...[/bold]")
    session = VBulletinSession()
    if not session.login(username, password):
        console.print("[red]Login failed. Check credentials in .env[/red]")
        return

    console.print("[bold]Fetching memberlist...[/bold]")
    html = session.get("memberlist.php?order=DESC&sort=posts&pp=100")
    members = parse_memberlist(html)
    console.print(f"  Found {len(members)} members in top 100.")

    console.print("[bold]Fetching last activity dates...[/bold]")
    for i, member in enumerate(members):
        profile_html = session.get(f"member.php?u={member.user_id}")
        member.last_active = parse_last_active(profile_html)
        console.print(f"  [{i+1}/{len(members)}] {member.username}: {member.last_active}")

    inactive = filter_inactive(members, min_inactive_years=inactivity_years)
    console.print(f"\n[bold]{len(inactive)} members inactive for {inactivity_years}+ years.[/bold]")

    proposal = build_proposal(inactive, limit=30)
    approved = run_approval_ui(proposal)

    if approved:
        save_approved(approved)
    else:
        console.print("[yellow]No accounts approved. Nothing saved.[/yellow]")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Commit**

```bash
git add src/selection/cli.py select_accounts.py config/.gitignore
git commit -m "feat: interactive account approval CLI"
```

---

### Task 8: End-to-end run

- [ ] **Step 1: Run the full test suite**

```bash
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 2: Run the account selection tool against the live forum**

```bash
python select_accounts.py
```

Expected:
- Logs in successfully
- Fetches 100 members and their last activity dates (takes ~2 minutes due to 100 profile page requests)
- Shows the interactive approval UI with the top inactive members
- After approval, creates `config/approved_accounts.json`

- [ ] **Step 3: Inspect the output**

```bash
cat config/approved_accounts.json
```

Verify the JSON contains the approved alter egos with correct reversed usernames and user IDs. This file is the input for Plan 2 (Persona Workbench).

- [ ] **Step 4: Final commit**

```bash
git commit -m "chore: plan 1 complete — approved_accounts.json generated"
```

---

## What comes next

**Plan 2 — Persona Workbench:** Takes `config/approved_accounts.json` as input. Scrapes post history per alter ego, runs LLM persona analysis, and provides an iterative refinement UI until each persona is approved. Output: `personas/*.json`.

**Plan 3 — Event Orchestrator:** Takes `personas/*.json` as input. Polls the live forum, runs the six-gate decision pipeline, generates Dutch replies via LLM, routes to review queue, and posts approved replies to VBulletin.
