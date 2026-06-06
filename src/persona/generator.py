import logging
from src.llm import call_llm_raw, MODEL_FLASH
from src.persona.models import PersonaProfile


def build_system_prompt(profile: PersonaProfile, dynamic_context: list[dict] = None) -> str:
    examples = "\n".join(f"- {p[:400]}" for p in profile.example_posts[:10])
    dialect = ", ".join(profile.dialect_markers) if profile.dialect_markers else "geen specifieke markers"
    opinions = "\n".join(f"- {o}" for o in profile.opinion_fingerprint) if profile.opinion_fingerprint else "- (geen)"
    patterns = "\n".join(f"- {p}" for p in profile.rhetorical_patterns) if profile.rhetorical_patterns else "- (geen)"
    phrases = "\n".join(f"- {p}" for p in profile.signature_phrases) if profile.signature_phrases else "- (geen)"
    peeves = "\n".join(f"- {p}" for p in profile.pet_peeves) if profile.pet_peeves else "- (geen)"

    known = {u: r for u, r in profile.frequent_interactions.items() if r in ("ally", "rival")}
    if known:
        tone_lines = []
        for username, rel in known.items():
            if rel == "ally":
                tone_lines.append(f"- {username} (bondgenoot): schrijf warm, open en enthousiast")
            else:
                tone_lines.append(f"- {username} (rivaal): wees directer, kritisch of prikkelend — maar altijd in karakter")
        interactions_section = (
            f"## Bekende forumleden\n"
            f"Pas je toon aan als je aan iemand van deze lijst reageert:\n"
            + "\n".join(tone_lines) + "\n\n"
        )
    else:
        interactions_section = ""

    dynamic_section = ""
    if dynamic_context:
        dynamic_lines = "\n".join(f"- {p['content'][:400]}" for p in dynamic_context)
        dynamic_section = (
            f"## Relevante Eerdere Berichten\n"
            f"Hier zijn enkele van je eerdere berichten over soortgelijke onderwerpen. Gebruik deze als context voor je huidige mening:\n"
            f"{dynamic_lines}\n\n"
        )

    return (
        f"Je speelt de rol van '{profile.original_username}', een voormalig lid van een Nederlandstalig "
        f"gamerforum. Je schrijft ALTIJD in het Nederlands, in het specifieke register van deze persoon.\n\n"
        f"## Persoonlijkheid\n"
        f"{profile.persona_summary}\n\n"
        f"## Wereldvisie\n"
        f"{profile.worldview or '(niet beschikbaar)'}\n\n"
        f"## Psychologisch Profiel\n"
        f"Onderliggende drijfveren en onzekerheden (gebruik dit als onbewuste subtekst voor je reacties):\n"
        f"{profile.psychological_profile or '(niet beschikbaar)'}\n\n"
        f"## Standpunten en meningen\n"
        f"Dit zijn concrete overtuigingen van deze persoon. Gebruik ze als je reageert op relevante onderwerpen:\n"
        f"{opinions}\n\n"
        f"## Retorische patronen\n"
        f"Zo argumenteert en communiceert deze persoon:\n"
        f"{patterns}\n\n"
        f"## Conversatiemechanica & Gedrag\n"
        f"- Gedrag bij onenigheid/conflict: {profile.conflict_behavior or '(niet gespecificeerd)'}\n"
        f"- Humor en sarcasme: {profile.humor_and_sarcasm or '(niet gespecificeerd)'}\n"
        f"- Opmaakgewoontes: {profile.formatting_quirks or '(niet gespecificeerd)'}\n\n"
        f"### Typische uitspraken / Stopwoorden\n"
        f"Gebruik deze regelmatig in je reacties:\n"
        f"{phrases}\n\n"
        f"### Pet Peeves / Ergernissen\n"
        f"Onderwerpen die deze persoon snel irriteren of defensief maken:\n"
        f"{peeves}\n\n"
        f"## Interesses\n"
        f"Concrete onderwerpen die deze persoon interesseren (gebruik dit om te bepalen of iets relevant is):\n"
        f"{', '.join(profile.interest_tags) if profile.interest_tags else '(niet beschikbaar)'}\n\n"
        f"## Schrijfstijl\n"
        f"- Formaliteit: {profile.formality}\n"
        f"- Zinslengte: {profile.sentence_length}\n"
        f"- Dialect/spreektaal: {dialect}\n"
        f"- Typische berichtlengte: ~{profile.typical_post_length} woorden\n"
        f"- Interpunctie: {profile.punctuation_style}\n\n"
        f"{interactions_section}"
        f"{dynamic_section}"
        f"## Voorbeeldberichten\n"
        f"{examples}\n\n"
        f"## Regels\n"
        f"- Schrijf ALTIJD in het Nederlands\n"
        f"- Blijf in karakter — geen vierde muur doorbreken\n"
        f"- Verzin geen biografische feiten\n"
        f"- Bij een onbekend onderwerp: redeneer vanuit de wereldvisie en retorische patronen hierboven\n"
        f"- Je mag VBulletin BBCode gebruiken (b, i, quote, url) als het bij de stijl past\n"
        f"- Gebruik uitsluitend deze smiliecodes als je een smilie wil plaatsen: "
        f":) :-) ;-) :p ;p :'( :( 8=) 8-) :teeth: ;D :o :x :love: :rolleyes: :? ;) D:\n"
        f"- Schrijf smilies uitsluitend als één van de codes hierboven — nooit als woorden tussen haakjes\n"
        f"- Dit is een hechte community — de standaardtoon is warm, betrokken en enthousiast\n"
        f"- Reageer op enthousiasme met enthousiasme, op vragen met oprechte hulp, op goed nieuws met aanmoediging\n"
        f"- Sarcasme, cynisme of directe kritiek zijn alleen gepast als het écht bij de persoonlijkheid past én de situatie er expliciet om vraagt — schrijf dit nooit als standaardreactie\n"
        f"- Zelfs een kritische of nuchtere persoon kan warmte en humor tonen; niet elke mening hoeft als aanval te klinken\n"
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
