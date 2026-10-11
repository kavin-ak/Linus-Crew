"""Create a guard account interactively: python create_guard.py"""
import getpass
import re
from auth import hash_password
from db import Guard, SessionLocal, init_db


def main():
    init_db()
    username = input("Guard username: ").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,80}", username):
        raise SystemExit("Use 3-80 letters, digits, dots, underscores, or hyphens for username.")
    password = getpass.getpass("Password (minimum 12 characters): ")
    confirm = getpass.getpass("Confirm password: ")
    if len(password) < 12:
        raise SystemExit("Password must be at least 12 characters.")
    if password != confirm:
        raise SystemExit("Passwords do not match.")
    with SessionLocal() as db:
        if db.query(Guard).filter_by(username=username).first():
            raise SystemExit("That guard username already exists.")
        db.add(Guard(username=username, password_hash=hash_password(password), active=1))
        db.commit()
    print(f"Guard account '{username}' created. Keep the password private.")


if __name__ == "__main__":
    main()
