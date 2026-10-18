from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from patients.models import Patient
from payments.models import Payment


@pytest.fixture
def patient():
    return Patient.objects.create(name='Pay Tester', phone='9000000001', gender='M')


def make(patient, total, paid, **kw):
    return Payment.objects.create(patient=patient, total_amount=Decimal(total), amount_paid=Decimal(paid),
                                  payment_date=date.today(), **kw)


@pytest.mark.parametrize('total,paid,status', [('1000', '1000', 'fully_paid'), ('1000', '400', 'partial'), ('1000', '0.01', 'partial')])
def test_status_follows_amounts(patient, total, paid, status):
    p = make(patient, total, paid)
    assert p.payment_status == status and p.balance == Decimal(total) - Decimal(paid)


def test_overpayment_rejected(patient):
    with pytest.raises(ValidationError):
        make(patient, '100', '150')


def test_receipt_numbers_unique(patient):
    nums = {make(patient, '100', '100').receipt_number for _ in range(10)}
    assert len(nums) == 10


def test_gst_exclusive(patient):
    p = make(patient, '1000', '1', tax_type='exclusive', tax_percent=Decimal('18'))
    assert p.tax_amount == Decimal('180.00') and p.grand_total == Decimal('1180.00') and p.subtotal == Decimal('1000')


def test_gst_inclusive(patient):
    p = make(patient, '1180', '1', tax_type='inclusive', tax_percent=Decimal('18'))
    assert p.subtotal == Decimal('1000.00') and p.tax_amount == Decimal('180.00') and p.grand_total == Decimal('1180')


def test_no_tax(patient):
    p = make(patient, '500', '1', tax_type='none', tax_percent=Decimal('18'))
    assert p.tax_amount == 0 and p.grand_total == Decimal('500')


def test_exclusive_gst_balance_and_status_use_grand_total(patient):
    p = make(patient, '1000', '1000', tax_type='exclusive', tax_percent=Decimal('18'))
    assert p.payment_status == 'partial' and p.balance == Decimal('180.00')
    p2 = make(patient, '1000', '1180', tax_type='exclusive', tax_percent=Decimal('18'))
    assert p2.payment_status == 'fully_paid' and p2.balance == 0


def test_cannot_pay_more_than_grand_total(patient):
    with pytest.raises(ValidationError):
        make(patient, '1000', '1181', tax_type='exclusive', tax_percent=Decimal('18'))
