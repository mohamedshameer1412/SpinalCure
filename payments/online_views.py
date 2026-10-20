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
    if payment is None or order.status == 'cancelled':
        return render(request, 'payments/online_pay.html', {'order': order, 'payment': None}, status=404)
    return render(request, 'payments/online_pay.html', {
        'order': order, 'payment': payment, 'key_id': settings.RAZORPAY_KEY_ID, 'amount_paise': int(order.amount * 100)})


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
    online.mark_paid(order.order_id, payment_id)
    return JsonResponse({'status': 'success', 'message': gettext('Payment received. Thank you! A receipt is on its way to your email.')})


@csrf_exempt
@require_POST
def webhook(request):
    """Razorpay webhook (payment.captured / order.paid). Authenticated by the X-Razorpay-Signature HMAC."""
    if not rzp.verify_webhook_signature(request.body, request.headers.get('X-Razorpay-Signature', '')):
        return HttpResponse(status=400)
    try:
        event = json.loads(request.body)
        entity = event['payload']['payment']['entity']
    except (ValueError, KeyError, TypeError):
        return HttpResponse(status=200)   # an event we do not handle
    if event.get('event') in ('payment.captured', 'order.paid') and entity.get('status') == 'captured':
        online.mark_paid(entity.get('order_id', ''), entity.get('id', ''))
    return HttpResponse(status=200)
