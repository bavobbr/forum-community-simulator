import json
import logging
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from src.event import db, gates, thread_scraper
from src.event import generator as event_generator
from src.event.poller import fetch_new_posts, parse_post_date
from src.event.webui import create_app, _do_approve
from src.persona.models import PersonaProfile
from src.session import VBulletinSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _load_profiles(personas_dir: str) -> list[PersonaProfile]:
    profiles = []
    for path in Path(personas_dir).glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            profile = PersonaProfile.from_dict(data)
            if profile.is_approved:
                profiles.append(profile)
        except Exception as exc:
            logging.warning("Could not load %s: %s", path, exc)
    return profiles


def _is_image_only(content: str) -> bool:
    return not content.replace("[afbeelding]", "").strip()


def _poll_once(scanner, profiles, conn, alter_password, live_mode, cutoff,
               auto_approve_minutes, replies_per_cycle):
    try:
        new_posts = fetch_new_posts(scanner)
    except Exception as exc:
        logging.error("Poll failed: %s", exc)
        return

    # Phase 1: evaluate all unseen posts, collect (post, profile, weight) candidates
    candidates: list[tuple[dict, PersonaProfile, float]] = []
    evaluated_posts: list[dict] = []

    for post in new_posts:
        if db.is_seen(conn, post["post_id"]):
            continue

        post_dt = parse_post_date(post.get("date", ""))
        if post_dt and post_dt < cutoff:
            db.mark_seen(conn, post["post_id"], post["thread_id"], post["forum_id"])
            continue

        evaluated_posts.append(post)

        if _is_image_only(post.get("content", "")):
            continue

        post["quoted_alters"] = gates.detect_quoted_alters(post, profiles)
        for profile, weight in gates.evaluate_post(post, profiles, conn):
            candidates.append((post, profile, weight))

    # Phase 2: pick the top N most relevant candidates for this cycle
    candidates.sort(key=lambda x: x[2], reverse=True)
    selected = candidates[:replies_per_cycle]
    logging.info(
        "Cycle: %d new posts, %d candidates, %d selected (cap=%d)",
        len(evaluated_posts), len(candidates), len(selected), replies_per_cycle,
    )

    # Phase 3: generate and queue replies for selected candidates only
    for post, profile, _ in selected:
        is_quote_reply = profile.reversed_username in post.get("quoted_alters", set())

        if is_quote_reply:
            try:
                llm_reply = event_generator.generate_quote_reply(profile, post)
            except Exception as exc:
                logging.warning("Quote-reply generation failed for post %d / %s: %s",
                                post["post_id"], profile.reversed_username, exc)
                continue
            quote_block = (
                f"[QUOTE={post['author']};{post['post_id']}]"
                f"{post.get('content', '')}"
                f"[/QUOTE]\n"
            )
            reply_text = quote_block + llm_reply
        else:
            try:
                context = thread_scraper.fetch_thread_context(scanner, post["post_id"])
            except Exception as exc:
                logging.warning("Context fetch failed for post %d: %s", post["post_id"], exc)
                context = []

            triggering = next(
                (p for p in context if p["post_id"] == post["post_id"]),
                {"post_id": post["post_id"], "author": "?", "content": post.get("content", "")},
            )

            try:
                reply_text = event_generator.generate_reply(profile, triggering, context)
            except Exception as exc:
                logging.warning("Generation failed for post %d / %s: %s",
                                post["post_id"], profile.reversed_username, exc)
                continue

        auto_approve_at = (
            datetime.now(timezone.utc) + timedelta(minutes=auto_approve_minutes)
        ).isoformat()

        db.insert_pending(
            conn, post["post_id"], post["thread_id"], post["forum_id"],
            profile.reversed_username, reply_text, auto_approve_at,
        )
        logging.info("Queued reply from %s for post %d", profile.reversed_username, post["post_id"])

    # Phase 4: mark all evaluated posts as seen so they are not reprocessed
    for post in evaluated_posts:
        db.mark_seen(conn, post["post_id"], post["thread_id"], post["forum_id"])


def main():
    required_vars = ["GOOGLE_API_KEY", "FORUM_USERNAME", "FORUM_PASSWORD", "ALTER_PASSWORD", "FORUM_URL"]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        raise SystemExit(f"Missing env vars: {', '.join(missing)}")

    live_mode = os.getenv("LIVE_MODE", "false").lower() == "true"
    lookback_hours = int(os.getenv("LOOKBACK_HOURS", "48"))
    poll_interval = int(os.getenv("POLL_INTERVAL", "300"))
    auto_approve_minutes = int(os.getenv("AUTO_APPROVE_MINUTES", "10"))
    replies_per_cycle = int(os.getenv("REPLIES_PER_CYCLE", "3"))
    alter_password = os.getenv("ALTER_PASSWORD")

    profiles = _load_profiles("personas")
    if not profiles:
        raise SystemExit("No approved personas found in personas/")
    logging.info("Loaded %d approved personas", len(profiles))

    conn = db.init_db("event.db")

    scanner = VBulletinSession()
    if not scanner.login(os.getenv("FORUM_USERNAME"), os.getenv("FORUM_PASSWORD")):
        raise SystemExit("Scanner login failed")
    logging.info("Scanner logged in")

    app = create_app(conn, profiles, alter_password, live_mode)
    flask_thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False),
        daemon=True,
    )
    flask_thread.start()
    logging.info("Review queue: http://localhost:5000 [%s]", "LIVE" if live_mode else "SIMULATIE")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    logging.info("Processing posts newer than %s (LOOKBACK_HOURS=%d)", cutoff.isoformat(), lookback_hours)

    while True:
        _poll_once(scanner, profiles, conn, alter_password, live_mode, cutoff,
                   auto_approve_minutes, replies_per_cycle)

        for entry in db.get_pending_auto_approve(conn):
            logging.info("Auto-approving reply %d for %s", entry["id"], entry["alter_username"])
            _do_approve(conn, dict(entry), alter_password, live_mode)

        time.sleep(poll_interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Shutting down")
