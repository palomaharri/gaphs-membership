"""Members' library, paid-for files, public shop, forum."""
import mimetypes
import os
import secrets

from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request,
                   send_from_directory, url_for)

import db
import stripe_api
import courses_data
from auth_views import handle_checkout_completed
from helpers import (current_user, embed_for, has_access, login_required, member_required, money,
                     site_url, unlock_info)

members = Blueprint("members", __name__)
import edu
import forum_extras as fx
edu.init(members)  # Education Centre: host-aware branding


# ---- access rules -------------------------------------------------------------
def purchased(user, content_id, token=None):
    if token:
        row = db.q("SELECT id FROM purchases WHERE token = ? AND content_id = ?", (token, content_id), one=True)
        if row:
            return True
    if user:
        row = db.q("SELECT id FROM purchases WHERE user_id = ? AND content_id = ?", (user["id"], content_id), one=True)
        return bool(row)
    return False


def content_access(user, content, token=None):
    """Returns (allowed, days_until_open, how)."""
    if user and user["is_admin"]:
        return True, 0, "admin"
    if content["category"] == "report":  # GAPHS reports are free for everyone, members or not
        return True, 0, "open"
    if purchased(user, content["id"], token):
        return True, 0, "purchase"
    if user and has_access(user):
        ok, days = unlock_info(user, content["drip_days"])
        return ok, days, "member"
    return False, 0, "none"


def lesson_access(user, content, lesson, token=None):
    if user and user["is_admin"]:
        return True, 0
    if purchased(user, content["id"], token):
        return True, 0
    if user and has_access(user):
        ok_c, days_c = unlock_info(user, content["drip_days"])
        ok_l, days_l = unlock_info(user, lesson["drip_days"])
        return ok_c and ok_l, max(days_c, days_l)
    return False, 0


def media_for(item_row, token=None, lesson=False):
    """What to show for a video or PDF row (content item or lesson)."""
    kind = item_row["kind"]
    kind_path = "lesson" if lesson else "content"
    if kind == "pdf":
        return {"type": "pdf", "src": url_for("members.private_file", scope=kind_path, item_id=item_row["id"],
                                             **({"t": token} if token else {}))}
    if item_row["file_private"]:
        return {"type": "video", "src": url_for("members.private_file", scope=kind_path, item_id=item_row["id"],
                                                **({"t": token} if token else {}))}
    return embed_for(item_row["video_url"])


# ---- library ------------------------------------------------------------------
SECTIONS = [("course", "Courses", "Step-by-step learning, approved by GAPHS."),
            ("class", "Video guides", "Watch the Atelier Series guides, one topic at a time."),
            ("school", "From our approved schools", "Lessons shared with GAPHS members by home staging schools GAPHS has approved."),
            ("masterclass", "Master classes", "Longer, in-depth classes with industry experts."),
            ("webinar", "Webinars", "Recordings of GAPHS webinars with industry experts."),
            ("guide", "The Atelier Series", "Professional GAPHS guides to read, keep and put to work."),
            ("report", "Reports", "Industry reports from GAPHS, free for everyone."),
            ("ebook", "E-books", "Books to read and keep."),
            ("template", "Templates and tools", "Ready-to-use checklists, templates and worksheets.")]


def category_of(c):
    if c["category"]:
        return c["category"]
    if c["kind"] == "course":
        return "course"
    if c["kind"] == "pdf":
        return "ebook"
    return "class" if c["price"] else "webinar"


@members.route("/courses")
def courses():
    return render_template("courses.html", courses=courses_data.COURSES)


@members.route("/courses/<slug>")
def course_page(slug):
    c = courses_data.BY_SLUG.get(slug) or abort(404)
    if c.get("external"):
        faq = courses_data.COMMON_FAQ[:3] + c["faq_extra"]
    else:
        faq = courses_data.COMMON_FAQ[:3] + c["faq_extra"] + courses_data.COMMON_FAQ[3:]
    others = [x for x in courses_data.COURSES if x["slug"] != slug][:3]
    return render_template("course_page.html", c=c, faq=faq, others=others, about=courses_data.ABOUT,
                           about_hsec=courses_data.ABOUT_HSEC,
                           sent=request.args.get("sent"))


@members.route("/courses/<slug>/notify", methods=["POST"])
def course_notify(slug):
    c = courses_data.BY_SLUG.get(slug) or abort(404)
    if request.form.get("website"):
        return redirect(url_for("members.course_page", slug=slug, sent=1))
    email = (request.form.get("email") or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1] or len(email) > 200:
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("members.course_page", slug=slug) + "#notify")
    src = "course:" + slug
    if not db.q("SELECT 1 FROM subscribers WHERE email = ?", (email,), one=True):
        db.run("INSERT INTO subscribers(email, source, created_at) VALUES (?,?,?)", (email, src, db.now_iso()))
    return redirect(url_for("members.course_page", slug=slug, sent=1) + "#notify")


@members.route("/library")
def library():
    user = current_user()
    member = bool(user and has_access(user))
    items = db.q("SELECT * FROM content WHERE published = 1 ORDER BY sort, id")
    groups = {k: [] for k, _, _ in SECTIONS}
    for c in items:
        ok = False
        if user:
            ok, _, _ = content_access(user, c)
        groups.setdefault(category_of(c), []).append({"c": c, "ok": ok})
    groups["report"].reverse()  # reports: newest first
    tabs = [(k, t.split(":")[0]) for k, t, d in SECTIONS if groups.get(k)]
    active = request.args.get("type", "")
    if active not in dict(tabs):
        active = ""
    sections = [(k, t, d, groups[k]) for k, t, d in SECTIONS if groups.get(k) and (not active or k == active)]
    return render_template("library.html", sections=sections, member=member, tabs=tabs, active=active,
                           sales_courses=courses_data.COURSES)


@members.route("/library/<int:item_id>")
@member_required
def item(item_id):
    user = current_user()
    c = db.q("SELECT * FROM content WHERE id = ? AND published = 1", (item_id,), one=True)
    if not c and not (user["is_admin"]):
        abort(404)
    if not c:
        c = db.q("SELECT * FROM content WHERE id = ?", (item_id,), one=True) or abort(404)
    ok, days, _ = content_access(user, c)
    lessons = []
    if c["kind"] == "course":
        for l in db.q("SELECT * FROM lessons WHERE content_id = ? ORDER BY sort, id", (c["id"],)):
            lok, ldays = lesson_access(user, c, l)
            lessons.append({"l": l, "ok": lok, "days": ldays})
    media = media_for(c) if ok and c["kind"] != "course" else None
    return render_template("item.html", c=c, ok=ok, days=days, lessons=lessons, media=media, token=None)


@members.route("/library/<int:item_id>/lesson/<int:lesson_id>")
def lesson(item_id, lesson_id):
    user = current_user()
    token = request.args.get("t")
    c = db.q("SELECT * FROM content WHERE id = ?", (item_id,), one=True) or abort(404)
    l = db.q("SELECT * FROM lessons WHERE id = ? AND content_id = ?", (lesson_id, item_id), one=True) or abort(404)
    ok, days = lesson_access(user, c, l, token)
    if not user and not ok:
        return redirect(url_for("auth.login", next=request.path))
    siblings = db.q("SELECT * FROM lessons WHERE content_id = ? ORDER BY sort, id", (item_id,))
    media = media_for(l, token, lesson=True) if ok else None
    return render_template("lesson.html", c=c, l=l, ok=ok, days=days, media=media, siblings=siblings, token=token, tk=token)


@members.route("/files/<scope>/<int:item_id>")
def private_file(scope, item_id):
    user = current_user()
    token = request.args.get("t")
    if scope == "lesson":
        l = db.q("SELECT * FROM lessons WHERE id = ?", (item_id,), one=True) or abort(404)
        c = db.q("SELECT * FROM content WHERE id = ?", (l["content_id"],), one=True) or abort(404)
        ok, _ = lesson_access(user, c, l, token)
        row = l
    elif scope == "content":
        c = db.q("SELECT * FROM content WHERE id = ?", (item_id,), one=True) or abort(404)
        ok, _, _ = content_access(user, c, token)
        row = c
    else:
        abort(404)
    if not ok:
        abort(403)
    name = os.path.basename(row["file_private"] or "")
    if not name:
        abort(404)
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    resp = send_from_directory(db.PRIVATE_UPLOADS, name, mimetype=mime, conditional=True,
                               as_attachment=request.args.get("download") == "1",
                               download_name=(row["title"] or "file")[:80] + os.path.splitext(name)[1])
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


# ---- public shop ---------------------------------------------------------------
@members.route("/shop")
def shop():
    return redirect(url_for("members.library"))


@members.route("/shop/<int:item_id>")
def shop_item(item_id):
    c = db.q("SELECT * FROM content WHERE id = ? AND published = 1", (item_id,), one=True) or abort(404)
    user = current_user()
    owned = purchased(user, item_id) if user else False
    member_free = bool(user and has_access(user))
    lessons = db.q("SELECT title FROM lessons WHERE content_id = ? ORDER BY sort, id", (item_id,)) if c["kind"] == "course" else []
    more = [x for x in db.q("""SELECT * FROM content WHERE published = 1 AND price > 0 AND id != ?
                               ORDER BY (kind = ?) DESC, sort, id LIMIT 12""", (item_id, c["kind"]))
            if not (user and purchased(user, x["id"]))][:4]
    return render_template("shop_item.html", c=c, owned=owned, member_free=member_free, lessons=lessons, more=more)


@members.route("/shop/<int:item_id>/buy", methods=["POST"])
def shop_buy(item_id):
    c = db.q("SELECT * FROM content WHERE id = ? AND published = 1 AND price > 0", (item_id,), one=True) or abort(404)
    user = current_user()
    if user and has_access(user):
        flash("Members have this included.", "info")
        return redirect(url_for("members.item", item_id=item_id))
    email = (user["email"] if user else (request.form.get("email") or "")).strip().lower()
    if "@" not in email:
        flash("Please enter your email so we can send you the link.", "error")
        return redirect(url_for("members.shop_item", item_id=item_id))
    if stripe_api.enabled("courses"):
        try:
            sess = stripe_api.payment_checkout(
                c["title"], c["price"], c["id"], user["id"] if user else None, email,
                site_url() + url_for("members.shop_thanks") + "?session_id={CHECKOUT_SESSION_ID}",
                site_url() + url_for("members.shop_item", item_id=item_id))
        except stripe_api.StripeError as exc:
            current_app.logger.error("Stripe: %s", exc)
            flash("We could not start the payment: %s" % exc, "error")
            return redirect(url_for("members.shop_item", item_id=item_id))
        return redirect(sess["url"], 303)
    import json
    token = secrets.token_urlsafe(18)
    db.run("INSERT INTO pending_checkouts(token, kind, payload, created_at) VALUES (?,?,?,?)",
           (token, "payment", json.dumps({"content_id": c["id"], "name": c["title"], "amount": c["price"],
                                          "email": email}), db.now_iso()))
    return redirect(url_for("auth.simulate", token=token))


@members.route("/shop/thanks")
def shop_thanks():
    sid = request.args.get("session_id", "")
    token = None
    if sid and stripe_api.enabled("courses"):
        try:
            token = handle_checkout_completed(stripe_api.get_session(sid, "courses"))
        except stripe_api.StripeError as exc:
            current_app.logger.warning("Could not confirm session: %s", exc)
    if token:
        return redirect(url_for("members.purchase", token=token))
    flash("Thank you. We are confirming your payment; the link is on its way by email.", "info")
    return redirect(url_for("members.shop"))


@members.route("/purchase/<token>")
def purchase(token):
    p = db.q("SELECT * FROM purchases WHERE token = ?", (token,), one=True) or abort(404)
    c = db.q("SELECT * FROM content WHERE id = ?", (p["content_id"],), one=True) or abort(404)
    lessons = db.q("SELECT * FROM lessons WHERE content_id = ? ORDER BY sort, id", (c["id"],)) if c["kind"] == "course" else []
    media = media_for(c, token) if c["kind"] != "course" else None
    return render_template("purchase.html", c=c, lessons=lessons, media=media, token=token, tk=token)


# ---- forum ----------------------------------------------------------------------
def author_name(row_user_id):
    r = db.q("""SELECT u.name, p.business_name FROM users u LEFT JOIN profiles p ON p.user_id = u.id
                WHERE u.id = ?""", (row_user_id,), one=True)
    if not r:
        return "Member"
    return r["business_name"] or r["name"] or "Member"


@members.route("/forum")
@member_required
def forum():
    cats = db.q("""SELECT c.*, (SELECT COUNT(*) FROM threads t WHERE t.category_id = c.id) AS n_threads,
                   (SELECT MAX(last_post_at) FROM threads t WHERE t.category_id = c.id) AS last_at
                   FROM forum_categories c ORDER BY c.sort, c.id""")
    return render_template("forum.html", cats=cats)


@members.route("/forum/c/<int:cat_id>")
@member_required
def forum_category(cat_id):
    cat = db.q("SELECT * FROM forum_categories WHERE id = ?", (cat_id,), one=True) or abort(404)
    threads = db.q("""SELECT t.*, COALESCE(p.business_name, u.name) AS author, p.logo AS logo, u.is_admin AS is_admin,
                      (SELECT COUNT(*) FROM posts po WHERE po.thread_id = t.id) AS n_posts
                      FROM threads t JOIN users u ON u.id = t.user_id LEFT JOIN profiles p ON p.user_id = u.id
                      WHERE t.category_id = ? ORDER BY t.pinned DESC, t.last_post_at DESC LIMIT 200""", (cat_id,))
    return render_template("forum_category.html", cat=cat, threads=threads)


@members.route("/forum/c/<int:cat_id>/new", methods=["POST"])
@member_required
def forum_new_thread(cat_id):
    user = current_user()
    db.q("SELECT id FROM forum_categories WHERE id = ?", (cat_id,), one=True) or abort(404)
    title = (request.form.get("title") or "").strip()[:160]
    body = (request.form.get("body") or "").strip()[:8000]
    if not title or not body:
        flash("Please add a title and a message.", "error")
        return redirect(url_for("members.forum_category", cat_id=cat_id))
    if fx.blocked(title + " " + body):
        flash(fx.BLOCK_MSG, "error")
        return redirect(url_for("members.forum_category", cat_id=cat_id))
    if user["is_admin"] and fx.schedule(cat_id, user, title, body, request.form.get("publish_at_utc")):
        flash("Scheduled. It will be posted automatically at the time you chose.", "success")
        return redirect(url_for("members.forum_category", cat_id=cat_id))
    now = db.now_iso()
    tid = db.run("INSERT INTO threads(category_id, user_id, title, created_at, last_post_at) VALUES (?,?,?,?,?)",
                 (cat_id, user["id"], title, now, now))
    db.run("INSERT INTO posts(thread_id, user_id, body, created_at) VALUES (?,?,?,?)", (tid, user["id"], body, now))
    fx.notify_new(tid, user, body, True)
    return redirect(url_for("members.forum_thread", thread_id=tid))


@members.route("/forum/t/<int:thread_id>")
@member_required
def forum_thread(thread_id):
    t = db.q("SELECT * FROM threads WHERE id = ?", (thread_id,), one=True) or abort(404)
    cat = db.q("SELECT * FROM forum_categories WHERE id = ?", (t["category_id"],), one=True)
    posts = db.q("""SELECT po.*, COALESCE(p.business_name, u.name) AS author, p.slug, p.logo AS logo, u.is_admin AS is_admin
                    FROM posts po JOIN users u ON u.id = po.user_id LEFT JOIN profiles p ON p.user_id = u.id
                    WHERE po.thread_id = ? ORDER BY po.created_at, po.id""", (thread_id,))
    return render_template("thread.html", t=t, cat=cat, posts=posts)


@members.route("/forum/t/<int:thread_id>/reply", methods=["POST"])
@member_required
def forum_reply(thread_id):
    user = current_user()
    db.q("SELECT id FROM threads WHERE id = ?", (thread_id,), one=True) or abort(404)
    body = (request.form.get("body") or "").strip()[:8000]
    if not body:
        flash("Please write a message first.", "error")
    elif fx.blocked(body):
        flash(fx.BLOCK_MSG, "error")
    else:
        now = db.now_iso()
        db.run("INSERT INTO posts(thread_id, user_id, body, created_at) VALUES (?,?,?,?)",
               (thread_id, user["id"], body, now))
        db.run("UPDATE threads SET last_post_at = ? WHERE id = ?", (now, thread_id))
        fx.notify_new(thread_id, user, body, False)
    return redirect(url_for("members.forum_thread", thread_id=thread_id) + "#end")


@members.route("/forum/post/<int:post_id>/delete", methods=["POST"])
@member_required
def forum_delete_post(post_id):
    user = current_user()
    post = db.q("SELECT * FROM posts WHERE id = ?", (post_id,), one=True) or abort(404)
    if post["user_id"] != user["id"] and not user["is_admin"]:
        abort(403)
    first = db.q("SELECT id FROM posts WHERE thread_id = ? ORDER BY created_at, id LIMIT 1",
                 (post["thread_id"],), one=True)
    cat = db.q("SELECT category_id FROM threads WHERE id = ?", (post["thread_id"],), one=True)["category_id"]
    if first and first["id"] == post_id:
        db.run("DELETE FROM threads WHERE id = ?", (post["thread_id"],))
        flash("Thread deleted.", "success")
        return redirect(url_for("members.forum_category", cat_id=cat))
    db.run("DELETE FROM posts WHERE id = ?", (post_id,))
    flash("Message deleted.", "success")
    return redirect(url_for("members.forum_thread", thread_id=post["thread_id"]))


@members.route("/forum/t/<int:thread_id>/pin", methods=["POST"])
@login_required
def forum_pin(thread_id):
    user = current_user()
    if not user["is_admin"]:
        abort(403)
    t = db.q("SELECT * FROM threads WHERE id = ?", (thread_id,), one=True) or abort(404)
    db.run("UPDATE threads SET pinned = ? WHERE id = ?", (0 if t["pinned"] else 1, thread_id))
    return redirect(url_for("members.forum_thread", thread_id=thread_id))
