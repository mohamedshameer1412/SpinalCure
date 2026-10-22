"""What the public site says about opening hours and where the clinic is, derived from live data.

Opening hours come from the doctors' weekly availability (the same hours patients can actually book), so changing
Availability changes the website's footer and contact section at once. The old free-text "working hours" is used only when
no weekly hours have been set. The map link opens Google Maps: the clinic's own link if one was entered, else the listing
found in its map embed, else a search for the address.
"""
from urllib.parse import quote

from django.utils.dates import WEEKDAYS_ABBR
from django.utils.formats import time_format
from django.utils.translation import gettext

DAYS = range(7)


def _merge(spans):
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _day_range(days):
    """[0, 1, 2, 3, 5] -> 'Mon–Thu, Sat'"""
    parts, i = [], 0
    days = sorted(days)
    while i < len(days):
        j = i
        while j + 1 < len(days) and days[j + 1] == days[j] + 1:
            j += 1
        a, b = str(WEEKDAYS_ABBR[days[i]]), str(WEEKDAYS_ABBR[days[j]])
        parts.append(a if i == j else (f'{a}, {b}' if j == i + 1 else f'{a}–{b}'))
        i = j + 1
    return ', '.join(parts)


def weekly_hours():
    """One line per group of days that share the same hours, or '' when no weekly hours are set."""
    from appointments.models import DoctorAvailability
    per_day = {d: [] for d in DAYS}
    for a in DoctorAvailability.objects.filter(is_available=True, practitioner__is_active=True).only(
            'day_of_week', 'start_time', 'end_time'):
        if a.day_of_week in per_day:
            per_day[a.day_of_week].append((a.start_time, a.end_time))
    if not any(per_day.values()):
        return ''
    groups = {}
    for d in DAYS:
        groups.setdefault(tuple(_merge(per_day[d])), []).append(d)
    lines = []
    for spans, days in sorted(groups.items(), key=lambda kv: (not kv[0], kv[1][0])):
        text = ', '.join(f"{time_format(a, 'g:i a')} – {time_format(b, 'g:i a')}" for a, b in spans) if spans else gettext('Closed')
        lines.append(f'{_day_range(days)}: {text}')
    return '\n'.join(lines)


def opening_hours(clinic):
    from .content_i18n import tx
    return weekly_hours() or (tx(clinic, 'working_hours') if clinic else '')


def map_url(clinic):
    if not clinic or not (clinic.address or clinic.map_link):
        return ''
    if clinic.map_link:
        return clinic.map_link
    from spinalcure.seo import _map_facts
    try:
        _geo, listing = _map_facts(clinic)
    except Exception:
        listing = ''
    return listing or 'https://www.google.com/maps/search/?api=1&query=' + quote(' '.join((clinic.address or '').split()))
