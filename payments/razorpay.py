"""Razorpay (https://razorpay.com/docs/api/) over plain HTTPS: orders, Checkout signature check, webhooks.

Settings (env): RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET. Use the rzp_test_ keys until the
account is activated; switching to rzp_live_ keys needs no code change.
The amount always comes from the database, never from the browser.
"""
import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request

from django.conf import settings

API = 'https://api.razorpay.com/v1'


class RazorpayError(Exception):
    pass


def enabled():
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def _call(method, path, payload=None):
    token = base64.b64encode(f'{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}'.encode()).decode()
    req = urllib.request.Request(f'{API}{path}', method=method, data=json.dumps(payload).encode() if payload else None,
                                 headers={'Authorization': f'Basic {token}', 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        raise RazorpayError(f'Razorpay error {e.code}: {detail}') from None
    except urllib.error.URLError as e:
        raise RazorpayError(f'Razorpay unreachable: {e.reason}') from None


def create_order(amount_paise, receipt, notes=None):
    """Create an order; returns its id (order_xxx)."""
    data = _call('POST', '/orders', {'amount': int(amount_paise), 'currency': 'INR', 'receipt': receipt[:40],
                                     'notes': notes or {}})
    return data['id']


def fetch_payment(payment_id):
    return _call('GET', f'/payments/{payment_id}')


def fetch_order_payments(order_id):
    """All payment attempts made against an order (used to reconcile missed webhooks)."""
    return _call('GET', f'/orders/{order_id}/payments').get('items', [])


def refund(payment_id, amount_paise, notes=None):
    """Refund (part of) a captured payment; returns the refund entity (id rfnd_xxx, status)."""
    return _call('POST', f'/payments/{payment_id}/refund', {'amount': int(amount_paise), 'notes': notes or {}})


def _hmac(secret, message):
    return hmac.new(secret.encode(), message if isinstance(message, bytes) else message.encode(), hashlib.sha256).hexdigest()


def verify_checkout_signature(order_id, payment_id, signature):
    """Checkout success handler: signature = HMAC_SHA256(key_secret, order_id|payment_id)."""
    if not (order_id and payment_id and signature and settings.RAZORPAY_KEY_SECRET):
        return False
    return hmac.compare_digest(_hmac(settings.RAZORPAY_KEY_SECRET, f'{order_id}|{payment_id}'), str(signature))


def verify_webhook_signature(raw_body, signature):
    """Webhook: X-Razorpay-Signature = HMAC_SHA256(webhook_secret, raw request body)."""
    if not (signature and settings.RAZORPAY_WEBHOOK_SECRET):
        return False
    return hmac.compare_digest(_hmac(settings.RAZORPAY_WEBHOOK_SECRET, raw_body), str(signature))
