"""Minimal Stripe client over plain HTTPS (no extra packages needed).

Set STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET to go live. With no key set the site runs in
TEST MODE: checkout is simulated on a local page, no money moves.
"""
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.stripe.com/v1"


def secret_key(account="members"):
    """Two Stripe accounts: "members" (GAPHS memberships) and "courses" (courses and other products).
    The courses account falls back to the members key when no separate key is set."""
    main = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if account == "courses":
        return os.environ.get("STRIPE_COURSES_SECRET_KEY", "").strip() or main
    return main


def webhook_secret(account="members"):
    main = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if account == "courses":
        return os.environ.get("STRIPE_COURSES_WEBHOOK_SECRET", "").strip() or main
    return main


def enabled(account="members"):
    return bool(secret_key(account))


class StripeError(Exception):
    def __init__(self, message, status=0):
        super().__init__(message)
        self.status = status


def _flatten(value, prefix, out):
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten(v, "%s[%s]" % (prefix, k) if prefix else str(k), out)
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            _flatten(v, "%s[%d]" % (prefix, i), out)
    elif isinstance(value, bool):
        out.append((prefix, "true" if value else "false"))
    elif value is not None:
        out.append((prefix, str(value)))


def api(method, path, data=None, account="members"):
    body = None
    url = API + path
    if data:
        pairs = []
        _flatten(data, "", pairs)
        encoded = urllib.parse.urlencode(pairs)
        if method == "GET":
            url += "?" + encoded
        else:
            body = encoded.encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", "Bearer " + secret_key(account))
    if body is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            detail = ""
        raise StripeError(detail or "Stripe error %s" % exc.code, exc.code)
    except urllib.error.URLError as exc:
        raise StripeError("Could not reach Stripe: %s" % exc.reason)


def _tax():
    if os.environ.get("STRIPE_AUTOMATIC_TAX", "") in ("1", "true", "yes"):
        return {"automatic_tax": {"enabled": True}}
    return {}


def founding_coupon(amount_off_pence):
    """One-time discount that takes the first annual payment down to the founding rate."""
    coupon_id = "founding-%d" % amount_off_pence
    try:
        api("GET", "/coupons/" + coupon_id)
    except StripeError as exc:
        if exc.status != 404:
            raise
        api("POST", "/coupons", {
            "id": coupon_id, "amount_off": amount_off_pence, "currency": "eur",
            "duration": "once", "name": "Founding rate",
        })
    return coupon_id


def subscription_checkout(user, name, unit_amount, interval, success_url, cancel_url, discount_pence=0):
    data = {
        "mode": "subscription",
        "client_reference_id": str(user["id"]),
        "customer_email": user["email"],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items": [{
            "quantity": 1,
            "price_data": {
                "currency": "eur",
                "unit_amount": unit_amount,
                "recurring": {"interval": interval},
                "product_data": {"name": name},
            },
        }],
        "metadata": {"user_id": user["id"]},
        "subscription_data": {"metadata": {"user_id": user["id"]}},
    }
    if discount_pence > 0:
        data["discounts"] = [{"coupon": founding_coupon(discount_pence)}]
    data.update(_tax())
    return api("POST", "/checkout/sessions", data)


def payment_checkout(name, unit_amount, content_id, user_id, email, success_url, cancel_url):
    data = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items": [{
            "quantity": 1,
            "price_data": {"currency": "eur", "unit_amount": unit_amount, "product_data": {"name": name}},
        }],
        "metadata": {"content_id": content_id, "user_id": user_id or ""},
    }
    if email:
        data["customer_email"] = email
    data.update(_tax())
    return api("POST", "/checkout/sessions", data, account="courses")


def get_session(session_id, account="members"):
    return api("GET", "/checkout/sessions/" + session_id, account=account)


def get_subscription(sub_id):
    return api("GET", "/subscriptions/" + sub_id)


def subscription_period_end(sub):
    """Unix time the current period ends (field moved between API versions)."""
    if sub.get("current_period_end"):
        return sub["current_period_end"]
    try:
        return sub["items"]["data"][0]["current_period_end"]
    except (KeyError, IndexError, TypeError):
        return None


def portal_session(customer_id, return_url):
    return api("POST", "/billing_portal/sessions", {"customer": customer_id, "return_url": return_url})


def verify_webhook(payload, sig_header, secret, tolerance=300):
    """Check the Stripe-Signature header. Returns the parsed event or raises ValueError."""
    if not secret or not sig_header:
        raise ValueError("missing signature")
    parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
    ts = parts.get("t")
    sigs = [v for k, v in (p.split("=", 1) for p in sig_header.split(",") if "=" in p) if k == "v1"]
    if not ts or not sigs:
        raise ValueError("bad signature header")
    signed = ("%s." % ts).encode("utf-8") + payload
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in sigs):
        raise ValueError("signature mismatch")
    if abs(time.time() - int(ts)) > tolerance:
        raise ValueError("timestamp outside tolerance")
    return json.loads(payload.decode("utf-8"))
