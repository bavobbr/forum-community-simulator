# Interest Tags Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `interest_tags` to `PersonaProfile`, populate them via the LLM analyzer, and use them in `gates.py` to let content-level keyword matches bypass the forum-section threshold.

**Architecture:** `interest_tags` is a flat `list[str]` of 10–15 concrete keywords per persona. In the analyzer, it is generated on the first pass and updated additively on refine passes (same pattern as `dialect_markers`). In `gates.py`, a case-insensitive substring match of any tag in post content bypasses the `topic_weights` gate — identical treatment to a name mention. Rate limits still apply.

**Tech Stack:** Python dataclasses, `google-genai` SDK, pytest, `unittest.mock.patch`

---

### Task 1: Add `interest_tags` to `PersonaProfile`

**Files:**
- Modify: `src/persona/models.py`
- Test: `tests/persona/test_models.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/persona/test_models.py`:

```python
def test_interest_tags_defaults_to_empty():
    profile = PersonaProfile.from_alter_ego(_sample_alter())
    assert profile.interest_tags == []


def test_interest_tags_round_trips():
    profile = PersonaProfile.from_alter_ego(_sample_alter())
    profile.interest_tags = ["wielrennen", "Remco Evenepoel"]
    d = profile.to_dict()
    restored = PersonaProfile.from_dict(d)
    assert restored.interest_tags == ["wielrennen", "Remco Evenepoel"]


def test_from_dict_handles_missing_interest_tags():
    minimal = {
        "user_id": 42, "original_username": "foo", "reversed_username": "oof",
        "post_count": 100, "last_active": "2020-01-01",
    }
    profile = PersonaProfile.from_dict(minimal)
    assert profile.interest_tags == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/persona/test_models.py::test_interest_tags_defaults_to_empty tests/persona/test_models.py::test_interest_tags_round_trips tests/persona/test_models.py::test_from_dict_handles_missing_interest_tags -v
```

Expected: `AttributeError: 'PersonaProfile' object has no attribute 'interest_tags'`

- [ ] **Step 3: Add the field to `PersonaProfile`**

In `src/persona/models.py`, add after the `rhetorical_patterns` field (line 50):

```python
    interest_tags: list[str] = field(default_factory=list)
```

In `from_dict` (after the `rhetorical_patterns=` line), add:

```python
            interest_tags=d.get("interest_tags", []),
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/persona/test_models.py::test_interest_tags_defaults_to_empty tests/persona/test_models.py::test_interest_tags_round_trips tests/persona/test_models.py::test_from_dict_handles_missing_interest_tags -v
```

Expected: all 3 PASS

- [ ] **Step 5: Run full suite to check for regressions**

```bash
pytest -v
```

Expected: all previously passing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add src/persona/models.py tests/persona/test_models.py
git commit -m "feat: add interest_tags field to PersonaProfile"
```

---

### Task 2: Populate `interest_tags` in the first-pass analyzer

**Files:**
- Modify: `src/persona/analyzer.py`
- Test: `tests/persona/test_analyzer.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/persona/test_analyzer.py`:

```python
def test_analyze_first_batch_populates_interest_tags():
    response = dict(_MOCK_ANALYSIS_RESPONSE)
    response["interest_tags"] = ["PlayStation", "Nintendo Switch", "Elden Ring"]
    with patch("src.persona.analyzer.call_llm", return_value=json.dumps(response)):
        profile = analyze_first_batch(_ALTER, _SAMPLE_POSTS)
    assert profile.interest_tags == ["PlayStation", "Nintendo Switch", "Elden Ring"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/persona/test_analyzer.py::test_analyze_first_batch_populates_interest_tags -v
```

Expected: FAIL — `interest_tags` is `[]` (field exists but `_apply_analysis` ignores it)

- [ ] **Step 3: Add `interest_tags` to `_SCHEMA_DESCRIPTION` and `_apply_analysis`**

In `src/persona/analyzer.py`, add to `_SCHEMA_DESCRIPTION` (after the `"rhetorical_patterns"` line, before the closing `}`):

```python
  "interest_tags": ["10-15 specifieke concrete onderwerpen: eigennamen, hobby's, merken, ploegen, spellen, games, tv-series, ... — dingen die letterlijk in posts voorkomen"]
```

In `_apply_analysis`, add after the `profile.rhetorical_patterns =` line:

```python
    profile.interest_tags = data.get("interest_tags", profile.interest_tags)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/persona/test_analyzer.py::test_analyze_first_batch_populates_interest_tags -v
```

Expected: PASS

- [ ] **Step 5: Run full suite to check for regressions**

```bash
pytest -v
```

Expected: all previously passing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add src/persona/analyzer.py tests/persona/test_analyzer.py
git commit -m "feat: populate interest_tags in first-pass persona analysis"
```

---

### Task 3: Merge `new_interest_tags` in the refine pass

**Files:**
- Modify: `src/persona/analyzer.py`
- Test: `tests/persona/test_analyzer.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/persona/test_analyzer.py`:

```python
def test_refine_merges_new_interest_tags():
    existing = PersonaProfile.from_alter_ego(_ALTER)
    existing.posts_analyzed = 100
    existing.pages_loaded = 1
    existing.interest_tags = ["PlayStation"]
    response = dict(_MOCK_REFINE_RESPONSE)
    response["new_interest_tags"] = ["Nintendo Switch", "PlayStation"]  # PlayStation is a duplicate
    with patch("src.persona.analyzer.call_llm", return_value=json.dumps(response)):
        updated = refine_with_batch(existing, _SAMPLE_POSTS)
    assert "Nintendo Switch" in updated.interest_tags
    assert updated.interest_tags.count("PlayStation") == 1  # no duplicate


def test_refine_includes_existing_tags_in_prompt():
    existing = PersonaProfile.from_alter_ego(_ALTER)
    existing.posts_analyzed = 100
    existing.pages_loaded = 1
    existing.interest_tags = ["wielrennen", "Remco Evenepoel"]
    response = dict(_MOCK_REFINE_RESPONSE)
    response["new_interest_tags"] = []
    with patch("src.persona.analyzer.call_llm", return_value=json.dumps(response)) as mock_llm:
        refine_with_batch(existing, _SAMPLE_POSTS)
    _, user_prompt, _ = mock_llm.call_args[0]
    assert "wielrennen" in user_prompt
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/persona/test_analyzer.py::test_refine_merges_new_interest_tags tests/persona/test_analyzer.py::test_refine_includes_existing_tags_in_prompt -v
```

Expected: both FAIL — `new_interest_tags` key not handled, existing tags not in prompt

- [ ] **Step 3: Add `new_interest_tags` to `_REFINE_SCHEMA`**

In `src/persona/analyzer.py`, add to `_REFINE_SCHEMA` (after `"new_rhetorical_patterns"` line, before the closing `}`):

```python
  "new_interest_tags": ["nieuwe tags niet al in het bestaande profiel"]
```

- [ ] **Step 4: Add merge logic to `_merge_refine`**

In `_merge_refine`, add after the `profile.rhetorical_patterns.extend(new_patterns)` line:

```python
    new_tags = [t for t in data.get("new_interest_tags", []) if t not in profile.interest_tags]
    profile.interest_tags.extend(new_tags)
```

- [ ] **Step 5: Add existing tags to `current_summary` in `refine_with_batch`**

In `refine_with_batch`, replace the entire `current_summary` block with:

```python
    current_summary = (
        f"Gebruiker: {profile.original_username}\n"
        f"Huidige dialect markers: {', '.join(profile.dialect_markers)}\n"
        f"Huidige opinion fingerprint ({len(profile.opinion_fingerprint)} items): "
        + "; ".join(profile.opinion_fingerprint) + "\n"
        f"Huidige topic weights: {profile.topic_weights}\n"
        f"Huidige persona summary: {profile.persona_summary}\n"
        f"Huidige typical_post_length: {profile.typical_post_length} woorden\n"
        f"Huidige interest tags: {', '.join(profile.interest_tags) or '(geen)'}"
    )

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/persona/test_analyzer.py::test_refine_merges_new_interest_tags tests/persona/test_analyzer.py::test_refine_includes_existing_tags_in_prompt -v
```

Expected: both PASS

- [ ] **Step 7: Run full suite to check for regressions**

```bash
pytest -v
```

Expected: all previously passing tests still PASS

- [ ] **Step 8: Commit**

```bash
git add src/persona/analyzer.py tests/persona/test_analyzer.py
git commit -m "feat: merge new_interest_tags in persona refine pass"
```

---

### Task 4: Use `interest_tags` in gates routing

**Files:**
- Modify: `src/event/gates.py`
- Test: `tests/event/test_gates.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/event/test_gates.py`:

```python
def test_tag_match_bypasses_topic_weight(conn):
    profile = _make_profile(forum_name="Videogames", weight=0.0)
    profile.interest_tags = ["wielrennen", "Remco Evenepoel"]
    post = _make_post(forum_name="Zwam", content="De Tour de France was fantastisch, wielrennen op zijn best!")
    result = evaluate_post(post, [profile], conn)
    assert profile in result


def test_tag_match_is_case_insensitive(conn):
    profile = _make_profile(forum_name="Videogames", weight=0.0)
    profile.interest_tags = ["Remco Evenepoel"]
    post = _make_post(forum_name="Zwam", content="remco evenepoel wint weer!")
    result = evaluate_post(post, [profile], conn)
    assert profile in result


def test_tag_match_respects_rate_limit(conn):
    from src.event.db import increment_rate
    from datetime import datetime, timezone
    profile = _make_profile(forum_name="Videogames", weight=0.0, hourly_cap=1)
    profile.interest_tags = ["wielrennen"]
    post = _make_post(forum_name="Zwam", content="wielrennen is geweldig")
    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y-%m-%dT%H")
    day_key = now.strftime("%Y-%m-%d")
    increment_rate(conn, "ejdar", hour_key, day_key)
    result = evaluate_post(post, [profile], conn)
    assert result == []


def test_no_tags_still_requires_topic_weight(conn):
    profile = _make_profile(forum_name="Videogames", weight=0.0)
    profile.interest_tags = []
    post = _make_post(forum_name="Zwam", content="wielrennen is geweldig")
    result = evaluate_post(post, [profile], conn)
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/event/test_gates.py::test_tag_match_bypasses_topic_weight tests/event/test_gates.py::test_tag_match_is_case_insensitive tests/event/test_gates.py::test_tag_match_respects_rate_limit tests/event/test_gates.py::test_no_tags_still_requires_topic_weight -v
```

Expected: `test_tag_match_bypasses_topic_weight` and `test_tag_match_is_case_insensitive` FAIL (profile not returned); others PASS incidentally

- [ ] **Step 3: Add tag_match to `evaluate_post`**

In `src/event/gates.py`, replace the block starting with `mentioned = profile.reversed_username.lower()` (lines 31–41) with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/event/test_gates.py::test_tag_match_bypasses_topic_weight tests/event/test_gates.py::test_tag_match_is_case_insensitive tests/event/test_gates.py::test_tag_match_respects_rate_limit tests/event/test_gates.py::test_no_tags_still_requires_topic_weight -v
```

Expected: all 4 PASS

- [ ] **Step 5: Run full suite to check for regressions**

```bash
pytest -v
```

Expected: all previously passing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add src/event/gates.py tests/event/test_gates.py
git commit -m "feat: bypass topic_weight gate on interest_tags match"
```
