"""Blocked list: people and companies we do not accept as members or customers.
Entries are an email address, a whole domain (@company.com) or a name (person or business).
Checked on sign-up, free sign-up with a code, purchases and the sign-up forms.
Managed in Admin > Blocked list. Registered from app.py with blocklist.init(app)."""
import re
import sqlite3

from flask import abort, flash, redirect, render_template, request, url_for

import db
from helpers import admin_required

SEED = [
    ("name", "zaid shuhaiber", "Casa e Progetti"),
    ("name", "casa e progetti", "Casa e Progetti"),
    ("name", "casa & progetti", "Casa e Progetti"),
    ("name", "elaine penhaul", "Lemon and Lime"),
    ("name", "kirsty fisher", "Lemon and Lime"),
    ("name", "kirtsy fisher", "Lemon and Lime (spelling as given)"),
    ("name", "lemon and lime", "Lemon and Lime"),
    ("name", "lemon & lime", "Lemon and Lime"),
    ("name", "alex willcocks", "Burbeck"),
    ("name", "burbeck", "Burbeck"),
    ("domain", "lemonandlimeinteriors.co.uk", "Lemon and Lime (check the real domain)"),
    ("domain", "burbeckinteriors.com", "Burbeck (check the real domain)"),
]
FORM_PATHS = ("/signup", "/gift", "/invite")


def _norm(s):
    s = (s or "").lower().replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9@. ]", " ", s).split())


def _con():
    return sqlite3.connect(db.DB_PATH)


def ensure():
    con = _con()
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS blocklist(
            id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, value TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)""")
        if not con.execute("SELECT 1 FROM settings WHERE key = 'blocklist_v1'").fetchone():
            for kind, value, note in SEED:
                con.execute("INSERT INTO blocklist(kind, value, note, created_at) VALUES (?,?,?,?)",
                            (kind, _norm(value), note, db.now_iso()))
            con.execute("INSERT INTO settings(key, value) VALUES ('blocklist_v1', '1')")
        con.commit()
    finally:
        con.close()


def entries():
    con = _con()
    try:
        return con.execute("SELECT id, kind, value, note FROM blocklist").fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()


def match(email="", name="", business=""):
    """Return the matching entry (id, kind, value, note) or None."""
    email, texts = _norm(email), [_norm(name), _norm(business)]
    for e in entries():
        _id, kind, value, _n = e
        if kind == "email" and email == value:
            return e
        if kind == "domain" and email.endswith("@" + value.lstrip("@")) or (kind == "domain" and email.endswith("." + value.lstrip("@"))):
            return e
        if kind == "name" and any(value and value in t for t in texts + [email.split("@")[0].replace(".", " ")]):
            return e
    return None


def init(app):
    ensure()

    @app.before_request
    def _block_check():
        if request.method != "POST":
            return None
        p = request.path
        if not (p.startswith(FORM_PATHS) or (p.startswith("/shop/") and p.endswith("/buy")) or p.endswith("/notify")):
            return None
        hit = match(request.form.get("email"), request.form.get("name"),
                    request.form.get("business_name") or request.form.get("company"))
        if hit:
            return render_template("message.html", title="We can't accept this application",
                                   text="We are unable to process this request. If you think this is a mistake, please contact us."), 403
        return None

    @app.route("/admin/blocked", methods=["GET", "POST"], endpoint="admin_blocked")
    @admin_required
    def admin_blocked():
        if request.method == "POST":
            if request.form.get("do") == "delete":
                db.run("DELETE FROM blocklist WHERE id = ?", (request.form.get("id"),))
                flash("Removed.", "info")
            else:
                lines = [l.strip() for l in (request.form.get("entries") or "").splitlines() if l.strip()]
                kind = request.form.get("kind") if request.form.get("kind") in ("email", "domain", "name") else "name"
                note = (request.form.get("note") or "").strip()[:200]
                for l in lines:
                    v = _norm(l.lstrip("@")) if kind == "domain" else _norm(l)
                    if v and not db.q("SELECT 1 FROM blocklist WHERE kind = ? AND value = ?", (kind, v), one=True):
                        db.run("INSERT INTO blocklist(kind, value, note, created_at) VALUES (?,?,?,?)", (kind, v, note, db.now_iso()))
                flash("Added.", "info")
            return redirect(url_for("admin_blocked"))
        rows = db.q("SELECT * FROM blocklist ORDER BY note, kind, value")
        found = []
        for u in db.q("""SELECT u.id, u.name, u.email, u.status, p.business_name FROM users u
                         LEFT JOIN profiles p ON p.user_id = u.id WHERE u.is_admin = 0"""):
            if match(u["email"], u["name"], u["business_name"]):
                found.append(u)
        return render_template("admin/blocked.html", rows=rows, found=found)
