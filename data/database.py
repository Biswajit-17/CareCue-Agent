"""SQLite database setup and connection management for CareCue."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "carecue.db"


SCHEMA_SQL = """
-- Core tables with indexes for common query patterns

CREATE TABLE IF NOT EXISTS caregivers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    timezone TEXT DEFAULT 'UTC',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY,
    caregiver_id TEXT NOT NULL REFERENCES caregivers(id),
    name TEXT NOT NULL,
    date_of_birth TEXT NOT NULL,
    notes TEXT,
    phone TEXT,
    email TEXT,
    telegram_chat_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patients_caregiver ON patients(caregiver_id);
CREATE INDEX IF NOT EXISTS idx_patients_telegram ON patients(telegram_chat_id);

CREATE TABLE IF NOT EXISTS telegram_linking_codes (
    code TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id),
    created_at TEXT NOT NULL,
    used BOOLEAN DEFAULT 0
);

CREATE TABLE IF NOT EXISTS doctors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    specialty TEXT,
    practice_name TEXT,
    phone TEXT,
    fax TEXT,
    email TEXT,
    address TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pharmacies (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id),
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    address TEXT,
    fax TEXT,
    email TEXT,
    hours TEXT,
    is_preferred BOOLEAN DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pharmacies_patient ON pharmacies(patient_id);

CREATE TABLE IF NOT EXISTS prescriptions (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id),
    doctor_id TEXT NOT NULL REFERENCES doctors(id),
    pharmacy_id TEXT REFERENCES pharmacies(id),
    medication_name TEXT NOT NULL,
    generic_name TEXT,
    strength TEXT NOT NULL,
    form TEXT,
    route TEXT,
    dose_amount REAL NOT NULL,
    dose_unit TEXT NOT NULL,
    frequency TEXT NOT NULL,
    frequency_hours INTEGER,
    instructions TEXT,
    refill_cycle_days INTEGER NOT NULL,
    refills_remaining INTEGER DEFAULT 0,
    total_refills_allowed INTEGER DEFAULT 0,
    last_filled_date TEXT,
    next_refill_due TEXT,
    prescription_start_date TEXT NOT NULL,
    prescription_end_date TEXT,
    is_active BOOLEAN DEFAULT 1,
    discontinued_date TEXT,
    discontinuation_reason TEXT,
    ndc_code TEXT,
    rxnorm_cui TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prescriptions_patient ON prescriptions(patient_id);
CREATE INDEX IF NOT EXISTS idx_prescriptions_doctor ON prescriptions(doctor_id);
CREATE INDEX IF NOT EXISTS idx_prescriptions_active ON prescriptions(is_active, next_refill_due);
CREATE INDEX IF NOT EXISTS idx_prescriptions_med ON prescriptions(medication_name);

CREATE TABLE IF NOT EXISTS refills (
    id TEXT PRIMARY KEY,
    prescription_id TEXT NOT NULL REFERENCES prescriptions(id),
    requested_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    filled_date TEXT,
    picked_up_date TEXT,
    pharmacy_id TEXT REFERENCES pharmacies(id),
    quantity INTEGER,
    days_supply INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_refills_prescription ON refills(prescription_id);
CREATE INDEX IF NOT EXISTS idx_refills_status ON refills(status);

CREATE TABLE IF NOT EXISTS dose_logs (
    id TEXT PRIMARY KEY,
    prescription_id TEXT NOT NULL REFERENCES prescriptions(id),
    scheduled_time TEXT NOT NULL,
    actual_time TEXT,
    status TEXT NOT NULL DEFAULT 'missed',
    dose_amount REAL,
    notes TEXT,
    logged_by TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dose_logs_prescription ON dose_logs(prescription_id);
CREATE INDEX IF NOT EXISTS idx_dose_logs_scheduled ON dose_logs(scheduled_time);

CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id),
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    related_prescription_ids TEXT NOT NULL DEFAULT '[]',
    related_refill_ids TEXT NOT NULL DEFAULT '[]',
    is_read BOOLEAN DEFAULT 0,
    is_action_taken BOOLEAN DEFAULT 0,
    action_taken TEXT,
    created_at TEXT NOT NULL,
    read_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_patient ON alerts(patient_id);
CREATE INDEX IF NOT EXISTS idx_alerts_unread ON alerts(patient_id, is_read);

CREATE TABLE IF NOT EXISTS dose_confirmation_tokens (
    token TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id),
    prescription_id TEXT NOT NULL REFERENCES prescriptions(id),
    scheduled_time TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used BOOLEAN DEFAULT 0,
    pending BOOLEAN DEFAULT 1,
    used_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dose_tokens_prescription ON dose_confirmation_tokens(prescription_id, scheduled_time);
CREATE INDEX IF NOT EXISTS idx_dose_tokens_patient_pending ON dose_confirmation_tokens(patient_id, pending);
"""


def get_connection() -> sqlite3.Connection:
    """Get a new SQLite connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_connection():
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def db_transaction():
    """Context manager for explicit transactions."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate(conn) -> None:
    """Lightweight migration for existing databases (additive only)."""
    # patients table: add phone/email/telegram_chat_id if missing
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(patients)").fetchall()}
    if "phone" not in cols:
        conn.execute("ALTER TABLE patients ADD COLUMN phone TEXT")
    if "email" not in cols:
        conn.execute("ALTER TABLE patients ADD COLUMN email TEXT")
    if "telegram_chat_id" not in cols:
        conn.execute("ALTER TABLE patients ADD COLUMN telegram_chat_id INTEGER")

    # dose_confirmation_tokens table: add patient_id/pending if missing
    dcols = {row["name"] for row in conn.execute("PRAGMA table_info(dose_confirmation_tokens)").fetchall()}
    if "patient_id" not in dcols:
        conn.execute("ALTER TABLE dose_confirmation_tokens ADD COLUMN patient_id TEXT DEFAULT ''")
    if "pending" not in dcols:
        conn.execute("ALTER TABLE dose_confirmation_tokens ADD COLUMN pending BOOLEAN DEFAULT 1")

    # telegram_linking_codes table: create if missing
    tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "telegram_linking_codes" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS telegram_linking_codes (
                code TEXT PRIMARY KEY,
                patient_id TEXT NOT NULL REFERENCES patients(id),
                created_at TEXT NOT NULL,
                used BOOLEAN DEFAULT 0
            )
        """)


def init_database() -> None:
    """Initialize the database schema."""
    with db_connection() as conn:
        conn.executescript(SCHEMA_SQL)
        _migrate(conn)


def reset_database() -> None:
    """Drop all tables and reinitialize (for development/testing)."""
    with db_connection() as conn:
        conn.executescript("""
            DROP TABLE IF EXISTS telegram_linking_codes;
            DROP TABLE IF EXISTS dose_confirmation_tokens;
            DROP TABLE IF EXISTS alerts;
            DROP TABLE IF EXISTS dose_logs;
            DROP TABLE IF EXISTS refills;
            DROP TABLE IF EXISTS prescriptions;
            DROP TABLE IF EXISTS pharmacies;
            DROP TABLE IF EXISTS doctors;
            DROP TABLE IF EXISTS patients;
            DROP TABLE IF EXISTS caregivers;
        """)
        conn.executescript(SCHEMA_SQL)


def get_db_path() -> Path:
    """Return the database file path."""
    return DB_PATH