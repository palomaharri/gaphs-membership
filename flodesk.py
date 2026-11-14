"""Sends new newsletter subscribers to Flodesk. Does nothing until FLODESK_API_KEY is set."""
import base64
import json
import os
import threading
import urllib.request


def push(email, source=""):
    key = os.environ.get("FLODESK_API_KEY", "").strip()
    email = (email or "").strip()
    if not key or not email:
        return
    seg = ""
    if str(source).startswith(("edu", "course")):
        seg = os.environ.get("FLODESK_SEGMENT_EDU", "").strip()
    seg = seg or os.environ.get("FLODESK_SEGMENT_ID", "").strip()
    body = {"email": email}
    if seg:
        body["segment_ids"] = [seg]

    def work():
        try:
            token = base64.b64encode((key + ":").encode()).decode()
            req = urllib.request.Request(
                "https://api.flodesk.com/v1/subscribers",
                data=json.dumps(body).encode(),
                method="POST",
                headers={"Authorization": "Basic " + token, "Content-Type": "application/json",
                         "User-Agent": "Global Association of Professional Home Stagers (gaphs.org)"})
            urllib.request.urlopen(req, timeout=15).read()
        except Exception:
            pass

    threading.Thread(target=work, daemon=True).start()
