"""Session clinical note as PDF (ReportLab with Unicode fonts, so Tamil/Hindi notes print correctly)."""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from spinalcure.pdf_fonts import register, uni


def _para(text, style, default=''):
    text = (text or '').strip() or default
    return Paragraph('<br/>'.join(uni(line) for line in text.splitlines()), style)


def session_note_pdf(session, clinic):
    regular, bold = register()
    base = dict(fontName=regular, shaping=1)
    h1 = ParagraphStyle('h1', fontName=bold, fontSize=16, leading=20, shaping=1, textColor=colors.HexColor('#14532d'))
    small = ParagraphStyle('s', fontSize=8.5, leading=11, textColor=colors.HexColor('#475569'), **base)
    label = ParagraphStyle('l', fontName=bold, fontSize=8, leading=10, shaping=1, textColor=colors.HexColor('#64748b'))
    body = ParagraphStyle('b', fontSize=10, leading=14, **base)
    h2 = ParagraphStyle('h2', fontName=bold, fontSize=11, leading=14, shaping=1, spaceBefore=8, spaceAfter=3)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f'Session {session.session_number}', author=clinic.name if clinic else 'SpinalCure')
    story = [Paragraph(uni(clinic.name if clinic else 'SpinalCure Clinic'), h1)]
    if clinic:
        story.append(Paragraph(' · '.join(uni(x) for x in (clinic.address, clinic.phone, clinic.email) if x), small))
    story += [Spacer(1, 4 * mm), HRFlowable(width='100%', color=colors.HexColor('#e2e8f0')), Spacer(1, 3 * mm)]

    facts = [
        ('PATIENT', session.patient.name), ('PATIENT ID', session.patient.patient_id_str or str(session.patient.pk)[:8]),
        ('SESSION', f'#{session.session_number}'), ('DATE', session.session_date.strftime('%d %b %Y')),
        ('PRACTITIONER', session.consulted_by.name if session.consulted_by else '—'),
        ('DURATION', f'{session.duration_minutes} min'),
        ('PAIN (0-10)', session.pain_scale if session.pain_scale is not None else '—'),
        ('MOBILITY (0-10)', session.mobility_score if session.mobility_score is not None else '—'),
    ]
    cells = [[Paragraph(k, label), Paragraph(uni(v), body)] for k, v in facts]
    rows = [cells[i] + cells[i + 1] for i in range(0, len(cells), 2)]
    t = Table(rows, colWidths=[28 * mm, 57 * mm, 28 * mm, 57 * mm])
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    story.append(t)

    for title, value, default in [
        ('Acupoints used', session.acupoints_used, '—'),
        ('Techniques used', session.techniques_used, 'Not specified'),
        ('Practitioner notes', session.practitioner_notes, 'No notes recorded.'),
        ('Patient feedback', session.patient_feedback, 'No feedback recorded.'),
    ]:
        story += [Paragraph(title, h2), _para(value, body, default)]
    if session.next_appointment_date:
        story += [Paragraph('Next appointment', h2), Paragraph(session.next_appointment_date.strftime('%d %b %Y'), body)]
    story += [Spacer(1, 8 * mm), Paragraph('Confidential clinical record. Do not share without the patient\'s consent.', small)]
    doc.build(story)
    return buf.getvalue()
