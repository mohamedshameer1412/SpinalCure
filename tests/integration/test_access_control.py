"""Server-side authorization on real views and API endpoints."""
import pytest
from django.urls import reverse

from accounts.models import CustomUser



@pytest.mark.parametrize('role,url_name,ok', [
    ('receptionist', 'patient-list', True),
    ('staff', 'patient-list', False),
    ('receptionist', 'export_patients_csv', False),   # was open to any logged-in user
    ('doctor', 'export_patients_csv', True),
    ('receptionist', 'expense_list', False),
    ('clinic_admin', 'expense_list', True),
    ('doctor', 'admin_users', False),                  # was open via is_staff
    ('clinic_admin', 'admin_users', True),
    ('clinic_admin', 'admin_activity_log', False),
    ('owner', 'admin_activity_log', True),
    ('receptionist', 'event_list', False),
    ('doctor', 'event_list', True),
])
def test_view_access(users, login, role, url_name, ok):
    resp = login(users[role]).get(reverse(url_name))
    assert (resp.status_code == 200) is ok, (role, url_name, resp.status_code)


def test_anonymous_redirected_to_login(client, db):
    resp = client.get(reverse('patient-list'))
    assert resp.status_code == 302 and '/accounts/login/' in resp['Location']


def test_clinic_admin_cannot_create_superadmin(users, login):
    c = login(users['clinic_admin'])
    c.post(reverse('admin_user_create'), {'username': 'evil', 'email': 'evil@test.com',
                                          'password': 'Str0ng-Pass-2026!', 'role': 'superadmin'})
    assert not CustomUser.objects.filter(username='evil').exists()
    c.post(reverse('admin_user_create'), {'username': 'newdoc', 'email': 'newdoc@test.com',
                                          'password': 'Str0ng-Pass-2026!', 'role': 'doctor'})
    assert CustomUser.objects.get(username='newdoc').role == 'doctor'


def test_weak_password_rejected(users, login):
    login(users['owner']).post(reverse('admin_user_create'), {'username': 'weak', 'email': 'w@test.com',
                                                              'password': '12345678', 'role': 'staff'})
    assert not CustomUser.objects.filter(username='weak').exists()


def test_cannot_edit_or_disable_higher_rank(users, login):
    c = login(users['clinic_admin'])
    c.post(reverse('admin_user_edit', args=[users['owner'].pk]), {'role': 'staff'})
    c.post(reverse('admin_user_toggle', args=[users['owner'].pk]))
    owner = CustomUser.objects.get(pk=users['owner'].pk)
    assert owner.role == 'owner' and owner.is_active


def test_toggle_requires_post(users, login):
    resp = login(users['owner']).get(reverse('admin_user_toggle', args=[users['staff'].pk]))
    assert resp.status_code == 405
    assert CustomUser.objects.get(pk=users['staff'].pk).is_active


def test_dashboard_hides_finance_from_receptionist(users, login):
    resp = login(users['receptionist']).get(reverse('dashboard'))
    assert resp.status_code == 200
    assert resp.context['expense_monthly'] == [] and resp.context['expenses_today'] is None
    resp = login(users['staff']).get(reverse('dashboard'))
    assert resp.context['revenue_monthly'] == [] and resp.context['pending_dues'] is None


@pytest.mark.parametrize('role,method,status', [
    ('staff', 'get', 403),
    ('receptionist', 'get', 200),
    ('receptionist', 'post', 403),
])
def test_payments_api(users, client, role, method, status):
    client.force_login(users[role])
    resp = getattr(client, method)('/api/payments/', {}, content_type='application/json')
    assert resp.status_code == status


def test_public_practitioner_api_read_only(client, users):
    assert client.get('/api/clinic/practitioners/').status_code == 200
    assert client.post('/api/clinic/practitioners/', {}).status_code in (401, 403)
    client.force_login(users['doctor'])
    assert client.post('/api/clinic/practitioners/', {}).status_code == 403


def test_api_me_and_events_list_work(users, client):
    client.force_login(users['doctor'])
    assert client.get('/api/auth/me/').json()['role'] == 'doctor'
    assert client.get('/api/events/').status_code == 200


def test_patient_list_links_match_role(users, login):
    from tests.conftest_helpers import make_patient
    p = make_patient()
    html = login(users['receptionist']).get(reverse('patient-list')).content.decode()
    detail = f'"{reverse("patient-detail", args=[p.pk])}"'
    assert reverse('patient_print_card', args=[p.pk]) in html and detail not in html
    html = login(users['doctor']).get(reverse('patient-list')).content.decode()
    assert detail in html


def test_dashboard_stats_api_needs_billing_role(users, client):
    client.force_login(users['staff'])
    assert client.get('/api/analytics/dashboard-stats/').status_code == 403
    client.force_login(users['receptionist'])
    assert client.get('/api/analytics/dashboard-stats/').status_code == 200


def test_payment_form_saves_items_gst_and_refund(users, login):
    from payments.models import Payment
    from tests.conftest_helpers import make_patient
    p = make_patient()
    c = login(users['receptionist'])
    c.post(reverse('payment_create'), {
        'payer_type': 'patient', 'patient': str(p.pk), 'amount_paid': '500', 'payment_mode': 'upi',
        'payment_date': '2026-10-18', 'tax_type': 'exclusive', 'tax_percent': '18', 'total_amount': '1',
        'item_description': ['Consultation', 'Session'], 'item_sac': ['999312', ''], 'item_qty': ['1', '2'], 'item_price': ['300', '100'],
    })
    pay = Payment.objects.get()
    assert pay.total_amount == 500 and pay.items.count() == 2 and pay.grand_total == 590
    # receptionists cannot refund; admins can
    login(users['receptionist']).post(reverse('payment_refund', args=[pay.pk]), {'amount': '100', 'reason': 'x'})
    assert pay.refunds.count() == 0
    login(users['clinic_admin']).post(reverse('payment_refund', args=[pay.pk]), {'amount': '100', 'reason': 'x', 'mode': 'cash'})
    assert pay.refunds.count() == 1
    html = login(users['clinic_admin']).get(reverse('payment_invoice', args=[pay.pk])).content.decode()
    assert 'CGST 9%' in html and 'SGST 9%' in html and pay.receipt_number in html


def test_session_pdf(users, login):
    from patients.models import Session
    from tests.conftest_helpers import make_patient
    p = make_patient(name='முருகன்')
    s = Session.objects.create(patient=p, session_number=1, session_date='2026-10-01', acupoints_used='LI4, ST36\nGB34',
                               practitioner_notes='வலி குறைந்தது')
    r = login(users['doctor']).get(reverse('session-pdf', args=[s.pk]))
    assert r.status_code == 200 and r.content.startswith(b'%PDF') and 'முருகன்' not in r['Content-Disposition']
