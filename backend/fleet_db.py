"""Separate SQLite database for staff/college vehicles and their gate-entry log."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint, create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

IST = ZoneInfo("Asia/Kolkata")
DB_PATH = Path(__file__).resolve().parent / "fleet.db"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
FleetSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
FleetBase = declarative_base()


def fleet_now():
    return datetime.now(IST).replace(tzinfo=None)


class FleetVehicle(FleetBase):
    __tablename__ = "fleet_vehicles"
    id = Column(Integer, primary_key=True)
    plate = Column(String(20), nullable=False, unique=True, index=True)
    category = Column(String(20), nullable=False)  # STAFF or COLLEGE
    owner_name = Column(String(100), nullable=False)
    department = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    vehicle_status = Column(String(30), nullable=False, default="OUTSIDE CAMPUS")
    created_at = Column(DateTime, default=fleet_now, nullable=False)


class FleetVehicleLog(FleetBase):
    __tablename__ = "fleet_vehicle_logs"
    id = Column(Integer, primary_key=True)
    plate = Column(String(20), nullable=False, index=True)
    category = Column(String(20), nullable=False)  # STAFF, COLLEGE, or MANUAL
    owner_name = Column(String(100), nullable=True)
    permission = Column(String(20), nullable=False)  # REGISTERED or MANUALLY_GRANTED
    guard_username = Column(String(80), nullable=False)
    scan_confidence = Column(String(30), nullable=True)
    details = Column(Text, nullable=True)
    vehicle_status = Column(String(30), nullable=False, default="UNKNOWN")
    entered_at = Column(DateTime, default=fleet_now, nullable=False, index=True)


def init_fleet_db():
    FleetBase.metadata.create_all(engine)
    # Safe migration for fleet.db files created by earlier versions.
    inspector = inspect(engine)
    with engine.begin() as conn:
        vehicle_cols = {c["name"] for c in inspector.get_columns("fleet_vehicles")}
        if "vehicle_status" not in vehicle_cols:
            conn.execute(text("ALTER TABLE fleet_vehicles ADD COLUMN vehicle_status VARCHAR(30) NOT NULL DEFAULT 'OUTSIDE CAMPUS'"))
        log_cols = {c["name"] for c in inspector.get_columns("fleet_vehicle_logs")}
        if "vehicle_status" not in log_cols:
            conn.execute(text("ALTER TABLE fleet_vehicle_logs ADD COLUMN vehicle_status VARCHAR(30) NOT NULL DEFAULT 'UNKNOWN'"))


def vehicle_out(v):
    return {"id": v.id, "plate": v.plate, "category": v.category,
            "owner_name": v.owner_name, "department": v.department,
            "notes": v.notes, "vehicle_status": v.vehicle_status, "created_at": v.created_at.strftime("%Y-%m-%d %H:%M:%S")}


def log_out(row):
    return {"id": row.id, "plate": row.plate, "category": row.category,
            "owner_name": row.owner_name, "permission": row.permission,
            "guard_username": row.guard_username, "scan_confidence": row.scan_confidence,
            "details": row.details, "vehicle_status": row.vehicle_status, "entered_at": row.entered_at.strftime("%Y-%m-%d %H:%M:%S")}
