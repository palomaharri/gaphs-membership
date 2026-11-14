"""Renewal reminder emails: sent automatically before a membership renews, and manually from Admin > Renewals."""
import os
import threading
import time
from datetime import timedelta

import db
from helpers import money, send_mail

PLAN_KEYS = {("member", "annual"): "member_annual", ("member", "monthly"): "member_monthly",
             ("professional", "annual"): "pro_annual", ("professional", "monthly"): "pro_monthly"}


def reminder_days():
    out = []
    for part in (db.setting("reminder_days", "30,7") or "").split(","):
        part = part.strip()
        if part.isdigit() and int(part) > 0:
            out.append(int(part))
    return sorted(set(out), reverse=True)


def upcoming(days=45):
    """Active, auto-renewing members whose period ends within `days`."""
    now = db.parse_iso(db.now_iso())
    rows = db.q("""SELECT * FROM users WHERE status = 'active' AND comped = 0 AND is_admin = 0
                   AND plan IS NOT NULL AND period_end IS NOT NULL ORDER BY period_end""")
    out = []
    for r in rows:
        end = db.parse_iso(r["period_end"])
        if end and now <= end <= now + timedelta(days=days):
            out.append((r, end, (end - now).days))
    return out


def send_reminder(user, end, kind):
    """Sends one reminder and records it, so it can never go out twice for the same renewal."""
    site = os.environ.get("SITE_URL", "").rstrip("/")
    import mails
    subject, text, html = mails.renewal(user, end, site)
    ok = send_mail(user["email"], subject, text, html)
    if ok:
        db.run("INSERT OR IGNORE INTO reminders(user_id, period_end, kind, sent_at) VALUES (?,?,?,?)",
               (user["id"], user["period_end"], kind, db.now_iso()))
    return ok


def run_due():
    """Sends every reminder that is due and not yet sent. Returns how many went out."""
    sent = 0
    for user, end, left in upcoming(max(reminder_days() or [0])):
        for d in reminder_days():
            if left <= d:
                kind = "r%d" % d
                # only the nearest window that applies (avoid sending 30 and 7 on the same day)
                nxt = [x for x in reminder_days() if left <= x]
                if d != min(nxt):
                    continue
                if db.q("SELECT 1 FROM reminders WHERE user_id=? AND period_end=? AND kind=?",
                        (user["id"], user["period_end"], kind), one=True):
                    continue
                if send_reminder(user, end, kind):
                    sent += 1
    return sent


def start_background(app):
    """Checks every 6 hours. Safe with several workers: a reminder is recorded once sent."""
    def loop():
        time.sleep(60)
        while True:
            try:
                with app.app_context():
                    run_due()
            except Exception as exc:
                app.logger.warning("Reminder run failed: %s", exc)
            time.sleep(6 * 3600)
    threading.Thread(target=loop, daemon=True).start()
