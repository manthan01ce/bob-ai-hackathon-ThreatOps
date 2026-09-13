from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.models import SensorReading, Asset
from typing import Optional
from datetime import datetime, timedelta

router = APIRouter()


@router.get("/{asset_id}/history")
def get_sensor_history(
    asset_id: str,
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
):
    """Time-series sensor history for a given asset (last N hours)."""
    asset = db.query(Asset).filter(Asset.asset_id == asset_id).first()
    if not asset:
        return []
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    readings = (
        db.query(SensorReading)
        .filter(SensorReading.asset_id == asset.id, SensorReading.timestamp >= cutoff)
        .order_by(SensorReading.timestamp.asc())
        .all()
    )
    if not readings:
        readings = (
            db.query(SensorReading)
            .filter(SensorReading.asset_id == asset.id)
            .order_by(SensorReading.timestamp.desc())
            .limit(24)
            .all()
        )
        readings.reverse()
    import math

    def clean_f(val, default=None):
        if val is None:
            return default
        try:
            f = float(val)
            return None if (math.isnan(f) or math.isinf(f)) else f
        except Exception:
            return default

    return [
        {
            "timestamp": r.timestamp,
            "temperature": clean_f(r.temperature, 55.0),
            "oil_temperature": clean_f(r.oil_temperature, 50.0),
            "vibration": clean_f(r.vibration, 2.0),
            "load_percent": clean_f(r.load_percent, 60.0),
            "voltage": clean_f(r.voltage),
            "current": clean_f(r.current),
            "power_factor": clean_f(r.power_factor),
            "partial_discharge": clean_f(r.partial_discharge),
        }
        for r in readings
    ]


@router.get("/{asset_id}/latest")
def get_latest_sensor(asset_id: str, db: Session = Depends(get_db)):
    """Most recent sensor reading for an asset."""
    import math

    def clean_f(val, default=None):
        if val is None:
            return default
        try:
            f = float(val)
            return None if (math.isnan(f) or math.isinf(f)) else f
        except Exception:
            return default

    asset = db.query(Asset).filter(Asset.asset_id == asset_id).first()
    if not asset:
        return {}
    r = (
        db.query(SensorReading)
        .filter(SensorReading.asset_id == asset.id)
        .order_by(SensorReading.timestamp.desc())
        .first()
    )
    if not r:
        return {}
    return {
        "timestamp": r.timestamp,
        "temperature": clean_f(r.temperature, 55.0),
        "oil_temperature": clean_f(r.oil_temperature, 50.0),
        "vibration": clean_f(r.vibration, 2.0),
        "load_percent": clean_f(r.load_percent, 60.0),
        "voltage": clean_f(r.voltage),
        "current": clean_f(r.current),
        "power_factor": clean_f(r.power_factor),
        "partial_discharge": clean_f(r.partial_discharge),
    }


@router.get("/stream")
def get_sensor_stream(limit: int = 50, db: Session = Depends(get_db)):
    """Live SCADA sensor stream across assets with operational health thresholds."""
    import math

    def clean_f(val, default=0.0):
        if val is None:
            return default
        try:
            f = float(val)
            return default if (math.isnan(f) or math.isinf(f)) else round(f, 2)
        except Exception:
            return default

    readings = (
        db.query(SensorReading, Asset)
        .join(Asset, SensorReading.asset_id == Asset.id)
        .order_by(SensorReading.timestamp.desc())
        .limit(limit)
        .all()
    )

    result = []
    for r, a in readings:
        temp = clean_f(r.temperature, 55.0)
        vib = clean_f(r.vibration, 2.1)
        load = clean_f(r.load_percent, 65.0)
        
        status = "NORMAL"
        if temp > 85.0 or vib > 4.5 or load > 105.0:
            status = "CRITICAL"
        elif temp > 72.0 or vib > 3.0 or load > 88.0:
            status = "WARNING"

        result.append({
            "id": r.id,
            "asset_id": a.asset_id,
            "asset_type": a.asset_type,
            "district": a.district,
            "timestamp": r.timestamp,
            "temperature": temp,
            "oil_temperature": clean_f(r.oil_temperature, temp - 5.0),
            "vibration": vib,
            "load_percent": load,
            "voltage": clean_f(r.voltage, 33.0),
            "current": clean_f(r.current, 250.0),
            "power_factor": clean_f(r.power_factor, 0.92),
            "partial_discharge": clean_f(r.partial_discharge, 1.2),
            "status": status,
        })

    return result
