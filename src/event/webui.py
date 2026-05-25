import logging
import os
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template_string

from src.event import db
from src.event import thread_scraper
from src.event import generator as event_generator
from src.event import poster
from src.session import VBulletinSession

_QUEUE_TEMPLATE = """<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="utf-8">
<title>Shrimp Resurrect — Review Queue</title>
<style>
  body { font-family: monospace; max-width: 900px; margin: 40px auto; padding: 0 20px; background: #1a1a1a; color: #ccc; }
  h1 { color: #fff; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 0.8em; }
  .badge-live { background: #c0392b; color: #fff; }
  .badge-sim  { background: #2980b9; color: #fff; }
  .card { border: 1px solid #444; margin: 16px 0; padding: 16px; background: #252525; }
  .card h3 { margin: 0 0 8px; color: #fff; }
  .post-excerpt { background: #333; padding: 8px; margin: 8px 0; color: #aaa; }
  .generated-text { background: #1e3a1e; padding: 8px; margin: 8px 0; color: #9f9; white-space: pre-wrap; }
  .actions { margin-top: 10px; }
  button { margin-right: 8px; padding: 6px 14px; cursor: pointer; }
  textarea { width: 100%; height: 80px; background: #333; color: #ccc; border: 1px solid #555; padding: 6px; }
  .edit-area { display: none; margin-top: 8px; }
  .empty { color: #888; padding: 20px; text-align: center; }
</style>
</head>
<body>
<h1>Shrimp Resurrect
  <span class="badge {% if live_mode %}badge-live{% else %}badge-sim{% endif %}">
    {% if live_mode %}LIVE{% else %}SIMULATIE{% endif %}
  </span>
</h1>
<p><a href="/status" style="color:#888">status JSON</a></p>
{% if not replies %}
  <p class="empty">Geen wachtende reacties.</p>
{% endif %}
{% for r in replies %}
<div class="card">
  <h3>
    <a href="{{ forum_url }}/showthread.php?t={{ r['thread_id'] }}" target="_blank" style="color:#fff">
      Thread #{{ r['thread_id'] }}
    </a>
    &nbsp;&mdash;&nbsp;<strong>{{ r['alter_username'] }}</strong>
    {% if r['auto_approve_at'] %}<small style="color:#888">(auto: {{ r['auto_approve_at'][:16] }})</small>{% endif %}
  </h3>
  <div class="post-excerpt">post #{{ r['post_id'] }}</div>
  <div class="generated-text">{{ r['reply_text'] }}</div>
  <div class="actions">
    <form method="post" action="/reply/{{ r['id'] }}/approve" style="display:inline">
      <button type="submit" style="background:#27ae60;color:#fff">✓ Goedkeuren</button>
    </form>
    <button onclick="toggleEdit({{ r['id'] }})" style="background:#2980b9;color:#fff">✎ Bewerken</button>
    <form method="post" action="/reply/{{ r['id'] }}/discard" style="display:inline">
      <button type="submit" style="background:#c0392b;color:#fff">✗ Verwijderen</button>
    </form>
    <form method="post" action="/reply/{{ r['id'] }}/regenerate" style="display:inline">
      <button type="submit" style="background:#8e44ad;color:#fff">↺ Opnieuw genereren</button>
    </form>
  </div>
  <div class="edit-area" id="edit-{{ r['id'] }}">
    <form method="post" action="/reply/{{ r['id'] }}/edit">
      <textarea name="reply_text">{{ r['reply_text'] }}</textarea>
      <button type="submit" style="background:#27ae60;color:#fff;margin-top:6px">Opslaan &amp; Goedkeuren</button>
    </form>
  </div>
</div>
{% endfor %}
<script>
function toggleEdit(id) {
  var el = document.getElementById('edit-' + id);
  el.style.display = el.style.display === 'none' || el.style.display === '' ? 'block' : 'none';
}
</script>
</body>
</html>"""


def _do_approve(conn, entry: dict, alter_password: str, live_mode: bool) -> bool:
    if live_mode:
        success = poster.post_reply(
            entry["alter_username"], alter_password,
            entry["thread_id"], entry["reply_text"],
        )
        status = "approved" if success else "failed"
    else:
        success = True
        status = "approved"

    db.update_status(conn, entry["id"], status)
    db.insert_posted(
        conn, entry["alter_username"], entry["thread_id"],
        entry["post_id"], entry["reply_text"], simulated=not live_mode,
    )

    if live_mode and success:
        now = datetime.now(timezone.utc)
        db.increment_rate(conn, entry["alter_username"],
                          now.strftime("%Y-%m-%dT%H"), now.strftime("%Y-%m-%d"))
    return success


def create_app(conn, client, profiles, alter_password: str, live_mode: bool) -> Flask:
    app = Flask(__name__)
    profile_map = {p.reversed_username: p for p in profiles}
    forum_url = os.getenv("FORUM_URL", "https://forum.shrimprefuge.be")

    @app.route("/")
    def index():
        pending = [dict(r) for r in db.get_pending(conn)]
        return render_template_string(
            _QUEUE_TEMPLATE, replies=pending, live_mode=live_mode, forum_url=forum_url
        )

    @app.route("/reply/<int:reply_id>/approve", methods=["POST"])
    def approve(reply_id):
        entry = db.get_pending_by_id(conn, reply_id)
        if not entry:
            return "Not found", 404
        _do_approve(conn, dict(entry), alter_password, live_mode)
        return "", 204

    @app.route("/reply/<int:reply_id>/discard", methods=["POST"])
    def discard(reply_id):
        db.update_status(conn, reply_id, "discarded")
        return "", 204

    @app.route("/reply/<int:reply_id>/edit", methods=["POST"])
    def edit(reply_id):
        new_text = request.form.get("reply_text", "").strip()
        if not new_text:
            return "reply_text required", 400
        db.update_reply_text(conn, reply_id, new_text)
        entry = db.get_pending_by_id(conn, reply_id)
        if not entry:
            return "Not found", 404
        _do_approve(conn, dict(entry), alter_password, live_mode)
        return "", 204

    @app.route("/reply/<int:reply_id>/regenerate", methods=["POST"])
    def regenerate(reply_id):
        entry = db.get_pending_by_id(conn, reply_id)
        if not entry:
            return "Not found", 404
        profile = profile_map.get(entry["alter_username"])
        if not profile:
            return "Profile not found", 404
        try:
            scanner = VBulletinSession()
            scanner.login(os.getenv("FORUM_USERNAME", ""), os.getenv("FORUM_PASSWORD", ""))
            context = thread_scraper.fetch_thread_context(scanner, entry["post_id"])
            triggering = next(
                (p for p in context if p["post_id"] == entry["post_id"]),
                {"post_id": entry["post_id"], "author": "?", "content": ""},
            )
            new_text = event_generator.generate_reply(client, profile, triggering, context)
            db.update_reply_text(conn, reply_id, new_text)
        except Exception as exc:
            logging.warning("Regenerate failed for reply %d: %s", reply_id, exc)
            return "Generation failed", 500
        return "", 204

    @app.route("/status")
    def status():
        day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return jsonify({
            "live_mode": live_mode,
            "pending_count": len(db.get_pending(conn)),
            "posts_today": db.get_daily_posts_summary(conn, day_key),
        })

    return app
