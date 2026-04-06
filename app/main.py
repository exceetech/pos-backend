from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base

from app.models import *

from app.routes import auth_routes
from app.routes import product_routes
from app.routes import bill_routes
from app.routes import report_routes
from app.routes import shop_routes
from app.routes import billing_settings_routes
from app.routes.security_routes import router as security_router
from app.routes import admin_routes
from app.routes.analytics_routes import router as analytics_router
from app.routes import subscription_routes as subscription


from apscheduler.schedulers.background import BackgroundScheduler
from app.database import SessionLocal
from app.services.expiry_service import check_subscriptions
from app.routes import credit_routes as credit



app = FastAPI(
    title="POS Backend",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables
Base.metadata.create_all(bind=engine)

# Routers
app.include_router(auth_routes.router)
app.include_router(product_routes.router)
app.include_router(bill_routes.router)
app.include_router(report_routes.router)
app.include_router(shop_routes.router)
app.include_router(billing_settings_routes.router)
app.include_router(security_router)
app.include_router(admin_routes.router)
app.include_router(analytics_router)
app.include_router(subscription.router)
app.include_router(credit.router)


# Root
@app.get("/")
def root():
    return {"message": "POS Backend Running Successfully!"}


scheduler = BackgroundScheduler()
def run_expiry_check():
    db = SessionLocal()
    check_subscriptions(db)
    db.close()


# ⏰ Runs every 24 hours
scheduler.add_job(run_expiry_check, "interval", hours=24)
scheduler.start()


#READY FOR AWS HOSTING