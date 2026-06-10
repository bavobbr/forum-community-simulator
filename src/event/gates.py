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
_BBCODE_QUOTE_RE = re.compile(r"\[(?:QUOTE|CITAAT)[^\]]*\].*?\[/(?:QUOTE|CITAAT)\]", re.IGNORECASE | re.DOTALL)
_BBCODE_TAG_RE = re.compile(r"\[[^\]]*\]")


def _passes_rate_cap(profile: PersonaProfile, conn) -> bool:
    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y-%m-%dT%H")
    cutoff_hour_key = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H")
    hourly = db.get_hourly_count(conn, profile.reversed_username, hour_key)
    daily = db.get_daily_count(conn, profile.reversed_username, cutoff_hour_key)
    return hourly < profile.hourly_cap and daily < profile.daily_cap


def is_meaningful(post: dict) -> bool:
    stripped = _BBCODE_QUOTE_RE.sub("", post.get("content", ""))
    stripped = _BBCODE_TAG_RE.sub("", stripped)
    return len(stripped.split()) >= _MIN_CONTENT_WORDS


def get_triggered_profiles(post: dict, profiles: list[PersonaProfile]) -> list[PersonaProfile]:
    all_reversed = {p.reversed_username for p in profiles}
    if post.get("author", "") in all_reversed:
        return []
    content_lower = post.get("content", "").lower()
    triggered = []
    for profile in profiles:
        rev = profile.reversed_username.lower()
        orig = profile.original_username.lower()
        marker = f"originally posted by {rev}"
        if (rev in content_lower
                or orig in content_lower
                or f"[quote={rev}" in content_lower
                or f"[quote={orig}" in content_lower
                or marker in content_lower):
            triggered.append(profile)
    return triggered


def evaluate_post_random(
    post: dict,
    available_profiles: list[PersonaProfile],
    conn,
) -> list[tuple[PersonaProfile, float]]:
    """Return up to 2 (profile, weight) pairs that should respond to this post from the available pool."""
    all_reversed = {p.reversed_username for p in available_profiles}
    if post.get("author", "") in all_reversed:
        return []

    if post["forum_id"] in _EXCLUDED_FORUM_IDS:
        return []

    if not is_meaningful(post):
        return []

    forum_name = post.get("forum_name", "")
    content = post.get("content", "")

    passed: list[tuple[PersonaProfile, float]] = []

    for profile in available_profiles:
        tag_match = any(tag.lower() in content.lower() for tag in profile.interest_tags)

        if not tag_match:
            weight = profile.topic_weights.get(forum_name, 0.0)
            if weight < _RELEVANCE_THRESHOLD:
                continue
            if random.random() >= weight:
                continue
        else:
            weight = profile.topic_weights.get(forum_name, 1.0)

        if not _passes_rate_cap(profile, conn):
            logging.debug("Rate limit hit for %s", profile.reversed_username)
            continue

        passed.append((profile, weight))

    passed.sort(key=lambda x: x[1], reverse=True)
    return passed[:_MAX_RESPONDERS]
