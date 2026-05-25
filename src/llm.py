import os
from google import genai
from google.genai import types

_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY", ""))

MODEL_PRO = "gemini-3.1-pro-preview"    # workbench: complex analysis & persona generation
MODEL_FLASH = "gemini-3.5-flash"  # live event: speed-critical reply generation


def call_llm(system: str, user: str, max_tokens: int) -> str:
    resp = _client.models.generate_content(
        model=MODEL_PRO,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
        ),
        contents=[user],
    )
    if resp.candidates and resp.candidates[0].finish_reason.name == "MAX_TOKENS":
        raise ValueError(f"Gemini response afgekapt bij {max_tokens} tokens (model limiet bereikt)")
    return resp.text


def call_llm_raw(system: str, user: str, max_tokens: int, model: str = MODEL_FLASH):
    return _client.models.generate_content(
        model=model,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
        ),
        contents=[user],
    )
