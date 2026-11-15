"""GAPHS (Global Association of Professional Home Stagers): membership site.  Run locally with:  python3 app.py"""
import os
import secrets
import sqlite3
from datetime import timedelta

from flask import Flask, render_template, request

import db
import stripe_api
from admin_views import admin
from auth_views import auth
from helpers import COUNTRIES, COUNTRY_NAMES
from helpers import (csrf_protect, csrf_token, current_user, embed_for, fmt_date, founding_open, has_access,
                     img_url, media_url, money, plan_label, price, public_plans)
from members_views import members


def _secret_key():
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    path = os.path.join(db.DATA_DIR, "secret_key")
    if not os.path.exists(path):
        with open(path, "w") as fh:
            fh.write(secrets.token_hex(32))
        os.chmod(path, 0o600)
    with open(path) as fh:
        return fh.read().strip()


def _seed_admin():
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not email or not password:
        return
    con = sqlite3.connect(db.DB_PATH)
    row = con.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if row:
        con.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (row[0],))
    else:
        con.execute("""INSERT INTO users(email, pw_hash, name, is_admin, comped, status, created_at, started_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (email, db.hash_password(password), "Admin", 1, 1, "active", db.now_iso(), db.now_iso()))
    con.commit()
    con.close()


def _seed_demo_member():
    """Optional test account: set DEMO_MEMBER_EMAIL and DEMO_MEMBER_PASSWORD to get a free, active Member
    (plan "professional") with a hidden business page. Remove the two settings to stop it being recreated."""
    email = os.environ.get("DEMO_MEMBER_EMAIL", "").strip().lower()
    password = os.environ.get("DEMO_MEMBER_PASSWORD", "")
    if not email or not password:
        return
    con = sqlite3.connect(db.DB_PATH)
    if not con.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        now = db.now_iso()
        cur = con.execute("""INSERT INTO users(email, pw_hash, name, plan, billing, status, comped, created_at, started_at,
                                               qualifying_course, agreed_at)
                             VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                          (email, db.hash_password(password), "Test Member", "professional", "annual", "active", 1,
                           now, now, "GAPHS test account", now))
        slug = "gaphs-test-studio"
        n = 1
        while con.execute("SELECT 1 FROM profiles WHERE slug = ?", (slug,)).fetchone():
            n += 1
            slug = "gaphs-test-studio-%d" % n
        con.execute("""INSERT INTO profiles(user_id, business_name, slug, tagline, bio, location, country, services,
                                            contact_email, published, approved)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (cur.lastrowid, "GAPHS Test Studio", slug, "A test account for the GAPHS board",
                     "This is a test business page. It is hidden from the directory until you tick Show my page.",
                     "Madrid", "Spain", "Consultation, occupied staging, vacant staging", email, 0, 1))
        con.commit()
    con.close()


WELCOME_POSTS = {
    "Introductions": ("Welcome to the GAPHS members' forum", """Welcome to the members' forum of the Global Association of Professional Home Stagers. This section is dedicated to introductions among members worldwide.

When introducing yourself, you may wish to include:
- Your name, your business and the country in which you practise
- Your principal areas of activity
- Your professional interests within the Association

Introductions help members connect and collaborate across borders.

Kind regards,
The GAPHS Board"""),
    "Projects and ideas": ("Projects and professional exchange", """This section is dedicated to sharing projects, raising questions and exchanging professional practice.

Members are invited to share:
- Recent projects, with before and after photographs (with the client's permission)
- Professional questions on which they would value colleagues' views
- Products, suppliers or methods they recommend

Your experience may be of considerable value to fellow members.

Kind regards,
The GAPHS Board"""),
    "Business and pricing": ("Business practice and pricing", """This section is dedicated to the business side of the profession.

Suggested topics include:
- Pricing of services
- Business development and client acquisition
- Working with real estate agents and developers
- Market conditions in your country

All contributions should be constructive and respectful, in accordance with the GAPHS Code of Ethics and Conduct.

Kind regards,
The GAPHS Board"""),
}

OLD_WELCOME_POSTS = {'Introductions': ('Welcome to the GAPHS community', "Welcome to the members' forum of the Global Association of Professional Home Stagers. This is the place to say hello and let fellow members around the world get to know you.\n\nTell us:\n- Your name, your business and the country you work in\n- The kind of staging you do most\n- What you would like to get from being part of GAPHS\n\nEveryone here started somewhere, and every introduction helps us connect and support each other across borders.\n\nWith warm regards,\nThe GAPHS Board"), 'Projects and ideas': ("Share what you're working on", "This is our space to celebrate projects, ask questions and swap what works.\n\nYou could share:\n- A recent staging, with before and after photos (with your client's permission)\n- A challenge you would like fresh eyes on\n- A product, supplier or method you can't live without\n\nYour experience could be exactly what another member needs today.\n\nWith warm regards,\nThe GAPHS Board"), 'Business and pricing': ("Let's talk business", "Running a staging business is easier when you can talk it through with peers.\n\nGood topics to start with:\n- How you price your services\n- Finding and winning clients\n- Working with real estate agents and developers\n- What works in your market, and what doesn't\n\nPlease be open, generous and kind, and keep to our Code of Ethics and Conduct.\n\nWith warm regards,\nThe GAPHS Board")}


def _update_welcome_v2():
    """One-time: bring the pinned welcome threads already posted into the formal wording."""
    con = sqlite3.connect(db.DB_PATH)
    try:
        if con.execute("SELECT 1 FROM settings WHERE key = 'welcome_v2'").fetchone():
            return
        for cat, (old_subject, old_body) in OLD_WELCOME_POSTS.items():
            new_subject, new_body = WELCOME_POSTS[cat]
            for (tid,) in con.execute("SELECT id FROM threads WHERE title = ?", (old_subject,)).fetchall():
                con.execute("UPDATE threads SET title = ? WHERE id = ?", (new_subject, tid))
                con.execute("UPDATE posts SET body = ? WHERE thread_id = ? AND body = ?", (new_body, tid, old_body))
        con.execute("INSERT INTO settings(key, value) VALUES ('welcome_v2', '1')")
        con.commit()
    finally:
        con.close()


def _seed_welcome():
    """One-time: post a pinned welcome thread from the admin account in each forum topic."""
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    if not email:
        return
    con = sqlite3.connect(db.DB_PATH)
    try:
        if con.execute("SELECT 1 FROM settings WHERE key = 'welcome_v1'").fetchone():
            return
        admin = con.execute("SELECT id, name FROM users WHERE email = ?", (email,)).fetchone()
        if not admin:
            return
        if admin[1] in ("", "Admin"):
            con.execute("UPDATE users SET name = ? WHERE id = ?", ("GAPHS", admin[0]))
        now = db.now_iso()
        for title, (subject, body) in WELCOME_POSTS.items():
            cat = con.execute("SELECT id FROM forum_categories WHERE title = ?", (title,)).fetchone()
            if not cat:
                continue
            cur = con.execute("INSERT INTO threads(category_id, user_id, title, pinned, created_at, last_post_at)"
                              " VALUES (?,?,?,?,?,?)", (cat[0], admin[0], subject, 1, now, now))
            con.execute("INSERT INTO posts(thread_id, user_id, body, created_at) VALUES (?,?,?,?)",
                        (cur.lastrowid, admin[0], body, now))
        con.execute("INSERT INTO settings(key, value) VALUES ('welcome_v1', '1')")
        con.commit()
    finally:
        con.close()


# DRAFT shop prices for non-members, in cents (members open everything free). Change them in Admin > Content.
GUIDE_PRICE = 999
COURSE_PRICE = 24700
GIFT_SLUG = "the-agents-guide-to-home-staging"   # free guide offered on the home page in exchange for an email


def _seed_library_v1():
    """One-time: the GAPHS Library. The Atelier Series guides and their video guides, and the course
    Home Staging for Real Estate Agents with its lessons and twelve downloads. Covers come from seed/;
    the PDFs and videos stay in Google Drive until Admin > Content > Import files from Google Drive copies them in."""
    import shutil
    from seed_data import COURSE, DOWNLOADS, GUIDES, download_slug, lesson_body, narration_by_slide
    con = sqlite3.connect(db.DB_PATH)
    try:
        if con.execute("SELECT 1 FROM settings WHERE key = 'gaphs_library_v1'").fetchone():
            return
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed")
        now = db.now_iso()

        def cover(stem):
            src = os.path.join(base, stem + ".jpg")
            if not os.path.exists(src):
                return ""
            name = secrets.token_hex(10) + ".jpg"
            shutil.copyfile(src, os.path.join(db.PUBLIC_UPLOADS, name))
            return name

        def add(title, kind, desc, cov, drive_id, price, sort, featured, category):
            return con.execute("""INSERT INTO content(title, kind, description, cover, video_url, file_private, drip_days,
                                  price, sort, published, created_at, featured, category, drive_id)
                                  VALUES (?,?,?,?,'','',0,?,?,1,?,?,?,?)""",
                               (title, kind, desc, cov, price, sort, now, featured, category, drive_id)).lastrowid

        # the course: first in the Library and in the home page slider
        cid = add(COURSE["title"], "course", COURSE["description"].replace("**", ""), cover(COURSE["slug"]), "",
                  COURSE_PRICE, -1, 1, "course")
        slides = narration_by_slide(os.path.join(base, "agents_course_narration.txt"))
        sort = 0
        for title, summary, first, last in COURSE["lessons"]:
            con.execute("""INSERT INTO lessons(content_id, title, kind, video_url, file_private, drip_days, sort, body, drive_id)
                           VALUES (?,?,'video','','',0,?,?,'')""",
                        (cid, title, sort, summary + "\n\n" + lesson_body(slides, first, last)))
            sort += 1
        con.execute("""INSERT INTO lessons(content_id, title, kind, video_url, file_private, drip_days, sort, body, drive_id)
                       VALUES (?,?,'pdf','','',0,?,?,?)""",
                    (cid, "Course slides", sort, "All the course slides in one PDF, to follow along or print.", COURSE["slides_pdf"]))
        sort += 1
        for no, title, desc, drive_id in DOWNLOADS:
            con.execute("""INSERT INTO lessons(content_id, title, kind, video_url, file_private, drip_days, sort, body, drive_id)
                           VALUES (?,?,'pdf','','',0,?,?,?)""",
                        (cid, "Download %s: %s" % (no, title), sort, desc, drive_id))
            sort += 1
        # the Atelier Series guides and their video guides
        gift_id = None
        for i, g in enumerate(GUIDES):
            gift = g["slug"] == GIFT_SLUG
            gid = add(g["title"], "pdf", "The Atelier Series No. %s. %s\n\n%s" % (g["no"], g["subtitle"], g["description"]),
                      cover(g["slug"]), g["pdf"], None if gift else GUIDE_PRICE, 200 + i, 0 if gift else 1, "guide")
            if gift:
                gift_id = gid
            if g["video"]:
                add(g["title"], "video", "The video guide to The Atelier Series No. %s. %s" % (g["no"], g["description"]),
                    cover(g["slug"] + "-video"), g["video"], None, 100 + i, 0, "class")
        if gift_id:
            con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('gift_content_id', ?)", (str(gift_id),))
        con.execute("INSERT INTO settings(key, value) VALUES ('gaphs_library_v1', '1')")
        con.commit()
    finally:
        con.close()


def lesson_text(text):
    """Lesson text to HTML: lines starting with ### become headings, blank lines separate paragraphs. Escaped."""
    from markupsafe import Markup, escape
    out = []
    for block in (text or "").replace("\r\n", "\n").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("### "):
            head, _, rest = block.partition("\n")
            out.append("<h3>%s</h3>" % escape(head[4:].strip()))
            if rest.strip():
                out.append("<p>%s</p>" % escape(rest.strip()).replace("\n", Markup("<br>")))
        else:
            out.append("<p>%s</p>" % escape(block).replace("\n", Markup("<br>")))
    return Markup("".join(out))


def _seed_library_v2():
    """One-time: videos from GAPHS-approved schools (Entre2portes). Free for members; files come from Google Drive."""
    import shutil
    from seed_data import SCHOOL_VIDEOS
    con = sqlite3.connect(db.DB_PATH)
    try:
        if con.execute("SELECT 1 FROM settings WHERE key = 'gaphs_library_v2'").fetchone():
            return
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed")
        for i, v in enumerate(SCHOOL_VIDEOS):
            if con.execute("SELECT 1 FROM content WHERE title = ?", (v["title"],)).fetchone():
                continue
            cname = ""
            if os.path.exists(os.path.join(base, v["slug"] + ".jpg")):
                cname = secrets.token_hex(10) + ".jpg"
                shutil.copyfile(os.path.join(base, v["slug"] + ".jpg"), os.path.join(db.PUBLIC_UPLOADS, cname))
            con.execute("""INSERT INTO content(title, kind, description, cover, video_url, file_private, drip_days,
                           price, sort, published, created_at, featured, category, drive_id)
                           VALUES (?,'video',?,?,'','',0,NULL,?,1,?,0,'school',?)""",
                        (v["title"], v["description"], cname, 150 + i, db.now_iso(), v["drive"]))
        con.execute("INSERT INTO settings(key, value) VALUES ('gaphs_library_v2', '1')")
        con.commit()
    finally:
        con.close()


def create_app():
    app = Flask(__name__)
    db.init_db()
    _seed_admin()
    _seed_demo_member()
    _seed_welcome()
    _update_welcome_v2()
    _seed_library_v1()
    _seed_library_v2()
    site_url = os.environ.get("SITE_URL", "")
    app.config.update(
        SECRET_KEY=_secret_key(),
        MAX_CONTENT_LENGTH=600 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=site_url.startswith("https://"),
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )
    app.teardown_appcontext(db.close_db)
    app.jinja_env.filters["lesson_text"] = lesson_text
    app.before_request(csrf_protect)

    @app.context_processor
    def inject():
        return {
            "user": current_user(), "csrf": csrf_token, "img_url": img_url, "price": price, "money": money,
            "fmt_date": fmt_date, "plan_label": plan_label, "media_url": media_url, "can_access": has_access,
            "test_mode": not stripe_api.enabled(), "founding_open": founding_open(),
            "founding_limit": db.int_setting("founding_limit"), "embed_for": embed_for, "public_plans": public_plans,
            "country_names": COUNTRY_NAMES, "countries": COUNTRIES,
        }

    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        return resp

    for blueprint in (auth, members, admin):
        app.register_blueprint(blueprint)
    import blocklist
    blocklist.init(app)
    import seo
    seo.init(app)
    import blog
    blog.init(app)
    import fonts
    fonts.init(app)

    def message(code, title, text):
        return render_template("message.html", code=code, title=title, text=text), code

    @app.errorhandler(400)
    def bad(e):
        return message(400, "Something went wrong", getattr(e, "description", "Please go back and try again."))

    @app.errorhandler(403)
    def forbidden(e):
        return message(403, "Not available", "You do not have access to this page.")

    @app.errorhandler(404)
    def missing(e):
        return message(404, "Page not found", "That page does not exist, or it is not public.")

    @app.errorhandler(413)
    def too_big(e):
        return message(413, "File too large", "That file is too big to upload here. For large videos, paste a Vimeo or YouTube link instead.")

    if not os.environ.get("HSA_NO_BACKGROUND"):
        import reminders
        reminders.start_background(app)
    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
