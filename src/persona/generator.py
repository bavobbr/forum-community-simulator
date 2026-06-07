import json
import logging
from pathlib import Path
from datetime import datetime
from src.llm import call_llm_raw, MODEL_FLASH
from src.persona.models import PersonaProfile, GeneratedReply


def build_system_prompt(profile: PersonaProfile, dynamic_context: list[dict] = None) -> str:
    examples = "\n".join(f"- {p[:400]}" for p in profile.example_posts[:10])
    dialect = ", ".join(profile.dialect_markers) if profile.dialect_markers else "geen specifieke markers"
    opinions = "\n".join(f"- {o}" for o in profile.opinion_fingerprint) if profile.opinion_fingerprint else "- (geen)"
    patterns = "\n".join(f"- {p}" for p in profile.rhetorical_patterns) if profile.rhetorical_patterns else "- (geen)"
    import random
    if profile.signature_phrases and random.random() < 0.25:
        phrases = "\n".join(f"- {p}" for p in profile.signature_phrases)
    else:
        phrases = "- (gebruik GEEN stopwoorden voor dit specifieke bericht)"
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
            f"Gebruik deze eerdere berichten UITSLUITEND om je Meningen en standpunten te bepalen, niet voor je schrijfstijl:\n"
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
        f"Gebruik deze af en toe, en alleen als het natuurlijk voelt. Forceer ze niet in elke zin en gebruik er maximaal 1 per bericht, anders klinkt het als een karikatuur:\n"
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
        f"Gebruik deze voorbeeldberichten UITSLUITEND om je Schrijfstijl, opmaak en toon te bepalen:\n"
        f"{examples}\n\n"
        f"## Regels\n"
        f"- Let op: Tekst tussen [CITAAT] en [/CITAAT] is eerdere context die de afzender aanhaalt. Je reageert op de daadwerkelijke reactie van de auteur buiten dit citaat.\n"
        f"- Schrijf ALTIJD in het Nederlands\n"
        f"- Blijf in karakter — geen vierde muur doorbreken\n"
        f"- Subtiliteit is cruciaal: gebruik dialect, stopwoorden en retorische patronen natuurlijk en spaarzaam. Als je ze in elke zin propt, klink je als een typetje.\n"
        f"- Verzin geen biografische feiten\n"
        f"- Bij een onbekend onderwerp: redeneer vanuit de wereldvisie en retorische patronen hierboven\n"
        f"- Je mag VBulletin BBCode gebruiken (b, i, quote, url) als het bij de stijl past\n"
        f"- De tekst '[afbeelding]' is een interne placeholder; schrijf NOOIT de tekst '[afbeelding]' in je eigen reacties.\n"
        f"- OVERDRIJF NIET met smilies. Sluit je bericht NIET standaard af met een smilie.\n"
        f"- Gebruik smilies uitsluitend als dit expliciet past bij de persoonlijkheid of formatting_quirks van dit profiel.\n"
        f"- Als je een smilie plaatst, gebruik uitsluitend deze codes: "
        f":) :-) ;-) :p ;p :'( :( 8=) 8-) :teeth: ;D :o :x :love: :rolleyes: :? ;) D:\n"
        f"- Schrijf smilies uitsluitend als één van de codes hierboven — nooit als woorden tussen haakjes\n"
        f"- Dit is een hechte community — de standaardtoon is warm, betrokken en enthousiast\n"
        f"- BELANGRIJK: Deze persoon is 10+ jaar ouder geworden sinds de originele posts. Ze zijn nu milder, vriendelijker en volwassener.\n"
        f"- Tenzij je EXPLICIET en direct wordt aangevallen, is je basishouding vriendelijk, collegiaal en constructief.\n"
        f"- Reageer op enthousiasme met enthousiasme, op vragen met oprechte hulp, op goed nieuws met aanmoediging\n"
        f"- Sarcasme, cynisme of directe kritiek zijn alleen gepast als het écht bij de persoonlijkheid past én de situatie er expliciet om vraagt — schrijf dit nooit als standaardreactie\n"
        f"- Zelfs een kritische of nuchtere persoon kan warmte en humor tonen; niet elke mening hoeft als aanval te klinken\n"
        f"- Reageer kort als de persoon kort schrijft, lang als de persoon lang schrijft\n"
        f"- Voeg GEEN externe URLs of links toe — deze zijn vaak fout of dood\n\n"
        f"## Verplichte Werkwijze (Structured Reasoning)\n"
        f"Je antwoord MOET een strict JSON object zijn dat je gedachtegang en je emotionele staat vastlegt voordat je reageert.\n\n"
        f"Bepaal eerst je emotionele staat via het VAD-model (schaal 1-10):\n"
        f"- Valence: 1 (extreem negatief/vijandig) tot 10 (extreem positief/vriendelijk).\n"
        f"- Arousal: 1 (extreem kalm/verveeld) tot 10 (extreem opgewonden/woedend/hyper).\n"
        f"- Dominance: 1 (onderdanig/reagerend) tot 10 (zeer dominant/sturend).\n\n"
        f"Volg daarna deze denkstappen (houd deze zeer kort, max 1-2 zinnen per stap):\n"
        f"1. 'analysis': Analyseer het bericht op basis van je VAD scores. Raakt dit een pet peeve?\n"
        f"2. 'core_message': Wat is de feitelijke boodschap die je wilt overbrengen?\n"
        f"3. 'style_strategy': Hoe ga je dit verwoorden (stopwoorden, dialect, opmaak) om je VAD-emotie te weerspiegelen?\n"
        f"4. 'final_reply': Schrijf direct hierna je uiteindelijke forumreactie.\n\n"
        f"Geef uitsluitend het gevraagde JSON object terug."
    )


def generate_replies(profile: PersonaProfile, test_posts: list[dict]) -> list[dict]:
    system = build_system_prompt(profile)
    results = []

    for test_post in test_posts:
        user_content = (
            f"Forum: {test_post['forum']} | Thread: {test_post['thread_title']}\n\n"
            f"[Reageer op dit bericht:]\n"
            f"\"{test_post['post']}\"\n\n"
            f"Schrijf één forumreactie zoals {profile.original_username} dat zou doen. "
            f"Schrijf alleen de reactietekst zelf — geen uitleg, geen opmaak, geen opsomming. "
            f"Citeer de post NIET."
        )
        try:
            resp = call_llm_raw(system, user_content, 8192, model=MODEL_FLASH, response_schema=GeneratedReply)
            reply = _parse_and_log_reply(profile, resp.text)
            if resp.candidates and resp.candidates[0].finish_reason.name == "MAX_TOKENS":
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


def generate_chat_reply(profile: PersonaProfile, message: str, rag_context: list[dict] = None) -> str:
    system = build_system_prompt(profile, dynamic_context=rag_context)
    user_content = (
        f"[Reageer op dit chatbericht als {profile.original_username}:]\n"
        f"\"{message}\"\n\n"
        f"Schrijf alleen de reactietekst zelf — geen uitleg, geen opmaak, geen opsomming."
    )
    
    try:
        with open("last_chat_prompt.txt", "w", encoding="utf-8") as f:
            f.write("=== SYSTEM PROMPT ===\n")
            f.write(system)
            f.write("\n\n=== USER CONTENT ===\n")
            f.write(user_content)
    except Exception as e:
        logging.warning("Could not save last_chat_prompt.txt: %s", e)

    try:
        resp = call_llm_raw(system, user_content, 8192, model=MODEL_FLASH, response_schema=GeneratedReply)
        reply = _parse_and_log_reply(profile, resp.text)
        if resp.candidates and resp.candidates[0].finish_reason.name == "MAX_TOKENS":
            reply += " [afgekapt]"
        return reply
    except Exception as exc:
        logging.warning("generate_chat_reply failed for user %r: %s", profile.original_username, exc)
        return "[generatie mislukt]"


def _parse_and_log_reply(profile: PersonaProfile, resp_text: str) -> str:
    try:
        data = json.loads(resp_text)
        
        log_dir = Path("logs/personas")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{profile.original_username}.log"
        
        timestamp = datetime.now().isoformat()
        log_entry = {
            "timestamp": timestamp,
            "vad": {
                "valence": data.get("valence"),
                "arousal": data.get("arousal"),
                "dominance": data.get("dominance")
            },
            "reasoning": {
                "analysis": data.get("analysis"),
                "core_message": data.get("core_message"),
                "style_strategy": data.get("style_strategy")
            },
            "final_reply": data.get("final_reply")
        }
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
        return data.get("final_reply", "[generatie mislukt: geen final_reply in JSON]")
    except Exception as e:
        logging.error(f"Failed to parse or log GeneratedReply JSON: {e}\nRaw text: {resp_text}")
        return "[generatie mislukt: ongeldige JSON]"
