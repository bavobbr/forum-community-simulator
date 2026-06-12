import os
from google import genai
from google.genai import types
from pydantic import BaseModel

_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY", ""))

MODEL_PRO = "gemini-3.1-pro-preview"    # workbench: complex analysis & persona generation
MODEL_FLASH = "gemini-3.5-flash"  # live event: speed-critical reply generation


def call_llm(system: str, user: str, max_tokens: int) -> str:
    resp = _client.models.generate_content(
        model=MODEL_PRO,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            automatic_function_calling={"disable": True},
        ),
        contents=[user],
    )
    if resp.candidates and resp.candidates[0].finish_reason.name == "MAX_TOKENS":
        raise ValueError(f"Gemini response afgekapt bij {max_tokens} tokens (model limiet bereikt)")
    return resp.text


def call_llm_raw(system: str, user: str, max_tokens: int, model: str = MODEL_FLASH, response_schema: type[BaseModel] | dict | None = None):
    config_args = {
        "system_instruction": system,
        "max_output_tokens": max_tokens,
        "automatic_function_calling": {"disable": True},
    }
    if response_schema:
        config_args["response_mime_type"] = "application/json"
        config_args["response_schema"] = response_schema

    return _client.models.generate_content(
        model=model,
        config=types.GenerateContentConfig(**config_args),
        contents=[user],
    )

def generate_embedding(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of strings."""
    if not texts:
        return []
    from concurrent.futures import ThreadPoolExecutor
    import time
    from google import genai
    import os

    local_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY", ""))

    embeddings = [None] * len(texts)
    def fetch_embedding(idx, text):
        for attempt in range(3):
            try:
                resp = local_client.models.embed_content(
                    model="gemini-embedding-2",
                    contents=text,
                )
                embeddings[idx] = resp.embeddings[0].values
                return
            except Exception as e:
                if attempt == 2:
                    raise
                time.sleep(1 * (attempt + 1))

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for idx, text in enumerate(texts):
            futures.append(executor.submit(fetch_embedding, idx, text))
        for future in futures:
            future.result()
            
    return embeddings
