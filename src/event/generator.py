from src.llm import call_llm_raw
from src.persona.generator import build_system_prompt, _parse_and_log_reply, clean_legacy_quotes
from src.rag.db import search_posts
from src.persona.models import PersonaProfile, GeneratedReply


def generate_reply(
    profile: PersonaProfile,
    triggering_post: dict,
    context_posts: list[dict],
) -> str:
    """Generate a reply to triggering_post using context_posts as thread context."""
    dynamic_context = search_posts(profile.original_username, triggering_post["content"])
    system = build_system_prompt(profile, dynamic_context)

    context_blocks = []
    for p in context_posts:
        if p["post_id"] == triggering_post["post_id"]:
            continue
        # Clean up legacy RAG database formatting dynamically
        content = clean_legacy_quotes(p['content'])
        context_blocks.append(f"--- Bericht van {p['author']} ---\n{content}")
    
    context_lines = "\n\n".join(context_blocks)

    context_section = ""
    if context_lines:
        context_section = (
            f"[Vorige berichten in de thread:]\n{context_lines}\n\n"
            f"LET OP: Lees de context hierboven zorgvuldig. Controleer wat andere gebruikers én jijzelf ({profile.reversed_username}) al hebben gezegd. Herhaal GEEN eerdere punten of opmerkingen. Voeg een NIEUWE gedachte toe aan het gesprek.\n\n"
        )

    forum = triggering_post.get("forum_name", "")
    thread = triggering_post.get("thread_title", "")

    user_content = (
        f"Forum: {forum} | Thread: {thread}\n\n"
        f"{context_section}"
        f"--- NIEUWE REACTIE OM OP TE REAGEREN ---\n"
        f"Bericht van: {triggering_post['author']}\n"
        f"Inhoud:\n"
        f"{clean_legacy_quotes(triggering_post['content'])}\n"
        f"----------------------------------------\n\n"
        f"Schrijf één forumreactie zoals {profile.reversed_username} dat zou doen. "
        f"Schrijf alleen de reactietekst zelf — geen uitleg, geen opmaak, geen opsomming. "
        f"Citeer de post NIET."
    )

    try:
        import logging
        with open("last_event_prompt.txt", "w", encoding="utf-8") as f:
            f.write("=== SYSTEM PROMPT ===\n")
            f.write(system)
            f.write("\n\n=== USER CONTENT ===\n")
            f.write(user_content)
    except Exception as e:
        logging.warning("Could not save last_event_prompt.txt: %s", e)

    resp = call_llm_raw(system, user_content, 8192, response_schema=GeneratedReply)
    reply = _parse_and_log_reply(profile, resp.text)
    if resp.candidates and resp.candidates[0].finish_reason.name == "MAX_TOKENS":
        reply += " [afgekapt]"
    return reply


def generate_quote_reply(profile: PersonaProfile, triggering_post: dict) -> str:
    """Generate a direct reply to a post that quoted this alter ego. No thread context."""
    dynamic_context = search_posts(profile.original_username, triggering_post["content"])
    system = build_system_prompt(profile, dynamic_context)

    user_content = (
        f"Iemand heeft jou geciteerd en reageert direct op jou. Reageer terug op dit specifieke bericht:\n\n"
        f"--- NIEUWE REACTIE OM OP TE REAGEREN ---\n"
        f"Bericht van: {triggering_post['author']}\n"
        f"Inhoud:\n"
        f"{clean_legacy_quotes(triggering_post['content'])}\n"
        f"----------------------------------------\n\n"
        f"Schrijf één forumreactie zoals {profile.reversed_username} dat zou doen. "
        f"Schrijf alleen de reactietekst zelf — geen uitleg, geen opmaak, geen opsomming. "
        f"Citeer de post NIET."
    )

    resp = call_llm_raw(system, user_content, 8192, response_schema=GeneratedReply)
    reply = _parse_and_log_reply(profile, resp.text)
    if resp.candidates and resp.candidates[0].finish_reason.name == "MAX_TOKENS":
        reply += " [afgekapt]"
    return reply
