import re
import random
import logging
from datetime import datetime, timezone, timedelta

from src.persona.models import PersonaProfile
from src.event import db

_EXCLUDED_FORUM_IDS = {20, 29, 40, 42}
_RELEVANCE_THRESHOLD = 0.2
_MAX_RESPONDERS = 2
_MIN_CONTENT_WORDS = 5
_BBCODE_QUOTE_RE = re.compile(r"\[QUOTE[^\]]*\].*?\[/QUOTE\]", re.IGNORECASE | re.DOTALL)
_BBCODE_TAG_RE = re.compile(r"\[[^\]]*\]")


def detect_quoted_alters(post: dict, profiles: list[PersonaProfile]) -> set[str]:
    all_reversed = {p.reversed_username for p in profiles}
    if post.get("author", "") in all_reversed:
        return set()
    content = post.get("content", "").lower()
    quoted = set()
    for profile in profiles:
        marker = f"originally posted by {profile.reversed_username.lower()}"
        if marker in content:
            quoted.add(profile.reversed_username)
    return quoted


def evaluate_post(
    post: dict,
    profiles: list[PersonaProfile],
    conn,
) -> list[tuple[PersonaProfile, float]]:
    """Return up to 2 (profile, weight) pairs that should respond to this post.

    Weight reflects relevance — callers can use it for cross-post prioritisation.
    """
    all_reversed = {p.reversed_username for p in profiles}
    if post.get("author", "") in all_reversed:
        return []

    if post["forum_id"] in _EXCLUDED_FORUM_IDS:
        return []

    stripped = _BBCODE_QUOTE_RE.sub("", post.get("content", ""))
    stripped = _BBCODE_TAG_RE.sub("", stripped)
    if len(stripped.split()) < _MIN_CONTENT_WORDS:
        return []

    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y-%m-%dT%H")
    cutoff_hour_key = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H")
    forum_name = post.get("forum_name", "")
    content = post.get("content", "")

    passed: list[tuple[PersonaProfile, float]] = []

    for profile in profiles:
        if profile.reversed_username in post.get("quoted_alters", set()):
            weight = 1.0
        else:
            mentioned = profile.reversed_username.lower() in content.lower()
            tag_match = any(tag.lower() in content.lower() for tag in profile.interest_tags)

            if not mentioned and not tag_match:
                weight = profile.topic_weights.get(forum_name, 0.0)
                if weight < _RELEVANCE_THRESHOLD:
                    continue
                if random.random() >= weight:
                    continue
            else:
                weight = profile.topic_weights.get(forum_name, 1.0)

        hourly = db.get_hourly_count(conn, profile.reversed_username, hour_key)
        daily = db.get_daily_count(conn, profile.reversed_username, cutoff_hour_key)
        if hourly >= profile.hourly_cap or daily >= profile.daily_cap:
            logging.debug("Rate limit hit for %s", profile.reversed_username)
            continue

        passed.append((profile, weight))

    passed.sort(key=lambda x: x[1], reverse=True)
    return passed[:_MAX_RESPONDERS]
