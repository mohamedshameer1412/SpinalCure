"""GST math, payment status, invoice numbering, items and refunds."""
from datetime import date
from decimal import Decimal as D

import pytest
from django.core.exceptions import ValidationError

from payments.models import Payment, Refund, financial_year
from tests.conftest_helpers import make_patient

pytestmark = pytest.mark.django_db


def pay(**kw):
    data = dict(patient=make_patient(phone=f'98765{Payment.objects.count():05d}'), total_amount=D('1000'), amount_paid=D('0'),
                payment_date=date(2026, 10, 18))
    data.update(kw)
    return Payment.objects.create(**data)


def test_exclusive_gst_split_and_status():
    p = pay(tax_type='exclusive', tax_percent=D('18'), amount_paid=D('1000'))
    assert (p.subtotal, p.tax_amount, p.cgst, p.sgst, p.igst) == (D('1000.00'), D('180.00'), D('90.00'), D('90.00'), D('0.00'))
    assert p.grand_total == D('1180.00') and p.balance == D('180.00')
    assert p.payment_status == 'partial'  # was wrongly "fully paid" before GST was counted
    p.amount_paid = D('1180')
    p.save()
    assert p.payment_status == 'fully_paid' and p.balance == 0


def test_inclusive_gst_and_odd_paise_split():
    p = pay(tax_type='inclusive', tax_percent=D('18'), total_amount=D('999.99'), amount_paid=D('999.99'))
    assert p.subtotal + p.tax_amount == D('999.99')
    assert p.cgst + p.sgst == p.tax_amount  # never loses a paisa
    assert p.payment_status == 'fully_paid'


def test_interstate_uses_igst():
    p = pay(tax_type='exclusive', tax_percent=D('18'), is_interstate=True)
    assert p.igst == D('180.00') and p.cgst == p.sgst == 0


def test_unpaid_invoice_allowed_and_overpay_rejected():
    assert pay(amount_paid=D('0')).payment_status == 'unpaid'
    with pytest.raises(ValidationError):
        pay(amount_paid=D('1000.01'))
    with pytest.raises(ValidationError):
        pay(tax_type='exclusive', tax_percent=D('0'))  # GST chosen but no rate


def test_invoice_numbers_consecutive_per_financial_year():
    a, b = pay(), pay()
    c = pay(payment_date=date(2027, 4, 1))
    assert a.receipt_number == 'SC/2026-27/00001' and b.receipt_number == 'SC/2026-27/00002'
    assert c.receipt_number == 'SC/2027-28/00001'
    assert financial_year(date(2027, 3, 31)) == '2026-27'


def test_refund_cannot_exceed_paid():
    p = pay(amount_paid=D('500'))
    Refund(payment=p, amount=D('300'), reason='x').full_clean()
    Refund.objects.create(payment=p, amount=D('300'), reason='x')
    with pytest.raises(ValidationError):
        Refund(payment=p, amount=D('201'), reason='y').full_clean()
    assert p.refunded_amount == D('300.00')


def test_receipt_and_session_pdfs_render_unicode():
    from payments.pdf_utils import generate_receipt_pdf
    p = pay(tax_type='exclusive', tax_percent=D('18'), amount_paid=D('100'), notes='internal-only-note')
    p.patient.name = 'முருகன் <b>&'
    p.items.create(description='அக்குபஞ்சர் session', sac_code='999312', quantity=2, unit_price=D('500'))
    pdf = generate_receipt_pdf(p)
    assert pdf.startswith(b'%PDF') and b'internal-only-note' not in pdf
