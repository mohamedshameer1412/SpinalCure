from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils.translation import gettext

from .models import Payment, PaymentRefund


class RefundError(Exception):
    pass


def refund_payment(payment_id, amount, reason, user, mode='cash'):
    """Record a refund. Serialised on the payment row so two concurrent refunds can never exceed what was paid."""
    try:
        amount = Decimal(str(amount)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        raise RefundError(gettext('Enter a valid refund amount.'))
    reason = (reason or '').strip()
    if amount <= 0:
        raise RefundError(gettext('Refund amount must be greater than zero.'))
    if not reason:
        raise RefundError(gettext('A reason is required for a refund.'))
    if mode not in dict(Payment.PAYMENT_MODE_CHOICES):
        raise RefundError(gettext('Choose a valid refund mode.'))
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        if amount > payment.refundable:
            raise RefundError(gettext('Refund exceeds the refundable amount (₹%(max)s).') % {'max': payment.refundable})
        return PaymentRefund.objects.create(payment=payment, amount=amount, reason=reason[:300], mode=mode, refunded_by=user)
