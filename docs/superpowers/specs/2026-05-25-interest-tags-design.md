# Interest Tags — Design Spec
**Date:** 2026-05-25

## Problem

`topic_weights` keys off forum *section* (Zwam, Videogames, …). Most personas have high Zwam weight, so section-based routing can't distinguish a post about "Remco Evenepoel" from a post about a broken PC — both land in Zwam. We need per-persona content-level interest signals to route better.

## Solution

Add `interest_tags: list[str]` to `PersonaProfile` — 10–15 concrete, specific keywords per persona (proper nouns, hobbies, brands, sports teams, game titles, etc.). In `gates.py`, a case-insensitive substring match of any tag in the post body bypasses the forum-section gate, identical to how a name mention already works.

---

## 1. Model (`src/persona/models.py`)

Add one field to `PersonaProfile`:

```python
interest_tags: list[str] = field(default_factory=list)
```

`from_dict` reads `d.get("interest_tags", [])`. No cap enforced in the model; the analyzer prompt targets 10–15, which is specific enough that natural bloat is unlikely.

---

## 2. Analyzer (`src/persona/analyzer.py`)

### First-pass schema (`_SCHEMA_DESCRIPTION`)

Add:
```json
"interest_tags": ["10-15 specifieke concrete onderwerpen: eigennamen, hobby's, merken, ploegen, spellen, ..."]
```

LLM instruction: ask for things that appear verbatim or near-verbatim in Dutch forum posts (e.g. "wielrennen", "Remco Evenepoel", "PlayStation", "Honda Hornet", "D&D").

### Refine/diff schema (`_REFINE_SCHEMA`)

Add:
```json
"new_interest_tags": ["nieuwe tags niet al in het bestaande profiel"]
```

Merged additively in `_merge_refine` — same pattern as `new_dialect_markers`. No hard cap.

### `current_summary` in `refine_with_batch`

Add a line showing existing tags so the LLM doesn't repeat them:
```
Huidige interest tags: wielrennen, Remco Evenepoel, ...
```

---

## 3. Gates (`src/event/gates.py`)

Replace the current mention-only check with a combined mention+tag check:

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

A tag match is treated identically to a name mention: bypasses the threshold and probabilistic roll, but **rate limits still apply**. The fallback weight of `1.0` ensures tag-matched personas sort at the top when multiple candidates pass.

---

## 4. Tests

- `tests/persona/test_analyzer.py`: verify `interest_tags` is populated from first-pass JSON; verify `new_interest_tags` is merged additively in refine.
- `tests/event/test_gates.py` (new or existing): verify tag match bypasses topic_weight gate; verify rate limits still block a tag-matched persona; verify tag matching is case-insensitive.

---

## Out of scope

- Semantic/embedding-based matching (keyword substring is sufficient and keeps gate latency near zero).
- A separate backfill script (personas are being regenerated from scratch).
- Any UI changes to the workbench (tags are shown as part of the existing profile summary panel implicitly via the JSON editor).
