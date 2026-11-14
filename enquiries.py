"""Client enquiries from a member's directory page: a contact form that emails the member (the client's
address is the reply-to), sends the association a copy, and keeps a record so enquiries can be counted
per member. Admin > Enquiries shows the totals and the messages."""
import os
import re
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from html import escape

from flask import abort, current_app, flash, redirect, render_template, request, url_for

import db
import helpers
import mails
from admin_views import admin
from helpers import admin_required

COPY_TO = "info@gaphs.org"
_ready = [False]


def ensure():
    if _ready[0]:
        return
    db.run("""CREATE TABLE IF NOT EXISTS enquiries(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, business TEXT NOT NULL DEFAULT '',
        name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '', message TEXT NOT NULL,
        ip TEXT NOT NULL DEFAULT '', delivered INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)""")
    _ready[0] = True


def count(uid):
    """How many enquiries a member has received through their page. Used on their account page."""
    try:
        ensure()
        row = db.q("SELECT COUNT(*) AS n FROM enquiries WHERE user_id = ?", (uid,), one=True)
        return row["n"] if row else 0
    except Exception:
        return 0


def _para(text):
    return ('<p style="margin:0 0 18px;font-size:16px;line-height:1.65;color:#2A2A2A">%s</p>'
            % escape(text).replace("\n", "<br>"))


def _send(to, subject, text, reply_to=None):
    host = os.environ.get("SMTP_HOST", "")
    addr = parseaddr(os.environ.get("MAIL_FROM", "") or os.environ.get("SMTP_USER", ""))[1]
    if not host or not addr or not to:
        return False
    msg = EmailMessage()
    msg["From"] = formataddr(("GAPHS", addr))
    msg["To"] = to
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text)
    inner = "".join(_para(b.strip()) for b in re.split(r"\n\s*\n", text.strip()) if b.strip())
    msg.add_alternative(mails._layout(subject, inner), subtype="html")
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
        client = smtplib.SMTP_SSL(host, port, timeout=20) if port == 465 else smtplib.SMTP(host, port, timeout=20)
        with client as smtp:
            if port != 465:
                smtp.starttls()
            if os.environ.get("SMTP_USER"):
                smtp.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
            smtp.send_message(msg)
        return True
    except Exception as exc:
        current_app.logger.warning("enquiry email to %s failed: %s", to, exc)
        return False


def submit(slug):
    """POST from the form on a business page."""
    ensure()
    p = db.q("""SELECT p.*, u.email AS account_email, u.name AS owner_name FROM profiles p
                JOIN users u ON u.id = p.user_id WHERE p.slug = ?""", (slug,), one=True) or abort(404)
    back = url_for("auth.business", slug=slug)
    if request.form.get("website"):  # hidden field only robots fill in
        return redirect(back + "?sent=1#enquiry")
    name = (request.form.get("name") or "").strip()[:120]
    email = (request.form.get("email") or "").strip().lower()[:200]
    phone = (request.form.get("phone") or "").strip()[:60]
    message = (request.form.get("message") or "").strip()[:4000]
    problem = ""
    if not name or "@" not in email or "." not in email.split("@")[-1]:
        problem = "Please enter your name and a valid email address."
    elif len(message) < 10:
        problem = "Please write a short message so they know how to help."
    else:
        try:
            import forum_extras
            if forum_extras.blocked(message + " " + name):
                problem = "Your message contains language that is not allowed. Please reword it and send again."
        except Exception:
            pass
    ip = (request.headers.get("X-Forwarded-For", request.remote_addr or "") or "").split(",")[0].strip()[:60]
    if not problem:
        recent = db.q("SELECT created_at FROM enquiries WHERE ip = ? ORDER BY id DESC LIMIT 5", (ip,))
        now = db.parse_iso(db.now_iso())
        if len(recent) == 5 and now:
            oldest = db.parse_iso(recent[-1]["created_at"])
            if oldest and (now - oldest).total_seconds() < 3600:
                problem = "You have sent several enquiries in a short time. Please try again later."
    if problem:
        flash(problem, "error")
        return redirect(back + "#enquiry")
    business = p["business_name"] or p["owner_name"] or ""
    to = (p["contact_email"] or "").strip() or p["account_email"]
    site = helpers.site_url()
    details = "Name: %s\nEmail: %s%s" % (name, email, ("\nPhone: %s" % phone) if phone else "")
    ok = _send(to, "New enquiry from your GAPHS directory page",
               "You have a new enquiry through your page in the GAPHS member directory.\n\n%s\n\n"
               "Message:\n%s\n\nReply to this email to answer %s directly.\n\nYour page: %s%s"
               % (details, message, name, site, back), reply_to=email)
    eid = db.run("""INSERT INTO enquiries(user_id, business, name, email, phone, message, ip, delivered, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                 (p["user_id"], business, name, email, phone, message, ip, 1 if ok else 0, db.now_iso()))
    try:
        total = count(p["user_id"])
        _send(os.environ.get("ENQUIRY_COPY_EMAIL", COPY_TO), "Directory enquiry for %s" % business,
              "Copy of an enquiry sent through the GAPHS directory.\n\nFor: %s (%s)\n\n%s\n\nMessage:\n%s\n\n"
              "Delivered to the member: %s\n\nThat makes %d enquir%s for this member. All enquiries: %s/admin/enquiries"
              % (business, to, details, message, "yes" if ok else "NO, the email failed", total,
                 "y" if total == 1 else "ies", site), reply_to=email)
    except Exception as exc:
        current_app.logger.warning("enquiry copy: %s", exc)
    return redirect(back + "?sent=1#enquiry")


@admin.route("/enquiries")
@admin_required
def enquiries():
    ensure()
    totals = db.q("""SELECT e.user_id, MAX(e.business) AS business, COUNT(*) AS n, MAX(e.created_at) AS last_at,
                     p.slug FROM enquiries e LEFT JOIN profiles p ON p.user_id = e.user_id
                     GROUP BY e.user_id ORDER BY n DESC, last_at DESC""")
    uid = request.args.get("member", type=int)
    if uid:
        rows = db.q("SELECT * FROM enquiries WHERE user_id = ? ORDER BY id DESC LIMIT 500", (uid,))
    else:
        rows = db.q("SELECT * FROM enquiries ORDER BY id DESC LIMIT 200")
    total = db.q("SELECT COUNT(*) AS n FROM enquiries", one=True)["n"]
    return render_template("admin/enquiries.html", totals=totals, rows=rows, total=total, member=uid)
