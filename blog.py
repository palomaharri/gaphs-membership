"""The GAPHS Journal: public blog at /blog, managed in Admin > Blog.

Posts live in the blog_posts table. On first start the published 2026 posts from the GAPHS
"BLOG POST FOR WEBSITE" sheet are added from seed/blog_posts.json, with cover cards from seed/blog/.
Registered from app.py: blog.init(app).
"""
import json
import os
import re
import secrets
import shutil
import unicodedata
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from markupsafe import Markup, escape

import db
from admin_views import admin
from helpers import admin_required, delete_public, save_image

blog = Blueprint("blog", __name__)
ROOT = os.path.dirname(os.path.abspath(__file__))
CATEGORIES = ["Association news", "Events", "Partnerships", "Member spotlight", "Research", "Business", "Insights"]
PER_PAGE = 12
_ready = [False]


def ensure():
    if _ready[0]:
        return
    db.run("""CREATE TABLE IF NOT EXISTS blog_posts(
        id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT '', excerpt TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '',
        cover TEXT NOT NULL DEFAULT '', published_on TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'published',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    _ready[0] = True


def seed():
    """One-time import of the 2026 posts (setting gaphs_blog_v1)."""
    ensure()
    if db.setting("gaphs_blog_v1"):
        return
    path = os.path.join(ROOT, "seed", "blog_posts.json")
    if os.path.exists(path):
        for p in json.load(open(path, encoding="utf-8")):
            if db.q("SELECT 1 FROM blog_posts WHERE slug = ?", (p["slug"],), one=True):
                continue
            cover = ""
            src = os.path.join(ROOT, "seed", "blog", p.get("cover", ""))
            if p.get("cover") and os.path.exists(src):
                cover = secrets.token_hex(10) + ".jpg"
                shutil.copyfile(src, os.path.join(db.PUBLIC_UPLOADS, cover))
            now = db.now_iso()
            db.run("""INSERT INTO blog_posts(slug, title, category, excerpt, body, cover, published_on, status, created_at, updated_at)
                      VALUES (?,?,?,?,?,?,?,?,?,?)""",
                   (p["slug"], p["title"], p["category"], p["excerpt"], p["body"], cover, p["date"], "published", now, now))
    db.set_setting("gaphs_blog_v1", "1")


def slugify(text):
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:70].strip("-") or "post"


def unique_slug(title, post_id=None):
    base = slugify(title)
    slug, n = base, 1
    while True:
        row = db.q("SELECT id FROM blog_posts WHERE slug = ?", (slug,), one=True)
        if not row or row["id"] == post_id:
            return slug
        n += 1
        slug = "%s-%d" % (base, n)


def nice_date(iso):
    try:
        d = date.fromisoformat(iso[:10])
        return "%d %s %d" % (d.day, d.strftime("%B"), d.year)
    except Exception:
        return ""


_URL = re.compile(r"(https?://[^\s<]+[^\s<.,;:!?)\]'\"])")
_BULLET = re.compile(r"^\s*(?:[•\-\*·▪◦●]|\d+[.)])\s+")


def _inline(text):
    html = str(escape(text))
    return _URL.sub(lambda m: '<a href="%s" target="_blank" rel="noopener">%s</a>' % (m.group(1), m.group(1)), html)


def _is_heading(line, nxt):
    s = line.strip()
    return (len(s) <= 90 and not re.search(r"[.,;:!]$", s) and s[:1].isupper() and nxt is not None
            and len(nxt.strip()) > len(s) and not _BULLET.match(s))


def blog_html(text):
    """Post text to HTML: one paragraph per line, short title-like lines become headings, bullet lines become lists."""
    lines = [l.strip() for l in (text or "").replace("\r\n", "\n").replace(" ", "\n").split("\n")]
    lines = [l for l in lines if l]
    out, items = [], []

    def flush():
        if items:
            out.append("<ul>%s</ul>" % "".join("<li>%s</li>" % i for i in items))
            items.clear()

    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if _BULLET.match(line) and not _is_heading(_BULLET.sub("", line), None):
            items.append(_inline(_BULLET.sub("", line)))
            continue
        flush()
        if i > 0 and _is_heading(line, nxt):
            out.append("<h2>%s</h2>" % _inline(line))
        else:
            out.append("<p>%s</p>" % _inline(line))
    flush()
    return Markup("".join(out))


def latest(n=3):
    try:
        ensure()
        return db.q("SELECT * FROM blog_posts WHERE status = 'published' AND published_on <= ? "
                    "ORDER BY published_on DESC, id DESC LIMIT ?", (date.today().isoformat(), n))
    except Exception:
        return []


# ---------- public ----------

@blog.route("/blog")
def index():
    ensure()
    cat = request.args.get("category", "")
    page = max(1, request.args.get("page", 1, type=int))
    where, args = "status = 'published' AND published_on <= ?", [date.today().isoformat()]
    if cat:
        where += " AND category = ?"
        args.append(cat)
    total = db.q("SELECT COUNT(*) AS n FROM blog_posts WHERE " + where, tuple(args), one=True)["n"]
    rows = db.q("SELECT * FROM blog_posts WHERE " + where + " ORDER BY published_on DESC, id DESC LIMIT ? OFFSET ?",
                tuple(args) + (PER_PAGE, (page - 1) * PER_PAGE))
    used = [r["category"] for r in db.q("SELECT DISTINCT category FROM blog_posts WHERE status = 'published'")]
    cats = [c for c in CATEGORIES if c in used] + sorted(c for c in used if c and c not in CATEGORIES)
    return render_template("blog_index.html", posts=rows, cats=cats, cat=cat, page=page,
                           pages=max(1, (total + PER_PAGE - 1) // PER_PAGE), nice_date=nice_date)


@blog.route("/blog/<slug>")
def post(slug):
    ensure()
    p = db.q("SELECT * FROM blog_posts WHERE slug = ?", (slug,), one=True)
    from helpers import current_user
    user = current_user()
    if not p or (p["status"] != "published" and not (user and user["is_admin"])):
        abort(404)
    more = db.q("SELECT * FROM blog_posts WHERE status = 'published' AND id != ? AND published_on <= ? "
                "ORDER BY (category = ?) DESC, published_on DESC LIMIT 3", (p["id"], date.today().isoformat(), p["category"]))
    return render_template("blog_post.html", p=p, body=blog_html(p["body"]), more=more, nice_date=nice_date)


# ---------- admin ----------

@admin.route("/blog")
@admin_required
def blog_list():
    ensure()
    rows = db.q("SELECT * FROM blog_posts ORDER BY published_on DESC, id DESC")
    return render_template("admin/blog.html", posts=rows, nice_date=nice_date)


@admin.route("/blog/new", methods=["GET", "POST"])
@admin.route("/blog/<int:post_id>", methods=["GET", "POST"])
@admin_required
def blog_edit(post_id=None):
    ensure()
    p = db.q("SELECT * FROM blog_posts WHERE id = ?", (post_id,), one=True) if post_id else None
    if post_id and not p:
        abort(404)
    if request.method == "POST":
        if request.form.get("delete") and p:
            if p["cover"]:
                delete_public(p["cover"])
            db.run("DELETE FROM blog_posts WHERE id = ?", (p["id"],))
            flash("Post deleted.", "success")
            return redirect(url_for("admin.blog_list"))
        title = (request.form.get("title") or "").strip()[:200]
        body = (request.form.get("body") or "").strip()
        if not title or not body:
            flash("Please add a title and the text of the post.", "error")
            return render_template("admin/blog_edit.html", p=p, form=request.form, cats=CATEGORIES, today=date.today().isoformat())
        on = (request.form.get("published_on") or "").strip()[:10]
        try:
            date.fromisoformat(on)
        except ValueError:
            on = date.today().isoformat()
        excerpt = (request.form.get("excerpt") or "").strip()[:400]
        if not excerpt:
            first = next((l.strip() for l in body.split("\n") if l.strip()), "")
            excerpt = first if len(first) <= 230 else first[:227].rsplit(" ", 1)[0] + "…"
        status = "draft" if request.form.get("status") == "draft" else "published"
        category = (request.form.get("category") or "").strip()[:60]
        slug = unique_slug(request.form.get("slug") or title, p["id"] if p else None)
        cover = p["cover"] if p else ""
        try:
            new = save_image(request.files.get("cover"), max_px=1600, max_bytes=8 * 1024 * 1024)
        except ValueError as e:
            flash(str(e), "error")
            return render_template("admin/blog_edit.html", p=p, form=request.form, cats=CATEGORIES, today=date.today().isoformat())
        if new:
            if cover:
                delete_public(cover)
            cover = new
        now = db.now_iso()
        if p:
            db.run("""UPDATE blog_posts SET slug=?, title=?, category=?, excerpt=?, body=?, cover=?, published_on=?,
                      status=?, updated_at=? WHERE id=?""",
                   (slug, title, category, excerpt, body, cover, on, status, now, p["id"]))
        else:
            db.run("""INSERT INTO blog_posts(slug, title, category, excerpt, body, cover, published_on, status, created_at, updated_at)
                      VALUES (?,?,?,?,?,?,?,?,?,?)""", (slug, title, category, excerpt, body, cover, on, status, now, now))
        flash("Post saved." if status == "published" else "Draft saved. It is not on the website yet.", "success")
        return redirect(url_for("admin.blog_list"))
    return render_template("admin/blog_edit.html", p=p, form=None, cats=CATEGORIES, today=date.today().isoformat())


def init(app):
    app.register_blueprint(blog)
    app.jinja_env.globals["latest_posts"] = latest
    app.jinja_env.globals["nice_date"] = nice_date
    with app.app_context():
        try:
            seed()
        except Exception as e:  # never stop the site starting because of the blog import
            app.logger.warning("Blog import skipped: %s", e)
