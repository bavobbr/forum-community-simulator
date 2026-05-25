# Gemini LLM Refactor Design

## Goal

Replace the Anthropic SDK with Google Gemini (`gemini-3.5-flash`) across the entire codebase by introducing a thin `src/llm.py` helper that owns all provider-specific details.

## Context

The Anthropic API key is unavailable due to a Stripe billing issue. Google Gemini works fine. The codebase has three LLM call sites with identical call shapes (system prompt + user text + max_tokens → string), making a thin helper a natural fit. No multi-vendor abstraction is needed — this is a hardwire to Gemini.

## Architecture

A new `src/llm.py` module initialises the Gemini client once at import time using the `GOOGLE_API_KEY` environment variable and exposes a single function:

```python
def call_llm(system: str, user: str, max_tokens: int) -> str
```

All three domain modules drop their `client` parameter and call `call_llm` directly. The two entry points (`event.py`, `workbench.py`) stop constructing and passing a client altogether.

## New File: `src/llm.py`

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
```

Truncation detection (used in `analyzer.py` to detect incomplete JSON): `resp.candidates[0].finish_reason.name == "MAX_TOKENS"` replaces `response.stop_reason == "max_tokens"`. The `call_llm` helper does not hide this — callers that need it call the Gemini SDK response directly via a second helper or check the return value length. To keep it simple, `analyzer.py` will use a second function:

```python
def call_llm_raw(system: str, user: str, max_tokens: int):
    """Returns the raw response for callers that need finish_reason."""
    return _client.models.generate_content(...)
```

Both functions live in `src/llm.py`.

## Files Changed

| File | Change |
|---|---|
| `src/llm.py` | **new** — Gemini client init, `call_llm()`, `call_llm_raw()` |
| `src/persona/analyzer.py` | drop `client` param; replace 2× Anthropic calls with `call_llm` / `call_llm_raw`; update truncation check |
| `src/persona/generator.py` | drop `client` param; replace 1× Anthropic call with `call_llm` |
| `src/event/generator.py` | drop `client` param; replace 1× Anthropic call with `call_llm` |
| `src/workbench/cli.py` | drop `client` type hint and parameter from all functions that accepted it |
| `event.py` | remove `import anthropic`, remove `client = anthropic.Anthropic()`, remove client arg from `generate_reply` calls |
| `workbench.py` | remove `import anthropic`, remove client construction, remove client arg from CLI calls |
| `requirements.txt` | `anthropic==0.104.1` → `google-genai` (unpinned, latest stable) |
| `.env.example` | `ANTHROPIC_API_KEY=your_key_here` → `GOOGLE_API_KEY=your_key_here` |

## Truncation Handling

`analyzer.py` checks whether the LLM response was truncated mid-JSON and raises an error if so. This check currently uses `response.stop_reason == "max_tokens"`. After refactor it uses:

```python
resp = call_llm_raw(system, user, max_tokens)
text = resp.text
truncated = resp.candidates[0].finish_reason.name == "MAX_TOKENS"
```

## Environment Variable

`ANTHROPIC_API_KEY` is replaced by `GOOGLE_API_KEY`. The `workbench.py` entry point currently reads `ANTHROPIC_API_KEY` explicitly and passes it to the client constructor. After refactor, neither entry point touches the API key — `src/llm.py` reads `GOOGLE_API_KEY` at import time.

## Testing

Existing tests that mock `anthropic.Anthropic` must be updated to mock `src.llm.call_llm` (or `src.llm.call_llm_raw`) instead. No new test logic needed — the mock surface shrinks from SDK calls to a single function.

## Non-Goals

- No multi-vendor support
- No runtime model switching
- No streaming
- No retry logic (Gemini SDK handles transient errors at the network level)
