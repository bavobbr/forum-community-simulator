import logging
from src.persona.models import PersonaProfile
from src.persona.generator import build_system_prompt

_MODEL = "claude-sonnet-4-6"


def generate_reply(
    client,
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

    response = client.messages.create(
        model=_MODEL,
        max_tokens=400,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    reply = response.content[0].text
    if response.stop_reason == "max_tokens":
        reply += " [afgekapt]"
    return reply
