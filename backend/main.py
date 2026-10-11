import re
from contextlib import asynccontextmanager
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path

import cv2
import numpy as np
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError

from auth import create_session, destroy_session, get_guard, verify_password
from db import Guard, Registration, Scan, VehicleState, SessionLocal, init_db, now_ist, today_ist
from plates import edit_distance, mask_mobile, normalize_user_input
from fleet_db import (FleetSession, FleetVehicle, FleetVehicleLog, init_fleet_db,
                      vehicle_out, log_out)

STATE = {}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_fleet_db()
    from anpr import PlateReader
    print("Loading EasyOCR model (first run downloads model weights)...")
    STATE["reader"] = PlateReader()
    print(f"EasyOCR ready (gpu={STATE['reader'].gpu})")
    yield


app = FastAPI(title="Campus Gate ANPR", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


class RegistrationIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    vehicle_number: str = Field(min_length=6, max_length=20)
    mobile: str = Field(min_length=10, max_length=15)
    address: str = Field(min_length=3, max_length=300)
    num_visitors: int = Field(ge=1, le=10)
    visit_date: date

    @field_validator("name", "address")
    @classmethod
    def strip_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("This field is required")
        return value

    @field_validator("vehicle_number")
    @classmethod
    def valid_plate(cls, value):
        plate = normalize_user_input(value)
        if not plate:
            raise ValueError("Invalid Indian plate; expected format like TN37AB1234")
        return plate

    @field_validator("mobile")
    @classmethod
    def valid_mobile(cls, value):
        value = re.sub(r"[\s-]", "", value)
        if value.startswith("+91"):
            value = value[3:]
        if not re.fullmatch(r"\d{10}", value):
            raise ValueError("Mobile must be 10 digits")
        return value

    @field_validator("visit_date")
    @classmethod
    def valid_date(cls, value):
        if value < today_ist():
            raise ValueError("Visit date cannot be in the past")
        return value


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class FleetVehicleIn(BaseModel):
    plate: str = Field(min_length=6, max_length=20)
    category: str
    owner_name: str = Field(min_length=2, max_length=100)
    department: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("plate")
    @classmethod
    def valid_fleet_plate(cls, value):
        plate = normalize_user_input(value)
        if not plate:
            raise ValueError("Invalid number plate; expected format like TN37AB1234")
        return plate

    @field_validator("category")
    @classmethod
    def valid_category(cls, value):
        value = value.strip().upper()
        if value not in {"STAFF", "COLLEGE"}:
            raise ValueError("Category must be STAFF or COLLEGE")
        return value

    @field_validator("owner_name")
    @classmethod
    def clean_owner(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Owner/vehicle name is required")
        return value


class ManualDecisionIn(BaseModel):
    plate: str = Field(min_length=1, max_length=20)
    permission_granted: bool
    confidence: float | None = None
    details: str | None = Field(default=None, max_length=500)

    @field_validator("plate")
    @classmethod
    def clean_decision_plate(cls, value):
        value = normalize_user_input(value)
        if not value:
            raise ValueError("A valid detected plate is required")
        return value


def registration_out(r: Registration, private=False):
    out = {
        "id": r.id, "reference": r.public_ref, "name": r.name,
        "vehicle_number": r.vehicle_number, "visit_date": r.visit_date.isoformat(),
        "num_visitors": r.num_visitors, "status": r.status,
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
    }
    if private:
        out.update(mobile=r.mobile, address=r.address)
    return out


def scan_out(s: Scan):
    return {"id": s.id, "plate": s.plate, "status": s.status, "confidence": s.confidence,
            "visitor_name": s.visitor_name, "vehicle_type": s.vehicle_type, "guard_username": s.guard_username,
            "details": s.details, "vehicle_status": s.vehicle_status, "scanned_at": s.scanned_at.strftime("%Y-%m-%d %H:%M:%S")}


@app.post("/register", status_code=201)
def register(body: RegistrationIn):
    """Public endpoint: store a visitor registration for date-based gate matching."""
    with SessionLocal() as db:
        record = Registration(**body.model_dump(), status="REGISTERED")
        db.add(record)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, f"{body.vehicle_number} already has a registration for {body.visit_date}")
        db.refresh(record)
        return {"message": "Registration saved successfully. Security will verify the vehicle plate at the gate.",
                "registration": registration_out(record)}


@app.get("/visitor/status/{reference}")
def visitor_status(reference: str):
    """Unpredictable reference lets a visitor check only their own request."""
    with SessionLocal() as db:
        r = db.query(Registration).filter_by(public_ref=reference).first()
        if not r:
            raise HTTPException(404, "Registration not found")
        return registration_out(r)


@app.post("/auth/login")
def guard_login(body: LoginIn):
    with SessionLocal() as db:
        guard = db.query(Guard).filter_by(username=body.username.strip(), active=1).first()
        if not guard or not verify_password(body.password, guard.password_hash):
            raise HTTPException(401, "Invalid username or password")
        token = create_session(guard.username)
        return {"access_token": token, "token_type": "bearer", "username": guard.username,
                "expires_in": 28800}


@app.get("/auth/me")
def auth_me(guard=Depends(get_guard)):
    return guard


@app.post("/auth/logout")
def guard_logout(authorization: str | None = Header(default=None), guard=Depends(get_guard)):
    # Header is resolved by get_guard; token is also read here for revocation.
    if authorization and authorization.startswith("Bearer "):
        destroy_session(authorization[7:].strip())
    return {"ok": True}


@app.get("/registrations")
def registrations(only_today: bool = False, status: str | None = None, guard=Depends(get_guard)):
    with SessionLocal() as db:
        q = db.query(Registration)
        if only_today:
            q = q.filter(Registration.visit_date == today_ist())
        # Registration status is informational only; there is no guard approval workflow.
        if status and status == "REGISTERED":
            q = q.filter(Registration.status == "REGISTERED")
        return [registration_out(r, private=True) for r in q.order_by(Registration.visit_date, Registration.id).all()]


@app.get("/fleet/vehicles")
def fleet_vehicles(guard=Depends(get_guard)):
    with FleetSession() as db:
        return [vehicle_out(v) for v in db.query(FleetVehicle).order_by(FleetVehicle.category, FleetVehicle.plate).all()]


@app.post("/fleet/vehicles", status_code=201)
def add_fleet_vehicle(body: FleetVehicleIn, guard=Depends(get_guard)):
    with FleetSession() as db:
        existing = db.query(FleetVehicle).filter_by(plate=body.plate).first()
        if existing:
            raise HTTPException(409, f"{body.plate} is already in the staff/college vehicle database")
        row = FleetVehicle(plate=body.plate, category=body.category,
                           owner_name=body.owner_name.strip(),
                           department=(body.department or "").strip() or None,
                           notes=(body.notes or "").strip() or None)
        db.add(row)
        db.commit()
        db.refresh(row)
        return vehicle_out(row)


@app.delete("/fleet/vehicles/{vehicle_id}")
def delete_fleet_vehicle(vehicle_id: int, guard=Depends(get_guard)):
    with FleetSession() as db:
        row = db.get(FleetVehicle, vehicle_id)
        if not row:
            raise HTTPException(404, "Fleet vehicle not found")
        db.delete(row)
        db.commit()
        return {"ok": True}


@app.get("/fleet/logs")
def fleet_logs(limit: int = 100, guard=Depends(get_guard)):
    limit = max(1, min(limit, 500))
    with FleetSession() as db:
        rows = (db.query(FleetVehicleLog).filter(FleetVehicleLog.category.in_(["STAFF", "COLLEGE"]))
                .order_by(FleetVehicleLog.id.desc()).limit(limit).all())
        return [log_out(row) for row in rows]


def toggle_status(current: str | None) -> str:
    """Flip an authorized vehicle between inside and outside campus."""
    return "OUTSIDE CAMPUS" if current == "INSIDE CAMPUS" else "INSIDE CAMPUS"


def other_vehicle_status(db, plate: str, transition: bool) -> str:
    state = db.query(VehicleState).filter_by(plate=plate).first()
    if state is None:
        state = VehicleState(plate=plate, vehicle_status="OUTSIDE CAMPUS")
        db.add(state)
        db.flush()
    if transition:
        state.vehicle_status = toggle_status(state.vehicle_status)
        state.updated_at = now_ist().replace(tzinfo=None)
    return state.vehicle_status


@app.post("/manual-decision")
def manual_decision(body: ManualDecisionIn, guard=Depends(get_guard)):
    """Record explicit guard decision; granted entries update current campus status."""
    plate = body.plate
    now = now_ist().replace(tzinfo=None)
    status = "GRANTED" if body.permission_granted else "UNREGISTERED"
    details = (body.details or "Guard manually granted entry") if body.permission_granted else (body.details or "Guard denied entry")
    vehicle_status = None
    manual_vehicle_type = "OTHER"
    if body.permission_granted:
        with FleetSession() as fleet:
            registered_fleet = fleet.query(FleetVehicle).filter_by(plate=plate).first()
            if registered_fleet:
                manual_vehicle_type = registered_fleet.category
                registered_fleet.vehicle_status = toggle_status(registered_fleet.vehicle_status)
                vehicle_status = registered_fleet.vehicle_status
                fleet.add(FleetVehicleLog(plate=plate, category=registered_fleet.category,
                    owner_name=registered_fleet.owner_name, permission="MANUALLY_GRANTED",
                    guard_username=guard["username"],
                    scan_confidence=str(body.confidence) if body.confidence is not None else None,
                    details="Guard manually confirmed permission",
                    vehicle_status=vehicle_status))
                fleet.commit()
        if vehicle_status is None:
            with SessionLocal() as db:
                vehicle_status = other_vehicle_status(db, plate, True)
                db.commit()
    with SessionLocal() as db:
        matching_registration = (db.query(Registration)
            .filter(Registration.vehicle_number == plate, Registration.visit_date == today_ist()).first())
        if manual_vehicle_type == "OTHER" and matching_registration:
            manual_vehicle_type = "VISITOR"
        db.add(Scan(plate=plate, status=status, confidence=body.confidence,
                    visitor_name=matching_registration.name if manual_vehicle_type == "VISITOR" and matching_registration else None,
                    vehicle_type=manual_vehicle_type,
                    guard_username=guard["username"], details=f"MANUAL DECISION: {details}",
                    vehicle_status=vehicle_status, scanned_at=now))
        db.commit()
    return {"ok": True, "status": status, "plate": plate, "vehicle_status": vehicle_status,
            "message": (f"Permission granted. Vehicle status: {vehicle_status.lower()}. Entry recorded in the appropriate vehicle log." if body.permission_granted
                        else "Permission denied. Vehicle status was not changed and no authorized entry was recorded.")}


@app.post("/scan")
def scan(file: UploadFile = File(...), guard=Depends(get_guard)):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(415, "Upload a JPEG, PNG, WEBP, or BMP image")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image must be 10 MB or smaller")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "Could not decode image")
    res = STATE["reader"].read(img)
    res.update(status="NO_PLATE", visitor=None, near_match=None, date=today_ist().isoformat(), vehicle_status=None)
    plate = res.get("plate")
    details = "No usable plate detected; guard should enter the plate manually and decide permission"
    transition_allowed = True
    with SessionLocal() as db:
        # Debounce repeated video frames so a stationary vehicle doesn't flip status every frame.
        plate_query = Scan.plate == plate if plate else Scan.plate.is_(None)
        last_same = (db.query(Scan).filter(Scan.guard_username == guard["username"], plate_query)
                     .order_by(Scan.id.desc()).first())
        recent_duplicate = bool(last_same and (now_ist().replace(tzinfo=None) - last_same.scanned_at).total_seconds() < 10)
        transition_allowed = not recent_duplicate
        if plate:
            todays = db.query(Registration).filter(Registration.visit_date == today_ist()).all()
            exact = next((r for r in todays if r.vehicle_number == plate), None)
            if exact:
                res["status"] = "GRANTED"
                res["vehicle_type"] = "VISITOR"
                res["visitor"] = {"name": exact.name, "num_visitors": exact.num_visitors}
                details = "Exact visitor registration match for today"
                res["manual_permission_required"] = False
                res["vehicle_status"] = other_vehicle_status(db, plate, transition_allowed)
            else:
                near = next((r for r in todays if edit_distance(r.vehicle_number, plate) == 1), None)
                if near:
                    res["status"] = "CHECK_MANUALLY"
                    res["vehicle_type"] = "VISITOR"
                    res["near_match"] = {"vehicle_number": near.vehicle_number, "name": near.name,
                                          "num_visitors": near.num_visitors, "status": near.status}
                    res["manual_permission_required"] = True
                    details = "Near-match visitor plate found; guard must verify plate and permission"
                else:
                    with FleetSession() as fleet:
                        registered_fleet = fleet.query(FleetVehicle).filter_by(plate=plate).first()
                        if registered_fleet:
                            res["status"] = "GRANTED"
                            res["vehicle_type"] = registered_fleet.category
                            res["fleet_vehicle"] = {"category": registered_fleet.category,
                                "owner_name": registered_fleet.owner_name,
                                "department": registered_fleet.department}
                            details = f"Registered {registered_fleet.category.lower()} vehicle"
                            if transition_allowed:
                                registered_fleet.vehicle_status = toggle_status(registered_fleet.vehicle_status)
                                fleet.add(FleetVehicleLog(plate=plate, category=registered_fleet.category,
                                    owner_name=registered_fleet.owner_name, permission="REGISTERED",
                                    guard_username=guard["username"],
                                    scan_confidence=str(res.get("confidence")) if res.get("confidence") is not None else None,
                                    details="Exact staff/college fleet plate match",
                                    vehicle_status=registered_fleet.vehicle_status))
                                fleet.commit()
                            res["vehicle_status"] = registered_fleet.vehicle_status
                            res["manual_permission_required"] = False
                        else:
                            res["status"] = "UNREGISTERED"
                            res["vehicle_type"] = "OTHER"
                            res["manual_permission_required"] = True
                            details = "Plate absent from visitor registrations and staff/college vehicle database; guard decision required"
        else:
            res["manual_permission_required"] = True
            res["vehicle_type"] = "OTHER"
        # Log every scan result, but avoid writing repeated identical webcam frames within 10 sec.
        now = now_ist().replace(tzinfo=None)
        duplicate = bool(last_same and last_same.status == res["status"] and
                         (now - last_same.scanned_at).total_seconds() < 10)
        if not duplicate:
            saved_scan = Scan(plate=plate, status=res["status"], confidence=res.get("confidence"),
                              visitor_name=(res.get("visitor") or {}).get("name"),
                              vehicle_type=res.get("vehicle_type") or ("OTHER" if plate else None),
                              guard_username=guard["username"], details=details,
                              vehicle_status=res.get("vehicle_status"), scanned_at=now)
            db.add(saved_scan)
            db.commit()
            db.refresh(saved_scan)
            res["scan_id"] = saved_scan.id
        else:
            res["scan_id"] = last_same.id
    return res


@app.get("/scans")
def scans(limit: int = 20, guard=Depends(get_guard)):
    limit = max(1, min(limit, 200))
    with SessionLocal() as db:
        rows = db.query(Scan).order_by(Scan.id.desc()).limit(limit).all()
        return [scan_out(s) for s in rows]


@app.get("/other-vehicle-logs")
def other_vehicle_logs(limit: int = 200, guard=Depends(get_guard)):
    """Visitor and other-vehicle scan history, excluding staff/college fleet vehicles."""
    limit = max(1, min(limit, 500))
    with SessionLocal() as db:
        rows = (db.query(Scan)
                .filter(Scan.plate.isnot(None))
                .filter(Scan.vehicle_type.notin_(["STAFF", "COLLEGE"]))
                .order_by(Scan.id.desc()).limit(limit).all())
        return [scan_out(row) for row in rows]


@app.get("/dashboard/stats")
def dashboard_stats(guard=Depends(get_guard)):
    with SessionLocal() as db:
        regs = db.query(Registration).filter_by(visit_date=today_ist()).all()
        scans_today = db.query(Scan).filter(Scan.scanned_at >= datetime.combine(today_ist(), dt_time.min)).all()
        return {
            "date": today_ist().isoformat(), "registrations_today": len(regs),
            "upcoming_registrations": db.query(Registration).filter(Registration.visit_date > today_ist()).count(),
            "scanned_today": len(scans_today),
            "granted": sum(s.status == "GRANTED" for s in scans_today),
            "unregistered": sum(s.status == "UNREGISTERED" for s in scans_today),
            "manual_check": sum(s.status == "CHECK_MANUALLY" for s in scans_today),
        }


@app.get("/health")
def health():
    return {"ok": "reader" in STATE, "today_ist": today_ist().isoformat()}


# Legacy standalone page remains available at the backend root for compatibility.
app.mount("/legacy", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="legacy")
