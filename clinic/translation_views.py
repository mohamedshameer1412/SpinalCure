"""Admin > Translations: coverage per language, edit/review auto-translated website content, run auto-translate."""
from urllib.parse import urlencode

from django.apps import apps
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from spinalcure.decorators import superadmin_required
from . import content_i18n as ci

CAP = 150  # rows rendered per page; filters narrow it


@superadmin_required
def translations_page(request):
    langs = ci.target_langs()
    lang = request.GET.get('lang') if request.GET.get('lang') in langs else langs[0]
    show = request.GET.get('filter', 'todo')
    model = request.GET.get('model', '')
    q = request.GET.get('q', '').strip().lower()
    units = list(ci.iter_units(lang, [model] if model in ci.REGISTRY else None))
    for u in units:
        u.lang = lang
        u.where = f"{ci.LABELS.get(u.model_label, u.model_label)} · {u.obj_name} · {u.field.replace('_', ' ')}"
    if show == 'todo':  # needs attention: missing, outdated, or machine text nobody reviewed yet
        units = [u for u in units if u.status in ('missing', 'stale', 'auto')]
    if q:
        units = [u for u in units if q in u.source.lower() or q in u.value.lower() or q in u.obj_name.lower()]
    langs_info = {c['lang']: c for c in ci.coverage()}
    provider = ci.get_provider()
    return render(request, 'clinic/admin/translations.html', {
        'cov': list(langs_info.values()), 'active': langs_info[lang], 'lang': lang, 'show': show, 'model': model, 'q': q,
        'rtl': lang == 'ar', 'units': units[:CAP], 'hidden': max(0, len(units) - CAP),
        'models': [(k, ci.LABELS.get(k, k)) for k in ci.REGISTRY],
        'provider': provider.id if provider else None,
        'best_provider': provider is not None and provider.id != 'mymemory',
    })


@superadmin_required
@require_POST
def translation_action(request):
    p = request.POST
    lang, action = p.get('lang', ''), p.get('action', '')
    who = request.user.get_username()
    back = {'lang': lang, 'filter': p.get('filter', 'todo'), 'model': p.get('model', ''), 'q': p.get('q', '')}
    try:
        if lang not in ci.target_langs():
            raise ValueError(gettext('Unknown language.'))
        label, oid, field = p.get('model_label', ''), p.get('object_id', ''), p.get('field', '')
        if action == 'save':
            ci.save_edit(label, oid, field, lang, p.get('text', ''), who)
        elif action == 'final':
            ci.mark_final(label, oid, field, lang, who)
        elif action == 'keep':
            ci.keep_mine(label, oid, field, lang, who)
        elif action in ('save_object', 'final_object', 'translate_object'):
            # whole-record actions from the panel inside each content form
            obj = apps.get_model(label).objects.filter(pk=oid).first() if label in ci.REGISTRY else None
            if obj is None:
                raise ValueError(gettext('Unknown record.'))
            units = ci.object_units(obj, lang)
            if action == 'save_object':
                for u in units:
                    text = p.get('t__' + u.field)
                    if text is not None and text.strip() != u.value.strip():
                        ci.save_edit(label, oid, u.field, lang, text, who)
                messages.success(request, gettext('Translations saved.'))
            elif action == 'final_object':
                for u in units:
                    if u.status in ('auto', 'edited'):
                        ci.mark_final(label, oid, u.field, lang, who)
                messages.success(request, gettext('Marked as reviewed.'))
            else:
                done, errors, provider = ci.translate_units(lang, units, user=who)
                if provider is None:
                    messages.warning(request, gettext('Machine translation is turned off. Type the translations yourself.'))
                elif errors:
                    messages.error(request, ' '.join(errors))
                else:
                    messages.success(request, gettext('Translated %(n)s item(s). Please read them through.') % {'n': done})
        elif action in ('regenerate', 'translate'):
            # regenerate: one unit, even over a person's text. translate: everything a machine may write.
            units = [u for u in ci.iter_units(lang, [back['model']] if back['model'] in ci.REGISTRY else None)] if action == 'translate' \
                else [u for u in ci.iter_units(lang, [label]) if (u.object_id, u.field) == (oid, field)]
            done, errors, provider = ci.translate_units(lang, units, force=(action == 'regenerate'), user=who)
            if provider is None:
                messages.warning(request, gettext('Machine translation is turned off. Type the translations yourself.'))
            elif errors:
                messages.error(request, ' '.join(errors))
            if provider and done:
                messages.success(request, gettext('Translated %(n)s item(s). Please read them through before relying on them.') % {'n': done})
            elif provider and not errors:
                messages.info(request, gettext('Nothing to translate: everything a machine may fill is already filled.'))
        else:
            raise ValueError(gettext('Unknown action.'))
    except ValueError as e:
        messages.error(request, str(e))
    nxt = p.get('next', '')
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(nxt)
    return redirect(f"{reverse('admin_translations')}?{urlencode({k: v for k, v in back.items() if v})}")
