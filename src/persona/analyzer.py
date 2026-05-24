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
        f'"{alter["original_username"]}" (user_id: {alter["user_id"]}, totaal {alter["post_count"]} posts op het forum).\n\n'
        f"Berichten:\n{posts_text}\n\n"
        f"Geef een JSON object terug met dit schema:\n{_SCHEMA_DESCRIPTION}\n\n"
        f"Kies maximaal 20 representatieve verbatim posts als example_posts. "
        f"Geef enkel het JSON object terug, geen uitleg."
    )

    response = client.messages.create(
        model=_MODEL,
        max_tokens=3000,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        data = _parse_json_response(response.content[0].text)
    except (AttributeError, IndexError):
        data = None

    if data:
        _apply_analysis(profile, data)
        profile.posts_analyzed = len(posts)
        profile.pages_loaded = 1

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

    response = client.messages.create(
        model=_MODEL,
        max_tokens=3000,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        data = _parse_json_response(response.content[0].text)
    except (AttributeError, IndexError):
        data = None

    if data:
        _apply_analysis(profile, data)
        profile.posts_analyzed += len(posts)
        profile.pages_loaded += 1

    return profile
