"""Online payment (Razorpay): staff create a link, the payer pays on a public page, a webhook confirms."""
import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from spinalcure.rbac import has_capability
from . import online, razorpay as rzp
from .models import OnlineOrder, Payment

logger = logging.getLogger(__name__)


@login_required
@require_POST
def create_online_link(request, pk):
    if not has_capability(request.user, 'billing.manage'):
        messages.error(request, gettext('You do not have permission to perform this action.'))
        return redirect('dashboard')
    payment = get_object_or_404(Payment, pk=pk)
    if not rzp.enabled():
        messages.error(request, gettext('Online payments are not set up. Add the Razorpay keys first.'))
        return redirect('payment_invoice', pk=pk)
    try:
        order = online.create_link(payment, request.user.get_username())
    except ValueError:
        messages.info(request, gettext('Nothing is due on this payment.'))
        return redirect('payment_invoice', pk=pk)
    except rzp.RazorpayError as e:
        logger.error('Razorpay order failed: %s', e)
        messages.error(request, gettext('Could not create the payment link. Please try again.'))
        return redirect('payment_invoice', pk=pk)
    link = request.build_absolute_uri(reverse('online_pay', args=[order.token]))
    messages.success(request, gettext('Payment link created: %(link)s') % {'link': link})
    return redirect('payment_invoice', pk=pk)


def pay_page(request, token):
    order = get_object_or_404(OnlineOrder, token=token)
    payment = order.payment
    if payment is None:
        return render(request, 'payments/online_pay.html', {'order': order, 'payment': None}, status=404)
    if order.status != 'paid' and (order.status == 'cancelled' or order.is_expired or payment.balance < order.amount):
        # Superseded, expired, or the balance changed since the link was made: never collect a stale amount.
        return render(request, 'payments/online_pay.html', {'order': order, 'payment': None}, status=410)
    from clinic.models import ClinicProfile
    clinic = ClinicProfile.objects.first()
    return render(request, 'payments/online_pay.html', {'order': order, 'payment': payment, 'checkout': {
        'key': settings.RAZORPAY_KEY_ID, 'amount': int(order.amount * 100), 'currency': 'INR', 'order_id': order.order_id,
        'name': getattr(clinic, 'name', '') or 'Spinal Cure', 'description': payment.receipt_number,
        'prefill': {'name': str(payment.payer_name or ''), 'contact': str(payment.payer_phone or '')}}})


@require_POST
@ratelimit(key='ip', rate='30/h', method='POST', block=True)
def pay_verify(request, token):
    """Checkout success callback from the browser. Only a valid signature records the payment."""
    order = get_object_or_404(OnlineOrder, token=token)
    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return HttpResponseBadRequest()
    payment_id = str(data.get('razorpay_payment_id', ''))[:40]
    if str(data.get('razorpay_order_id', '')) != order.order_id or not rzp.verify_checkout_signature(
            order.order_id, payment_id, data.get('razorpay_signature', '')):
        logger.warning('Invalid Razorpay signature for order %s', order.order_id)
        return JsonResponse({'status': 'error', 'message': gettext('We could not verify this payment. If money was deducted, it will be confirmed automatically or refunded by Razorpay.')}, status=400)
    # A valid signature proves Razorpay authorised this payment; ask Razorpay whether it was captured, and for how much.
    try:
        entity = rzp.fetch_payment(payment_id)
    except rzp.RazorpayError as e:
        logger.warning('Could not confirm %s: %s', payment_id, e)
        entity = None
    if entity and entity.get('order_id') == order.order_id and entity.get('status') == 'captured':
        online.apply_captured(order.order_id, entity)
    order.refresh_from_db()
    if order.status == 'paid':
        return JsonResponse({'status': 'success', 'message': gettext('Payment received. Thank you! A receipt is on its way to your email.')})
    return JsonResponse({'status': 'processing', 'message': gettext('Your payment is being confirmed. You will receive a receipt once it is complete; there is no need to pay again.')})


@csrf_exempt
@require_POST
def webhook(request):
    """Razorpay webhook, authenticated by the X-Razorpay-Signature HMAC over the raw body. Events may repeat or arrive
    out of order; every handler is idempotent and a later event never undoes a paid order."""
    if not rzp.verify_webhook_signature(request.body, request.headers.get('X-Razorpay-Signature', '')):
        return HttpResponse(status=400)
    try:
        event = json.loads(request.body)
        name, payload = event.get('event', ''), event.get('payload') or {}
    except (ValueError, AttributeError):
        return HttpResponse(status=200)
    entity = ((payload.get('payment') or {}).get('entity')) or {}
    if name in ('payment.captured', 'order.paid'):
        online.apply_captured(entity.get('order_id', ''), entity)
    elif name == 'payment.failed':
        online.record_failure(entity.get('order_id', ''), entity)
    elif name in ('refund.processed', 'refund.failed'):
        refund = ((payload.get('refund') or {}).get('entity')) or {}
        _refund_update(str(refund.get('id', ''))[:40], 'processed' if name == 'refund.processed' else 'failed')
    return HttpResponse(status=200)


def _refund_update(refund_id, status):
    from .models import PaymentRefund
    if not refund_id:
        return
    updated = PaymentRefund.objects.filter(gateway_refund_id=refund_id).exclude(gateway_status=status).update(gateway_status=status)
    if updated and status == 'failed':
        online._alert('Razorpay refund failed', f'Refund {refund_id} failed at the gateway; return the money another way.', refund_id)
