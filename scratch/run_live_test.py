import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import SessionLocal
from app.models.shop import Shop

# Patch the insights service to return ALL insights, not just top 3
filepath = "/Users/adeebfarhan/Desktop/expos/pos-backend/app/services/insights_service.py"
with open(filepath, "r") as f:
    content = f.read()

content_patched = content.replace("return sorted_insights[:3]", "return sorted_insights")

with open(filepath, "w") as f:
    f.write(content_patched)

# Reload module if necessary, but we are just importing it now
from app.services.insights_service import generate_structured_insights

db = SessionLocal()

# Find the first shop
shop = db.query(Shop).first()
if not shop:
    print("No shops found in the database. Cannot run insights.")
    sys.exit(1)

shop_id = shop.id
print(f"Running insights for Shop ID: {shop_id} ({shop.shop_name})...")

try:
    insights = generate_structured_insights(db, shop_id)
    
    report = f"# AI Insights Live Database Test Report\n\n"
    report += f"**Target Shop:** {shop.shop_name} (ID: {shop_id})\n"
    report += f"**Total Insights Triggered by Live Data:** {len(insights)}\n\n"
    report += "---\n\n"
    
    if not insights:
        report += "No insights were triggered. The database might not have enough recent data (last 30-60 days) to calculate anything meaningful.\n"
    else:
        for ins in insights:
            report += f"### [{ins['type'].upper()}] {ins['title']}\n"
            report += f"> {ins['description']}\n\n"
            report += f"**Action Required:** {ins['actionText']} (`{ins['actionType']}`)\n\n"
            report += "---\n\n"
            
    with open("/Users/adeebfarhan/.gemini/antigravity/brain/bfb1db26-2cee-4b41-a28b-ad6f4807923e/artifacts/live_db_test_report.md", "w") as f:
        f.write(report)
        
    print(f"Generated report with {len(insights)} live insights.")

finally:
    # Restore the original code
    with open(filepath, "w") as f:
        f.write(content)
        
db.close()
