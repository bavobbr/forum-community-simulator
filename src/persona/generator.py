import logging
from src.llm import call_llm_raw, MODEL_FLASH
from src.persona.models import PersonaProfile


def build_system_prompt(profile: PersonaProfile) -> str:
    examples = "\n".join(f"- {p[:400]}" for p in profile.example_posts[:10])
    dialect = ", ".join(profile.dialect_markers) if profile.dialect_markers else "geen specifieke markers"
    opinions = "\n".join(f"- {o}" for o in profile.opinion_fingerprint) if profile.opinion_fingerprint else "- (geen)"
    patterns = "\n".join(f"- {p}" for p in profile.rhetorical_patterns) if profile.rhetorical_patterns else "- (geen)"

    return (
        f"Je speelt de rol van '{profile.original_username}', een voormalig lid van een Nederlandstalig "
        f"gamerforum. Je schrijft ALTIJD in het Nederlands, in het specifieke register van deze persoon.\n\n"
        f"## Persoonlijkheid\n"
        f"{profile.persona_summary}\n\n"
        f"## Wereldvisie\n"
        f"{profile.worldview or '(niet beschikbaar)'}\n\n"
        f"## Standpunten en meningen\n"
        f"Dit zijn concrete overtuigingen van deze persoon. Gebruik ze als je reageert op relevante onderwerpen:\n"
        f"{opinions}\n\n"
        f"## Retorische patronen\n"
        f"Zo argumenteert en communiceert deze persoon:\n"
        f"{patterns}\n\n"
        f"## Interesses\n"
        f"Concrete onderwerpen die deze persoon interesseren (gebruik dit om te bepalen of iets relevant is):\n"
        f"{', '.join(profile.interest_tags) if profile.interest_tags else '(niet beschikbaar)'}\n\n"
        f"## Schrijfstijl\n"
        f"- Formaliteit: {profile.formality}\n"
        f"- Zinslengte: {profile.sentence_length}\n"
        f"- Dialect/spreektaal: {dialect}\n"
        f"- Typische berichtlengte: ~{profile.typical_post_length} woorden\n"
        f"- Interpunctie: {profile.punctuation_style}\n\n"
        f"## Voorbeeldberichten\n"
        f"{examples}\n\n"
        f"## Regels\n"
        f"- Schrijf ALTIJD in het Nederlands\n"
        f"- Blijf in karakter — geen vierde muur doorbreken\n"
        f"- Verzin geen biografische feiten\n"
        f"- Bij een onbekend onderwerp: redeneer vanuit de wereldvisie en retorische patronen hierboven\n"
        f"- Je mag VBulletin BBCode gebruiken (b, i, quote, url) als het bij de stijl past\n"
        f"- Dit is een hechte community — mensen kennen elkaar en zijn over het algemeen betrokken en vriendelijk\n"
        f"- Banter en directe kritiek zijn ok waar ze écht bij de persoon passen, maar niet elke post verdient sarcasme\n"
        f"- Reageer ook welgemeend positief of enthousiast als de context dat vraagt\n"
        f"- Reageer kort als de persoon kort schrijft, lang als de persoon lang schrijft\n"
        f"- Voeg GEEN externe URLs of links toe — deze zijn vaak fout of dood"
    )


def generate_replies(profile: PersonaProfile, test_posts: list[dict]) -> list[dict]:
    system = build_system_prompt(profile)
    results = []

    for test_post in test_posts:
        user_content = (
            f"Forum: {test_post['forum']} | Thread: {test_post['thread_title']}\n\n"
            f"[Reageer op dit bericht:]\n"
            f"\"{test_post['post']}\"\n\n"
            f"Schrijf één forumreactie zoals {profile.reversed_username} dat zou doen. "
            f"Schrijf alleen de reactietekst zelf — geen uitleg, geen opmaak, geen opsomming. "
            f"Citeer de post NIET."
        )
        try:
            resp = call_llm_raw(system, user_content, 2048, model=MODEL_FLASH)
            reply = resp.text
            if resp.candidates[0].finish_reason.name == "MAX_TOKENS":
                reply += " [afgekapt]"
        except Exception as exc:
            logging.warning("generate_replies failed for post %r: %s", test_post.get("id"), exc)
            reply = "[generatie mislukt]"

        results.append({
            "id": test_post["id"],
            "label": test_post["label"],
            "post": test_post["post"],
            "reply": reply,
        })

    return results
