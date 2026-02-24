from fastapi import FastAPI
from app.database import engine, Base
from app.models import *
from app.routes import auth_routes
from app.routes import product_routes

# Create FastAPI app
app = FastAPI(
    title="POS Backend",
    version="1.0.0"
)

# Create ALL database tables
Base.metadata.create_all(bind=engine)

# Include routes
app.include_router(auth_routes.router)
app.include_router(product_routes.router)

# Root test route
@app.get("/")
def root():
    return {"message": "POS Backend Running Successfully!"}