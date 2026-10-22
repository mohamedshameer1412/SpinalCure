"""Student ID cards, drawn by the same renderer as staff cards (idcards.render) so both look alike.

A student card is not stored: it is computed from the Student and the registration it is for, so it can never get out
of step with their details. The student code is the card number; the QR code opens the public verification page.
"""
from datetime import timedelta
from types import SimpleNamespace

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from idcards import render


def verify_url(student):
    return settings.SITE_URL.rstrip('/') + reverse('student_verify', args=[student.student_code])


def _status(reg):
    if reg.status != 'confirmed':
        return 'revoked'
    end = valid_until(reg)
    return 'expired' if end < timezone.localdate() else 'active'


def valid_until(reg):
    """The batch's end date, or a year after it starts when no end date is set."""
    return reg.batch.end_date or (reg.batch.start_date + timedelta(days=365))


def card_for(reg):
    """A duck-typed stand-in for idcards.IDCard that render.card_data() can read."""
    st, batch = reg.student, reg.batch
    user = SimpleNamespace(get_full_name=lambda: st.name, username=st.name, photo=st.photo, phone=st.phone, email=st.email)
    holder = SimpleNamespace(
        user=user, employee_id=st.student_code, designation=batch.course.title, department=batch.name,
        contact_phone=st.phone, contact_email=st.email, joined_on=batch.start_date, emergency_contact_name='',
        emergency_contact_phone='', blood_group=st.blood_group, skills='', GENDER_CHOICES=st.GENDER_CHOICES,
        gender=st.gender, date_of_birth=st.date_of_birth, address=st.address)
    status = _status(reg)
    return SimpleNamespace(
        holder=holder, card_type='student', get_card_type_display=lambda: 'Student', issued_on=(st.profile_completed_at or timezone.now()).date(),
        expires_on=valid_until(reg), effective_status=status, display_id=st.student_code, card_id=st.student_code,
        show_phone=True, show_email=False, show_blood_group=True, show_skills=False, show_emergency_contact=False)


def face(reg, side, scale=1, lang='en'):
    card = card_for(reg)
    url = verify_url(reg.student)
    return render.render_face(card, side, url, url, scale, lang)


def png(reg, side, scale=2, lang='en'):
    return render.to_png_bytes(face(reg, side, scale, lang))


def pdf(reg, lang='en'):
    return render.to_pdf_bytes(face(reg, 'front', 3, lang), face(reg, 'back', 3, lang))


def best_registration(student):
    """The registration a card is drawn for: the newest confirmed one, else the newest."""
    regs = list(student.registrations.select_related('batch__course').order_by('-registered_at'))
    return next((r for r in regs if r.status == 'confirmed'), regs[0] if regs else None)
