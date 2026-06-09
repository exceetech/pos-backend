import os
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from app.models.inventory import Inventory
from app.models.bill import Bill
from app.models.bill_items import BillItem
from app.models.purchase import Purchase
from app.models.credit import CreditAccount, CreditTransaction
from app.models.scrap import Scrap
from app.models.purchase_return import PurchaseReturn
from app.models.credit_note import CreditNote
from app.models.customer import Customer

def generate_structured_insights(db: Session, shop_id: int):
    insights = []
    now = datetime.now()
    today_dt = now
    thirty_days_ago = now - timedelta(days=30)
    fourteen_days_ago = now - timedelta(days=14)
    seven_days_ago = now - timedelta(days=7)
    forty_eight_hours_ago = now - timedelta(hours=48)
    sixty_days_ago = now - timedelta(days=60)

    # ---------------------------------------------------------
    # EXISTING 5 INSIGHTS
    # ---------------------------------------------------------
    # 1. Imminent Stockout (Fire)
    low_stock_count = db.query(func.count(Inventory.product_id)).filter(
        Inventory.shop_id == shop_id,
        Inventory.current_stock > 0,
        Inventory.current_stock <= 5,
        Inventory.is_active == True
    ).scalar() or 0

    if low_stock_count > 0:
        insights.append({
            "type": "fire",
            "title": "Low Stock Warning",
            "description": f"You have {low_stock_count} products running critically low on stock (under 5 units). Restock soon.",
            "actionText": "Review Inventory",
            "actionType": "VIEW_INVENTORY"
        })

    # 2. High-Risk Credit Defaulters (Fire)
    stale_credit_accounts = db.query(CreditAccount).filter(
        CreditAccount.shop_id == shop_id,
        CreditAccount.due_amount > 0,
        CreditAccount.is_active == True
    ).all()
    
    defaulters_count = 0
    trapped_credit = 0.0
    for acc in stale_credit_accounts:
        last_tx = db.query(CreditTransaction).filter(
            CreditTransaction.account_id == acc.id
        ).order_by(CreditTransaction.created_at.desc()).first()
        
        if not last_tx or (last_tx.created_at and last_tx.created_at.replace(tzinfo=None) < thirty_days_ago):
            defaulters_count += 1
            trapped_credit += acc.due_amount

    if defaulters_count > 0:
        insights.append({
            "type": "fire",
            "title": "Stale Debt Alert",
            "description": f"₹{trapped_credit:,.2f} is pending from {defaulters_count} customers who haven't made a payment in >30 days.",
            "actionText": "Send Reminders",
            "actionType": "VIEW_CREDIT"
        })

    # 3. Dead Stock Capital Trap (Leak)
    recent_sales = db.query(BillItem.shop_product_id).join(Bill, BillItem.bill_id == Bill.id).filter(
        Bill.shop_id == shop_id,
        Bill.created_at >= thirty_days_ago,
        Bill.active == True
    ).distinct().all()
    recently_sold_ids = [r[0] for r in recent_sales]

    dead_stock_query = db.query(Inventory).filter(
        Inventory.shop_id == shop_id,
        Inventory.current_stock > 0,
        Inventory.is_active == True
    )
    if recently_sold_ids:
        dead_stock_query = dead_stock_query.filter(Inventory.product_id.not_in(recently_sold_ids))
    
    dead_stock_items = dead_stock_query.all()
    dead_capital = sum([(item.current_stock * item.average_cost) for item in dead_stock_items])
    dead_count = len(dead_stock_items)

    if dead_count > 0 and dead_capital > 100:
        insights.append({
            "type": "leak",
            "title": "Dead Stock Capital",
            "description": f"You have ₹{dead_capital:,.2f} tied up in {dead_count} products that haven't sold a single unit in 30 days.",
            "actionText": "Clearance Plan",
            "actionType": "VIEW_INVENTORY"
        })

    # 4. Cash Flow Trap (Leak)
    cash_purchases = db.query(func.sum(Purchase.invoice_value)).filter(
        Purchase.shop_id == shop_id,
        Purchase.is_credit == 0,
        Purchase.created_at >= seven_days_ago
    ).scalar() or 0.0

    cash_sales = db.query(func.sum(Bill.total_amount)).filter(
        Bill.shop_id == shop_id,
        Bill.payment_method.not_in(["Credit", "Udhar"]),
        Bill.active == True,
        Bill.created_at >= seven_days_ago
    ).scalar() or 0.0

    if cash_purchases > cash_sales and cash_purchases > 1000:
        deficit = cash_purchases - cash_sales
        insights.append({
            "type": "leak",
            "title": "Cash Flow Deficit",
            "description": f"Warning: You paid ₹{cash_purchases:,.2f} to suppliers but only received ₹{cash_sales:,.2f} in cash sales this week.",
            "actionText": "Analyze Bills",
            "actionType": "VIEW_DASHBOARD"
        })

    # 5. Discount Drain (Leak)
    recent_discounts = db.query(func.sum(Bill.discount)).filter(
        Bill.shop_id == shop_id,
        Bill.created_at >= seven_days_ago,
        Bill.active == True
    ).scalar() or 0.0

    if recent_discounts > 500:
        insights.append({
            "type": "leak",
            "title": "Discount Drain",
            "description": f"You gave ₹{recent_discounts:,.2f} in counter discounts this week. Ensure these are converting into repeat business.",
            "actionText": "Check Bills",
            "actionType": "VIEW_BILLS"
        })

    # ---------------------------------------------------------
    # NEW 15 INSIGHTS (Phase 2)
    # ---------------------------------------------------------

    # Helper for profit calculation
    calc_profit = (BillItem.subtotal - (Inventory.average_cost * BillItem.quantity))

    # 6. High-Margin Star (Gold)
    best_profit_item = db.query(
        BillItem.product_name, 
        func.sum(calc_profit).label("total_profit")
    ).join(Bill, Bill.id == BillItem.bill_id).join(
        Inventory, Inventory.product_id == BillItem.shop_product_id
    ).filter(
        Bill.shop_id == shop_id, 
        Bill.created_at >= thirty_days_ago, 
        Bill.active == True
    ).group_by(BillItem.product_name).order_by(func.sum(calc_profit).desc()).first()

    if best_profit_item and best_profit_item.total_profit and best_profit_item.total_profit > 500:
        insights.append({
            "type": "gold",
            "title": "High-Margin Star",
            "description": f"'{best_profit_item.product_name}' brought in ₹{best_profit_item.total_profit:,.2f} profit this month! Keep it well stocked.",
            "actionText": "Check Stock",
            "actionType": "VIEW_INVENTORY"
        })

    # 7. Loss-Making Products (Leak)
    loss_making = db.query(
        BillItem.product_name, 
        func.sum(calc_profit).label("total_profit"), 
        func.sum(BillItem.quantity).label("total_qty")
    ).join(Bill, Bill.id == BillItem.bill_id).join(
        Inventory, Inventory.product_id == BillItem.shop_product_id
    ).filter(
        Bill.shop_id == shop_id, 
        Bill.created_at >= thirty_days_ago, 
        Bill.active == True
    ).group_by(BillItem.product_name).having(func.sum(calc_profit) < -100).first()

    if loss_making and loss_making.total_profit is not None:
        insights.append({
            "type": "leak",
            "title": "Loss-Making Product Alert",
            "description": f"You sold {loss_making.total_qty} units of '{loss_making.product_name}' at a total loss of ₹{abs(loss_making.total_profit):,.2f}.",
            "actionText": "Check Bills",
            "actionType": "VIEW_BILLS"
        })

    # 8. Peak Sales Hour (Gold)
    peak_hour = db.query(
        extract('hour', Bill.created_at).label("hour"), 
        func.count(Bill.id).label("count")
    ).filter(
        Bill.shop_id == shop_id, 
        Bill.created_at >= thirty_days_ago, 
        Bill.active == True
    ).group_by(extract('hour', Bill.created_at)).order_by(func.count(Bill.id).desc()).first()

    if peak_hour and peak_hour.count > 10:
        hr = int(peak_hour.hour)
        ampm = "AM" if hr < 12 else "PM"
        hr_formatted = hr if hr <= 12 else hr - 12
        if hr_formatted == 0: hr_formatted = 12
        insights.append({
            "type": "gold",
            "title": "Peak Sales Hour",
            "description": f"Your busiest time is {hr_formatted} {ampm}. Ensure your best staff are available and stock is arranged.",
            "actionText": "Great",
            "actionType": "NONE"
        })

    # 9. AOV Drop (Leak)
    last_7_aov = db.query(func.avg(Bill.total_amount)).filter(
        Bill.shop_id == shop_id, Bill.created_at >= seven_days_ago, Bill.active == True
    ).scalar() or 0.0
    
    prev_7_aov = db.query(func.avg(Bill.total_amount)).filter(
        Bill.shop_id == shop_id, Bill.created_at >= fourteen_days_ago, Bill.created_at < seven_days_ago, Bill.active == True
    ).scalar() or 0.0

    if prev_7_aov > 500 and last_7_aov < prev_7_aov:
        drop_pct = ((prev_7_aov - last_7_aov) / prev_7_aov) * 100
        if drop_pct > 15:
            insights.append({
                "type": "leak",
                "title": "Order Value Dropping",
                "description": f"Average order value dropped {drop_pct:.1f}% this week (₹{prev_7_aov:.0f} → ₹{last_7_aov:.0f}). Try up-selling items.",
                "actionText": "Analyze Bills",
                "actionType": "VIEW_BILLS"
            })

    # 10. Overstock Capital (Leak)
    recent_60_sales = db.query(BillItem.shop_product_id).join(Bill, BillItem.bill_id == Bill.id).filter(
        Bill.shop_id == shop_id,
        Bill.created_at >= sixty_days_ago,
        Bill.active == True
    ).distinct().all()
    recent_60_ids = [r[0] for r in recent_60_sales]

    overstock_query = db.query(Inventory).filter(
        Inventory.shop_id == shop_id,
        Inventory.current_stock > 100,
        Inventory.is_active == True
    )
    if recent_60_ids:
        overstock_query = overstock_query.filter(Inventory.product_id.not_in(recent_60_ids))
    
    overstock_items = overstock_query.all()
    over_capital = sum([(item.current_stock * item.average_cost) for item in overstock_items])
    if over_capital > 2000:
        insights.append({
            "type": "leak",
            "title": "Overstock Capital Trap",
            "description": f"You have ₹{over_capital:,.2f} trapped in {len(overstock_items)} items with >100 stock but 0 sales in 60 days.",
            "actionText": "View Stock",
            "actionType": "VIEW_INVENTORY"
        })

    # 11. Wastage / Scrap Alert (Leak)
    scrap_value = db.query(func.sum(Scrap.invoice_value)).filter(
        Scrap.shop_id == shop_id, 
        Scrap.created_at >= thirty_days_ago
    ).scalar() or 0.0

    if scrap_value > 500:
        insights.append({
            "type": "leak",
            "title": "High Wastage Alert",
            "description": f"₹{scrap_value:,.2f} worth of goods were scrapped this month. Keep a close eye on expiry dates.",
            "actionText": "Review Scrap",
            "actionType": "VIEW_SCRAP"
        })

    # 12. Velocity Stockout Risk (Fire)
    top_fast_items = db.query(
        BillItem.shop_product_id,
        BillItem.product_name,
        func.sum(BillItem.quantity).label("qty_sold_7_days")
    ).join(Bill, Bill.id == BillItem.bill_id).filter(
        Bill.shop_id == shop_id,
        Bill.created_at >= seven_days_ago,
        Bill.active == True
    ).group_by(BillItem.shop_product_id, BillItem.product_name).order_by(func.sum(BillItem.quantity).desc()).limit(10).all()

    for item in top_fast_items:
        daily_velocity = item.qty_sold_7_days / 7.0
        if daily_velocity > 1:
            inv = db.query(Inventory).filter(Inventory.product_id == item.shop_product_id).first()
            if inv and 0 < inv.current_stock < (daily_velocity * 3):
                insights.append({
                    "type": "fire",
                    "title": "Velocity Stockout Risk",
                    "description": f"'{item.product_name}' is selling fast! Your remaining {inv.current_stock} stock will run out in < 3 days.",
                    "actionText": "Restock Now",
                    "actionType": "VIEW_INVENTORY"
                })
                break 

    # 13. Supplier Return Rate (Leak)
    return_val = db.query(func.sum(PurchaseReturn.invoice_value)).filter(
        PurchaseReturn.shop_id == shop_id, 
        PurchaseReturn.created_at >= thirty_days_ago
    ).scalar() or 0.0

    if return_val > 2000:
        insights.append({
            "type": "leak",
            "title": "High Supplier Returns",
            "description": f"You returned ₹{return_val:,.2f} worth of goods to suppliers this month. Check supplier quality.",
            "actionText": "View Returns",
            "actionType": "VIEW_RETURNS"
        })

    # 14. Credit Recovery Success (Gold)
    recovered = db.query(func.sum(CreditTransaction.amount)).filter(
        CreditTransaction.shop_id == shop_id, 
        CreditTransaction.type == 'PAY', 
        CreditTransaction.created_at >= seven_days_ago
    ).scalar() or 0.0

    given = db.query(func.sum(CreditTransaction.amount)).filter(
        CreditTransaction.shop_id == shop_id, 
        CreditTransaction.type == 'ADD', 
        CreditTransaction.created_at >= seven_days_ago
    ).scalar() or 0.0

    if recovered > given and recovered > 1000:
        insights.append({
            "type": "gold",
            "title": "Credit Recovery Success",
            "description": f"Excellent! You recovered ₹{recovered:,.2f} in pending Udhar this week, outpacing new credit given.",
            "actionText": "View Accounts",
            "actionType": "VIEW_CREDIT"
        })

    # 15. Highest Value Order (Gold)
    highest_bill = db.query(Bill).filter(
        Bill.shop_id == shop_id, 
        Bill.created_at >= thirty_days_ago, 
        Bill.active == True
    ).order_by(Bill.total_amount.desc()).first()

    if highest_bill and highest_bill.total_amount > 2000:
        insights.append({
            "type": "gold",
            "title": "Highest Value Order",
            "description": f"You captured a single order worth ₹{highest_bill.total_amount:,.2f} this month! Keep driving large ticket sales.",
            "actionText": "View Sales",
            "actionType": "VIEW_BILLS"
        })

    # 16. High Customer Return Rate (Leak)
    cust_return = db.query(func.sum(CreditNote.total_amount)).filter(
        CreditNote.shop_id == shop_id, 
        CreditNote.created_at >= thirty_days_ago
    ).scalar() or 0.0

    if cust_return > 1000:
        insights.append({
            "type": "leak",
            "title": "High Customer Returns",
            "description": f"You issued ₹{cust_return:,.2f} in credit notes (returns) this month. Track reasons for returns.",
            "actionText": "View Dashboard",
            "actionType": "VIEW_DASHBOARD"
        })

    # 17. Unpaid Supplier Bills (Fire)
    unpaid_purchases = db.query(func.sum(Purchase.invoice_value)).filter(
        Purchase.shop_id == shop_id, 
        Purchase.is_credit == 1, 
        Purchase.created_at < thirty_days_ago
    ).scalar() or 0.0

    if unpaid_purchases > 5000:
        insights.append({
            "type": "fire",
            "title": "Unpaid Supplier Bills",
            "description": f"You have ₹{unpaid_purchases:,.2f} in credit purchases older than 30 days pending payment.",
            "actionText": "View Purchases",
            "actionType": "VIEW_PURCHASES"
        })

    # 18. Zero-Sales Day Alert (Fire)
    sales_48h = db.query(func.count(Bill.id)).filter(
        Bill.shop_id == shop_id, 
        Bill.created_at >= forty_eight_hours_ago, 
        Bill.active == True
    ).scalar() or 0

    if sales_48h == 0:
        insights.append({
            "type": "fire",
            "title": "Zero Sales Warning",
            "description": "No sales recorded in the last 48 hours. Ensure your system is synced and staff are billing correctly.",
            "actionText": "Check Sync",
            "actionType": "VIEW_DASHBOARD"
        })

    # 19. GST Liability Estimate (Leak/Alert)
    sales_gst = db.query(func.sum(Bill.gst)).filter(
        Bill.shop_id == shop_id, 
        Bill.created_at >= thirty_days_ago, 
        Bill.active == True
    ).scalar() or 0.0
    
    purchase_gst = db.query(func.sum(Purchase.cgst_amount + Purchase.sgst_amount + Purchase.igst_amount)).filter(
        Purchase.shop_id == shop_id, 
        Purchase.created_at >= thirty_days_ago
    ).scalar() or 0.0

    est_liability = sales_gst - purchase_gst
    if est_liability > 1000:
        insights.append({
            "type": "leak",
            "title": "Est. GST Liability",
            "description": f"Your estimated GST liability for the last 30 days is ₹{est_liability:,.2f}. Keep funds prepared.",
            "actionText": "View Reports",
            "actionType": "VIEW_DASHBOARD"
        })

    # 20. Margin Erosion (Leak)
    total_profit_7 = db.query(
        func.sum(calc_profit)
    ).join(Bill, Bill.id == BillItem.bill_id).join(
        Inventory, Inventory.product_id == BillItem.shop_product_id
    ).filter(
        Bill.shop_id == shop_id, 
        Bill.created_at >= seven_days_ago, 
        Bill.active == True
    ).scalar() or 0.0
    
    total_sales_7 = db.query(func.sum(Bill.total_amount)).filter(
        Bill.shop_id == shop_id, 
        Bill.created_at >= seven_days_ago, 
        Bill.active == True
    ).scalar() or 0.0

    if total_sales_7 > 5000 and total_profit_7 > 0:
        margin_pct = (total_profit_7 / total_sales_7) * 100
        if margin_pct < 10:
            insights.append({
                "type": "leak",
                "title": "Margin Erosion",
                "description": f"Your profit margin dropped to {margin_pct:.1f}% this week. Check if discounts or costs are too high.",
                "actionText": "View Bills",
                "actionType": "VIEW_BILLS"
            })


    # 21. AOV Trend Tracker
    sales_last_7 = db.query(func.sum(Bill.total_amount), func.count(Bill.id)).filter(
        Bill.shop_id == shop_id, Bill.created_at >= seven_days_ago, Bill.active == True
    ).first()
    fourteen_days_ago = today_dt - timedelta(days=14)
    sales_prev_7 = db.query(func.sum(Bill.total_amount), func.count(Bill.id)).filter(
        Bill.shop_id == shop_id, Bill.created_at >= fourteen_days_ago, Bill.created_at < seven_days_ago, Bill.active == True
    ).first()
    
    if sales_last_7 and sales_prev_7 and sales_prev_7[1] and sales_last_7[1] and sales_prev_7[1] > 0 and sales_last_7[1] > 0:
        aov_last = sales_last_7[0] / sales_last_7[1]
        aov_prev = sales_prev_7[0] / sales_prev_7[1]
        if aov_last < aov_prev * 0.8:
            insights.append({
                "type": "leak",
                "title": "AOV Drop Warning",
                "description": f"Average order value dropped from ₹{aov_prev:.1f} to ₹{aov_last:.1f} this week. Encourage upselling.",
                "actionText": "View Bills",
                "actionType": "VIEW_BILLS"
            })
        elif aov_last > aov_prev * 1.2:
            insights.append({
                "type": "gold",
                "title": "AOV Growth",
                "description": f"Great job! Average order value grew from ₹{aov_prev:.1f} to ₹{aov_last:.1f} this week.",
                "actionText": "View Bills",
                "actionType": "VIEW_BILLS"
            })

    # 23. Single-Supplier Vulnerability
    total_purchase_30 = db.query(func.sum(Purchase.invoice_value)).filter(
        Purchase.shop_id == shop_id, Purchase.created_at >= thirty_days_ago
    ).scalar() or 0.0
    if total_purchase_30 > 10000:
        top_supplier = db.query(func.sum(Purchase.invoice_value)).filter(
            Purchase.shop_id == shop_id, Purchase.created_at >= thirty_days_ago
        ).group_by(Purchase.supplier_name).order_by(func.sum(Purchase.invoice_value).desc()).limit(1).first()
        
        if top_supplier and top_supplier[0] > (total_purchase_30 * 0.8):
            insights.append({
                "type": "fire",
                "title": "Supplier Dependency Risk",
                "description": f"Over 80% of your recent purchases rely on a single supplier. Consider finding backups.",
                "actionText": "View Purchases",
                "actionType": "VIEW_PURCHASES"
            })

    # 24. Weekend vs. Weekday Shift
    all_bills_30 = db.query(Bill.total_amount, Bill.created_at).filter(
        Bill.shop_id == shop_id, Bill.created_at >= thirty_days_ago, Bill.active == True
    ).all()
    weekend_rev = sum(b.total_amount for b in all_bills_30 if b.created_at.weekday() >= 5)
    total_rev = sum(b.total_amount for b in all_bills_30)
    if total_rev > 10000 and weekend_rev > (total_rev * 0.5):
        insights.append({
            "type": "gold",
            "title": "Weekend Sales Boom",
            "description": f"More than 50% of your revenue (₹{weekend_rev:,.2f}) comes on weekends. Prepare stock accordingly.",
            "actionText": "View Inventory",
            "actionType": "VIEW_INVENTORY"
        })

    # 25. Low-Margin Volume Drivers
    vol_drivers = db.query(
        BillItem.product_name,
        func.sum(BillItem.quantity).label("tot_qty"),
        func.sum(calc_profit).label("tot_profit")
    ).join(Bill, Bill.id == BillItem.bill_id).join(
        Inventory, Inventory.product_id == BillItem.shop_product_id
    ).filter(
        Bill.shop_id == shop_id, Bill.created_at >= thirty_days_ago, Bill.active == True
    ).group_by(BillItem.shop_product_id, BillItem.product_name).having(
        func.sum(BillItem.quantity) > 50,
        func.sum(calc_profit) / func.sum(BillItem.quantity * BillItem.price) < 0.05
    ).limit(1).first()

    if vol_drivers:
        insights.append({
            "type": "leak",
            "title": "Low Margin Volume Driver",
            "description": f"'{vol_drivers.product_name}' sells fast but yields <5% profit margin. Consider raising prices slightly.",
            "actionText": "View Inventory",
            "actionType": "VIEW_INVENTORY"
        })

    # 26. High-Margin Slow Movers
    slow_movers = db.query(
        BillItem.product_name,
        func.sum(BillItem.quantity).label("tot_qty"),
        func.sum(calc_profit).label("tot_profit")
    ).join(Bill, Bill.id == BillItem.bill_id).join(
        Inventory, Inventory.product_id == BillItem.shop_product_id
    ).filter(
        Bill.shop_id == shop_id, Bill.created_at >= thirty_days_ago, Bill.active == True
    ).group_by(BillItem.shop_product_id, BillItem.product_name).having(
        func.sum(BillItem.quantity) > 0,
        func.sum(BillItem.quantity) < 5,
        func.sum(calc_profit) / func.sum(BillItem.quantity * BillItem.price) > 0.4
    ).limit(1).first()

    if slow_movers:
        insights.append({
            "type": "gold",
            "title": "High Margin Slow Mover",
            "description": f"'{slow_movers.product_name}' yields >40% profit but rarely sells. Promote this item more!",
            "actionText": "View Inventory",
            "actionType": "VIEW_INVENTORY"
        })

    # 27. Credit vs Cash Ratio
    total_revenue_30 = db.query(func.sum(Bill.total_amount)).filter(
        Bill.shop_id == shop_id, Bill.created_at >= thirty_days_ago, Bill.active == True
    ).scalar() or 0.0
    credit_rev = db.query(func.sum(Bill.total_amount)).filter(
        Bill.shop_id == shop_id, Bill.created_at >= thirty_days_ago, Bill.active == True, Bill.payment_method == "credit"
    ).scalar() or 0.0
    if total_revenue_30 > 5000 and credit_rev > (total_revenue_30 * 0.6):
        insights.append({
            "type": "leak",
            "title": "Cash Flow Alert",
            "description": f"Over 60% of your monthly sales (₹{credit_rev:,.2f}) are on Udhar (Credit). Monitor your cash flow.",
            "actionText": "View Accounts",
            "actionType": "VIEW_CREDIT"
        })

    # 28. Dead Credit Accounts
    ninety_days_ago = today_dt - timedelta(days=90)
    # Check updated_at property if exists, else created_at
    dead_accs = db.query(func.count(CreditAccount.id)).filter(
        CreditAccount.shop_id == shop_id, 
        CreditAccount.due_amount > 500,
        CreditAccount.created_at < ninety_days_ago
    ).scalar() or 0
    if dead_accs > 0:
        insights.append({
            "type": "leak",
            "title": "Dead Credit Accounts",
            "description": f"You have {dead_accs} credit accounts with pending balances untouched for over 90 days.",
            "actionText": "View Accounts",
            "actionType": "VIEW_CREDIT"
        })

    # 29. Sudden Sales Drop
    if sales_last_7 and sales_prev_7 and sales_prev_7[0] and sales_last_7[0] and sales_prev_7[0] > 5000:
        if sales_last_7[0] < sales_prev_7[0] * 0.7:
            insights.append({
                "type": "fire",
                "title": "Sudden Sales Drop",
                "description": f"Sales dropped by over 30% this week (₹{sales_last_7[0]:,.2f} vs ₹{sales_prev_7[0]:,.2f}). Investigate immediately.",
                "actionText": "View Bills",
                "actionType": "VIEW_BILLS"
            })

    # 30. Serial Returner
    serial_returner = db.query(
        CreditNote.customer_name,
        func.count(CreditNote.id)
    ).filter(
        CreditNote.shop_id == shop_id, CreditNote.created_at >= thirty_days_ago
    ).group_by(CreditNote.customer_name).having(func.count(CreditNote.id) >= 3).limit(1).first()
    
    if serial_returner and serial_returner[0]:
        insights.append({
            "type": "leak",
            "title": "Serial Returner Detected",
            "description": f"Customer '{serial_returner[0]}' has returned items 3 or more times this month.",
            "actionText": "View Returns",
            "actionType": "VIEW_RETURNS"
        })

    # 31. ITC Accumulation vs Output Tax (GST)
    if sales_gst > 0 and purchase_gst > (sales_gst * 1.5):
        insights.append({
            "type": "gold",
            "title": "ITC Accumulation",
            "description": f"Your Input Tax Credit (₹{purchase_gst:,.2f}) far exceeds Output Tax (₹{sales_gst:,.2f}). You can claim a refund.",
            "actionText": "View Reports",
            "actionType": "VIEW_DASHBOARD"
        })

    # 32. Discount Drain
    discount_drain = db.query(func.sum(Bill.discount)).filter(
        Bill.shop_id == shop_id, Bill.created_at >= seven_days_ago, Bill.active == True
    ).scalar() or 0.0
    if total_profit_7 > 0 and discount_drain > (total_profit_7 * 0.15):
        insights.append({
            "type": "leak",
            "title": "Discount Drain",
            "description": f"You gave ₹{discount_drain:,.2f} in counter discounts this week. This wiped out >15% of your total profit.",
            "actionText": "View Bills",
            "actionType": "VIEW_BILLS"
        })

    # 33. Stale Purchase Batches
    from app.models.purchase_batch import PurchaseBatch
    stale_batches = db.query(func.count(PurchaseBatch.id)).filter(
        PurchaseBatch.shop_id == shop_id,
        PurchaseBatch.quantity_remaining > 0,
        PurchaseBatch.created_at < sixty_days_ago
    ).scalar() or 0
    if stale_batches > 0:
        insights.append({
            "type": "leak",
            "title": "Stale Purchase Batches",
            "description": f"You have {stale_batches} purchase batches older than 60 days that still have unsold stock.",
            "actionText": "View Inventory",
            "actionType": "VIEW_INVENTORY"
        })

    # 34. Category-Wise Growth Indicator
    # Since category might be on ShopProduct, let's skip for safe query, or join ShopProduct.
    from app.models.shop_products import ShopProduct
    top_cat = db.query(
        ShopProduct.category,
        func.sum(BillItem.subtotal)
    ).join(BillItem, BillItem.shop_product_id == ShopProduct.id).join(
        Bill, Bill.id == BillItem.bill_id
    ).filter(
        Bill.shop_id == shop_id, Bill.created_at >= thirty_days_ago, Bill.active == True, ShopProduct.category != ""
    ).group_by(ShopProduct.category).order_by(func.sum(BillItem.subtotal).desc()).limit(1).first()
    
    if top_cat and top_cat[0] and top_cat[1] > 2000:
        insights.append({
            "type": "gold",
            "title": "Category Growth",
            "description": f"The '{top_cat[0]}' category is driving major revenue (₹{top_cat[1]:,.2f}) this month. Expand this section.",
            "actionText": "View Inventory",
            "actionType": "VIEW_INVENTORY"
        })

    # 35. Pre-GST vs Post-GST Stock Mix
    non_gst_stock = db.query(func.count(ShopProduct.id)).filter(
        ShopProduct.shop_id == shop_id, ShopProduct.hsn_code == None, ShopProduct.is_active == True
    ).scalar() or 0
    total_stock = db.query(func.count(ShopProduct.id)).filter(
        ShopProduct.shop_id == shop_id, ShopProduct.is_active == True
    ).scalar() or 0
    if total_stock > 100 and (non_gst_stock / total_stock) > 0.3:
        insights.append({
            "type": "leak",
            "title": "Missing HSN Codes",
            "description": f"Over 30% of your active products are missing HSN codes, affecting accurate GST filing.",
            "actionText": "Update Products",
            "actionType": "VIEW_INVENTORY"
        })

    # 36. Fastest Recovering Credit Customers
    fastest_recovery = db.query(
        CreditAccount.name,
        func.sum(CreditTransaction.amount)
    ).join(CreditAccount, CreditAccount.id == CreditTransaction.account_id).filter(
        CreditTransaction.shop_id == shop_id, CreditTransaction.type == 'PAY', CreditTransaction.created_at >= thirty_days_ago
    ).group_by(CreditAccount.name).order_by(func.sum(CreditTransaction.amount).desc()).limit(1).first()
    if fastest_recovery and fastest_recovery[1] > 2000:
        insights.append({
            "type": "gold",
            "title": "Top Credit Payer",
            "description": f"Customer '{fastest_recovery[0]}' made the highest credit payments (₹{fastest_recovery[1]:,.2f}) this month. Appreciate their promptness.",
            "actionText": "View Accounts",
            "actionType": "VIEW_CREDIT"
        })

    # 37. Best Day to Restock (Lowest Sales Day)
    # Use python mapping
    day_counts = [0]*7
    for b in all_bills_30:
        day_counts[b.created_at.weekday()] += 1
    if total_rev > 5000:
        lowest_day_idx = day_counts.index(min(day_counts))
        days_str = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        insights.append({
            "type": "gold",
            "title": "Best Day to Restock",
            "description": f"Historically, {days_str[lowest_day_idx]} is your quietest day. Use this time to restock and clean.",
            "actionText": "View Purchases",
            "actionType": "VIEW_PURCHASES"
        })

    # 38. Dormant Products Waking Up
    # Look for items sold today that hadn't sold in previous 30 days
    sold_today = set(item.shop_product_id for item in db.query(BillItem.shop_product_id).join(Bill).filter(
        Bill.shop_id == shop_id, Bill.created_at >= today_dt - timedelta(days=1), Bill.active == True
    ).all())
    sold_prev = set(item.shop_product_id for item in db.query(BillItem.shop_product_id).join(Bill).filter(
        Bill.shop_id == shop_id, Bill.created_at >= thirty_days_ago, Bill.created_at < today_dt - timedelta(days=1), Bill.active == True
    ).all())
    woken_up = sold_today - sold_prev
    if woken_up and len(woken_up) > 0:
        woken_product = db.query(ShopProduct).filter(ShopProduct.id == list(woken_up)[0]).first()
        if woken_product:
            insights.append({
                "type": "gold",
                "title": "Dormant Product Waking Up",
                "description": f"'{woken_product.variant_name}' suddenly sold today after 30 days of zero sales.",
                "actionText": "View Inventory",
                "actionType": "VIEW_INVENTORY"
            })

    # 39. Most Discounted Categories
    most_discounted = db.query(
        ShopProduct.category,
        func.sum(Bill.discount)
    ).join(BillItem, BillItem.shop_product_id == ShopProduct.id).join(
        Bill, Bill.id == BillItem.bill_id
    ).filter(
        Bill.shop_id == shop_id, Bill.created_at >= thirty_days_ago, Bill.active == True, ShopProduct.category != ""
    ).group_by(ShopProduct.category).order_by(func.sum(Bill.discount).desc()).limit(1).first()
    
    if most_discounted and most_discounted[0] and most_discounted[1] > 500:
        insights.append({
            "type": "leak",
            "title": "Most Discounted Category",
            "description": f"The '{most_discounted[0]}' category received the most discounts (₹{most_discounted[1]:,.2f}) this month. Check if pricing is too high.",
            "actionText": "View Inventory",
            "actionType": "VIEW_INVENTORY"
        })

    # 40. Supplier Return Frequency
    freq_supplier_return = db.query(
        PurchaseReturn.supplier_name,
        func.count(PurchaseReturn.id)
    ).filter(
        PurchaseReturn.shop_id == shop_id, PurchaseReturn.created_at >= thirty_days_ago
    ).group_by(PurchaseReturn.supplier_name).having(func.count(PurchaseReturn.id) >= 2).limit(1).first()
    if freq_supplier_return:
        insights.append({
            "type": "leak",
            "title": "High Supplier Return Frequency",
            "description": f"You returned items to '{freq_supplier_return[0]}' 2 or more times this month. Quality might be dropping.",
            "actionText": "View Returns",
            "actionType": "VIEW_RETURNS"
        })

    # 42. Peak Return Days
    all_returns_30 = db.query(CreditNote.created_at).filter(
        CreditNote.shop_id == shop_id, CreditNote.created_at >= thirty_days_ago
    ).all()
    if len(all_returns_30) > 5:
        rday_counts = [0]*7
        for r in all_returns_30:
            rday_counts[r[0].weekday()] += 1
        peak_rday_idx = rday_counts.index(max(rday_counts))
        insights.append({
            "type": "leak",
            "title": "Peak Return Day",
            "description": f"Historically, {days_str[peak_rday_idx]} has the highest number of customer returns.",
            "actionText": "View Dashboard",
            "actionType": "VIEW_DASHBOARD"
        })

    # 43. Cash Collection Velocity
    # Estimate based on credit account total udhar vs total payments
    udhar_total = db.query(func.sum(CreditAccount.due_amount)).filter(CreditAccount.shop_id == shop_id).scalar() or 0.0
    if udhar_total > 5000 and recovered > (udhar_total * 0.1):
        insights.append({
            "type": "gold",
            "title": "High Cash Collection Velocity",
            "description": f"You collected >10% of your total outstanding Udhar this week. Great liquidity flow!",
            "actionText": "View Accounts",
            "actionType": "VIEW_CREDIT"
        })

    # 44. First-Time Buyer Conversion (Estimated)
    # Customers with exactly 1 bill
    new_buyers = db.query(func.count(Customer.id)).filter(
        Customer.shop_id == shop_id, Customer.created_at >= seven_days_ago
    ).scalar() or 0
    if new_buyers > 5:
        insights.append({
            "type": "gold",
            "title": "New Customer Conversion",
            "description": f"You acquired {new_buyers} new registered customers this week. Focus on retaining them.",
            "actionText": "View Bills",
            "actionType": "VIEW_BILLS"
        })

    # 45. Unsold Products Tracking
    unsold_products = db.query(func.count(ShopProduct.id)).filter(
        ShopProduct.shop_id == shop_id, ShopProduct.is_active == True, ShopProduct.is_purchased == False
    ).scalar() or 0
    if unsold_products > 10:
        insights.append({
            "type": "leak",
            "title": "Unsold / Zero Purchase Products",
            "description": f"You have {unsold_products} active products in your catalog that have never been purchased or sold.",
            "actionText": "View Inventory",
            "actionType": "VIEW_INVENTORY"
        })

    # 46. Seasonal Product Alert
    # Just identifying products that sold > 20 qty this week
    if top_fast_items and len(top_fast_items) > 0 and top_fast_items[0].qty_sold_7_days > 50:
        insights.append({
            "type": "gold",
            "title": "High Demand Surge",
            "description": f"'{top_fast_items[0].product_name}' is experiencing a massive demand surge ({top_fast_items[0].qty_sold_7_days} sold this week).",
            "actionText": "View Inventory",
            "actionType": "VIEW_INVENTORY"
        })

    # 47. Supplier Payment Cycle Deficit
    # Comparing payment terms...
    insights.append({
        "type": "fire",
        "title": "Credit Payment Deficit",
        "description": f"Your pending supplier credit (₹{unpaid_purchases:,.2f}) is aging. Delaying payments might impact supplier relations.",
        "actionText": "View Purchases",
        "actionType": "VIEW_PURCHASES"
    })

    # 48. Micro-Transaction Dominance
    micro_bills = db.query(func.count(Bill.id)).filter(
        Bill.shop_id == shop_id, Bill.created_at >= seven_days_ago, Bill.active == True, Bill.total_amount < 50
    ).scalar() or 0
    total_bills_7 = db.query(func.count(Bill.id)).filter(
        Bill.shop_id == shop_id, Bill.created_at >= seven_days_ago, Bill.active == True
    ).scalar() or 0
    if total_bills_7 > 50 and (micro_bills / total_bills_7) > 0.5:
        insights.append({
            "type": "leak",
            "title": "Micro-Transaction Dominance",
            "description": f"Over 50% of your recent bills are under ₹50. Transaction costs and counter time might outweigh margins.",
            "actionText": "View Bills",
            "actionType": "VIEW_BILLS"
        })

    # 49. Invoice Value Clustering
    if total_bills_7 > 20:
        avg_val = total_sales_7 / total_bills_7
        insights.append({
            "type": "gold",
            "title": "Invoice Value Cluster",
            "description": f"Your average invoice value this week centers around ₹{avg_val:,.2f}. Try bumping this with cross-selling.",
            "actionText": "View Bills",
            "actionType": "VIEW_BILLS"
        })

    # 50. Inventory Turnover Ratio (Estimated)
    total_stock_qty = db.query(func.sum(Inventory.current_stock)).filter(Inventory.shop_id == shop_id).scalar() or 0.0
    total_sold_qty = db.query(func.sum(BillItem.quantity)).join(Bill).filter(
        Bill.shop_id == shop_id, Bill.created_at >= thirty_days_ago, Bill.active == True
    ).scalar() or 0.0
    if total_stock_qty > 0 and (total_sold_qty / total_stock_qty) < 0.1:
        insights.append({
            "type": "leak",
            "title": "Low Inventory Turnover",
            "description": f"You only sold {(total_sold_qty / total_stock_qty) * 100:.1f}% of your total physical stock this month. Optimize ordering.",
            "actionText": "View Inventory",
            "actionType": "VIEW_INVENTORY"
        })

    # ---------------------------------------------------------
    # SORT AND RETURN TOP 3
    # Priority: Fire -> Leak -> Gold
    # ---------------------------------------------------------
    insights.sort(key=lambda x: {"fire": 0, "leak": 1, "gold": 2}.get(x["type"], 3))
    return insights[:3]
