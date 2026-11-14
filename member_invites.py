"""Invites for existing members: one personal code each, Professional plan, valid until their renewal date.
Admin > Member invites. Nothing is ever sent until an admin presses a Send button on that page."""
import csv
import io
import os
import re
import smtplib
import time
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from html import escape

from flask import current_app, flash, redirect, render_template, request, url_for

import db
import helpers
import mails
from admin_views import admin, new_invite_code
from helpers import admin_required, current_user

SENDER_NAME = "GAPHS"
REPLY_TO = "info@gaphs.org"

DEFAULT_SUBJECT = "Your GAPHS directory page is ready to create"
DEFAULT_BODY = """Hello [First name],

GAPHS has a new members' platform, and as an existing member you are among the first to use it.

It brings together everything your membership includes: a page for your business in the GAPHS member directory, where clients and real estate agents can find you, the Library of courses, video guides and the Atelier Series guides, and a members' forum to share ideas with professionals across countries.

Before we open the platform to everyone, we are giving existing members the chance to create their directory page first, so it is ready when visitors arrive.

[Link]

What to do (about five minutes):

1. Click your personal link above.
2. Choose a password.
3. Add your business details: logo, photos, profile, services, website and social links.
4. Accept the Terms, Code of Ethics and Privacy Policy.

[Membership line]

Your link is personal and works once. If anything doesn't work, reply to this email and we will help.

Warm regards,
Paloma Harrington
Vice President, GAPHS"""

DEFAULT_REMINDER_SUBJECT = "A reminder: your GAPHS directory page"
DEFAULT_REMINDER_BODY = """Hello [First name],

Here is your link again. The new GAPHS members' platform is live, and your directory page is waiting for you to create it.

[Link]

It takes about five minutes: choose a password, add your business details and accept the Terms. The sooner your page is up, the sooner clients and agents can find you.

[Membership line]

If anything doesn't work, reply to this email and we will help.

Warm regards,
Paloma Harrington
Vice President, GAPHS"""

_ready = [False]
_last_sweep = [0.0]


def ensure():
    if _ready[0]:
        return
    db.run("""CREATE TABLE IF NOT EXISTS member_invites(
        id INTEGER PRIMARY KEY AUTOINCREMENT, invite_id INTEGER, code TEXT NOT NULL, name TEXT NOT NULL DEFAULT '',
        business TEXT NOT NULL DEFAULT '', email TEXT NOT NULL, renewal TEXT NOT NULL DEFAULT '', user_id INTEGER,
        sent_at TEXT, reminded_at TEXT, created_at TEXT NOT NULL)""")
    _ready[0] = True


def _parse_date(text):
    text = (text or "").strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d/%m/%Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def _renewal_dt(mi):
    return _parse_date(mi["renewal"]) if mi["renewal"] else None


def _pretty(dt):
    return "%d %s" % (dt.day, dt.strftime("%B %Y")) if dt else ""


def for_invite(inv):
    """The existing-member record behind an invite code, or None for ordinary codes."""
    if not inv:
        return None
    try:
        ensure()
        return db.q("SELECT * FROM member_invites WHERE invite_id = ?", (inv["id"],), one=True)
    except Exception:
        return None


def prefill(mi):
    return {"name": mi["name"], "email": mi["email"], "business_name": mi["business"]}


def apply_signup(inv, uid):
    """After an existing member signs up with their code: link the account and end their free period on the renewal date."""
    try:
        mi = for_invite(inv)
        if not mi:
            return
        db.run("UPDATE member_invites SET user_id = ? WHERE id = ?", (uid, mi["id"]))
        dt = _renewal_dt(mi)
        if dt:
            end = dt.strftime("%Y-%m-%dT23:59:59Z")
            if not db.parse_iso(end):
                end = dt.strftime("%Y-%m-%d")
            db.run("UPDATE users SET period_end = ? WHERE id = ?", (end, uid))
    except Exception as exc:
        current_app.logger.warning("member invite signup: %s", exc)


@admin.before_app_request
def _end_carried_over():
    """Once memberships can be paid for (GAPHS Stripe connected), a carried-over free period ends on its renewal date."""
    if time.time() - _last_sweep[0] < 3600:
        return None
    _last_sweep[0] = time.time()
    try:
        import stripe_api
        if not stripe_api.enabled():
            return None
        ensure()
        now = db.parse_iso(db.now_iso())
        for u in db.q("""SELECT u.id, u.period_end FROM users u JOIN member_invites m ON m.user_id = u.id
                         WHERE u.comped = 1 AND u.is_admin = 0 AND u.period_end IS NOT NULL"""):
            end = db.parse_iso(u["period_end"])
            if end and now and end < now:
                db.run("UPDATE users SET comped = 0, status = 'canceled' WHERE id = ?", (u["id"],))
    except Exception as exc:
        current_app.logger.warning("member invite sweep: %s", exc)
    return None


# ---- the email -----------------------------------------------------------------
def _texts():
    return {"subject": db.setting("mi_subject", "") or DEFAULT_SUBJECT,
            "body": db.setting("mi_body", "") or DEFAULT_BODY,
            "r_subject": db.setting("mi_r_subject", "") or DEFAULT_REMINDER_SUBJECT,
            "r_body": db.setting("mi_r_body", "") or DEFAULT_REMINDER_BODY}


def _para(text):
    return ('<p style="margin:0 0 18px;font-size:16px;line-height:1.65;color:#2A2A2A">%s</p>'
            % escape(text).replace("\n", "<br>"))


def render(mi, subject, body, site):
    """Returns (subject, plain text, html) for one member."""
    name = (mi["name"] or "").strip()
    first = name.split(" ")[0] if name else "there"
    link = "%s/invite?code=%s" % (site, mi["code"])
    dt = _renewal_dt(mi)
    if dt and dt >= datetime.utcnow():
        line = ("Your membership carries across as a GAPHS membership and stays active until your renewal date, %s."
                % _pretty(dt))
    else:
        line = ("Your membership carries across as a GAPHS membership. Your renewal is now due, "
                "and we will be in touch about it separately.")
    values = {"[First name]": first, "[Name]": name, "[Business]": mi["business"] or "", "[Link]": link,
              "[Renewal date]": _pretty(dt), "[Membership line]": line}
    for key, val in values.items():
        subject = subject.replace(key, val)
        body = body.replace(key, val)
    body = body.replace("\r\n", "\n").strip()
    inner = ""
    for block in re.split(r"\n\s*\n", body):
        block = block.strip()
        if not block:
            continue
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if block == link:
            inner += '<p style="margin:6px 0 24px">%s</p>' % mails._button("Create my page", link)
        elif all(re.match(r"^\d+[.)]\s+", l) for l in lines):
            items = "".join('<li style="margin:0 0 8px">%s</li>' % escape(re.sub(r"^\d+[.)]\s+", "", l)) for l in lines)
            inner += ('<ol style="margin:0 0 20px;padding-left:22px;font-size:16px;line-height:1.55;color:#2A2A2A">%s</ol>'
                      % items)
        elif len(lines) == 1 and block.endswith(":") and len(block) < 70:
            inner += mails._h(block[:-1])
        else:
            inner += _para(block)
    return subject, body, mails._layout(subject, inner)


def _send_many(messages):
    """messages: list of (to, subject, text, html). One SMTP connection for the lot. Returns the list of addresses sent."""
    host = os.environ.get("SMTP_HOST", "")
    addr = parseaddr(os.environ.get("MAIL_FROM", "") or os.environ.get("SMTP_USER", ""))[1]
    if not host or not addr or not messages:
        return []
    done = []
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
        client = smtplib.SMTP_SSL(host, port, timeout=20) if port == 465 else smtplib.SMTP(host, port, timeout=20)
        with client as smtp:
            if port != 465:
                smtp.starttls()
            if os.environ.get("SMTP_USER"):
                smtp.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
            for to, subject, text, html in messages:
                msg = EmailMessage()
                msg["From"] = formataddr((SENDER_NAME, addr))
                msg["To"] = to
                msg["Subject"] = subject
                msg["Reply-To"] = REPLY_TO
                msg.set_content(text)
                msg.add_alternative(html, subtype="html")
                try:
                    smtp.send_message(msg)
                    done.append(to)
                except Exception as exc:
                    current_app.logger.warning("Invite email to %s failed: %s", to, exc)
    except Exception as exc:
        current_app.logger.warning("Invite email connection failed: %s", exc)
    return done


def _rows():
    return db.q("""SELECT m.*, COALESCE(i.uses, 0) AS uses, COALESCE(i.active, 0) AS active
                   FROM member_invites m LEFT JOIN invites i ON i.id = m.invite_id ORDER BY m.id""")


def _joined(r):
    return bool(r["user_id"] or r["uses"])


def _import(text):
    added = skipped = left_out = 0
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    today = datetime.utcnow()
    for raw in reader:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        email = (row.get("email") or "").lower()
        if "@" not in email:
            continue
        notes = (row.get("notes") or "").lower()
        if "not renew" in notes or "not be renew" in notes:
            left_out += 1
            continue
        if db.q("SELECT 1 FROM member_invites WHERE lower(email) = ?", (email,), one=True):
            skipped += 1
            continue
        name = re.sub(r"\s+", " ", row.get("member name") or row.get("name") or "")
        business = row.get("business name") or row.get("business") or ""
        end = _parse_date(row.get("membership expiry date") or row.get("renewal") or row.get("renewal date") or "")
        start = _parse_date(row.get("membership start date") or "")
        if end and start and start > today:  # start date typed a year ahead: the period is really one year earlier
            end = end.replace(year=end.year - 1)
        code = new_invite_code()
        invite_id = db.run("INSERT INTO invites(code, label, max_uses, created_at) VALUES (?,?,?,?)",
                           (code, (business or name)[:120], 1, db.now_iso()))
        if not invite_id:
            got = db.q("SELECT id FROM invites WHERE code = ?", (code,), one=True)
            invite_id = got["id"] if got else None
        db.run("""INSERT INTO member_invites(invite_id, code, name, business, email, renewal, created_at)
                  VALUES (?,?,?,?,?,?,?)""",
               (invite_id, code, name, business, email, end.strftime("%Y-%m-%d") if end else "", db.now_iso()))
        added += 1
    return added, skipped, left_out


@admin.route("/member-invites", methods=["GET", "POST"])
@admin_required
def member_invites():
    ensure()
    me = current_user()
    site = helpers.site_url()
    t = _texts()
    if request.method == "POST":
        do = request.form.get("do", "")
        if do == "import":
            text = request.form.get("csv") or ""
            up = request.files.get("file")
            if up and up.filename:
                text = up.read().decode("utf-8", "replace")
            if not text.strip():
                flash("Choose the member sheet (CSV) first.", "error")
            else:
                added, skipped, left_out = _import(text)
                flash("%d member%s added with a personal code. %d already on the list. %d left out (marked as not renewing)."
                      % (added, "" if added == 1 else "s", skipped, left_out), "success")
        elif do == "texts":
            for key, field in (("mi_subject", "subject"), ("mi_body", "body"),
                               ("mi_r_subject", "r_subject"), ("mi_r_body", "r_body")):
                db.set_setting(key, (request.form.get(field) or "").strip())
            flash("Email wording saved. Nothing has been sent.", "success")
        elif do == "date":
            dt = _parse_date(request.form.get("renewal"))
            if dt:
                db.run("UPDATE member_invites SET renewal = ? WHERE id = ?",
                       (dt.strftime("%Y-%m-%d"), request.form.get("id", type=int)))
                flash("Renewal date updated.", "success")
            else:
                flash("Please enter the date like 2027-03-14.", "error")
        elif do == "remove":
            mi = db.q("SELECT * FROM member_invites WHERE id = ?", (request.form.get("id", type=int),), one=True)
            if mi and not mi["user_id"]:
                db.run("DELETE FROM invites WHERE id = ? AND uses = 0", (mi["invite_id"],))
                db.run("DELETE FROM member_invites WHERE id = ?", (mi["id"],))
                flash("Removed. Their code no longer works.", "success")
        elif do in ("test", "test_reminder"):
            rows = _rows()
            if not rows:
                flash("Add the members first.", "error")
            else:
                which = ("r_subject", "r_body") if do == "test_reminder" else ("subject", "body")
                subject, text, html = render(rows[0], t[which[0]], t[which[1]], site)
                ok = _send_many([(me["email"], "[TEST] " + subject, text, html)])
                flash(("Test sent to %s. It shows what %s will receive." % (me["email"], rows[0]["name"])) if ok
                      else "The test could not be sent. Check the email settings.", "success" if ok else "error")
        elif do in ("send_one", "send_all", "remind_all"):
            if do != "send_one" and request.form.get("confirm") != "yes":
                flash("Tick the box to confirm before sending.", "error")
                return redirect(url_for("admin.member_invites"))
            rows = _rows()
            if do == "send_one":
                rows = [r for r in rows if r["id"] == request.form.get("id", type=int) and not _joined(r)]
            elif do == "send_all":
                rows = [r for r in rows if not r["sent_at"] and not _joined(r)]
            else:
                rows = [r for r in rows if r["sent_at"] and not _joined(r)]
            reminder = do == "remind_all" or (do == "send_one" and rows and rows[0]["sent_at"])
            which = ("r_subject", "r_body") if reminder else ("subject", "body")
            batch = [(r["email"],) + render(r, t[which[0]], t[which[1]], site) for r in rows]
            sent = set(_send_many(batch))
            col = "reminded_at" if reminder else "sent_at"
            for r in rows:
                if r["email"] in sent:
                    db.run("UPDATE member_invites SET %s = ? WHERE id = ?" % col, (db.now_iso(), r["id"]))
            flash("%d of %d email%s sent." % (len(sent), len(rows), "" if len(rows) == 1 else "s"),
                  "success" if len(sent) == len(rows) and rows else "error")
        return redirect(url_for("admin.member_invites"))
    rows = _rows()
    view = []
    for r in rows:
        dt = _renewal_dt(r)
        view.append({"r": r, "joined": _joined(r), "renewal": _pretty(dt), "due": bool(dt and dt < datetime.utcnow()),
                     "link": "%s/invite?code=%s" % (site, r["code"]),
                     "sent": (r["sent_at"] or "")[:10], "reminded": (r["reminded_at"] or "")[:10]})
    sample = rows[0] if rows else {"name": "Jane Example", "business": "Example Staging", "email": "jane@example.com",
                                    "code": "GAPHS-EXAMPLE", "renewal": "2027-03-14"}
    kind = request.args.get("preview", "invite")
    which = ("r_subject", "r_body") if kind == "reminder" else ("subject", "body")
    p_subject, _text, p_html = render(sample, t[which[0]], t[which[1]], site)
    counts = {"all": len(view), "joined": sum(1 for v in view if v["joined"]),
              "unsent": sum(1 for v in view if not v["sent"] and not v["joined"]),
              "waiting": sum(1 for v in view if v["sent"] and not v["joined"])}
    sender = formataddr((SENDER_NAME, parseaddr(os.environ.get("MAIL_FROM", "") or os.environ.get("SMTP_USER", ""))[1]))
    return render_template("admin/member_invites.html", rows=view, t=t, counts=counts, preview_html=p_html,
                           preview_subject=p_subject, preview_kind=kind, sender=sender, reply_to=REPLY_TO,
                           sample_name=sample["name"], email_ready=bool(os.environ.get("SMTP_HOST")))
