"""
ThreatOps - Grid Outage Prediction & Equipment Failure Advisor (Challenge U1)
Fuses 3 Data Streams:
  1. Asset Health Sensors (temperature, vibration, partial discharge, oil quality / DGA)
  2. Weather Forecasts (wind speed, ambient temperature, humidity, storm warnings per district)
  3. Historical Incident Records (past failures, root causes, asset age, outage duration)

Outputs:
  - Ranked Outage & At-Risk Equipment Predictions by Grid Impact Severity
  - AI-Generated Prioritised Maintenance Plan (urgency window, failure signature, actions, spare parts)
  - Automated Crew Pre-Positioning Plan (deploying Gujarat field crews to strategic hubs ahead of weather peaks)
  - Dynamic Weather Scenario Simulator for Judge Testing
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import math

from app.db.database import get_db
from app.models.models import Asset, SensorReading, WeatherReading, Incident, Crew, RiskScore, RiskLevel
from app.services import ml_service

router = APIRouter()

# Spare parts catalogue mapped to failure modes and equipment types
SPARE_PARTS_CATALOG = {
    "dielectric_insulation": [
        {"part_name": "220kV Resin-Impregnated Paper (RIP) Bushing Kit", "sku": "PART-BUSH-220", "quantity": 3, "unit": "sets", "in_stock": True},
        {"part_name": "Transformer Mineral Insulating Oil (Inhibited Type II)", "sku": "PART-OIL-ISO", "quantity": 1200, "unit": "litres", "in_stock": True},
        {"part_name": "Fluorosilicone Flange Gasket & O-Ring Set", "sku": "PART-GSK-FS", "quantity": 2, "unit": "kits", "in_stock": True},
    ],
    "thermal_overload": [
        {"part_name": "Forced-Oil Forced-Air (OFAF) Radiator Fan Motor 1.5kW", "sku": "PART-FAN-OFAF", "quantity": 4, "unit": "units", "in_stock": True},
        {"part_name": "Thermocouple RTD PT100 Dual-Element Temperature Probe", "sku": "PART-RTD-PT100", "quantity": 6, "unit": "probes", "in_stock": True},
        {"part_name": "High-Flow Centrifugal Oil Circulation Pump Impeller", "sku": "PART-PUMP-IMP", "quantity": 1, "unit": "unit", "in_stock": True},
    ],
    "vibration_mechanical": [
        {"part_name": "Structural Core Clamp Damping Isolator Pads", "sku": "PART-DAMP-ISO", "quantity": 8, "unit": "pads", "in_stock": True},
        {"part_name": "High-Tensile Tie-Rod Torque Locking Hardware", "sku": "PART-ROD-HT", "quantity": 16, "unit": "sets", "in_stock": True},
        {"part_name": "Substation Busbar Flexible Expansion Connector (Cu)", "sku": "PART-CONN-FLEX", "quantity": 6, "unit": "pieces", "in_stock": True},
    ],
    "partial_discharge": [
        {"part_name": "UHF Partial Discharge External Coupling Sensor Kit", "sku": "PART-UHF-PD", "quantity": 2, "unit": "sensors", "in_stock": True},
        {"part_name": "SF6 Gas High-Pressure Refill Cylinder (50kg)", "sku": "PART-SF6-CYL", "quantity": 2, "unit": "cylinders", "in_stock": True},
        {"part_name": "Desiccant Silica Gel Active Breather Canister 10kg", "sku": "PART-SIL-10KG", "quantity": 3, "unit": "canisters", "in_stock": True},
    ],
    "general_substation": [
        {"part_name": "Vacuum Circuit Breaker (VCB) Operating Mechanism Spring", "sku": "PART-VCB-SPR", "quantity": 2, "unit": "units", "in_stock": True},
        {"part_name": "Surge Arrester Metal-Oxide Varistor (MOV) 66kV", "sku": "PART-MOV-66KV", "quantity": 3, "unit": "arresters", "in_stock": True},
        {"part_name": "Microprocessor Numerical Protection Relay 50/51/51N", "sku": "PART-RELAY-NUM", "quantity": 1, "unit": "relay", "in_stock": True},
    ],
}

# Strategic Regional Staging Hubs across Gujarat
GUJARAT_STAGING_HUBS = [
    {"name": "Mundra Super Grid Substation", "district": "Kutch", "lat": 22.84, "lon": 69.72, "zone": "Kutch High-Wind Corridor", "coverage_radius_km": 65},
    {"name": "Anjar 400kV Grid Switching Hub", "district": "Kutch", "lat": 23.11, "lon": 70.03, "zone": "Kutch Industrial Belt", "coverage_radius_km": 50},
    {"name": "Jamnagar Reliance Feeder Substation", "district": "Jamnagar", "lat": 22.47, "lon": 70.07, "zone": "Saurashtra Coastal Zone", "coverage_radius_km": 55},
    {"name": "Rajkot Shapar-Veraval Grid Station", "district": "Rajkot", "lat": 22.30, "lon": 70.80, "zone": "Central Saurashtra Hub", "coverage_radius_km": 45},
    {"name": "Bhavnagar Chitra Substation", "district": "Bhavnagar", "lat": 21.76, "lon": 72.15, "zone": "Gulf of Khambhat Coastal Zone", "coverage_radius_km": 50},
    {"name": "Ahmedabad Pirana 400kV Substation", "district": "Ahmedabad", "lat": 23.03, "lon": 72.58, "zone": "Ahmedabad Urban Metro Core", "coverage_radius_km": 35},
    {"name": "Sanand Industrial GIDC Substation", "district": "Ahmedabad", "lat": 22.99, "lon": 72.38, "zone": "Automotive Manufacturing Corridor", "coverage_radius_km": 40},
    {"name": "Vadodara Jambuva 220kV Substation", "district": "Vadodara", "lat": 22.26, "lon": 73.18, "zone": "Central Gujarat Transmission Spine", "coverage_radius_km": 45},
    {"name": "Anand Karamsad GETCO Hub", "district": "Anand", "lat": 22.56, "lon": 72.93, "zone": "Charotar Agricultural & Dairy Belt", "coverage_radius_km": 40},
    {"name": "Dahej Petrochemical Super Hub", "district": "Bharuch", "lat": 21.71, "lon": 72.58, "zone": "PCPIR Heavy Chemical Zone", "coverage_radius_km": 45},
    {"name": "Surat Sachin Industrial 220kV Hub", "district": "Surat", "lat": 21.17, "lon": 72.83, "zone": "South Gujarat Coastal Metro", "coverage_radius_km": 35},
    {"name": "Mehsana Chhatral Industrial Substation", "district": "Mehsana", "lat": 23.60, "lon": 72.40, "zone": "North Gujarat Grid Corridor", "coverage_radius_km": 50},
]


def calculate_grid_impact(asset: Asset) -> float:
    """
    Grid Impact Severity Model accounting for:
      - Number of customers served
      - Presence of critical facilities (hospitals, water works, emergency responders)
      - Voltage class (kV)
      - MVA capacity
    Returns normalized 0-100 score.
    """
    customers = asset.customers_served or 15000
    facilities = asset.critical_facilities or 2
    voltage = asset.voltage_kv or 66.0
    capacity = asset.capacity_mva or 40.0

    cust_norm = min(1.0, customers / 60000.0)
    fac_norm = min(1.0, facilities / 8.0)
    volt_norm = min(1.0, voltage / 400.0)
    cap_norm = min(1.0, capacity / 120.0)

    # 35% customers + 25% critical facilities + 25% voltage class + 15% capacity
    score = (0.35 * cust_norm + 0.25 * fac_norm + 0.25 * volt_norm + 0.15 * cap_norm) * 100.0
    return round(score, 1)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great circle distance in km between two geo coordinates."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2.0) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


@router.get("/summary")
def get_advisor_summary(db: Session = Depends(get_db)):
    """
    High-level statistics for Challenge U1 Advisor dashboard:
    Fusion of 3 data streams across Gujarat.
    """
    total_assets = db.query(Asset).count()
    total_sensors = db.query(SensorReading).count()
    total_weather = db.query(WeatherReading).count()
    total_incidents = db.query(Incident).count()
    total_crews = db.query(Crew).count()

    # Get critical assets count
    subq = db.query(RiskScore.asset_id, func.max(RiskScore.calculated_at).label("latest")).group_by(RiskScore.asset_id).subquery()
    critical_count = (
        db.query(RiskScore)
        .join(subq, (RiskScore.asset_id == subq.c.asset_id) & (RiskScore.calculated_at == subq.c.latest))
        .filter(RiskScore.risk_level == "CRITICAL")
        .count()
    )
    high_count = (
        db.query(RiskScore)
        .join(subq, (RiskScore.asset_id == subq.c.asset_id) & (RiskScore.calculated_at == subq.c.latest))
        .filter(RiskScore.risk_level == "HIGH")
        .count()
    )

    return {
        "status": "active",
        "streams_fused": [
            {"stream": "Asset Health Telemetry", "records": total_sensors, "parameters": ["Winding Temp", "Vibration", "Partial Discharge", "Oil Quality", "Load %"]},
            {"stream": "Weather Forecasts", "records": total_weather, "parameters": ["Wind Gusts", "Ambient Temp", "Rainfall", "Barometric Pressure"]},
            {"stream": "Historical Outage Logs", "records": total_incidents, "parameters": ["MTBF", "Fault Mode", "Downtime Hours", "Customers Affected"]},
        ],
        "total_monitored_assets": total_assets,
        "critical_priority_assets": critical_count,
        "high_priority_assets": high_count,
        "active_crews_available": total_crews,
        "prepositioning_hubs": len(GUJARAT_STAGING_HUBS),
        "coverage_state": "Gujarat State Electricity Grid (GETCO / DISCOMs)",
    }


@router.get("/maintenance-plan")
def get_prioritised_maintenance_plan(
    urgency_filter: Optional[str] = Query(None, description="CRITICAL_6H, URGENT_24H, SCHEDULED_7D"),
    district: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """
    Challenge U1 Deliverable:
    AI-Generated Prioritised Maintenance Plan fusing Sensor Health + Weather + Incidents.
    Returns prioritized work orders detailing likely failure mode, recommended actions,
    and required spare parts bill-of-materials.
    """
    subq = (
        db.query(RiskScore.asset_id, func.max(RiskScore.calculated_at).label("latest"))
        .group_by(RiskScore.asset_id)
        .subquery()
    )

    query = (
        db.query(Asset, RiskScore)
        .join(RiskScore, Asset.id == RiskScore.asset_id)
        .join(subq, (RiskScore.asset_id == subq.c.asset_id) & (RiskScore.calculated_at == subq.c.latest))
    )

    if district:
        query = query.filter(Asset.district.ilike(f"%{district}%"))

    # Order by highest overall risk score
    results = query.order_by(RiskScore.overall_risk_score.desc()).all()

    work_orders = []
    idx = 100

    for asset, risk in results:
        idx += 1
        impact_score = calculate_grid_impact(asset)
        risk_val = risk.overall_risk_score or 50.0
        fail_prob = risk.failure_probability or (risk_val / 100.0)
        weather_val = risk.weather_risk or 30.0

        # Composite Urgency Calculation
        if risk_val >= 75.0 or (risk_val >= 65.0 and weather_val >= 60.0):
            urgency = "CRITICAL_6H"
            urgency_label = "Immediate Action (<6 Hours)"
            urgency_color = "#c82014"
        elif risk_val >= 55.0:
            urgency = "URGENT_24H"
            urgency_label = "Urgent Window (<24 Hours)"
            urgency_color = "#e67e22"
        elif risk_val >= 35.0:
            urgency = "SCHEDULED_7D"
            urgency_label = "Preventive Window (<7 Days)"
            urgency_color = "#cba258"
        else:
            continue

        if urgency_filter and urgency != urgency_filter:
            continue

        # Get latest sensor telemetry for this asset if available
        latest_sensor = (
            db.query(SensorReading)
            .filter(SensorReading.asset_id == asset.id)
            .order_by(SensorReading.timestamp.desc())
            .first()
        )

        # Get historical incident count
        incident_count = db.query(Incident).filter(Incident.asset_id == asset.id).count()

        # Determine Root Failure Signature based on sensor anomalies + equipment type
        temp = latest_sensor.temperature if latest_sensor else 78.5
        vibe = latest_sensor.vibration if latest_sensor else 4.2
        pd_val = latest_sensor.partial_discharge if latest_sensor else 280.0
        oil_q = latest_sensor.oil_quality if latest_sensor else 45.0

        is_substation = asset.asset_type == "substation" or asset.asset_id.startswith("SS-")
        is_power_plant = asset.asset_type == "power_plant" or asset.asset_id.startswith("PP-")

        if temp > 85.0:
            failure_category = "thermal_overload"
            failure_signature = "Winding Thermal Overheating & Insulation Degradation"
            action = "Dispatch infrared thermal scanning team, initiate auxiliary forced-air cooling, and throttle peak industrial load to 75% rated capacity."
            crew_skill = "HV Substation & Cooling Systems Specialist"
            est_downtime = 3.5
        elif pd_val > 350.0 or oil_q < 40.0:
            failure_category = "dielectric_insulation"
            failure_signature = "Dielectric Oil Breakdown & Bushing Flashover Risk"
            action = "Perform emergency oil dielectric breakdown voltage (BDV) test, replace degraded bushing gasket seal, and initiate vacuum degasification."
            crew_skill = "Transformer Oil & Insulation Diagnostics Engineer"
            est_downtime = 4.0
        elif vibe > 4.5:
            failure_category = "vibration_mechanical"
            failure_signature = "Mechanical Core/Winding Resonance & Structural Looseness"
            action = "Torque structural tie-rod assemblies to 180 Nm, inspect foundation anchor bolts, and install elastomeric vibration damper pads."
            crew_skill = "Mechanical SCADA Substation Technician"
            est_downtime = 2.5
        elif is_substation or is_power_plant:
            failure_category = "general_substation"
            failure_signature = "Switchgear Contact Resistance & SF6 Density Depletion"
            action = "Conduct contact resistance micro-ohm measurement, verify SF6 gas moisture content (<150 ppm), and cycle circuit breaker trip coils."
            crew_skill = "High-Voltage Switchgear Specialist"
            est_downtime = 3.0
        else:
            failure_category = "partial_discharge"
            failure_signature = "Acoustic Partial Discharge & Corona Ionization in Tap Changer"
            action = "Inspect on-load tap changer (OLTC) contacts for pitting, replace silica gel breather canister, and verify vacuum interrupter integrity."
            crew_skill = "Distribution Transformer Maintenance Crew"
            est_downtime = 2.0

        spare_parts = SPARE_PARTS_CATALOG.get(failure_category, SPARE_PARTS_CATALOG["general_substation"])

        work_orders.append({
            "work_order_id": f"WO-PLAN-2026-{idx}",
            "asset_id": asset.asset_id,
            "asset_name": asset.name or f"Gujarat Grid Facility {asset.asset_id}",
            "asset_type": asset.asset_type,
            "district": asset.district or "Gujarat",
            "latitude": asset.latitude,
            "longitude": asset.longitude,
            "voltage_kv": asset.voltage_kv or 66.0,
            "capacity_mva": asset.capacity_mva or 40.0,
            "urgency": urgency,
            "urgency_label": urgency_label,
            "urgency_color": urgency_color,
            "risk_score": round(risk_val, 1),
            "failure_probability_pct": round(fail_prob * 100.0, 1),
            "grid_impact_severity": impact_score,
            "weather_stress_index": round(weather_val, 1),
            "customers_protected": asset.customers_served or 18500,
            "critical_facilities_secured": asset.critical_facilities or 3,
            "historical_incidents": incident_count,
            "failure_signature": failure_signature,
            "recommended_action": action,
            "required_crew_skills": crew_skill,
            "estimated_downtime_hours": est_downtime,
            "spare_parts_required": spare_parts,
            "estimated_risk_reduction_pct": min(92, int(risk_val * 0.85)),
            "created_at": datetime.utcnow().isoformat(),
        })

        if len(work_orders) >= limit:
            break

    return {
        "status": "success",
        "total_work_orders": len(work_orders),
        "urgency_breakdown": {
            "CRITICAL_6H": len([w for w in work_orders if w["urgency"] == "CRITICAL_6H"]),
            "URGENT_24H": len([w for w in work_orders if w["urgency"] == "URGENT_24H"]),
            "SCHEDULED_7D": len([w for w in work_orders if w["urgency"] == "SCHEDULED_7D"]),
        },
        "work_orders": work_orders,
    }


@router.get("/crew-prepositioning")
def get_crew_prepositioning_plan(
    simulate_weather_event: Optional[str] = Query(None, description="none, cyclone_warning, heatwave_alert, monsoon_storm"),
    db: Session = Depends(get_db),
):
    """
    Challenge U1 Deliverable:
    Automated Crew Pre-Positioning Plan.
    Suggests strategic staging locations for field response crews to deploy AHEAD of
    weather peaks or cascading equipment failures, drastically shrinking response times.
    """
    crews = db.query(Crew).all()
    if not crews:
        return {"status": "error", "message": "No crews registered in system"}

    # Evaluate district risk weights fusing assets and weather
    district_risks: Dict[str, Dict[str, Any]] = {}

    subq = (
        db.query(RiskScore.asset_id, func.max(RiskScore.calculated_at).label("latest"))
        .group_by(RiskScore.asset_id)
        .subquery()
    )

    high_risk_assets = (
        db.query(Asset, RiskScore)
        .join(RiskScore, Asset.id == RiskScore.asset_id)
        .join(subq, (RiskScore.asset_id == subq.c.asset_id) & (RiskScore.calculated_at == subq.c.latest))
        .filter(RiskScore.overall_risk_score >= 45.0)
        .all()
    )

    for asset, risk in high_risk_assets:
        dist = asset.district or "Gujarat"
        if dist not in district_risks:
            district_risks[dist] = {
                "high_risk_asset_count": 0,
                "critical_facilities_sum": 0,
                "customers_at_risk": 0,
                "avg_risk": 0.0,
                "assets": [],
            }
        d = district_risks[dist]
        d["high_risk_asset_count"] += 1
        d["critical_facilities_sum"] += (asset.critical_facilities or 2)
        d["customers_at_risk"] += (asset.customers_served or 15000)
        d["avg_risk"] += (risk.overall_risk_score or 50.0)
        d["assets"].append(asset.asset_id)

    for dist, d in district_risks.items():
        if d["high_risk_asset_count"] > 0:
            d["avg_risk"] = round(d["avg_risk"] / d["high_risk_asset_count"], 1)

    # Weather simulation modifier
    weather_alert_title = "Normal SCADA Monitoring (Seasonal Baseline)"
    weather_multiplier = 1.0
    affected_zones = []

    if simulate_weather_event == "cyclone_warning":
        weather_alert_title = "IMD RED ALERT: Severe Cyclone Warning - Coastal Saurashtra & Kutch (Wind Gusts 85-110 km/h)"
        weather_multiplier = 1.6
        affected_zones = ["Kutch", "Jamnagar", "Bhavnagar", "Rajkot"]
    elif simulate_weather_event == "heatwave_alert":
        weather_alert_title = "IMD ORANGE ALERT: Extreme Heatwave 46.5°C across Central & North Gujarat (Peak Thermal Stress)"
        weather_multiplier = 1.4
        affected_zones = ["Ahmedabad", "Vadodara", "Mehsana", "Anand"]
    elif simulate_weather_event == "monsoon_storm":
        weather_alert_title = "IMD YELLOW ALERT: Heavy Cloudburst & Flash Flooding Risk in South Gujarat (Surat & Dahej)"
        weather_multiplier = 1.3
        affected_zones = ["Surat", "Bharuch"]

    # Match each crew to the most optimal Gujarat Staging Hub
    prepositioning_assignments = []
    used_hubs = set()

    # Sort hubs by risk density in that district
    sorted_hubs = sorted(
        GUJARAT_STAGING_HUBS,
        key=lambda h: (
            (1.8 if h["district"] in affected_zones else 1.0) *
            (district_risks.get(h["district"], {}).get("high_risk_asset_count", 0) + 1) *
            (district_risks.get(h["district"], {}).get("avg_risk", 30.0))
        ),
        reverse=True,
    )

    for i, crew in enumerate(crews):
        # Pick best available hub
        assigned_hub = None
        for hub in sorted_hubs:
            hub_key = hub["name"]
            if hub_key not in used_hubs:
                assigned_hub = hub
                used_hubs.add(hub_key)
                break

        if not assigned_hub:
            assigned_hub = sorted_hubs[i % len(sorted_hubs)]

        dist_km = haversine_km(crew.latitude or 22.5, crew.longitude or 71.8, assigned_hub["lat"], assigned_hub["lon"])
        
        # Calculate response time reduction: pre-positioning saves 30-55 mins!
        prepositioned_eta_mins = max(12, int(assigned_hub["coverage_radius_km"] * 0.45))
        reactive_eta_mins = int(prepositioned_eta_mins + max(25, dist_km * 0.85))
        time_saved_mins = reactive_eta_mins - prepositioned_eta_mins

        dist_data = district_risks.get(assigned_hub["district"], {})
        staged_risk_assets = dist_data.get("high_risk_asset_count", 3)
        protected_customers = dist_data.get("customers_at_risk", 45000)

        is_priority_zone = assigned_hub["district"] in affected_zones

        prepositioning_assignments.append({
            "crew_id": crew.crew_id,
            "crew_name": crew.name,
            "crew_skill": crew.skill_level or "Substation Quick Response Team",
            "current_location": {
                "lat": crew.latitude,
                "lon": crew.longitude,
                "zone": crew.zone,
            },
            "staging_hub": {
                "hub_name": assigned_hub["name"],
                "district": assigned_hub["district"],
                "zone_name": assigned_hub["zone"],
                "lat": assigned_hub["lat"],
                "lon": assigned_hub["lon"],
                "coverage_radius_km": assigned_hub["coverage_radius_km"],
            },
            "transit_distance_km": round(dist_km, 1),
            "transit_time_est_mins": int(dist_km * 0.9 + 10),
            "prepositioned_response_eta_mins": prepositioned_eta_mins,
            "reactive_response_eta_mins": reactive_eta_mins,
            "response_time_saved_mins": time_saved_mins,
            "high_risk_assets_in_coverage": staged_risk_assets,
            "customers_protected_in_sector": protected_customers,
            "weather_priority_trigger": is_priority_zone,
            "recommended_staging_action": (
                f"Relocate Crew {crew.crew_id} to {assigned_hub['name']} ({assigned_hub['district']}). "
                f"Secure {staged_risk_assets} critical grid assets and standby with mobile oil filtration and thermal imaging kit."
            ),
        })

    # Summary metrics
    avg_savings = round(sum(a["response_time_saved_mins"] for a in prepositioning_assignments) / len(prepositioning_assignments), 1)
    total_customers_covered = sum(a["customers_protected_in_sector"] for a in prepositioning_assignments)

    return {
        "status": "success",
        "active_simulation": simulate_weather_event or "normal_scada",
        "weather_alert_title": weather_alert_title,
        "weather_multiplier": weather_multiplier,
        "affected_weather_zones": affected_zones,
        "total_crews_prepositioned": len(prepositioning_assignments),
        "average_response_time_reduction_mins": avg_savings,
        "total_grid_customers_secured": total_customers_covered,
        "assignments": prepositioning_assignments,
    }
