from src.llm import call_llm_raw
from src.persona.models import PersonaProfile
from src.persona.generator import build_system_prompt


def generate_reply(
    profile: PersonaProfile,
    triggering_post: dict,
    context_posts: list[dict],
) -> str:
    """Generate a reply to triggering_post using context_posts as thread context."""
    system = build_system_prompt(profile)

    context_lines = "\n".join(
        f"{p['author']}: {p['content']}"
        for p in context_posts
        if p["post_id"] != triggering_post["post_id"]
    )

    user_content = (
        f"[Vorige berichten in de thread:]\n{context_lines}\n\n"
        f"[Nieuw bericht van {triggering_post['author']}:]\n"
        f"\"{triggering_post['content']}\"\n\n"
        f"Schrijf een reactie zoals {profile.reversed_username} dat zou doen."
    )

    resp = call_llm_raw(system, user_content, 400)
    reply = resp.text
    if resp.candidates[0].finish_reason.name == "MAX_TOKENS":
        reply += " [afgekapt]"
    return reply
