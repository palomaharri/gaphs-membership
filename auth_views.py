"""Public site, sign-up and payment, member dashboard, business pages."""
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect, render_template,
                   request, send_from_directory, session, url_for)

import db
import stripe_api
from helpers import (clear_attempts, csrf_token, current_user, founding_open, has_access, login_required,
                     money, plan_label, public_plans, gets_page, record_attempt, save_image, delete_public, send_mail,
                     site_url, throttled, fmt_date)

auth = Blueprint("auth", __name__)

PLAN_KEYS = {
    ("member", "annual"): "member_annual",
    ("member", "monthly"): "member_monthly",
    ("professional", "annual"): "pro_annual",
    ("professional", "monthly"): "pro_monthly",
}
ELIGIBLE_SQL = """
  (u.status IN ('active','past_due') OR u.comped = 1 OR u.is_admin = 1)
  AND p.published = 1 AND p.approved = 1 AND p.business_name != ''
  AND p.bio != '' AND p.location != '' AND p.services != '' AND p.logo != ''
  AND (p.contact_email != '' OR p.phone != '')
"""

REQUIRED_FIELDS = (("bio", "About your business"), ("location", "Where you work"), ("services", "Services"),
                   ("logo", "Logo"))


def missing_fields(p):
    """What still needs filling in before a page can go live."""
    out = [label for key, label in REQUIRED_FIELDS if not (p[key] or "")]
    if not ((p["contact_email"] or "") or (p["phone"] or "")):
        out.append("Contact email or phone")
    return out


# ---- small helpers ----------------------------------------------------------
def plan_amount(plan, billing):
    key = PLAN_KEYS.get((plan, billing))
    return db.int_setting(key) if key else 0


def founding_ok(plan, billing, code=""):
    if db.int_setting("founding_limit") <= 0:   # GAPHS: no founding rate
        return False
    if plan != "member" or billing != "annual":
        return False
    saved = db.setting("founding_code")
    if code and saved and secrets.compare_digest(code, saved):
        return True
    return founding_open()


def clean_url(value, social=None):
    value = (value or "").strip()
    if not value:
        return ""
    if social == "instagram" and not value.lower().startswith("http"):
        handle = value.lstrip("@/ ").split("/")[-1]
        return "https://instagram.com/" + handle if handle else ""
    if not value.lower().startswith(("http://", "https://")):
        value = "https://" + value
    return value[:300]


def safe_next(target):
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return None


def profile_values(form):
    def f(name, limit=300):
        return (form.get(name) or "").strip()[:limit]
    return {
        "business_name": f("business_name", 120),
        "tagline": f("tagline", 160),
        "bio": f("bio", 3000),
        "location": f("location", 160),
        "address": f("address", 300),
        "country": f("country", 80),
        "services": f("services", 1500),
        "contact_email": f("contact_email", 160),
        "phone": f("phone", 60),
        "website": clean_url(form.get("website")),
        "instagram": clean_url(form.get("instagram"), "instagram"),
        "facebook": clean_url(form.get("facebook")),
        "linkedin": clean_url(form.get("linkedin")),
    }


def login_user(user_id):
    session.clear()
    session["uid"] = user_id
    session.permanent = True


def activate(user_id, customer=None, subscription=None, period_end=None):
    """Mark a member as paid. Safe to call more than once."""
    user = db.q("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
    if not user:
        return
    started = user["started_at"] or db.now_iso()
    if not period_end:
        days = 365 if user["billing"] == "annual" else 31
        period_end = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    first_time = user["status"] == "pending"
    db.run("""UPDATE users SET status = 'active', started_at = ?, period_end = ?,
              stripe_customer = COALESCE(?, stripe_customer),
              stripe_subscription = COALESCE(?, stripe_subscription) WHERE id = ?""",
           (started, period_end, customer, subscription, user_id))
    if first_time:
        db.run("UPDATE profiles SET approved = 1 WHERE user_id = ?", (user_id,))
        import mails
        subject, text, html = mails.welcome(user, site_url())
        send_mail(user["email"], subject, text, html)


@auth.route("/contact", methods=["GET", "POST"])
def contact():
    user = current_user()
    if request.method == "POST":
        return redirect(url_for("auth.contact"))
    if request.method == "NEVER":
        key = "contact:" + (request.headers.get("X-Forwarded-For", request.remote_addr) or "").split(",")[0].strip()
        if request.form.get("website"):   # hidden field: only bots fill it in
            return redirect(url_for("auth.contact", sent=1))
        name = (request.form.get("name") or "").strip()[:120]
        email = (request.form.get("email") or "").strip()[:200]
        body = (request.form.get("message") or "").strip()[:5000]
        if throttled(key, 5, 3600):
            flash("Too many messages just now. Please try again later.", "error")
        elif "@" not in email or len(body) < 5:
            flash("Please enter your email and a message.", "error")
        else:
            record_attempt(key)
            db.run("INSERT INTO messages(name, email, body, created_at) VALUES (?,?,?,?)",
                   (name, email, body, db.now_iso()))
            to = os.environ.get("CONTACT_EMAIL") or os.environ.get("ADMIN_EMAIL", "")
            if to:
                try:
                    send_mail(to, "New message from GAPHS website",
                              "From: %s <%s>\n\n%s\n\nReply directly to %s." % (name or "(no name)", email, body, email))
                except Exception:
                    pass
            return redirect(url_for("auth.contact", sent=1))
        return render_template("contact.html", sent=False, name=name, email=email, body=body)
    return render_template("contact.html", sent=bool(request.args.get("sent")), name=user["name"] if user else "",
                           email=user["email"] if user else "", body="")


@auth.route("/gift", methods=["GET", "POST"])
def gift():
    """Free ebook in exchange for an email address."""
    gid = db.int_setting("gift_content_id") if db.setting("gift_content_id") else 0
    c = db.q("SELECT * FROM content WHERE id = ? AND published = 1", (gid,), one=True) if gid else None
    if not c:
        abort(404)
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        if "@" not in email or "." not in email.split("@")[-1] or len(email) > 200:
            flash("Please enter a valid email address.", "error")
            return redirect(url_for("auth.gift"))
        if not db.q("SELECT 1 FROM subscribers WHERE email = ?", (email,), one=True):
            db.run("INSERT INTO subscribers(email, source, created_at) VALUES (?,?,?)", (email, "gift:both" if request.form.get("both") else "gift", db.now_iso()))
        row = db.q("SELECT token FROM purchases WHERE content_id = ? AND email = ? AND amount = 0", (c["id"], email), one=True)
        token = row["token"] if row else record_purchase(c["id"], None, email, None, 0)
        try:
            link = site_url() + url_for("members.purchase", token=token)
            send_mail(email, "Your free guide from GAPHS",
                      "Thank you for your interest in GAPHS. Here is your free guide, %s:\n\n%s\n\nKeep this link: it is your access.\n\nThe GAPHS team" % (c["title"], link))
        except Exception:
            pass
        if request.form.get("both"):
            return redirect(url_for("auth.gift", t=token))
        return redirect(url_for("members.purchase", token=token))
    tok = request.args.get("t") or ""
    if tok and not db.q("SELECT 1 FROM purchases WHERE token = ? AND content_id = ?", (tok, c["id"]), one=True):
        tok = ""
    return render_template("gift.html", c=c, token=tok, report=None)


def record_purchase(content_id, user_id, email, session_id, amount):
    if session_id and db.q("SELECT id FROM purchases WHERE stripe_session = ?", (session_id,), one=True):
        return db.q("SELECT token FROM purchases WHERE stripe_session = ?", (session_id,), one=True)["token"]
    token = secrets.token_urlsafe(24)
    db.run("""INSERT INTO purchases(content_id, user_id, email, token, stripe_session, amount, paid_at)
              VALUES (?,?,?,?,?,?,?)""", (content_id, user_id, email, token, session_id, amount, db.now_iso()))
    return token


def handle_checkout_completed(sess):
    """Used by both the webhook and the success page, so it must be repeatable."""
    if sess.get("mode") == "subscription":
        uid = sess.get("client_reference_id") or (sess.get("metadata") or {}).get("user_id")
        if not uid:
            return None
        period_end = None
        sub_id = sess.get("subscription")
        if sub_id and stripe_api.enabled():
            try:
                end = stripe_api.subscription_period_end(stripe_api.get_subscription(sub_id))
                if end:
                    period_end = datetime.fromtimestamp(end, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except stripe_api.StripeError:
                pass
        activate(int(uid), sess.get("customer"), sub_id, period_end)
        return "subscription"
    if sess.get("mode") == "payment" and sess.get("payment_status") == "paid":
        meta = sess.get("metadata") or {}
        email = (sess.get("customer_details") or {}).get("email") or sess.get("customer_email") or ""
        uid = int(meta["user_id"]) if meta.get("user_id") else None
        return record_purchase(int(meta["content_id"]), uid, email, sess.get("id"), sess.get("amount_total") or 0)
    return None


def start_checkout(user):
    """Send the member to pay: real Stripe when keys are set, otherwise the test-mode page."""
    plan, billing = user["plan"], user["billing"]
    amount = plan_amount(plan, billing)
    if not amount:
        flash("That plan is not available yet.", "error")
        return redirect(url_for("auth.join"))
    name = "Global Association of Professional Home Stagers: %s (%s)" % (plan_label(plan), billing)
    discount = 0
    if user["founding"] and plan == "member" and billing == "annual":
        discount = max(0, amount - db.int_setting("founding"))
    import accreditation as _acc
    if _acc.wants(user["id"]):  # Accredited: always the full yearly fee, no founding discount, no credit
        amount, discount, billing = _acc.price(), 0, "annual"
        name = "Global Association of Professional Home Stagers: Accredited (annual)"
    if stripe_api.enabled():
        try:
            sess = stripe_api.subscription_checkout(
                user, name, amount, "year" if billing == "annual" else "month",
                site_url() + url_for("auth.checkout_success") + "?session_id={CHECKOUT_SESSION_ID}",
                site_url() + url_for("auth.dashboard"), discount)
        except stripe_api.StripeError as exc:
            current_app.logger.error("Stripe: %s", exc)
            flash("We could not start the payment: %s" % exc, "error")
            return redirect(url_for("auth.dashboard"))
        return redirect(sess["url"], 303)
    token = secrets.token_urlsafe(18)
    db.run("INSERT INTO pending_checkouts(token, kind, payload, created_at) VALUES (?,?,?,?)",
           (token, "subscription", json.dumps({"user_id": user["id"], "name": name, "amount": amount - discount,
                                               "then": amount, "interval": billing}), db.now_iso()))
    return redirect(url_for("auth.simulate", token=token))


# ---- public pages -----------------------------------------------------------
@auth.route("/")
def home():
    featured = db.q("""SELECT * FROM content WHERE published = 1 AND featured = 1 AND (price > 0 OR category = 'course')
                       ORDER BY sort, id LIMIT 12""")
    gid = db.setting("gift_content_id")
    gift = db.q("SELECT * FROM content WHERE id = ? AND published = 1", (gid,), one=True) if gid.isdigit() else None
    return render_template("home.html", founding_limit=db.int_setting("founding_limit"),
                           founding_open=founding_open(), featured=featured, gift=gift)


@auth.route("/media/<path:name>")
def media(name):
    resp = send_from_directory(db.PUBLIC_UPLOADS, os.path.basename(name), max_age=86400)
    return resp


@auth.route("/terms")
def terms():
    return render_template("legal.html", title="Terms and Conditions", body=db.setting("terms_text"))


@auth.route("/privacy")
def privacy():
    return render_template("legal.html", title="Privacy Policy", body=db.setting("privacy_text"))


@auth.route("/manifest.webmanifest")
def manifest():
    import json as _json
    data = {
        "name": "Global Association of Professional Home Stagers", "short_name": "GAPHS", "start_url": "/dashboard?source=app",
        "scope": "/", "display": "standalone", "background_color": "#1A1A1A", "theme_color": "#1A1A1A",
        "icons": [
            {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "/static/icons/icon-maskable-192.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
            {"src": "/static/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    from flask import Response
    return Response(_json.dumps(data), mimetype="application/manifest+json")


@auth.route("/sw.js")
def service_worker():
    from flask import Response
    js = "self.addEventListener('install',function(e){self.skipWaiting();});self.addEventListener('activate',function(e){e.waitUntil(self.clients.claim());});self.addEventListener('fetch',function(e){});"
    return Response(js, mimetype="application/javascript", headers={"Cache-Control": "no-cache"})


@auth.route("/code-of-conduct")
def code_of_conduct():
    return render_template("legal.html", title="Code of Ethics and Conduct", body=db.setting("code_text"))


@auth.route("/directory")
def directory():
    """The global directory: choose a country, then narrow by city, name or service."""
    from helpers import COUNTRIES
    term = (request.args.get("q") or "").strip()[:100]
    country = match_country(request.args.get("country"))
    typed = (request.args.get("country") or "").strip()[:80]
    if typed and not country:
        term = (term + " " + typed).strip()   # not a country we know: search for it as text
    base = """FROM profiles p JOIN users u ON u.id = p.user_id
              WHERE %s AND (u.plan IN (%s) OR u.founding = 1)""" % (ELIGIBLE_SQL, ",".join("?" * len(public_plans())) or "''")
    args = list(public_plans())
    counts = {r["country"]: r["n"] for r in db.q("SELECT p.country, COUNT(*) AS n " + base + " GROUP BY p.country", args)
              if r["country"]}
    listings = []
    if country or term:
        sql, a2 = "SELECT p.*, u.plan " + base, list(args)
        if country:
            sql += " AND p.country = ?"
            a2.append(country)
        if term:
            sql += " AND (p.business_name LIKE ? OR p.location LIKE ? OR p.services LIKE ? OR p.country LIKE ?)"
            a2 += ["%" + term + "%"] * 4
        sql += " ORDER BY p.country, p.business_name COLLATE NOCASE LIMIT 300"
        listings = db.q(sql, a2)
    codes = {name: code for code, name in COUNTRIES}
    return render_template("directory.html", listings=listings, term=term, country=country,
                           counts=sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])), country_codes=codes,
                           searched=bool(country or term), typed=typed)


COUNTRY_ALIASES = {"uk": "United Kingdom", "great britain": "United Kingdom", "britain": "United Kingdom", "england": "United Kingdom",
                   "scotland": "United Kingdom", "wales": "United Kingdom", "northern ireland": "United Kingdom",
                   "usa": "United States", "us": "United States", "america": "United States", "united states of america": "United States",
                   "uae": "United Arab Emirates", "holland": "Netherlands", "the netherlands": "Netherlands",
                   "espana": "Spain", "españa": "Spain", "italia": "Italy", "deutschland": "Germany", "schweiz": "Switzerland",
                   "suisse": "Switzerland", "svizzera": "Switzerland", "österreich": "Austria", "osterreich": "Austria",
                   "polska": "Poland", "hellas": "Greece", "ellada": "Greece", "brasil": "Brazil", "méxico": "Mexico",
                   "belgique": "Belgium", "belgie": "Belgium", "sverige": "Sweden", "norge": "Norway", "danmark": "Denmark",
                   "suomi": "Finland", "hrvatska": "Croatia", "srbija": "Serbia", "türkiye": "Turkey", "turkiye": "Turkey",
                   "czechia": "Czech Republic", "eire": "Ireland", "korea": "South Korea"}


def match_country(text):
    """Turn what the visitor typed into one of our country names, or '' if we cannot tell."""
    from helpers import COUNTRY_NAMES
    t = " ".join((text or "").strip().lower().split())[:80]
    if not t:
        return ""
    names = {n.lower(): n for n in COUNTRY_NAMES}
    if t in names:
        return names[t]
    if t in COUNTRY_ALIASES and COUNTRY_ALIASES[t] in COUNTRY_NAMES:
        return COUNTRY_ALIASES[t]
    starts = [n for low, n in names.items() if low.startswith(t)]
    return starts[0] if len(starts) == 1 else ""


@auth.route("/directory/request", methods=["POST"])
def directory_request():
    """A visitor found no stager in their country: pass the request on to GAPHS."""
    country = match_country(request.form.get("country")) or (request.form.get("country") or "").strip()[:80]
    back = url_for("auth.directory", country=country) if country else url_for("auth.directory")
    if request.form.get("website"):            # hidden field: only bots fill it in
        return redirect(back)
    key = "dirreq:" + (request.headers.get("X-Forwarded-For", request.remote_addr) or "").split(",")[0].strip()
    name = (request.form.get("name") or "").strip()[:120]
    email = (request.form.get("email") or "").strip()[:200]
    city = (request.form.get("city") or "").strip()[:120]
    note = (request.form.get("message") or "").strip()[:3000]
    if throttled(key, 5, 3600):
        flash("Too many requests just now. Please try again later.", "error")
        return redirect(back)
    if "@" not in email:
        flash("Please enter your email so we can reply.", "error")
        return redirect(back)
    record_attempt(key)
    body = "Looking for a home stager in %s%s.\n\n%s" % (city + ", " if city else "", country or "(country not given)", note or "(no message)")
    db.run("INSERT INTO messages(name, email, body, created_at) VALUES (?,?,?,?)", (name, email, body, db.now_iso()))
    to = os.environ.get("CONTACT_EMAIL") or "info@gaphs.org"
    try:
        send_mail(to, "Stager request: %s" % (country or "unknown country"),
                  "From: %s <%s>\n\n%s\n\nReply directly to %s." % (name or "(no name)", email, body, email))
    except Exception:
        pass
    flash("Thank you. Your request has been received and the Association will reply by email, normally within a few working days.", "success")
    return redirect(back + ("&" if "?" in back else "?") + "asked=1")


@auth.route("/directory/<slug>")
def business(slug):
    row = db.q("""SELECT p.*, u.plan, u.founding, u.status, u.comped, u.is_admin, u.id AS uid FROM profiles p
                  JOIN users u ON u.id = p.user_id WHERE p.slug = ?""", (slug,), one=True)
    if not row:
        abort(404)
    me = current_user()
    owner_preview = me and (me["id"] == row["uid"] or me["is_admin"])
    live = (row["published"] and row["approved"] and row["business_name"] and not missing_fields(row)
            and (row["status"] in ("active", "past_due") or row["comped"] or row["is_admin"])
            and gets_page(row["plan"], row["founding"]))
    if not live and not owner_preview:
        abort(404)
    photos = db.q("SELECT * FROM gallery WHERE user_id = ? ORDER BY sort, id", (row["uid"],))
    return render_template("business.html", p=row, photos=photos, preview=not live)


def valid_invite(code):
    code = (code or "").strip().upper()
    if not code:
        return None
    row = db.q("SELECT * FROM invites WHERE code = ? AND active = 1", (code,), one=True)
    if row and row["uses"] < row["max_uses"]:
        return row
    return None


@auth.route("/invite", methods=["GET", "POST"])
def invite():
    """Free sign-up for people holding an invite code."""
    code = (request.values.get("code") or "").strip().upper()
    if code:
        if valid_invite(code):
            return redirect(url_for("auth.signup", invite=code))
        flash("That code is not valid, or it has already been used. Please check it and try again.", "error")
    return render_template("invite.html", code=code)


# ---- join & sign-up ---------------------------------------------------------
@auth.route("/join")
def join():
    code = request.args.get("code", "")
    return render_template(
        "join.html", plan=request.args.get("plan", ""), billing=request.args.get("billing", "annual"),
        code=code, founding_available=founding_ok("member", "annual", code),
        prices={k: db.int_setting(k) for k in ("member_annual", "member_monthly", "pro_annual",
                                              "pro_monthly", "founding")},
        founding_limit=db.int_setting("founding_limit"))


@auth.route("/signup", methods=["GET", "POST"])
def signup():
    me = current_user()
    plan = request.values.get("plan", "")
    billing = request.values.get("billing", "annual")
    code = request.values.get("code", "")
    want_founding = bool(request.values.get("founding"))
    inv = valid_invite(request.values.get("invite"))
    if request.values.get("invite") and not inv:
        flash("That code is not valid, or it has already been used.", "error")
        return redirect(url_for("auth.invite"))
    if inv:  # GAPHS: an invite code gives a free Member (stager) membership with a directory page
        plan, billing, want_founding = "professional", "annual", False
    import member_invites as _mi
    mi = _mi.for_invite(inv) if inv else None
    if mi:  # existing member carried over: Professional, valid until their renewal date
        plan, want_founding = "professional", False
    import accreditation as _acc
    acc = False  # GAPHS: no Accredited tier
    if acc:  # Accredited: a Professional membership at the Accredited fee, plus an assessed application
        plan, billing, want_founding = "professional", "annual", False
    if plan not in ("member", "professional") or billing not in ("annual", "monthly"):
        return redirect(url_for("auth.join"))
    amount = plan_amount(plan, billing)
    if not amount:
        flash("Monthly membership isn't open yet. Please choose annual.", "info")
        return redirect(url_for("auth.join", plan=plan))
    can_found = False if inv else (want_founding and founding_ok(plan, billing, code))
    if want_founding and not can_found:
        flash("The founding rate places have all been taken, so the standard price applies.", "info")
    if me and has_access(me):
        return redirect(url_for("auth.dashboard"))
    form = request.form if request.method == "POST" else (_mi.prefill(mi) if mi else {})
    errors = []
    if request.method == "POST":
        v = profile_values(request.form)
        name = (request.form.get("name") or "").strip()[:120]
        email = (request.form.get("email") or "").strip().lower()[:200]
        pw = request.form.get("password") or ""
        qual = (request.form.get("qualifying_course") or "").strip()[:300]
        if not name:
            errors.append("Please enter your name.")
        if "@" not in email or "." not in email.split("@")[-1]:
            errors.append("Please enter a valid email address.")
        if not me:
            if len(pw) < 8:
                errors.append("Choose a password of at least 8 characters.")
            if pw != request.form.get("password2"):
                errors.append("The two passwords do not match.")
        if not v["business_name"]:
            errors.append("Please enter your business name.")
        if not v["address"]:
            errors.append("Please enter your business address.")
        if not v["country"]:
            errors.append("Please choose your country.")
        if gets_page(plan, can_found) and not inv:
            for key, label in REQUIRED_FIELDS:
                if key == "logo":
                    has_logo = bool(request.files.get("logo") and request.files["logo"].filename) or \
                        bool(me and db.q("SELECT logo FROM profiles WHERE user_id = ? AND logo != ''", (me["id"],), one=True))
                    if not has_logo:
                        errors.append("Please add your logo.")
                elif not v[key]:
                    errors.append("Please fill in: %s." % label.lower())
        if plan == "professional" and not qual and not inv:
            errors.append("Please tell us which home staging training course you have completed.")
        if acc:
            errors.extend(_acc.validate(request.form))
        for field, label in (("agree_terms", "Terms and Conditions"), ("agree_code", "Code of Ethics and Conduct"),
                             ("agree_privacy", "Privacy Policy")):
            if not request.form.get(field):
                errors.append("Please tick to agree to the %s." % label)
        existing = db.q("SELECT * FROM users WHERE email = ?", (email,), one=True)
        if existing and (not me or existing["id"] != me["id"]):
            if existing["status"] in ("active", "past_due") or existing["comped"]:
                errors.append("There is already a member with that email. Please log in instead.")
            else:
                errors.append("There is already an account with that email. Please log in to finish joining.")
        logo = None
        if not errors:
            try:
                logo = save_image(request.files.get("logo"), 800, keep_alpha=True)
            except ValueError as exc:
                errors.append(str(exc))
        if not errors:
            now = db.now_iso()
            terms_v = db.text_version(db.setting("terms_text"))
            code_v = db.text_version(db.setting("code_text"))
            priv_v = db.text_version(db.setting("privacy_text"))
            if me:
                uid = me["id"]
                db.run("""UPDATE users SET name=?, plan=?, billing=?, founding=?, qualifying_course=?, agreed_at=?,
                          terms_version=?, code_version=?, privacy_version=? WHERE id=?""",
                       (name, plan, billing, 1 if can_found else 0, qual, now, terms_v, code_v, priv_v, uid))
            else:
                uid = db.run("""INSERT INTO users(email, pw_hash, name, created_at, plan, billing, founding,
                                qualifying_course, agreed_at, terms_version, code_version, privacy_version)
                                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (email, db.hash_password(pw), name, now, plan, billing, 1 if can_found else 0,
                              qual, now, terms_v, code_v, priv_v))
            prof = db.q("SELECT * FROM profiles WHERE user_id = ?", (uid,), one=True)
            slug = prof["slug"] if prof and prof["slug"] else db.unique_slug(v["business_name"], uid)
            if prof:
                db.run("""UPDATE profiles SET business_name=?, slug=?, tagline=?, bio=?, location=?, address=?, country=?, services=?,
                          contact_email=?, phone=?, website=?, instagram=?, facebook=?, linkedin=? WHERE user_id=?""",
                       (v["business_name"], slug, v["tagline"], v["bio"], v["location"], v["address"], v["country"], v["services"],
                        v["contact_email"] or email, v["phone"], v["website"], v["instagram"], v["facebook"],
                        v["linkedin"], uid))
                if logo:
                    delete_public(prof["logo"])
                    db.run("UPDATE profiles SET logo = ? WHERE user_id = ?", (logo, uid))
            else:
                db.run("""INSERT INTO profiles(user_id, business_name, slug, tagline, bio, logo, location, address, country, services,
                          contact_email, phone, website, instagram, facebook, linkedin)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (uid, v["business_name"], slug, v["tagline"], v["bio"], logo or "", v["location"], v["address"], v["country"],
                        v["services"], v["contact_email"] or email, v["phone"], v["website"], v["instagram"],
                        v["facebook"], v["linkedin"]))
            if acc:
                _acc.save(uid, request.form)
            login_user(uid)
            if inv:
                db.run("UPDATE users SET comped = 1, status = 'active', started_at = COALESCE(started_at, ?) WHERE id = ?",
                       (now, uid))
                db.run("UPDATE invites SET uses = uses + 1 WHERE id = ?", (inv["id"],))
                _mi.apply_signup(inv, uid)
                flash("Welcome! Your membership is active. Please complete your business page so it appears in the directory.", "success")
                return redirect(url_for("auth.profile_edit"))
            return start_checkout(db.q("SELECT * FROM users WHERE id = ?", (uid,), one=True))
    return render_template("signup.html", plan=plan, billing=billing, amount=amount, form=form, errors=errors,
                           founding=can_found, gets_page=gets_page(plan, can_found), code=code, then_amount=amount, invite=inv,
                           founding_price=db.int_setting("founding"),
                           terms_text=db.setting("terms_text"), code_text=db.setting("code_text"), me=me)


# ---- payment return pages ----------------------------------------------------
@auth.route("/checkout/success")
def checkout_success():
    sid = request.args.get("session_id", "")
    if sid and stripe_api.enabled():
        try:
            sess = stripe_api.get_session(sid)
            if sess.get("status") == "complete":
                handle_checkout_completed(sess)
        except stripe_api.StripeError as exc:
            current_app.logger.warning("Could not confirm session: %s", exc)
    flash("Thank you, your payment was received.", "success")
    return redirect(url_for("auth.dashboard"))


@auth.route("/checkout/start", methods=["POST"])
@login_required
def checkout_start():
    user = current_user()
    if has_access(user) and not user["is_admin"]:
        return redirect(url_for("auth.dashboard"))
    if not user["plan"]:
        return redirect(url_for("auth.join"))
    return start_checkout(user)


@auth.route("/simulate/<token>", methods=["GET", "POST"])
def simulate(token):
    """Test-mode checkout. Only exists while no Stripe key is configured."""
    if stripe_api.enabled():
        abort(404)
    row = db.q("SELECT * FROM pending_checkouts WHERE token = ?", (token,), one=True)
    if not row:
        abort(404)
    data = json.loads(row["payload"])
    if request.method == "POST":
        db.run("DELETE FROM pending_checkouts WHERE token = ?", (token,))
        if row["kind"] == "subscription":
            activate(data["user_id"], "cus_test", "sub_test")
            flash("Test payment complete. Your membership is active.", "success")
            return redirect(url_for("auth.dashboard"))
        me = current_user()
        email = (data.get("email") or (me["email"] if me else "")).strip().lower()
        ptoken = record_purchase(data["content_id"], me["id"] if me else None, email, "test_" + token, data["amount"])
        flash("Test payment complete.", "success")
        return redirect(url_for("members.purchase", token=ptoken))
    return render_template("simulate.html", data=data, kind=row["kind"], token=token, me=current_user())


@auth.route("/stripe/webhook-courses", methods=["POST"])
def stripe_webhook_courses():
    return _stripe_webhook("courses")


@auth.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    return _stripe_webhook("members")


def _stripe_webhook(account):
    try:
        event = stripe_api.verify_webhook(request.get_data(), request.headers.get("Stripe-Signature", ""),
                                          stripe_api.webhook_secret(account))
    except ValueError as exc:
        current_app.logger.warning("Webhook rejected: %s", exc)
        return jsonify(error="bad signature"), 400
    obj = event["data"]["object"]
    kind = event["type"]
    if kind == "checkout.session.completed":
        handle_checkout_completed(obj)
    elif kind in ("customer.subscription.updated", "customer.subscription.deleted"):
        user = db.q("SELECT * FROM users WHERE stripe_subscription = ?", (obj["id"],), one=True)
        if user:
            status = {"active": "active", "trialing": "active", "past_due": "past_due"}.get(obj.get("status"), "canceled")
            if kind == "customer.subscription.deleted":
                status = "canceled"
            end = stripe_api.subscription_period_end(obj)
            end_iso = datetime.fromtimestamp(end, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if end else user["period_end"]
            db.run("UPDATE users SET status = ?, period_end = ? WHERE id = ?", (status, end_iso, user["id"]))
    elif kind == "invoice.payment_failed":
        user = db.q("SELECT * FROM users WHERE stripe_customer = ?", (obj.get("customer"),), one=True)
        if user and user["status"] == "active":
            db.run("UPDATE users SET status = 'past_due' WHERE id = ?", (user["id"],))
    elif kind == "invoice.paid":
        user = db.q("SELECT * FROM users WHERE stripe_customer = ?", (obj.get("customer"),), one=True)
        if user and user["status"] in ("past_due", "active"):
            try:
                lines = obj["lines"]["data"]
                end = max(l["period"]["end"] for l in lines)
                end_iso = datetime.fromtimestamp(end, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except (KeyError, ValueError, TypeError):
                end_iso = user["period_end"]
            db.run("UPDATE users SET status = 'active', period_end = ? WHERE id = ?", (end_iso, user["id"]))
    return jsonify(ok=True)


# ---- login / logout / password ---------------------------------------------
@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        key = "%s|%s" % (request.remote_addr, email)
        if throttled(key):
            flash("Too many attempts. Please wait a few minutes and try again.", "error")
            return render_template("login.html", next=request.form.get("next", "")), 429
        user = db.q("SELECT * FROM users WHERE email = ?", (email,), one=True)
        if user and db.check_password(request.form.get("password") or "", user["pw_hash"]):
            clear_attempts(key)
            login_user(user["id"])
            target = safe_next(request.form.get("next"))
            return redirect(target or url_for("auth.dashboard"))
        record_attempt(key)
        flash("That email and password do not match.", "error")
    return render_template("login.html", next=request.args.get("next", ""))


@auth.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.home"))


@auth.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        user = db.q("SELECT * FROM users WHERE email = ?", (email,), one=True)
        if user:
            token = secrets.token_urlsafe(32)
            expires = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            db.run("UPDATE users SET reset_token = ?, reset_expires = ? WHERE id = ?", (token, expires, user["id"]))
            send_mail(email, "Reset your password",
                      "Use this link within one hour to choose a new password:\n%s/reset/%s\n" % (site_url(), token))
        flash("If that email has an account, we have sent a link to reset the password.", "info")
        return redirect(url_for("auth.login"))
    return render_template("forgot.html")


@auth.route("/reset/<token>", methods=["GET", "POST"])
def reset(token):
    user = db.q("SELECT * FROM users WHERE reset_token = ?", (token,), one=True)
    expires = db.parse_iso(user["reset_expires"]) if user else None
    if not user or not expires or expires < datetime.now(timezone.utc):
        flash("That reset link has expired. Please ask for a new one.", "error")
        return redirect(url_for("auth.forgot"))
    if request.method == "POST":
        pw = request.form.get("password") or ""
        if len(pw) < 8 or pw != request.form.get("password2"):
            flash("Choose a password of at least 8 characters and type it twice.", "error")
        else:
            db.run("UPDATE users SET pw_hash = ?, reset_token = NULL, reset_expires = NULL WHERE id = ?",
                   (db.hash_password(pw), user["id"]))
            flash("Password changed. You can log in now.", "success")
            return redirect(url_for("auth.login"))
    return render_template("reset.html", token=token)


# ---- member dashboard --------------------------------------------------------
@auth.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    profile = db.q("SELECT * FROM profiles WHERE user_id = ?", (user["id"],), one=True)
    purchases = db.q("""SELECT pu.*, c.title FROM purchases pu JOIN content c ON c.id = pu.content_id
                        WHERE pu.user_id = ? ORDER BY pu.paid_at DESC""", (user["id"],))
    listing = None
    if profile:
        if not gets_page(user["plan"], user["founding"]):
            listing = "not_included"
        elif not has_access(user):
            listing = "needs_payment"
        elif missing_fields(profile):
            listing = "incomplete"
        elif not profile["approved"]:
            listing = "offline"
        elif not profile["published"]:
            listing = "hidden"
        else:
            listing = "live"
    return render_template("dashboard.html", user=user, profile=profile, purchases=purchases, listing=listing,
                           missing=missing_fields(profile) if profile else [],
                           test_mode=not stripe_api.enabled(), has_access=has_access(user),
                           agreed=fmt_date(user["agreed_at"]),
                           next_content=_next_content(user))


def _next_content(user):
    """For monthly members: the next lesson that opens, so the dashboard can say what is coming."""
    if not user or user["billing"] != "monthly" or not has_access(user):
        return None
    from helpers import days_since_start
    days = days_since_start(user)
    row = db.q("""SELECT l.title, l.drip_days, c.title AS course FROM lessons l JOIN content c ON c.id = l.content_id
                  WHERE c.published = 1 AND l.drip_days > ? ORDER BY l.drip_days LIMIT 1""", (days,), one=True)
    if not row:
        return None
    return {"title": row["title"], "course": row["course"], "in_days": row["drip_days"] - days}


@auth.route("/dashboard/account", methods=["POST"])
@login_required
def account_update():
    user = current_user()
    name = (request.form.get("name") or "").strip()[:120]
    email = (request.form.get("email") or "").strip().lower()[:200]
    if not name or "@" not in email:
        flash("Please enter your name and a valid email.", "error")
        return redirect(url_for("auth.dashboard"))
    clash = db.q("SELECT id FROM users WHERE email = ? AND id != ?", (email, user["id"]), one=True)
    if clash:
        flash("That email is already used by another account.", "error")
        return redirect(url_for("auth.dashboard"))
    new_pw = request.form.get("new_password") or ""
    if new_pw:
        if not db.check_password(request.form.get("current_password") or "", user["pw_hash"]):
            flash("Your current password was not right, so nothing was changed.", "error")
            return redirect(url_for("auth.dashboard"))
        if len(new_pw) < 8:
            flash("The new password needs at least 8 characters.", "error")
            return redirect(url_for("auth.dashboard"))
        db.run("UPDATE users SET pw_hash = ? WHERE id = ?", (db.hash_password(new_pw), user["id"]))
    db.run("UPDATE users SET name = ?, email = ? WHERE id = ?", (name, email, user["id"]))
    flash("Account details saved.", "success")
    return redirect(url_for("auth.dashboard"))


@auth.route("/billing/portal", methods=["POST"])
@login_required
def billing_portal():
    user = current_user()
    if stripe_api.enabled() and user["stripe_customer"]:
        try:
            sess = stripe_api.portal_session(user["stripe_customer"], site_url() + url_for("auth.dashboard"))
            return redirect(sess["url"], 303)
        except stripe_api.StripeError as exc:
            flash("Could not open the billing page: %s" % exc, "error")
    else:
        flash("Billing management opens here once payments are live.", "info")
    return redirect(url_for("auth.dashboard"))


# ---- business page editing ---------------------------------------------------
@auth.route("/dashboard/profile", methods=["GET", "POST"])
@login_required
def profile_edit():
    user = current_user()
    prof = db.q("SELECT * FROM profiles WHERE user_id = ?", (user["id"],), one=True)
    if not prof:
        db.run("INSERT INTO profiles(user_id, business_name, contact_email) VALUES (?,?,?)",
               (user["id"], user["name"], user["email"]))
        prof = db.q("SELECT * FROM profiles WHERE user_id = ?", (user["id"],), one=True)
    errors = []
    if request.method == "POST":
        v = profile_values(request.form)
        if not v["business_name"]:
            errors.append("Your business needs a name.")
        if not v["address"]:
            errors.append("Please enter your business address.")
        if not v["country"]:
            errors.append("Please choose your country.")
        logo = None
        if not errors:
            try:
                logo = save_image(request.files.get("logo"), 800, keep_alpha=True)
            except ValueError as exc:
                errors.append(str(exc))
        if not errors:
            slug = prof["slug"] or db.unique_slug(v["business_name"], user["id"])
            db.run("""UPDATE profiles SET business_name=?, slug=?, tagline=?, bio=?, location=?, address=?, country=?, services=?,
                      contact_email=?, phone=?, website=?, instagram=?, facebook=?, linkedin=?, published=?
                      WHERE user_id=?""",
                   (v["business_name"], slug, v["tagline"], v["bio"], v["location"], v["address"], v["country"], v["services"],
                    v["contact_email"], v["phone"], v["website"], v["instagram"], v["facebook"], v["linkedin"],
                    1 if request.form.get("published") else 0, user["id"]))
            if logo:
                delete_public(prof["logo"])
                db.run("UPDATE profiles SET logo = ? WHERE user_id = ?", (logo, user["id"]))
            elif request.form.get("remove_logo"):
                delete_public(prof["logo"])
                db.run("UPDATE profiles SET logo = '' WHERE user_id = ?", (user["id"],))
            fresh = db.q("SELECT * FROM profiles WHERE user_id = ?", (user["id"],), one=True)
            gaps = missing_fields(fresh)
            if gaps and gets_page(user["plan"], user["founding"]):
                flash("Saved. Your page goes live once these are filled in: %s." % ", ".join(gaps).lower(), "info")
            else:
                flash("Your business page has been updated.", "success")
            return redirect(url_for("auth.profile_edit"))
    photos = db.q("SELECT * FROM gallery WHERE user_id = ? ORDER BY sort, id", (user["id"],))
    return render_template("profile_edit.html", p=dict(prof), photos=photos, errors=errors, user=user,
                           form=request.form if request.method == "POST" else None,
                           public=gets_page(user["plan"], user["founding"]), missing=missing_fields(prof))


@auth.route("/dashboard/gallery", methods=["POST"])
@login_required
def gallery_add():
    user = current_user()
    count = db.q("SELECT COUNT(*) AS n FROM gallery WHERE user_id = ?", (user["id"],), one=True)["n"]
    added = 0
    for f in request.files.getlist("photos"):
        if not f or not f.filename:
            continue
        if count + added >= 6:
            flash("You can have up to 6 photos. Remove one to add another.", "info")
            break
        try:
            name = save_image(f, 1200, quality=78, max_bytes=15 * 1024 * 1024)
        except ValueError as exc:
            flash(str(exc), "error")
            continue
        db.run("INSERT INTO gallery(user_id, path, sort) VALUES (?,?,?)", (user["id"], name, count + added))
        added += 1
    if added:
        flash("%d photo%s added." % (added, "" if added == 1 else "s"), "success")
    return redirect(url_for("auth.profile_edit") + "#gallery")


@auth.route("/dashboard/gallery/<int:photo_id>/delete", methods=["POST"])
@login_required
def gallery_delete(photo_id):
    user = current_user()
    row = db.q("SELECT * FROM gallery WHERE id = ? AND user_id = ?", (photo_id, user["id"]), one=True)
    if row:
        delete_public(row["path"])
        db.run("DELETE FROM gallery WHERE id = ?", (photo_id,))
        flash("Photo removed.", "success")
    return redirect(url_for("auth.profile_edit") + "#gallery")
