"""Home Staging Education Centre: host-aware branding.

One Flask app, two front doors. When a request arrives on the Education Centre domain
(env var EDU_HOST, default homestagingeducationcentre.co.uk, with or without www.) the site
shows Education Centre branding and a course landing page at "/". Every other host
(homestagingassociation.org, onrender.com, localhost) keeps the Home Staging Association look.

Hooked in with one line at the bottom of members_views.py:  import edu; edu.init(members)
"""
import os
import re
import sys

from flask import Response, abort, flash, has_request_context, json, redirect, render_template, request

import courses_data
import db

EDU_NAME = "Home Staging Education Centre"
HSA_NAME = "Global Association of Professional Home Stagers"   # the main site (name kept from the replica)
SELLER = "Global Association of Professional Home Stagers"
HIDDEN_CATEGORIES = ("webinar", "report")   # HSA only: never shown or sold on the Education Centre site
GIFT_TITLE = "A Day in the Life of a Home Stager"   # the one free item on the Education Centre site

BRAND_EDU = {"name": EDU_NAME, "short": "Education Centre", "theme": "#9C7D2F", "edu": True}
BRAND_HSA = {"name": "GAPHS · " + HSA_NAME, "short": "GAPHS", "theme": "#1A1A1A", "edu": False}


def edu_host():
    """Second-brand domain. GAPHS has none, so this stays empty unless EDU_HOST is set."""
    return (os.environ.get("EDU_HOST") or "").strip().lower()


def is_edu():
    if not has_request_context():
        return False
    host = (request.host or "").split(":")[0].lower()
    return bool(edu_host()) and host in (edu_host(), "www." + edu_host())


def brand():
    return BRAND_EDU if is_edu() else BRAND_HSA


def canonical_url():
    """Course pages (and the Education Centre home page) always point at the Education Centre domain."""
    path = request.path
    if not edu_host():
        return None
    if path == "/courses" or path.startswith("/courses/"):
        return "https://%s%s" % (edu_host(), path)
    if path == "/" and is_edu():
        return "https://%s/" % edu_host()
    return None


def _norm(text):
    text = (text or "").lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return re.sub(r"^the ", "", text)


def course_row(c):
    """The published course in the library whose title matches this sales-page course, or None.
    A match means the course is ready: the page shows a Buy button (or Start link) instead of 'Coming soon'."""
    try:
        rows = db.q("SELECT * FROM content WHERE published = 1 AND kind = 'course'")
    except Exception:
        return None
    want = _norm(c["title"])
    for r in rows:
        if _norm(r["title"]) == want:
            return r
    return None


def manifest():
    data = {
        "name": EDU_NAME, "short_name": "Education Centre", "start_url": "/", "scope": "/",
        "display": "standalone", "background_color": "#F6F1E9", "theme_color": "#9C7D2F",
        "icons": [
            {"src": "/static/icons/edu-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icons/edu-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }
    return Response(json.dumps(data), mimetype="application/manifest+json")


def _site_url_for(orig):
    def site_url():
        if is_edu():
            return "https://" + edu_host()
        return orig()
    site_url._edu_wrapped = True
    return site_url


def _patch_helpers():
    """Emails and links built from SITE_URL point at the HSA domain; on the Education Centre host they
    should carry the Education Centre name, colours and address. Done once, on the first request."""
    import helpers
    if getattr(helpers, "_edu_patched", False):
        return
    orig_site, orig_html = helpers.site_url, helpers.email_html
    new_site = _site_url_for(orig_site)

    def email_html(subject, body):
        html = orig_html(subject, body)
        if is_edu():
            html = (html.replace(HSA_NAME, EDU_NAME).replace("#1A1A1A", "#3F4A3C")
                    .replace("#1A1A1A", "#9C7D2F").replace("#F5F1E8", "#F6F1E9"))
        return html

    helpers.site_url, helpers.email_html = new_site, email_html
    import sys
    for _name in ("members_views", "auth_views", "admin_views", "app", "mails", "reminders"):
        _mod = sys.modules.get(_name)
        if _mod is not None and hasattr(_mod, "site_url"):
            _mod.site_url = new_site
    # Remember which site each checkout started on, so the access email links back to the same site.
    try:
        import stripe_api as _sa
        _orig_pc = _sa.payment_checkout

        def payment_checkout(*a, **k):
            sess = _orig_pc(*a, **k)
            try:
                db.run("CREATE TABLE IF NOT EXISTS checkout_sites(session_id TEXT PRIMARY KEY, site TEXT)")
                db.run("INSERT OR REPLACE INTO checkout_sites(session_id, site) VALUES (?,?)", (sess["id"], new_site()))
            except Exception:
                pass
            return sess

        _sa.payment_checkout = payment_checkout
    except Exception:
        pass
    # The gift e-book is free to anyone with an account on the Education Centre site.
    try:
        import members_views as mv
        orig_access = mv.content_access

        def _free(content):
            return content["title"] == GIFT_TITLE or (content["kind"] == "course" and not content["price"])

        def content_access(user, content, token=None):
            if not is_edu():
                return orig_access(user, content, token)
            # Education Centre: HSA membership unlocks nothing here. Admin, a purchase, or a free item for a logged-in account.
            if user and user["is_admin"]:
                return True, 0, "admin"
            if mv.purchased(user, content["id"], None):
                return True, 0, "purchase"
            if user and _free(content):
                return True, 0, "open"
            return False, 0, "none"

        orig_lesson = mv.lesson_access

        def lesson_access(user, content, lesson, token=None):
            if not is_edu():
                return orig_lesson(user, content, lesson, token)
            ok, days, _ = content_access(user, content, token)
            return ok, days

        mv.lesson_access = lesson_access
        mv.content_access = content_access
        # Membership gives no discount or free access on the Education Centre: members buy like everyone else.
        if hasattr(mv, "has_access"):
            orig_has = mv.has_access
            mv.has_access = lambda user, *a, **k: False if is_edu() else orig_has(user, *a, **k)
    except Exception:
        pass
    # Email the buyer their access link as soon as a purchase is recorded (once per Stripe session).
    try:
        import auth_views
        orig_record = auth_views.record_purchase

        def record_purchase(content_id, user_id, email, session_id, amount):
            existed = bool(session_id and db.q("SELECT id FROM purchases WHERE stripe_session = ?", (session_id,), one=True))
            tk = orig_record(content_id, user_id, email, session_id, amount)
            if not existed and email and "@" in email:
                try:
                    c = db.q("SELECT title FROM content WHERE id = ?", (content_id,), one=True)
                    title = c["title"] if c else "your purchase"
                    link = "https://%s/purchase/%s" % (edu_host(), tk)
                    subject = "Your access: " + title
                    text = ("Thank you for your purchase.\n\n%s\n\nOpen it any time with this private link:\n%s\n\n"
                            "Keep this email: the link is your access. Create a free account with this email address "
                            "to find your purchases in one place.\n\n%s" % (title, link, EDU_NAME))
                    body = ('<p>Thank you for your purchase.</p><p><strong>%s</strong></p>'
                            '<p><a href="%s" style="display:inline-block;padding:12px 22px;background:#9C7D2F;color:#ffffff;'
                            'text-decoration:none;border-radius:4px">Open your purchase</a></p>'
                            '<p>Or copy this private link: <br><a href="%s">%s</a></p>'
                            '<p>Keep this email: the link is your access.</p>' % (title, link, link, link))
                    html = helpers.email_html(subject, body)
                    html = (html.replace(HSA_NAME, EDU_NAME).replace("#1A1A1A", "#3F4A3C")
                            .replace("#1A1A1A", "#9C7D2F").replace("#F5F1E8", "#F6F1E9"))
                    _send_access_email(email, title, tk, _checkout_site(session_id))
                except Exception as exc:
                    try:
                        from flask import current_app
                        current_app.logger.warning("Purchase email failed: %s", exc)
                    except Exception:
                        pass
            return tk

        auth_views.record_purchase = record_purchase
    except Exception:
        pass
    helpers._edu_patched = True


def _is_hidden(content_id):
    import members_views as mv
    c = db.q("SELECT * FROM content WHERE id = ?", (content_id,), one=True)
    return bool(c) and mv.category_of(c) in HIDDEN_CATEGORIES


def _edu_library():
    """Everything for sale on the Education Centre site, minus webinars and reports (HSA only)."""
    import members_views as mv
    user = mv.current_user()
    items = db.q("SELECT * FROM content WHERE published = 1 ORDER BY sort, id")
    groups = {k: [] for k, _, _ in mv.SECTIONS}
    for c in items:
        cat = mv.category_of(c)
        if cat in HIDDEN_CATEGORIES:
            continue
        ok = False
        if user:
            ok, _, _ = mv.content_access(user, c)
        groups.setdefault(cat, []).append({"c": c, "ok": ok, "gift": c["title"] == GIFT_TITLE})
    sections = [(k, t, d, groups[k]) for k, t, d in mv.SECTIONS if groups.get(k)]
    return render_template("edu_library.html", sections=sections)


def _claim_purchases(user):
    """Attach purchases made with this email address to the account."""
    try:
        db.run("UPDATE purchases SET user_id = ? WHERE user_id IS NULL AND lower(email) = lower(?)",
               (user["id"], user["email"]))
    except Exception:
        pass


def _ensure_account(email):
    """Find or create a plain account (no membership) for a buyer. Returns (user, set_password_token or None)."""
    import secrets
    from datetime import datetime, timedelta, timezone
    email = (email or "").strip().lower()
    user = db.q("SELECT * FROM users WHERE email = ?", (email,), one=True)
    if user:
        return user, None
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.run("INSERT INTO users(email, pw_hash, name, created_at, reset_token, reset_expires) VALUES (?,?,?,?,?,?)",
           (email, db.hash_password(secrets.token_urlsafe(24)), "", db.now_iso(), token, expires))
    return db.q("SELECT * FROM users WHERE email = ?", (email,), one=True), token


def _checkout_site(session_id):
    try:
        db.run("CREATE TABLE IF NOT EXISTS checkout_sites(session_id TEXT PRIMARY KEY, site TEXT)")
        r = db.q("SELECT site FROM checkout_sites WHERE session_id = ?", (session_id,), one=True) if session_id else None
        if r and r["site"]:
            return r["site"]
    except Exception:
        pass
    return None


def _send_access_email(email, title, tk, site=None):
    """Email a buyer how to log in and watch. New buyers also get a link to choose their password."""
    import helpers
    user, set_token = _ensure_account(email)
    if user:
        db.run("UPDATE purchases SET user_id = ? WHERE token = ? AND user_id IS NULL", (user["id"], tk))
    if not site:
        site = ("https://" + edu_host()) if is_edu() else helpers.site_url()
    _on_edu = edu_host() in site
    _name = EDU_NAME if _on_edu else HSA_NAME
    login_url = site + "/login"
    courses_url = site + "/my-courses"
    subject = "Your access: " + title
    if set_token:
        set_url = site + "/reset/" + set_token
        text = ("Thank you for your purchase of %s.\n\n"
                "Step 1. Choose your password. The link works for 7 days.\n\n"
                "Choose my password: %s\n\n"
                "Step 2. Then log in any time with this email address and your password.\n\n"
                "Log in: %s\n\n"
                "Your courses are always waiting for you.\n\n"
                "My courses: %s\n\n"
                "If the password link has expired, open the login page and choose Forgot your password.\n\n%s"
                % (title, set_url, login_url, courses_url, _name))
    else:
        text = ("Thank you for your purchase of %s.\n\n"
                "Log in with the email address you used to buy.\n\n"
                "Log in: %s\n\n"
                "Your courses are always waiting for you.\n\n"
                "My courses: %s\n\n%s"
                % (title, login_url, courses_url, _name))
    html = helpers.email_html(subject, text)
    if _on_edu:
        html = (html.replace(HSA_NAME, EDU_NAME).replace("#1A1A1A", "#3F4A3C")
                .replace("#1A1A1A", "#9C7D2F").replace("#F5F1E8", "#F6F1E9"))
    helpers.send_mail(email, subject, text, html)


def _fx(name):
    """Late-bound call into forum_extras (tagging, notifications, scheduling, blocked words)."""
    def call(*a, **k):
        import forum_extras
        return getattr(forum_extras, name)(*a, **k)
    return call


def _enquiry_count(uid):
    try:
        import enquiries
        return enquiries.count(uid)
    except Exception:
        return 0


def _acc_status(uid):
    """Accreditation status for templates: '' / applied / review / feedback / accredited."""
    try:
        import accreditation
        return accreditation.status(uid)
    except Exception:
        return ""


def init(bp):
    """Register the Education Centre hooks on a blueprint (they apply to the whole app)."""

    @bp.app_context_processor
    def _edu_context():
        return {"brand": brand(), "is_edu": is_edu(), "canonical_url": canonical_url(),
                "seller": SELLER, "edu_host": edu_host(), "course_row": course_row, "acc_status": _acc_status,
                "forum_html": _fx("html"), "forum_notify_on": _fx("notify_on"), "forum_scheduled": _fx("scheduled"),
                "forum_extra_words": _fx("extra_words"), "enquiry_count": _enquiry_count}

    @bp.route("/forum/members.json")
    def forum_members_json():
        return _fx("members_json")()

    @bp.route("/forum/notifications", methods=["POST"])
    def forum_notifications():
        return _fx("set_notify")()

    @bp.route("/forum/scheduled/<int:sid>/cancel", methods=["POST"])
    def forum_scheduled_cancel(sid):
        return _fx("cancel_scheduled")(sid)

    @bp.route("/forum/blocked-words", methods=["POST"])
    def forum_blocked_words():
        return _fx("save_words")()

    @bp.before_app_request
    def _forum_publish():
        try:
            _fx("publish_due")()
        except Exception:
            pass
        return None

    @bp.route("/directory/<slug>/enquiry", methods=["POST"])
    def directory_enquiry(slug):
        import enquiries
        return enquiries.submit(slug)

    @bp.route("/podcast/question", methods=["GET", "POST"])
    def podcast_question():
        """HSA podcast questions: not used on the GAPHS site."""
        abort(404)
        import helpers
        if request.method == "POST":
            if request.form.get("website"):
                return redirect("/podcast/question?sent=1")
            name = (request.form.get("name") or "").strip()[:120]
            email = (request.form.get("email") or "").strip().lower()[:200]
            question = (request.form.get("question") or "").strip()[:3000]
            if len(question) < 10 or "@" not in email or "." not in email.split("@")[-1]:
                flash("Please add your email and your question.", "error")
                return redirect("/podcast/question")
            try:
                import forum_extras
                if forum_extras.blocked(question + " " + name):
                    flash("Your question contains language that is not allowed. Please reword it.", "error")
                    return redirect("/podcast/question")
            except Exception:
                pass
            try:
                to = os.environ.get("PODCAST_NOTIFY_EMAIL", "info@gaphs.org")
                helpers.send_mail(to, "Podcast question from %s" % (name or email),
                                  "A question for the HSA Podcast.\n\nName: %s\n\nEmail: %s\n\nQuestion:\n%s"
                                  % (name or "(not given)", email, question))
            except Exception:
                pass
            return redirect("/podcast/question?sent=1")
        return render_template("podcast_question.html", sent=request.args.get("sent"))

    @bp.route("/accredited")
    def accredited():
        abort(404)  # GAPHS: no Accredited tier (the code stays for later)
        if is_edu():
            abort(404)
        return render_template("accredited.html")

    @bp.route("/accreditation-terms")
    def accreditation_terms():
        abort(404)
        if is_edu():
            abort(404)
        return render_template("accreditation_terms.html")

    @bp.route("/accreditation", methods=["GET", "POST"])
    def accreditation_me():
        abort(404)
        if is_edu():
            abort(404)
        import accreditation
        return accreditation.my_page()

    @bp.route("/coaching", methods=["GET", "POST"])
    def coaching():
        """HSA coaching page: not used on the GAPHS site."""
        import helpers
        abort(404)
        user = helpers.current_user()
        if not user:
            flash("Please log in to find out about coaching.", "info")
            return redirect("/login?next=/coaching")
        if not helpers.has_access(user):
            flash("Coaching is for current members.", "info")
            return redirect("/join")
        if request.method == "POST":
            if request.form.get("website"):
                return redirect("/coaching?sent=1#interest")
            email = (request.form.get("email") or "").strip().lower()[:200]
            name = (request.form.get("name") or "").strip()[:120]
            note = (request.form.get("note") or "").strip()[:1500]
            if "@" not in email or "." not in email.split("@")[-1]:
                flash("Please enter a valid email address.", "error")
                return redirect("/coaching#interest")
            member = "Yes" if (user and helpers.has_access(user)) else "No"
            try:
                db.run("""CREATE TABLE IF NOT EXISTS coaching_interest(id INTEGER PRIMARY KEY AUTOINCREMENT,
                          name TEXT, email TEXT NOT NULL, note TEXT, member TEXT, created_at TEXT NOT NULL)""")
                db.run("INSERT INTO coaching_interest(name, email, note, member, created_at) VALUES (?,?,?,?,?)",
                       (name, email, note, member, db.now_iso()))
            except Exception:
                pass
            try:
                to = os.environ.get("COACHING_NOTIFY_EMAIL", "info@gaphs.org")
                body = ("Someone has registered interest in 1:1 coaching on the HSA website.\n\n"
                        "Name: %s\n\nEmail: %s\n\nLogged in as a member: %s\n\nWhat they would like help with:\n%s"
                        % (name or "(not given)", email, member, note or "(nothing written)"))
                helpers.send_mail(to, "Coaching interest: %s" % (name or email), body)
            except Exception:
                pass
            return redirect("/coaching?sent=1#interest")
        return render_template("coaching.html", sent=request.args.get("sent"))

    @bp.before_app_request
    def _edu_request():
        _patch_helpers()
        if request.method not in ("GET", "HEAD"):
            return None
        _edu = is_edu()
        _buyer = request.path == "/my-courses" or request.path.startswith("/purchase/")
        if not _edu and request.path == "/faqs":
            return render_template("faqs.html")
        if not _edu and not _buyer:
            return None
        if _edu and request.path == "/":
            return render_template("edu_home.html", courses=courses_data.COURSES, about=courses_data.ABOUT,
                                   sent=request.args.get("sent"))
        import helpers
        _u = helpers.current_user()
        if _u:
            _claim_purchases(_u)
        if _edu and request.path == "/dashboard":
            return redirect("/my-courses")
        if request.path == "/my-courses":
            if not _u:
                return redirect("/login?next=/my-courses")
            rows = db.q("SELECT p.token, c.title FROM purchases p JOIN content c ON c.id = p.content_id "
                        "WHERE p.user_id = ? ORDER BY p.id DESC", (_u["id"],))
            return render_template("edu_my_courses.html", rows=rows)
        pm = re.match(r"^/purchase/([^/]+)$", request.path)
        if pm:
            p = db.q("SELECT * FROM purchases WHERE token = ?", (pm.group(1),), one=True)
            if p:
                if _u and (_u["is_admin"] or p["user_id"] == _u["id"]):
                    return None
                if _u:
                    flash("That purchase belongs to a different account. Log in with the email you bought with.", "error")
                    return redirect("/my-courses")
                if not p["user_id"] and p["email"]:
                    try:
                        _o, _t = _ensure_account(p["email"])
                        if _o:
                            db.run("UPDATE purchases SET user_id = ? WHERE id = ? AND user_id IS NULL", (_o["id"], p["id"]))
                            p = db.q("SELECT * FROM purchases WHERE id = ?", (p["id"],), one=True)
                    except Exception:
                        pass
                owner = db.q("SELECT reset_token FROM users WHERE id = ?", (p["user_id"],), one=True) if p["user_id"] else None
                if owner and owner["reset_token"]:
                    flash("Choose a password so you can log in and watch whenever you like.", "info")
                    return redirect("/reset/" + owner["reset_token"])
                return redirect("/login?next=/purchase/" + pm.group(1))
        if not _edu:
            return None
        if request.path == "/manifest.webmanifest":
            return manifest()
        if request.path == "/terms":
            return render_template("edu_terms.html")
        if request.path == "/library":
            return _edu_library()
        m = re.match(r"^/(?:library|shop)/(\d+)(?:/|$)", request.path)
        if m and _is_hidden(int(m.group(1))):
            abort(404)
        return None

    def edu_notify():
        if request.form.get("website"):
            return redirect("/?sent=1#keep-me-posted")
        email = (request.form.get("email") or "").strip().lower()
        if "@" not in email or "." not in email.split("@")[-1] or len(email) > 200:
            flash("Please enter a valid email address.", "error")
            return redirect("/#keep-me-posted")
        if not db.q("SELECT 1 FROM subscribers WHERE email = ?", (email,), one=True):
            db.run("INSERT INTO subscribers(email, source, created_at) VALUES (?,?,?)",
                   (email, "edu:home", db.now_iso()))
        return redirect("/?sent=1#keep-me-posted")

    bp.add_url_rule("/keep-me-posted", "edu_notify", edu_notify, methods=["POST"])
import edu_mail
_send_access_email = edu_mail.send_access_email
