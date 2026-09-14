from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.database import get_db
from app.models.models import Asset, SensorReading, RiskScore, Prediction, Recommendation, Incident
from typing import Optional
from datetime import datetime, timedelta
import math

router = APIRouter()


@router.get("/summary")
def get_dashboard_summary(db: Session = Depends(get_db)):
    """Main dashboard KPI summary."""
    total_assets = db.query(Asset).count()

    # Latest risk scores
    subq = (
        db.query(RiskScore.asset_id, func.max(RiskScore.calculated_at).label("latest"))
        .group_by(RiskScore.asset_id)
        .subquery()
    )
    latest_risks = (
        db.query(RiskScore)
        .join(subq, (RiskScore.asset_id == subq.c.asset_id) & (RiskScore.calculated_at == subq.c.latest))
        .all()
    )

    critical_count = sum(1 for r in latest_risks if r.risk_level == "CRITICAL")
    at_risk_count = sum(1 for r in latest_risks if r.risk_level in ("HIGH", "CRITICAL"))

    # Predicted failures in next 48h
    cutoff = datetime.utcnow() - timedelta(hours=1)
    predicted_failures = (
        db.query(Prediction)
        .filter(Prediction.failure_probability >= 0.75, Prediction.prediction_time >= cutoff)
        .count()
    )

    # Customers at risk from high-risk assets
    high_risk_ids = [r.asset_id for r in latest_risks if r.risk_level in ("HIGH", "CRITICAL")]
    customers_at_risk = (
        db.query(func.sum(Asset.customers_served))
        .filter(Asset.id.in_(high_risk_ids))
        .scalar() or 0
    )

    return {
        "total_assets": total_assets,
        "critical_assets": critical_count,
        "at_risk_assets": at_risk_count,
        "predicted_failures": predicted_failures,
        "customers_at_risk": customers_at_risk,
    }


@router.get("/risk-map")
def get_risk_map(db: Session = Depends(get_db)):
    """Return all assets with their latest risk level and coordinates for map rendering."""
    subq = (
        db.query(RiskScore.asset_id, func.max(RiskScore.calculated_at).label("latest"))
        .group_by(RiskScore.asset_id)
        .subquery()
    )
    results = (
        db.query(Asset, RiskScore)
        .join(RiskScore, Asset.id == RiskScore.asset_id)
        .join(subq, (RiskScore.asset_id == subq.c.asset_id) & (RiskScore.calculated_at == subq.c.latest))
        .all()
    )

    return [
        {
            "asset_id": a.asset_id,
            "asset_type": a.asset_type,
            "name": a.name,
            "latitude": a.latitude,
            "longitude": a.longitude,
            "risk_level": r.risk_level,
            "overall_risk_score": r.overall_risk_score,
            "failure_probability": r.failure_probability,
            "customers_served": a.customers_served,
            "district": a.district,
        }
        for a, r in results
    ]


@router.get("/top-risk")
def get_top_risk_assets(
    limit: int = 10,
    sort_by: Optional[str] = Query("composite", description="composite, risk_only, customer_only"),
    db: Session = Depends(get_db)
):
    """
    Top N unique assets ranked by Customer-Weighted Composite Priority Index (CPI).
    Balances physical equipment risk (55%), population blackout vulnerability (35%),
    and critical facility security (10%) so higher-customer assets are prioritized
    without healthy assets jumping ahead.
    """
    subq_risk = (
        db.query(RiskScore.asset_id, func.max(RiskScore.id).label("latest_risk_id"))
        .group_by(RiskScore.asset_id)
        .subquery()
    )
    subq_pred = (
        db.query(Prediction.asset_id, func.max(Prediction.id).label("latest_pred_id"))
        .group_by(Prediction.asset_id)
        .subquery()
    )
    # Fetch top candidates (sample 150 unique assets for global composite re-ranking)
    results = (
        db.query(Asset, RiskScore, Prediction)
        .join(RiskScore, Asset.id == RiskScore.asset_id)
        .join(subq_risk, RiskScore.id == subq_risk.c.latest_risk_id)
        .outerjoin(subq_pred, Asset.id == subq_pred.c.asset_id)
        .outerjoin(Prediction, Prediction.id == subq_pred.c.latest_pred_id)
        .all()
    )

    seen = set()
    scored_candidates = []

    for a, r, p in results:
        if a.asset_id in seen:
            continue
        seen.add(a.asset_id)

        risk_val = float(r.overall_risk_score or 50.0)
        risk_norm = min(1.0, max(0.0, risk_val / 100.0))
        
        cust = int(a.customers_served or 15000)
        # Logarithmic population scaling: log10(max(100, C)) / 5.301 (200k saturation)
        cust_norm = min(1.0, math.log10(max(100, cust)) / 5.301)
        
        fac = int(a.critical_facilities or 2)
        fac_norm = min(1.0, fac / 8.0)

        # Composite Priority Index (CPI):
        # 55% Physical Failure Risk + 35% Customer Impact + 10% Critical Infrastructure
        cpi = (0.55 * risk_norm + 0.35 * cust_norm + 0.10 * fac_norm) * 100.0
        cpi = round(cpi, 1)

        scored_candidates.append({
            "asset": a,
            "risk": r,
            "pred": p,
            "cpi": cpi,
            "cust_norm": round(cust_norm, 3),
        })

    # Sort based on requested criteria (default: composite)
    if sort_by == "risk_only":
        scored_candidates.sort(key=lambda x: float(x["risk"].overall_risk_score or 0.0), reverse=True)
    elif sort_by == "customer_only":
        scored_candidates.sort(key=lambda x: int(x["asset"].customers_served or 0), reverse=True)
    else:
        scored_candidates.sort(key=lambda x: x["cpi"], reverse=True)

    top_items = scored_candidates[:limit]

    return [
        {
            "rank": idx + 1,
            "asset_id": item["asset"].asset_id,
            "asset_name": item["asset"].name,
            "asset_type": item["asset"].asset_type,
            "risk_level": item["risk"].risk_level,
            "overall_risk_score": item["risk"].overall_risk_score,
            "composite_priority_score": item["cpi"],
            "failure_probability": item["risk"].failure_probability,
            "impact_score": item["risk"].impact_score,
            "health_score": item["pred"].health_score if item["pred"] else 50.0,
            "customers_served": item["asset"].customers_served,
            "critical_facilities": item["asset"].critical_facilities,
            "district": item["asset"].district,
            "ranking_model": "Composite Risk + Customer Weighted (55/35/10)",
        }
        for idx, item in enumerate(top_items)
    ]




@router.get("/recent-alerts")
def get_recent_alerts(limit: int = 10, db: Session = Depends(get_db)):
    """Recent incidents and high-risk predictions as alerts."""
    recent_incidents = (
        db.query(Incident, Asset)
        .join(Asset, Incident.asset_id == Asset.id)
        .order_by(Incident.started_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "type": "incident",
            "asset_id": a.asset_id,
            "asset_type": a.asset_type,
            "severity": i.severity,
            "fault_type": i.fault_type,
            "customers_affected": i.customers_affected,
            "started_at": i.started_at,
        }
        for i, a in recent_incidents
    ]


@router.get("/recommendations")
def get_top_recommendations(limit: int = 5, db: Session = Depends(get_db)):
    """Top open recommendations ordered by priority."""
    results = (
        db.query(Recommendation, Asset)
        .join(Asset, Recommendation.asset_id == Asset.id)
        .filter(Recommendation.status == "open")
        .order_by(Recommendation.priority.asc())
        .limit(limit)
        .all()
    )

    return [
        {
            "asset_id": a.asset_id,
            "asset_type": a.asset_type,
            "priority": r.priority,
            "action_type": r.action_type,
            "description": r.description,
            "urgency": r.urgency,
        }
        for r, a in results
    ]
