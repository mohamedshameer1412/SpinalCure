import io
from datetime import date
from decimal import Decimal

import pytest
from pypdf import PdfReader

from patients.models import Patient
from payments.models import Payment
from payments.pdf_utils import generate_receipt_pdf
from spinalcure.pdftext import ShapedText, needs_shaping, para
from spinalcure.utils import SpinalCureExport

ROWS = [['பிரியா நடராஜன்', 'अंकिता शर्मा', 'محمد العلي', 'A & B <i>Co</i>']]


def pdf_of(response):
    return PdfReader(io.BytesIO(response.content))


def image_count(page):
    xo = page['/Resources'].get('/XObject') or {}
    return len(xo)


def test_detects_complex_scripts_only():
    assert all(needs_shaping(t) for t in ROWS[0][:3])
    assert not needs_shaping('Plain Latin 123 ₹')


def test_para_escapes_markup_in_latin_data():
    from reportlab.lib.styles import getSampleStyleSheet
    p = para('A & B <script>x</script>', getSampleStyleSheet()['Normal'])
    assert 'A &amp; B &lt;script&gt;' in p.text


def test_export_pdf_draws_complex_script_cells_as_shaped_images():
    resp = SpinalCureExport.to_pdf(ROWS, ['Tamil', 'Hindi', 'Arabic', 'Latin'], lambda r: r, title='Names', filename_prefix='n')
    reader = pdf_of(resp)
    assert len(reader.pages) == 1 and image_count(reader.pages[0]) == 3          # three shaped cells, Latin stays text
    assert 'A & B' in reader.pages[0].extract_text()


def test_export_survives_markup_like_data():
    resp = SpinalCureExport.to_pdf([['<b>x</b> & y', None, 3]], ['a', 'b', 'c'], lambda r: r, title='t', filename_prefix='t')
    assert resp.status_code == 200 and b'%PDF' in resp.content[:8]


@pytest.mark.django_db
def test_receipt_with_tamil_payer_and_arabic_description():
    pt = Patient.objects.create(name='பிரியா நடராஜன்', phone='9000000077', gender='F')
    pay = Payment.objects.create(patient=pt, total_amount=Decimal('500'), amount_paid=Decimal('500'),
                                 payment_date=date.today(), description='جلسة علاج')
    reader = PdfReader(io.BytesIO(generate_receipt_pdf(pay)))
    assert image_count(reader.pages[0]) >= 2                                       # payer name + description


def test_shaped_text_wraps_and_has_height():
    t = ShapedText('வணக்கம் ' * 30, size=9)
    w, h = t.wrap(120, 1000)
    assert w == 120 and h > 9 * 2


@pytest.fixture
def session_obj():
    from datetime import date as d
    from patients.models import Session
    pt = Patient.objects.create(name='Session Pat', phone='9000000088', gender='M')
    return Session.objects.create(patient=pt, session_number=3, session_date=d.today(), acupoints_used='GB30\nBL40',
                                  practitioner_notes='வலி குறைந்துள்ளது\nSecond line & <b>markup</b>', pain_scale=4, mobility_score=3)


@pytest.mark.parametrize('role,status', [('doctor', 200), ('superadmin', 200), ('receptionist', 302), ('owner', 302), ('staff', 302)])
def test_session_pdf_view_is_clinical_only_and_renders(session_obj, role, status):
    from django.contrib.auth import get_user_model
    from django.test import Client
    from spinalcure.utils import encode_b64uuid
    u = get_user_model().objects.create_user(username=f'sp-{role}', email=f'sp-{role}@x.com', password='x-Str0ng-pass!', role=role)
    c = Client()
    c.force_login(u)
    r = c.get(f'/en/patients/sessions/{encode_b64uuid(session_obj.pk)}/pdf/')
    assert r.status_code == status
    if status == 200:
        assert r['Content-Type'] == 'application/pdf'
        reader = PdfReader(io.BytesIO(r.content))
        text = reader.pages[0].extract_text()
        assert 'Clinical Session Note #3' in text and 'Second line & <b>markup</b>' in text   # escaped, shown literally
        assert image_count(reader.pages[0]) >= 1                                              # the Tamil line is shaped
