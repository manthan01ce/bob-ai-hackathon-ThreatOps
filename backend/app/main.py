from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import engine
from app.models import models
from app.api import assets, sensors, weather, incidents, predictions, risks, dashboard, crews, planning

# Create all tables on startup
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="PowerGrid AI API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(assets.router,      prefix="/api/assets",      tags=["Assets"])
app.include_router(sensors.router,     prefix="/api/sensors",     tags=["Sensors"])
app.include_router(weather.router,     prefix="/api/weather",     tags=["Weather"])
app.include_router(incidents.router,   prefix="/api/incidents",   tags=["Incidents"])
app.include_router(predictions.router, prefix="/api/predictions", tags=["Predictions"])
app.include_router(risks.router,       prefix="/api/risks",       tags=["Risks"])
app.include_router(dashboard.router,   prefix="/api/dashboard",   tags=["Dashboard"])
app.include_router(crews.router,       prefix="/api/crews",       tags=["Crews"])
app.include_router(planning.router,    prefix="/api/planning",    tags=["Planning"])



@app.get("/")
def health_check():
    return {"status": "ok", "message": "PowerGrid AI API is running"}
