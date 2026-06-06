# Forum Community Simulator — Gemini Context & Developer Guide

This file provides system architecture details, codebase conventions, Gemini API integrations, and developer guidelines for the **Forum Community Simulator** project.

---

## 🚀 Project Overview

The project is a 24-hour AI-driven event simulated or executed live on a Dutch-language shrimp-keeping forum (`your-forum.example.com`, running **vBulletin 3.7**).
- **Goal:** Resurrect the 27 most historically active forum members who have been inactive for over 2 years.
- **AI Alter Egos:** Each inactive member gets an AI persona with:
  1. A reversed username (e.g. `ShrimpKing` $\rightarrow$ `gniKpmirS`).
  2. A mirrored avatar.
  3. An AI persona crafted from their actual historical post data.
- **Modes:** 
  - **Phase 1 — Workbench CLI:** Scraping, analyzing, and refining the persona files interactively.
  - **Phase 2 — Live Event:** Polling the forum, generating replies via Gemini Flash, and managing a review/approval web queue (Flask).

---

## 📁 Project Architecture & File Layout

```
.
├── select_accounts.py        # Selection pipeline runner (produces approved_accounts.json)
├── workbench.py              # Phase 1: Interactive TUI CLI for persona building
├── event.py                  # Phase 2: Orchestrator loop (poller + review queue flask app)
│
├── config/
│   ├── approved_accounts.json# List of the 27 selected/approved alter egos (gitignored)
│   └── test_posts.json       # Test posts for generating reply previews in workbench
│
├── personas/                 # Output directory containing approved persona profiles (gitignored)
│   └── {username}.json       # One JSON per approved alter ego persona
│
├── src/
│   ├── llm.py                # Wrapper around google-genai SDK (Single Source of Truth)
│   ├── models.py             # Shared data schemas / dataclasses
│   ├── session.py            # Custom HTTP requests wrapper managing vBulletin login & sessions
│   │
│   ├── scraper/              # Base scrapers for profiles and member lists
│   │   ├── memberlist.py     # Parses vBulletin's poster member list
│   │   └── profile.py        # Scrapes profile fields (like last active dates)
│   │
│   ├── selection/            # Logic for filtering candidates during Phase 0 selection
│   │   ├── pipeline.py       # Inactivity filter and account proposals
│   │   └── cli.py            # Console GUI for selecting/approving accounts
│   │
│   ├── persona/              # Module for scraping & refining AI personas
│   │   ├── models.py         # PersonaProfile schema and serializer/deserializer
│   │   ├── scraper.py        # PostScraper — handles historical post retrieval
│   │   ├── analyzer.py       # Interacts with Gemini Pro to build/refine profiles
│   │   └── generator.py      # Prompt builder and response generator
│   │
│   └── event/                # Phase 2 Event Loop componentry
│       ├── poller.py         # vBulletin getdaily/sandbox post poller
│       ├── thread_scraper.py # Context retriever (collects recent thread posts)
│       ├── gates.py          # Forum-wide response gating (relevance/caps)
│       ├── sandbox_gates.py  # Sandbox thread trigger and response gates
│       ├── generator.py      # Gemini Flash live response generation
│       ├── db.py             # SQLite helper (event.db) for seen posts/pending queue
│       ├── webui.py          # Flask approval UI (runs on port 5000)
│       └── poster.py         # Logs in as alter-egos and posts HTTP replies
│
└── tests/                    # Unit tests suite (pytest)
    ├── conftest.py           # Injects mock environment variables
    └── ...
```

---

## 🤖 Gemini API Integration (`src/llm.py`)

The project uses the new Google GenAI Python SDK (`google-genai`).

### Key Models & Roles
| Model | Identifier | Purpose / Phase |
| :--- | :--- | :--- |
| **Pro** | `gemini-3.1-pro-preview` | Complex persona analysis & iterative profile refinement (Phase 1 Workbench) |
| **Flash** | `gemini-3.5-flash` | Live event generation (Phase 2) & sample reply previews in Workbench |

### Helper Functions
- **`call_llm(system: str, user: str, max_tokens: int) -> str`**:
  - Always uses `gemini-3.1-pro-preview` (Pro).
  - Automatically raises `ValueError` if the response gets truncated (`finish_reason == "MAX_TOKENS"`).
  - Used for profile generation and refinement.
- **`call_llm_raw(system: str, user: str, max_tokens: int, model: str = MODEL_FLASH)`**:
  - Allows specifying the model (defaults to `gemini-3.5-flash`).
  - Returns the raw API response object (callers inspect things like `finish_reason`).

### Key Context Constraints
- **Example Posts:** Verbatim examples are parsed, selected, and truncated **in Python** (using `_select_examples` in `src/persona/analyzer.py`). This prevents Gemini Pro from wasting its output tokens returning original post text.
- **JSON Outputs:** Prompts in `analyzer.py` explicitly instruct the models to return *only* valid JSON.
- **Opinion Fingerprint Cap:** Up to 25 items are captured inside `PersonaProfile.opinion_fingerprint`.

---

## 🔍 vBulletin 3.7 Scraper & Session Quirks

vBulletin does not provide a JSON API, requiring HTML scraping with the following behaviors:

1. **Authentication:**
   - Requires MD5 password hashing (`vb_login_md5password` form parameter).
   - Session cookies must be checked by executing a subsequent `GET` to `index.php`.
   - The security token is extracted from the javascript context (`SECURITYTOKEN = '...'`) of `index.php` and included in subsequent POST requests.
2. **Search Limits & Incremental Windowing:**
   - vBulletin limits searches (e.g. `search.php?do=finduser`) to **200 results** (exactly 2 pages of 100).
   - To scrape more, the scraper uses the advanced search form (`do=process`) with the query parameter `searchdate=N` (N = days ago) combined with `beforeafter=before` and `order=descending`.
   - By capturing `oldest_post_ts` from each batch and passing it as `before_ts` to the next page fetch, the script rolls backward in time to collect thousands of historical posts.
   - **Rate Limits:** vBulletin rate-limits search queries. The project enforces a minimum delay (e.g. `SEARCH_DELAY=6` seconds) between search actions. There is no rate limit on viewing individual threads or post pages.
3. **Content Enrichment:**
   - Search results return truncated snippets. To fetch full posts, `PostScraper` fetches `showthread.php?p={post_id}` and replaces the snippet with the full text body using BeautifulSoup.
   - Smilie `<img>` tags are converted into text values (e.g., replacement based on image title). Other image tags are replaced with `[afbeelding]`.

---

## 🛡️ Gating Logic & Operating Modes

`event.py` runs in one of two mutually exclusive modes:

### 1. Forum-Wide Mode (Default)
Polls the entire forum via `getdaily` searches.
- **Gates (`src/event/gates.py`):**
  - **Excluded Forums:** Filters out IDs `{20, 29, 40, 42}` (HQ, Donations, Discretie, Forum Games).
  - **Short Posts:** Skip posts that contain fewer than 5 words after stripping BBCode tags and quotes.
  - **Bypasses:** If the post quotes the alter ego (`"originally posted by {reversed_username}"`) or mentions their username, it bypasses random gates and enters with weight `1.0`.
  - **Topic Gates:** Otherwise, checks `topic_weights[forum_name] >= 0.2`. It then runs a stochastic filter: `random.random() < topic_weight`.
  - **Rate Caps:** Skips candidate if their hourly count $\ge$ `hourly_cap` (default 3) or daily rolling 24h count $\ge$ `daily_cap` (default 10).
- **Cycle Caps:** All selected `(post, profile, weight)` tuples are sorted by weight descending. The top `REPLIES_PER_CYCLE` (default 3) are chosen.

### 2. Sandbox Mode (Activated when `SANDBOX_THREAD_IDS` is set in `.env`)
Watches a specific comma-separated set of threads.
- **Gates (`src/event/sandbox_gates.py`):**
  - If a user mentions or quotes a bot (reversed or original username), those bots (up to 3) are triggered.
  - If no triggers occur, random eligible bots (up to `SANDBOX_REPLIES_PER_POST`, default 3) are selected.
  - No cycle-level capping occurs (all triggered bots respond, bypassing `REPLIES_PER_CYCLE`).

---

## 🛠️ Developer Setup & Commands

### Virtual Environment Setup
Ensure you are using Python 3.11+.

```powershell
# Create venv
python -m venv .venv

# Activate venv
.venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

### Running Tests
The project features a suite of 180+ tests. Testing sets a dummy API key in `tests/conftest.py` so real LLM calls are blocked.

> **Note for AI Agents on Windows:** If the `pytest` command is not recognized in the global terminal, you must either activate the virtual environment first (`.\.venv\Scripts\Activate.ps1`) or invoke it via python: `python -m pytest`.

```powershell
# Run all tests
pytest

# Run a specific test suite
pytest tests/event/

# Run with coverage report
pytest --cov=src
```

### Running the Workbench
Workbench interactive loop is used to scrape post histories and construct persona profiles:

```powershell
python workbench.py
```
- Press `b` to trigger bulk initial analysis for all unstarted alter egos.
- Inside a persona: `l` loads/refines, `s` generates sample preview replies, `a` approves, `e` edits JSON, `x` resets.

### Agentic Persona Builder (via Gemini Skills)
As an alternative to the Python `workbench.py` CLI, AI agents can autonomously build personas using the **Build Persona Skill** (`.gemini/skills/build-persona/SKILL.md`).
- Just ask the agent to *"build a persona for username X"*.
- The agent will dynamically spawn a `DataCollector` subagent to paginate through the `get_user_posts` MCP tool and save raw posts to a scratch file.
- It will then spawn a `PersonaAnalyzer` subagent to ingest the raw posts into its massive context window and generate the final structured JSON.
- The resulting JSON is saved to the `agent_personas/` directory (which is safely gitignored to protect user data).

### Running the Orchestrator (Live Event)
Runs the polling thread and launches the Flask local review UI.

```powershell
python event.py
```
- Review approval queue in web browser: **`http://localhost:5000`**
- Set `LIVE_MODE=true` in `.env` to make alter egos post live replies.

---

## 🔌 MCP Server (Model Context Protocol)

The project includes an **MCP Server** (`src/mcp/server.py`) powered by the official `mcp` Python SDK (using `FastMCP`).
This server allows external AI agents (like Claude Desktop or Cursor) to securely interface with the forum using semantic tools, abstracting away the vBulletin scraping idiosyncrasies.

**Key Architecture Points:**
- **Shared Session:** The server initializes a single `VBulletinSession` authenticated via `.env` credentials (`FORUM_USERNAME`, `FORUM_PASSWORD`) upon the first request.
- **Read-Only Context:**
  - `forum://memberlist/top100`: Exposes the top posters from the forum.
  - `forum://user/{user_id}/last_active`: Returns the last active date (safely converted from Python `datetime.date` to an ISO string for JSON serialization).
- **Mutations & Search Actions:**
  - `get_user_posts` wraps `PostScraper.fetch_window` to support paging.
  - `get_thread_context` retrieves conversation history.
  - `get_daily_activity` wraps the `getdaily` poller.
  - `post_reply` logs in securely as a specific alter-ego to post live responses.

---

## 💡 Guidelines for Future Coding Sessions

1. **Preserve Mocks:** `tests/conftest.py` automatically overrides `GOOGLE_API_KEY` to prevent accidental billing and API traffic during test runs. Ensure all LLM modules patch at the call site (e.g. mock `src.persona.analyzer.call_llm` rather than `_client` directly).
2. **Comment Preservation:** Keep all existing docstrings, annotations, and comments intact unless directly requested to clean them up.
3. **No Direct Requests inside Sandbox or Production Paths:** Always wrap API sessions in `VBulletinSession` and handle transient request errors or timeouts gracefully (using `_TIMEOUT = 30`).
4. **Planning Mode workflow:** If making architectural updates (like changing gates or altering JSON schemas), stop and write an implementation plan inside `docs/superpowers/plans/` and wait for review.
