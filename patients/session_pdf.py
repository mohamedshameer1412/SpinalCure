"""Clinical session note as a PDF (ReportLab; complex scripts are shaped by spinalcure.pdftext)."""
from io import BytesIO

from django.utils import formats, timezone
from django.utils.translation import gettext as _
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, SimpleDocTemplate, Spacer

from spinalcure.pdftext import para

GREEN, DARK, GREY = colors.HexColor('#166534'), colors.HexColor('#111827'), colors.HexColor('#6b7280')


def _styles():
    base = dict(fontName='Helvetica', fontSize=10, leading=14, textColor=DARK)
    return {
        'clinic': ParagraphStyle('clinic', **{**base, 'fontName': 'Helvetica-Bold', 'fontSize': 16, 'textColor': GREEN, 'alignment': TA_CENTER, 'leading': 20}),
        'sub': ParagraphStyle('sub', **{**base, 'fontSize': 8.5, 'textColor': GREY, 'alignment': TA_CENTER}),
        'title': ParagraphStyle('title', **{**base, 'fontName': 'Helvetica-Bold', 'fontSize': 13, 'alignment': TA_CENTER, 'leading': 18}),
        'section': ParagraphStyle('section', **{**base, 'fontName': 'Helvetica-Bold', 'fontSize': 11, 'textColor': GREEN, 'leading': 16}),
        'bold': ParagraphStyle('bold', **{**base, 'fontName': 'Helvetica-Bold'}),
        'body': ParagraphStyle('body', **base),
        'foot': ParagraphStyle('foot', **{**base, 'fontSize': 8, 'textColor': GREY, 'alignment': TA_CENTER}),
    }


def build_session_note(session, clinic):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
                            title=_('Session Note - %(session_number)s') % {'session_number': session.session_number})
    s = _styles()
    story = []

    def line(label, value):
        story.append(para(f'{label} {value}' if value else label, s['body']))

    story += [para(getattr(clinic, 'name', None) or 'SpinalCure Clinic', s['clinic'])]
    if clinic:
        story.append(para((clinic.address or '').replace('\n', ', '), s['sub']))
        story.append(para(_('Phone: %(phone)s | Email: %(email)s') % {'phone': clinic.phone, 'email': clinic.email}, s['sub']))
    story += [Spacer(1, 3 * mm), HRFlowable(width='100%', thickness=1, color=GREEN), Spacer(1, 3 * mm)]
    story += [para(_('Clinical Session Note #%(session_number)s') % {'session_number': session.session_number}, s['title']), Spacer(1, 4 * mm)]

    line(_('Patient Name:'), session.patient.name)
    line(_('Patient ID:'), _('#SC-%(id)s') % {'id': str(session.patient.id)[:8]})
    line(_('Session Date:'), formats.date_format(session.session_date, 'l, F j, Y'))
    if session.consulted_by:
        line(_('Consulting Doctor:'), session.consulted_by.name)
    line(_('Duration:'), _('%(duration_minutes)s minutes') % {'duration_minutes': session.duration_minutes})

    def section(title):
        story.extend([Spacer(1, 5 * mm), para(title, s['section']), HRFlowable(width='100%', thickness=0.4, color=colors.HexColor('#d1d5db')), Spacer(1, 2 * mm)])

    section(_('Recovery Metrics'))
    line(_('Pain Scale:'), f'{session.pain_scale} / 10')
    line(_('Mobility Score:'), f'{session.mobility_score} / 5')

    def block(label, text, empty):
        story.append(para(label, s['bold']))
        for chunk in (text or empty).splitlines() or [empty]:
            story.append(para(chunk, s['body']))
        story.append(Spacer(1, 2 * mm))

    section(_('Treatment Details'))
    block(_('Acupoints Used:'), session.acupoints_used, '—')
    block(_('Techniques Employed:'), session.techniques_used, _('Not specified'))
    section(_('Clinical Notes & Observations'))
    block('', session.practitioner_notes, _('No notes recorded.'))
    section(_('Patient Feedback'))
    block('', session.patient_feedback, _('No feedback recorded.'))
    if session.next_appointment_date:
        section(_('Follow-up'))
        line(_('Next Scheduled Appointment:'), formats.date_format(session.next_appointment_date, 'F j, Y'))

    story += [Spacer(1, 10 * mm), HRFlowable(width='100%', thickness=0.4, color=colors.HexColor('#d1d5db')), Spacer(1, 2 * mm),
              para(f"{_('Generated on')} {formats.date_format(timezone.localtime(), 'F j, Y, g:i a')} {_('by SpinalCure HMS. Highly confidential medical record.')}", s['foot'])]
    doc.build(story)
    return buf.getvalue()
