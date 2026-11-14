"""Admin > Content > Import files from Google Drive.

The Library was first filled in from the GAPHS content folder in Google Drive: each item (and each course
lesson or download) remembers its Drive file in `drive_id`. This copies those files into the site's own
private storage, once. For the copy to work, the Drive folder must be shared as "Anyone with the link can
view" while it runs; afterwards set it back to Restricted. The site then serves its own copies, to members
and buyers only.
"""
import os
import re
import secrets
import threading
import urllib.parse
import urllib.request

from flask import flash, redirect, url_for

import db
from admin_views import admin
from helpers import admin_required

URL = "https://drive.usercontent.google.com/download?"
EXT = {"application/pdf": ".pdf", "video/mp4": ".mp4", "text/html": ".html"}
state = {"running": False, "done": 0, "total": 0, "current": "", "errors": []}
_lock = threading.Lock()


def _download(drive_id):
    """Saves the file into PRIVATE_UPLOADS and returns its stored name."""
    url = URL + urllib.parse.urlencode({"id": drive_id, "export": "download", "confirm": "t"})
    req = urllib.request.Request(url, headers={"User-Agent": "GAPHS membership site"})
    with urllib.request.urlopen(req, timeout=60) as r:
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip()
        disp = r.headers.get("Content-Disposition") or ""
        m = re.search(r'filename="?([^";]+)', disp)
        ext = os.path.splitext(m.group(1))[1].lower() if m else EXT.get(ctype, "")
        if ctype == "text/html" and not m:
            raise RuntimeError("Google Drive refused: share the folder as 'Anyone with the link can view' and try again")
        name = secrets.token_hex(10) + (ext or ".bin")
        tmp = os.path.join(db.PRIVATE_UPLOADS, name + ".part")
        with open(tmp, "wb") as fh:
            while True:
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                fh.write(chunk)
    os.replace(tmp, os.path.join(db.PRIVATE_UPLOADS, name))
    return name


def pending():
    """[(table, id, title, drive_id)] still to copy."""
    con = db.sqlite3.connect(db.DB_PATH)
    try:
        rows = [("content",) + tuple(r) for r in con.execute(
            "SELECT id, title, drive_id FROM content WHERE drive_id != '' AND file_private = ''")]
        rows += [("lessons",) + tuple(r) for r in con.execute(
            "SELECT id, title, drive_id FROM lessons WHERE drive_id != '' AND file_private = ''")]
        return rows
    finally:
        con.close()


def _run():
    todo = pending()
    state.update(total=len(todo), done=0, errors=[])
    for table, row_id, title, drive_id in todo:
        state["current"] = title
        try:
            name = _download(drive_id)
            con = db.sqlite3.connect(db.DB_PATH)
            con.execute("UPDATE %s SET file_private = ? WHERE id = ?" % table, (name, row_id))
            con.commit()
            con.close()
        except Exception as exc:
            state["errors"].append("%s: %s" % (title, exc))
        state["done"] += 1
    state.update(running=False, current="")


@admin.route("/content/import-drive", methods=["POST"])
@admin_required
def import_drive():
    with _lock:
        if state["running"]:
            flash("The copy from Google Drive is already running.", "info")
        elif not pending():
            flash("Every file is already in the site.", "success")
        else:
            state["running"] = True
            threading.Thread(target=_run, daemon=True).start()
            flash("Copying files from Google Drive. Refresh this page to see progress.", "info")
    return redirect(url_for("admin.content"))
