# Plan 2: Persona Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an interactive terminal workbench that scrapes post history per alter ego, builds and iteratively refines persona profiles via Claude API, and lets the forum owner approve each of the 25 personas before going live.

**Architecture:** A paginated post scraper fetches posts from VBulletin's "finduser" search page (100 per page). The first analysis batch combines pages 1+2 (200 posts); each subsequent batch loads one page (100 posts). An LLM analyzer builds and refines a `PersonaProfile` JSON doc from those posts. A Rich terminal workbench ties it together: load batch → analyze → show sample replies → rate → repeat until approved. Approved profiles land in `personas/{username}.json`.

**Tech Stack:** Python, anthropic SDK, beautifulsoup4, rich, requests, pytest

---

## File Map

| File | Role |
|---|---|
| `requirements.txt` | Add `anthropic` dependency |
| `.env` / `.env.example` | Add `ANTHROPIC_API_KEY` |
| `src/persona/__init__.py` | Package marker |
| `src/persona/models.py` | `PersonaProfile` dataclass with `to_dict` / `from_dict` / `from_alter_ego` |
| `src/persona/scraper.py` | `parse_posts_page()`, `parse_search_id()`, `parse_has_next_page()`, `PostScraper`; initial batch fetches 2 pages (200 posts) in the CLI, not here |
| `src/persona/analyzer.py` | `analyze_first_batch()`, `refine_with_batch()` — calls Anthropic API |
| `src/persona/generator.py` | `generate_replies()` — generates sample replies against test posts |
| `src/workbench/__init__.py` | Package marker |
| `src/workbench/cli.py` | Rich terminal workbench loop: persona list → load-analyze-rate cycle → approve |
| `config/test_posts.json` | Canonical 5-post Dutch test set used for all personas |
| `personas/` | Output dir (gitignored); one JSON file per approved persona |
| `workbench.py` | Entry point: login → load approved accounts → run workbench CLI |
| `tests/persona/__init__.py` | Package marker |
| `tests/persona/test_models.py` | Unit tests for PersonaProfile serialisation |
| `tests/persona/test_scraper.py` | Unit tests for HTML parsers (uses existing fixture) |
| `tests/persona/test_analyzer.py` | Unit tests for analyzer (mocked Anthropic client) |
| `tests/persona/test_generator.py` | Unit tests for generator (mocked Anthropic client) |
| `tests/workbench/__init__.py` | Package marker |

---

## Task 1: Persona Profile Model + Dependencies

**Files:**
- Modify: `requirements.txt`
- Modify: `.env`
- Modify: `.env.example`
- Create: `src/persona/__init__.py`
- Create: `src/persona/models.py`
- Create: `tests/persona/__init__.py`
- Create: `tests/persona/test_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/persona/__init__.py` (empty) and `tests/persona/test_models.py`:

```python
from src.persona.models import PersonaProfile


def _sample_alter() -> dict:
    return {
        "user_id": 10,
        "original_username": "Trojan",
        "reversed_username": "najorT",
        "post_count": 18123,
        "last_active": "2013-06-07",
    }


def test_from_alter_ego_creates_blank_profile():
    profile = PersonaProfile.from_alter_ego(_sample_alter())
    assert profile.user_id == 10
    assert profile.original_username == "Trojan"
    assert profile.reversed_username == "najorT"
    assert profile.post_count == 18123
    assert profile.last_active == "2013-06-07"
    assert profile.posts_analyzed == 0
    assert profile.is_approved is False
    assert profile.example_posts == []


def test_to_dict_round_trips():
    profile = PersonaProfile.from_alter_ego(_sample_alter())
    profile.posts_analyzed = 100
    profile.is_approved = True
    profile.dialect_markers = ["ge", "da", "ni"]
    profile.example_posts = ["post one", "post two"]
    profile.persona_summary = "Direct, flemish gamer"

    d = profile.to_dict()
    restored = PersonaProfile.from_dict(d)

    assert restored.user_id == 10
    assert restored.posts_analyzed == 100
    assert restored.is_approved is True
    assert restored.dialect_markers == ["ge", "da", "ni"]
    assert restored.example_posts == ["post one", "post two"]
    assert restored.persona_summary == "Direct, flemish gamer"


def test_from_dict_handles_missing_optional_fields():
    minimal = {
        "user_id": 42,
        "original_username": "foo",
        "reversed_username": "oof",
        "post_count": 100,
        "last_active": "2020-01-01",
    }
    profile = PersonaProfile.from_dict(minimal)
    assert profile.daily_cap == 10
    assert profile.hourly_cap == 3
    assert profile.topic_weights == {}
    assert profile.opinion_fingerprint == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && python -m pytest tests/persona/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.persona'`

- [ ] **Step 3: Create the persona model**

Create `src/persona/__init__.py` (empty).

Create `src/persona/models.py`:

```python
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class PersonaProfile:
    # Identity (from approved_accounts.json)
    user_id: int
    original_username: str
    reversed_username: str
    post_count: int
    last_active: str  # ISO date string

    # Analysis state
    posts_analyzed: int = 0
    pages_loaded: int = 0
    is_approved: bool = False

    # Writing style (LLM-derived)
    dialect_markers: list[str] = field(default_factory=list)
    formality: str = "casual"
    sentence_length: str = "medium"
    bbcode_habits: list[str] = field(default_factory=list)
    punctuation_style: str = ""

    # Topics: forum_name -> weight 0.0-1.0
    topic_weights: dict[str, float] = field(default_factory=dict)
    opinion_fingerprint: list[str] = field(default_factory=list)

    # Relationships: username -> "ally" | "rival" | "neutral"
    frequent_interactions: dict[str, str] = field(default_factory=dict)

    # Activity pattern
    peak_hours: list[int] = field(default_factory=list)

    # Post length characteristics
    typical_post_length: str = "medium"  # "short" | "medium" | "long"

    # Rate limits
    daily_cap: int = 10
    hourly_cap: int = 3

    # Few-shot examples and narrative summary
    example_posts: list[str] = field(default_factory=list)
    persona_summary: str = ""

    @classmethod
    def from_alter_ego(cls, alter: dict) -> "PersonaProfile":
        return cls(
            user_id=alter["user_id"],
            original_username=alter["original_username"],
            reversed_username=alter["reversed_username"],
            post_count=alter["post_count"],
            last_active=alter["last_active"],
        )

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "original_username": self.original_username,
            "reversed_username": self.reversed_username,
            "post_count": self.post_count,
            "last_active": self.last_active,
            "posts_analyzed": self.posts_analyzed,
            "pages_loaded": self.pages_loaded,
            "is_approved": self.is_approved,
            "dialect_markers": self.dialect_markers,
            "formality": self.formality,
            "sentence_length": self.sentence_length,
            "bbcode_habits": self.bbcode_habits,
            "punctuation_style": self.punctuation_style,
            "topic_weights": self.topic_weights,
            "opinion_fingerprint": self.opinion_fingerprint,
            "frequent_interactions": self.frequent_interactions,
            "peak_hours": self.peak_hours,
            "typical_post_length": self.typical_post_length,
            "daily_cap": self.daily_cap,
            "hourly_cap": self.hourly_cap,
            "example_posts": self.example_posts,
            "persona_summary": self.persona_summary,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PersonaProfile":
        return cls(
            user_id=d["user_id"],
            original_username=d["original_username"],
            reversed_username=d["reversed_username"],
            post_count=d["post_count"],
            last_active=d["last_active"],
            posts_analyzed=d.get("posts_analyzed", 0),
            pages_loaded=d.get("pages_loaded", 0),
            is_approved=d.get("is_approved", False),
            dialect_markers=d.get("dialect_markers", []),
            formality=d.get("formality", "casual"),
            sentence_length=d.get("sentence_length", "medium"),
            bbcode_habits=d.get("bbcode_habits", []),
            punctuation_style=d.get("punctuation_style", ""),
            topic_weights=d.get("topic_weights", {}),
            opinion_fingerprint=d.get("opinion_fingerprint", []),
            frequent_interactions=d.get("frequent_interactions", {}),
            peak_hours=d.get("peak_hours", []),
            typical_post_length=d.get("typical_post_length", "medium"),
            daily_cap=d.get("daily_cap", 10),
            hourly_cap=d.get("hourly_cap", 3),
            example_posts=d.get("example_posts", []),
            persona_summary=d.get("persona_summary", ""),
        )
```

- [ ] **Step 4: Add anthropic dependency**

Edit `requirements.txt` — add `anthropic==0.49.0` (or latest stable at install time):

```
requests==2.32.3
beautifulsoup4==4.12.3
rich==13.7.1
python-dotenv==1.0.1
anthropic>=0.49.0
freezegun==1.5.1
pytest==8.2.2
pytest-cov==5.0.0
```

Add to `.env` and `.env.example`:

```
ANTHROPIC_API_KEY=your_key_here
```

Install:

```bash
pip install anthropic
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && python -m pytest tests/persona/test_models.py -v
```

Expected: 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/persona/__init__.py src/persona/models.py tests/persona/__init__.py tests/persona/test_models.py requirements.txt .env.example
git commit -m "feat: add PersonaProfile model and anthropic dependency"
```

---

## Task 2: Post Content Scraper

**Files:**
- Create: `src/persona/scraper.py`
- Create: `tests/persona/test_scraper.py`

This scraper parses the VBulletin `search.php?do=finduser` page. We already have a fixture (`tests/fixtures/search_user_119.html`) captured during Plan 1. Each post lives in `<table id="post{id}">`. The fixture shows user radje (id 119), 200 total results, 8 pages of 25, with a searchid in pagination links. The scraper always fetches 100 posts per page; combining pages into a 200-post initial batch is the CLI's responsibility, not the scraper's.

- [ ] **Step 1: Write the failing tests**

Create `tests/persona/test_scraper.py`:

```python
import re
from pathlib import Path
from src.persona.scraper import parse_posts_page, parse_search_id, parse_has_next_page

FIXTURE = (Path(__file__).parent.parent / "fixtures" / "search_user_119.html").read_text(
    encoding="latin-1"
)


def test_parse_posts_page_returns_correct_count():
    posts = parse_posts_page(FIXTURE)
    assert len(posts) == 25  # default pp=25 in fixture


def test_parse_posts_page_post_structure():
    posts = parse_posts_page(FIXTURE)
    first = posts[0]
    assert first["post_id"] == 1743241
    assert first["thread_id"] == 12769
    assert first["thread_title"] == "Welke spellekes zijde mee bezig"
    assert first["forum_id"] == 22
    assert first["forum_name"] == "Videogames"
    assert "mewgenics" in first["content"]
    assert first["date"] == "09-03-2026, 19:04"


def test_parse_posts_page_content_has_substance():
    posts = parse_posts_page(FIXTURE)
    for post in posts:
        assert len(post["content"]) > 10, f"Post {post['post_id']} has too little content"


def test_parse_search_id_extracts_id():
    search_id = parse_search_id(FIXTURE)
    assert search_id == "11065652"


def test_parse_has_next_page_true_when_multiple_pages():
    assert parse_has_next_page(FIXTURE) is True


def test_parse_has_next_page_false_on_single_page():
    single_page_html = "<html><body><div>Results 1 to 5 of 5</div></body></html>"
    assert parse_has_next_page(single_page_html) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && python -m pytest tests/persona/test_scraper.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.persona.scraper'`

- [ ] **Step 3: Implement the post scraper parsers**

Create `src/persona/scraper.py`:

```python
import re
import time
from bs4 import BeautifulSoup
from src.session import VBulletinSession

_POST_ID_PATTERN = re.compile(r"^post(\d+)$")
_FORUM_ID_PATTERN = re.compile(r"f=(\d+)")
_THREAD_ID_PATTERN = re.compile(r"t=(\d+)")
_DATE_PATTERN = re.compile(r"\b(\d{2}-\d{2}-\d{4}),\s*(\d{2}:\d{2})\b")
_SEARCH_ID_PATTERN = re.compile(r"searchid=(\d+)")


def parse_posts_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    posts = []

    for table in soup.find_all("table", id=_POST_ID_PATTERN):
        post_id_match = _POST_ID_PATTERN.match(table["id"])
        if not post_id_match:
            continue
        post_id = int(post_id_match.group(1))

        thead = table.find("td", class_="thead")
        if not thead:
            continue

        forum_link = thead.find("a", href=_FORUM_ID_PATTERN)
        forum_name = forum_link.get_text(strip=True) if forum_link else ""
        forum_id_match = _FORUM_ID_PATTERN.search(forum_link["href"]) if forum_link else None
        forum_id = int(forum_id_match.group(1)) if forum_id_match else 0

        thead_text = thead.get_text(separator=" ", strip=True)
        date_match = _DATE_PATTERN.search(thead_text)
        post_date = f"{date_match.group(1)}, {date_match.group(2)}" if date_match else ""

        alt1 = table.find("td", class_="alt1")
        if not alt1:
            continue

        thread_link = alt1.find("a", href=_THREAD_ID_PATTERN)
        thread_title = ""
        thread_id = 0
        if thread_link:
            strong = thread_link.find("strong")
            thread_title = strong.get_text(strip=True) if strong else thread_link.get_text(strip=True)
            tid_match = _THREAD_ID_PATTERN.search(thread_link["href"])
            thread_id = int(tid_match.group(1)) if tid_match else 0

        content = ""
        content_div = alt1.find("div", class_="alt2")
        if content_div:
            em = content_div.find("em")
            if em:
                post_link = em.find("a")
                if post_link:
                    post_link.decompose()
                content = em.get_text(separator=" ", strip=True)

        posts.append({
            "post_id": post_id,
            "thread_id": thread_id,
            "thread_title": thread_title,
            "forum_id": forum_id,
            "forum_name": forum_name,
            "date": post_date,
            "content": content,
        })

    return posts


def parse_search_id(html: str) -> str | None:
    match = _SEARCH_ID_PATTERN.search(html)
    return match.group(1) if match else None


def parse_has_next_page(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    return bool(soup.find("a", title=re.compile(r"Next Page", re.IGNORECASE)))


class PostScraper:
    def __init__(self, session: VBulletinSession, delay: int = 6):
        self.session = session
        self.delay = delay
        self._search_ids: dict[int, str] = {}

    def fetch_batch(self, user_id: int, page: int = 1) -> tuple[list[dict], bool]:
        """Fetch one page of posts. Returns (posts, has_more_pages).
        Page 1 initialises the search and caches the searchid for subsequent pages."""
        time.sleep(self.delay)

        if page == 1:
            html = self.session.get(f"search.php?do=finduser&u={user_id}&pp=100")
            search_id = parse_search_id(html)
            if search_id:
                self._search_ids[user_id] = search_id
        else:
            search_id = self._search_ids.get(user_id)
            if not search_id:
                raise ValueError(f"No searchid for user {user_id}. Call page=1 first.")
            html = self.session.get(f"search.php?searchid={search_id}&pp=100&page={page}")

        posts = parse_posts_page(html)
        has_more = parse_has_next_page(html)
        return posts, has_more
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && python -m pytest tests/persona/test_scraper.py -v
```

Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/persona/scraper.py tests/persona/test_scraper.py
git commit -m "feat: add post content scraper for finduser search results"
```

---

## Task 3: Test Post Set Config

**Files:**
- Create: `config/test_posts.json`
- Create: `tests/workbench/__init__.py`

This is the fixed set of 5 Dutch test prompts used across all 25 personas. They never change; they're how we compare persona quality over iterations.

- [ ] **Step 1: Create the test post set**

Create `config/test_posts.json`:

```json
[
  {
    "id": 1,
    "label": "Politiek debat",
    "post": "Wtf, hoe kunnen ze dit gedaan hebben? Ik snap echt niet hoe mensen nog op die idioten stemmen. Ge moet blind zijn om dat ni te zien."
  },
  {
    "id": 2,
    "label": "Gaming hot take",
    "post": "Hebben jullie al de nieuwe Zelda gespeeld? Is't goed of typisch weer overhyped Nintendo gedoe voor de fanboys?"
  },
  {
    "id": 3,
    "label": "Directe banter",
    "post": "Ge kunt toch echt nie spelen hoor, zagen we wel genoeg gisteren. Absolute bot lol"
  },
  {
    "id": 4,
    "label": "Film mening",
    "post": "Inception is de beste film aller tijden en als ge dat ni begrijpt zijt ge gewoon te dom. Fight me."
  },
  {
    "id": 5,
    "label": "Agressieve tegenstand",
    "post": "Dat is echt de domste mening die ik ooit gelezen heb op dit forum. Serieus, hoe durft ge dat te typen."
  }
]
```

Create `tests/workbench/__init__.py` (empty).

- [ ] **Step 2: Verify the file loads correctly**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && python -c "
import json
posts = json.loads(open('config/test_posts.json').read())
assert len(posts) == 5
assert all('id' in p and 'label' in p and 'post' in p for p in posts)
print('OK:', [p['label'] for p in posts])
"
```

Expected: `OK: ['Politiek debat', 'Gaming hot take', 'Directe banter', 'Film mening', 'Agressieve tegenstand']`

- [ ] **Step 3: Commit**

```bash
git add config/test_posts.json tests/workbench/__init__.py
git commit -m "feat: add canonical Dutch test post set for persona validation"
```

---

## Task 4: LLM Persona Analyzer

**Files:**
- Create: `src/persona/analyzer.py`
- Create: `tests/persona/test_analyzer.py`

The analyzer calls Claude via the Anthropic SDK. It takes a list of post dicts and the current profile (or None for first batch), and returns an updated PersonaProfile. JSON is parsed from the API response. If JSON parsing fails, the profile is returned unchanged with a warning — never crash.

- [ ] **Step 1: Write the failing tests**

Create `tests/persona/test_analyzer.py`:

```python
import json
from unittest.mock import MagicMock, patch
from src.persona.models import PersonaProfile
from src.persona.analyzer import analyze_first_batch, refine_with_batch

_SAMPLE_POSTS = [
    {
        "post_id": 1,
        "thread_id": 10,
        "thread_title": "Welke spellekes zijde mee bezig",
        "forum_id": 22,
        "forum_name": "Videogames",
        "date": "09-03-2026, 19:04",
        "content": "mewgenics is raar genoeg mijn ding ni, klikt ni. probeer wss nog eens op dood moment",
    },
    {
        "post_id": 2,
        "thread_id": 20,
        "thread_title": "Politiek",
        "forum_id": 9,
        "forum_name": "Zwam",
        "date": "08-03-2026, 10:00",
        "content": "ge zijt echt ne zever man, da klopt van geen kanten",
    },
]

_MOCK_ANALYSIS_RESPONSE = {
    "dialect_markers": ["ge", "ni", "da", "wss"],
    "formality": "very_casual",
    "sentence_length": "short",
    "bbcode_habits": [],
    "punctuation_style": "weinig hoofdletters, geen punt op het einde",
    "topic_weights": {"Videogames": 0.8, "Zwam": 0.6},
    "opinion_fingerprint": ["sceptisch over hype", "direct in taal"],
    "frequent_interactions": {},
    "peak_hours": [18, 19, 20],
    "typical_post_length": "short",
    "daily_cap": 5,
    "hourly_cap": 2,
    "example_posts": [
        "mewgenics is raar genoeg mijn ding ni, klikt ni.",
        "ge zijt echt ne zever man, da klopt van geen kanten",
    ],
    "persona_summary": "Direct en nuchter gamer uit Vlaanderen. Schrijft in dialect, kort en bondig.",
}


def _make_mock_client(response_dict: dict) -> MagicMock:
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(response_dict))]
    mock_client.messages.create.return_value = mock_message
    return mock_client


def test_analyze_first_batch_returns_profile():
    alter = {
        "user_id": 119,
        "original_username": "radje",
        "reversed_username": "ejdar",
        "post_count": 8432,
        "last_active": "2026-03-09",
    }
    mock_client = _make_mock_client(_MOCK_ANALYSIS_RESPONSE)

    profile = analyze_first_batch(mock_client, alter, _SAMPLE_POSTS)

    assert isinstance(profile, PersonaProfile)
    assert profile.user_id == 119
    assert profile.posts_analyzed == 2
    assert profile.pages_loaded == 1
    assert profile.dialect_markers == ["ge", "ni", "da", "wss"]
    assert profile.formality == "very_casual"
    assert profile.daily_cap == 5
    assert len(profile.example_posts) == 2
    assert "Direct" in profile.persona_summary


def test_analyze_first_batch_calls_api_with_posts():
    alter = {
        "user_id": 119,
        "original_username": "radje",
        "reversed_username": "ejdar",
        "post_count": 8432,
        "last_active": "2026-03-09",
    }
    mock_client = _make_mock_client(_MOCK_ANALYSIS_RESPONSE)

    analyze_first_batch(mock_client, alter, _SAMPLE_POSTS)

    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args[1]
    prompt = call_kwargs["messages"][0]["content"]
    assert "radje" in prompt
    assert "mewgenics" in prompt


def test_refine_with_batch_updates_existing_profile():
    alter = {
        "user_id": 119,
        "original_username": "radje",
        "reversed_username": "ejdar",
        "post_count": 8432,
        "last_active": "2026-03-09",
    }
    existing = PersonaProfile.from_alter_ego(alter)
    existing.posts_analyzed = 100
    existing.pages_loaded = 1
    existing.dialect_markers = ["ge", "ni"]

    updated_response = dict(_MOCK_ANALYSIS_RESPONSE)
    updated_response["dialect_markers"] = ["ge", "ni", "da", "wss", "zever"]
    mock_client = _make_mock_client(updated_response)

    updated = refine_with_batch(mock_client, existing, _SAMPLE_POSTS)

    assert updated.posts_analyzed == 102
    assert updated.pages_loaded == 2
    assert "da" in updated.dialect_markers


def test_analyze_handles_malformed_json_gracefully():
    alter = {
        "user_id": 119,
        "original_username": "radje",
        "reversed_username": "ejdar",
        "post_count": 8432,
        "last_active": "2026-03-09",
    }
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="this is not json {{{")]
    mock_client.messages.create.return_value = mock_message

    # Should not raise; returns blank profile from alter
    profile = analyze_first_batch(mock_client, alter, _SAMPLE_POSTS)
    assert profile.user_id == 119
    assert profile.posts_analyzed == 0  # unchanged on failure
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && python -m pytest tests/persona/test_analyzer.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.persona.analyzer'`

- [ ] **Step 3: Implement the analyzer**

Create `src/persona/analyzer.py`:

```python
import json
import re
from src.persona.models import PersonaProfile

_MODEL = "claude-sonnet-4-6"

_SYSTEM = (
    "Je bent een expert in het analyseren van online forum gedrag van Nederlandstalige gebruikers. "
    "Je analyseert berichten en geeft je antwoord altijd als geldig JSON object, zonder uitleg of markdown."
)

_SCHEMA_DESCRIPTION = """{
  "dialect_markers": ["lijst van typische dialect-/spreektaalwoorden die deze gebruiker gebruikt"],
  "formality": "very_casual | casual | formal",
  "sentence_length": "short | medium | long",
  "bbcode_habits": ["quote", "bold", "url", ...],
  "punctuation_style": "korte beschrijving van interpunctie en hoofdlettergebruik",
  "topic_weights": {"forumnaam": gewicht_0_tot_1, ...},
  "opinion_fingerprint": ["typisch standpunt 1", "typisch standpunt 2", ...],
  "frequent_interactions": {"username": "ally | rival | neutral", ...},
  "peak_hours": [18, 19, 20],
  "typical_post_length": "short | medium | long",
  "daily_cap": gemiddeld_posts_per_dag_als_int,
  "hourly_cap": max_posts_per_uur_als_int,
  "example_posts": ["verbatim post 1", "verbatim post 2", ...],
  "persona_summary": "Narratieve beschrijving van de persoonlijkheid in 2-4 zinnen in het Nederlands."
}"""


def _format_posts(posts: list[dict]) -> str:
    lines = []
    for p in posts:
        lines.append(f"[{p['date']} | {p['forum_name']}] {p['content']}")
    return "\n".join(lines)


def _parse_json_response(text: str) -> dict | None:
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def _apply_analysis(profile: PersonaProfile, data: dict) -> None:
    profile.dialect_markers = data.get("dialect_markers", profile.dialect_markers)
    profile.formality = data.get("formality", profile.formality)
    profile.sentence_length = data.get("sentence_length", profile.sentence_length)
    profile.bbcode_habits = data.get("bbcode_habits", profile.bbcode_habits)
    profile.punctuation_style = data.get("punctuation_style", profile.punctuation_style)
    profile.topic_weights = data.get("topic_weights", profile.topic_weights)
    profile.opinion_fingerprint = data.get("opinion_fingerprint", profile.opinion_fingerprint)
    profile.frequent_interactions = data.get("frequent_interactions", profile.frequent_interactions)
    profile.peak_hours = data.get("peak_hours", profile.peak_hours)
    profile.typical_post_length = data.get("typical_post_length", profile.typical_post_length)
    profile.daily_cap = data.get("daily_cap", profile.daily_cap)
    profile.hourly_cap = data.get("hourly_cap", profile.hourly_cap)
    profile.example_posts = data.get("example_posts", profile.example_posts)
    profile.persona_summary = data.get("persona_summary", profile.persona_summary)


def analyze_first_batch(client, alter: dict, posts: list[dict]) -> PersonaProfile:
    profile = PersonaProfile.from_alter_ego(alter)
    posts_text = _format_posts(posts)

    prompt = (
        f"Analyseer de volgende {len(posts)} forumberichten van gebruiker "
        f'"{alter["original_username"]}" (user_id: {alter["user_id"]}).\n\n'
        f"Berichten:\n{posts_text}\n\n"
        f"Geef een JSON object terug met dit schema:\n{_SCHEMA_DESCRIPTION}\n\n"
        f"Kies maximaal 20 representatieve verbatim posts als example_posts. "
        f"Geef enkel het JSON object terug, geen uitleg."
    )

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=2000,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        data = _parse_json_response(response.content[0].text)
        if data:
            _apply_analysis(profile, data)
            profile.posts_analyzed = len(posts)
            profile.pages_loaded = 1
    except Exception:
        pass

    return profile


def refine_with_batch(client, profile: PersonaProfile, posts: list[dict]) -> PersonaProfile:
    posts_text = _format_posts(posts)
    current_json = json.dumps(profile.to_dict(), ensure_ascii=False, indent=2)

    prompt = (
        f"Je hebt een bestaand persona profiel voor gebruiker "
        f'"{profile.original_username}". Je krijgt nu {len(posts)} nieuwe forumberichten.\n\n'
        f"Huidig profiel:\n{current_json}\n\n"
        f"Nieuwe berichten:\n{posts_text}\n\n"
        f"Verfijn het profiel op basis van de nieuwe berichten. "
        f"Geef het volledige bijgewerkte JSON profiel terug met dit schema:\n{_SCHEMA_DESCRIPTION}\n\n"
        f"Vervang example_posts niet volledig — voeg maximaal 5 nieuwe toe als ze representatiever zijn. "
        f"Geef enkel het JSON object terug, geen uitleg."
    )

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=2000,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        data = _parse_json_response(response.content[0].text)
        if data:
            _apply_analysis(profile, data)
            profile.posts_analyzed += len(posts)
            profile.pages_loaded += 1
    except Exception:
        pass

    return profile
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && python -m pytest tests/persona/test_analyzer.py -v
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/persona/analyzer.py tests/persona/test_analyzer.py
git commit -m "feat: add LLM persona analyzer with first-batch and incremental refinement"
```

---

## Task 5: Reply Generator

**Files:**
- Create: `src/persona/generator.py`
- Create: `tests/persona/test_generator.py`

Takes a profile and a test post dict, calls Claude with a persona system prompt + the test post as user message, and returns the generated Dutch reply string.

- [ ] **Step 1: Write the failing tests**

Create `tests/persona/test_generator.py`:

```python
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
    {"id": 1, "label": "Politiek debat", "post": "Wtf, hoe kunnen ze dit gedaan hebben?"},
    {"id": 2, "label": "Gaming hot take", "post": "Is de nieuwe Zelda goed?"},
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && python -m pytest tests/persona/test_generator.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.persona.generator'`

- [ ] **Step 3: Implement the reply generator**

Create `src/persona/generator.py`:

```python
from src.persona.models import PersonaProfile

_MODEL = "claude-sonnet-4-6"


def build_system_prompt(profile: PersonaProfile) -> str:
    examples = "\n".join(f"- {p}" for p in profile.example_posts[:15])
    dialect = ", ".join(profile.dialect_markers) if profile.dialect_markers else "geen specifieke markers"

    return (
        f"Je speelt de rol van '{profile.original_username}', een voormalig lid van een Nederlandstalig "
        f"gamerforum. Je schrijft ALTIJD in het Nederlands, in het specifieke register van deze persoon.\n\n"
        f"Persoonlijkheid: {profile.persona_summary}\n\n"
        f"Schrijfstijl:\n"
        f"- Formaliteit: {profile.formality}\n"
        f"- Zinslengte: {profile.sentence_length}\n"
        f"- Dialect/spreektaal: {dialect}\n"
        f"- Typische berichtlengte: {profile.typical_post_length}\n"
        f"- Interpunctie: {profile.punctuation_style}\n\n"
        f"Voorbeeldberichten van deze persoon:\n{examples}\n\n"
        f"Regels:\n"
        f"- Schrijf ALTIJD in het Nederlands\n"
        f"- Blijf in karakter — geen vierde muur doorbreken\n"
        f"- Verzin geen biografische feiten\n"
        f"- Je mag VBulletin BBCode gebruiken (b, i, quote, url) als het bij de stijl past\n"
        f"- Harde taal en banter zijn acceptabel als het past bij de persoon\n"
        f"- Reageer kort als de persoon kort schrijft, lang als de persoon lang schrijft"
    )


def generate_replies(client, profile: PersonaProfile, test_posts: list[dict]) -> list[dict]:
    system = build_system_prompt(profile)
    results = []

    for test_post in test_posts:
        user_content = (
            f"Iemand heeft het volgende gepost op het forum:\n\n"
            f"\"{test_post['post']}\"\n\n"
            f"Schrijf een reactie zoals {profile.original_username} dat zou doen."
        )
        try:
            response = client.messages.create(
                model=_MODEL,
                max_tokens=400,
                system=system,
                messages=[{"role": "user", "content": user_content}],
            )
            reply = response.content[0].text
        except Exception:
            reply = "[generatie mislukt]"

        results.append({
            "id": test_post["id"],
            "label": test_post["label"],
            "post": test_post["post"],
            "reply": reply,
        })

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && python -m pytest tests/persona/test_generator.py -v
```

Expected: 4 tests PASS

- [ ] **Step 5: Run full test suite**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && python -m pytest -v
```

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/persona/generator.py tests/persona/test_generator.py
git commit -m "feat: add persona reply generator with character system prompt"
```

---

## Task 6: Workbench CLI

**Files:**
- Create: `src/workbench/__init__.py`
- Create: `src/workbench/cli.py`

The workbench is a Rich terminal UI. It loads the 25 approved accounts and for each one runs the loop: load batch → analyze → generate samples → rate samples → save profile. There are no unit tests for this (it's I/O-driven terminal interaction) — it's verified by running it manually.

- [ ] **Step 1: Create the workbench package**

Create `src/workbench/__init__.py` (empty).

- [ ] **Step 2: Create the workbench CLI**

Create `src/workbench/cli.py`:

```python
import json
import os
from pathlib import Path

import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from src.persona.models import PersonaProfile
from src.persona.scraper import PostScraper
from src.persona.analyzer import analyze_first_batch, refine_with_batch
from src.persona.generator import generate_replies

_PERSONAS_DIR = Path("personas")
_TEST_POSTS_PATH = Path("config/test_posts.json")


def _persona_path(username: str) -> Path:
    return _PERSONAS_DIR / f"{username}.json"


def _load_profile(alter: dict) -> PersonaProfile:
    path = _persona_path(alter["original_username"])
    if path.exists():
        return PersonaProfile.from_dict(json.loads(path.read_text(encoding="utf-8")))
    return PersonaProfile.from_alter_ego(alter)


def _save_profile(profile: PersonaProfile) -> None:
    _PERSONAS_DIR.mkdir(exist_ok=True)
    path = _persona_path(profile.original_username)
    path.write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def _load_test_posts() -> list[dict]:
    return json.loads(_TEST_POSTS_PATH.read_text(encoding="utf-8"))


def _show_persona_list(console: Console, alters: list[dict]) -> None:
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=4)
    table.add_column("Username", min_width=18)
    table.add_column("Posts", justify="right")
    table.add_column("Analyzed", justify="right")
    table.add_column("Status", min_width=14)

    for i, alter in enumerate(alters, 1):
        profile = _load_profile(alter)
        status = "[green]✓ approved[/green]" if profile.is_approved else (
            f"[yellow]{profile.posts_analyzed} posts[/yellow]" if profile.posts_analyzed > 0
            else "[dim]not started[/dim]"
        )
        table.add_row(
            str(i),
            alter["original_username"],
            f"{alter['post_count']:,}",
            str(profile.posts_analyzed),
            status,
        )

    approved = sum(1 for a in alters if _load_profile(a).is_approved)
    console.print(Panel(table, title=f"Personas — {approved}/{len(alters)} approved"))


def _rate_samples(console: Console, samples: list[dict]) -> list[dict]:
    rated = []
    for i, sample in enumerate(samples, 1):
        console.print(Panel(
            f"[bold]{sample['label']}[/bold]\n\n"
            f"[dim]Post:[/dim] {sample['post']}\n\n"
            f"[bold cyan]Reply:[/bold cyan] {sample['reply']}",
            title=f"Sample {i}/{len(samples)}",
        ))
        while True:
            choice = console.input("[i] in-character  [x] off-character  [s] skip: ").strip().lower()
            if choice in ("i", "x", "s"):
                break
            console.print("[yellow]Kies i, x of s[/yellow]")
        rated.append({**sample, "rating": choice})
    return rated


def _run_persona_workbench(
    console: Console,
    alter: dict,
    scraper: PostScraper,
    client: anthropic.Anthropic,
    test_posts: list[dict],
) -> None:
    profile = _load_profile(alter)
    username = alter["original_username"]

    console.print(Panel(
        f"[bold]{username}[/bold] (ID {alter['user_id']}, {alter['post_count']:,} posts)\n"
        f"Posts analyzed: {profile.posts_analyzed} | Approved: {profile.is_approved}",
        title="Persona Workbench",
    ))

    if profile.is_approved:
        console.print("[green]Deze persona is al goedgekeurd.[/green]")
        choice = console.input("[r] herwerk  [q] terug: ").strip().lower()
        if choice != "r":
            return
        profile.is_approved = False

    while True:
        is_first_batch = profile.pages_loaded == 0

        if is_first_batch:
            # Initial batch: fetch pages 1 and 2 together (200 posts) for richer first analysis
            console.print(f"\n[bold]Eerste batch laden (pagina 1-2, ~200 posts)...[/bold]")
            try:
                posts1, has_more1 = scraper.fetch_batch(alter["user_id"], page=1)
                posts2, has_more = scraper.fetch_batch(alter["user_id"], page=2) if has_more1 else ([], False)
            except Exception as exc:
                console.print(f"[red]Scrape mislukt: {exc}[/red]")
                return
            posts = posts1 + posts2
        else:
            next_page = profile.pages_loaded + 1
            console.print(f"\n[bold]Volgende batch laden (pagina {next_page}, ~100 posts)...[/bold]")
            try:
                posts, has_more = scraper.fetch_batch(alter["user_id"], page=next_page)
            except Exception as exc:
                console.print(f"[red]Scrape mislukt: {exc}[/red]")
                return

        if not posts:
            console.print("[yellow]Geen posts gevonden op deze pagina.[/yellow]")
            break

        console.print(f"  {len(posts)} posts opgehaald. Analyseren met Claude...")
        if is_first_batch:
            profile = analyze_first_batch(client, alter, posts)
            profile.pages_loaded = 2  # consumed pages 1 and 2
        else:
            profile = refine_with_batch(client, profile, posts)
        _save_profile(profile)
        console.print(f"  Profiel opgeslagen. Totaal geanalyseerd: {profile.posts_analyzed} posts")

        console.print("\n[bold]Voorbeeldreacties genereren...[/bold]")
        samples = generate_replies(client, profile, test_posts)
        rated = _rate_samples(console, samples)

        in_char = sum(1 for r in rated if r["rating"] == "i")
        console.print(f"\n[bold]Resultaat:[/bold] {in_char}/{len(samples)} in-character")

        if not has_more:
            console.print("[dim]Geen verdere pagina's beschikbaar.[/dim]")

        while True:
            options = "[l] volgende batch  [a] goedkeuren  [e] JSON bewerken  [q] terug naar lijst"
            if not has_more:
                options = "[a] goedkeuren  [e] JSON bewerken  [q] terug naar lijst"
            choice = console.input(f"\n{options}: ").strip().lower()

            if choice == "l" and has_more:
                break
            elif choice == "a":
                profile.is_approved = True
                _save_profile(profile)
                console.print(f"[green]✓ {username} goedgekeurd![/green]")
                return
            elif choice == "e":
                path = _persona_path(username)
                console.print(f"[dim]Bewerk: {path.resolve()}[/dim]")
                console.input("Druk Enter als klaar...")
                profile = PersonaProfile.from_dict(json.loads(path.read_text(encoding="utf-8")))
            elif choice == "q":
                return
            else:
                console.print("[yellow]Ongeldige keuze[/yellow]")


def run_workbench(
    alters: list[dict],
    scraper: PostScraper,
    client: anthropic.Anthropic,
) -> None:
    console = Console()
    test_posts = _load_test_posts()

    while True:
        console.clear()
        _show_persona_list(console, alters)

        choice = console.input("\nSelecteer persona [1-25] of q om te stoppen: ").strip().lower()
        if choice == "q":
            break
        try:
            idx = int(choice) - 1
            if not (0 <= idx < len(alters)):
                raise ValueError
        except ValueError:
            console.print("[yellow]Ongeldige keuze[/yellow]")
            console.input("Enter om door te gaan...")
            continue

        _run_persona_workbench(console, alters[idx], scraper, client, test_posts)
        console.input("\nEnter om terug te gaan naar de lijst...")

    approved = sum(1 for a in alters if _load_profile(a).is_approved)
    console.print(f"\n[bold]Klaar. {approved}/{len(alters)} personas goedgekeurd.[/bold]")
```

- [ ] **Step 3: Verify it imports cleanly**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && python -c "from src.workbench.cli import run_workbench; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/workbench/__init__.py src/workbench/cli.py
git commit -m "feat: add persona workbench CLI with load-analyze-rate loop"
```

---

## Task 7: Entry Point + Personas Gitignore

**Files:**
- Create: `workbench.py`
- Modify: `.gitignore`

- [ ] **Step 1: Update .gitignore to exclude persona files**

Edit `.gitignore` — add the personas output directory:

```
# Persona profiles (contain scraped post data)
personas/
```

- [ ] **Step 2: Create the entry point**

Create `workbench.py`:

```python
import json
import os
from pathlib import Path
from dotenv import load_dotenv
import anthropic
from rich.console import Console

from src.session import VBulletinSession
from src.persona.scraper import PostScraper
from src.workbench.cli import run_workbench

load_dotenv()

_APPROVED_ACCOUNTS = Path("config/approved_accounts.json")

def main() -> None:
    console = Console()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]ANTHROPIC_API_KEY ontbreekt in .env[/red]")
        return

    username = os.getenv("FORUM_USERNAME")
    password = os.getenv("FORUM_PASSWORD")
    search_delay = int(os.getenv("SEARCH_DELAY", "6"))

    alters = json.loads(_APPROVED_ACCOUNTS.read_text(encoding="utf-8"))
    console.print(f"[bold]{len(alters)} alter egos geladen.[/bold]")

    console.print("[bold]Inloggen op forum...[/bold]")
    session = VBulletinSession()
    if not session.login(username, password):
        console.print("[red]Login mislukt. Controleer credentials in .env[/red]")
        return
    console.print("[green]Ingelogd.[/green]")

    scraper = PostScraper(session, delay=search_delay)
    client = anthropic.Anthropic(api_key=api_key)

    run_workbench(alters, scraper, client)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify the entry point imports and runs to the login step**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && python -c "
import workbench
print('imports OK')
"
```

Expected: `imports OK`

- [ ] **Step 4: Run the full test suite one final time**

```bash
cd /home/bavobbr/dev/shrimp-resurrect && python -m pytest -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add workbench.py .gitignore
git commit -m "feat: add workbench.py entry point and gitignore for personas output"
```

---

## Running the Workbench

After completing all tasks:

```bash
# Add your Anthropic API key to .env:
# ANTHROPIC_API_KEY=sk-ant-...

python workbench.py
```

The workbench will:
1. Login to the forum as wokebot
2. Show the list of 25 alter egos with approval status
3. For each selected persona: scrape 200 posts (pages 1+2) for first analysis; then 100 posts per subsequent batch → show sample replies → rate them
4. Repeat until you're happy, then approve
5. Save each approved profile to `personas/{username}.json`

Each `personas/{username}.json` feeds directly into Plan 3 (Event Orchestrator).

---

## Self-Review Checklist

**Spec coverage:**
- ✅ Paginated post scraper (100 posts/page); first batch fetches pages 1+2 = 200 posts; subsequent batches = 100 posts each
- ✅ PersonaProfile model (all fields from spec: style, topics, opinions, relationships, activity, rate limits, examples)
- ✅ LLM analysis — first batch from scratch, incremental refinement
- ✅ Test post set (5 diverse Dutch prompts, fixed across all personas)
- ✅ Sample reply generation using persona system prompt
- ✅ Interactive workbench: load → analyze → rate → approve loop
- ✅ Human edit hook (option e to edit JSON before continuing)
- ✅ Profiles saved to `personas/{username}.json`
- ✅ Entry point `workbench.py` with forum login

**Type consistency:** PersonaProfile.from_dict / to_dict round-trip tested. Analyzer uses `profile.to_dict()` for current-profile context in prompt — consistent with from_dict in refine_with_batch. PostScraper.fetch_batch returns `tuple[list[dict], bool]` — used correctly in workbench CLI.

**Placeholder scan:** No TBDs, no "implement later", all code steps are complete.
