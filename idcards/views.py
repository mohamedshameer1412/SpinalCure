from django.utils.translation import gettext
import hashlib
import hmac
import logging

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone, translation
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit

from accounts.models import StaffProfile
from spinalcure.rbac import has_capability, require_capability
from spinalcure.utils import log_action

from . import render as card_render
from . import service, ui
from .forms import BrandingForm, IssueForm
from .models import CardVerificationLog, IDCard, IDCardBranding, normalise_card_id

logger = logging.getLogger(__name__)
LANGS = {code for code, _name in settings.LANGUAGES}
PAGE_SIZE = 15


def _lang(request):
    wanted = request.GET.get('lang') or translation.get_language() or 'en'
    wanted = wanted.split('-')[0]
    return wanted if wanted in LANGS else 'en'


def _digest(value):
    key = hashlib.sha256(b'idcard-ip:' + settings.SECRET_KEY.encode()).digest()
    return hmac.new(key, (value or '').encode(), hashlib.sha256).hexdigest()


def _client_ip(request):
    return request.META.get('REMOTE_ADDR', '')


def _no_store(resp):
    resp['Cache-Control'] = 'no-store, max-age=0'
    resp['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
    resp['Referrer-Policy'] = 'no-referrer'
    return resp


# ── management ─────────────────────────────────────────────────────────────────────────────────

@require_capability('idcards.manage')
def dashboard(request):
    q = request.GET.get('q', '').strip()
    ctype, status = request.GET.get('type', ''), request.GET.get('status', '')
    profiles = StaffProfile.objects.select_related('user').order_by('employee_id')
    if q:
        profiles = profiles.filter(Q(employee_id__icontains=q) | Q(user__first_name__icontains=q) |
                                   Q(user__last_name__icontains=q) | Q(user__username__icontains=q) |
                                   Q(designation__icontains=q) | Q(department__icontains=q))
    if ctype in ('owner', 'staff'):
        profiles = profiles.filter(user__role='owner') if ctype == 'owner' else profiles.exclude(user__role='owner')
    rows = []
    for p in profiles:
        card = p.cards.exclude(status='revoked').first() or p.cards.first()
        eff = card.effective_status if card else 'none'
        if status and status != eff:
            continue
        rows.append({'profile': p, 'card': card, 'status': eff})
    page = Paginator(rows, PAGE_SIZE).get_page(request.GET.get('page'))
    counts = {k: 0 for k in ('none', 'active', 'deactivated', 'revoked', 'expired', 'inactive')}
    for p in StaffProfile.objects.select_related('user'):
        c = p.cards.exclude(status='revoked').first() or p.cards.first()
        counts[c.effective_status if c else 'none'] += 1
    return render(request, 'idcards/dashboard.html', {
        'page': page, 'q': q, 'ctype': ctype, 'status': status, 'counts': counts,
        'statuses': ['active', 'deactivated', 'revoked', 'expired', 'inactive', 'none']})


@require_capability('idcards.manage')
def issue(request):
    form = IssueForm(request.POST or None, initial={'holder': request.GET.get('holder')})
    if request.method == 'POST' and form.is_valid():
        try:
            card = service.issue(form.cleaned_data['holder'], request.user,
                                 expires_on=form.cleaned_data['expires_on'], **form.options())
        except service.CardError as exc:
            form.add_error(None, exc.message)
        except Exception as exc:                       # model validation errors
            from django.core.exceptions import ValidationError
            if isinstance(exc, ValidationError):
                for msg in exc.messages:
                    form.add_error(None, msg)
            else:
                raise
        else:
            log_action(request, 'create', 'IDCard', f'{card.display_id} / {card.holder.employee_id}', object_id=card.pk)
            messages.success(request, gettext('ID card issued to %(value1)s.') % {'value1': card.holder.user.get_full_name() or card.holder.employee_id})
            return redirect('idcard_detail', pk=card.pk)
    return render(request, 'idcards/issue.html', {'form': form})


def _own_or_manage(request, card):
    if has_capability(request.user, 'idcards.manage'):
        return True
    return card.holder.user_id == request.user.pk


def _get_card(request, pk):
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return None, redirect_to_login(request.get_full_path())
    card = get_object_or_404(IDCard.objects.select_related('holder__user'), pk=pk)
    if not _own_or_manage(request, card):
        raise Http404            # do not reveal that someone else's card exists
    return card, None


@require_capability('idcards.manage')
def detail(request, pk):
    card = get_object_or_404(IDCard.objects.select_related('holder__user'), pk=pk)
    lang = _lang(request)
    history = IDCard.objects.filter(holder=card.holder).order_by('-created_at')
    logs = card.verifications.all()[:10]
    return render(request, 'idcards/detail.html', {
        'card': card, 'c': ui.card_context(card, lang), 'history': history, 'logs': logs, 'lang': lang,
        'share_url': settings.SITE_URL.rstrip('/') + reverse('idcard_share', args=[card.share_token]) if card.share_enabled else '',
        'languages': settings.LANGUAGES, 'can_issue_new': card.status == 'revoked'})


@require_POST
@require_capability('idcards.manage')
def action(request, pk):
    card = get_object_or_404(IDCard.objects.select_related('holder__user'), pk=pk)
    act = request.POST.get('action')
    try:
        if act == 'deactivate':
            service.deactivate(card, request.user)
            messages.success(request, gettext('Card deactivated. It no longer verifies; you can reactivate it later.'))
        elif act == 'reactivate':
            service.reactivate(card, request.user)
            messages.success(request, gettext('Card reactivated.'))
        elif act == 'revoke':
            service.revoke(card, request.user, request.POST.get('reason', ''))
            messages.success(request, gettext('Card revoked permanently.'))
        elif act == 'reissue':
            new = service.reissue(card, request.user, reason=request.POST.get('reason', 'Reissued') or 'Reissued')
            messages.success(request, gettext('New card issued. The previous card was revoked.'))
            log_action(request, 'create', 'IDCard', f'{new.display_id} (reissue)', object_id=new.pk)
            return redirect('idcard_detail', pk=new.pk)
        elif act == 'share_on':
            service.set_sharing(card, request.user, True)
            messages.success(request, gettext('Public sharing enabled.'))
        elif act == 'share_off':
            service.set_sharing(card, request.user, False)
            messages.success(request, gettext('Public sharing disabled.'))
        elif act == 'share_rotate':
            service.rotate_share_token(card, request.user)
            messages.success(request, gettext('Share link replaced. The old link no longer works.'))
        else:
            messages.error(request, gettext('Unknown action.'))
            return redirect('idcard_detail', pk=pk)
    except service.CardError as exc:
        messages.error(request, exc.message)
    else:
        log_action(request, 'update', 'IDCard', f'{card.display_id}: {act}', object_id=card.pk)
    return redirect('idcard_detail', pk=pk)


@require_capability('idcards.manage')
def branding(request):
    form = BrandingForm(request.POST or None, instance=IDCardBranding.get())
    if request.method == 'POST' and form.is_valid():
        form.save()
        log_action(request, 'update', 'IDCardBranding', 'Card branding')
        messages.success(request, gettext('Card branding saved.'))
        return redirect('idcard_branding')
    sample = IDCard.objects.select_related('holder__user').first()
    return render(request, 'idcards/branding.html', {
        'form': form, 'c': ui.card_context(sample, _lang(request)) if sample else None})


# ── personal card ──────────────────────────────────────────────────────────────────────────────

def mine(request):
    """Every signed-in user sees only their own card."""
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    cards = list(service.cards_for_user(request.user))
    card = next((c for c in cards if c.status != 'revoked'), None) or (cards[0] if cards else None)
    lang = _lang(request)
    return render(request, 'idcards/mine.html', {
        'card': card, 'c': ui.card_context(card, lang) if card else None, 'lang': lang, 'languages': settings.LANGUAGES,
        'has_profile': hasattr(request.user, 'staff_profile'),
        'share_url': (settings.SITE_URL.rstrip('/') + reverse('idcard_share', args=[card.share_token])) if card and card.share_enabled and card.is_valid else ''})


# ── authorised downloads (server-rendered fallback / non-JS) ───────────────────────────────────

def _scale(request):
    try:
        return max(1, min(3, int(request.GET.get('scale', '1'))))
    except ValueError:
        return 1


def card_png(request, pk, side):
    if side not in ('front', 'back'):
        raise Http404
    card, redirect_resp = _get_card(request, pk)
    if redirect_resp:
        return redirect_resp
    img = card_render.render_face(card, side, ui.verify_url(card), ui.org_url(card), _scale(request), _lang(request))
    resp = HttpResponse(card_render.to_png_bytes(img), content_type='image/png')
    resp['Content-Disposition'] = f'attachment; filename="id-card-{card.holder.employee_id}-{side}.png"'
    return _no_store(resp)


def card_pdf(request, pk):
    card, redirect_resp = _get_card(request, pk)
    if redirect_resp:
        return redirect_resp
    lang = _lang(request)
    faces = [card_render.render_face(card, s, ui.verify_url(card), ui.org_url(card), 3, lang) for s in ('front', 'back')]
    resp = HttpResponse(card_render.to_pdf_bytes(*faces), content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="id-card-{card.holder.employee_id}.pdf"'
    return _no_store(resp)


# ── public verification & sharing ──────────────────────────────────────────────────────────────

BAD_LOOKUPS_PER_HOUR = 12


def _record(card, result, attempted, ip):
    try:
        CardVerificationLog.objects.create(card=card, result=result, attempted=attempted[:24], ip_hash=_digest(ip))
    except Exception:
        logger.exception('verification log failed')


def _too_many_bad(ip):
    return cache.get(f'idcard_bad:{_digest(ip)}', 0) >= BAD_LOOKUPS_PER_HOUR


def _note_bad(ip):
    key = f'idcard_bad:{_digest(ip)}'
    cache.add(key, 0, timeout=3600)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=3600)


@require_GET
@ratelimit(key='ip', rate='60/m', method='GET', block=True)
def verify(request, card_id):
    """
    Public authenticity check behind the QR code. Reveals only: organisation, holder name, card type, status,
    issue/expiry dates (and the photo for an active card, if the organisation allows it). No contact details,
    employee id, designation or anything medical. Unknown and malformed ids look identical.
    """
    ip = _client_ip(request)
    if _too_many_bad(ip):
        return _no_store(HttpResponse('Too many unrecognised lookups. Please try again later.', status=429,
                                      content_type='text/plain'))
    normalised = normalise_card_id(card_id)
    card = IDCard.objects.select_related('holder__user').filter(card_id=normalised).first() if normalised else None
    if card is None:
        _note_bad(ip)
        _record(None, 'unknown', card_id, ip)
        resp = render(request, 'idcards/verify.html', {'found': False}, status=404)
        return _no_store(resp)
    status = card.effective_status
    _record(card, status, card.card_id, ip)
    from clinic.models import ClinicProfile
    clinic, brand = ClinicProfile.objects.first(), IDCardBranding.get()
    user = card.holder.user
    ctx = {
        'found': True, 'status': status, 'valid': status == 'active', 'clinic': clinic, 'brand': brand,
        'name': user.get_full_name() or user.username, 'card_type': card.get_card_type_display(),
        'issued': card.issued_on, 'expires': card.expires_on, 'tail': card.card_id[-4:],
        'photo_url': reverse('idcard_verify_photo', args=[card.card_id])
                     if (status == 'active' and brand.show_photo_on_verify and user.photo) else '',
    }
    return _no_store(render(request, 'idcards/verify.html', ctx))


@require_GET
@ratelimit(key='ip', rate='60/m', method='GET', block=True)
def verify_photo(request, card_id):
    """The holder photo shown on the public verify page: staff photos are private files, so this is the only
    public way to one, and only while the card is active and the organisation allows photos on verify."""
    from django.http import FileResponse
    normalised = normalise_card_id(card_id)
    card = IDCard.objects.select_related('holder__user').filter(card_id=normalised).first() if normalised else None
    user = card.holder.user if card else None
    if not (card and card.effective_status == 'active' and IDCardBranding.get().show_photo_on_verify and user.photo):
        raise Http404
    resp = FileResponse(user.photo.open('rb'), content_type='image/' + (user.photo.name.rsplit('.', 1)[-1].lower()
                                                                          .replace('jpg', 'jpeg')))
    resp['Cache-Control'] = 'private, max-age=300'
    resp['X-Content-Type-Options'] = 'nosniff'
    return resp


def _shared(token):
    if not token or len(token) > 64:
        raise Http404
    return get_object_or_404(IDCard.objects.select_related('holder__user'), share_token=token, share_enabled=True)


@require_GET
@ratelimit(key='ip', rate='60/m', method='GET', block=True)
def share(request, token):
    """Optional public page with link-preview metadata. Only the front, with contact details removed."""
    card = _shared(token)
    status = card.effective_status
    from clinic.models import ClinicProfile
    clinic = ClinicProfile.objects.first()
    user = card.holder.user
    name = user.get_full_name() or user.username
    org = clinic.name if clinic else 'SpinalCure'
    image_url = settings.SITE_URL.rstrip('/') + reverse('idcard_share_image', args=[token])
    resp = render(request, 'idcards/share.html', {
        'card': card, 'status': status, 'valid': status == 'active', 'name': name, 'org': org, 'clinic': clinic,
        'card_type': card.get_card_type_display(), 'image_url': image_url,
        'page_url': settings.SITE_URL.rstrip('/') + request.path,
        'verify_url': ui.verify_url(card)})
    resp['Referrer-Policy'] = 'no-referrer'
    resp['Cache-Control'] = 'public, max-age=60' if status == 'active' else 'no-store'
    return resp


@require_GET
@ratelimit(key='ip', rate='60/m', method='GET', block=True)
def share_image(request, token):
    card = _shared(token)
    if card.effective_status != 'active':
        raise Http404
    lang = _lang(request)
    img = card_render.render_face(card, 'front', ui.verify_url(card), ui.org_url(card), 1, lang, public=True)
    resp = HttpResponse(card_render.to_png_bytes(img), content_type='image/png')
    resp['Cache-Control'] = 'public, max-age=300'
    resp['Content-Disposition'] = 'inline; filename="id-card.png"'
    return resp
