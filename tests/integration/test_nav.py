import pytest
from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()

# role -> (links that must appear, links that must not)
EXPECT = {
    'superadmin': (['/appointments/availability/', '/idcards/', '/notifications/', '/payments/expenses/', '/accounts/admin/'], []),
    'receptionist': (['/appointments/', '/patients/', '/payments/', '/notifications/'],
                     ['/payments/expenses/', '/appointments/availability/', '/idcards/', '/accounts/admin/']),
    'staff': (['/notifications/', '/idcards/mine/'], ['/patients/', '/payments/', '/appointments/availability/', '/accounts/admin/']),
}


@pytest.mark.parametrize('role', EXPECT)
def test_sidebar_reflects_capabilities(role):
    u = User.objects.create_user(username=f'nav-{role}', email=f'{role}@x.com', password='x-Str0ng-pass!', role=role)
    c = Client()
    c.force_login(u)
    r = c.get('/en/notifications/')
    assert r.status_code == 200
    html = r.content.decode()
    show, hide = EXPECT[role]
    for frag in show:
        assert frag in html, f'{role} should see {frag}'
    for frag in hide:
        assert f'href="/en{frag}"' not in html, f'{role} must not see {frag}'
