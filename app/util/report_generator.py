from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether,
    BaseDocTemplate, PageTemplate, Frame, NextPageTemplate
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from datetime import datetime
from app.util.time_utils import local_now
import os

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


pdfmetrics.registerFont(
    TTFont("DejaVu", "app/util/fonts/DejaVuSans.ttf")
)
pdfmetrics.registerFont(
    TTFont("DejaVu-Bold", "app/util/fonts/DejaVuSans-Bold.ttf")
    if os.path.exists("app/util/fonts/DejaVuSans-Bold.ttf") else
    TTFont("DejaVu-Bold", "app/util/fonts/DejaVuSans.ttf")
)

LOGO_PATH = "app/util/assets/scalancer_logo.png"

# Human-readable label for the report_type passed in from report_routes.py
# ("today" / "weekly" / "monthly" / "custom").
REPORT_TYPE_LABELS = {
    "today": "Daily Report",
    "daily": "Daily Report",
    "weekly": "Weekly Report",
    "monthly": "Monthly Report",
    "custom": "Custom Range Report",
}


def report_type_label(report_type):
    return REPORT_TYPE_LABELS.get((report_type or "").lower(), "Analytics Report")


def period_range_label(period_start, period_end):
    """Human-readable date range the report's figures were pulled from,
    e.g. 'July 31, 2026' for a single day or 'July 01 – July 31, 2026'
    for a range. Falls back to None if no period was supplied (caller
    then shows today's date, as before)."""
    if not period_start or not period_end:
        return None

    if period_start == period_end:
        return period_start.strftime("%B %d, %Y")

    if period_start.year == period_end.year:
        if period_start.month == period_end.month:
            return f"{period_start.strftime('%B %d')} – {period_end.strftime('%d, %Y')}"
        return f"{period_start.strftime('%B %d')} – {period_end.strftime('%B %d, %Y')}"

    return f"{period_start.strftime('%B %d, %Y')} – {period_end.strftime('%B %d, %Y')}"

# ================= PAGE GEOMETRY =================
# The teal header band is drawn full-bleed (edge-to-edge) directly on the
# canvas — not as a flowable — so its background actually reaches the true
# page edges. Everything else keeps normal margins (no border/frame drawn
# around the body content).
PAGE_W, PAGE_H = A4
LEFT_MARGIN = 1.4 * cm
RIGHT_MARGIN = 1.4 * cm
BOTTOM_MARGIN = 2.5 * cm
TOP_MARGIN_LATER = 1.6 * cm

# Content width matches the (zero-padding) frame width exactly, since the
# Frames below are built with left/right padding = 0.
TOTAL_WIDTH = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN

BAND_HEIGHT = 3.3 * cm
RULE_HEIGHT = 0.09 * cm
GAP_BELOW_RULE = 0.6 * cm
TOP_MARGIN_FIRST = BAND_HEIGHT + RULE_HEIGHT + GAP_BELOW_RULE

# ================= CHAMPAGNE PALETTE =================
TEAL = colors.HexColor("#0F6E56")
TEAL_DEEP = colors.HexColor("#085041")
GOLD = colors.HexColor("#B8895A")
GOLD_DEEP = colors.HexColor("#8A6526")
INK = colors.HexColor("#1A1A18")
MUTED = colors.HexColor("#6B6455")
MUTED_LIGHT = colors.HexColor("#9A8F79")
CREAM = colors.HexColor("#FBF7EC")
GOLD_TINT = colors.HexColor("#F3ECDD")
TEAL_TINT = colors.HexColor("#DDEEEE")
HAIRLINE = colors.HexColor("#EFE9DA")
WHITE = colors.white


# ================= HAIRLINE TABLE (Daily Sales / Top Products / Peak Hours) =================
def hairline_table(data, header_color):
    col_count = len(data[0])
    col_width = TOTAL_WIDTH / col_count
    col_widths = [col_width] * col_count

    table = Table(data, colWidths=col_widths, repeatRows=1)

    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "DejaVu"),

        ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"),
        ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, INK),

        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("FONTSIZE", (0, 1), (-1, -1), 9.5),
        ("LINEBELOW", (0, 1), (-1, -2), 0.5, HAIRLINE),

        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),

        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    return table


# ================= SECTION LABEL (gold/teal vertical tick + caps title) =================
def section_label(text, accent_color):
    # A single-row, two-cell table: the first cell is left empty and simply
    # painted with the accent color, giving a vertical "tick" bar without
    # nesting a Table inside a Table (nested fixed-width tables confuse
    # ReportLab's column-width solver and can throw negative-width errors).
    label = Paragraph(
        f"<font color='#1A1A18'><b>{text.upper()}</b></font>",
        ParagraphStyle(
            "SectionLabel", fontSize=12.5, fontName="DejaVu-Bold",
            textColor=INK, leading=14
        )
    )

    bar_width = 0.1 * cm
    row = Table(
        [["", label]],
        colWidths=[bar_width, TOTAL_WIDTH - bar_width],
        rowHeights=[0.5 * cm],
    )
    row.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), accent_color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (1, 0), (1, 0), 10),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return row


# ================= HERO KPI CARDS (Revenue / Bills / Avg Bill) =================
def kpi_cards(currency_symbol, revenue, bills, average):
    def card(label, value, bg, label_color):
        p_label = Paragraph(
            f"<font color='{label_color}' size='8'><b>{label}</b></font>",
            ParagraphStyle("KpiLabel", fontName="DejaVu-Bold", leading=10)
        )
        p_value = Paragraph(
            f"<font color='#1A1A18' size='14'><b>{value}</b></font>",
            ParagraphStyle("KpiValue", fontName="DejaVu-Bold", leading=17, spaceBefore=3)
        )
        t = Table([[p_label], [p_value]], colWidths=[(TOTAL_WIDTH - 0.6 * cm) / 3])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ]))
        return t

    spacer = Spacer(0.3 * cm, 1)

    row = Table(
        [[
            card("REVENUE", f"{currency_symbol}{revenue:,.2f}", GOLD_TINT, "#8A6526"),
            spacer,
            card("BILLS", f"{bills}", TEAL_TINT, "#085041"),
            spacer,
            card("AVG BILL", f"{currency_symbol}{average:,.2f}", GOLD_TINT, "#8A6526"),
        ]],
        colWidths=[
            (TOTAL_WIDTH - 0.6 * cm) / 3, 0.3 * cm,
            (TOTAL_WIDTH - 0.6 * cm) / 3, 0.3 * cm,
            (TOTAL_WIDTH - 0.6 * cm) / 3,
        ]
    )
    row.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return row


# ================= LETTERHEAD BANNER (canvas, full-bleed) =================
def _draw_letterhead(canvas, title_text, shop=None):
    """Paints the teal header band + gold rule edge-to-edge (true page
    bleed), with the eyebrow/title text, shop details, and Scalancer
    logo/wordmark drawn directly on top. This runs before the frame's
    flowables are laid out, so it sits underneath everything else."""
    canvas.saveState()

    band_top = PAGE_H
    band_bottom = PAGE_H - BAND_HEIGHT

    canvas.setFillColor(TEAL)
    canvas.rect(0, band_bottom, PAGE_W, BAND_HEIGHT, stroke=0, fill=1)

    canvas.setFillColor(GOLD)
    canvas.rect(0, band_bottom - RULE_HEIGHT, PAGE_W, RULE_HEIGHT, stroke=0, fill=1)

    # Eyebrow + title, left-aligned with the body content below.
    canvas.setFillColor(colors.HexColor("#DDEEEE"))
    canvas.setFont("DejaVu-Bold", 9)
    canvas.drawString(LEFT_MARGIN, band_top - 1.0 * cm, "EXPOS")

    canvas.setFillColor(colors.white)
    canvas.setFont("DejaVu-Bold", 19)
    canvas.drawString(LEFT_MARGIN, band_top - 1.9 * cm, title_text)

    # Shop identity — name + address/phone/GSTIN — sits under the title,
    # inside the remaining band height.
    max_width = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN - 3.6 * cm

    def _truncate(text, font, size):
        original = text
        while text and canvas.stringWidth(text, font, size) > max_width:
            text = text[:-1]
        if text != original:
            text = text.rstrip() + "…"
        return text

    if shop:
        shop_name = (shop.get("name") or "").strip()
        if shop_name:
            canvas.setFillColor(colors.white)
            canvas.setFont("DejaVu-Bold", 10.5)
            canvas.drawString(LEFT_MARGIN, band_top - 2.45 * cm, _truncate(shop_name, "DejaVu-Bold", 10.5))

        detail_parts = []
        if shop.get("address"):
            detail_parts.append(str(shop["address"]).strip())
        if shop.get("phone"):
            detail_parts.append(str(shop["phone"]).strip())
        if shop.get("gstin"):
            detail_parts.append(f"GSTIN: {shop['gstin']}")
        detail_line = "  •  ".join(p for p in detail_parts if p)

        if detail_line:
            canvas.setFillColor(colors.HexColor("#BFE0D8"))
            canvas.setFont("DejaVu", 7.5)
            canvas.drawString(LEFT_MARGIN, band_top - 2.85 * cm, _truncate(detail_line, "DejaVu", 7.5))

    # Logo + wordmark, right-aligned.
    if os.path.exists(LOGO_PATH):
        logo_w = logo_h = 1.3 * cm
        group_w = 3.2 * cm
        group_right = PAGE_W - RIGHT_MARGIN
        logo_x = group_right - group_w / 2 - logo_w / 2
        logo_y = band_bottom + BAND_HEIGHT * 0.42

        canvas.drawImage(
            LOGO_PATH, logo_x, logo_y, width=logo_w, height=logo_h,
            preserveAspectRatio=True, mask="auto"
        )

        canvas.setFillColor(colors.white)
        canvas.setFont("DejaVu-Bold", 9)
        text = "SCALANCER"
        text_w = canvas.stringWidth(text, "DejaVu-Bold", 9)
        canvas.drawString(group_right - group_w / 2 - text_w / 2, logo_y - 0.4 * cm, text)

    canvas.restoreState()


# ================= FOOTER (canvas, drawn on every page) =================
FOOTER_LOGO_SIZE = 0.55 * cm
FOOTER_BOTTOM_PADDING = 0.55 * cm  # clear air below the tagline, above the true page edge
FOOTER_GAP_RULE_TO_LOGO = 0.5 * cm
FOOTER_GAP_LOGO_TO_BRAND = 0.34 * cm
FOOTER_GAP_BRAND_TO_TAGLINE = 0.4 * cm


def _draw_footer(canvas, doc):
    """Paints the hairline rule + logo + brand/tagline at the bottom of the
    current page. Runs once per page (as an onPage callback), so it repeats
    on every page instead of appearing only after the last flowable.

    Built bottom-up from a fixed padding above the true page edge, so the
    stack is always centered and evenly spaced regardless of margin size."""
    canvas.saveState()

    center_x = PAGE_W / 2

    tagline_y = FOOTER_BOTTOM_PADDING
    canvas.setFillColor(MUTED_LIGHT)
    canvas.setFont("DejaVu", 7.5)
    canvas.drawCentredString(center_x, tagline_y, "Built with care by Scalancer, the makers of ExPOS.")

    brand_y = tagline_y + FOOTER_GAP_BRAND_TO_TAGLINE
    canvas.setFont("DejaVu-Bold", 8)
    canvas.drawCentredString(center_x, brand_y, "SCALANCER")

    logo_bottom = brand_y + FOOTER_GAP_LOGO_TO_BRAND
    if os.path.exists(LOGO_PATH):
        canvas.drawImage(
            LOGO_PATH,
            center_x - FOOTER_LOGO_SIZE / 2, logo_bottom,
            width=FOOTER_LOGO_SIZE, height=FOOTER_LOGO_SIZE,
            preserveAspectRatio=True, mask="auto"
        )
        rule_y = logo_bottom + FOOTER_LOGO_SIZE + FOOTER_GAP_RULE_TO_LOGO
    else:
        rule_y = logo_bottom + FOOTER_GAP_RULE_TO_LOGO

    canvas.setStrokeColor(HAIRLINE)
    canvas.setLineWidth(0.5)
    canvas.line(LEFT_MARGIN, rule_y, PAGE_W - RIGHT_MARGIN, rule_y)

    canvas.restoreState()


# ================= MAIN =================
def generate_report_pdf(file_path, summary, daily, monthly, products, peak, report_type="today",
                         period_start=None, period_end=None, shop=None):

    # ================= CURRENCY =================
    # I7 FIX: the app sends its display symbol directly — use it as-is
    # (trimmed, sanity-capped) instead of substring-matching $/€ only.
    currency_symbol = "₹"

    if shop and shop.get("currency"):
        cur = str(shop.get("currency")).strip()
        if 0 < len(cur) <= 4:
            currency_symbol = cur

    # Switch to the smaller-top-margin template starting from page 2 — the
    # header band is only drawn (full-bleed) on page 1.
    elements = [NextPageTemplate("Later")]

    period_pill = Table(
        [[Paragraph(
            f"<font color='#085041' size='8'><b>{report_type_label(report_type).upper()}</b></font>",
            ParagraphStyle("PeriodPill", fontName="DejaVu-Bold", alignment=TA_CENTER)
        )]],
        colWidths=[3.4 * cm]
    )
    period_pill.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TEAL_TINT),
        ("ROUNDEDCORNERS", [10, 10, 10, 10]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    range_label = period_range_label(period_start, period_end) or local_now().strftime("%B %d, %Y")
    date_p = Paragraph(
        f"<font color='#6B6455' size='10'>{range_label}</font>",
        ParagraphStyle("DateStyle", fontName="DejaVu")
    )
    currency_pill = Table(
        [[Paragraph(
            f"<font color='#8A6526' size='8'><b>{currency_symbol} {currency_symbol == '₹' and 'INR' or ''}</b></font>".strip(),
            ParagraphStyle("CurrencyPill", fontName="DejaVu-Bold", alignment=TA_CENTER)
        )]],
        colWidths=[2.2 * cm]
    )
    currency_pill.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GOLD_TINT),
        ("ROUNDEDCORNERS", [10, 10, 10, 10]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    date_row = Table(
        [[period_pill, date_p, currency_pill]],
        colWidths=[3.4 * cm, TOTAL_WIDTH - 3.4 * cm - 2.2 * cm, 2.2 * cm]
    )
    date_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "LEFT"),
        ("ALIGN", (-1, 0), (-1, 0), "RIGHT"),
        ("LEFTPADDING", (1, 0), (1, 0), 10),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(date_row)
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(
        f"<font color='#9A8F79' size='7.5'>Generated on {local_now().strftime('%B %d, %Y, %I:%M %p')}</font>",
        ParagraphStyle("GeneratedOn", fontName="DejaVu", leftIndent=0)
    ))
    elements.append(Spacer(1, 14))

    # ================= HERO KPI CARDS =================
    elements.append(kpi_cards(
        currency_symbol, summary["revenue"], summary["bills"], summary["average"]
    ))
    elements.append(Spacer(1, 22))

    # ================= DAILY =================
    data = [["DATE", f"REVENUE ({currency_symbol})", "BILLS"]]
    for d in daily:
        data.append([d["date"], f"{d['revenue']:.2f}", d["bills"]])

    elements.append(KeepTogether([
        section_label("Daily Sales", TEAL),
        Spacer(1, 8),
        hairline_table(data, TEAL),
    ]))
    elements.append(Spacer(1, 20))

    # ================= MONTHLY =================
    data = [["MONTH", f"REVENUE ({currency_symbol})", "BILLS"]]
    for m in monthly:
        data.append([m["month"], f"{m['revenue']:.2f}", m["bills"]])

    elements.append(KeepTogether([
        section_label("Monthly Sales", GOLD),
        Spacer(1, 8),
        hairline_table(data, GOLD),
    ]))
    elements.append(Spacer(1, 20))

    # ================= PRODUCTS =================
    data = [["PRODUCT", "QUANTITY", f"REVENUE ({currency_symbol})"]]
    for p in products:
        data.append([p["product"], p["quantity"], f"{p['revenue']:.2f}"])

    elements.append(KeepTogether([
        section_label("Top Products", GOLD),
        Spacer(1, 8),
        hairline_table(data, GOLD),
    ]))
    elements.append(Spacer(1, 20))

    # ================= PEAK =================
    data = [["HOUR", "BILLS", f"REVENUE ({currency_symbol})"]]
    for p in peak:
        data.append([f"{p['hour']}:00", p["bills"], f"{p['revenue']:.2f}"])

    elements.append(KeepTogether([
        section_label("Peak Hours", TEAL),
        Spacer(1, 8),
        hairline_table(data, TEAL),
    ]))

    # ================= BUILD =================
    # Two page templates: "First" reserves room at the top for the
    # full-bleed teal header band (drawn straight on the canvas, not as a
    # flowable, so its background reaches the true page edges); "Later"
    # uses a normal small top margin since the header only appears once.
    # Both draw the same thin card-style border around their content frame.
    frame_first = Frame(
        LEFT_MARGIN, BOTTOM_MARGIN,
        PAGE_W - LEFT_MARGIN - RIGHT_MARGIN,
        PAGE_H - TOP_MARGIN_FIRST - BOTTOM_MARGIN,
        id="first", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0
    )
    frame_later = Frame(
        LEFT_MARGIN, BOTTOM_MARGIN,
        PAGE_W - LEFT_MARGIN - RIGHT_MARGIN,
        PAGE_H - TOP_MARGIN_LATER - BOTTOM_MARGIN,
        id="later", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0
    )

    def _on_first_page(canvas, doc):
        _draw_letterhead(canvas, "Analytics report", shop=shop)
        _draw_footer(canvas, doc)

    def _on_later_pages(canvas, doc):
        _draw_footer(canvas, doc)

    pdf = BaseDocTemplate(
        file_path,
        pagesize=A4,
        pageTemplates=[
            PageTemplate(id="First", frames=[frame_first], onPage=_on_first_page),
            PageTemplate(id="Later", frames=[frame_later], onPage=_on_later_pages),
        ],
    )

    pdf.build(elements)

    return file_path
