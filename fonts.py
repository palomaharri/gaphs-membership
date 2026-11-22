"""Self-hosted fonts: downloaded once from Google Fonts by the server, then served from our own site,
so visitors' browsers never contact Google. Registered from app.py with fonts.init(app)."""
import hashlib
import os
import re
import threading
import time
import urllib.request

from flask import Response, abort, send_from_directory

import db

CSS_URL = ("https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,500;0,8..60,600;1,8..60,400"
           "&family=Inter:wght@300;400;500;600&family=Montserrat:wght@300;400;500&display=swap")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
KEEP = ("latin", "latin-ext")
# the cached stylesheet is named after the font list, so a new font list is downloaded afresh
CSS_FILE = "fonts-%s.css" % hashlib.sha1(CSS_URL.encode()).hexdigest()[:10]
_lock = threading.Lock()
_last_try = [0.0]


def _dir():
    d = os.path.join(db.DATA_DIR, "fonts")
    os.makedirs(d, exist_ok=True)
    return d


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()


def _build():
    """Download the CSS and font files and save a local fonts.css. Returns True on success."""
    css = _get(CSS_URL).decode("utf-8")
    out = []
    for block in re.split(r"(?=/\* )", css):
        m = re.match(r"/\* ([a-z0-9-]+) \*/", block)
        if not m or m.group(1) not in KEEP:
            continue
        u = re.search(r"url\((https://[^)]+\.woff2)\)", block)
        if not u:
            continue
        name = hashlib.sha1(u.group(1).encode()).hexdigest()[:16] + ".woff2"
        path = os.path.join(_dir(), name)
        if not os.path.exists(path):
            data = _get(u.group(1))
            with open(path, "wb") as fh:
                fh.write(data)
        out.append(block.replace(u.group(1), "/fonts/" + name))
    if not out:
        return False
    with open(os.path.join(_dir(), CSS_FILE), "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    return True


def _ensure():
    p = os.path.join(_dir(), CSS_FILE)
    if os.path.exists(p):
        return True
    with _lock:
        if os.path.exists(p):
            return True
        if time.time() - _last_try[0] < 600:
            return False
        _last_try[0] = time.time()
        try:
            return _build()
        except Exception:
            return False


def init(app):
    @app.route("/fonts/fonts.css")
    def fonts_css():
        if _ensure():
            with open(os.path.join(_dir(), CSS_FILE), encoding="utf-8") as fh:
                body = fh.read()
            resp = Response(body, mimetype="text/css")
            resp.headers["Cache-Control"] = "public, max-age=604800"
        else:
            resp = Response("", mimetype="text/css")  # falls back to system fonts, retried later
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.route("/fonts/<name>")
    def font_file(name):
        if not re.fullmatch(r"[0-9a-f]{16}\.woff2", name):
            abort(404)
        resp = send_from_directory(_dir(), name, mimetype="font/woff2")
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp
