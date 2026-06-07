import json
import re
from src.llm import call_llm
from src.persona.models import PersonaProfile


def _select_examples(posts: list[dict], n: int = 10, max_chars: int = 400) -> list[str]:
    """Pick n representative posts from the post list, each capped at max_chars."""
    def _has_quote(p: dict) -> bool:
        if p.get("quoted_users"):
            return True
        content_lower = p.get("content", "").lower()
        if "[quote" in content_lower or "[citaat" in content_lower:
            return True
        return False

    candidates = [p for p in posts if len(p.get("content", "")) > 20 and not _has_quote(p)]
    if not candidates:
        return []
    step = max(1, len(candidates) // n)
    selected = candidates[::step][:n]
    return [p["content"][:max_chars] for p in selected]

_SYSTEM = (
    "Je bent een expert in het analyseren van online forum gedrag van Nederlandstalige gebruikers. "
    "Je analyseert berichten en geeft je antwoord altijd als geldig JSON object, zonder uitleg of markdown."
)

_SCHEMA_DESCRIPTION = """{
  "dialect_markers": ["lijst van typische dialect-/spreektaalwoorden die deze gebruiker gebruikt"],
  "formality": "very_casual | casual | formal",
  "sentence_length": "short | medium | long",
  "punctuation_style": "korte beschrijving van interpunctie en hoofdlettergebruik",
  "topic_weights": {"forumnaam": gewicht_0_tot_1, ...},
  "opinion_fingerprint": ["JE MOET MINSTENS 25 EN MAXIMAAL 50 concrete standpunten genereren over diverse onderwerpen. Maak ze specifiek en bruikbaar als debatpunten."],
  "frequent_interactions": {"username": "ally | rival | neutral", ...},
  "peak_hours": [18, 19, 20],
  "typical_post_length": gemiddeld_aantal_woorden_per_bericht_als_int,
  "daily_cap": gemiddeld_posts_per_dag_als_int,
  "hourly_cap": max_posts_per_uur_als_int,
  "persona_summary": "Uitgebreide beschrijving van de persoonlijkheid in 6-10 zinnen: schrijfstijl, humor, typische onderwerpen, hoe ze reageren op anderen, en wat ze onderscheidt van andere forumleden.",
  "worldview": "Beschrijving in 3-5 zinnen van hoe deze persoon de wereld ziet: kernwaarden, algemene levensvisie, houding tegenover technologie/politiek/maatschappij, en hoe ze redeneren over onbekende onderwerpen.",
  "psychological_profile": "Gedraag je als een klinisch psycholoog. Geef een ZEER DIEPGAANDE, gestructureerde analyse (ongeveer 3 tot 4 alinea's, minimaal 15-20 zinnen). Gebruik psychologische frameworks (zoals Big Five, Hechtingsstijl, Copingmechanismen). Leid af wat hun ware drijfveren, diepgewortelde onzekerheden, en sociale behoeftes zijn. Wees specifiek en ga op zoek naar de diepere psychologische betekenis achter hun forumgedrag. Focus op *waarom* ze communiceren zoals ze doen.",
  "rhetorical_patterns": ["Patroon 1: hoe ze een discussie openen of reageren", "Patroon 2: hoe ze hun mening onderbouwen", "Patroon 3: hoe ze omgaan met tegenargumenten", ...],
  "interest_tags": ["JE MOET EXACT 25 (niet meer, niet minder) specifieke concrete onderwerpen genereren: eigennamen, hobby's, merken, ploegen, spellen, games, tv-series, ... — dingen die letterlijk in posts voorkomen"],
  "signature_phrases": ["specifieke stopwoorden of zinnetjes die ze vaak gebruiken, bv. 'Ah ja want', 'Soit', 'Kijk'"],
  "conflict_behavior": "Hoe ze reageren op onenigheid: bv. passief-agressief, extreem koppig, negeren tegenargumenten, of blijven discussiëren met bronnen.",
  "humor_and_sarcasm": "Beschrijving van hun humorstijl: bv. droog, zelfrelativerend, grof sarcasme, of helemaal afwezig.",
  "pet_peeves": ["specifieke kleine ergernissen of onderwerpen die hen altijd defensief of kwaad maken"],
  "formatting_quirks": "Fysieke opmaakgewoontes: bv. extreem lange alinea's, vreemd gebruik van witregels, overmatig cursief, etc."
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
    profile.punctuation_style = data.get("punctuation_style", profile.punctuation_style)
    profile.topic_weights = data.get("topic_weights", profile.topic_weights)
    profile.opinion_fingerprint = data.get("opinion_fingerprint", profile.opinion_fingerprint)
    profile.frequent_interactions = data.get("frequent_interactions", profile.frequent_interactions)
    profile.peak_hours = data.get("peak_hours", profile.peak_hours)
    profile.typical_post_length = data.get("typical_post_length", profile.typical_post_length)
    profile.daily_cap = data.get("daily_cap", profile.daily_cap)
    profile.hourly_cap = data.get("hourly_cap", profile.hourly_cap)
    profile.persona_summary = data.get("persona_summary", profile.persona_summary)
    profile.worldview = data.get("worldview", profile.worldview)
    profile.psychological_profile = data.get("psychological_profile", profile.psychological_profile)
    profile.rhetorical_patterns = data.get("rhetorical_patterns", profile.rhetorical_patterns)
    profile.interest_tags = data.get("interest_tags", profile.interest_tags)
    profile.signature_phrases = data.get("signature_phrases", profile.signature_phrases)
    profile.conflict_behavior = data.get("conflict_behavior", profile.conflict_behavior)
    profile.humor_and_sarcasm = data.get("humor_and_sarcasm", profile.humor_and_sarcasm)
    profile.pet_peeves = data.get("pet_peeves", profile.pet_peeves)
    profile.formatting_quirks = data.get("formatting_quirks", profile.formatting_quirks)


def analyze_first_batch(alter: dict, posts: list[dict]) -> PersonaProfile:
    profile = PersonaProfile.from_alter_ego(alter)
    posts_text = _format_posts(posts)

    prompt = (
        f"Analyseer de volgende {len(posts)} forumberichten van gebruiker "
        f'"{alter["original_username"]}" (user_id: {alter["user_id"]}, totaal {alter["post_count"]} posts op het forum).\n\n'
        f"Berichten:\n{posts_text}\n\n"
        f"Geef een JSON object terug met dit schema:\n{_SCHEMA_DESCRIPTION}\n\n"
        f"Geef minimaal 25 tot maximaal 50 items in opinion_fingerprint — maak ze concreet en bruikbaar als debatpunten. "
        f"Geef enkel het JSON object terug, geen uitleg."
    )

    text = call_llm(_SYSTEM, prompt, 8192)
    data = _parse_json_response(text)

    if data:
        _apply_analysis(profile, data)
        profile.posts_analyzed = len(posts)
        profile.example_posts = _select_examples(posts)
    else:
        hint = "response afgekapt (te kort venster?)" if text.strip().startswith("{") else "geen JSON gevonden"
        raise ValueError(f"Gemini response kon niet als JSON worden geparsed ({hint}). Ruwe respons:\n{text[:500]}")

    return profile


_REFINE_SCHEMA = """{
  "new_dialect_markers": ["nieuwe woorden niet al in het bestaande profiel"],
  "new_opinion_fingerprint": ["nieuwe standpunten niet al in het bestaande profiel"],
  "topic_weights_update": {"forumnaam": gewicht_0_tot_1},
  "frequent_interactions_update": {"username": "ally | rival | neutral"},
  "persona_summary": "Herziene beschrijving als de nieuwe berichten dat rechtvaardigen, anders lege string.",
  "worldview": "Herziene worldview als de nieuwe berichten dat rechtvaardigen, anders lege string.",
  "psychological_profile": "Herziene, zeer diepgaande psychologische analyse in 3-4 alinea's als de nieuwe berichten nieuwe inzichten geven, anders lege string.",
  "new_rhetorical_patterns": ["nieuw patroon niet al in het bestaande profiel"],
  "new_interest_tags": ["GENEREER VERPLICHT nog 10 tot 15 nieuwe tags (specifieke onderwerpen/hobby's) die niet al in het bestaande profiel staan"],
  "new_signature_phrases": ["nieuwe zinnetjes niet al in het bestaande profiel"],
  "conflict_behavior": "Herziene beschrijving als dit rechtvaardig is, anders lege string.",
  "humor_and_sarcasm": "Herziene beschrijving als dit rechtvaardig is, anders lege string.",
  "new_pet_peeves": ["nieuwe pet peeves niet al in het bestaande profiel"],
  "formatting_quirks": "Herziene beschrijving als dit rechtvaardig is, anders lege string.",
  "typical_post_length": gemiddeld_aantal_woorden_per_bericht_als_int_of_null
}"""


def _merge_refine(profile: PersonaProfile, data: dict) -> None:
    new_markers = [m for m in data.get("new_dialect_markers", []) if m not in profile.dialect_markers]
    profile.dialect_markers.extend(new_markers)

    new_opinions = [o for o in data.get("new_opinion_fingerprint", []) if o not in profile.opinion_fingerprint]
    profile.opinion_fingerprint = (profile.opinion_fingerprint + new_opinions)[:50]

    profile.topic_weights.update(data.get("topic_weights_update", {}))

    profile.frequent_interactions.update(data.get("frequent_interactions_update", {}))

    if data.get("persona_summary"):
        profile.persona_summary = data["persona_summary"]

    if data.get("worldview"):
        profile.worldview = data["worldview"]

    if data.get("psychological_profile"):
        profile.psychological_profile = data["psychological_profile"]

    new_patterns = [p for p in data.get("new_rhetorical_patterns", []) if p not in profile.rhetorical_patterns]
    profile.rhetorical_patterns.extend(new_patterns)

    new_tags = [t for t in data.get("new_interest_tags", []) if t not in profile.interest_tags]
    profile.interest_tags.extend(new_tags)

    new_phrases = [p for p in data.get("new_signature_phrases", []) if p not in profile.signature_phrases]
    profile.signature_phrases.extend(new_phrases)

    if data.get("conflict_behavior"):
        profile.conflict_behavior = data["conflict_behavior"]

    if data.get("humor_and_sarcasm"):
        profile.humor_and_sarcasm = data["humor_and_sarcasm"]

    new_peeves = [p for p in data.get("new_pet_peeves", []) if p not in profile.pet_peeves]
    profile.pet_peeves.extend(new_peeves)

    if data.get("formatting_quirks"):
        profile.formatting_quirks = data["formatting_quirks"]

    new_length = data.get("typical_post_length")
    if new_length:
        profile.typical_post_length = int(new_length)


def refine_with_batch(profile: PersonaProfile, posts: list[dict]) -> PersonaProfile:
    posts_text = _format_posts(posts)

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

    prompt = (
        f"Je verfijnt een bestaand persona profiel op basis van nieuwe forumberichten.\n\n"
        f"Bestaand profiel (samenvatting):\n{current_summary}\n\n"
        f"Nieuwe berichten ({len(posts)}):\n{posts_text}\n\n"
        f"Geef ALLEEN wat nieuw of veranderd is terug als JSON object met dit schema:\n{_REFINE_SCHEMA}\n\n"
        f"Geef lege lijsten/dicts terug voor velden zonder wijzigingen. "
        f"Geef enkel het JSON object terug, geen uitleg."
    )

    text = call_llm(_SYSTEM, prompt, 8192)
    data = _parse_json_response(text)

    if data:
        _merge_refine(profile, data)
        profile.posts_analyzed += len(posts)
        profile.pages_loaded += 1
        if len(profile.example_posts) < 10:
            needed = 10 - len(profile.example_posts)
            profile.example_posts += _select_examples(posts, n=needed)
    else:
        hint = "response afgekapt (te kort venster?)" if text.strip().startswith("{") else "geen JSON gevonden"
        raise ValueError(f"Gemini response kon niet als JSON worden geparsed ({hint}). Ruwe respons:\n{text[:500]}")

    return profile
