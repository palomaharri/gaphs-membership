"""Accredited membership: a Professional membership at a higher yearly fee, plus an assessed application
(portfolio links and course certificates). The plan stored on the account stays 'professional'; the
application lives in the accreditation table. Admin > Accreditation reviews it: accept, or send feedback."""
import os
import re

from flask import current_app, flash, redirect, render_template, request, url_for

import db
import helpers
import mails
from admin_views import admin
from helpers import admin_required

PRICE_PENCE = 50000
NOTIFY = "info@gaphs.org"
LABELS = {"applied": "Under review", "review": "Resubmitted, under review", "feedback": "Feedback sent",
          "accredited": "Accredited"}
_ready = [False]


def ensure():
    if _ready[0]:
        return
    db.run("""CREATE TABLE IF NOT EXISTS accreditation(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL UNIQUE, years TEXT NOT NULL DEFAULT '',
        projects TEXT NOT NULL DEFAULT '', portfolio TEXT NOT NULL DEFAULT '', certs TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'applied', feedback TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT, decided_at TEXT)""")
    try:  # added later: what the member's renewal date was before an upgrade, to tell when the new fee is paid
        db.run("ALTER TABLE accreditation ADD COLUMN prev TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass
    _ready[0] = True


def price():
    try:
        return int(db.setting("accredited_annual", "") or PRICE_PENCE)
    except (TypeError, ValueError):
        return PRICE_PENCE


def get(uid):
    try:
        ensure()
        return db.q("SELECT * FROM accreditation WHERE user_id = ?", (uid,), one=True)
    except Exception:
        return None


def _mark(user):
    return "u|" + (user["period_end"] or "none")


def is_paid(user, row):
    """Has the Accredited fee been paid? New sign-ups: the membership is active. Upgrades: the membership
    has been paid again since the application (its renewal date has moved)."""
    active = bool(user["comped"] or user["status"] in ("active", "past_due"))
    if not row["prev"]:
        return active
    return active and _mark(user) != row["prev"]


def sync(user, row):
    """Once an upgrade is paid for, the account becomes a Professional (annual) membership."""
    try:
        if row["prev"] and is_paid(user, row) and (user["plan"] != "professional" or user["founding"]):
            db.run("UPDATE users SET plan = 'professional', billing = 'annual', founding = 0 WHERE id = ?", (user["id"],))
    except Exception:
        pass


def status(uid):
    """'' for ordinary members, otherwise applied / review / feedback / accredited. Used in templates."""
    row = get(uid) if uid else None
    if not row:
        return ""
    if row["prev"]:
        u = db.q("SELECT * FROM users WHERE id = ?", (uid,), one=True)
        if u:
            sync(u, row)
            if not is_paid(u, row):
                return ""  # upgrade started but not paid for: still an ordinary member
    return row["status"]


def wants(uid):
    return bool(get(uid))


def _links(text):
    out = []
    for line in re.split(r"[\r\n]+", text or ""):
        line = line.strip()
        if not line:
            continue
        if not re.match(r"^https?://", line, re.I):
            line = "https://" + line
        out.append(line[:500])
    return out[:30]


def validate(form, agree=True):
    errors = []
    if len(_links(form.get("acc_portfolio"))) < 3:
        errors.append("Please add links to at least three portfolio projects, one per line.")
    if not _links(form.get("acc_certs")):
        errors.append("Please add a link to at least one course certificate.")
    if not (form.get("acc_years") or "").strip():
        errors.append("Please tell us how long your company has been trading.")
    if agree and not form.get("agree_accreditation"):
        errors.append("Please tick to agree to the Accreditation Terms.")
    return errors


def _send(to, subject, text):
    """Branded email from the association. Never breaks the page."""
    try:
        import member_invites
        inner = "".join(member_invites._para(b.strip()) for b in re.split(r"\n\s*\n", text.strip()) if b.strip())
        return bool(member_invites._send_many([(to, subject, text, mails._layout(subject, inner))]))
    except Exception as exc:
        try:
            current_app.logger.warning("accreditation email: %s", exc)
            return helpers.send_mail(to, subject, text)
        except Exception:
            return False


def _notify_admin(uid, what):
    try:
        u = db.q("SELECT name, email FROM users WHERE id = ?", (uid,), one=True)
        row = get(uid)
        to = os.environ.get("ACCREDITATION_NOTIFY_EMAIL", NOTIFY)
        text = ("%s\n\nName: %s\n\nEmail: %s\n\nTrading for: %s\n\nProjects completed: %s\n\nPortfolio links:\n%s\n\n"
                "Certificates:\n%s\n\nNotes:\n%s\n\nReview it in Admin, Accreditation: %s/admin/accreditation"
                % (what, u["name"], u["email"], row["years"], row["projects"] or "(not given)", row["portfolio"],
                   row["certs"], row["notes"] or "(none)", helpers.site_url()))
        _send(to, "Accreditation: %s" % u["name"], text)
    except Exception as exc:
        current_app.logger.warning("accreditation notify: %s", exc)


def save(uid, form, resubmit=False):
    """Create or update the application from the form fields."""
    ensure()
    vals = ((form.get("acc_years") or "").strip()[:120], (form.get("acc_projects") or "").strip()[:120],
            "\n".join(_links(form.get("acc_portfolio"))), "\n".join(_links(form.get("acc_certs"))),
            (form.get("acc_notes") or "").strip()[:3000])
    row = get(uid)
    if row:
        new_status = "review" if row["status"] == "feedback" else row["status"]
        db.run("""UPDATE accreditation SET years = ?, projects = ?, portfolio = ?, certs = ?, notes = ?, status = ?,
                  updated_at = ? WHERE user_id = ?""", vals + (new_status, db.now_iso(), uid))
        _notify_admin(uid, "An accreditation application has been updated and resubmitted." if resubmit
                      else "An accreditation application has been updated.")
    else:
        db.run("""INSERT INTO accreditation(user_id, years, projects, portfolio, certs, notes, status, created_at)
                  VALUES (?,?,?,?,?,?,?,?)""", (uid,) + vals + ("applied", db.now_iso()))
        _notify_admin(uid, "A new accreditation application has been submitted. Review starts once the fee is paid.")


# ---- applicant's own page (registered from edu.init on the public blueprint) ------------------------
def my_page():
    user = helpers.current_user()
    if not user:
        flash("Please log in to see your accreditation application.", "info")
        return redirect("/login?next=/accreditation")
    row = get(user["id"])
    errors = []
    if row and row["prev"] and not is_paid(user, row):
        # an upgrade that was started but not paid for: the form stays open so they can finish
        if request.method == "POST":
            errors = validate(request.form)
            if not errors:
                save(user["id"], request.form)
                import auth_views
                return auth_views.start_checkout(user)
        form = request.form if request.method == "POST" else {
            "acc_years": row["years"], "acc_projects": row["projects"], "acc_portfolio": row["portfolio"],
            "acc_certs": row["certs"], "acc_notes": row["notes"]}
        return render_template("accreditation_me.html", row=None, errors=errors, paid=False, label="", form=form)
    if row:
        sync(user, row)
    if not row:
        # Upgrade: an existing member applies. A full new application at the full fee; nothing is credited.
        if request.method == "POST":
            errors = validate(request.form)
            if not errors:
                save(user["id"], request.form)
                db.run("UPDATE accreditation SET prev = ? WHERE user_id = ?", (_mark(user), user["id"]))
                import auth_views
                fresh = db.q("SELECT * FROM users WHERE id = ?", (user["id"],), one=True)
                return auth_views.start_checkout(fresh)
        return render_template("accreditation_me.html", row=None, errors=errors, paid=False, label="",
                               form=request.form if request.method == "POST" else {})
    if request.method == "POST" and row["status"] != "accredited":
        errors = validate(request.form, agree=False)
        if not errors:
            save(user["id"], request.form, resubmit=row["status"] == "feedback")
            flash("Thank you. Your application has been updated and sent to us.", "success")
            return redirect("/accreditation")
    form = request.form if request.method == "POST" else {
        "acc_years": row["years"], "acc_projects": row["projects"], "acc_portfolio": row["portfolio"],
        "acc_certs": row["certs"], "acc_notes": row["notes"]}
    paid = is_paid(user, row)
    return render_template("accreditation_me.html", row=row, form=form, errors=errors, paid=paid,
                           label=LABELS.get(row["status"], row["status"]))


# ---- admin -----------------------------------------------------------------------------------------
@admin.route("/accreditation", methods=["GET", "POST"])
@admin_required
def accreditation():
    ensure()
    site = helpers.site_url()
    if request.method == "POST":
        uid = request.form.get("user_id", type=int)
        do = request.form.get("do", "")
        u = db.q("SELECT * FROM users WHERE id = ?", (uid,), one=True)
        row = get(uid) if u else None
        if not row:
            flash("That application was not found.", "error")
        elif do == "accept":
            db.run("UPDATE accreditation SET status = 'accredited', decided_at = ? WHERE user_id = ?", (db.now_iso(), uid))
            first = (u["name"] or "").strip().split(" ")[0] or "there"
            ok = _send(u["email"], "You are now a GAPHS Accredited member",
                       "Hello %s,\n\nCongratulations. We have reviewed your application, and your company is now an "
                       "GAPHS Accredited member.\n\nYour Accredited status now shows on your directory page, and your "
                       "GAPHS Accredited logo is ready to download from My account: %s/dashboard\n\n"
                       "Your Accredited status runs with your membership year and renews with it.\n\n"
                       "Warm regards,\nThe GAPHS Board\nGlobal Association of Professional Home Stagers" % (first, site))
            flash("Accepted. %s" % ("They have been emailed." if ok else "The email could not be sent."), "success")
        elif do == "feedback":
            text = (request.form.get("feedback") or "").strip()[:4000]
            if not text:
                flash("Write your feedback first.", "error")
            else:
                db.run("UPDATE accreditation SET status = 'feedback', feedback = ?, decided_at = ? WHERE user_id = ?",
                       (text, db.now_iso(), uid))
                first = (u["name"] or "").strip().split(" ")[0] or "there"
                ok = _send(u["email"], "Your GAPHS Accreditation application: our feedback",
                           "Hello %s,\n\nThank you for applying for GAPHS Accredited membership. We have reviewed your "
                           "application, and we would like to see a little more before we can confirm your Accredited "
                           "status. Our feedback is below.\n\n%s\n\nYou have 90 days to update your application, at no "
                           "extra cost. Update it here: %s/accreditation\n\nIn the meantime, your Professional "
                           "membership and directory page stay fully active.\n\n"
                           "Warm regards,\nThe GAPHS Board\nGlobal Association of Professional Home Stagers" % (first, text, site))
                flash("Feedback saved. %s" % ("They have been emailed." if ok else "The email could not be sent."), "success")
        elif do == "remove":
            db.run("DELETE FROM accreditation WHERE user_id = ?", (uid,))
            flash("Application removed. Their account is now an ordinary Professional membership.", "success")
        return redirect(url_for("admin.accreditation"))
    rows = db.q("""SELECT a.*, u.name, u.email, p.business_name, p.slug
                   FROM accreditation a JOIN users u ON u.id = a.user_id
                   LEFT JOIN profiles p ON p.user_id = u.id ORDER BY a.id DESC""")
    users = {u["id"]: u for u in db.q("SELECT * FROM users WHERE id IN (SELECT user_id FROM accreditation)")}
    for r in rows:
        if r["user_id"] in users:
            sync(users[r["user_id"]], r)
    view = [{"r": r, "label": LABELS.get(r["status"], r["status"]),
             "paid": bool(r["user_id"] in users and is_paid(users[r["user_id"]], r)),
             "upgrade": bool(r["prev"]),
             "portfolio": [l for l in r["portfolio"].split("\n") if l],
             "certs": [l for l in r["certs"].split("\n") if l]} for r in rows]
    return render_template("admin/accreditation.html", rows=view)
