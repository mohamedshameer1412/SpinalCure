import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

User = get_user_model()
DASH = reverse('dashboard')


def login(role):
    u = User.objects.create_user(username=f'd-{role}', email=f'd-{role}@x.com', password='x-Str0ng-pass!', role=role)
    c = Client()
    c.force_login(u)
    return c


@pytest.mark.parametrize('role', ['superadmin', 'owner', 'clinicadmin', 'doctor', 'receptionist'])
def test_finance_roles_see_the_full_dashboard(role):
    r = login(role).get(DASH)
    assert r.status_code == 200 and 'Revenue Today' in r.content.decode()


def test_staff_role_gets_no_financial_data():
    r = login('staff').get(DASH)
    html = r.content.decode()
    assert r.status_code == 200 and 'Revenue' not in html and 'Pending Dues' not in html and 'revenue-data' not in html


@pytest.mark.parametrize('role', ['doctor', 'receptionist'])
def test_expense_data_is_not_embedded_for_roles_without_expense_access(role):
    html = login(role).get(DASH).content.decode()
    assert 'Expenses Today' not in html
    assert 'id="expense-data"' in html and '"total"' not in html.split('id="expense-data"')[1].split('</script>')[0]


@pytest.mark.parametrize('role,status', [('owner', 200), ('doctor', 200), ('staff', 403)])
def test_stats_api_requires_billing_access(role, status):
    assert login(role).get('/api/analytics/dashboard-stats/').status_code == status
