"""Online payment links (Razorpay): create a link for a payment's balance, and record it as paid exactly once.

Every confirmation (browser callback, webhook, reconciliation) goes through apply_captured(), which checks the
captured entity against the order (status, currency, amount) before mark_paid() touches the money."""
import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from . import razorpay as rzp
from .models import OnlineOrder, Payment

logger = logging.getLogger(__name__)


def _alert(subject, detail, key):
    try:
        from notifications.service import notify_staff
        notify_staff('admin_alert', 'billing.manage', context={'subject': subject, 'detail': detail},
                     dedupe_key=f'rzp-alert:{key}')
    except Exception:
        logger.exception('Could not raise payment alert %s', key)


def create_link(payment, user=''):
    """New order for the current balance; earlier unpaid links for the same payment are cancelled so a stale link
    can never collect more than is due. Raises ValueError if nothing is due, RazorpayError if the API fails."""
    amount = Decimal(payment.balance).quantize(Decimal('0.01'))
    if amount <= 0:
        raise ValueError('Nothing is due on this payment.')
    order_id = rzp.create_order(int(amount * 100), receipt=payment.receipt_number, notes={'payment': str(payment.pk)})
    ttl = int(getattr(settings, 'RAZORPAY_LINK_TTL_HOURS', 168))
    with transaction.atomic():
        OnlineOrder.objects.filter(payment_ref=str(payment.pk), status='created').update(status='cancelled')
        return OnlineOrder.objects.create(payment_ref=str(payment.pk), amount=amount, order_id=order_id,
                                          created_by=str(user)[:150], expires_at=timezone.now() + timedelta(hours=ttl))


def apply_captured(order_id, entity):
    """Validate a Razorpay payment entity against our order and record it. Returns True only if this call paid it."""
    order = OnlineOrder.objects.filter(order_id=order_id).first()
    if order is None:
        logger.warning('Razorpay payment for unknown order %s', order_id)
        return False
    pid = str(entity.get('id', ''))[:40]
    if entity.get('status') != 'captured':
        return False
    if entity.get('currency') != 'INR' or int(entity.get('amount') or 0) != int(order.amount * 100):
        reason = f'Captured {entity.get("amount")} {entity.get("currency")} does not match order {int(order.amount * 100)} INR'
        OnlineOrder.objects.filter(pk=order.pk).update(failure_reason=reason[:300])
        _alert('Online payment needs review', f'{order.order_id} / {pid}: {reason}. Not applied to the invoice.', pid)
        return False
    return mark_paid(order_id, pid, Decimal(int(entity['amount'])) / 100)


def mark_paid(order_id, gateway_payment_id, amount_captured=None):
    """Apply a captured payment to its Payment. Idempotent: the callback, webhook and reconciliation may all arrive.
    A cancelled or expired link that was still paid is applied too: the money was taken, so it must be recorded."""
    overpaid = Decimal('0')
    with transaction.atomic():
        order = OnlineOrder.objects.select_for_update().filter(order_id=order_id).first()
        if order is None or order.status == 'paid':
            return False
        payment = Payment.objects.select_for_update().filter(pk=order.payment_ref).first()
        if payment is None:
            logger.error('Online order %s paid but its payment no longer exists', order_id)
            _alert('Online payment without invoice', f'{order_id} / {gateway_payment_id} was paid but its invoice is gone.', gateway_payment_id)
            return False
        captured = amount_captured if amount_captured is not None else order.amount
        due = max(payment.grand_total - payment.amount_paid, Decimal('0'))
        overpaid = max(captured - due, Decimal('0'))
        payment.amount_paid = min(payment.amount_paid + captured, payment.grand_total)
        payment.payment_mode = 'razorpay'
        note = f'Razorpay {gateway_payment_id}'
        payment.notes = f'{payment.notes}\n{note}'.strip() if payment.notes else note
        payment.save()
        order.status, order.gateway_payment_id, order.paid_at = 'paid', gateway_payment_id, timezone.now()
        order.amount_captured = captured
        if overpaid:
            order.reconciliation_note = f'Overpaid by {overpaid}; refund or adjust.'
        order.save(update_fields=['status', 'gateway_payment_id', 'paid_at', 'amount_captured', 'reconciliation_note'])
    if overpaid:
        _alert('Online overpayment', f'{payment.receipt_number}: {gateway_payment_id} exceeded the balance by ₹{overpaid}.', gateway_payment_id)
    try:
        from notifications.service import notify_staff
        notify_staff('online_payment_received', 'billing.view', url=reverse('payment_invoice', args=[payment.pk]),
                     context={'who': payment.receipt_number, 'amount': f'₹{captured}', 'receipt': payment.receipt_number},
                     dedupe_key=f'rzp:{gateway_payment_id}')
    except Exception:
        logger.exception('Staff notification failed for %s', payment.receipt_number)
    try:
        from .utils import send_payment_receipt_email
        send_payment_receipt_email(payment)
    except Exception:  # the money is recorded; a failed receipt email must not undo that
        logger.exception('Receipt email failed for %s', payment.receipt_number)
    return True


def record_failure(order_id, entity):
    """A failed attempt (payment.failed). The payer may retry on the same link, so the order stays open."""
    order = OnlineOrder.objects.filter(order_id=order_id).exclude(status='paid').first()
    if order is None:
        return False
    reason = str(entity.get('error_description') or entity.get('error_code') or 'failed')[:300]
    OnlineOrder.objects.filter(pk=order.pk).update(failure_reason=reason)
    return True


def reconcile(older_than_minutes=10):
    """Catch payments whose webhook never arrived: ask Razorpay about every open order and apply captured ones."""
    cutoff = timezone.now() - timedelta(minutes=older_than_minutes)
    applied = checked = 0
    for order in OnlineOrder.objects.filter(status__in=('created', 'cancelled'), created_at__lt=cutoff,
                                            created_at__gt=timezone.now() - timedelta(days=30)):
        checked += 1
        try:
            items = rzp.fetch_order_payments(order.order_id)
        except rzp.RazorpayError as e:
            logger.warning('Reconcile %s failed: %s', order.order_id, e)
            continue
        for entity in items:
            if entity.get('status') == 'captured' and apply_captured(order.order_id, entity):
                applied += 1
                OnlineOrder.objects.filter(pk=order.pk, reconciliation_note='').update(reconciliation_note='Confirmed by reconciliation')
                break
    return checked, applied
