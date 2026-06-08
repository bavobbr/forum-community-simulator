import random
import sqlite3

from src.persona.models import PersonaProfile
from src.event.gates import _passes_rate_cap, is_meaningful

_MAX_TRIGGERED = 3


def _find_triggered(post: dict, profiles: list[PersonaProfile]) -> list[PersonaProfile]:
    content_lower = post.get("content", "").lower()
    triggered = []
    for profile in profiles:
        rev = profile.reversed_username.lower()
        orig = profile.original_username.lower()
        if (rev in content_lower
                or orig in content_lower
                or f"[quote={rev}" in content_lower
                or f"[quote={orig}" in content_lower):
            triggered.append(profile)
    return triggered


def evaluate_post_sandbox(
    post: dict,
    profiles: list[PersonaProfile],
    conn: sqlite3.Connection,
    replies_per_post: int = 3,
) -> list[tuple[PersonaProfile, float]]:
    all_reversed = {p.reversed_username for p in profiles}
    if post.get("author", "") in all_reversed:
        return []
        
    triggered = _find_triggered(post, profiles)
    if triggered:
        return [(p, 1.0) for p in triggered[:_MAX_TRIGGERED]]

    if not is_meaningful(post):
        return []

    eligible = [p for p in profiles if _passes_rate_cap(p, conn)]
    sample = random.sample(eligible, min(replies_per_post, len(eligible)))
    return [(p, 1.0) for p in sample]
