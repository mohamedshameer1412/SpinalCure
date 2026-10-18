import threading
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from django.urls import reverse

from patients.models import Patient
from payments.models import Payment, PaymentRefund
from payments.refunds import RefundError, refund_payment

User = get_user_model()


def user(role):
    existing = User.objects.filter(username=f'b-{role}').first()
    return existing or User.objects.create_user(username=f'b-{role}', email=f'b-{role}@x.com', password='x-Str0ng-pass!', role=role)


@pytest.fixture
def pay():
    pt = Patient.objects.create(name='Bill Payer', phone='9000000042', gender='F')
    return Payment.objects.create(patient=pt, total_amount=Decimal('1000'), amount_paid=Decimal('1000'),
                                  payment_date=date.today(), tax_type='exclusive', tax_percent=Decimal('18'))


def test_refund_reduces_net_and_cannot_exceed(pay):
    refund_payment(pay.pk, '300', 'Cancelled session', user('owner'))
    assert pay.refunded_total == Decimal('300') and pay.net_paid == Decimal('700')
    with pytest.raises(RefundError):
        refund_payment(pay.pk, '800', 'too much', user('clinicadmin'))
    refund_payment(pay.pk, '700', 'rest', user('clinicadmin'))
    with pytest.raises(RefundError):
        refund_payment(pay.pk, '0.01', 'one more', user('clinicadmin'))


@pytest.mark.parametrize('amount,reason', [('0', 'x'), ('-5', 'x'), ('abc', 'x'), ('10', '   ')])
def test_refund_validation(pay, amount, reason):
    with pytest.raises(RefundError):
        refund_payment(pay.pk, amount, reason, None)
    assert PaymentRefund.objects.count() == 0


@pytest.mark.parametrize('role,allowed', [('owner', True), ('clinicadmin', True), ('receptionist', False), ('doctor', False), ('staff', False)])
def test_refund_endpoint_permissions(pay, role, allowed):
    c = Client()
    c.force_login(user(role))
    c.post(reverse('payment_refund', args=[pay.pk]), {'amount': '100', 'reason': 'r', 'mode': 'cash'})
    assert PaymentRefund.objects.filter(payment=pay).exists() is allowed


def test_refund_requires_post(pay):
    c = Client()
    c.force_login(user('owner'))
    assert c.get(reverse('payment_refund', args=[pay.pk])).status_code == 405


@pytest.mark.parametrize('role,allowed', [('owner', True), ('receptionist', False), ('staff', False)])
def test_report_permissions_and_totals(pay, role, allowed):
    refund_payment(pay.pk, '100', 'r', user('owner'))
    c = Client()
    c.force_login(user(role))
    r = c.get(reverse('payments_report'))
    if allowed:
        assert r.status_code == 200
        assert r.context['collected'] == Decimal('1000') and r.context['refunded'] == Decimal('100')
        assert r.context['net'] == Decimal('900') and r.context['gst'] == Decimal('180.00')
    else:
        assert r.status_code == 302


def test_report_bad_dates_fall_back(pay):
    c = Client()
    c.force_login(user('owner'))
    assert c.get(reverse('payments_report'), {'from': 'nope', 'to': '2020-13-45'}).status_code == 200


def test_delete_payment_blocked_for_non_management(pay):
    c = Client()
    c.force_login(user('receptionist'))
    c.post(reverse('payment_delete', args=[pay.pk]))
    assert Payment.objects.filter(pk=pay.pk).exists()


def test_invoice_shows_refund_form_only_for_authorised(pay):
    c = Client()
    c.force_login(user('receptionist'))
    assert reverse('payment_refund', args=[pay.pk]) not in c.get(reverse('payment_invoice', args=[pay.pk])).content.decode()
    c2 = Client()
    c2.force_login(user('owner'))
    assert reverse('payment_refund', args=[pay.pk]) in c2.get(reverse('payment_invoice', args=[pay.pk])).content.decode()
