import random
import sqlite3

from src.persona.models import PersonaProfile
from src.event.gates import _passes_rate_cap, is_meaningful




def evaluate_post_sandbox_random(
    post: dict,
    available_profiles: list[PersonaProfile],
    conn: sqlite3.Connection,
    replies_per_post: int = 3,
) -> list[tuple[PersonaProfile, float]]:
    all_reversed = {p.reversed_username for p in available_profiles}
    if post.get("author", "") in all_reversed:
        return []

    if not is_meaningful(post):
        return []

    eligible = [p for p in available_profiles if _passes_rate_cap(p, conn)]
    sample = random.sample(eligible, min(replies_per_post, len(eligible)))
    return [(p, 1.0) for p in sample]
