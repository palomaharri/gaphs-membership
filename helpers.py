"""Shared helpers: auth, CSRF, uploads, access rules, email, formatting."""
import os
import re
import secrets
import smtplib
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from functools import wraps
from urllib.parse import parse_qs, urlparse

from flask import abort, current_app, flash, g, redirect, request, session, url_for
from PIL import Image, ImageOps

import db

Image.MAX_IMAGE_PIXELS = 60000000

# Plan keys are kept from the replica. On GAPHS: "professional" is a GAPHS Member (a trained home stager, with a
# directory page); "member" is an Associate (an industry partner: agents, developers, photographers and others).
PLANS = {
    "member": {"label": "Associate"},
    "professional": {"label": "Member"},
}

# Countries for sign-up, business pages and the directory: (ISO code, name). The code lets the directory
# suggest the visitor's own country from their browser language.
COUNTRIES = [
    ("AL", "Albania"), ("DZ", "Algeria"), ("AD", "Andorra"), ("AR", "Argentina"), ("AM", "Armenia"), ("AU", "Australia"),
    ("AT", "Austria"), ("AZ", "Azerbaijan"), ("BS", "Bahamas"), ("BH", "Bahrain"), ("BB", "Barbados"), ("BE", "Belgium"),
    ("BM", "Bermuda"), ("BO", "Bolivia"), ("BA", "Bosnia and Herzegovina"), ("BW", "Botswana"), ("BR", "Brazil"),
    ("BG", "Bulgaria"), ("CA", "Canada"), ("KY", "Cayman Islands"), ("CL", "Chile"), ("CN", "China"), ("CO", "Colombia"),
    ("CR", "Costa Rica"), ("HR", "Croatia"), ("CY", "Cyprus"), ("CZ", "Czech Republic"), ("DK", "Denmark"),
    ("DO", "Dominican Republic"), ("EC", "Ecuador"), ("EG", "Egypt"), ("EE", "Estonia"), ("FI", "Finland"),
    ("FR", "France"), ("GE", "Georgia"), ("DE", "Germany"), ("GI", "Gibraltar"), ("GR", "Greece"), ("GT", "Guatemala"),
    ("HK", "Hong Kong"), ("HU", "Hungary"), ("IS", "Iceland"), ("IN", "India"), ("ID", "Indonesia"), ("IE", "Ireland"),
    ("IL", "Israel"), ("IT", "Italy"), ("JM", "Jamaica"), ("JP", "Japan"), ("JO", "Jordan"), ("KZ", "Kazakhstan"),
    ("KE", "Kenya"), ("KW", "Kuwait"), ("LV", "Latvia"), ("LB", "Lebanon"), ("LI", "Liechtenstein"), ("LT", "Lithuania"),
    ("LU", "Luxembourg"), ("MY", "Malaysia"), ("MT", "Malta"), ("MU", "Mauritius"), ("MX", "Mexico"), ("MD", "Moldova"),
    ("MC", "Monaco"), ("ME", "Montenegro"), ("MA", "Morocco"), ("NL", "Netherlands"), ("NZ", "New Zealand"),
    ("NG", "Nigeria"), ("MK", "North Macedonia"), ("NO", "Norway"), ("OM", "Oman"), ("PA", "Panama"), ("PY", "Paraguay"),
    ("PE", "Peru"), ("PH", "Philippines"), ("PL", "Poland"), ("PT", "Portugal"), ("PR", "Puerto Rico"), ("QA", "Qatar"),
    ("RO", "Romania"), ("SA", "Saudi Arabia"), ("RS", "Serbia"), ("SG", "Singapore"), ("SK", "Slovakia"),
    ("SI", "Slovenia"), ("ZA", "South Africa"), ("KR", "South Korea"), ("ES", "Spain"), ("SE", "Sweden"),
    ("CH", "Switzerland"), ("TW", "Taiwan"), ("TH", "Thailand"), ("TN", "Tunisia"), ("TR", "Turkey"), ("UA", "Ukraine"),
    ("AE", "United Arab Emirates"), ("GB", "United Kingdom"), ("US", "United States"), ("UY", "Uruguay"),
    ("VN", "Vietnam"), ("ZZ", "Other"),
]
COUNTRY_NAMES = [name for _code, name in COUNTRIES]
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
PRIVATE_EXT = {".pdf", ".mp4", ".mov", ".m4v", ".webm", ".zip", ".docx", ".xlsx", ".pptx"}


# ---- formatting ------------------------------------------------------------
def money(pence):
    pence = int(pence or 0)
    if pence % 100 == 0:
        return "€{:,}".format(pence // 100)
    return "€{:,.2f}".format(pence / 100)


def price(key):
    return money(db.int_setting({"founding": "founding", "member_annual": "member_annual",
                                 "pro_annual": "pro_annual"}.get(key, key)))


def fmt_date(value):
    dt = db.parse_iso(value) if isinstance(value, str) else value
    return dt.strftime("%-d %B %Y") if dt else ""


def plan_label(plan):
    return PLANS.get(plan, {}).get("label", "")


# ---- auth ------------------------------------------------------------------
def current_user():
    if "user" not in g:
        uid = session.get("uid")
        g.user = db.q("SELECT * FROM users WHERE id = ?", (uid,), one=True) if uid else None
    return g.user


def has_access(user):
    """Paid-up members (and comped members, and admins) can use the members' area."""
    if not user:
        return False
    return bool(user["is_admin"] or user["comped"] or user["status"] in ("active", "past_due"))


def login_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if not current_user():
            flash("Please log in to continue.", "info")
            return redirect(url_for("auth.login", next=request.path))
        return view(*a, **kw)
    return wrapper


def member_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        user = current_user()
        if not user:
            flash("Please log in to continue.", "info")
            return redirect(url_for("auth.login", next=request.path))
        if not has_access(user):
            flash("This area is for current members. Choose a plan to join.", "info")
            return redirect(url_for("auth.dashboard") if user["status"] == "pending" else url_for("auth.join"))
        return view(*a, **kw)
    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        user = current_user()
        if not user:
            return redirect(url_for("auth.login", next=request.path))
        if not user["is_admin"]:
            abort(403)
        return view(*a, **kw)
    return wrapper


# ---- CSRF ------------------------------------------------------------------
def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


def csrf_protect():
    if request.method == "POST" and request.endpoint not in ("auth.stripe_webhook", "auth.stripe_webhook_courses"):
        sent = request.form.get("csrf") or request.headers.get("X-CSRF-Token", "")
        if not sent or not secrets.compare_digest(sent, session.get("csrf", "")):
            abort(400, "Your session expired. Go back, refresh the page and try again.")


# ---- simple login throttle -------------------------------------------------
_attempts = {}


def throttled(key, limit=8, window=600):
    now = time.time()
    hits = [t for t in _attempts.get(key, []) if now - t < window]
    _attempts[key] = hits
    return len(hits) >= limit


def record_attempt(key):
    _attempts.setdefault(key, []).append(time.time())


def clear_attempts(key):
    _attempts.pop(key, None)


# ---- membership timing -----------------------------------------------------
def days_since_start(user):
    started = db.parse_iso(user["started_at"]) if user and user["started_at"] else None
    if not started:
        return 0
    return max(0, (datetime.now(timezone.utc) - started).days)


def unlock_info(user, drip_days):
    """(unlocked, days_remaining). Annual members, comped members and admins see everything."""
    if not user:
        return False, drip_days
    if user["is_admin"] or user["comped"] or user["billing"] == "annual":
        return True, 0
    remaining = int(drip_days or 0) - days_since_start(user)
    return remaining <= 0, max(0, remaining)


def gets_page(plan, founding=0):
    """Public directory page: plans set in admin, plus every founding-rate member."""
    return plan in public_plans() or bool(founding)


def public_plans():
    return [p.strip() for p in db.setting("public_plans").split(",") if p.strip()]


def founding_taken():
    row = db.q("SELECT COUNT(*) AS n FROM users WHERE founding = 1 AND status IN ('active','past_due')", one=True)
    return row["n"]


def founding_open():
    return founding_taken() < db.int_setting("founding_limit")


# ---- uploads ---------------------------------------------------------------
def _ext(filename):
    return os.path.splitext(filename or "")[1].lower()


def save_image(file_storage, max_px=1600, keep_alpha=False, quality=86, max_bytes=None):
    """Validate and store an image in the public folder. Returns the stored file name."""
    if not file_storage or not file_storage.filename:
        return None
    if _ext(file_storage.filename) not in IMAGE_EXT:
        raise ValueError("Please upload a JPG, PNG or WebP image.")
    if max_bytes:
        st = file_storage.stream
        st.seek(0, 2)
        size = st.tell()
        st.seek(0)
        if size > max_bytes:
            raise ValueError("That photo is too large. Please choose one under %d MB." % (max_bytes // (1024 * 1024)))
    try:
        img = Image.open(file_storage.stream)
        img.load()
    except Exception:
        raise ValueError("That image could not be read.")
    img = ImageOps.exif_transpose(img)
    img.thumbnail((max_px, max_px))
    name = secrets.token_hex(10)
    if keep_alpha and img.mode in ("RGBA", "LA", "P"):
        name += ".png"
        img.convert("RGBA").save(os.path.join(db.PUBLIC_UPLOADS, name), "PNG", optimize=True)
    else:
        name += ".jpg"
        img.convert("RGB").save(os.path.join(db.PUBLIC_UPLOADS, name), "JPEG", quality=quality, optimize=True)
    return name


def save_private(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    ext = _ext(file_storage.filename)
    if ext not in PRIVATE_EXT:
        raise ValueError("Allowed files: PDF, MP4, MOV, WebM, ZIP, Word, Excel, PowerPoint.")
    name = secrets.token_hex(10) + ext
    file_storage.save(os.path.join(db.PRIVATE_UPLOADS, name))
    return name


def delete_public(name):
    if name:
        try:
            os.remove(os.path.join(db.PUBLIC_UPLOADS, os.path.basename(name)))
        except OSError:
            pass


def delete_private(name):
    if name:
        try:
            os.remove(os.path.join(db.PRIVATE_UPLOADS, os.path.basename(name)))
        except OSError:
            pass


def media_url(name):
    return url_for("auth.media", name=name) if name else ""


def img_url(key):
    """Site image: uploaded in Admin > Images, else the bundled default."""
    row = db.q("SELECT path FROM site_images WHERE key = ?", (key,), one=True)
    if row:
        return url_for("auth.media", name=row["path"])
    default = os.path.join(db.BASE_DIR, "static", "img", "site", key + ".jpg")
    if os.path.exists(default):
        return url_for("static", filename="img/site/%s.jpg" % key)
    return ""


# ---- video embeds ----------------------------------------------------------
def embed_for(url):
    """Turn a pasted video link into something the page can play."""
    url = (url or "").strip()
    if not url:
        return None
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if host in ("www.youtube.com", "youtube.com", "m.youtube.com"):
        vid = parse_qs(u.query).get("v", [""])[0] or (u.path.split("/embed/")[-1] if "/embed/" in u.path else "")
        if vid:
            return {"type": "iframe", "src": "https://www.youtube-nocookie.com/embed/" + re.sub(r"[^\w-]", "", vid)}
    if host == "youtu.be":
        return {"type": "iframe", "src": "https://www.youtube-nocookie.com/embed/" + re.sub(r"[^\w-]", "", u.path.strip("/"))}
    if host in ("vimeo.com", "www.vimeo.com", "player.vimeo.com"):
        segs = [s for s in u.path.split("/") if s]
        vid = next((s for s in segs if s.isdigit()), "")
        if vid:
            src = "https://player.vimeo.com/video/" + vid
            h = parse_qs(u.query).get("h", [""])[0]
            if not h and len(segs) > 1 and not segs[-1].isdigit():
                h = segs[-1]
            if h:
                src += "?h=" + re.sub(r"[^\w]", "", h)
            return {"type": "iframe", "src": src}
    if u.path.lower().endswith((".mp4", ".webm", ".mov", ".m4v")):
        return {"type": "video", "src": url}
    if u.scheme in ("http", "https"):
        return {"type": "link", "src": url}
    return None


# ---- email -----------------------------------------------------------------
def email_html(subject, body):
    """Wraps a plain-text message in the Association's branded email layout."""
    import re
    from html import escape
    paras = []
    for block in body.strip().split("\n\n"):
        m = re.search(r"(https?://\S+)", block)
        text = escape(block).replace("\n", "<br>")
        if m and len(block.split("\n")) == 1 and block.strip().endswith(m.group(1)):
            label = escape(block[:m.start()].strip().rstrip(":")) or "Open"
            paras.append('<p style="margin:0 0 14px;font-size:16px;line-height:1.6;color:#2A2A2A">%s</p>'
                         '<p style="margin:0 0 22px"><a href="%s" style="background:#B8963E;color:#1A1A1A;text-decoration:none;'
                         'padding:13px 26px;border-radius:2px;font-size:13px;letter-spacing:2px;text-transform:uppercase;font-weight:600;display:inline-block">Open my account</a></p>'
                         % (label, escape(m.group(1))))
        else:
            paras.append('<p style="margin:0 0 18px;font-size:16px;line-height:1.6;color:#2A2A2A">%s</p>' % text)
    return ('<!doctype html><html><body style="margin:0;padding:0;background:#F5F1E8">'
            '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" style="background:#F5F1E8;padding:32px 12px"><tr><td align="center">'
            '<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%%;background:#FFFFFF;border-radius:8px;overflow:hidden;font-family:Helvetica,Arial,sans-serif">'
            '<tr><td style="background:#1A1A1A;padding:26px 36px;color:#B8963E;font-size:12px;letter-spacing:0.22em;text-transform:uppercase">Global Association of Professional Home Stagers</td></tr>'
            '<tr><td style="padding:34px 36px 12px"><h1 style="margin:0 0 22px;font-family:Georgia,serif;font-weight:400;font-size:26px;line-height:1.25;color:#1A1A1A">%s</h1>%s</td></tr>'
            '<tr><td style="padding:8px 36px 32px;font-size:13px;line-height:1.5;color:#888888;border-top:1px solid #E8E2D4">'
            'Global Association of Professional Home Stagers &middot; info@gaphs.org</td></tr></table></td></tr></table></body></html>'
            % (escape(subject), "".join(paras)))


def send_mail(to, subject, body, html=None):
    """Sends through SMTP when configured (SMTP_HOST, SMTP_USER, SMTP_PASSWORD, MAIL_FROM)."""
    host = os.environ.get("SMTP_HOST", "")
    if not host:
        current_app.logger.info("EMAIL (SMTP not configured) to=%s subject=%s", to, subject)
        return False
    msg = EmailMessage()
    _from = os.environ.get("MAIL_FROM", os.environ.get("SMTP_USER", "no-reply@localhost"))
    if "<" not in _from:
        _from = "GAPHS <%s>" % _from
    msg["From"] = _from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    msg.add_alternative(html or email_html(subject, body), subtype="html")
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
    except Exception as exc:  # never break the page over an email
        current_app.logger.warning("Email failed: %s", exc)
        return False


def site_url():
    return os.environ.get("SITE_URL", "").rstrip("/") or request.url_root.rstrip("/")
