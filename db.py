"""Database layer: SQLite, schema, settings, small helpers."""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone

from flask import g

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
DB_PATH = os.path.join(DATA_DIR, "site.db")
PUBLIC_UPLOADS = os.path.join(DATA_DIR, "uploads", "public")
PRIVATE_UPLOADS = os.path.join(DATA_DIR, "uploads", "private")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  pw_hash TEXT NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  is_admin INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  reset_token TEXT, reset_expires TEXT,
  plan TEXT,                      -- member | professional
  billing TEXT,                   -- annual | monthly
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | active | past_due | canceled
  started_at TEXT, period_end TEXT,
  stripe_customer TEXT, stripe_subscription TEXT,
  founding INTEGER NOT NULL DEFAULT 0,
  qualifying_course TEXT DEFAULT '',
  agreed_at TEXT, terms_version TEXT, code_version TEXT, privacy_version TEXT,
  comped INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS profiles (
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  business_name TEXT NOT NULL DEFAULT '',
  slug TEXT UNIQUE,
  tagline TEXT DEFAULT '', bio TEXT DEFAULT '',
  logo TEXT DEFAULT '',
  location TEXT DEFAULT '', services TEXT DEFAULT '',
  contact_email TEXT DEFAULT '', phone TEXT DEFAULT '', website TEXT DEFAULT '',
  instagram TEXT DEFAULT '', facebook TEXT DEFAULT '', linkedin TEXT DEFAULT '',
  published INTEGER NOT NULL DEFAULT 1,
  approved INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS gallery (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  path TEXT NOT NULL, sort INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS content (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL, kind TEXT NOT NULL,   -- video | pdf | course
  description TEXT DEFAULT '',
  cover TEXT DEFAULT '',
  video_url TEXT DEFAULT '', file_private TEXT DEFAULT '',
  drip_days INTEGER NOT NULL DEFAULT 0,
  price INTEGER,                -- pence; set = sold in the public shop
  sort INTEGER NOT NULL DEFAULT 0,
  published INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lessons (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
  title TEXT NOT NULL, kind TEXT NOT NULL,   -- video | pdf
  video_url TEXT DEFAULT '', file_private TEXT DEFAULT '',
  drip_days INTEGER NOT NULL DEFAULT 0,
  sort INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS purchases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  content_id INTEGER NOT NULL REFERENCES content(id),
  user_id INTEGER, email TEXT DEFAULT '',
  token TEXT NOT NULL UNIQUE,
  stripe_session TEXT UNIQUE,
  amount INTEGER NOT NULL DEFAULT 0,
  paid_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS forum_categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL, description TEXT DEFAULT '', sort INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS threads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category_id INTEGER NOT NULL REFERENCES forum_categories(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id),
  title TEXT NOT NULL, pinned INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, last_post_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id),
  body TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders (
  user_id INTEGER NOT NULL, period_end TEXT NOT NULL, kind TEXT NOT NULL, sent_at TEXT NOT NULL,
  PRIMARY KEY (user_id, period_end, kind)
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS site_images (key TEXT PRIMARY KEY, path TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS subscribers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  source TEXT DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT DEFAULT '', email TEXT NOT NULL, body TEXT NOT NULL,
  created_at TEXT NOT NULL, handled INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pending_checkouts (
  token TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invites(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  label TEXT NOT NULL DEFAULT '',
  max_uses INTEGER NOT NULL DEFAULT 1,
  uses INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    # prices in cents (euros): Associate (plan "member") EUR 160, Member (plan "professional") EUR 200 a year
    "member_annual": "16000",
    "pro_annual": "20000",
    "founding": "17000",
    "member_monthly": "0",   # 0 = monthly not offered (GAPHS: yearly fees only)
    "pro_monthly": "0",
    "founding_limit": "0",     # GAPHS: no founding rate
    "reminder_days": "30,7",   # days before renewal to email members
    "founding_code": "",     # link code for existing members: /join?founding=CODE
    "public_plans": "professional,member",   # which plans get a public business page (Members and Associates)
    "terms_text": "[Draft site: paste the GAPHS Terms and Conditions in Admin > Terms and wording]",
    "code_text": "[Draft site: paste the GAPHS Code of Ethics and Conduct in Admin > Terms and wording]",
    "privacy_text": "[Draft site: paste the GAPHS Privacy Policy in Admin > Terms and wording]",
}

DEFAULT_CATEGORIES = [
    ("Introductions", "Say hello and tell us about your business and your country."),
    ("Projects and ideas", "Share projects, ask questions and swap what works."),
    ("Business and pricing", "Talk through pricing, clients and running your business."),
    ("Chapters and events", "News from GAPHS chapters, webinars and events around the world."),
]


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def q(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def run(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    if sql.lstrip().upper().startswith("INSERT INTO SUBSCRIBERS"):
        try:
            import flodesk
            flodesk.push(args[0], args[1] if len(args) > 1 else "")
        except Exception:
            pass
    return cur.lastrowid


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(PUBLIC_UPLOADS, exist_ok=True)
    os.makedirs(PRIVATE_UPLOADS, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    for k, v in DEFAULT_SETTINGS.items():
        con.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
    if "featured" not in [r[1] for r in con.execute("PRAGMA table_info(content)")]:
        con.execute("ALTER TABLE content ADD COLUMN featured INTEGER NOT NULL DEFAULT 0")
    if "category" not in [r[1] for r in con.execute("PRAGMA table_info(content)")]:
        con.execute("ALTER TABLE content ADD COLUMN category TEXT NOT NULL DEFAULT ''")
    ccols = [r[1] for r in con.execute("PRAGMA table_info(content)")]
    if "drive_id" not in ccols:   # Google Drive source file, copied in by Admin > Content > Import from Google Drive
        con.execute("ALTER TABLE content ADD COLUMN drive_id TEXT NOT NULL DEFAULT ''")
    lcols = [r[1] for r in con.execute("PRAGMA table_info(lessons)")]
    if "body" not in lcols:       # lesson text, shown under the video or PDF
        con.execute("ALTER TABLE lessons ADD COLUMN body TEXT NOT NULL DEFAULT ''")
    if "drive_id" not in lcols:
        con.execute("ALTER TABLE lessons ADD COLUMN drive_id TEXT NOT NULL DEFAULT ''")
    ucols = [r[1] for r in con.execute("PRAGMA table_info(users)")]
    for col in ("certificate_url", "portfolio_url"):   # Member applications: links to the training certificate and portfolio
        if col not in ucols:
            con.execute("ALTER TABLE users ADD COLUMN %s TEXT NOT NULL DEFAULT ''" % col)
    pcols = [r[1] for r in con.execute("PRAGMA table_info(profiles)")]
    for col in ("address", "country", "photo"):   # photo: the professional's own portrait
        if col not in pcols:
            con.execute("ALTER TABLE profiles ADD COLUMN %s TEXT NOT NULL DEFAULT ''" % col)
    if not con.execute("SELECT 1 FROM settings WHERE key='gaphs_tiers_v1'").fetchone():
        # GAPHS tiers: Member (stager) and Associate (industry partner); no founding rate, no Accredited tier
        con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('founding_limit', '0')")
        con.execute("INSERT INTO settings(key, value) VALUES ('gaphs_tiers_v1', '1')")
    if not con.execute("SELECT 1 FROM settings WHERE key='gaphs_dir_v2'").fetchone():
        # Board, November 2026: Associates also have a profile in the global directory
        con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('public_plans', 'professional,member')")
        con.execute("INSERT INTO settings(key, value) VALUES ('gaphs_dir_v2', '1')")
    if not con.execute("SELECT 1 FROM settings WHERE key='gaphs_prices_v2'").fetchone():
        # Board prices, November 2026: Member EUR 200, Associate EUR 160 a year, no monthly option
        for k, v in (("pro_annual", "20000"), ("member_annual", "16000"), ("pro_monthly", "0"), ("member_monthly", "0")):
            con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (k, v))
        con.execute("INSERT INTO settings(key, value) VALUES ('gaphs_prices_v2', '1')")
    if con.execute("SELECT COUNT(*) FROM forum_categories").fetchone()[0] == 0:
        for i, (t, d) in enumerate(DEFAULT_CATEGORIES):
            con.execute("INSERT INTO forum_categories(title, description, sort) VALUES (?,?,?)", (t, d, i))
    con.commit()
    con.close()


def setting(key, default=""):
    row = q("SELECT value FROM settings WHERE key = ?", (key,), one=True)
    return row["value"] if row else DEFAULT_SETTINGS.get(key, default)


def set_setting(key, value):
    run("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)))


def int_setting(key):
    try:
        return int(setting(key))
    except ValueError:
        return int(DEFAULT_SETTINGS.get(key, "0") or 0)


def text_version(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


# ---- passwords --------------------------------------------------------------
def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$%s$%s" % (salt.hex(), digest.hex())


def check_password(password, stored):
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def slugify(text):
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:60] or "business"


def unique_slug(base, exclude_user=None):
    slug = slugify(base)
    candidate, n = slug, 1
    while True:
        row = q("SELECT user_id FROM profiles WHERE slug = ?", (candidate,), one=True)
        if row is None or row["user_id"] == exclude_user:
            return candidate
        n += 1
        candidate = "%s-%d" % (slug, n)
