import os
from google import genai
from google.genai import types

# Initialize client with API key; mocked in tests
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
