"""Online payment links (Razorpay): create a link for a payment's balance, and record it as paid exactly once."""
import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from . import razorpay as rzp
from .models import OnlineOrder, Payment

logger = logging.getLogger(__name__)


def create_link(payment, user=''):
    """New order for the current balance. Raises ValueError if nothing is due, RazorpayError if the API fails."""
    amount = Decimal(payment.balance).quantize(Decimal('0.01'))
    if amount <= 0:
        raise ValueError('Nothing is due on this payment.')
    order_id = rzp.create_order(int(amount * 100), receipt=payment.receipt_number, notes={'payment': str(payment.pk)})
    return OnlineOrder.objects.create(payment_ref=str(payment.pk), amount=amount, order_id=order_id, created_by=str(user)[:150])


def mark_paid(order_id, gateway_payment_id):
    """Apply a captured payment to its Payment. Idempotent: the browser callback and the webhook may both arrive."""
    with transaction.atomic():
        order = OnlineOrder.objects.select_for_update().filter(order_id=order_id).first()
        if order is None or order.status == 'paid':
            return False
        payment = Payment.objects.select_for_update().filter(pk=order.payment_ref).first()
        if payment is None:
            logger.error('Online order %s paid but payment %s no longer exists', order_id, order.payment_ref)
            return False
        payment.amount_paid = min(payment.amount_paid + order.amount, payment.grand_total)
        payment.payment_mode = 'razorpay'
        note = f'Razorpay {gateway_payment_id}'
        payment.notes = f'{payment.notes}\n{note}'.strip() if payment.notes else note
        payment.save()
        order.status, order.gateway_payment_id, order.paid_at = 'paid', gateway_payment_id, timezone.now()
        order.save(update_fields=['status', 'gateway_payment_id', 'paid_at'])
    try:
        from .utils import send_payment_receipt_email
        send_payment_receipt_email(payment)
    except Exception:  # the money is recorded; a failed receipt email must not undo that
        logger.exception('Receipt email failed for %s', payment.receipt_number)
    return True
