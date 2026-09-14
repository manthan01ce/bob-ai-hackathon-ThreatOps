from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text,
    ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.db.database import Base


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AssetStatus(str, enum.Enum):
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"
    DECOMMISSIONED = "decommissioned"


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(String(50), unique=True, nullable=False, index=True)
    asset_type = Column(String(50), nullable=False)          # transformer, substation, feeder
    name = Column(String(150))
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    capacity_mva = Column(Float)
    voltage_kv = Column(Float)
    manufacturer = Column(String(100))
    installation_date = Column(DateTime)
    status = Column(SAEnum(AssetStatus), default=AssetStatus.ACTIVE)
    customers_served = Column(Integer, default=0)
    critical_facilities = Column(Integer, default=0)
    district = Column(String(100))
    state = Column(String(50), default="Gujarat")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sensor_readings = relationship("SensorReading", back_populates="asset", cascade="all, delete-orphan")
    incidents = relationship("Incident", back_populates="asset", cascade="all, delete-orphan")
    predictions = relationship("Prediction", back_populates="asset", cascade="all, delete-orphan")
    risk_scores = relationship("RiskScore", back_populates="asset", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="asset", cascade="all, delete-orphan")
    maintenance_records = relationship("MaintenanceRecord", back_populates="asset", cascade="all, delete-orphan")

    @property
    def age_years(self):
        if self.installation_date:
            return (datetime.utcnow() - self.installation_date).days // 365
        return None


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    temperature = Column(Float)           # °C — winding temperature
    oil_temperature = Column(Float)       # °C — OTI
    vibration = Column(Float)             # mm/s
    oil_quality = Column(Float)           # 0-100 quality index
    partial_discharge = Column(Float)     # pC
    load_percent = Column(Float)          # % of rated capacity
    voltage = Column(Float)               # kV
    current = Column(Float)               # A
    power_kw = Column(Float)
    power_kva = Column(Float)
    power_factor = Column(Float)
    frequency = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    asset = relationship("Asset", back_populates="sensor_readings")


class WeatherReading(Base):
    __tablename__ = "weather_readings"

    id = Column(Integer, primary_key=True, index=True)
    station_name = Column(String(150))
    district = Column(String(100))
    state = Column(String(50))
    latitude = Column(Float)
    longitude = Column(Float)
    recorded_at = Column(DateTime, nullable=False, index=True)
    avg_temp = Column(Float)
    min_temp = Column(Float)
    max_temp = Column(Float)
    wind_speed = Column(Float)
    air_pressure = Column(Float)
    rainfall = Column(Float)
    elevation = Column(Float)
    season = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    incident_type = Column(String(50))     # outage, partial_failure, maintenance
    fault_type = Column(String(100))
    severity = Column(SAEnum(RiskLevel))
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime)
    customers_affected = Column(Integer, default=0)
    root_cause = Column(Text)
    weather_condition = Column(String(100))
    voltage_at_fault = Column(Float)
    current_at_fault = Column(Float)
    power_load_mw = Column(Float)
    temperature_at_fault = Column(Float)
    wind_speed_at_fault = Column(Float)
    duration_hrs = Column(Float)
    downtime_hrs = Column(Float)
    maintenance_status = Column(String(50))
    component_health = Column(Float)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    asset = relationship("Asset", back_populates="incidents")


class MaintenanceRecord(Base):
    __tablename__ = "maintenance_records"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    maintenance_type = Column(String(100))
    performed_at = Column(DateTime)
    next_due_at = Column(DateTime)
    technician = Column(String(100))
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    asset = relationship("Asset", back_populates="maintenance_records")


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    model_version = Column(String(20), default="v1.0")
    prediction_time = Column(DateTime, default=datetime.utcnow)
    failure_probability = Column(Float)     # 0.0 – 1.0
    risk_window = Column(String(20))        # "6h", "24h", "48h", "7d"
    health_score = Column(Float)            # 0-100
    dga_hydrogen = Column(Float)
    dga_methane = Column(Float)
    dga_ethylene = Column(Float)
    dga_co = Column(Float)
    life_expectation = Column(Float)        # years remaining
    predicted_failure_type = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    asset = relationship("Asset", back_populates="predictions")


class RiskScore(Base):
    __tablename__ = "risk_scores"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    failure_probability = Column(Float)
    impact_score = Column(Float)           # 0-100 based on customers + critical facilities
    weather_risk = Column(Float)           # 0-100 based on current weather
    overall_risk_score = Column(Float)     # composite 0-100
    risk_level = Column(SAEnum(RiskLevel))
    calculated_at = Column(DateTime, default=datetime.utcnow)

    asset = relationship("Asset", back_populates="risk_scores")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    priority = Column(Integer)               # 1 = highest
    action_type = Column(String(100))        # inspect, replace, reduce_load, monitor
    description = Column(Text)
    urgency = Column(String(20))             # immediate, 6h, 24h, 7d
    status = Column(String(20), default="open")
    created_at = Column(DateTime, default=datetime.utcnow)

    asset = relationship("Asset", back_populates="recommendations")


class Crew(Base):
    __tablename__ = "crews"

    id = Column(Integer, primary_key=True, index=True)
    crew_id = Column(String(20), unique=True)
    name = Column(String(100))
    latitude = Column(Float)
    longitude = Column(Float)
    zone = Column(String(50))
    available = Column(Boolean, default=True)
    skill_level = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)


class WorkOrderRecord(Base):
    __tablename__ = "work_orders"

    id = Column(Integer, primary_key=True, index=True)
    work_order_id = Column(String(50), unique=True, index=True)
    asset_id = Column(String(50), index=True)
    asset_type = Column(String(50))
    district = Column(String(100))
    urgency = Column(String(50))
    priority = Column(String(50))
    failure_signature = Column(String(200))
    recommended_action = Column(Text)
    spare_parts_json = Column(Text)
    status = Column(String(50), default="DISPATCHED")  # DRAFT, DISPATCHED, IN_TRANSIT, ON_SITE, VERIFIED_RESTORED
    assigned_crew = Column(String(100))
    scada_interlock_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

