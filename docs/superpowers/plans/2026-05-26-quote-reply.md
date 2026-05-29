# Quote-Reply Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a real forum user quotes one of our alter egos, that alter replies back with a VBulletin quote block prepended to the LLM-generated reply.

**Architecture:** Enrich each post dict with a `quoted_alters` set before gate evaluation. The gate uses this to set `weight = 1.0` and skip the topic/random checks while still applying rate caps. `_poll_once` detects the flag when building the LLM prompt and constructing the final reply text.

**Tech Stack:** Python, existing gates/generator/event pipeline.

---

## File map

| File | Change |
|---|---|
| `src/event/gates.py` | Add `detect_quoted_alters`; restructure `evaluate_post` loop with quote bypass |
| `src/event/generator.py` | Add `generate_quote_reply` |
| `event.py` | Call `detect_quoted_alters` per post; route quote candidates through `generate_quote_reply` and prepend quote block |
| `tests/event/test_gates.py` | Tests for `detect_quoted_alters` and the gate bypass |
| `tests/event/test_generator.py` | Tests for `generate_quote_reply` |

---

### Task 1: `detect_quoted_alters` — detection function

**Files:**
- Modify: `src/event/gates.py`
- Test: `tests/event/test_gates.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/event/test_gates.py` (below the existing imports, add the import for `detect_quoted_alters`):

```python
from src.event.gates import evaluate_post, detect_quoted_alters
```

Then add the following test functions at the bottom of the file:

```python
def _make_profile_with_reversed(reversed_username):
    p = PersonaProfile.from_alter_ego({
        "user_id": 1, "original_username": reversed_username[::-1],
        "reversed_username": reversed_username,
        "post_count": 100, "last_active": "2023-01-01",
    })
    return p


def test_detect_quoted_alters_finds_quoted_profile():
    profiles = [_make_profile_with_reversed("ejdar"), _make_profile_with_reversed("nboj")]
    post = {"author": "real_user", "content": "[QUOTE=ejdar;123]something[/QUOTE]\nOriginally Posted by ejdar\nhello"}
    result = detect_quoted_alters(post, profiles)
    assert "ejdar" in result
    assert "nboj" not in result


def test_detect_quoted_alters_is_case_insensitive():
    profiles = [_make_profile_with_reversed("Ejdar")]
    post = {"author": "real_user", "content": "originally posted by ejdar"}
    result = detect_quoted_alters(post, profiles)
    assert "Ejdar" in result


def test_detect_quoted_alters_returns_empty_when_alter_quotes_alter():
    profiles = [_make_profile_with_reversed("ejdar"), _make_profile_with_reversed("nboj")]
    post = {"author": "ejdar", "content": "Originally Posted by nboj\nsomething"}
    result = detect_quoted_alters(post, profiles)
    assert result == set()


def test_detect_quoted_alters_returns_empty_when_no_quote():
    profiles = [_make_profile_with_reversed("ejdar")]
    post = {"author": "real_user", "content": "Gewoon een bericht zonder citaat"}
    result = detect_quoted_alters(post, profiles)
    assert result == set()


def test_detect_quoted_alters_can_find_multiple():
    profiles = [_make_profile_with_reversed("ejdar"), _make_profile_with_reversed("nboj")]
    post = {
        "author": "real_user",
        "content": "Originally Posted by ejdar\n...\nOriginally Posted by nboj\n..."
    }
    result = detect_quoted_alters(post, profiles)
    assert result == {"ejdar", "nboj"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/event/test_gates.py::test_detect_quoted_alters_finds_quoted_profile -v
```

Expected: `FAILED` with `ImportError: cannot import name 'detect_quoted_alters'`

- [ ] **Step 3: Implement `detect_quoted_alters` in `src/event/gates.py`**

Add directly after the module-level constants (after `_MAX_RESPONDERS = 2`), before `evaluate_post`:

```python
def detect_quoted_alters(post: dict, profiles: list[PersonaProfile]) -> set[str]:
    all_reversed = {p.reversed_username for p in profiles}
    if post.get("author", "") in all_reversed:
        return set()
    content = post.get("content", "").lower()
    quoted = set()
    for profile in profiles:
        marker = f"originally posted by {profile.reversed_username.lower()}"
        if marker in content:
            quoted.add(profile.reversed_username)
    return quoted
```

- [ ] **Step 4: Run all new tests to verify they pass**

```bash
pytest tests/event/test_gates.py -v -k "detect_quoted"
```

Expected: 5 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/event/gates.py tests/event/test_gates.py
git commit -m "feat: add detect_quoted_alters to gates"
```

---

### Task 2: Gate bypass for quoted alter egos

**Files:**
- Modify: `src/event/gates.py` (restructure `evaluate_post` loop)
- Test: `tests/event/test_gates.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/event/test_gates.py`:

```python
def test_quoted_alter_gets_max_weight(conn):
    profile = _make_profile(reversed_username="ejdar", forum_name="Offtopic", weight=0.0)
    post = _make_post(forum_name="Zwam", content="Originally Posted by ejdar\nhello")
    post["quoted_alters"] = {"ejdar"}
    result = evaluate_post(post, [profile], conn)
    assert len(result) == 1
    _, weight = result[0]
    assert weight == 1.0


def test_quoted_alter_still_respects_rate_cap(conn):
    from src.event.db import increment_rate
    from datetime import datetime, timezone
    profile = _make_profile(reversed_username="ejdar", forum_name="Offtopic", weight=0.0, hourly_cap=1)
    post = _make_post(forum_name="Zwam", content="Originally Posted by ejdar\nhello")
    post["quoted_alters"] = {"ejdar"}
    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y-%m-%dT%H")
    day_key = now.strftime("%Y-%m-%d")
    increment_rate(conn, "ejdar", hour_key, day_key)
    result = evaluate_post(post, [profile], conn)
    assert result == []


def test_non_quoted_alter_uses_normal_logic(conn):
    profile = _make_profile(reversed_username="ejdar", forum_name="Offtopic", weight=0.0)
    post = _make_post(forum_name="Zwam", content="Gewoon een bericht")
    post["quoted_alters"] = set()
    result = evaluate_post(post, [profile], conn)
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/event/test_gates.py::test_quoted_alter_gets_max_weight -v
```

Expected: `FAILED` — the quoted alter is not bypassing the topic/relevance check yet.

- [ ] **Step 3: Restructure `evaluate_post` in `src/event/gates.py`**

Replace the entire `for profile in profiles:` loop body. The current loop body is:

```python
    for profile in profiles:
        mentioned = profile.reversed_username.lower() in content.lower()
        tag_match = any(tag.lower() in content.lower() for tag in profile.interest_tags)

        if not mentioned and not tag_match:
            weight = profile.topic_weights.get(forum_name, 0.0)
            if weight < _RELEVANCE_THRESHOLD:
                continue
            if random.random() >= weight:
                continue
        else:
            weight = profile.topic_weights.get(forum_name, 1.0)

        hourly = db.get_hourly_count(conn, profile.reversed_username, hour_key)
        daily = db.get_daily_count(conn, profile.reversed_username, day_key)
        if hourly >= profile.hourly_cap or daily >= profile.daily_cap:
            logging.debug("Rate limit hit for %s", profile.reversed_username)
            continue

        passed.append((profile, weight))
```

Replace with:

```python
    for profile in profiles:
        if profile.reversed_username in post.get("quoted_alters", set()):
            weight = 1.0
        else:
            mentioned = profile.reversed_username.lower() in content.lower()
            tag_match = any(tag.lower() in content.lower() for tag in profile.interest_tags)

            if not mentioned and not tag_match:
                weight = profile.topic_weights.get(forum_name, 0.0)
                if weight < _RELEVANCE_THRESHOLD:
                    continue
                if random.random() >= weight:
                    continue
            else:
                weight = profile.topic_weights.get(forum_name, 1.0)

        hourly = db.get_hourly_count(conn, profile.reversed_username, hour_key)
        daily = db.get_daily_count(conn, profile.reversed_username, day_key)
        if hourly >= profile.hourly_cap or daily >= profile.daily_cap:
            logging.debug("Rate limit hit for %s", profile.reversed_username)
            continue

        passed.append((profile, weight))
```

- [ ] **Step 4: Run all gate tests to verify they pass**

```bash
pytest tests/event/test_gates.py -v
```

Expected: all tests `PASSED` (the three new ones plus the 9 existing ones).

- [ ] **Step 5: Commit**

```bash
git add src/event/gates.py tests/event/test_gates.py
git commit -m "feat: gate bypass for quoted alter egos (weight=1.0, rate cap still applies)"
```

---

### Task 3: `generate_quote_reply` in event/generator.py

**Files:**
- Modify: `src/event/generator.py`
- Test: `tests/event/test_generator.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/event/test_generator.py` (after existing imports, add `generate_quote_reply`):

```python
from src.event.generator import generate_reply, generate_quote_reply
```

Then add at the bottom of the file:

```python
_TRIGGERING_QUOTE = {"post_id": 99, "author": "RealUser", "content": "ejdar ik ben het niet eens met jou"}


def test_generate_quote_reply_calls_api():
    with patch("src.event.generator.call_llm_raw", return_value=_make_mock_resp()) as mock_raw:
        result = generate_quote_reply(_make_profile(), _TRIGGERING_QUOTE)
    assert result == "Da valt mee"
    mock_raw.assert_called_once()


def test_generate_quote_reply_prompt_contains_framing():
    with patch("src.event.generator.call_llm_raw", return_value=_make_mock_resp()) as mock_raw:
        generate_quote_reply(_make_profile(), _TRIGGERING_QUOTE)
    _system, user_msg, _max = mock_raw.call_args[0]
    assert "geciteerd" in user_msg
    assert "RealUser" in user_msg
    assert "ejdar ik ben het niet eens met jou" in user_msg


def test_generate_quote_reply_has_no_context_lines():
    with patch("src.event.generator.call_llm_raw", return_value=_make_mock_resp()) as mock_raw:
        generate_quote_reply(_make_profile(), _TRIGGERING_QUOTE)
    _system, user_msg, _max = mock_raw.call_args[0]
    assert "Vorige berichten" not in user_msg


def test_generate_quote_reply_appends_afgekapt_on_max_tokens():
    with patch("src.event.generator.call_llm_raw", return_value=_make_mock_resp("Lang antwoord", "MAX_TOKENS")):
        result = generate_quote_reply(_make_profile(), _TRIGGERING_QUOTE)
    assert result == "Lang antwoord [afgekapt]"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/event/test_generator.py::test_generate_quote_reply_calls_api -v
```

Expected: `FAILED` with `ImportError: cannot import name 'generate_quote_reply'`

- [ ] **Step 3: Implement `generate_quote_reply` in `src/event/generator.py`**

Add at the bottom of the file:

```python
def generate_quote_reply(profile: PersonaProfile, triggering_post: dict) -> str:
    """Generate a direct reply to a post that quoted this alter ego. No thread context."""
    system = build_system_prompt(profile)

    user_content = (
        f"Iemand heeft jou geciteerd en reageert direct op jou. Reageer terug op dit specifieke bericht:\n\n"
        f"[Bericht van {triggering_post['author']}:]\n"
        f"\"{triggering_post['content']}\"\n\n"
        f"Schrijf één forumreactie zoals {profile.reversed_username} dat zou doen. "
        f"Schrijf alleen de reactietekst zelf — geen uitleg, geen opmaak, geen opsomming. "
        f"Citeer de post NIET."
    )

    resp = call_llm_raw(system, user_content, 2048)
    reply = resp.text
    if resp.candidates[0].finish_reason.name == "MAX_TOKENS":
        reply += " [afgekapt]"
    return reply
```

- [ ] **Step 4: Run all generator tests to verify they pass**

```bash
pytest tests/event/test_generator.py -v
```

Expected: all tests `PASSED` (4 new + 5 existing).

- [ ] **Step 5: Commit**

```bash
git add src/event/generator.py tests/event/test_generator.py
git commit -m "feat: add generate_quote_reply to event generator"
```

---

### Task 4: Wire up quote detection and routing in `event.py`

**Files:**
- Modify: `event.py`

- [ ] **Step 1: Call `detect_quoted_alters` before `evaluate_post` in `_poll_once`**

In `event.py`, find the Phase 1 block inside the `for post in new_posts:` loop. The current code after the `_is_image_only` check is:

```python
        for profile, weight in gates.evaluate_post(post, profiles, conn):
            candidates.append((post, profile, weight))
```

Replace with:

```python
        post["quoted_alters"] = gates.detect_quoted_alters(post, profiles)
        for profile, weight in gates.evaluate_post(post, profiles, conn):
            candidates.append((post, profile, weight))
```

- [ ] **Step 2: Route quote candidates through `generate_quote_reply` in Phase 3**

In `event.py`, find the Phase 3 loop. The current block is:

```python
    for post, profile, _ in selected:
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
```

Replace with:

```python
    for post, profile, _ in selected:
        is_quote_reply = profile.reversed_username in post.get("quoted_alters", set())

        if is_quote_reply:
            try:
                llm_reply = event_generator.generate_quote_reply(profile, post)
            except Exception as exc:
                logging.warning("Quote-reply generation failed for post %d / %s: %s",
                                post["post_id"], profile.reversed_username, exc)
                continue
            quote_block = (
                f"[QUOTE={post['author']};{post['post_id']}]"
                f"{post.get('content', '')}"
                f"[/QUOTE]\n"
            )
            reply_text = quote_block + llm_reply
        else:
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
```

- [ ] **Step 3: Run the full test suite to verify nothing is broken**

```bash
pytest -v
```

Expected: all tests `PASSED`. The number should be the existing count plus the 9 new tests added in Tasks 1–3.

- [ ] **Step 4: Commit**

```bash
git add event.py
git commit -m "feat: wire up quote detection and quote-reply routing in _poll_once"
```
