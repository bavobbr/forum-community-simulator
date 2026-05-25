import random
import logging
from datetime import datetime, timezone

from src.persona.models import PersonaProfile
from src.event import db

_EXCLUDED_FORUM_IDS = {20, 29, 40, 42}
_RELEVANCE_THRESHOLD = 0.2
_MAX_RESPONDERS = 2


def evaluate_post(
    post: dict,
    profiles: list[PersonaProfile],
    conn,
) -> list[PersonaProfile]:
    """Return up to 2 profiles that should respond to this post."""
    if post["forum_id"] in _EXCLUDED_FORUM_IDS:
        return []

    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y-%m-%dT%H")
    day_key = now.strftime("%Y-%m-%d")
    forum_name = post.get("forum_name", "")
    content = post.get("content", "")

    passed: list[tuple[PersonaProfile, float]] = []

    for profile in profiles:
        mentioned = profile.reversed_username.lower() in content.lower()

        if not mentioned:
            weight = profile.topic_weights.get(forum_name, 0.0)
            if weight < _RELEVANCE_THRESHOLD:
                continue
            if random.random() >= weight:
                continue
        else:
            weight = profile.topic_weights.get(forum_name, 1.0)

        hourly = db.get_hourly_count(conn, profile.reversed_username, hour_key)
        daily = db.get_daily_count(conn, profile.reversed_username, day_key)
        if hourly >= profile.hourly_cap or daily >= profile.daily_cap:
            logging.debug("Rate limit hit for %s", profile.reversed_username)
            continue

        passed.append((profile, weight))

    passed.sort(key=lambda x: x[1], reverse=True)
    return [p for p, _ in passed[:_MAX_RESPONDERS]]
