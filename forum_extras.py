"""Forum extras: tagging members (@[Name]), email notifications with a per-member off switch,
admin-only scheduled threads, and a blocked-words filter. Hooked from members_views (new thread / reply)
and from edu.init (routes and template helpers)."""
import re
import time
from html import escape

from flask import abort, current_app, flash, jsonify, redirect, request, url_for
from markupsafe import Markup

import db
import helpers

BLOCK_MSG = ("Your message was not published because it contains language that is not allowed in the forum. "
             "Please reword it and post again.")
# Whole-word matches, any capitalisation. Admins can add more on the Forum page.
DEFAULT_BLOCKED = """fuck fucker fuckers fucking fucked motherfucker motherfuckers shit shits shitty bullshit
bitch bitches bastard bastards asshole assholes arsehole arseholes dick dickhead dickheads prick pricks
cunt cunts twat twats wanker wankers tosser tossers slut sluts whore whores piss pissed bollocks
nigger niggers nigga faggot faggots fag fags retard retards retarded spastic paki pakis chink chinks
kike kikes spic spics tranny trannies dyke dykes coon coons""".split()
MENTION = re.compile(r"@\[([^\[\]\n]{1,120})\]")
_ready = [False]
_last_publish = [0.0]


def ensure():
    if _ready[0]:
        return
    db.run("CREATE TABLE IF NOT EXISTS forum_prefs(user_id INTEGER PRIMARY KEY, notify INTEGER NOT NULL DEFAULT 1)")
    db.run("""CREATE TABLE IF NOT EXISTS forum_scheduled(
        id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        title TEXT NOT NULL, body TEXT NOT NULL, publish_at TEXT NOT NULL, created_at TEXT NOT NULL)""")
    _ready[0] = True


# ---- blocked words -----------------------------------------------------------------------------------
def _words():
    extra = re.split(r"[\s,;]+", (db.setting("forum_blocked_words", "") or "").lower())
    return set(w for w in DEFAULT_BLOCKED + extra if w)


def blocked(text):
    """True when the text contains a blocked word (whole words; common letter swaps such as @ for a are undone)."""
    low = (text or "").lower()
    low = MENTION.sub(" ", low)
    plain = low.translate(str.maketrans({"@": "a", "$": "s", "0": "o", "1": "i", "3": "e", "!": "i", "*": ""}))
    words = _words()
    for candidate in (low, plain):
        for token in re.findall(r"[a-z']+", candidate):
            if token in words or token.strip("'") in words:
                return True
    for token in re.findall(r"[a-z*]+", low):  # starred-out letters: f*ck, sh*t
        if "*" in token and len(token) > 2 and len(token.replace("*", "")) >= 2:
            pattern = re.compile("^" + re.escape(token).replace(r"\*", "[a-z]") + "$")
            if any(pattern.match(w) for w in words):
                return True
    return False


# ---- members and tagging -----------------------------------------------------------------------------
def _members():
    """People who can be tagged: current members and admins, by the name the forum shows for them."""
    rows = db.q("""SELECT u.id, u.email, u.is_admin, COALESCE(NULLIF(p.business_name, ''), u.name) AS label, p.slug
                   FROM users u LEFT JOIN profiles p ON p.user_id = u.id
                   WHERE u.is_admin = 1 OR u.comped = 1 OR u.status IN ('active', 'past_due')""")
    return [r for r in rows if (r["label"] or "").strip()]


def members_json():
    user = helpers.current_user()
    if not user or not helpers.has_access(user):
        abort(403)
    names = sorted(set(r["label"].strip() for r in _members()), key=lambda s: s.lower())
    return jsonify(names)


def html(body):
    """Post text for display: escaped, with @[Name] turned into the member's name (linked to their page)."""
    try:
        slugs = {r["label"].strip().lower(): r["slug"] for r in _members()}
    except Exception:
        slugs = {}

    def one(m):
        name = m.group(1).strip()
        slug = slugs.get(name.lower())
        if slug:
            return '<a href="%s"><strong>@%s</strong></a>' % (escape(url_for("auth.business", slug=slug)), escape(name))
        return "<strong>@%s</strong>" % escape(name)

    parts, last = [], 0
    for m in MENTION.finditer(body or ""):
        parts.append(escape((body or "")[last:m.start()]))
        parts.append(one(m))
        last = m.end()
    parts.append(escape((body or "")[last:]))
    return Markup("".join(parts))


# ---- notifications -----------------------------------------------------------------------------------
def notify_on(user):
    try:
        ensure()
        row = db.q("SELECT notify FROM forum_prefs WHERE user_id = ?", (user["id"],), one=True)
        return True if row is None else bool(row["notify"])
    except Exception:
        return True


def set_notify():
    user = helpers.current_user()
    if not user:
        abort(403)
    ensure()
    on = 1 if request.form.get("notify") == "1" else 0
    db.run("INSERT OR REPLACE INTO forum_prefs(user_id, notify) VALUES (?,?)", (user["id"], on))
    flash("Forum emails are now %s." % ("on" if on else "off"), "success")
    return redirect(url_for("members.forum"))


def _wants(uid):
    row = db.q("SELECT notify FROM forum_prefs WHERE user_id = ?", (uid,), one=True)
    return True if row is None else bool(row["notify"])


def _send(to, subject, text):
    try:
        import accreditation
        return accreditation._send(to, subject, text)
    except Exception as exc:
        current_app.logger.warning("forum email: %s", exc)
        return False


def notify_new(thread_id, author, body, first):
    """After a post goes live: email members who were tagged, and (for a reply) the person who started the thread."""
    try:
        ensure()
        t = db.q("SELECT * FROM threads WHERE id = ?", (thread_id,), one=True)
        if not t:
            return
        site = helpers.site_url()
        link = "%s/forum/t/%d" % (site, thread_id)
        who = db.q("""SELECT COALESCE(NULLIF(p.business_name, ''), u.name) AS label FROM users u
                      LEFT JOIN profiles p ON p.user_id = u.id WHERE u.id = ?""", (author["id"],), one=True)
        who = (who["label"] if who and who["label"] else "A member").strip()
        excerpt = MENTION.sub(lambda m: "@" + m.group(1), body or "").strip()
        if len(excerpt) > 600:
            excerpt = excerpt[:600].rstrip() + "..."
        off = "You can turn these emails off on the forum's front page: %s/forum" % site
        done = set([author["id"]])
        tagged = set(n.strip().lower() for n in MENTION.findall(body or ""))
        if tagged:
            for r in _members():
                if r["label"].strip().lower() in tagged and r["id"] not in done:
                    done.add(r["id"])
                    if _wants(r["id"]):
                        _send(r["email"], "%s mentioned you in the GAPHS forum" % who,
                              "%s mentioned you in \"%s\".\n\n%s\n\nRead it and reply here: %s\n\n%s"
                              % (who, t["title"], excerpt, link, off))
        if not first and t["user_id"] not in done:
            starter = db.q("SELECT id, email FROM users WHERE id = ?", (t["user_id"],), one=True)
            if starter and _wants(starter["id"]):
                _send(starter["email"], "New reply to your thread in the GAPHS forum",
                      "%s replied to your thread \"%s\".\n\n%s\n\nRead it and reply here: %s\n\n%s"
                      % (who, t["title"], excerpt, link, off))
    except Exception as exc:
        current_app.logger.warning("forum notify: %s", exc)


# ---- scheduled threads (admin only) ------------------------------------------------------------------
def _clean_when(value):
    """'2026-11-20T09:00:00.000Z' (sent by the browser in UTC) -> a stored UTC time, or None."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})(?::(\d{2}))?", (value or "").strip())
    if not m:
        return None
    return "%sT%s:%sZ" % (m.group(1), m.group(2), m.group(3) or "00")


def schedule(cat_id, user, title, body, when):
    """Admin posts with a future date: keep it back until then. Returns True when it was scheduled."""
    stamp = _clean_when(when)
    if not stamp or not user["is_admin"]:
        return False
    ensure()
    due, now = db.parse_iso(stamp), db.parse_iso(db.now_iso())
    if not due or not now or due <= now:
        return False
    db.run("INSERT INTO forum_scheduled(category_id, user_id, title, body, publish_at, created_at) VALUES (?,?,?,?,?,?)",
           (cat_id, user["id"], title, body, stamp, db.now_iso()))
    return True


def scheduled(cat_id):
    try:
        ensure()
        return db.q("SELECT * FROM forum_scheduled WHERE category_id = ? ORDER BY publish_at", (cat_id,))
    except Exception:
        return []


def cancel_scheduled(sid):
    user = helpers.current_user()
    if not user or not user["is_admin"]:
        abort(403)
    ensure()
    row = db.q("SELECT * FROM forum_scheduled WHERE id = ?", (sid,), one=True) or abort(404)
    db.run("DELETE FROM forum_scheduled WHERE id = ?", (sid,))
    flash("Scheduled thread cancelled. It will not be posted.", "success")
    return redirect(url_for("members.forum_category", cat_id=row["category_id"]))


def publish_due():
    """Runs with site traffic, at most once a minute: posts any scheduled thread whose time has come."""
    if time.time() - _last_publish[0] < 60:
        return
    _last_publish[0] = time.time()
    try:
        ensure()
        now_s = db.now_iso()
        now = db.parse_iso(now_s)
        for row in db.q("SELECT * FROM forum_scheduled ORDER BY publish_at"):
            due = db.parse_iso(row["publish_at"])
            if not due or not now or due > now:
                continue
            db.run("DELETE FROM forum_scheduled WHERE id = ?", (row["id"],))
            if not db.q("SELECT id FROM forum_categories WHERE id = ?", (row["category_id"],), one=True):
                continue
            tid = db.run("INSERT INTO threads(category_id, user_id, title, created_at, last_post_at) VALUES (?,?,?,?,?)",
                         (row["category_id"], row["user_id"], row["title"], now_s, now_s))
            db.run("INSERT INTO posts(thread_id, user_id, body, created_at) VALUES (?,?,?,?)",
                   (tid, row["user_id"], row["body"], now_s))
            notify_new(tid, {"id": row["user_id"]}, row["body"], True)
    except Exception as exc:
        try:
            current_app.logger.warning("forum publish: %s", exc)
        except Exception:
            pass


def save_words():
    user = helpers.current_user()
    if not user or not user["is_admin"]:
        abort(403)
    db.set_setting("forum_blocked_words", (request.form.get("words") or "").strip()[:4000])
    flash("Blocked words saved.", "success")
    return redirect(url_for("members.forum"))


def extra_words():
    return db.setting("forum_blocked_words", "") or ""
