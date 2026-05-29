# Gemini LLM Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Anthropic SDK with Google Gemini (`gemini-3.5-flash`) by creating a thin `src/llm.py` helper and updating all call sites.

**Architecture:** A new `src/llm.py` owns all Gemini SDK details (client, model name, config). Three domain modules (`analyzer.py`, `persona/generator.py`, `event/generator.py`) drop their `client` parameter and call `call_llm` / `call_llm_raw` directly. Entry points (`event.py`, `workbench.py`) stop constructing a client.

**Tech Stack:** `google-genai` (replaces `anthropic`), Python 3.11+, pytest

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `src/llm.py` | **create** | Gemini client init, `call_llm()`, `call_llm_raw()` |
| `tests/test_llm.py` | **create** | Unit tests for `src/llm.py` |
| `src/persona/analyzer.py` | **modify** | Drop `client` param, use `call_llm` |
| `tests/persona/test_analyzer.py` | **modify** | Patch `src.llm.call_llm` instead of mock_client |
| `src/persona/generator.py` | **modify** | Drop `client` param, use `call_llm_raw` |
| `tests/persona/test_generator.py` | **modify** | Patch `src.llm.call_llm_raw` instead of mock_client |
| `src/event/generator.py` | **modify** | Drop `client` param, use `call_llm_raw` |
| `tests/event/test_generator.py` | **modify** | Patch `src.llm.call_llm_raw` instead of mock_client |
| `src/workbench/cli.py` | **modify** | Drop `client` param from functions |
| `src/event/webui.py` | **modify** | Drop `client` param from `create_app` |
| `event.py` | **modify** | Drop Anthropic import + client construction |
| `workbench.py` | **modify** | Drop Anthropic import + client construction |
| `tests/event/test_webui.py` | **modify** | Remove `client = MagicMock()` from fixture |
| `requirements.txt` | **modify** | Add `google-genai`, remove `anthropic` |
| `.env.example` | **modify** | `ANTHROPIC_API_KEY` → `GOOGLE_API_KEY` |

---

## Task 1: Add google-genai to dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add google-genai to requirements.txt**

Replace `anthropic==0.104.1` with `google-genai` (keep everything else unchanged):

```
requests==2.32.3
beautifulsoup4==4.12.3
rich==13.7.1
python-dotenv==1.0.1
google-genai
freezegun==1.5.1
pytest==8.2.2
pytest-cov==5.0.0
flask==3.1.0
```

- [ ] **Step 2: Install the new dependency**

Run: `pip install google-genai`

Expected: Package installs without error. Verify with `python -c "from google import genai; print('ok')"`.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "deps: replace anthropic with google-genai"
```

---

## Task 2: Create `src/llm.py` + tests

**Files:**
- Create: `src/llm.py`
- Create: `tests/test_llm.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_llm.py`:

```python
from unittest.mock import MagicMock, patch
import src.llm as llm_module


def test_call_llm_returns_response_text():
    mock_resp = MagicMock()
    mock_resp.text = "het antwoord"
    with patch.object(llm_module, "_client") as mock_client:
        mock_client.models.generate_content.return_value = mock_resp
        result = llm_module.call_llm("systeem", "gebruiker", 200)
    assert result == "het antwoord"


def test_call_llm_passes_model_and_contents():
    mock_resp = MagicMock()
    mock_resp.text = "antwoord"
    with patch.object(llm_module, "_client") as mock_client:
        mock_client.models.generate_content.return_value = mock_resp
        llm_module.call_llm("mijn systeem", "mijn vraag", 400)
    call_kwargs = mock_client.models.generate_content.call_args[1]
    assert call_kwargs["model"] == "gemini-3.5-flash"
    assert call_kwargs["contents"] == ["mijn vraag"]


def test_call_llm_raw_returns_response_object():
    mock_resp = MagicMock()
    mock_resp.text = "antwoord"
    with patch.object(llm_module, "_client") as mock_client:
        mock_client.models.generate_content.return_value = mock_resp
        resp = llm_module.call_llm_raw("systeem", "vraag", 400)
    assert resp is mock_resp


def test_call_llm_raw_passes_max_output_tokens():
    mock_resp = MagicMock()
    mock_resp.text = "x"
    with patch.object(llm_module, "_client") as mock_client:
        mock_client.models.generate_content.return_value = mock_resp
        llm_module.call_llm_raw("s", "u", 777)
    call_kwargs = mock_client.models.generate_content.call_args[1]
    assert call_kwargs["config"].max_output_tokens == 777
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm.py -v`

Expected: FAIL with `ModuleNotFoundError` or `ImportError` (module doesn't exist yet).

- [ ] **Step 3: Create `src/llm.py`**

```python
import os
from google import genai
from google.genai import types

_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY", ""))
_MODEL = "gemini-3.5-flash"


def call_llm(system: str, user: str, max_tokens: int) -> str:
    resp = _client.models.generate_content(
        model=_MODEL,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
        ),
        contents=[user],
    )
    return resp.text


def call_llm_raw(system: str, user: str, max_tokens: int):
    return _client.models.generate_content(
        model=_MODEL,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
        ),
        contents=[user],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_llm.py -v`

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llm.py tests/test_llm.py
git commit -m "feat: add src/llm.py with call_llm and call_llm_raw for Gemini"
```

---

## Task 3: Refactor `src/persona/analyzer.py`

**Files:**
- Modify: `src/persona/analyzer.py`
- Modify: `tests/persona/test_analyzer.py`

- [ ] **Step 1: Update the tests first**

Replace the entire `tests/persona/test_analyzer.py` with:

```python
import json
from unittest.mock import patch
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

_ALTER = {
    "user_id": 119,
    "original_username": "radje",
    "reversed_username": "ejdar",
    "post_count": 8432,
    "last_active": "2026-03-09",
}


def test_analyze_first_batch_returns_profile():
    with patch("src.llm.call_llm", return_value=json.dumps(_MOCK_ANALYSIS_RESPONSE)):
        profile = analyze_first_batch(_ALTER, _SAMPLE_POSTS)
    assert isinstance(profile, PersonaProfile)
    assert profile.user_id == 119
    assert profile.posts_analyzed == 2
    assert profile.pages_loaded == 0
    assert profile.dialect_markers == ["ge", "ni", "da", "wss"]
    assert profile.formality == "very_casual"
    assert profile.daily_cap == 5
    assert len(profile.example_posts) == 2
    assert "Direct" in profile.persona_summary


def test_analyze_first_batch_calls_api_with_posts():
    with patch("src.llm.call_llm", return_value=json.dumps(_MOCK_ANALYSIS_RESPONSE)) as mock_llm:
        analyze_first_batch(_ALTER, _SAMPLE_POSTS)
    mock_llm.assert_called_once()
    _system, user_prompt, _max = mock_llm.call_args[0]
    assert "radje" in user_prompt
    assert "mewgenics" in user_prompt


def test_refine_with_batch_updates_existing_profile():
    existing = PersonaProfile.from_alter_ego(_ALTER)
    existing.posts_analyzed = 100
    existing.pages_loaded = 1
    existing.dialect_markers = ["ge", "ni"]
    updated_response = dict(_MOCK_ANALYSIS_RESPONSE)
    updated_response["dialect_markers"] = ["ge", "ni", "da", "wss", "zever"]
    with patch("src.llm.call_llm", return_value=json.dumps(updated_response)):
        updated = refine_with_batch(existing, _SAMPLE_POSTS)
    assert updated.posts_analyzed == 102
    assert updated.pages_loaded == 2
    assert "da" in updated.dialect_markers


def test_analyze_handles_malformed_json_gracefully():
    with patch("src.llm.call_llm", return_value="this is not json {{{"):
        profile = analyze_first_batch(_ALTER, _SAMPLE_POSTS)
    assert profile.user_id == 119
    assert profile.posts_analyzed == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/persona/test_analyzer.py -v`

Expected: FAIL — `analyze_first_batch` still takes `client` as first arg, call signatures don't match.

- [ ] **Step 3: Update `src/persona/analyzer.py`**

Replace the file content:

```python
import json
import re
from src.llm import call_llm
from src.persona.models import PersonaProfile

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
        quoted = p.get("quoted_users", [])
        if quoted:
            note = f" [bevat citaat van: {', '.join(quoted)}]"
        else:
            note = ""
        lines.append(f"[{p['date']} | {p['forum_name']} | {p['thread_title']}]{note} {p['content']}")
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


def analyze_first_batch(alter: dict, posts: list[dict]) -> PersonaProfile:
    profile = PersonaProfile.from_alter_ego(alter)
    posts_text = _format_posts(posts)

    prompt = (
        f"Analyseer de volgende {len(posts)} forumberichten van gebruiker "
        f'"{alter["original_username"]}" (user_id: {alter["user_id"]}, totaal {alter["post_count"]} posts op het forum).\n\n'
        f"Berichten:\n{posts_text}\n\n"
        f"Geef een JSON object terug met dit schema:\n{_SCHEMA_DESCRIPTION}\n\n"
        f"Kies maximaal 20 representatieve verbatim posts als example_posts. "
        f"Beperk opinion_fingerprint tot maximaal 15 items. "
        f"Geef enkel het JSON object terug, geen uitleg."
    )

    text = call_llm(_SYSTEM, prompt, 3000)
    data = _parse_json_response(text)

    if data:
        _apply_analysis(profile, data)
        profile.posts_analyzed = len(posts)

    return profile


def refine_with_batch(profile: PersonaProfile, posts: list[dict]) -> PersonaProfile:
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
        f"Behoud bestaande opinion_fingerprint vermeldingen tenzij de nieuwe berichten ze expliciet tegenspreken — voeg nieuwe standpunten toe, maximaal 15 in totaal. "
        f"Geef enkel het JSON object terug, geen uitleg."
    )

    text = call_llm(_SYSTEM, prompt, 3000)
    data = _parse_json_response(text)

    if data:
        _apply_analysis(profile, data)
        profile.posts_analyzed += len(posts)
        profile.pages_loaded += 1

    return profile
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/persona/test_analyzer.py -v`

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/persona/analyzer.py tests/persona/test_analyzer.py
git commit -m "refactor: analyzer.py uses call_llm, drops client param"
```

---

## Task 4: Refactor `src/persona/generator.py`

**Files:**
- Modify: `src/persona/generator.py`
- Modify: `tests/persona/test_generator.py`

- [ ] **Step 1: Update the tests first**

Replace the entire `tests/persona/test_generator.py` with:

```python
from unittest.mock import MagicMock, patch
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
    {"id": 1, "label": "Politiek debat", "forum": "Zwam", "thread_title": "Politiek algemeen", "post": "Wtf, hoe kunnen ze dit gedaan hebben?"},
    {"id": 2, "label": "Gaming hot take", "forum": "Videogames", "thread_title": "Welke spellekes zijde mee bezig", "post": "Is de nieuwe Zelda goed?"},
]


def _make_mock_resp(text="Typische radje reply", finish_reason="STOP"):
    resp = MagicMock()
    resp.text = text
    resp.candidates[0].finish_reason.name = finish_reason
    return resp


def test_generate_replies_returns_one_per_test_post():
    with patch("src.llm.call_llm_raw", return_value=_make_mock_resp()) as mock_raw:
        results = generate_replies(_make_profile(), _TEST_POSTS)
    assert len(results) == 2
    assert mock_raw.call_count == 2


def test_generate_replies_result_structure():
    with patch("src.llm.call_llm_raw", return_value=_make_mock_resp("Da weet ik nie hoor")):
        results = generate_replies(_make_profile(), _TEST_POSTS)
    for r in results:
        assert "label" in r
        assert "post" in r
        assert "reply" in r
        assert "id" in r
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
    with patch("src.llm.call_llm_raw", return_value=_make_mock_resp()) as mock_raw:
        generate_replies(_make_profile(), _TEST_POSTS[:1])
    _system, user_content, _max = mock_raw.call_args[0]
    assert "Wtf, hoe kunnen ze dit gedaan hebben?" in user_content
    assert "Zwam" in user_content
    assert "Politiek algemeen" in user_content


def test_generate_replies_appends_afgekapt_on_max_tokens():
    with patch("src.llm.call_llm_raw", return_value=_make_mock_resp("Lang antwoord", "MAX_TOKENS")):
        results = generate_replies(_make_profile(), _TEST_POSTS[:1])
    assert results[0]["reply"] == "Lang antwoord [afgekapt]"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/persona/test_generator.py -v`

Expected: FAIL — `generate_replies` still takes `client` as first arg.

- [ ] **Step 3: Update `src/persona/generator.py`**

Replace the file content:

```python
import logging
from src.llm import call_llm_raw
from src.persona.models import PersonaProfile


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


def generate_replies(profile: PersonaProfile, test_posts: list[dict]) -> list[dict]:
    system = build_system_prompt(profile)
    results = []

    for test_post in test_posts:
        user_content = (
            f"Forum: {test_post['forum']} | Thread: {test_post['thread_title']}\n\n"
            f"Iemand heeft het volgende gepost:\n\n"
            f"\"{test_post['post']}\"\n\n"
            f"Schrijf een reactie zoals {profile.original_username} dat zou doen."
        )
        try:
            resp = call_llm_raw(system, user_content, 400)
            reply = resp.text
            if resp.candidates[0].finish_reason.name == "MAX_TOKENS":
                reply += " [afgekapt]"
        except Exception as exc:
            logging.warning("generate_replies failed for post %r: %s", test_post.get("id"), exc)
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

Run: `pytest tests/persona/test_generator.py -v`

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/persona/generator.py tests/persona/test_generator.py
git commit -m "refactor: persona/generator.py uses call_llm_raw, drops client param"
```

---

## Task 5: Refactor `src/event/generator.py`

**Files:**
- Modify: `src/event/generator.py`
- Modify: `tests/event/test_generator.py`

- [ ] **Step 1: Update the tests first**

Replace the entire `tests/event/test_generator.py` with:

```python
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
    with patch("src.llm.call_llm_raw", return_value=_make_mock_resp()) as mock_raw:
        result = generate_reply(_make_profile(), _TRIGGERING, _CONTEXT)
    assert result == "Da valt mee"
    mock_raw.assert_called_once()


def test_generate_reply_includes_context_in_prompt():
    with patch("src.llm.call_llm_raw", return_value=_make_mock_resp()) as mock_raw:
        generate_reply(_make_profile(), _TRIGGERING, _CONTEXT)
    _system, user_msg, _max = mock_raw.call_args[0]
    assert "Alice" in user_msg
    assert "Wie speelt er nog Zelda?" in user_msg
    assert "Carol" in user_msg
    assert "Is het goed?" in user_msg


def test_generate_reply_prompt_uses_reversed_username():
    with patch("src.llm.call_llm_raw", return_value=_make_mock_resp()) as mock_raw:
        generate_reply(_make_profile(), _TRIGGERING, _CONTEXT)
    _system, user_msg, _max = mock_raw.call_args[0]
    assert "ejdar" in user_msg


def test_generate_reply_appends_afgekapt_on_max_tokens():
    with patch("src.llm.call_llm_raw", return_value=_make_mock_resp("Lang antwoord", "MAX_TOKENS")):
        result = generate_reply(_make_profile(), _TRIGGERING, _CONTEXT)
    assert result == "Lang antwoord [afgekapt]"


def test_generate_reply_raises_on_api_error():
    with patch("src.llm.call_llm_raw", side_effect=RuntimeError("API down")):
        with pytest.raises(RuntimeError):
            generate_reply(_make_profile(), _TRIGGERING, _CONTEXT)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/event/test_generator.py -v`

Expected: FAIL — `generate_reply` still takes `client` as first arg.

- [ ] **Step 3: Update `src/event/generator.py`**

Replace the file content:

```python
import logging
from src.llm import call_llm_raw
from src.persona.models import PersonaProfile
from src.persona.generator import build_system_prompt


def generate_reply(
    profile: PersonaProfile,
    triggering_post: dict,
    context_posts: list[dict],
) -> str:
    """Generate a reply to triggering_post using context_posts as thread context."""
    system = build_system_prompt(profile)

    context_lines = "\n".join(
        f"{p['author']}: {p['content']}"
        for p in context_posts
        if p["post_id"] != triggering_post["post_id"]
    )

    user_content = (
        f"[Vorige berichten in de thread:]\n{context_lines}\n\n"
        f"[Nieuw bericht van {triggering_post['author']}:]\n"
        f"\"{triggering_post['content']}\"\n\n"
        f"Schrijf een reactie zoals {profile.reversed_username} dat zou doen."
    )

    resp = call_llm_raw(system, user_content, 400)
    reply = resp.text
    if resp.candidates[0].finish_reason.name == "MAX_TOKENS":
        reply += " [afgekapt]"
    return reply
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/event/test_generator.py -v`

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/event/generator.py tests/event/test_generator.py
git commit -m "refactor: event/generator.py uses call_llm_raw, drops client param"
```

---

## Task 6: Update wire-up (cli.py, webui.py, event.py, workbench.py)

**Files:**
- Modify: `src/workbench/cli.py`
- Modify: `src/event/webui.py`
- Modify: `event.py`
- Modify: `workbench.py`
- Modify: `tests/event/test_webui.py`

These files pass `client` through to domain modules that no longer accept it. No new tests needed — existing tests just need the `client` arg removed from `create_app`.

- [ ] **Step 1: Update `tests/event/test_webui.py`**

The `app` fixture passes `client = MagicMock()` to `create_app`. Remove it.

Replace the fixture (lines 19–27) with:

```python
@pytest.fixture
def app():
    conn = init_db(":memory:")
    profiles = [_make_profile()]
    flask_app = create_app(conn, profiles, "testpass", live_mode=False)
    flask_app.config["TESTING"] = True
    yield flask_app, conn
    conn.close()
```

Also remove the `from unittest.mock import MagicMock` import since it's no longer used.

- [ ] **Step 2: Run the webui tests to verify they currently pass (baseline)**

Run: `pytest tests/event/test_webui.py -v`

Expected: Some tests FAIL because `create_app` still takes `client` but the fixture no longer passes it. That's correct — we'll fix `create_app` next.

- [ ] **Step 3: Update `src/event/webui.py`**

Change line 113: `def create_app(conn, client, profiles, alter_password: str, live_mode: bool) -> Flask:`
→ `def create_app(conn, profiles, alter_password: str, live_mode: bool) -> Flask:`

Change line 166: `new_text = event_generator.generate_reply(client, profile, triggering, context)`
→ `new_text = event_generator.generate_reply(profile, triggering, context)`

Full updated file:

```python
import logging
import os
import random
import time
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template_string

from src.event import db
from src.event import thread_scraper
from src.event import generator as event_generator
from src.event import poster
from src.session import VBulletinSession

_QUEUE_TEMPLATE = """<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="utf-8">
<title>Shrimp Resurrect — Review Queue</title>
<style>
  body { font-family: monospace; max-width: 900px; margin: 40px auto; padding: 0 20px; background: #1a1a1a; color: #ccc; }
  h1 { color: #fff; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 0.8em; }
  .badge-live { background: #c0392b; color: #fff; }
  .badge-sim  { background: #2980b9; color: #fff; }
  .card { border: 1px solid #444; margin: 16px 0; padding: 16px; background: #252525; }
  .card h3 { margin: 0 0 8px; color: #fff; }
  .post-excerpt { background: #333; padding: 8px; margin: 8px 0; color: #aaa; }
  .generated-text { background: #1e3a1e; padding: 8px; margin: 8px 0; color: #9f9; white-space: pre-wrap; }
  .actions { margin-top: 10px; }
  button { margin-right: 8px; padding: 6px 14px; cursor: pointer; }
  textarea { width: 100%; height: 80px; background: #333; color: #ccc; border: 1px solid #555; padding: 6px; }
  .edit-area { display: none; margin-top: 8px; }
  .empty { color: #888; padding: 20px; text-align: center; }
</style>
</head>
<body>
<h1>Shrimp Resurrect
  <span class="badge {% if live_mode %}badge-live{% else %}badge-sim{% endif %}">
    {% if live_mode %}LIVE{% else %}SIMULATIE{% endif %}
  </span>
</h1>
<p><a href="/status" style="color:#888">status JSON</a></p>
{% if not replies %}
  <p class="empty">Geen wachtende reacties.</p>
{% endif %}
{% for r in replies %}
<div class="card">
  <h3>
    <a href="{{ forum_url }}/showthread.php?t={{ r['thread_id'] }}" target="_blank" style="color:#fff">
      Thread #{{ r['thread_id'] }}
    </a>
    &nbsp;&mdash;&nbsp;<strong>{{ r['alter_username'] }}</strong>
    {% if r['auto_approve_at'] %}<small style="color:#888">(auto: {{ r['auto_approve_at'][:16] }})</small>{% endif %}
  </h3>
  <div class="post-excerpt">post #{{ r['post_id'] }}</div>
  <div class="generated-text">{{ r['reply_text'] }}</div>
  <div class="actions">
    <form method="post" action="/reply/{{ r['id'] }}/approve" style="display:inline">
      <button type="submit" style="background:#27ae60;color:#fff">✓ Goedkeuren</button>
    </form>
    <button onclick="toggleEdit({{ r['id'] }})" style="background:#2980b9;color:#fff">✎ Bewerken</button>
    <form method="post" action="/reply/{{ r['id'] }}/discard" style="display:inline">
      <button type="submit" style="background:#c0392b;color:#fff">✗ Verwijderen</button>
    </form>
    <form method="post" action="/reply/{{ r['id'] }}/regenerate" style="display:inline">
      <button type="submit" style="background:#8e44ad;color:#fff">↺ Opnieuw genereren</button>
    </form>
  </div>
  <div class="edit-area" id="edit-{{ r['id'] }}">
    <form method="post" action="/reply/{{ r['id'] }}/edit">
      <textarea name="reply_text">{{ r['reply_text'] }}</textarea>
      <button type="submit" style="background:#27ae60;color:#fff;margin-top:6px">Opslaan &amp; Goedkeuren</button>
    </form>
  </div>
</div>
{% endfor %}
<script>
function toggleEdit(id) {
  var el = document.getElementById('edit-' + id);
  el.style.display = el.style.display === 'none' || el.style.display === '' ? 'block' : 'none';
}
</script>
</body>
</html>"""


def _do_approve(conn, entry: dict, alter_password: str, live_mode: bool) -> bool:
    if live_mode:
        success = poster.post_reply(
            entry["alter_username"], alter_password,
            entry["thread_id"], entry["reply_text"],
        )
        status = "approved" if success else "failed"
    else:
        success = True
        status = "approved"

    db.update_status(conn, entry["id"], status)

    if success:
        db.insert_posted(
            conn, entry["alter_username"], entry["thread_id"],
            entry["post_id"], entry["reply_text"], simulated=not live_mode,
        )
        if live_mode:
            now = datetime.now(timezone.utc)
            db.increment_rate(conn, entry["alter_username"],
                              now.strftime("%Y-%m-%dT%H"), now.strftime("%Y-%m-%d"))
            time.sleep(random.uniform(60, 180))
    return success


def create_app(conn, profiles, alter_password: str, live_mode: bool) -> Flask:
    app = Flask(__name__)
    profile_map = {p.reversed_username: p for p in profiles}
    forum_url = os.getenv("FORUM_URL", "https://your-forum.example.com")

    @app.route("/")
    def index():
        pending = [dict(r) for r in db.get_pending(conn)]
        return render_template_string(
            _QUEUE_TEMPLATE, replies=pending, live_mode=live_mode, forum_url=forum_url
        )

    @app.route("/reply/<int:reply_id>/approve", methods=["POST"])
    def approve(reply_id):
        entry = db.get_pending_by_id(conn, reply_id)
        if not entry or entry["status"] != "pending":
            return "Not found", 404
        _do_approve(conn, dict(entry), alter_password, live_mode)
        return "", 204

    @app.route("/reply/<int:reply_id>/discard", methods=["POST"])
    def discard(reply_id):
        db.update_status(conn, reply_id, "discarded")
        return "", 204

    @app.route("/reply/<int:reply_id>/edit", methods=["POST"])
    def edit(reply_id):
        new_text = request.form.get("reply_text", "").strip()
        if not new_text:
            return "reply_text required", 400
        db.update_reply_text(conn, reply_id, new_text)
        entry = db.get_pending_by_id(conn, reply_id)
        if not entry or entry["status"] != "pending":
            return "Not found", 404
        _do_approve(conn, dict(entry), alter_password, live_mode)
        return "", 204

    @app.route("/reply/<int:reply_id>/regenerate", methods=["POST"])
    def regenerate(reply_id):
        entry = db.get_pending_by_id(conn, reply_id)
        if not entry:
            return "Not found", 404
        profile = profile_map.get(entry["alter_username"])
        if not profile:
            return "Profile not found", 404
        try:
            scanner = VBulletinSession()
            scanner.login(os.getenv("FORUM_USERNAME", ""), os.getenv("FORUM_PASSWORD", ""))
            context = thread_scraper.fetch_thread_context(scanner, entry["post_id"])
            triggering = next(
                (p for p in context if p["post_id"] == entry["post_id"]),
                {"post_id": entry["post_id"], "author": "?", "content": ""},
            )
            new_text = event_generator.generate_reply(profile, triggering, context)
            db.update_reply_text(conn, reply_id, new_text)
        except Exception as exc:
            logging.warning("Regenerate failed for reply %d: %s", reply_id, exc)
            return "Generation failed", 500
        return "", 204

    @app.route("/status")
    def status():
        day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return jsonify({
            "live_mode": live_mode,
            "pending_count": len(db.get_pending(conn)),
            "posts_today": db.get_daily_posts_summary(conn, day_key),
        })

    return app
```

- [ ] **Step 4: Run webui tests to verify they pass**

Run: `pytest tests/event/test_webui.py -v`

Expected: 4 tests PASS.

- [ ] **Step 5: Update `src/workbench/cli.py`**

Replace the file content (drop `import anthropic`, drop `client` from function signatures and calls):

```python
import json
import re
from pathlib import Path

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
    safe = re.sub(r'[^\w\-]', '_', username)
    return _PERSONAS_DIR / f"{safe}.json"


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

    approved = 0
    for i, alter in enumerate(alters, 1):
        profile = _load_profile(alter)
        if profile.is_approved:
            approved += 1
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

        console.print(f"  {len(posts)} posts opgehaald. Analyseren met Gemini...")
        if is_first_batch:
            profile = analyze_first_batch(alter, posts)
            profile.pages_loaded = 2
        else:
            profile = refine_with_batch(profile, posts)
        _save_profile(profile)
        console.print(f"  Profiel opgeslagen. Totaal geanalyseerd: {profile.posts_analyzed} posts")

        console.print("\n[bold]Voorbeeldreacties genereren...[/bold]")
        samples = generate_replies(profile, test_posts)
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
                try:
                    profile = PersonaProfile.from_dict(json.loads(path.read_text(encoding="utf-8")))
                except (json.JSONDecodeError, KeyError) as exc:
                    console.print(f"[red]Ongeldig JSON — profiel niet herladen: {exc}[/red]")
            elif choice == "q":
                return
            else:
                console.print("[yellow]Ongeldige keuze[/yellow]")


def run_workbench(
    alters: list[dict],
    scraper: PostScraper,
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

        _run_persona_workbench(console, alters[idx], scraper, test_posts)
        console.input("\nEnter om terug te gaan naar de lijst...")

    approved = sum(1 for a in alters if _load_profile(a).is_approved)
    console.print(f"\n[bold]Klaar. {approved}/{len(alters)} personas goedgekeurd.[/bold]")
```

- [ ] **Step 6: Update `workbench.py`**

Replace the file content:

```python
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console

from src.session import VBulletinSession
from src.persona.scraper import PostScraper
from src.workbench.cli import run_workbench

load_dotenv()

_APPROVED_ACCOUNTS = Path("config/approved_accounts.json")

def main() -> None:
    console = Console()

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        console.print("[red]GOOGLE_API_KEY ontbreekt in .env[/red]")
        return

    username = os.getenv("FORUM_USERNAME")
    password = os.getenv("FORUM_PASSWORD")
    search_delay = int(os.getenv("SEARCH_DELAY", "6"))

    if not username or not password:
        console.print("[red]FORUM_USERNAME of FORUM_PASSWORD ontbreekt in .env[/red]")
        return

    try:
        alters = json.loads(_APPROVED_ACCOUNTS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        console.print(f"[red]Bestand niet gevonden: {_APPROVED_ACCOUNTS}[/red]")
        return
    except json.JSONDecodeError as exc:
        console.print(f"[red]Ongeldig JSON in {_APPROVED_ACCOUNTS}: {exc}[/red]")
        return
    console.print(f"[bold]{len(alters)} alter egos geladen.[/bold]")

    console.print("[bold]Inloggen op forum...[/bold]")
    session = VBulletinSession()
    if not session.login(username, password):
        console.print("[red]Login mislukt. Controleer credentials in .env[/red]")
        return
    console.print("[green]Ingelogd.[/green]")

    scraper = PostScraper(session, delay=search_delay)
    run_workbench(alters, scraper)


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Update `event.py`**

Replace the file content:

```python
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv

from src.event import db, gates, thread_scraper
from src.event import generator as event_generator
from src.event.poller import fetch_new_posts, parse_post_date
from src.event.webui import create_app, _do_approve
from src.persona.models import PersonaProfile
from src.session import VBulletinSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
load_dotenv()


def _load_profiles(personas_dir: str) -> list[PersonaProfile]:
    profiles = []
    for path in Path(personas_dir).glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            profile = PersonaProfile.from_dict(data)
            if profile.is_approved:
                profiles.append(profile)
        except Exception as exc:
            logging.warning("Could not load %s: %s", path, exc)
    return profiles


def _is_image_only(content: str) -> bool:
    return not content.replace("[afbeelding]", "").strip()


def _poll_once(scanner, profiles, conn, alter_password, live_mode, cutoff):
    try:
        new_posts = fetch_new_posts(scanner)
    except Exception as exc:
        logging.error("Poll failed: %s", exc)
        return

    for post in new_posts:
        if db.is_seen(conn, post["post_id"]):
            continue

        post_dt = parse_post_date(post.get("date", ""))
        if post_dt and post_dt < cutoff:
            db.mark_seen(conn, post["post_id"], post["thread_id"], post["forum_id"])
            continue

        respondents = gates.evaluate_post(post, profiles, conn)

        for profile in respondents:
            if _is_image_only(post.get("content", "")):
                continue

            try:
                context = thread_scraper.fetch_thread_context(scanner, post["post_id"])
            except Exception as exc:
                logging.warning("Context fetch failed for post %d: %s", post["post_id"], exc)
                context = []

            triggering = next(
                (p for p in context if p["post_id"] == post["post_id"]),
                {"post_id": post["post_id"], "author": "?", "content": post.get("content", "")},
            )

            try:
                reply_text = event_generator.generate_reply(profile, triggering, context)
            except Exception as exc:
                logging.warning("Generation failed for post %d / %s: %s",
                                post["post_id"], profile.reversed_username, exc)
                continue

            auto_approve_at = None
            if profile.auto_approve_minutes is not None:
                auto_approve_at = (
                    datetime.now(timezone.utc) + timedelta(minutes=profile.auto_approve_minutes)
                ).isoformat()

            db.insert_pending(
                conn, post["post_id"], post["thread_id"], post["forum_id"],
                profile.reversed_username, reply_text, auto_approve_at,
            )
            logging.info("Queued reply from %s for post %d", profile.reversed_username, post["post_id"])

        db.mark_seen(conn, post["post_id"], post["thread_id"], post["forum_id"])


def main():
    required_vars = ["GOOGLE_API_KEY", "FORUM_USERNAME", "FORUM_PASSWORD", "ALTER_PASSWORD"]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        raise SystemExit(f"Missing env vars: {', '.join(missing)}")

    live_mode = os.getenv("LIVE_MODE", "false").lower() == "true"
    lookback_hours = int(os.getenv("LOOKBACK_HOURS", "48"))
    poll_interval = int(os.getenv("POLL_INTERVAL", "300"))
    alter_password = os.getenv("ALTER_PASSWORD")

    profiles = _load_profiles("personas")
    if not profiles:
        raise SystemExit("No approved personas found in personas/")
    logging.info("Loaded %d approved personas", len(profiles))

    conn = db.init_db("event.db")

    scanner = VBulletinSession()
    if not scanner.login(os.getenv("FORUM_USERNAME"), os.getenv("FORUM_PASSWORD")):
        raise SystemExit("Scanner login failed")
    logging.info("Scanner logged in")

    app = create_app(conn, profiles, alter_password, live_mode)
    flask_thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False),
        daemon=True,
    )
    flask_thread.start()
    logging.info("Review queue: http://localhost:5000 [%s]", "LIVE" if live_mode else "SIMULATIE")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    logging.info("Processing posts newer than %s (LOOKBACK_HOURS=%d)", cutoff.isoformat(), lookback_hours)

    while True:
        _poll_once(scanner, profiles, conn, alter_password, live_mode, cutoff)

        for entry in db.get_pending_auto_approve(conn):
            logging.info("Auto-approving reply %d for %s", entry["id"], entry["alter_username"])
            _do_approve(conn, dict(entry), alter_password, live_mode)

        time.sleep(poll_interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Shutting down")
```

- [ ] **Step 8: Run the full test suite to verify everything passes**

Run: `pytest tests/ -v`

Expected: All tests PASS. No import errors, no `client` argument mismatches.

- [ ] **Step 9: Commit**

```bash
git add src/workbench/cli.py src/event/webui.py event.py workbench.py tests/event/test_webui.py
git commit -m "refactor: drop client param from wire-up, event.py uses GOOGLE_API_KEY"
```

---

## Task 7: Update `.env.example` and final cleanup

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Update `.env.example`**

Replace `ANTHROPIC_API_KEY=your_key_here` with `GOOGLE_API_KEY=your_key_here`:

```
FORUM_URL=https://your-forum.example.com
FORUM_USERNAME=wokebot
FORUM_PASSWORD=wokebot123
INACTIVITY_YEARS=2
SEARCH_DELAY=6
GOOGLE_API_KEY=your_key_here
ALTER_PASSWORD=your_shared_alter_password_here
LIVE_MODE=false
LOOKBACK_HOURS=48
POLL_INTERVAL=300
```

- [ ] **Step 2: Run the full test suite one final time**

Run: `pytest tests/ -v --tb=short`

Expected: All tests PASS.

- [ ] **Step 3: Verify imports are clean (no stray anthropic references)**

Run: `grep -r "anthropic" src/ event.py workbench.py requirements.txt .env.example`

Expected: No output (zero matches).

- [ ] **Step 4: Commit**

```bash
git add .env.example
git commit -m "refactor: update .env.example to GOOGLE_API_KEY"
```
