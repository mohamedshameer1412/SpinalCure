"""Razorpay: only a valid signature records money, the webhook is authenticated, and a payment is applied once."""
import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.core.management import call_command
from django.test import Client, override_settings
from django.utils import timezone
from django.urls import reverse

from patients.models import Patient
from payments import online
from payments.models import OnlineOrder, Payment, PaymentRefund
from payments.refunds import RefundError, refund_payment

KEYS = dict(RAZORPAY_KEY_ID='rzp_test_x', RAZORPAY_KEY_SECRET='secret', RAZORPAY_WEBHOOK_SECRET='whsec')
pytestmark = [pytest.mark.django_db]


@pytest.fixture
def payment():
    pt = Patient.objects.create(name='Ravi', phone='+919876500001')
    return Payment.objects.create(patient=pt, total_amount=Decimal('1000'), amount_paid=Decimal('200'), payment_mode='cash')


@pytest.fixture
def order(payment):
    with override_settings(**KEYS), mock.patch('payments.razorpay.create_order', return_value='order_ABC'):
        return online.create_link(payment, 'staff')


def sig(secret, msg):
    return hmac.new(secret.encode(), msg.encode() if isinstance(msg, str) else msg, hashlib.sha256).hexdigest()


def test_link_is_for_the_balance_from_the_database(order):
    assert order.amount == Decimal('800.00') and order.order_id == 'order_ABC' and len(order.token) >= 40


@override_settings(**KEYS)
def test_forged_signature_records_nothing(order, payment):
    r = Client().post(reverse('online_pay_verify', args=[order.token]), data=json.dumps(
        {'razorpay_order_id': 'order_ABC', 'razorpay_payment_id': 'pay_1', 'razorpay_signature': 'forged'}), content_type='application/json')
    assert r.status_code == 400
    payment.refresh_from_db()
    assert payment.amount_paid == Decimal('200')


def captured(pid='pay_1', order_id='order_ABC', amount=80000, currency='INR', status='captured'):
    return {'id': pid, 'order_id': order_id, 'amount': amount, 'currency': currency, 'status': status}


def hook(name, entity=None, refund=None):
    payload = {}
    if entity is not None:
        payload['payment'] = {'entity': entity}
    if refund is not None:
        payload['refund'] = {'entity': refund}
    event = json.dumps({'event': name, 'payload': payload})
    return Client().post('/payments/razorpay/webhook/', data=event, content_type='application/json',
                         HTTP_X_RAZORPAY_SIGNATURE=sig('whsec', event))


def verify(order, pid='pay_1'):
    body = {'razorpay_order_id': order.order_id, 'razorpay_payment_id': pid, 'razorpay_signature': sig('secret', f'{order.order_id}|{pid}')}
    return Client().post(reverse('online_pay_verify', args=[order.token]), data=json.dumps(body), content_type='application/json')


@override_settings(**KEYS)
def test_valid_signature_pays_once_even_if_webhook_repeats(order, payment):
    with mock.patch('payments.razorpay.fetch_payment', return_value=captured()):
        r = verify(order)
    assert r.status_code == 200 and r.json()['status'] == 'success'
    assert hook('payment.captured', captured()).status_code == 200
    assert hook('order.paid', captured()).status_code == 200
    payment.refresh_from_db()
    assert payment.amount_paid == Decimal('1000') and payment.payment_status == 'fully_paid' and payment.payment_mode == 'razorpay'
    assert OnlineOrder.objects.get(pk=order.pk).status == 'paid'


@override_settings(**KEYS)
def test_unsigned_webhook_is_rejected(order, payment):
    event = json.dumps({'event': 'payment.captured', 'payload': {'payment': {'entity': {'id': 'p', 'order_id': 'order_ABC', 'status': 'captured'}}}})
    assert Client().post('/payments/razorpay/webhook/', data=event, content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE='bad').status_code == 400
    payment.refresh_from_db()
    assert payment.amount_paid == Decimal('200')


@override_settings(**KEYS)
def test_signature_alone_does_not_record_until_razorpay_confirms_capture(order, payment):
    with mock.patch('payments.razorpay.fetch_payment', return_value=captured(status='authorized')):
        r = verify(order)
    assert r.json()['status'] == 'processing'
    payment.refresh_from_db()
    assert payment.amount_paid == Decimal('200')
    with mock.patch('payments.razorpay.fetch_payment', side_effect=online.rzp.RazorpayError('down')):
        assert verify(order).json()['status'] == 'processing'


@override_settings(**KEYS)
@pytest.mark.parametrize('entity', [captured(amount=100), captured(currency='USD')])
def test_amount_or_currency_mismatch_is_not_applied(order, payment, entity):
    assert hook('payment.captured', entity).status_code == 200
    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.amount_paid == Decimal('200') and order.status == 'created' and 'does not match' in order.failure_reason


@override_settings(**KEYS)
def test_failed_attempt_keeps_link_open_and_late_failure_never_undoes_payment(order, payment):
    hook('payment.failed', captured(status='failed') | {'error_description': 'Card declined'})
    order.refresh_from_db()
    assert order.status == 'created' and order.failure_reason == 'Card declined'
    hook('payment.captured', captured())
    hook('payment.failed', captured(pid='pay_0', status='failed') | {'error_description': 'late'})   # out of order
    order.refresh_from_db()
    assert order.status == 'paid' and order.failure_reason == 'Card declined'


@override_settings(**KEYS)
def test_new_link_cancels_old_one_and_stale_or_expired_links_are_gone(order, payment):
    with mock.patch('payments.razorpay.create_order', return_value='order_NEW'):
        new = online.create_link(payment, 'staff')
    assert OnlineOrder.objects.get(pk=order.pk).status == 'cancelled'
    assert Client().get(reverse('online_pay', args=[order.token])).status_code == 410
    assert Client().get(reverse('online_pay', args=[new.token])).status_code == 200
    payment.amount_paid = Decimal('900')
    payment.save()
    assert Client().get(reverse('online_pay', args=[new.token])).status_code == 410   # balance fell below the link amount
    payment.amount_paid = Decimal('200')
    payment.save()
    OnlineOrder.objects.filter(pk=new.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    assert Client().get(reverse('online_pay', args=[new.token])).status_code == 410


@override_settings(**KEYS)
def test_checkout_config_is_json_not_inline_js(order):
    html = Client().get(reverse('online_pay', args=[order.token])).content.decode()
    assert 'id="rzp-checkout"' in html and '"order_id": "order_ABC"' in html and 'secret' not in html


@override_settings(**KEYS)
def test_payment_on_a_cancelled_link_is_still_recorded(order, payment):
    OnlineOrder.objects.filter(pk=order.pk).update(status='cancelled')
    hook('payment.captured', captured())
    payment.refresh_from_db()
    assert payment.amount_paid == Decimal('1000')


@override_settings(**KEYS)
def test_reconcile_applies_missed_webhook_once(order, payment):
    OnlineOrder.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(minutes=30))
    with mock.patch('payments.razorpay.fetch_order_payments', return_value=[captured(pid='pay_0', status='failed'), captured()]):
        call_command('reconcile_razorpay')
        call_command('reconcile_razorpay')
    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.amount_paid == Decimal('1000') and order.status == 'paid' and order.gateway_payment_id == 'pay_1'


@override_settings(**KEYS)
def test_staff_are_notified_once_per_gateway_payment(order, payment):
    from accounts.models import CustomUser
    from notifications.models import Notification
    CustomUser.objects.create_user(username='boss', password='x', role='owner')
    hook('payment.captured', captured())
    hook('payment.captured', captured())
    assert Notification.objects.filter(event_type='online_payment_received').count() == 1


@override_settings(**KEYS)
def test_razorpay_refund_goes_through_gateway_and_webhook_updates_it(order, payment):
    hook('payment.captured', captured())
    with mock.patch('payments.razorpay.refund', return_value={'id': 'rfnd_1', 'status': 'pending'}) as m:
        r = refund_payment(payment.pk, '300', 'Course cancelled', None, mode='razorpay')
    m.assert_called_once_with('pay_1', 30000, notes=mock.ANY)
    assert r.gateway_refund_id == 'rfnd_1' and r.gateway_status == 'pending'
    hook('refund.processed', refund={'id': 'rfnd_1', 'payment_id': 'pay_1'})
    r.refresh_from_db()
    assert r.gateway_status == 'processed'


@override_settings(**KEYS)
def test_failed_gateway_refund_records_nothing(order, payment):
    hook('payment.captured', captured())
    with mock.patch('payments.razorpay.refund', side_effect=online.rzp.RazorpayError('x')), pytest.raises(RefundError):
        refund_payment(payment.pk, '300', 'x', None, mode='razorpay')
    assert not PaymentRefund.objects.exists()
    with pytest.raises(RefundError):
        refund_payment(payment.pk, '900', 'x', None, mode='razorpay')   # more than was paid online
