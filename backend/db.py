from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import secrets

from sqlalchemy import (Column, Date, DateTime, Float, Integer, String,
                        UniqueConstraint, create_engine, inspect, text)
from sqlalchemy.orm import declarative_base, sessionmaker

IST = ZoneInfo("Asia/Kolkata")
DB_PATH = Path(__file__).resolve().parent / "gate.db"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


def now_ist():
    return datetime.now(IST)


def today_ist():
    return now_ist().date()


def make_reference():
    return secrets.token_urlsafe(12)


class Registration(Base):
    __tablename__ = "registrations"
    id = Column(Integer, primary_key=True)
    public_ref = Column(String(32), unique=True, index=True, default=make_reference)
    name = Column(String, nullable=False)
    vehicle_number = Column(String, nullable=False, index=True)
    mobile = Column(String, nullable=False)
    address = Column(String, nullable=False)
    num_visitors = Column(Integer, nullable=False)
    visit_date = Column(Date, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="REGISTERED", index=True)
    reviewed_by = Column(String(80), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: now_ist().replace(tzinfo=None))
    __table_args__ = (UniqueConstraint("vehicle_number", "visit_date", name="uq_vehicle_date"),)


class Guard(Base):
    __tablename__ = "guards"
    id = Column(Integer, primary_key=True)
    username = Column(String(80), nullable=False, unique=True, index=True)
    password_hash = Column(String(300), nullable=False)
    active = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=lambda: now_ist().replace(tzinfo=None))


class VehicleState(Base):
    __tablename__ = "vehicle_states"
    id = Column(Integer, primary_key=True)
    plate = Column(String(20), nullable=False, unique=True, index=True)
    vehicle_status = Column(String(30), nullable=False, default="OUTSIDE CAMPUS")
    updated_at = Column(DateTime, default=lambda: now_ist().replace(tzinfo=None), nullable=False)


class Scan(Base):
    __tablename__ = "scans"
    id = Column(Integer, primary_key=True)
    plate = Column(String, nullable=True)
    status = Column(String, nullable=False)
    confidence = Column(Float, nullable=True)
    visitor_name = Column(String, nullable=True)
    vehicle_type = Column(String(20), nullable=True)  # VISITOR, STAFF, COLLEGE, OTHER
    guard_username = Column(String(80), nullable=True)
    details = Column(String(300), nullable=True)
    vehicle_status = Column(String(30), nullable=True)
    scanned_at = Column(DateTime, default=lambda: now_ist().replace(tzinfo=None))


def init_db():
    """Create missing tables and add new columns to older SQLite databases safely."""
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    with engine.begin() as conn:
        reg_cols = {c["name"] for c in inspector.get_columns("registrations")}
        migrations = {
            "public_ref": "VARCHAR(32)",
            "status": "VARCHAR(20) NOT NULL DEFAULT 'REGISTERED'",
            "reviewed_by": "VARCHAR(80)",
            "reviewed_at": "DATETIME",
        }
        for name, definition in migrations.items():
            if name not in reg_cols:
                conn.execute(text(f"ALTER TABLE registrations ADD COLUMN {name} {definition}"))
        scan_cols = {c["name"] for c in inspector.get_columns("scans")}
        for name, definition in {"guard_username": "VARCHAR(80)", "details": "VARCHAR(300)", "vehicle_type": "VARCHAR(20)", "vehicle_status": "VARCHAR(30)"}.items():
            if name not in scan_cols:
                conn.execute(text(f"ALTER TABLE scans ADD COLUMN {name} {definition}"))
        # Classify historical scans for the separated vehicle logs.
        conn.execute(text("UPDATE scans SET vehicle_type = 'VISITOR' WHERE vehicle_type IS NULL AND visitor_name IS NOT NULL"))
        conn.execute(text("UPDATE scans SET vehicle_type = 'OTHER' WHERE vehicle_type IS NULL AND plate IS NOT NULL AND (details IS NULL OR details NOT LIKE 'Registered % vehicle%')"))
        conn.execute(text("UPDATE scans SET vehicle_type = 'STAFF' WHERE vehicle_type IS NULL AND details LIKE 'Registered staff vehicle%'"))
        conn.execute(text("UPDATE scans SET vehicle_type = 'COLLEGE' WHERE vehicle_type IS NULL AND details LIKE 'Registered college vehicle%'"))
        # Backfill public references on rows created by older versions.
        rows = conn.execute(text("SELECT id FROM registrations WHERE public_ref IS NULL OR public_ref = ''")).fetchall()
        for (row_id,) in rows:
            conn.execute(text("UPDATE registrations SET public_ref = :ref WHERE id = :id"), {"ref": make_reference(), "id": row_id})
        # Old versions had a guard approval workflow. Registration is now passive:
        # every saved registration is eligible for matching on its visit date.
        conn.execute(text("UPDATE registrations SET status = 'REGISTERED' WHERE status IS NULL OR status != 'REGISTERED'"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_registrations_public_ref ON registrations(public_ref)"))
