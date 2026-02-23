from fastapi import FastAPI
from app.database import engine
from app.models.shop import Shop
from app.routes import auth_routes

# Create FastAPI app
app = FastAPI(
    title="POS Backend",
    version="1.0.0"
)

# Create database tables
Shop.metadata.create_all(bind=engine)

# Include routes
app.include_router(auth_routes.router)

# Root test route
@app.get("/")
def root():
    return {"message": "POS Backend Running Successfully!"}