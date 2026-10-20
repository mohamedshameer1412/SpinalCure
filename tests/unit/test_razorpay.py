"""Razorpay: only a valid signature records money, the webhook is authenticated, and a payment is applied once."""
import hashlib
import hmac
import json
from decimal import Decimal
from unittest import mock

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from patients.models import Patient
from payments import online
from payments.models import OnlineOrder, Payment

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


@override_settings(**KEYS)
def test_valid_signature_pays_once_even_if_webhook_repeats(order, payment):
    body = {'razorpay_order_id': 'order_ABC', 'razorpay_payment_id': 'pay_1', 'razorpay_signature': sig('secret', 'order_ABC|pay_1')}
    assert Client().post(reverse('online_pay_verify', args=[order.token]), data=json.dumps(body), content_type='application/json').status_code == 200
    event = json.dumps({'event': 'payment.captured', 'payload': {'payment': {'entity': {'id': 'pay_1', 'order_id': 'order_ABC', 'status': 'captured'}}}})
    r = Client().post('/payments/razorpay/webhook/', data=event, content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE=sig('whsec', event))
    assert r.status_code == 200
    payment.refresh_from_db()
    assert payment.amount_paid == Decimal('1000') and payment.payment_status == 'fully_paid' and payment.payment_mode == 'razorpay'
    assert OnlineOrder.objects.get(pk=order.pk).status == 'paid'


@override_settings(**KEYS)
def test_unsigned_webhook_is_rejected(order, payment):
    event = json.dumps({'event': 'payment.captured', 'payload': {'payment': {'entity': {'id': 'p', 'order_id': 'order_ABC', 'status': 'captured'}}}})
    assert Client().post('/payments/razorpay/webhook/', data=event, content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE='bad').status_code == 400
    payment.refresh_from_db()
    assert payment.amount_paid == Decimal('200')
