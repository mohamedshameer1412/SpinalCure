"""
ReportLab PDF Receipt Generator for SpinalCure payments.
Generates a professional single-page PDF receipt with clinic branding.
"""
import io
import os
from decimal import Decimal

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Brand colours ──────────────────────────────────────────────────────────
PRIMARY = colors.HexColor("#16a34a")     # green-600
PRIMARY_DARK = colors.HexColor("#14532d")  # green-900
LIGHT_BG = colors.HexColor("#f0fdf4")   # green-50
GRAY = colors.HexColor("#64748b")
DARK = colors.HexColor("#1e293b")
WHITE = colors.white
RED_STAMP = colors.HexColor("#dc2626")
ORANGE_STAMP = colors.HexColor("#d97706")
TABLE_STRIPE = colors.HexColor("#f8fafc")

W, H = A4  # 595 x 842 pts

from spinalcure.pdf_fonts import register, uni  # noqa: E402
BASE_FONT, BOLD_FONT = register()


def _styles():
    base = getSampleStyleSheet()
    return {
        "clinic_name": ParagraphStyle("clinic_name", fontSize=20, fontName=BOLD_FONT, shaping=1,
                                      textColor=WHITE, alignment=TA_LEFT, leading=24),
        "clinic_sub":  ParagraphStyle("clinic_sub", fontSize=9, fontName=BASE_FONT, shaping=1,
                                      textColor=colors.HexColor("#bbf7d0"), alignment=TA_LEFT, leading=13),
        "receipt_title": ParagraphStyle("receipt_title", fontSize=22, fontName=BOLD_FONT, shaping=1,
                                        textColor=WHITE, alignment=TA_RIGHT, leading=26),
        "receipt_num":  ParagraphStyle("receipt_num", fontSize=10, fontName=BASE_FONT, shaping=1,
                                       textColor=colors.HexColor("#bbf7d0"), alignment=TA_RIGHT),
        "label":   ParagraphStyle("label", fontSize=8, fontName=BOLD_FONT, shaping=1,
                                  textColor=GRAY, spaceAfter=1),
        "value":   ParagraphStyle("value", fontSize=10, fontName=BASE_FONT, shaping=1,
                                  textColor=DARK),
        "section": ParagraphStyle("section", fontSize=10, fontName=BOLD_FONT, shaping=1,
                                  textColor=PRIMARY_DARK, spaceBefore=4, spaceAfter=2),
        "th":      ParagraphStyle("th", fontSize=9, fontName=BOLD_FONT, shaping=1,
                                  textColor=WHITE, alignment=TA_LEFT),
        "td":      ParagraphStyle("td", fontSize=9, fontName=BASE_FONT, shaping=1, textColor=DARK),
        "td_r":    ParagraphStyle("td_r", fontSize=9, fontName=BASE_FONT, shaping=1,
                                  textColor=DARK, alignment=TA_RIGHT),
        "total_label": ParagraphStyle("total_label", fontSize=11, fontName=BOLD_FONT, shaping=1,
                                      textColor=DARK, alignment=TA_RIGHT),
        "total_val":   ParagraphStyle("total_val", fontSize=13, fontName=BOLD_FONT, shaping=1,
                                      textColor=PRIMARY_DARK, alignment=TA_RIGHT),
        "footer":  ParagraphStyle("footer", fontSize=8, fontName=BASE_FONT, shaping=1,
                                  textColor=GRAY, alignment=TA_CENTER),
        "note":    ParagraphStyle("note", fontSize=8, fontName=BASE_FONT, shaping=1,
                                  textColor=GRAY),
    }


def generate_receipt_pdf(payment) -> bytes:
    """
    Generate a ReportLab PDF receipt for a Payment instance.
    Returns raw bytes of the PDF.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=0,          # we paint the header manually
        bottomMargin=12 * mm,
    )

    # Pull clinic info
    try:
        from clinic.models import ClinicProfile
        clinic = ClinicProfile.objects.first()
    except Exception:
        clinic = None

    clinic_name = clinic.name if clinic else "SpinalCure Clinic"
    clinic_addr = (clinic.address if clinic else "").replace("\n", " | ")
    clinic_phone = clinic.phone if clinic else ""
    clinic_email = clinic.email if clinic else ""
    gstin = clinic.gstin if clinic else ""

    s = _styles()
    usable_w = W - 30 * mm   # 165 mm

    story = []

    # ── HEADER BAND (painted via canvas in onFirstPage / onLaterPages) ───────
    # We simulate a coloured header with a Table at the top of the story.
    header_data = [[
        Paragraph(f"<b>{uni(clinic_name)}</b>", s["clinic_name"]),
        Paragraph("RECEIPT", s["receipt_title"]),
    ]]
    # Sub-row: clinic details vs receipt number
    sub_text = f"{uni(clinic_addr)}<br/>{uni(clinic_phone)}  {uni(clinic_email)}"
    if gstin:
        sub_text += f"<br/>GSTIN: {uni(gstin)}"
    receipt_sub = f"{'Tax Invoice' if payment.tax_amount else 'Bill of Supply'} No: <b>{uni(payment.receipt_number)}</b>"
    header_data.append([
        Paragraph(sub_text, s["clinic_sub"]),
        Paragraph(receipt_sub, s["receipt_num"]),
    ])

    header_table = Table(header_data, colWidths=[usable_w * 0.6, usable_w * 0.4])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PRIMARY_DARK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 0), 14),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 14),
        ("LEFTPADDING", (0, 0), (0, -1), 12),
        ("RIGHTPADDING", (1, 0), (1, -1), 12),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 8 * mm))

    # ── STATUS STAMP ─────────────────────────────────────────────────────────
    status_map = {
        "fully_paid": ("PAID IN FULL", PRIMARY),
        "partial":    ("PARTIALLY PAID", ORANGE_STAMP),
        "unpaid":     ("UNPAID", RED_STAMP),
    }
    stamp_label, stamp_color = status_map.get(payment.payment_status, ("UNKNOWN", GRAY))
    stamp_data = [[Paragraph(f"<b>{stamp_label}</b>",
                             ParagraphStyle("stamp", fontSize=11, fontName=BOLD_FONT, shaping=1,
                                            textColor=WHITE, alignment=TA_CENTER))]]
    stamp = Table(stamp_data, colWidths=[usable_w])
    stamp.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), stamp_color),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    story.append(stamp)
    story.append(Spacer(1, 6 * mm))

    # ── BILLING DETAILS ROW ──────────────────────────────────────────────────
    bill_left = [
        [Paragraph("BILLED TO", s["label"])],
        [Paragraph(f"<b>{uni(payment.payer_name)}</b>", s["value"])],
        [Paragraph(uni(payment.payer_phone), s["value"])],
        [Paragraph(uni(payment.payer_address), s["note"])],
    ]
    bill_right = [
        [Paragraph("PAYMENT DATE", s["label"])],
        [Paragraph(payment.payment_date.strftime("%d %b %Y"), s["value"])],
        [Paragraph("PAYMENT MODE", s["label"])],
        [Paragraph(payment.get_payment_mode_display(), s["value"])],
    ]

    billing_table = Table(
        [[
            Table(bill_left, colWidths=[usable_w * 0.5]),
            Table(bill_right, colWidths=[usable_w * 0.5]),
        ]],
        colWidths=[usable_w * 0.5, usable_w * 0.5],
    )
    billing_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(billing_table)
    story.append(Spacer(1, 5 * mm))
    story.append(HRFlowable(width=usable_w, thickness=0.5, color=colors.HexColor("#e2e8f0")))
    story.append(Spacer(1, 5 * mm))

    # ── ITEMS TABLE ───────────────────────────────────────────────────────────
    th_style = ParagraphStyle("th2", fontSize=9, fontName=BOLD_FONT, shaping=1,
                              textColor=WHITE)
    items_header = [
        Paragraph("Description", th_style),
        Paragraph("Details", th_style),
        Paragraph("Amount", ParagraphStyle("th_r", fontSize=9, fontName=BOLD_FONT, shaping=1,
                                           textColor=WHITE, alignment=TA_RIGHT)),
    ]

    items_rows = [items_header]
    lines = list(payment.items.all())
    for it in lines:
        items_rows.append([
            Paragraph(uni(it.description), s["td"]),
            Paragraph(uni(f"{'SAC ' + it.sac_code + ' · ' if it.sac_code else ''}{it.quantity.normalize():f} × ₹{it.unit_price:,.2f}"), s["td"]),
            Paragraph(f"₹{it.line_total:,.2f}", s["td_r"]),
        ])
    if not lines:
        items_rows.append([
            Paragraph(uni(payment.description or "Treatment / service"), s["td"]),
            Paragraph(uni(payment.get_payer_type_display()), s["td"]),
            Paragraph(f"₹{payment.total_amount:,.2f}", s["td_r"]),
        ])

    items_table = Table(items_rows, colWidths=[usable_w * 0.45, usable_w * 0.30, usable_w * 0.25])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [TABLE_STRIPE, WHITE]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 4 * mm))

    # ── TOTALS ────────────────────────────────────────────────────────────────
    def tot_row(label, val, bold=False):
        lstyle = ParagraphStyle("tl", fontSize=10 if bold else 9,
                                fontName=BOLD_FONT if bold else BASE_FONT, shaping=1,
                                textColor=PRIMARY_DARK if bold else DARK,
                                alignment=TA_RIGHT)
        vstyle = ParagraphStyle("tv", fontSize=12 if bold else 10,
                                fontName=BOLD_FONT if bold else BASE_FONT, shaping=1,
                                textColor=PRIMARY_DARK if bold else DARK,
                                alignment=TA_RIGHT)
        return [Paragraph("", s["td"]), Paragraph(label, lstyle), Paragraph(val, vstyle)]

    tot_rows = []
    if payment.tax_amount:
        tot_rows.append(tot_row("Taxable value", f"₹{payment.subtotal:,.2f}"))
        if payment.is_interstate:
            tot_rows.append(tot_row(f"IGST {payment.tax_percent:g}%", f"₹{payment.igst:,.2f}"))
        else:
            tot_rows.append(tot_row(f"CGST {payment.half_rate:g}%", f"₹{payment.cgst:,.2f}"))
            tot_rows.append(tot_row(f"SGST {payment.half_rate:g}%", f"₹{payment.sgst:,.2f}"))
    tot_rows.append(tot_row("Invoice Total", f"₹{payment.grand_total:,.2f}", bold=True))
    tot_rows.append(tot_row("Amount Paid", f"₹{payment.amount_paid:,.2f}"))
    if payment.refunded_amount:
        tot_rows.append(tot_row("Refunded", f"−₹{payment.refunded_amount:,.2f}"))
    if payment.balance > 0:
        tot_rows.append(tot_row("Balance Due", f"₹{payment.balance:,.2f}", bold=True))

    tot_table = Table(tot_rows, colWidths=[usable_w * 0.45, usable_w * 0.30, usable_w * 0.25])
    tot_table.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEABOVE", (0, -1), (-1, -1), 1.0, PRIMARY),
    ]))
    story.append(tot_table)
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width=usable_w, thickness=0.5, color=colors.HexColor("#e2e8f0")))
    story.append(Spacer(1, 4 * mm))

    # ── GSTIN & NOTES ─────────────────────────────────────────────────────────
    # payment.notes are internal staff notes: never printed on the customer's receipt.
    story.append(Spacer(1, 8 * mm))

    # ── FOOTER ────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width=usable_w, thickness=0.5, color=colors.HexColor("#e2e8f0")))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        uni(f"Thank you for choosing {clinic_name}. This is a computer-generated receipt."),
        s["footer"],
    ))
    story.append(Paragraph(
        uni(f"{clinic_addr}  |  {clinic_phone}"),
        s["footer"],
    ))

    doc.build(story)
    return buffer.getvalue()
