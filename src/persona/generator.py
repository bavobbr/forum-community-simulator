from src.persona.models import PersonaProfile

_MODEL = "claude-sonnet-4-6"


def build_system_prompt(profile: PersonaProfile) -> str:
    examples = "\n".join(f"- {p}" for p in profile.example_posts[:15])
    dialect = ", ".join(profile.dialect_markers) if profile.dialect_markers else "geen specifieke markers"

    return (
        f"Je speelt de rol van '{profile.original_username}', een voormalig lid van een Nederlandstalig "
        f"gamerforum. Je schrijft ALTIJD in het Nederlands, in het specifieke register van deze persoon.\n\n"
        f"Persoonlijkheid: {profile.persona_summary}\n\n"
        f"Schrijfstijl:\n"
        f"- Formaliteit: {profile.formality}\n"
        f"- Zinslengte: {profile.sentence_length}\n"
        f"- Dialect/spreektaal: {dialect}\n"
        f"- Typische berichtlengte: {profile.typical_post_length}\n"
        f"- Interpunctie: {profile.punctuation_style}\n\n"
        f"Voorbeeldberichten van deze persoon:\n{examples}\n\n"
        f"Regels:\n"
        f"- Schrijf ALTIJD in het Nederlands\n"
        f"- Blijf in karakter — geen vierde muur doorbreken\n"
        f"- Verzin geen biografische feiten\n"
        f"- Je mag VBulletin BBCode gebruiken (b, i, quote, url) als het bij de stijl past\n"
        f"- Harde taal en banter zijn acceptabel als het past bij de persoon\n"
        f"- Reageer kort als de persoon kort schrijft, lang als de persoon lang schrijft"
    )


def generate_replies(client, profile: PersonaProfile, test_posts: list[dict]) -> list[dict]:
    system = build_system_prompt(profile)
    results = []

    for test_post in test_posts:
        user_content = (
            f"Iemand heeft het volgende gepost op het forum:\n\n"
            f"\"{test_post['post']}\"\n\n"
            f"Schrijf een reactie zoals {profile.original_username} dat zou doen."
        )
        try:
            response = client.messages.create(
                model=_MODEL,
                max_tokens=400,
                system=system,
                messages=[{"role": "user", "content": user_content}],
            )
            reply = response.content[0].text
            if response.stop_reason == "max_tokens":
                reply += " [afgekapt]"
        except Exception as exc:
            import logging
            logging.warning("generate_replies failed for post %r: %s", test_post.get("id"), exc)
            reply = "[generatie mislukt]"

        results.append({
            "id": test_post["id"],
            "label": test_post["label"],
            "post": test_post["post"],
            "reply": reply,
        })

    return results
