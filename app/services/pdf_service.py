from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os

def generate_invoice_pdf(bill, bill_items):

    folder = "invoices"
    os.makedirs(folder, exist_ok=True)

    file_path = f"{folder}/invoice_{bill.id}.pdf"

    c = canvas.Canvas(file_path, pagesize=letter)

    y = 750
    c.drawString(50, y, f"Invoice #{bill.id}")
    y -= 30

    for item in bill_items:
        text = f"{item.product_name}  x{item.quantity}  ₹{item.price}"
        c.drawString(50, y, text)
        y -= 20

    c.drawString(50, y - 20, f"Total: ₹{bill.total_amount}")

    c.save()

    return file_path