"""Create the first local administrator without hard-coding any credentials."""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import select
from database import SessionLocal, User, initialize_database
from security import hash_password

username = os.getenv("ADMIN_USERNAME")
password = os.getenv("ADMIN_PASSWORD")
if not username or not password:
    raise SystemExit("Set ADMIN_USERNAME and ADMIN_PASSWORD before running this command.")
if len(password) < 8:
    raise SystemExit("ADMIN_PASSWORD must be at least 8 characters.")

initialize_database()
with SessionLocal() as db:
    if db.scalar(select(User).where(User.username == username)):
        raise SystemExit("That username already exists; no changes were made.")
    db.add(User(username=username, password_hash=hash_password(password), role="admin"))
    db.commit()
print("Administrator created successfully.")
