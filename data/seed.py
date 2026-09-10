"""Seed data loader for CareCue - loads JSON seed files into SQLite."""

import json
from datetime import datetime
from pathlib import Path

from data.database import db_connection, init_database
from data.models import (
    Caregiver,
    Patient,
    Doctor,
    Pharmacy,
    Prescription,
    Refill,
    DoseLog,
)


SEED_DIR = Path(__file__).parent / "seed"

SEED_FILES = [
    ("caregivers.json", Caregiver),
    ("patients.json", Patient),
    ("doctors.json", Doctor),
    ("pharmacies.json", Pharmacy),
    ("prescriptions.json", Prescription),
    ("refills.json", Refill),
    ("dose_logs.json", DoseLog),
]


TABLE_INSERTS = {
    "caregivers": """
        INSERT INTO caregivers (id, name, email, phone, timezone, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
    "patients": """
        INSERT INTO patients (id, caregiver_id, name, date_of_birth, notes, phone, email, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "doctors": """
        INSERT INTO doctors (id, name, specialty, practice_name, phone, fax, email, address, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "pharmacies": """
        INSERT INTO pharmacies (id, patient_id, name, phone, address, fax, email, hours, is_preferred, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "prescriptions": """
        INSERT INTO prescriptions (
            id, patient_id, doctor_id, pharmacy_id, medication_name, generic_name,
            strength, form, route, dose_amount, dose_unit, frequency, frequency_hours,
            instructions, refill_cycle_days, refills_remaining, total_refills_allowed,
            last_filled_date, next_refill_due, prescription_start_date, prescription_end_date,
            is_active, discontinued_date, discontinuation_reason, ndc_code, rxnorm_cui,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "refills": """
        INSERT INTO refills (id, prescription_id, requested_date, status, filled_date, picked_up_date, pharmacy_id, quantity, days_supply, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "dose_logs": """
        INSERT INTO dose_logs (id, prescription_id, scheduled_time, actual_time, status, dose_amount, notes, logged_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
}


def parse_datetime(value: str | None) -> str | None:
    """Parse ISO datetime string to ensure consistent format."""
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.isoformat()


def parse_date(value: str | None) -> str | None:
    """Parse ISO date string."""
    if not value:
        return None
    return value  # Already ISO format


def load_seed_file(filename: str) -> list[dict]:
    """Load a single seed JSON file."""
    path = SEED_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Seed file not found: {path}")
    with open(path) as f:
        return json.load(f)


def seed_caregivers(conn, data: list[dict]) -> None:
    for item in data:
        conn.execute(TABLE_INSERTS["caregivers"], (
            item["id"], item["name"], item["email"], item.get("phone"),
            item.get("timezone", "UTC"), parse_datetime(item["created_at"])
        ))


def seed_patients(conn, data: list[dict]) -> None:
    for item in data:
        conn.execute(TABLE_INSERTS["patients"], (
            item["id"], item["caregiver_id"], item["name"],
            parse_date(item["date_of_birth"]), item.get("notes"),
            item.get("phone"), item.get("email"),
            parse_datetime(item["created_at"])
        ))


def seed_doctors(conn, data: list[dict]) -> None:
    for item in data:
        conn.execute(TABLE_INSERTS["doctors"], (
            item["id"], item["name"], item.get("specialty"),
            item.get("practice_name"), item.get("phone"), item.get("fax"),
            item.get("email"), item.get("address"), item.get("notes"),
            parse_datetime(item["created_at"])
        ))


def seed_pharmacies(conn, data: list[dict]) -> None:
    for item in data:
        conn.execute(TABLE_INSERTS["pharmacies"], (
            item["id"], item["patient_id"], item["name"], item["phone"],
            item.get("address"), item.get("fax"), item.get("email"),
            item.get("hours"), int(item.get("is_preferred", True)),
            parse_datetime(item["created_at"])
        ))


def seed_prescriptions(conn, data: list[dict]) -> None:
    for item in data:
        conn.execute(TABLE_INSERTS["prescriptions"], (
            item["id"], item["patient_id"], item["doctor_id"], item.get("pharmacy_id"),
            item["medication_name"], item.get("generic_name"),
            item["strength"], item.get("form"), item.get("route"),
            item["dose_amount"], item["dose_unit"], item["frequency"],
            item.get("frequency_hours"), item.get("instructions"),
            item["refill_cycle_days"], item["refills_remaining"],
            item["total_refills_allowed"],
            parse_date(item.get("last_filled_date")),
            parse_date(item.get("next_refill_due")),
            parse_date(item["prescription_start_date"]),
            parse_date(item.get("prescription_end_date")),
            int(item.get("is_active", True)),
            parse_date(item.get("discontinued_date")),
            item.get("discontinuation_reason"),
            item.get("ndc_code"), item.get("rxnorm_cui"),
            parse_datetime(item["created_at"]), parse_datetime(item["updated_at"])
        ))


def seed_refills(conn, data: list[dict]) -> None:
    for item in data:
        conn.execute(TABLE_INSERTS["refills"], (
            item["id"], item["prescription_id"],
            parse_date(item["requested_date"]), item["status"],
            parse_date(item.get("filled_date")),
            parse_date(item.get("picked_up_date")),
            item.get("pharmacy_id"), item.get("quantity"),
            item.get("days_supply"), item.get("notes"),
            parse_datetime(item["created_at"]), parse_datetime(item["updated_at"])
        ))


def seed_dose_logs(conn, data: list[dict]) -> None:
    for item in data:
        conn.execute(TABLE_INSERTS["dose_logs"], (
            item["id"], item["prescription_id"],
            parse_datetime(item["scheduled_time"]),
            parse_datetime(item.get("actual_time")),
            item["status"], item.get("dose_amount"),
            item.get("notes"), item.get("logged_by"),
            parse_datetime(item["created_at"])
        ))


SEED_FUNCTIONS = {
    "caregivers.json": seed_caregivers,
    "patients.json": seed_patients,
    "doctors.json": seed_doctors,
    "pharmacies.json": seed_pharmacies,
    "prescriptions.json": seed_prescriptions,
    "refills.json": seed_refills,
    "dose_logs.json": seed_dose_logs,
}


def seed_database(reset: bool = False) -> None:
    """Load all seed data into the database."""
    if reset:
        from .database import reset_database
        reset_database()
    else:
        init_database()

    with db_connection() as conn:
        for filename, _ in SEED_FILES:
            data = load_seed_file(filename)
            seed_func = SEED_FUNCTIONS[filename]
            seed_func(conn, data)
            print(f"Seeded {len(data)} records from {filename}")

    print("Database seeding complete!")


if __name__ == "__main__":
    import sys
    reset_flag = "--reset" in sys.argv
    seed_database(reset=reset_flag)