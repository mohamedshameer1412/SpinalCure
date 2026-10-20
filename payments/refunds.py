from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils.translation import gettext

from . import razorpay as rzp
from .models import OnlineOrder, Payment, PaymentRefund


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
        gateway_id = gateway_status = ''
        if mode == 'razorpay':
            # Money goes back through the gateway; the refund is only recorded if Razorpay accepted it.
            order = OnlineOrder.objects.filter(payment_ref=str(payment.pk), status='paid').exclude(
                gateway_payment_id='').order_by('-paid_at').first()
            if order is None:
                raise RefundError(gettext('No online payment found to refund through Razorpay. Choose another refund mode.'))
            if amount > (order.amount_captured or order.amount):
                raise RefundError(gettext('Refund exceeds the online payment (₹%(max)s).') % {'max': order.amount_captured or order.amount})
            try:
                entity = rzp.refund(order.gateway_payment_id, int(amount * 100), notes={'receipt': payment.receipt_number})
            except rzp.RazorpayError:
                raise RefundError(gettext('Razorpay did not accept the refund. Nothing was recorded; please try again.'))
            gateway_id, gateway_status = str(entity.get('id', ''))[:40], str(entity.get('status', ''))[:20]
        return PaymentRefund.objects.create(payment=payment, amount=amount, reason=reason[:300], mode=mode, refunded_by=user,
                                            gateway_refund_id=gateway_id, gateway_status=gateway_status)
