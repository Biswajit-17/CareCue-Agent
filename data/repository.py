"""Repository layer for CareCue - CRUD operations for all entities."""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .database import db_connection, get_connection
from .models import (
    Caregiver,
    Patient,
    Doctor,
    Pharmacy,
    Prescription,
    Refill,
    DoseLog,
    DoseToken,
    Alert,
    Frequency,
    RefillStatus,
    DoseStatus,
    AlertType,
    AlertSeverity,
)


class Repository:
    """Data access layer - all DB operations go through here."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    def _conn(self):
        if self.db_path:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            return conn
        return get_connection()

    # --- Caregiver ---
    def create_caregiver(self, caregiver: Caregiver) -> Caregiver:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO caregivers (id, name, email, phone, timezone, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (caregiver.id, caregiver.name, caregiver.email, caregiver.phone,
                  caregiver.timezone, caregiver.created_at.isoformat()))
        return caregiver

    def get_caregiver(self, caregiver_id: str) -> Optional[Caregiver]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM caregivers WHERE id = ?", (caregiver_id,)).fetchone()
            return self._row_to_caregiver(row) if row else None

    def get_caregiver_by_email(self, email: str) -> Optional[Caregiver]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM caregivers WHERE email = ?", (email,)).fetchone()
            return self._row_to_caregiver(row) if row else None

    def list_caregivers(self) -> list[Caregiver]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM caregivers ORDER BY created_at DESC").fetchall()
            return [self._row_to_caregiver(r) for r in rows]

    # --- Patient ---
    def create_patient(self, patient: Patient) -> Patient:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO patients (id, caregiver_id, name, date_of_birth, notes, phone, email, telegram_chat_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (patient.id, patient.caregiver_id, patient.name,
                  patient.date_of_birth.isoformat(), patient.notes,
                  patient.phone, str(patient.email) if patient.email else None,
                  patient.telegram_chat_id,
                  patient.created_at.isoformat()))
        return patient

    def get_patient(self, patient_id: str) -> Optional[Patient]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
            return self._row_to_patient(row) if row else None

    def get_patients_by_caregiver(self, caregiver_id: str) -> list[Patient]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM patients WHERE caregiver_id = ? ORDER BY created_at DESC",
                (caregiver_id,)
            ).fetchall()
            return [self._row_to_patient(r) for r in rows]

    def get_patient_by_phone(self, phone: str) -> Optional[Patient]:
        """Look up a patient by phone number (normalized: no dashes/spaces)."""
        normalized = phone.replace(" ", "").replace("-", "")
        with self._conn() as conn:
            for row in conn.execute("SELECT * FROM patients WHERE phone IS NOT NULL"):
                db_norm = (row["phone"] or "").replace(" ", "").replace("-", "")
                if db_norm == normalized:
                    return self._row_to_patient(row)
            return None

    def get_patient_by_telegram_chat_id(self, chat_id: int) -> Optional[Patient]:
        """Look up a patient by Telegram chat_id."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM patients WHERE telegram_chat_id = ?", (chat_id,)
            ).fetchone()
            return self._row_to_patient(row) if row else None

    # --- Telegram linking codes ---
    def create_linking_code(self, code: str, patient_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO telegram_linking_codes (code, patient_id, created_at, used) VALUES (?, ?, ?, 0)",
                (code, patient_id, datetime.utcnow().isoformat())
            )

    def get_linking_code(self, code: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM telegram_linking_codes WHERE code = ? AND used = 0",
                (code,)
            ).fetchone()
            if not row:
                return None
            return {"code": row["code"], "patient_id": row["patient_id"],
                    "created_at": row["created_at"]}

    def consume_linking_code(self, code: str) -> bool:
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE telegram_linking_codes SET used = 1 WHERE code = ? AND used = 0",
                (code,)
            )
            return cursor.rowcount > 0

    def set_patient_telegram_chat_id(self, patient_id: str, chat_id: int) -> bool:
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE patients SET telegram_chat_id = ? WHERE id = ?",
                (chat_id, patient_id)
            )
            return cursor.rowcount > 0

    # --- Doctor ---
    def create_doctor(self, doctor: Doctor) -> Doctor:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO doctors (id, name, specialty, practice_name, phone, fax, email, address, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (doctor.id, doctor.name, doctor.specialty, doctor.practice_name,
                  doctor.phone, doctor.fax, doctor.email, doctor.address,
                  doctor.notes, doctor.created_at.isoformat()))
        return doctor

    def get_doctor(self, doctor_id: str) -> Optional[Doctor]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM doctors WHERE id = ?", (doctor_id,)).fetchone()
            return self._row_to_doctor(row) if row else None

    def list_doctors(self) -> list[Doctor]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM doctors ORDER BY name").fetchall()
            return [self._row_to_doctor(r) for r in rows]

    # --- Pharmacy ---
    def create_pharmacy(self, pharmacy: Pharmacy) -> Pharmacy:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO pharmacies (id, patient_id, name, phone, address, fax, email, hours, is_preferred, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (pharmacy.id, pharmacy.patient_id, pharmacy.name, pharmacy.phone,
                  pharmacy.address, pharmacy.fax, pharmacy.email, pharmacy.hours,
                  int(pharmacy.is_preferred), pharmacy.created_at.isoformat()))
        return pharmacy

    def get_pharmacy(self, pharmacy_id: str) -> Optional[Pharmacy]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM pharmacies WHERE id = ?", (pharmacy_id,)).fetchone()
            return self._row_to_pharmacy(row) if row else None

    def get_pharmacies_by_patient(self, patient_id: str) -> list[Pharmacy]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM pharmacies WHERE patient_id = ? ORDER BY is_preferred DESC, name",
                (patient_id,)
            ).fetchall()
            return [self._row_to_pharmacy(r) for r in rows]

    def get_preferred_pharmacy(self, patient_id: str) -> Optional[Pharmacy]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM pharmacies WHERE patient_id = ? AND is_preferred = 1 LIMIT 1",
                (patient_id,)
            ).fetchone()
            return self._row_to_pharmacy(row) if row else None

    # --- Prescription ---
    def create_prescription(self, prescription: Prescription) -> Prescription:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO prescriptions (
                    id, patient_id, doctor_id, pharmacy_id, medication_name, generic_name,
                    strength, form, route, dose_amount, dose_unit, frequency, frequency_hours,
                    instructions, refill_cycle_days, refills_remaining, total_refills_allowed,
                    last_filled_date, next_refill_due, prescription_start_date, prescription_end_date,
                    is_active, discontinued_date, discontinuation_reason, ndc_code, rxnorm_cui,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                prescription.id, prescription.patient_id, prescription.doctor_id,
                prescription.pharmacy_id, prescription.medication_name,
                prescription.generic_name, prescription.strength, prescription.form,
                prescription.route, prescription.dose_amount, prescription.dose_unit,
                prescription.frequency.value, prescription.frequency_hours,
                prescription.instructions, prescription.refill_cycle_days,
                prescription.refills_remaining, prescription.total_refills_allowed,
                prescription.last_filled_date.isoformat() if prescription.last_filled_date else None,
                prescription.next_refill_due.isoformat() if prescription.next_refill_due else None,
                prescription.prescription_start_date.isoformat(),
                prescription.prescription_end_date.isoformat() if prescription.prescription_end_date else None,
                int(prescription.is_active), 
                prescription.discontinued_date.isoformat() if prescription.discontinued_date else None,
                prescription.discontinuation_reason, prescription.ndc_code,
                prescription.rxnorm_cui, prescription.created_at.isoformat(),
                prescription.updated_at.isoformat()
            ))
        return prescription

    def get_prescription(self, prescription_id: str) -> Optional[Prescription]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM prescriptions WHERE id = ?", (prescription_id,)).fetchone()
            return self._row_to_prescription(row) if row else None

    def get_prescriptions_by_patient(self, patient_id: str, active_only: bool = True) -> list[Prescription]:
        with self._conn() as conn:
            query = "SELECT * FROM prescriptions WHERE patient_id = ?"
            params = [patient_id]
            if active_only:
                query += " AND is_active = 1"
            query += " ORDER BY medication_name"
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_prescription(r) for r in rows]

    def get_prescriptions_by_doctor(self, doctor_id: str) -> list[Prescription]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM prescriptions WHERE doctor_id = ? AND is_active = 1 ORDER BY medication_name",
                (doctor_id,)
            ).fetchall()
            return [self._row_to_prescription(r) for r in rows]

    def get_prescriptions_due_for_refill(self, days_threshold: int = 7) -> list[Prescription]:
        """Get active prescriptions where next_refill_due is within threshold days."""
        from datetime import date, timedelta
        target_date = (date.today() + timedelta(days=days_threshold)).isoformat()
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM prescriptions
                WHERE is_active = 1
                AND next_refill_due IS NOT NULL
                AND next_refill_due <= ?
                ORDER BY next_refill_due
            """, (target_date,)).fetchall()
            return [self._row_to_prescription(r) for r in rows]

    def get_overdue_refills(self) -> list[Prescription]:
        """Get active prescriptions where next_refill_due is past."""
        today = date.today().isoformat()
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM prescriptions
                WHERE is_active = 1
                AND next_refill_due IS NOT NULL
                AND next_refill_due < ?
                ORDER BY next_refill_due
            """, (today,)).fetchall()
            return [self._row_to_prescription(r) for r in rows]

    def update_prescription(self, prescription: Prescription) -> Prescription:
        prescription.updated_at = datetime.utcnow()
        with self._conn() as conn:
            conn.execute("""
                UPDATE prescriptions SET
                    patient_id = ?, doctor_id = ?, pharmacy_id = ?, medication_name = ?,
                    generic_name = ?, strength = ?, form = ?, route = ?,
                    dose_amount = ?, dose_unit = ?, frequency = ?, frequency_hours = ?,
                    instructions = ?, refill_cycle_days = ?, refills_remaining = ?,
                    total_refills_allowed = ?, last_filled_date = ?, next_refill_due = ?,
                    prescription_start_date = ?, prescription_end_date = ?,
                    is_active = ?, discontinued_date = ?, discontinuation_reason = ?,
                    ndc_code = ?, rxnorm_cui = ?, updated_at = ?
                WHERE id = ?
            """, (
                prescription.patient_id, prescription.doctor_id, prescription.pharmacy_id,
                prescription.medication_name, prescription.generic_name, prescription.strength,
                prescription.form, prescription.route, prescription.dose_amount,
                prescription.dose_unit, prescription.frequency.value, prescription.frequency_hours,
                prescription.instructions, prescription.refill_cycle_days,
                prescription.refills_remaining, prescription.total_refills_allowed,
                prescription.last_filled_date.isoformat() if prescription.last_filled_date else None,
                prescription.next_refill_due.isoformat() if prescription.next_refill_due else None,
                prescription.prescription_start_date.isoformat(),
                prescription.prescription_end_date.isoformat() if prescription.prescription_end_date else None,
                int(prescription.is_active),
                prescription.discontinued_date.isoformat() if prescription.discontinued_date else None,
                prescription.discontinuation_reason, prescription.ndc_code,
                prescription.rxnorm_cui, prescription.updated_at.isoformat(),
                prescription.id
            ))
        return prescription

    # --- Refill ---
    def create_refill(self, refill: Refill) -> Refill:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO refills (id, prescription_id, requested_date, status, filled_date,
                                   picked_up_date, pharmacy_id, quantity, days_supply, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                refill.id, refill.prescription_id,
                refill.requested_date.isoformat(), refill.status.value,
                refill.filled_date.isoformat() if refill.filled_date else None,
                refill.picked_up_date.isoformat() if refill.picked_up_date else None,
                refill.pharmacy_id, refill.quantity, refill.days_supply,
                refill.notes, refill.created_at.isoformat(), refill.updated_at.isoformat()
            ))
        return refill

    def get_refill(self, refill_id: str) -> Optional[Refill]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM refills WHERE id = ?", (refill_id,)).fetchone()
            return self._row_to_refill(row) if row else None

    def get_refills_by_prescription(self, prescription_id: str) -> list[Refill]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM refills WHERE prescription_id = ? ORDER BY requested_date DESC",
                (prescription_id,)
            ).fetchall()
            return [self._row_to_refill(r) for r in rows]

    def get_pending_refills(self) -> list[Refill]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM refills WHERE status = 'pending' ORDER BY requested_date"
            ).fetchall()
            return [self._row_to_refill(r) for r in rows]

    def update_refill(self, refill: Refill) -> Refill:
        refill.updated_at = datetime.utcnow()
        with self._conn() as conn:
            conn.execute("""
                UPDATE refills SET
                    prescription_id = ?, requested_date = ?, status = ?, filled_date = ?,
                    picked_up_date = ?, pharmacy_id = ?, quantity = ?, days_supply = ?,
                    notes = ?, updated_at = ?
                WHERE id = ?
            """, (
                refill.prescription_id, refill.requested_date.isoformat(),
                refill.status.value,
                refill.filled_date.isoformat() if refill.filled_date else None,
                refill.picked_up_date.isoformat() if refill.picked_up_date else None,
                refill.pharmacy_id, refill.quantity, refill.days_supply,
                refill.notes, refill.updated_at.isoformat(), refill.id
            ))
        return refill

    # --- DoseLog ---
    def create_dose_log(self, dose_log: DoseLog) -> DoseLog:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO dose_logs (id, prescription_id, scheduled_time, actual_time,
                                     status, dose_amount, notes, logged_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dose_log.id, dose_log.prescription_id,
                dose_log.scheduled_time.isoformat(),
                dose_log.actual_time.isoformat() if dose_log.actual_time else None,
                dose_log.status.value, dose_log.dose_amount,
                dose_log.notes, dose_log.logged_by,
                dose_log.created_at.isoformat()
            ))
        return dose_log

    def get_dose_logs_by_prescription(self, prescription_id: str,
                                       start_date: Optional[date] = None,
                                       end_date: Optional[date] = None) -> list[DoseLog]:
        with self._conn() as conn:
            query = "SELECT * FROM dose_logs WHERE prescription_id = ?"
            params = [prescription_id]
            if start_date:
                query += " AND date(scheduled_time) >= ?"
                params.append(start_date.isoformat())
            if end_date:
                query += " AND date(scheduled_time) <= ?"
                params.append(end_date.isoformat())
            query += " ORDER BY scheduled_time"
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_dose_log(r) for r in rows]

    def get_recent_dose_logs(self, patient_id: str, days: int = 30) -> list[DoseLog]:
        """Get dose logs for all of a patient's prescriptions in the last N days."""
        from datetime import timedelta
        start = (date.today() - timedelta(days=days)).isoformat()
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT dl.* FROM dose_logs dl
                JOIN prescriptions p ON dl.prescription_id = p.id
                WHERE p.patient_id = ? AND date(dl.scheduled_time) >= ?
                ORDER BY dl.scheduled_time DESC
            """, (patient_id, start)).fetchall()
            return [self._row_to_dose_log(r) for r in rows]

    # --- Dose confirmation tokens ---
    def create_dose_token(self, token: DoseToken) -> DoseToken:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO dose_confirmation_tokens
                    (token, patient_id, prescription_id, scheduled_time, expires_at,
                     used, pending, used_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                token.token, token.patient_id, token.prescription_id,
                token.scheduled_time.isoformat(),
                token.expires_at.isoformat(),
                int(token.used), int(token.pending),
                token.used_at.isoformat() if token.used_at else None,
                token.created_at.isoformat(),
            ))
        return token

    def get_dose_token(self, token: str) -> Optional[DoseToken]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM dose_confirmation_tokens WHERE token = ?", (token,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_dose_token(row)

    def get_pending_token_by_patient(self, patient_id: str) -> Optional[DoseToken]:
        """Most recent pending, unused, unexpired token for a patient (SMS reply matching)."""
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            row = conn.execute("""
                SELECT * FROM dose_confirmation_tokens
                WHERE patient_id = ? AND pending = 1 AND used = 0 AND expires_at > ?
                ORDER BY created_at DESC LIMIT 1
            """, (patient_id, now)).fetchone()
            if not row:
                return None
            return self._row_to_dose_token(row)

    def token_exists_for_slot(self, prescription_id: str, scheduled_time: datetime) -> bool:
        """True if a pending, unused token exists for this dose slot."""
        with self._conn() as conn:
            row = conn.execute("""
                SELECT 1 FROM dose_confirmation_tokens
                WHERE prescription_id = ? AND scheduled_time = ? AND pending = 1 AND used = 0
                LIMIT 1
            """, (prescription_id, scheduled_time.isoformat())).fetchone()
            return row is not None

    def mark_token_used(self, token: str) -> bool:
        with self._conn() as conn:
            cursor = conn.execute("""
                UPDATE dose_confirmation_tokens
                SET used = 1, pending = 0, used_at = ?
                WHERE token = ? AND used = 0
            """, (datetime.utcnow().isoformat(), token))
            return cursor.rowcount > 0

    def expire_pending_tokens(self, patient_id: str) -> int:
        """Mark all expired pending tokens as not-pending. Returns count cleared."""
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            cursor = conn.execute("""
                UPDATE dose_confirmation_tokens
                SET pending = 0
                WHERE patient_id = ? AND pending = 1 AND used = 0 AND expires_at <= ?
            """, (patient_id, now))
            return cursor.rowcount

    def _row_to_dose_token(self, row) -> DoseToken:
        return DoseToken(
            token=row["token"],
            patient_id=row["patient_id"],
            prescription_id=row["prescription_id"],
            scheduled_time=datetime.fromisoformat(row["scheduled_time"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            used=bool(row["used"]),
            pending=bool(row["pending"]),
            used_at=datetime.fromisoformat(row["used_at"]) if row["used_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # --- Alert ---
    def create_alert(self, alert: Alert) -> Alert:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO alerts (id, patient_id, alert_type, severity, title, message,
                                  related_prescription_ids, related_refill_ids,
                                  is_read, is_action_taken, action_taken, created_at, read_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                alert.id, alert.patient_id, alert.alert_type.value, alert.severity.value,
                alert.title, alert.message,
                json.dumps(alert.related_prescription_ids),
                json.dumps(alert.related_refill_ids),
                int(alert.is_read), int(alert.is_action_taken),
                alert.action_taken, alert.created_at.isoformat(),
                alert.read_at.isoformat() if alert.read_at else None
            ))
        return alert

    def get_alert(self, alert_id: str) -> Optional[Alert]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
            return self._row_to_alert(row) if row else None

    def get_alerts_by_patient(self, patient_id: str, unread_only: bool = False) -> list[Alert]:
        with self._conn() as conn:
            query = "SELECT * FROM alerts WHERE patient_id = ?"
            params = [patient_id]
            if unread_only:
                query += " AND is_read = 0"
            query += " ORDER BY created_at DESC"
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_alert(r) for r in rows]

    def mark_alert_read(self, alert_id: str) -> bool:
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE alerts SET is_read = 1, read_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), alert_id)
            )
            return cursor.rowcount > 0

    def mark_alert_action_taken(self, alert_id: str, action: str) -> bool:
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE alerts SET is_action_taken = 1, action_taken = ? WHERE id = ?",
                (action, alert_id)
            )
            return cursor.rowcount > 0

    # --- Row conversion helpers ---
    def _row_to_caregiver(self, row) -> Caregiver:
        return Caregiver(
            id=row["id"], name=row["name"], email=row["email"],
            phone=row["phone"], timezone=row["timezone"],
            created_at=datetime.fromisoformat(row["created_at"])
        )

    def _row_to_patient(self, row) -> Patient:
        return Patient(
            id=row["id"], caregiver_id=row["caregiver_id"], name=row["name"],
            date_of_birth=date.fromisoformat(row["date_of_birth"]),
            notes=row["notes"],
            phone=row["phone"] if "phone" in row.keys() else None,
            email=row["email"] if "email" in row.keys() else None,
            telegram_chat_id=row["telegram_chat_id"] if "telegram_chat_id" in row.keys() else None,
            created_at=datetime.fromisoformat(row["created_at"])
        )

    def _row_to_doctor(self, row) -> Doctor:
        return Doctor(
            id=row["id"], name=row["name"], specialty=row["specialty"],
            practice_name=row["practice_name"], phone=row["phone"],
            fax=row["fax"], email=row["email"], address=row["address"],
            notes=row["notes"], created_at=datetime.fromisoformat(row["created_at"])
        )

    def _row_to_pharmacy(self, row) -> Pharmacy:
        return Pharmacy(
            id=row["id"], patient_id=row["patient_id"], name=row["name"],
            phone=row["phone"], address=row["address"], fax=row["fax"],
            email=row["email"], hours=row["hours"],
            is_preferred=bool(row["is_preferred"]),
            created_at=datetime.fromisoformat(row["created_at"])
        )

    def _row_to_prescription(self, row) -> Prescription:
        return Prescription(
            id=row["id"], patient_id=row["patient_id"], doctor_id=row["doctor_id"],
            pharmacy_id=row["pharmacy_id"], medication_name=row["medication_name"],
            generic_name=row["generic_name"], strength=row["strength"],
            form=row["form"], route=row["route"], dose_amount=row["dose_amount"],
            dose_unit=row["dose_unit"], frequency=Frequency(row["frequency"]),
            frequency_hours=row["frequency_hours"], instructions=row["instructions"],
            refill_cycle_days=row["refill_cycle_days"],
            refills_remaining=row["refills_remaining"],
            total_refills_allowed=row["total_refills_allowed"],
            last_filled_date=date.fromisoformat(row["last_filled_date"]) if row["last_filled_date"] else None,
            next_refill_due=date.fromisoformat(row["next_refill_due"]) if row["next_refill_due"] else None,
            prescription_start_date=date.fromisoformat(row["prescription_start_date"]),
            prescription_end_date=date.fromisoformat(row["prescription_end_date"]) if row["prescription_end_date"] else None,
            is_active=bool(row["is_active"]),
            discontinued_date=date.fromisoformat(row["discontinued_date"]) if row["discontinued_date"] else None,
            discontinuation_reason=row["discontinuation_reason"],
            ndc_code=row["ndc_code"], rxnorm_cui=row["rxnorm_cui"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"])
        )

    def _row_to_refill(self, row) -> Refill:
        return Refill(
            id=row["id"], prescription_id=row["prescription_id"],
            requested_date=date.fromisoformat(row["requested_date"]),
            status=RefillStatus(row["status"]),
            filled_date=date.fromisoformat(row["filled_date"]) if row["filled_date"] else None,
            picked_up_date=date.fromisoformat(row["picked_up_date"]) if row["picked_up_date"] else None,
            pharmacy_id=row["pharmacy_id"], quantity=row["quantity"],
            days_supply=row["days_supply"], notes=row["notes"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"])
        )

    def _row_to_dose_log(self, row) -> DoseLog:
        return DoseLog(
            id=row["id"], prescription_id=row["prescription_id"],
            scheduled_time=datetime.fromisoformat(row["scheduled_time"]),
            actual_time=datetime.fromisoformat(row["actual_time"]) if row["actual_time"] else None,
            status=DoseStatus(row["status"]), dose_amount=row["dose_amount"],
            notes=row["notes"], logged_by=row["logged_by"],
            created_at=datetime.fromisoformat(row["created_at"])
        )

    def _row_to_alert(self, row) -> Alert:
        return Alert(
            id=row["id"], patient_id=row["patient_id"],
            alert_type=AlertType(row["alert_type"]),
            severity=AlertSeverity(row["severity"]),
            title=row["title"], message=row["message"],
            related_prescription_ids=json.loads(row["related_prescription_ids"] or "[]"),
            related_refill_ids=json.loads(row["related_refill_ids"] or "[]"),
            is_read=bool(row["is_read"]), is_action_taken=bool(row["is_action_taken"]),
            action_taken=row["action_taken"],
            created_at=datetime.fromisoformat(row["created_at"]),
            read_at=datetime.fromisoformat(row["read_at"]) if row["read_at"] else None
        )

    def update_pharmacy(self, pharmacy: Pharmacy) -> Pharmacy:
        with self._conn() as conn:
            conn.execute("""
                UPDATE pharmacies SET
                    patient_id = ?, name = ?, phone = ?, address = ?,
                    fax = ?, email = ?, hours = ?, is_preferred = ?
                WHERE id = ?
            """, (
                pharmacy.patient_id, pharmacy.name, pharmacy.phone,
                pharmacy.address, pharmacy.fax, pharmacy.email,
                pharmacy.hours, int(pharmacy.is_preferred), pharmacy.id
            ))
        return pharmacy

    # --- DELETE methods ---

    def delete_patient(self, patient_id: str) -> bool:
        """Cascade delete patient and all related data."""
        with self._conn() as conn:
            # Get all prescriptions for this patient
            prescriptions = conn.execute("SELECT id FROM prescriptions WHERE patient_id = ?", (patient_id,)).fetchall()
            prescription_ids = [row["id"] for row in prescriptions]
            
            for rx_id in prescription_ids:
                # Delete dose_logs
                conn.execute("DELETE FROM dose_logs WHERE prescription_id = ?", (rx_id,))
                # Delete refills
                conn.execute("DELETE FROM refills WHERE prescription_id = ?", (rx_id,))
            # Delete prescriptions
            conn.execute("DELETE FROM prescriptions WHERE patient_id = ?", (patient_id,))
            # Delete alerts for this patient
            conn.execute("DELETE FROM alerts WHERE patient_id = ?", (patient_id,))
            # Delete dose confirmation tokens
            conn.execute("DELETE FROM dose_confirmation_tokens WHERE patient_id = ?", (patient_id,))
            # Delete telegram linking codes
            conn.execute("DELETE FROM telegram_linking_codes WHERE patient_id = ?", (patient_id,))
            # Delete pharmacies for this patient
            conn.execute("DELETE FROM pharmacies WHERE patient_id = ?", (patient_id,))
            # Finally delete the patient
            cursor = conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
            return cursor.rowcount > 0

    def delete_prescription(self, prescription_id: str) -> bool:
        """Cascade delete prescription and related refills/dose_logs."""
        with self._conn() as conn:
            # Delete dose_logs
            conn.execute("DELETE FROM dose_logs WHERE prescription_id = ?", (prescription_id,))
            # Delete refills
            conn.execute("DELETE FROM refills WHERE prescription_id = ?", (prescription_id,))
            # Delete alerts related to this prescription
            conn.execute("DELETE FROM alerts WHERE related_prescription_ids LIKE ?", (f'%"{prescription_id}"%',))
            # Delete the prescription
            cursor = conn.execute("DELETE FROM prescriptions WHERE id = ?", (prescription_id,))
            return cursor.rowcount > 0

    def delete_doctor(self, doctor_id: str) -> tuple[bool, str]:
        """Delete doctor if no active prescriptions reference it."""
        with self._conn() as conn:
            # Check for active prescriptions
            active_rx = conn.execute(
                "SELECT COUNT(*) as count FROM prescriptions WHERE doctor_id = ? AND is_active = 1", 
                (doctor_id,)
            ).fetchone()
            
            if active_rx and active_rx["count"] > 0:
                return False, f"Cannot delete — {active_rx['count']} active prescription(s) reference this doctor"
            
            cursor = conn.execute("DELETE FROM doctors WHERE id = ?", (doctor_id,))
            return cursor.rowcount > 0, ""

    def delete_pharmacy(self, pharmacy_id: str) -> tuple[bool, str]:
        """Delete pharmacy if no active prescriptions reference it."""
        with self._conn() as conn:
            # Check for active prescriptions
            active_rx = conn.execute(
                "SELECT COUNT(*) as count FROM prescriptions WHERE pharmacy_id = ? AND is_active = 1", 
                (pharmacy_id,)
            ).fetchone()
            
            if active_rx and active_rx["count"] > 0:
                return False, f"Cannot delete — {active_rx['count']} active prescription(s) reference this pharmacy"
            
            cursor = conn.execute("DELETE FROM pharmacies WHERE id = ?", (pharmacy_id,))
            return cursor.rowcount > 0, ""


# Singleton instance
_repository: Optional[Repository] = None


def get_repository() -> Repository:
    """Get the singleton repository instance."""
    global _repository
    if _repository is None:
        _repository = Repository()
    return _repository