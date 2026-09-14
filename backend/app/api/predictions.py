from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.database import get_db
from app.models.models import Prediction, Asset, SensorReading
from app.services.ml_service import predict_failure, get_model_info
from typing import Dict, Any, Optional
from pydantic import BaseModel

router = APIRouter()


class PredictRequest(BaseModel):
    hydrogen: Optional[float] = None
    methane: Optional[float] = None
    co: Optional[float] = None
    co2: Optional[float] = None
    ethylene: Optional[float] = None
    ethane: Optional[float] = None
    acetylene: Optional[float] = None
    power_factor: Optional[float] = None
    dielectric_rigidity: Optional[float] = None
    water_content: Optional[float] = None
    temperature: Optional[float] = None
    oil_temperature: Optional[float] = None
    vibration: Optional[float] = None
    load_percent: Optional[float] = None
    voltage: Optional[float] = None
    current: Optional[float] = None
    is_tr: Optional[bool] = None
    asset_type: Optional[str] = None
    asset_id: Optional[str] = None


@router.get("/model-info")
def model_info():
    """Returns trained XGBoost model status, accuracy metrics, and feature importances."""
    return get_model_info()


@router.post("/predict")
def run_prediction(payload: PredictRequest):
    """Run real-time XGBoost ML inference on custom telemetry input."""
    try:
        data = payload.model_dump()
        result = predict_failure(data)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/live/{asset_id}")
def get_live_prediction(asset_id: str, db: Session = Depends(get_db)):
    """
    Fetches the latest telemetry for an asset from the database and runs
    real-time XGBoost inference with unified IEC 60599 / IEC 60076-7 diagnostics.
    """
    asset = db.query(Asset).filter(Asset.asset_id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    sensor = (
        db.query(SensorReading)
        .filter(SensorReading.asset_id == asset.id)
        .order_by(SensorReading.timestamp.desc())
        .first()
    )

    pred_db = (
        db.query(Prediction)
        .filter(Prediction.asset_id == asset.id)
        .order_by(Prediction.prediction_time.desc())
        .first()
    )

    is_tr = asset.asset_type == "transformer" or str(asset.asset_id).startswith("TR-")

    telemetry = {
        "asset_id": asset.asset_id,
        "asset_name": asset.name,
        "asset_type": asset.asset_type,
        "district": asset.district,
        "is_tr": is_tr,
        "temperature": sensor.temperature if sensor else 58.0,
        "oil_temperature": sensor.oil_temperature if sensor else 52.0,
        "vibration": sensor.vibration if sensor else 2.1,
        "load_percent": sensor.load_percent if sensor else 65.0,
        "voltage": sensor.voltage if sensor else (11.0 if is_tr else 220.0),
        "current": sensor.current if sensor else 320.0,
        "power_factor": sensor.power_factor if sensor else 0.85,
        "hydrogen": pred_db.dga_hydrogen if pred_db else (12.0 if is_tr else 32.0),
        "methane": pred_db.dga_methane if pred_db else (15.0 if is_tr else 45.0),
        "co": pred_db.dga_co if pred_db else (180.0 if is_tr else 320.0),
        "ethylene": pred_db.dga_ethylene if pred_db else (6.0 if is_tr else 28.0),
        "acetylene": 0.2 if is_tr else (pred_db.dga_hydrogen * 0.1 if pred_db else 1.5),
    }

    try:
        prediction = predict_failure(telemetry)
        prediction["asset_id"] = asset.asset_id
        prediction["asset_type"] = asset.asset_type
        prediction["asset_name"] = asset.name
        prediction["district"] = asset.district
        prediction["voltage_kv"] = asset.voltage_kv
        prediction["capacity_mva"] = asset.capacity_mva
        prediction["customers_served"] = asset.customers_served
        prediction["raw_telemetry"] = telemetry
        return prediction
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-audit")
def run_batch_audit(db: Session = Depends(get_db)):
    """
    Autonomous Grid-Wide AI Health Sweep across all assets.
    Runs inference and returns high-risk assets, distribution of IEC diagnostics, and auto-generated mitigation.
    """
    # High-performance bulk audit query: avoid N+1 query loop
    # Fetch assets and their latest sensor readings with a subquery
    subq = (
        db.query(SensorReading.asset_id, func.max(SensorReading.timestamp).label("max_ts"))
        .group_by(SensorReading.asset_id)
        .subquery()
    )

    rows = (
        db.query(Asset, SensorReading)
        .outerjoin(subq, Asset.id == subq.c.asset_id)
        .outerjoin(SensorReading, (SensorReading.asset_id == Asset.id) & (SensorReading.timestamp == subq.c.max_ts))
        .limit(100)
        .all()
    )

    high_risk_list = []
    fault_summary = {}
    iec_summary = {}

    for asset, sensor in rows:
        is_tr = asset.asset_type == "transformer" or str(asset.asset_id).startswith("TR-")
        
        telemetry = {
            "asset_id": asset.asset_id,
            "is_tr": is_tr,
            "asset_type": asset.asset_type,
            "temperature": sensor.temperature if sensor else 58.0,
            "oil_temperature": sensor.oil_temperature if sensor else 52.0,
            "vibration": sensor.vibration if sensor else 2.1,
            "load_percent": sensor.load_percent if sensor else 65.0,
            "voltage": sensor.voltage if sensor else (11.0 if is_tr else 220.0),
            "current": sensor.current if sensor else 320.0,
            "power_factor": sensor.power_factor if sensor else 0.85,
        }
        
        pred = predict_failure(telemetry)
        f_mode = pred.get("predicted_fault_mode", "Normal")
        fault_summary[f_mode] = fault_summary.get(f_mode, 0) + 1

        iec_code = pred.get("iec_diagnostics", {}).get("diagnostic_code", "NORMAL")
        iec_summary[iec_code] = iec_summary.get(iec_code, 0) + 1

        if pred["failure_probability"] >= 0.70 or pred["risk_level"] in ("HIGH", "CRITICAL"):
            high_risk_list.append({
                "asset_id": asset.asset_id,
                "asset_name": asset.name,
                "asset_type": asset.asset_type,
                "district": asset.district,
                "failure_probability": pred["failure_probability"],
                "health_score": pred["health_score"],
                "predicted_fault_mode": f_mode,
                "risk_window": pred["risk_window"],
                "iec_code": iec_code,
                "recommended_action": pred["recommended_action"],
            })

    high_risk_list.sort(key=lambda x: x["failure_probability"], reverse=True)

    return {
        "status": "success",
        "total_audited": len(rows),
        "high_risk_detected": len(high_risk_list),
        "fault_distribution": fault_summary,
        "iec_distribution": iec_summary,
        "critical_assets": high_risk_list[:15],
    }


@router.get("/")
def get_predictions(limit: int = 50, db: Session = Depends(get_db)):
    results = (
        db.query(Prediction, Asset)
        .join(Asset, Prediction.asset_id == Asset.id)
        .order_by(Prediction.failure_probability.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "asset_id": a.asset_id,
            "asset_type": a.asset_type,
            "failure_probability": p.failure_probability,
            "health_score": p.health_score,
            "risk_window": p.risk_window,
            "life_expectation": p.life_expectation,
            "prediction_time": p.prediction_time,
        }
        for p, a in results
    ]


@router.get("/{asset_id}")
def get_prediction_for_asset(asset_id: str, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.asset_id == asset_id).first()
    if not asset:
        return {}
    prediction = (
        db.query(Prediction)
        .filter(Prediction.asset_id == asset.id)
        .order_by(Prediction.prediction_time.desc())
        .first()
    )
    return prediction or {}
