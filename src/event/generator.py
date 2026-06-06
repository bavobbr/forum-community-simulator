from src.llm import call_llm_raw
from src.persona.models import PersonaProfile
from src.persona.generator import build_system_prompt
from src.rag.db import search_posts


def generate_reply(
    profile: PersonaProfile,
    triggering_post: dict,
    context_posts: list[dict],
) -> str:
    """Generate a reply to triggering_post using context_posts as thread context."""
    dynamic_context = search_posts(profile.original_username, triggering_post["content"])
    system = build_system_prompt(profile, dynamic_context)

    context_lines = "\n".join(
        f"{p['author']}: {p['content']}"
        for p in context_posts
        if p["post_id"] != triggering_post["post_id"]
    )

    forum = triggering_post.get("forum_name", "")
    thread = triggering_post.get("thread_title", "")

    user_content = (
        f"Forum: {forum} | Thread: {thread}\n\n"
        f"[Vorige berichten in de thread:]\n{context_lines}\n\n"
        f"[Reageer op dit bericht van {triggering_post['author']}:]\n"
        f"\"{triggering_post['content']}\"\n\n"
        f"Schrijf één forumreactie zoals {profile.reversed_username} dat zou doen. "
        f"Schrijf alleen de reactietekst zelf — geen uitleg, geen opmaak, geen opsomming. "
        f"Citeer de post NIET."
    )

    resp = call_llm_raw(system, user_content, 2048)
    reply = resp.text
    if resp.candidates[0].finish_reason.name == "MAX_TOKENS":
        reply += " [afgekapt]"
    return reply


def generate_quote_reply(profile: PersonaProfile, triggering_post: dict) -> str:
    """Generate a direct reply to a post that quoted this alter ego. No thread context."""
    dynamic_context = search_posts(profile.original_username, triggering_post["content"])
    system = build_system_prompt(profile, dynamic_context)

    user_content = (
        f"Iemand heeft jou geciteerd en reageert direct op jou. Reageer terug op dit specifieke bericht:\n\n"
        f"[Bericht van {triggering_post['author']}:]\n"
        f"\"{triggering_post['content']}\"\n\n"
        f"Schrijf één forumreactie zoals {profile.reversed_username} dat zou doen. "
        f"Schrijf alleen de reactietekst zelf — geen uitleg, geen opmaak, geen opsomming. "
        f"Citeer de post NIET."
    )

    resp = call_llm_raw(system, user_content, 2048)
    reply = resp.text
    if resp.candidates[0].finish_reason.name == "MAX_TOKENS":
        reply += " [afgekapt]"
    return reply
