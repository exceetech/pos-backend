from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from datetime import datetime

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# ================= REGISTER FONT =================

pdfmetrics.registerFont(
    TTFont("DejaVu", "app/util/fonts/DejaVuSans.ttf")
)


# ================= CORPORATE TABLE =================

def corporate_table(data):

    table = Table(data, colWidths=[8*cm, 4*cm, 4*cm])

    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),

        ("FONTNAME", (0,0), (-1,0), "DejaVu"),
        ("FONTNAME", (0,1), (-1,-1), "DejaVu"),

        ("ALIGN", (1,1), (-1,-1), "RIGHT"),

        ("TOPPADDING", (0,0), (-1,0), 8),
        ("BOTTOMPADDING", (0,0), (-1,0), 8)
    ]))

    return table


# ================= PDF GENERATOR =================

def generate_report_pdf(file_path, summary, daily, monthly, products, peak):

    styles = getSampleStyleSheet()

    title = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        alignment=1,
        fontSize=22,
        fontName="DejaVu"
    )

    subtitle = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=11,
        spaceAfter=6,
        fontName="DejaVu"
    )

    section = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        spaceAfter=10,
        fontName="DejaVu"
    )

    paragraph = ParagraphStyle(
        "Paragraph",
        parent=styles["Normal"],
        fontSize=11,
        leading=16,
        fontName="DejaVu"
    )

    elements = []

    # ================= TITLE =================

    elements.append(Paragraph("Financial Sales Report", title))
    elements.append(Spacer(1, 20))

    elements.append(Paragraph("<b>Prepared by:</b> ExPOS Analytics System", subtitle))
    elements.append(Paragraph("<b>For:</b> Excee Technologies", subtitle))
    elements.append(Paragraph(
        f"<b>Date:</b> {datetime.now().strftime('%B %d, %Y')}",
        subtitle
    ))

    elements.append(Spacer(1, 25))

    # ================= EXECUTIVE SUMMARY =================

    elements.append(Paragraph("Executive Summary", section))

    text = f"""
    During this reporting period, the business generated a total revenue of
    ₹ {summary['revenue']:.2f} across {summary['bills']} completed sales transactions.
    The average bill value during this period was ₹ {summary['average']:.2f}.
    """

    elements.append(Paragraph(text, paragraph))

    elements.append(Spacer(1, 20))

    # ================= BUSINESS INSIGHTS =================

    elements.append(Paragraph("Business Insights & Recommendations", section))

    if products and peak and daily:

        top_product = max(products, key=lambda x: x["quantity"])["product"]
        weak_product = min(products, key=lambda x: x["quantity"])["product"]

        peak_hour = max(peak, key=lambda x: x["revenue"])["hour"]
        slow_hour = min(peak, key=lambda x: x["revenue"])["hour"]

        first_rev = daily[0]["revenue"]
        last_rev = daily[-1]["revenue"]

        if last_rev > first_rev:
            trend = "Sales are increasing"
        elif last_rev < first_rev:
            trend = "Sales are decreasing"
        else:
            trend = "Sales are stable"

        insight_text = f"""
        <font color="green"><b>Best Selling Product:</b> {top_product}</font><br/><br/>
        <font color="red"><b>Weak Product:</b> {weak_product}</font><br/><br/>

        <b>Peak Sales Time:</b> {peak_hour}:00<br/><br/>
        <b>Slow Sales Time:</b> {slow_hour}:00<br/><br/>

        <b>Sales Trend:</b> {trend}<br/><br/>

        <b>Recommendations:</b><br/>
        • Promote {weak_product} with discounts or combo offers.<br/>
        • Increase stock of {top_product} during peak hours.<br/>
        • Run promotional offers during slow hours.
        """

    else:
        insight_text = "Not enough data available to generate insights."

    elements.append(Paragraph(insight_text, paragraph))

    elements.append(Spacer(1, 25))

    # ================= OVERVIEW TABLE =================

    overview_table = Table([
        ["Total Revenue", f"₹ {summary['revenue']:.2f}"],
        ["Total Bills", summary["bills"]],
        ["Average Bill", f"₹ {summary['average']:.2f}"]
    ], colWidths=[8*cm, 8*cm])

    overview_table.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.5,colors.grey),
        ("ALIGN",(1,0),(1,-1),"RIGHT"),
        ("FONTNAME",(0,0),(-1,-1),"DejaVu")
    ]))

    elements.append(overview_table)

    elements.append(Spacer(1, 25))

    # ================= DAILY SALES =================

    elements.append(Paragraph("Daily Sales Analysis", section))

    data = [["Date","Revenue","Bills"]]

    for d in daily:
        data.append([
            d["date"],
            f"₹ {d['revenue']:.2f}",
            d["bills"]
        ])

    elements.append(corporate_table(data))

    elements.append(Spacer(1, 25))

    # ================= MONTHLY SALES =================

    elements.append(Paragraph("Monthly Sales Analysis", section))

    data = [["Month","Revenue","Bills"]]

    for m in monthly:
        data.append([
            m["month"],
            f"₹ {m['revenue']:.2f}",
            m["bills"]
        ])

    elements.append(corporate_table(data))

    elements.append(Spacer(1, 25))

    # ================= TOP PRODUCTS =================

    elements.append(Paragraph("Top Selling Products", section))

    data = [["Product","Quantity","Revenue"]]

    for p in products:
        data.append([
            p["product"],
            p["quantity"],
            f"₹ {p['revenue']:.2f}"
        ])

    elements.append(corporate_table(data))

    elements.append(Spacer(1, 25))

    # ================= PEAK HOURS =================

    elements.append(Paragraph("Peak Operating Hours", section))

    data = [["Hour","Bills","Revenue"]]

    for p in peak:
        data.append([
            f"{p['hour']}:00",
            p["bills"],
            f"₹ {p['revenue']:.2f}"
        ])

    elements.append(corporate_table(data))

    elements.append(Spacer(1, 40))

    # ================= FOOTER =================

    footer = Paragraph(
        "Generated by ExPOS Analytics | Excee Technologies",
        ParagraphStyle(
            "Footer",
            alignment=1,
            fontSize=9,
            textColor=colors.grey,
            fontName="DejaVu"
        )
    )

    elements.append(footer)

    pdf = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        leftMargin=2.5*cm,
        rightMargin=2.5*cm,
        topMargin=2.5*cm,
        bottomMargin=2.5*cm
    )

    pdf.build(elements)

    return file_path