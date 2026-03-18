from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from datetime import datetime

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


pdfmetrics.registerFont(
    TTFont("DejaVu", "app/util/fonts/DejaVuSans.ttf")
)

TOTAL_WIDTH = 16 * cm


# ================= TABLE =================
def corporate_table(data):

    col_count = len(data[0])
    col_width = TOTAL_WIDTH / col_count
    col_widths = [col_width] * col_count

    table = Table(data, colWidths=col_widths)

    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.grey),

        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#2E3B4E")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),

        ("FONTNAME", (0,0), (-1,-1), "DejaVu"),

        ("ALIGN", (0,0), (0,-1), "LEFT"),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
        ("ALIGN", (0,0), (-1,0), "CENTER"),

        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))

    return table


# ================= MAIN =================
def generate_report_pdf(file_path, summary, daily, monthly, products, peak, report_type="today", shop=None):

    styles = getSampleStyleSheet()

    date_style = ParagraphStyle(
        "DateStyle",
        parent=styles["Normal"],
        alignment=0,  # 🔥 LEFT align
        fontSize=11,
        textColor=colors.black,  # 🔥 BLACK color
        spaceAfter=10,
        fontName="DejaVu"
    )

    title = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        alignment=1,
        fontSize=24,
        textColor=colors.HexColor("#2E3B4E"),
        fontName="DejaVu"
    )

    subtitle = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        alignment=1,
        fontSize=11,
        textColor=colors.grey,
        spaceAfter=15,
        fontName="DejaVu"
    )

    section = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=colors.HexColor("#1F6F8B"),
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

    # ================= HEADER =================
    elements.append(Paragraph("ExPOS Analytics Report", title))


    elements.append(Spacer(1, 10))
    elements.append(Paragraph(
    f"<b>Date:</b> {datetime.now().strftime('%B %d, %Y')}",
        date_style
    ))

    elements.append(Spacer(1, 1))

    if shop:

        elements.append(Paragraph("Shop Information", section))

        shop_data = [
            ["Shop Name", shop.get("name", "-")],
            ["Address", shop.get("address", "-")],
            ["Email", shop.get("email", "-")],
            ["Phone", shop.get("phone", "-")],
            ["GSTIN", shop.get("gstin", "-")]
        ]

        shop_table = Table(
            shop_data,
            colWidths=[5*cm, 11*cm]   # clean layout
        )

        shop_table.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.3, colors.grey),

            ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#F5F5F5")),

            ("FONTNAME", (0,0), (-1,-1), "DejaVu"),

            ("ALIGN", (0,0), (0,-1), "LEFT"),
            ("ALIGN", (1,0), (1,-1), "LEFT"),

            ("TOPPADDING", (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ]))

        elements.append(shop_table)
        elements.append(Spacer(1, 20))

    # ================= KPI =================
    kpi_data = [
        ["Revenue", "Bills", "Avg Bill"],
        [
            f"₹ {summary['revenue']:.2f}",
            summary["bills"],
            f"₹ {summary['average']:.2f}"
        ]
    ]

    kpi = corporate_table(kpi_data)
    elements.append(kpi)
    elements.append(Spacer(1, 25))

    # ================= AI INSIGHT =================
    sales_text = "Not enough data"
    sales_color = "black"

    if len(daily) >= 2:
        first = daily[0]["revenue"]
        last = daily[-1]["revenue"]

        if first > 0:
            change = ((last - first) / first) * 100

            if change > 0:
                sales_text = f"▲ Sales increased by {abs(change):.1f}%"
                sales_color = "green"
            elif change < 0:
                sales_text = f"▼ Sales dropped by {abs(change):.1f}%"
                sales_color = "red"

    # ================= INSIGHTS =================
    elements.append(Paragraph("Key Insights", section))

    if products and peak and daily:

        top_product = max(products, key=lambda x: x["quantity"])["product"]
        weak_product = min(products, key=lambda x: x["quantity"])["product"]

        peak_hour = max(peak, key=lambda x: x["revenue"])["hour"]
        slow_hour = min(peak, key=lambda x: x["revenue"])["hour"]

        text = f"""
        <font color="{sales_color}"><b>{sales_text}</b></font><br/><br/>

        <b>Top Product:</b> <font color="green">{top_product}</font><br/>
        <b>Low Performer:</b> <font color="red">{weak_product}</font><br/><br/>

        <b>Peak Hour:</b> {peak_hour}:00<br/>
        <b>Slow Hour:</b> {slow_hour}:00<br/><br/>

        <b>Recommendations:</b><br/>
        • Promote <b>{weak_product}</b><br/>
        • Increase stock of <b>{top_product}</b><br/>
        • Run offers during <b>{slow_hour}:00</b>
        """

    else:
        text = "Not enough data available."

    elements.append(Paragraph(text, paragraph))
    elements.append(Spacer(1, 25))

    # ================= DAILY =================
    elements.append(Paragraph("Daily Sales", section))

    data = [["Date","Revenue","Bills"]]
    for d in daily:
        data.append([d["date"], f"₹ {d['revenue']:.2f}", d["bills"]])

    elements.append(corporate_table(data))
    elements.append(Spacer(1, 20))

    # ================= MONTHLY =================
    elements.append(Paragraph("Monthly Sales", section))

    data = [["Month","Revenue","Bills"]]
    for m in monthly:
        data.append([m["month"], f"₹ {m['revenue']:.2f}", m["bills"]])

    elements.append(corporate_table(data))
    elements.append(Spacer(1, 20))

    # ================= PRODUCTS =================
    elements.append(Paragraph("Top Products", section))

    data = [["Product","Quantity","Revenue"]]
    for p in products:
        data.append([p["product"], p["quantity"], f"₹ {p['revenue']:.2f}"])

    elements.append(corporate_table(data))
    elements.append(Spacer(1, 20))

    # ================= PEAK =================
    elements.append(Paragraph("Peak Hours", section))

    data = [["Hour","Bills","Revenue"]]
    for p in peak:
        data.append([f"{p['hour']}:00", p["bills"], f"₹ {p['revenue']:.2f}"])

    elements.append(corporate_table(data))
    elements.append(Spacer(1, 30))

    # ================= FOOTER =================
    elements.append(Paragraph(
        "Generated by ExPOS Analytics",
        ParagraphStyle(
            "Footer",
            alignment=1,
            fontSize=9,
            textColor=colors.grey,
            fontName="DejaVu"
        )
    ))

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