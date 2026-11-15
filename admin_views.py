"""Admin area: members, prices and wording, content, images, forum categories, orders."""
import secrets

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

import db
import reminders
from helpers import (admin_required, current_user, delete_private, delete_public, founding_taken, money,
                     save_image, save_private)

admin = Blueprint("admin", __name__, url_prefix="/admin")

SITE_IMAGE_SLOTS = [
    ("hero", "Top of the home page"),
    ("bed", "'About GAPHS' photo"),
    ("comm", "'Community' photo"),
    ("dir1", "Directory page, photo 1"), ("dir2", "Directory page, photo 2"), ("dir3", "Directory page, photo 3"),
]


def pence(value, default=0):
    try:
        return max(0, int(round(float((value or "").replace(",", "").replace("€", "").strip()) * 100)))
    except ValueError:
        return default


@admin.route("/")
@admin_required
def index():
    stats = {
        "active": db.q("SELECT COUNT(*) AS n FROM users WHERE status IN ('active','past_due')", one=True)["n"],
        "members": db.q("SELECT COUNT(*) AS n FROM users WHERE status IN ('active','past_due') AND plan='member'", one=True)["n"],
        "pros": db.q("SELECT COUNT(*) AS n FROM users WHERE status IN ('active','past_due') AND plan='professional'", one=True)["n"],
        "pending_pay": db.q("SELECT COUNT(*) AS n FROM users WHERE status = 'pending' AND plan IS NOT NULL", one=True)["n"],
        "awaiting": db.q("""SELECT COUNT(*) AS n FROM profiles p JOIN users u ON u.id = p.user_id
                            WHERE p.approved = 0 AND u.status IN ('active','past_due')""", one=True)["n"],
        "founding": founding_taken(), "founding_limit": db.int_setting("founding_limit"),
        "orders": db.q("SELECT COUNT(*) AS n FROM purchases", one=True)["n"],
    }
    return render_template("admin/index.html", stats=stats)


# ---- members --------------------------------------------------------------------
@admin.route("/members")
@admin_required
def members():
    term = (request.args.get("q") or "").strip()
    flt = request.args.get("filter", "")
    sql = """SELECT u.*, p.business_name, p.approved, p.slug FROM users u LEFT JOIN profiles p ON p.user_id = u.id WHERE 1=1"""
    args = []
    if term:
        sql += " AND (u.email LIKE ? OR u.name LIKE ? OR p.business_name LIKE ?)"
        args += ["%" + term + "%"] * 3
    if flt == "awaiting":
        sql += " AND p.approved = 0 AND u.status IN ('active','past_due')"
    elif flt in ("active", "pending", "canceled", "past_due"):
        sql += " AND u.status = ?"
        args.append(flt)
    sql += " ORDER BY u.created_at DESC LIMIT 500"
    return render_template("admin/members.html", rows=db.q(sql, args), term=term, flt=flt)


@admin.route("/members/add-admin", methods=["POST"])
@admin_required
def add_admin():
    """Create an admin login without a membership: no payment, no business page. They choose their own password."""
    from datetime import datetime, timedelta, timezone
    import helpers
    email = (request.form.get("email") or "").strip().lower()
    name = (request.form.get("name") or "").strip()
    if "@" not in email or "." not in email.split("@")[-1]:
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("admin.members"))
    existing = db.q("SELECT * FROM users WHERE email = ?", (email,), one=True)
    if existing:
        db.run("UPDATE users SET is_admin = 1 WHERE id = ?", (existing["id"],))
        flash("%s already had an account and now has admin access." % email, "success")
        return redirect(url_for("admin.members", q=email))
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.run("INSERT INTO users(email, pw_hash, name, created_at, reset_token, reset_expires, is_admin) VALUES (?,?,?,?,?,?,1)",
           (email, db.hash_password(secrets.token_urlsafe(24)), name, db.now_iso(), token, expires))
    link = helpers.site_url() + "/reset/" + token
    body = ("You have been given admin access to GAPHS website.\n\n"
            "Choose your password. The link works for 7 days.\n\n"
            "Choose my password: %s\n\n"
            "After that, log in with this email address and your password." % link)
    sent = False
    try:
        sent = helpers.send_mail(email, "Your admin access", body)
    except Exception:
        sent = False
    if sent:
        flash("Admin added. %s has been emailed a link to choose a password." % email, "success")
    else:
        flash("Admin added, but the email could not be sent. Ask them to use Forgot your password on the login page.", "error")
    return redirect(url_for("admin.members", q=email))


@admin.route("/members/<int:user_id>/action", methods=["POST"])
@admin_required
def member_action(user_id):
    me = current_user()
    u = db.q("SELECT * FROM users WHERE id = ?", (user_id,), one=True) or abort(404)
    act = request.form.get("action")
    if act == "approve":
        db.run("UPDATE profiles SET approved = 1 WHERE user_id = ?", (user_id,))
        flash("Listing approved.", "success")
    elif act == "unapprove":
        db.run("UPDATE profiles SET approved = 0 WHERE user_id = ?", (user_id,))
        flash("Listing taken offline.", "success")
    elif act == "comp":
        db.run("UPDATE users SET comped = ?, status = CASE WHEN ? = 1 AND status = 'pending' THEN 'active' ELSE status END, "
               "started_at = COALESCE(started_at, ?) WHERE id = ?",
               (0 if u["comped"] else 1, 0 if u["comped"] else 1, db.now_iso(), user_id))
        flash("Complimentary access %s." % ("removed" if u["comped"] else "given"), "success")
    elif act == "founding":
        db.run("UPDATE users SET founding = ? WHERE id = ?", (0 if u["founding"] else 1, user_id))
        flash("Founding rate flag updated.", "success")
    elif act == "admin":
        if user_id == me["id"]:
            flash("You cannot remove your own admin access.", "error")
        else:
            db.run("UPDATE users SET is_admin = ? WHERE id = ?", (0 if u["is_admin"] else 1, user_id))
            flash("Admin access updated.", "success")
    elif act == "temp_password":
        temp = secrets.token_urlsafe(9)
        db.run("UPDATE users SET pw_hash = ? WHERE id = ?", (db.hash_password(temp), user_id))
        flash("Temporary password for %s: %s (shown once; ask them to change it)." % (u["email"], temp), "success")
    elif act == "delete":
        if user_id == me["id"] or u["is_admin"]:
            flash("Admin accounts cannot be deleted here. Remove admin access first.", "error")
        else:
            prof = db.q("SELECT logo FROM profiles WHERE user_id = ?", (user_id,), one=True)
            for ph in db.q("SELECT path FROM gallery WHERE user_id = ?", (user_id,)):
                delete_public(ph["path"])
            if prof and prof["logo"]:
                delete_public(prof["logo"])
            db.run("DELETE FROM posts WHERE thread_id IN (SELECT id FROM threads WHERE user_id = ?)", (user_id,))
            db.run("DELETE FROM posts WHERE user_id = ?", (user_id,))
            db.run("DELETE FROM threads WHERE user_id = ?", (user_id,))
            db.run("DELETE FROM reminders WHERE user_id = ?", (user_id,))
            db.run("DELETE FROM gallery WHERE user_id = ?", (user_id,))
            db.run("DELETE FROM profiles WHERE user_id = ?", (user_id,))
            db.run("UPDATE purchases SET user_id = NULL WHERE user_id = ?", (user_id,))
            db.run("DELETE FROM users WHERE id = ?", (user_id,))
            flash("Account for %s deleted." % u["email"], "success")
            return redirect(url_for("admin.members"))
    elif act == "plan":
        plan = request.form.get("plan")
        billing = request.form.get("billing")
        if plan in ("member", "professional") and billing in ("annual", "monthly"):
            db.run("UPDATE users SET plan = ?, billing = ? WHERE id = ?", (plan, billing, user_id))
            flash("Plan updated.", "success")
    return redirect(request.referrer or url_for("admin.members"))


# ---- prices and wording -----------------------------------------------------------
@admin.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    if request.method == "POST":
        for key in ("member_annual", "member_monthly", "pro_annual", "pro_monthly", "founding"):
            db.set_setting(key, pence(request.form.get(key), db.int_setting(key)))
        try:
            db.set_setting("founding_limit", max(0, int(request.form.get("founding_limit") or 0)))
        except ValueError:
            pass
        db.set_setting("founding_code", (request.form.get("founding_code") or "").strip())
        plans = [p for p in ("member", "professional") if request.form.get("public_" + p)]
        db.set_setting("public_plans", ",".join(plans))
        flash("Settings saved.", "success")
        return redirect(url_for("admin.settings"))
    vals = {k: db.setting(k) for k in db.DEFAULT_SETTINGS}
    return render_template("admin/settings.html", v=vals, money=money, taken=founding_taken())


@admin.route("/texts", methods=["GET", "POST"])
@admin_required
def texts():
    if request.method == "POST":
        for key in ("terms_text", "code_text", "privacy_text"):
            if key in request.form:
                db.set_setting(key, request.form[key].replace("\r\n", "\n")[:200000])
        flash("Saved. New members agree to the updated wording.", "success")
        return redirect(url_for("admin.texts"))
    return render_template("admin/texts.html", v={k: db.setting(k) for k in ("terms_text", "code_text", "privacy_text")})


# ---- content ------------------------------------------------------------------------
def content_form_values():
    kind = request.form.get("kind", "video")
    if kind not in ("video", "pdf", "course"):
        kind = "video"
    price = (request.form.get("price") or "").strip()
    try:
        drip = max(0, int(request.form.get("drip_days") or 0))
    except ValueError:
        drip = 0
    return {
        "title": (request.form.get("title") or "").strip()[:160],
        "kind": kind,
        "description": (request.form.get("description") or "").strip()[:4000],
        "video_url": (request.form.get("video_url") or "").strip()[:500],
        "drip_days": drip,
        "price": pence(price) if price else None,
        "published": 1 if request.form.get("published") else 0,
        "featured": 1 if request.form.get("featured") else 0,
        "category": request.form.get("category") if request.form.get("category") in ("course", "class", "masterclass", "webinar", "guide", "report", "ebook", "template") else "",
    }


@admin.route("/content")
@admin_required
def content():
    rows = db.q("""SELECT c.*, (SELECT COUNT(*) FROM lessons l WHERE l.content_id = c.id) AS n_lessons,
                   (SELECT COUNT(*) FROM purchases p WHERE p.content_id = c.id) AS n_sold
                   FROM content c ORDER BY c.sort, c.id""")
    import drive_import
    st = dict(drive_import.state, pending=len(drive_import.pending()))
    return render_template("admin/content.html", rows=rows, drive_state=lambda: st)


@admin.route("/content/new", methods=["GET", "POST"])
@admin.route("/content/<int:item_id>", methods=["GET", "POST"])
@admin_required
def content_edit(item_id=None):
    c = db.q("SELECT * FROM content WHERE id = ?", (item_id,), one=True) if item_id else None
    if item_id and not c:
        abort(404)
    if request.method == "POST":
        v = content_form_values()
        if not v["title"]:
            flash("Please give it a title.", "error")
        else:
            try:
                cover = save_image(request.files.get("cover"), 1200)
                private = save_private(request.files.get("file")) if v["kind"] != "course" else None
            except ValueError as exc:
                flash(str(exc), "error")
                return render_template("admin/content_edit.html", c=c, lessons=[])
            if c:
                db.run("""UPDATE content SET title=?, kind=?, description=?, video_url=?, drip_days=?, price=?, published=?, featured=?, category=?
                          WHERE id=?""", (v["title"], v["kind"], v["description"], v["video_url"], v["drip_days"],
                                          v["price"], v["published"], v["featured"], v["category"], item_id))
                if cover:
                    delete_public(c["cover"])
                    db.run("UPDATE content SET cover = ? WHERE id = ?", (cover, item_id))
                if private:
                    delete_private(c["file_private"])
                    db.run("UPDATE content SET file_private = ? WHERE id = ?", (private, item_id))
                if request.form.get("remove_file"):
                    delete_private(c["file_private"])
                    db.run("UPDATE content SET file_private = '' WHERE id = ?", (item_id,))
            else:
                order = db.q("SELECT COALESCE(MAX(sort), 0) + 1 AS n FROM content", one=True)["n"]
                item_id = db.run("""INSERT INTO content(title, kind, description, cover, video_url, file_private, drip_days,
                                    price, sort, published, featured, category, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                 (v["title"], v["kind"], v["description"], cover or "", v["video_url"], private or "",
                                  v["drip_days"], v["price"], order, v["published"], v["featured"], v["category"], db.now_iso()))
            flash("Saved.", "success")
            return redirect(url_for("admin.content_edit", item_id=item_id))
    lessons = db.q("SELECT * FROM lessons WHERE content_id = ? ORDER BY sort, id", (item_id,)) if item_id else []
    return render_template("admin/content_edit.html", c=c, lessons=lessons)


@admin.route("/content/<int:item_id>/delete", methods=["POST"])
@admin_required
def content_delete(item_id):
    c = db.q("SELECT * FROM content WHERE id = ?", (item_id,), one=True) or abort(404)
    if db.q("SELECT id FROM purchases WHERE content_id = ?", (item_id,), one=True):
        db.run("UPDATE content SET published = 0 WHERE id = ?", (item_id,))
        flash("It has been bought before, so it was hidden instead of deleted.", "info")
        return redirect(url_for("admin.content"))
    for l in db.q("SELECT * FROM lessons WHERE content_id = ?", (item_id,)):
        delete_private(l["file_private"])
    delete_public(c["cover"])
    delete_private(c["file_private"])
    db.run("DELETE FROM content WHERE id = ?", (item_id,))
    flash("Deleted.", "success")
    return redirect(url_for("admin.content"))


@admin.route("/content/<int:item_id>/lessons", methods=["POST"])
@admin_required
def lesson_add(item_id):
    db.q("SELECT id FROM content WHERE id = ?", (item_id,), one=True) or abort(404)
    title = (request.form.get("title") or "").strip()[:160]
    kind = "pdf" if request.form.get("kind") == "pdf" else "video"
    try:
        drip = max(0, int(request.form.get("drip_days") or 0))
    except ValueError:
        drip = 0
    if not title:
        flash("Please give the lesson a title.", "error")
        return redirect(url_for("admin.content_edit", item_id=item_id))
    try:
        private = save_private(request.files.get("file"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.content_edit", item_id=item_id))
    order = db.q("SELECT COALESCE(MAX(sort), 0) + 1 AS n FROM lessons WHERE content_id = ?", (item_id,), one=True)["n"]
    db.run("""INSERT INTO lessons(content_id, title, kind, video_url, file_private, drip_days, sort, body)
              VALUES (?,?,?,?,?,?,?,?)""",
           (item_id, title, kind, (request.form.get("video_url") or "").strip()[:500], private or "", drip, order,
            (request.form.get("body") or "").strip()[:60000]))
    flash("Lesson added.", "success")
    return redirect(url_for("admin.content_edit", item_id=item_id) + "#lessons")


@admin.route("/lessons/<int:lesson_id>", methods=["POST"])
@admin_required
def lesson_update(lesson_id):
    l = db.q("SELECT * FROM lessons WHERE id = ?", (lesson_id,), one=True) or abort(404)
    act = request.form.get("action")
    if act == "delete":
        delete_private(l["file_private"])
        db.run("DELETE FROM lessons WHERE id = ?", (lesson_id,))
        flash("Lesson removed.", "success")
    elif act in ("up", "down"):
        sibs = db.q("SELECT id FROM lessons WHERE content_id = ? ORDER BY sort, id", (l["content_id"],))
        ids = [s["id"] for s in sibs]
        i = ids.index(lesson_id)
        j = i - 1 if act == "up" else i + 1
        if 0 <= j < len(ids):
            ids[i], ids[j] = ids[j], ids[i]
            for n, lid in enumerate(ids):
                db.run("UPDATE lessons SET sort = ? WHERE id = ?", (n, lid))
    else:
        title = (request.form.get("title") or l["title"]).strip()[:160]
        try:
            drip = max(0, int(request.form.get("drip_days") or 0))
        except ValueError:
            drip = l["drip_days"]
        try:
            private = save_private(request.files.get("file"))
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("admin.content_edit", item_id=l["content_id"]) + "#lessons")
        db.run("UPDATE lessons SET title = ?, drip_days = ?, video_url = ?, body = ? WHERE id = ?",
               (title, drip, (request.form.get("video_url") or "").strip()[:500],
                (request.form.get("body") or "").strip()[:60000], lesson_id))
        if private:
            delete_private(l["file_private"])
            db.run("UPDATE lessons SET file_private = ? WHERE id = ?", (private, lesson_id))
        flash("Lesson saved.", "success")
    return redirect(url_for("admin.content_edit", item_id=l["content_id"]) + "#lessons")


# ---- images, forum, orders --------------------------------------------------------------
@admin.route("/images", methods=["GET", "POST"])
@admin_required
def images():
    if request.method == "POST":
        key = request.form.get("key")
        if key not in dict(SITE_IMAGE_SLOTS):
            abort(400)
        if request.form.get("reset"):
            row = db.q("SELECT path FROM site_images WHERE key = ?", (key,), one=True)
            if row:
                delete_public(row["path"])
                db.run("DELETE FROM site_images WHERE key = ?", (key,))
            flash("Back to the original photo.", "success")
        else:
            try:
                name = save_image(request.files.get("image"), 1800)
            except ValueError as exc:
                flash(str(exc), "error")
                return redirect(url_for("admin.images"))
            if not name:
                flash("Choose a photo first.", "error")
                return redirect(url_for("admin.images"))
            old = db.q("SELECT path FROM site_images WHERE key = ?", (key,), one=True)
            if old:
                delete_public(old["path"])
            db.run("INSERT INTO site_images(key, path) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET path = excluded.path",
                   (key, name))
            flash("Photo replaced.", "success")
        return redirect(url_for("admin.images"))
    return render_template("admin/images.html", slots=SITE_IMAGE_SLOTS)


@admin.route("/forum", methods=["GET", "POST"])
@admin_required
def forum():
    if request.method == "POST":
        act = request.form.get("action")
        if act == "add":
            title = (request.form.get("title") or "").strip()[:120]
            if title:
                order = db.q("SELECT COALESCE(MAX(sort), 0) + 1 AS n FROM forum_categories", one=True)["n"]
                db.run("INSERT INTO forum_categories(title, description, sort) VALUES (?,?,?)",
                       (title, (request.form.get("description") or "").strip()[:300], order))
        elif act == "save":
            db.run("UPDATE forum_categories SET title = ?, description = ? WHERE id = ?",
                   ((request.form.get("title") or "").strip()[:120], (request.form.get("description") or "").strip()[:300],
                    int(request.form.get("id", 0))))
        elif act == "delete":
            db.run("DELETE FROM forum_categories WHERE id = ?", (int(request.form.get("id", 0)),))
        flash("Saved.", "success")
        return redirect(url_for("admin.forum"))
    return render_template("admin/forum.html", cats=db.q("SELECT * FROM forum_categories ORDER BY sort, id"))


@admin.route("/orders")
@admin_required
def orders():
    rows = db.q("""SELECT pu.*, c.title FROM purchases pu JOIN content c ON c.id = pu.content_id
                   ORDER BY pu.paid_at DESC LIMIT 500""")
    return render_template("admin/orders.html", rows=rows)


# ---- renewals -------------------------------------------------------------------
@admin.route("/renewals", methods=["GET", "POST"])
@admin_required
def renewals():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "days":
            days = ",".join(p.strip() for p in (request.form.get("reminder_days") or "").split(",") if p.strip().isdigit())
            db.set_setting("reminder_days", days or "30,7")
            flash("Reminder timing saved.", "info")
        elif action == "send_due":
            n = reminders.run_due()
            flash("%d reminder%s sent." % (n, "" if n == 1 else "s") if n else
                  "Nothing to send right now (or email is not set up yet).", "info")
        elif action == "send_one":
            u = db.q("SELECT * FROM users WHERE id = ?", (request.form.get("user_id", type=int),), one=True) or abort(404)
            end = db.parse_iso(u["period_end"])
            ok = bool(end) and reminders.send_reminder(u, end, "manual-" + db.now_iso())
            flash("Reminder sent." if ok else "The email could not be sent. Check that email sending is set up.", "info")
        return redirect(url_for("admin.renewals"))
    rows = []
    for u, end, left in reminders.upcoming(90):
        sent = db.q("SELECT kind FROM reminders WHERE user_id=? AND period_end=?", (u["id"], u["period_end"]))
        rows.append({"u": u, "end": end, "left": left, "sent": [r["kind"] for r in sent if not r["kind"].startswith("manual")]})
    return render_template("admin/renewals.html", rows=rows, days=db.setting("reminder_days", "30,7"),
                           smtp=bool(__import__("os").environ.get("SMTP_HOST")))


@admin.route("/members.csv")
@admin_required
def members_csv():
    import csv, io
    from flask import Response
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Name", "Email", "Business", "Plan", "Billing", "Status", "Founding rate", "Joined", "Renews / ends", "Agreed to terms", "Country", "Business address"])
    for r in db.q("""SELECT u.*, p.business_name, p.country, p.address FROM users u LEFT JOIN profiles p ON p.user_id = u.id
                     WHERE u.is_admin = 0 ORDER BY u.created_at DESC"""):
        w.writerow([r["name"], r["email"], r["business_name"] or "", r["plan"] or "", r["billing"] or "", r["status"],
                    "yes" if r["founding"] else "", (r["started_at"] or r["created_at"] or "")[:10],
                    (r["period_end"] or "")[:10], (r["agreed_at"] or "")[:10], r["country"] or "", r["address"] or ""])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=hsa-members.csv"})


@admin.route("/subscribers")
@admin_required
def subscribers():
    rows = db.q("SELECT * FROM subscribers ORDER BY created_at DESC")
    return render_template("admin/subscribers.html", rows=rows)


@admin.route("/subscribers.csv")
@admin_required
def subscribers_csv():
    import csv, io
    from flask import Response
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Email", "Source", "Signed up"])
    for r in db.q("SELECT * FROM subscribers ORDER BY created_at DESC"):
        w.writerow([r["email"], r["source"], r["created_at"][:10]])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=hsa-subscribers.csv"})


INVITE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_invite_code():
    for _ in range(50):
        code = "GAPHS-" + "".join(secrets.choice(INVITE_CHARS) for _ in range(6))
        if not db.q("SELECT 1 FROM invites WHERE code = ?", (code,), one=True):
            return code
    abort(500)


@admin.route("/invites", methods=["GET", "POST"])
@admin_required
def invites():
    if request.method == "POST":
        do = request.form.get("do", "create")
        if do == "create":
            label = (request.form.get("label") or "").strip()[:120]
            count = min(max(request.form.get("count", type=int) or 1, 1), 500)
            uses = min(max(request.form.get("max_uses", type=int) or 1, 1), 100000)
            custom = "".join(ch for ch in (request.form.get("custom") or "").upper() if ch.isalnum() or ch == "-")[:40]
            if custom:
                if db.q("SELECT 1 FROM invites WHERE code = ?", (custom,), one=True):
                    flash("That code already exists.", "error")
                else:
                    db.run("INSERT INTO invites(code, label, max_uses, created_at) VALUES (?,?,?,?)",
                           (custom, label, uses, db.now_iso()))
                    flash("Code %s created." % custom, "success")
            else:
                for _ in range(count):
                    db.run("INSERT INTO invites(code, label, max_uses, created_at) VALUES (?,?,?,?)",
                           (new_invite_code(), label, uses, db.now_iso()))
                flash("%d code%s created." % (count, "" if count == 1 else "s"), "success")
        else:
            iid = request.form.get("id", type=int)
            if do == "toggle":
                db.run("UPDATE invites SET active = 1 - active WHERE id = ?", (iid,))
            elif do == "delete":
                db.run("DELETE FROM invites WHERE id = ?", (iid,))
        return redirect(url_for("admin.invites"))
    from helpers import site_url
    return render_template("admin/invites.html", rows=db.q("SELECT * FROM invites ORDER BY id DESC LIMIT 1000"),
                           base=site_url())


@admin.route("/invites.csv")
@admin_required
def invites_csv():
    import csv, io
    from flask import Response
    from helpers import site_url
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Code", "Label", "Link", "Used", "Allowed", "Active"])
    for r in db.q("SELECT * FROM invites ORDER BY id"):
        w.writerow([r["code"], r["label"], site_url() + "/invite?code=" + r["code"], r["uses"], r["max_uses"],
                    "yes" if r["active"] else "no"])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=hsa-invite-codes.csv"})


@admin.route("/messages", methods=["GET", "POST"])
@admin_required
def messages():
    if request.method == "POST":
        mid = request.form.get("id", type=int)
        if mid:
            if request.form.get("do") == "delete":
                db.run("DELETE FROM messages WHERE id = ?", (mid,))
            else:
                db.run("UPDATE messages SET handled = 1 - handled WHERE id = ?", (mid,))
        return redirect(url_for("admin.messages"))
    return render_template("admin/messages.html", rows=db.q("SELECT * FROM messages ORDER BY handled, created_at DESC"))


import member_invites  # noqa: E402,F401  (adds Admin > Member invites; must stay at the end of this file)
import accreditation  # noqa: E402,F401  (adds Admin > Accreditation; must stay at the end of this file)
import enquiries  # noqa: E402,F401  (adds Admin > Enquiries; must stay at the end of this file)
import drive_import  # noqa: E402,F401  (adds Admin > Content > Import files from Google Drive; must stay at the end of this file)
import blog  # noqa: E402,F401  (adds Admin > Blog; the public pages are registered in app.py with blog.init; must stay at the end of this file)
