import base64
from io import BytesIO

import qrcode
import qrcode.image.svg
from django import forms
from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.models import CustomUser
from clinic.models import ClinicProfile
from notifications.services import notify_users
from spinalcure.decorators import role_required
from spinalcure.utils import client_ip, log_action, rate_limited
from .models import IDCard


def qr_data_uri(url):
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=1)
    buf = BytesIO()
    img.save(buf)
    return 'data:image/svg+xml;base64,' + base64.b64encode(buf.getvalue()).decode()


class CardForm(forms.ModelForm):
    class Meta:
        model = IDCard
        fields = ['user', 'card_type', 'designation', 'department', 'phone', 'show_email', 'joining_date', 'expiry_date',
                  'blood_group', 'emergency_contact', 'skills', 'photo']
        widgets = {'joining_date': forms.DateInput(attrs={'type': 'date'}), 'expiry_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields.pop('user')  # a card never moves to another person
        else:
            has_card = IDCard.objects.filter(status__in=('active', 'suspended')).values('user')
            self.fields['user'].queryset = CustomUser.objects.filter(is_active=True).exclude(pk__in=has_card).order_by('first_name', 'username')
            self.fields['user'].label_from_instance = lambda u: f'{u.get_full_name() or u.username} ({u.get_role_display()})'
        for f in self.fields.values():
            if not isinstance(f.widget, (forms.CheckboxInput, forms.ClearableFileInput)):
                f.widget.attrs.setdefault('class', 'w-full px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm')

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and hasattr(photo, 'size') and photo.size > 3 * 1024 * 1024:
            raise forms.ValidationError('Photo must be under 3 MB.')
        return photo

    def clean(self):
        data = super().clean()
        user = data.get('user')
        if user and not user.get_full_name():
            self.add_error('user', 'Add this person\'s first and last name to their account before issuing a card.')
        if data.get('expiry_date') and data.get('joining_date') and data['expiry_date'] <= data['joining_date']:
            self.add_error('expiry_date', 'Expiry must be after the joining date.')
        return data


def _card_context(request, card):
    verify_url = request.build_absolute_uri(reverse('idcard_verify', args=[card.verify_token]))
    clinic = ClinicProfile.objects.first()
    org_url = request.build_absolute_uri(reverse('clinic_portfolio'))
    return {
        'card': card, 'clinic': clinic, 'verify_url': verify_url,
        'share_url': request.build_absolute_uri(reverse('idcard_share', args=[card.verify_token])),
        'front_qr': qr_data_uri(verify_url), 'back_qr': qr_data_uri(org_url), 'org_url': org_url,
        'photo_url': card.photo.url if card.photo else (card.user.photo.url if card.user.photo else ''),
    }


@role_required('idcards_manage')
def card_list(request):
    q = request.GET.get('q', '').strip()
    cards = IDCard.objects.select_related('user')
    if q:
        cards = cards.filter(Q(card_number__icontains=q) | Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q)
                             | Q(designation__icontains=q) | Q(department__icontains=q))
    status = request.GET.get('status', '')
    if status in dict(IDCard.STATUS):
        cards = cards.filter(status=status)
    return render(request, 'idcards/list.html', {'cards': cards, 'q': q, 'status': status})


@role_required('idcards_manage')
def card_form(request, pk=None):
    card = get_object_or_404(IDCard, pk=pk) if pk else None
    form = CardForm(request.POST or None, request.FILES or None, instance=card)
    if request.method == 'POST' and form.is_valid():
        new = card is None
        card = form.save(commit=False)
        if new:
            card.issued_by = request.user
        card.save()
        log_action(request, 'create' if new else 'update', 'IDCard', str(card), object_id=card.pk)
        if new:
            notify_users([card.user], 'idcard_issued', 'Your ID card has been issued',
                         f'Card {card.card_number} is ready to view and download.', reverse('my_idcard'),
                         dedupe_key=f'idcard:{card.pk}:{card.version}')
        messages.success(request, f'ID card {card.card_number} {"issued" if new else "updated"}.')
        return redirect('idcard_detail', pk=card.pk)
    if not card and request.GET.get('user'):
        form.initial['user'] = request.GET['user']
    return render(request, 'idcards/form.html', {'form': form, 'card': card})


@role_required('dashboard_view')
def card_detail(request, pk):
    card = get_object_or_404(IDCard.objects.select_related('user'), pk=pk)
    if card.user_id != request.user.pk and not request.user.can('idcards_manage'):
        raise Http404  # staff see only their own card
    return render(request, 'idcards/detail.html', _card_context(request, card))


@role_required('dashboard_view')
def my_card(request):
    card = request.user.id_cards.exclude(status='revoked').order_by('-created_at').first()
    if not card:
        return render(request, 'idcards/detail.html', {'card': None})
    return render(request, 'idcards/detail.html', _card_context(request, card))


@require_POST
@role_required('idcards_manage')
def card_action(request, pk):
    card = get_object_or_404(IDCard, pk=pk)
    action, reason = request.POST.get('action'), request.POST.get('reason', '').strip()[:200]
    if card.status == 'revoked':
        messages.error(request, 'A revoked card cannot be changed. Issue a new card instead.')
    elif action == 'reissue':
        card.reissue()
        notify_users([card.user], 'idcard_issued', 'Your ID card was reissued',
                     'Previously printed or shared copies no longer verify. Download the new card.', reverse('my_idcard'),
                     dedupe_key=f'idcard:{card.pk}:{card.version}')
        messages.success(request, 'Card reissued. Old QR codes no longer verify.')
    elif action in ('suspend', 'revoke'):
        if not reason:
            messages.error(request, 'Please give a reason.')
            return redirect('idcard_detail', pk=pk)
        card.status, card.status_reason = ('suspended' if action == 'suspend' else 'revoked'), reason
        card.save(update_fields=['status', 'status_reason', 'updated_at'])
        if action == 'revoke':
            notify_users([card.user], 'idcard_revoked', 'Your ID card was revoked', '', reverse('dashboard'),
                         dedupe_key=f'idcard-revoked:{card.pk}')
        messages.success(request, f'Card {card.status}.')
    elif action == 'activate' and card.status == 'suspended':
        card.status, card.status_reason = 'active', ''
        card.save(update_fields=['status', 'status_reason', 'updated_at'])
        messages.success(request, 'Card reactivated.')
    else:
        messages.error(request, 'Unknown action.')
        return redirect('idcard_detail', pk=pk)
    log_action(request, 'update', 'IDCard', f'{card} {action}', object_id=card.pk, changes={'action': {'old': '', 'new': action}})
    return redirect('idcard_detail', pk=pk)


def _public_card(request, token):
    if rate_limited(f'idverify:{client_ip(request)}', 30, 60):
        return None, render(request, 'idcards/verify.html', {'rate_limited': True}, status=429)
    card = IDCard.objects.select_related('user').filter(verify_token=token).first()
    return card, None


def verify(request, token):
    """Public: authenticity and status only. No contact details, blood group or emergency contact."""
    card, limited = _public_card(request, token)
    if limited:
        return limited
    resp = render(request, 'idcards/verify.html', {'card': card, 'clinic': ClinicProfile.objects.first()},
                  status=200 if card else 404)
    resp['X-Robots-Tag'] = 'noindex'
    resp['Referrer-Policy'] = 'no-referrer'
    return resp


def share(request, token):
    """Public share page with Open Graph / Twitter tags; same limited data as verification."""
    card, limited = _public_card(request, token)
    if limited:
        return limited
    if not card or not card.is_valid:
        raise Http404
    clinic = ClinicProfile.objects.first()
    logo = request.build_absolute_uri(clinic.logo.url) if clinic and clinic.logo else ''
    resp = render(request, 'idcards/share.html', {
        'card': card, 'clinic': clinic, 'og_image': logo,
        'verify_url': request.build_absolute_uri(reverse('idcard_verify', args=[token])),
    })
    resp['X-Robots-Tag'] = 'noindex'
    return resp


def sync_with_user(user):
    """Called when an account is deactivated: active cards are suspended so printed cards stop verifying."""
    if not user.is_active:
        IDCard.objects.filter(user=user, status='active').update(status='suspended', status_reason='Account deactivated')
