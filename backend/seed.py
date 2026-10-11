"""Seed 5 registrations for TODAY (IST).

Edit SAMPLES so the plates match your 5 test photos, then run:  python seed.py
Re-running is safe: today's rows for these plates are replaced.
"""
from db import Registration, SessionLocal, init_db, today_ist
from plates import normalize_user_input

SAMPLES = [
    # (vehicle_number, name, mobile, address, num_visitors)
    ("TN37AB1234", "Arjun Kumar",     "9876543210", "Peelamedu, Coimbatore",     2),
    ("TN66C4521",  "Priya Raman",     "9123456780", "RS Puram, Coimbatore",      1),
    ("KA05MN7788", "Rahul Shetty",    "9988776655", "Jayanagar, Bengaluru",      3),
    ("KL07BX3090", "Anjali Menon",    "9447012345", "Kakkanad, Kochi",           4),
    ("TN38DK9001", "Senthil Murugan", "9003456789", "Singanallur, Coimbatore",   2),
]

if __name__ == "__main__":
    init_db()
    today = today_ist()
    with SessionLocal() as db:
        for plate, name, mobile, addr, n in SAMPLES:
            p = normalize_user_input(plate)
            assert p, f"Invalid plate in SAMPLES: {plate}"
            db.query(Registration).filter_by(vehicle_number=p, visit_date=today).delete()
            db.add(Registration(name=name, vehicle_number=p, mobile=mobile, address=addr,
                                num_visitors=n, visit_date=today, status="REGISTERED"))
            print(f"  {p:<12} {name}")
        db.commit()
    print(f"Seeded {len(SAMPLES)} registrations for {today} (IST)")
