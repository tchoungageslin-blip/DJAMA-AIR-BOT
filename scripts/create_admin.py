"""
Create the initial admin agent.
Run: python scripts/create_admin.py

Requires DATABASE_URL and JWT_SECRET environment variables to be set.
"""
import os
import sys
import hashlib

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.db.connection import execute_query
from api.config import settings


def create_admin():
    email = input("Email admin [admin@djamaairlogistics.com]: ").strip() or "admin@djamaairlogistics.com"
    full_name = input("Nom complet [Abdelkarim]: ").strip() or "Abdelkarim"
    password = input("Mot de passe [djama2025]: ").strip() or "djama2025"

    # Hash password using same method as auth service
    salt = settings.JWT_SECRET[:16]
    password_hash = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()

    # Check if agent already exists
    existing = execute_query(
        "SELECT id FROM agents WHERE email = %s",
        (email,),
        fetch_one=True
    )

    if existing:
        # Update password
        execute_query(
            "UPDATE agents SET password_hash = %s, full_name = %s WHERE email = %s",
            (password_hash, full_name, email)
        )
        print(f"Agent {email} updated successfully.")
    else:
        execute_query(
            """INSERT INTO agents (id, email, password_hash, full_name, role, is_active, created_at)
            VALUES (gen_random_uuid(), %s, %s, %s, 'ADMIN', true, NOW())""",
            (email, password_hash, full_name)
        )
        print(f"Admin agent {email} created successfully.")

    print("You can now login to the dashboard.")


if __name__ == "__main__":
    create_admin()
