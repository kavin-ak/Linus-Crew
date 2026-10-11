# Campus Gate ANPR — Visitor and Security Portals

A local hackathon prototype with a public visitor registration portal and a separate authenticated guard portal. The backend uses FastAPI, OpenCV, EasyOCR, SQLAlchemy, and SQLite; the frontend uses React and Vite.

## Features

- Public visitor registration. Submissions are stored immediately with status `REGISTERED`; guards do not approve or reject registrations.
- Private reference-based visitor status lookup.
- Guard login, dashboard, registration search, ANPR image/webcam/video scan UI, and scan history.
- Backend role enforcement: registration submission/status lookup are public; registration listing, scan, scan history, dashboard stats, and `/auth/me` require a valid guard bearer token.
- SQLite schema migration adds new columns to an existing `gate.db` without deleting its records.
- Passwords are stored as salted scrypt hashes. Prototype sessions are in-memory and expire after 8 hours; restarting the backend logs guards out.

## Requirements

- Python 3.11–3.13 with pip (the installed EasyOCR/PyTorch wheel compatibility depends on your exact package versions).
- Node.js LTS with npm.
- Internet on first backend launch so EasyOCR can download its pretrained weights.

## Windows setup

### 1. Backend (CMD window 1)

```bat
cd /d D:\Genesis\backend
py -3.13 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `.venv` already exists, do not recreate it unless it is broken; activate it instead. Run `py -3.13` only if Python 3.13 is installed.

Create a guard account interactively (password is not echoed and is never stored in plaintext):

```bat
python create_guard.py
```

Create the database schema and start the backend:

```bat
python -c "from db import init_db; init_db(); print('Database ready')"
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

The SQLite file is `backend\gate.db`. Keep it private and back it up before updates. Do not run `seed.py` on a real visitor database: it replaces the sample vehicle rows for today's date.

Optional: for a demo database only, seed sample registrations in another backend terminal with the virtual environment active:

```bat
python seed.py
```

Seeded records and public visitor submissions use the `REGISTERED` status. No guard approval is required; the gate scan checks the vehicle number and visit date.

### 2. Frontend (CMD window 2)

```bat
cd /d D:\Genesis\frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Keep both terminals running.

## Portal routes

- `http://localhost:5173/#/visitor/register` — public visitor registration and reference-based status check.
- `http://localhost:5173/#/guard/login` — guard sign-in.
- `http://localhost:5173/#/guard/dashboard` — authenticated dashboard.
- `http://localhost:5173/#/guard/scan` — authenticated ANPR scanner.
- `http://localhost:5173/#/guard/registrations` — authenticated registration list and scan history.
- `http://localhost:8000/docs` — development API documentation; keep local only.

## Security and prototype limitations

- Guard accounts are not publicly self-registered; create them locally using `create_guard.py`.
- Visitor references are unguessable bearer-style secrets. Anyone who possesses a reference can view its limited status response; visitors should keep it private.
- Guard sessions are held in memory and are invalidated when the backend restarts. For production, use persistent, revocable sessions or a well-reviewed identity provider, HTTPS, CSRF protections where applicable, rate limiting, stronger audit controls, and deployment-specific CORS settings.
- CORS currently permits only localhost and 127.0.0.1 on Vite's port 5173.
- This is software access-decision support only; it does not actuate a physical gate. OCR output can be wrong and a guard must manually verify uncertain cases.
- Database `create_all()` does not perform general schema migrations; this project adds explicit SQLite migrations for its added columns. Back up data before future schema changes.

## Smoke-test checklist

1. Submit a visitor registration; verify it is stored as `REGISTERED` and note the reference.
2. Use the reference on the visitor page to check status.
3. Confirm unauthenticated `GET /registrations`, `GET /scans`, `POST /scan`, and `GET /dashboard/stats` return 401.
4. Log in as a guard and verify registrations/dashboard become available.
5. Scan a registered plate for today and verify an exact match returns `GRANTED`.
6. Verify an unregistered plate is not granted access and a near-match returns `CHECK_MANUALLY`.
7. Try a no-plate image; verify the decision and scan log.
8. Restart backend and confirm registrations remain in SQLite (guard must log in again).

## Staff/college fleet database and manual permission flow

- Staff and college-owned plates are stored separately in `backend\fleet.db` (tables `fleet_vehicles` and `fleet_vehicle_logs`). Visitor registrations and general scan history remain in `gate.db`.
- Open **Security staff → Staff & college vehicles** to add/remove staff or college vehicles and view the dedicated entry log.
- An exact staff/college plate match is shown as `GRANTED` and written to `fleet_vehicle_logs`; repeated webcam/video frames from the same guard are suppressed for 10 seconds.
- If a plate is absent from both today's visitor registrations and `fleet.db`, the scanner asks the guard whether permission was granted. **Yes** records a `MANUALLY_GRANTED` entry in the dedicated log. **No** records the denial in the general scan history and does not add a fleet-log entry. The manually authorized vehicle is not automatically added to the permanent staff/college plate database, so the guard must decide again on a future arrival unless an administrator registers it.
- Back up both `gate.db` and `fleet.db`. This remains a prototype; manually confirm the plate and the driver's authorization before selecting Yes.
