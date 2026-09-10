"""CareCue FastAPI Backend - REST API for the UI."""

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import date, datetime
from pathlib import Path
import sys
import logging
import secrets

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.repository import get_repository
from data.models import (
    Caregiver, Patient, Doctor, Pharmacy, Prescription,
    Frequency, RefillStatus, DoseLog, DoseStatus
)
from tools.conflict_checker import conflict_checker
from tools.dose_pattern_checker import dose_pattern_checker


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="CareCue API", version="1.0.0")

# Global exception handler for clean error responses
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

# Serve static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

repo = get_repository()


# --- Pydantic Models for API ---

class CaregiverCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=30)
    timezone: str = Field("UTC", max_length=50)

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty")
        return v


class CaregiverResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: Optional[str]
    timezone: str
    created_at: str

    class Config:
        from_attributes = True


class PatientCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    date_of_birth: date
    notes: Optional[str] = Field(None, max_length=1000)
    phone: Optional[str] = Field(None, max_length=30)

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Patient name cannot be empty")
        return v


class PatientResponse(BaseModel):
    id: str
    caregiver_id: str
    name: str
    date_of_birth: date
    notes: Optional[str]
    phone: Optional[str] = None
    email: Optional[str] = None
    telegram_chat_id: Optional[int] = None
    age: int
    created_at: str

    class Config:
        from_attributes = True


class DoctorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    specialty: Optional[str] = Field(None, max_length=100)
    practice_name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=30)
    fax: Optional[str] = Field(None, max_length=30)
    email: Optional[EmailStr] = None
    address: Optional[str] = Field(None, max_length=300)
    notes: Optional[str] = Field(None, max_length=1000)

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Doctor name cannot be empty")
        return v


class DoctorResponse(BaseModel):
    id: str
    name: str
    specialty: Optional[str]
    practice_name: Optional[str]
    phone: Optional[str]
    fax: Optional[str]
    email: Optional[str]
    address: Optional[str]
    notes: Optional[str]
    created_at: str
    prescription_count: int = 0

    class Config:
        from_attributes = True


class PharmacyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    phone: str = Field(..., max_length=30)
    address: Optional[str] = Field(None, max_length=300)
    fax: Optional[str] = Field(None, max_length=30)
    email: Optional[EmailStr] = None
    hours: Optional[str] = Field(None, max_length=200)
    is_preferred: bool = True

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Pharmacy name cannot be empty")
        return v

    @field_validator("phone")
    @classmethod
    def phone_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Pharmacy phone cannot be empty")
        return v


class PharmacyResponse(BaseModel):
    id: str
    patient_id: str
    name: str
    phone: str
    address: Optional[str]
    fax: Optional[str]
    email: Optional[str]
    hours: Optional[str]
    is_preferred: bool
    created_at: str

    class Config:
        from_attributes = True


class PrescriptionCreate(BaseModel):
    doctor_id: str = Field(..., min_length=1)
    pharmacy_id: str = Field(..., min_length=1)
    medication_name: str = Field(..., min_length=1, max_length=200)
    generic_name: Optional[str] = Field(None, max_length=200)
    strength: str = Field(..., min_length=1, max_length=50)
    form: Optional[str] = Field(None, max_length=50)
    route: Optional[str] = Field(None, max_length=50)
    dose_amount: float = Field(..., gt=0)
    dose_unit: str = Field(..., min_length=1, max_length=30)
    frequency: Frequency
    frequency_hours: Optional[int] = Field(None, ge=1, le=24)
    instructions: Optional[str] = Field(None, max_length=500)
    refill_cycle_days: int = Field(..., ge=1, le=365)
    refills_remaining: int = Field(0, ge=0)
    total_refills_allowed: int = Field(0, ge=0)
    last_filled_date: date
    prescription_start_date: date
    ndc_code: Optional[str] = Field(None, max_length=50)
    rxnorm_cui: Optional[str] = Field(None, max_length=50)

    @field_validator("medication_name", "strength", "dose_unit")
    @classmethod
    def not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Field cannot be empty")
        return v


class PrescriptionResponse(BaseModel):
    id: str
    patient_id: str
    doctor_id: str
    pharmacy_id: Optional[str]
    medication_name: str
    generic_name: Optional[str]
    strength: str
    form: Optional[str]
    route: Optional[str]
    dose_amount: float
    dose_unit: str
    frequency: str
    frequency_hours: Optional[int]
    instructions: Optional[str]
    refill_cycle_days: int
    refills_remaining: int
    total_refills_allowed: int
    last_filled_date: Optional[date]
    next_refill_due: Optional[date]
    prescription_start_date: date
    prescription_end_date: Optional[date]
    is_active: bool
    days_until_refill: Optional[int]
    is_refill_due_soon: bool
    is_refill_overdue: bool
    ndc_code: Optional[str]
    rxnorm_cui: Optional[str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class DashboardSummary(BaseModel):
    total_overdue: int
    total_due_soon: int
    total_conflicts: int
    total_low_adherence: int
    patients: List[dict]


# --- Helper Functions ---

def caregiver_to_dict(c: Caregiver) -> dict:
    return {
        "id": c.id, "name": c.name, "email": c.email,
        "phone": c.phone, "timezone": c.timezone,
        "created_at": c.created_at.isoformat()
    }


def patient_to_dict(p: Patient) -> dict:
    return {
        "id": p.id, "caregiver_id": p.caregiver_id, "name": p.name,
        "date_of_birth": p.date_of_birth.isoformat(),
        "notes": p.notes,
        "phone": p.phone,
        "email": str(p.email) if p.email else None,
        "telegram_chat_id": p.telegram_chat_id,
        "age": p.age,
        "created_at": p.created_at.isoformat()
    }


def doctor_to_dict(d: Doctor, prescription_count: int = 0) -> dict:
    return {
        "id": d.id, "name": d.name, "specialty": d.specialty,
        "practice_name": d.practice_name, "phone": d.phone,
        "fax": d.fax, "email": d.email, "address": d.address,
        "notes": d.notes, "created_at": d.created_at.isoformat(),
        "prescription_count": prescription_count
    }


def pharmacy_to_dict(p: Pharmacy) -> dict:
    return {
        "id": p.id, "patient_id": p.patient_id, "name": p.name,
        "phone": p.phone, "address": p.address, "fax": p.fax,
        "email": p.email, "hours": p.hours, "is_preferred": p.is_preferred,
        "created_at": p.created_at.isoformat()
    }


def prescription_to_dict(rx: Prescription) -> dict:
    return {
        "id": rx.id, "patient_id": rx.patient_id, "doctor_id": rx.doctor_id,
        "pharmacy_id": rx.pharmacy_id, "medication_name": rx.medication_name,
        "generic_name": rx.generic_name, "strength": rx.strength,
        "form": rx.form, "route": rx.route, "dose_amount": rx.dose_amount,
        "dose_unit": rx.dose_unit, "frequency": rx.frequency.value,
        "frequency_hours": rx.frequency_hours, "instructions": rx.instructions,
        "refill_cycle_days": rx.refill_cycle_days,
        "refills_remaining": rx.refills_remaining,
        "total_refills_allowed": rx.total_refills_allowed,
        "last_filled_date": rx.last_filled_date.isoformat() if rx.last_filled_date else None,
        "next_refill_due": rx.next_refill_due.isoformat() if rx.next_refill_due else None,
        "prescription_start_date": rx.prescription_start_date.isoformat(),
        "prescription_end_date": rx.prescription_end_date.isoformat() if rx.prescription_end_date else None,
        "is_active": rx.is_active,
        "days_until_refill": rx.days_until_refill,
        "is_refill_due_soon": rx.is_refill_due_soon(),
        "is_refill_overdue": rx.is_refill_overdue,
        "ndc_code": rx.ndc_code, "rxnorm_cui": rx.rxnorm_cui,
        "created_at": rx.created_at.isoformat(),
        "updated_at": rx.updated_at.isoformat()
    }


# --- API Endpoints ---

@app.get("/")
async def root():
    return FileResponse(static_dir / "index.html")


# Caregivers
@app.get("/api/caregivers", response_model=List[CaregiverResponse])
async def list_caregivers():
    caregivers = repo.list_caregivers()
    return [caregiver_to_dict(c) for c in caregivers]


@app.post("/api/caregivers", response_model=CaregiverResponse)
async def create_caregiver(data: CaregiverCreate):
    existing = repo.get_caregiver_by_email(data.email)
    if existing:
        return caregiver_to_dict(existing)
    caregiver = Caregiver(
        name=data.name, email=data.email, phone=data.phone, timezone=data.timezone
    )
    repo.create_caregiver(caregiver)
    return caregiver_to_dict(caregiver)


# Patients
@app.get("/api/patients", response_model=List[PatientResponse])
async def list_patients(caregiver_id: str):
    patients = repo.get_patients_by_caregiver(caregiver_id)
    return [patient_to_dict(p) for p in patients]


@app.post("/api/patients", response_model=PatientResponse)
async def create_patient(caregiver_id: str, data: PatientCreate):
    patient = Patient(
        caregiver_id=caregiver_id,
        name=data.name,
        date_of_birth=data.date_of_birth,
        notes=data.notes,
        phone=data.phone,
    )
    repo.create_patient(patient)
    return patient_to_dict(patient)


@app.get("/api/patients/{patient_id}", response_model=PatientResponse)
async def get_patient(patient_id: str):
    patient = repo.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient_to_dict(patient)


# Doctors
@app.get("/api/doctors", response_model=List[DoctorResponse])
async def list_doctors():
    doctors = repo.list_doctors()
    return [
        doctor_to_dict(d, len(repo.get_prescriptions_by_doctor(d.id)))
        for d in doctors
    ]


@app.post("/api/doctors", response_model=DoctorResponse)
async def create_doctor(data: DoctorCreate):
    doctor = Doctor(
        name=data.name, specialty=data.specialty, practice_name=data.practice_name,
        phone=data.phone, fax=data.fax, email=data.email,
        address=data.address, notes=data.notes
    )
    repo.create_doctor(doctor)
    return doctor_to_dict(doctor)


# Pharmacies
@app.get("/api/pharmacies", response_model=List[PharmacyResponse])
async def list_pharmacies(patient_id: str):
    pharmacies = repo.get_pharmacies_by_patient(patient_id)
    return [pharmacy_to_dict(p) for p in pharmacies]


@app.post("/api/pharmacies", response_model=PharmacyResponse)
async def create_pharmacy(patient_id: str, data: PharmacyCreate):
    pharmacy = Pharmacy(
        patient_id=patient_id, name=data.name, phone=data.phone,
        address=data.address, fax=data.fax, email=data.email,
        hours=data.hours, is_preferred=data.is_preferred
    )
    repo.create_pharmacy(pharmacy)
    return pharmacy_to_dict(pharmacy)


@app.patch("/api/pharmacies/{pharmacy_id}")
async def update_pharmacy(pharmacy_id: str, data: dict):
    pharmacy = repo.get_pharmacy(pharmacy_id)
    if not pharmacy:
        raise HTTPException(status_code=404, detail="Pharmacy not found")
    
    for key, value in data.items():
        if hasattr(pharmacy, key):
            setattr(pharmacy, key, value)
    
    # If setting as preferred, unset others for this patient
    if data.get('is_preferred') is True:
        all_pharmacies = repo.get_pharmacies_by_patient(pharmacy.patient_id)
        for p in all_pharmacies:
            if p.id != pharmacy_id and p.is_preferred:
                p.is_preferred = False
                # Note: Would need update_pharmacy method in repo
    
    # For now, just update the single pharmacy
    # The repo would need an update_pharmacy method
    return pharmacy_to_dict(pharmacy)


@app.delete("/api/pharmacies/{pharmacy_id}", status_code=204)
async def delete_pharmacy(pharmacy_id: str):
    pharmacy = repo.get_pharmacy(pharmacy_id)
    if not pharmacy:
        raise HTTPException(status_code=404, detail="Pharmacy not found")
    
    success, message = repo.delete_pharmacy(pharmacy_id)
    if not success:
        raise HTTPException(status_code=409, detail=message)


@app.delete("/api/doctors/{doctor_id}", status_code=204)
async def delete_doctor(doctor_id: str):
    doctor = repo.get_doctor(doctor_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    
    success, message = repo.delete_doctor(doctor_id)
    if not success:
        raise HTTPException(status_code=409, detail=message)


@app.delete("/api/prescriptions/{prescription_id}", status_code=204)
async def delete_prescription(prescription_id: str):
    rx = repo.get_prescription(prescription_id)
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")
    
    success = repo.delete_prescription(prescription_id)
    if not success:
        raise HTTPException(status_code=404, detail="Prescription not found")


@app.delete("/api/patients/{patient_id}", status_code=204)
async def delete_patient(patient_id: str):
    patient = repo.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    success = repo.delete_patient(patient_id)
    if not success:
        raise HTTPException(status_code=404, detail="Patient not found")


# Prescriptions
@app.get("/api/prescriptions", response_model=List[PrescriptionResponse])
async def list_prescriptions(patient_id: str, active_only: bool = True):
    prescriptions = repo.get_prescriptions_by_patient(patient_id, active_only)
    return [prescription_to_dict(rx) for rx in prescriptions]


@app.get("/api/medications")
async def list_all_medications(caregiver_id: str, active_only: bool = True):
    """All prescriptions across all of a caregiver's patients, joined with patient + doctor names."""
    result = []
    for patient in repo.get_patients_by_caregiver(caregiver_id):
        for rx in repo.get_prescriptions_by_patient(patient.id, active_only):
            doctor = repo.get_doctor(rx.doctor_id)
            item = prescription_to_dict(rx)
            item["patient_id"] = patient.id
            item["patient_name"] = patient.name
            item["doctor_name"] = doctor.name if doctor else "Unknown doctor"
            result.append(item)
    return result


@app.post("/api/prescriptions", response_model=PrescriptionResponse)
async def create_prescription(patient_id: str, data: PrescriptionCreate):
    # Calculate next_refill_due
    from datetime import timedelta
    next_refill = data.last_filled_date + timedelta(days=data.refill_cycle_days)
    
    prescription = Prescription(
        patient_id=patient_id,
        doctor_id=data.doctor_id,
        pharmacy_id=data.pharmacy_id,
        medication_name=data.medication_name,
        generic_name=data.generic_name,
        strength=data.strength,
        form=data.form,
        route=data.route,
        dose_amount=data.dose_amount,
        dose_unit=data.dose_unit,
        frequency=data.frequency,
        frequency_hours=data.frequency_hours,
        instructions=data.instructions,
        refill_cycle_days=data.refill_cycle_days,
        refills_remaining=data.refills_remaining,
        total_refills_allowed=data.total_refills_allowed,
        last_filled_date=data.last_filled_date,
        next_refill_due=next_refill,
        prescription_start_date=data.prescription_start_date,
        ndc_code=data.ndc_code,
        rxnorm_cui=data.rxnorm_cui,
    )
    repo.create_prescription(prescription)
    return prescription_to_dict(prescription)


@app.patch("/api/prescriptions/{prescription_id}")
async def update_prescription(prescription_id: str, data: dict):
    rx = repo.get_prescription(prescription_id)
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")
    
    from datetime import date as date_type, timedelta
    from data.models import Frequency
    date_fields = ['last_filled_date', 'prescription_start_date', 'prescription_end_date', 'discontinued_date']
    for key, value in data.items():
        if hasattr(rx, key):
            if key in date_fields and value:
                setattr(rx, key, date_type.fromisoformat(value))
            elif key == 'frequency' and isinstance(value, str):
                setattr(rx, key, Frequency(value))
            else:
                setattr(rx, key, value)
    
    # Recalculate next_refill_due when last_filled_date changes
    if 'last_filled_date' in data and data['last_filled_date'] and rx.last_filled_date and rx.refill_cycle_days:
        rx.next_refill_due = rx.last_filled_date + timedelta(days=rx.refill_cycle_days)
    
    rx.updated_at = datetime.utcnow()
    repo.update_prescription(rx)
    return prescription_to_dict(rx)


# Dashboard
@app.get("/api/dashboard", response_model=DashboardSummary)
async def get_dashboard(caregiver_id: str):
    patients = repo.get_patients_by_caregiver(caregiver_id)
    
    total_overdue = 0
    total_due_soon = 0
    total_conflicts = 0
    total_low_adherence = 0
    patient_data = []
    
    for patient in patients:
        # Refills
        prescriptions = repo.get_prescriptions_by_patient(patient.id)
        patient_overdue = 0
        patient_due = 0
        for rx in prescriptions:
            if rx.is_refill_overdue:
                patient_overdue += 1
                total_overdue += 1
            elif rx.is_refill_due_soon():
                patient_due += 1
                total_due_soon += 1
        
        # Conflicts
        conflict_result = conflict_checker(patient.id)
        patient_conflicts = conflict_result["conflicts_found"]
        total_conflicts += patient_conflicts
        
        # Dose patterns
        pattern_result = dose_pattern_checker(patient.id)
        patient_adherence = pattern_result.get("adherence_rate")
        # Only count as low adherence if we have actual data
        if patient_adherence is not None and patient_adherence < 80:
            total_low_adherence += 1
        
        patient_data.append({
            "patient": patient_to_dict(patient),
            "overdue_count": patient_overdue,
            "due_soon_count": patient_due,
            "conflicts_count": patient_conflicts,
            "conflicts": conflict_result["conflicts"],
            "adherence": patient_adherence,
            "missed_streaks": pattern_result.get("missed_streaks", []),
            "prescriptions": [prescription_to_dict(rx) for rx in prescriptions]
        })
    
    return DashboardSummary(
        total_overdue=total_overdue,
        total_due_soon=total_due_soon,
        total_conflicts=total_conflicts,
        total_low_adherence=total_low_adherence,
        patients=patient_data
    )


# --- Telegram webhook + patient linking ---

TAKEN_KEYWORDS = {"yes", "y", "taken", "done"}
MISSED_KEYWORDS = {"no", "n", "not yet", "missed"}


@app.post("/api/patients/{patient_id}/telegram-link")
async def generate_telegram_link(patient_id: str):
    """Generate a short linking code for a patient to connect their Telegram."""
    patient = repo.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if patient.telegram_chat_id:
        return {"already_linked": True, "chat_id": patient.telegram_chat_id}
    code = secrets.token_hex(4).upper()  # 8-char hex code like "A1B2C3D4"
    repo.create_linking_code(code, patient_id)
    return {"code": code, "bot_username": "CareCueBot"}


@app.post("/telegram/webhook")
async def telegram_webhook(request_body: dict):
    """
    Telegram inbound webhook.

    Telegram POSTs JSON like:
    {"message": {"chat": {"id": 123456}, "text": "yes", "from": {...}}}

    Handles:
      - /start <CODE> — link patient to this chat_id
      - YES/NO replies — match to pending dose reminder
    """
    repo = get_repository()

    message = request_body.get("message")
    if not message:
        return {"ok": True}

    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()

    if not chat_id or not text:
        return {"ok": True}

    # Handle /start command for patient linking.
    if text.lower().startswith("/start"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return {"ok": True}
        code = parts[1].strip().upper()
        linking = repo.get_linking_code(code)
        if not linking:
            from tools.dose_reminder_sender import telegram_reply
            telegram_reply(chat_id, "Invalid linking code. Please check with your caregiver.")
            return {"ok": True}
        repo.set_patient_telegram_chat_id(linking["patient_id"], chat_id)
        repo.consume_linking_code(code)
        patient = repo.get_patient(linking["patient_id"])
        from tools.dose_reminder_sender import telegram_reply
        telegram_reply(chat_id, f"Linked! You will now receive dose reminders for {patient.name}.")
        return {"ok": True}

    # Handle dose confirmation replies (YES/NO).
    body = text.lower()
    patient = repo.get_patient_by_telegram_chat_id(chat_id)
    if not patient:
        from tools.dose_reminder_sender import telegram_reply
        telegram_reply(chat_id, "No CareCue account linked to this chat. Send /start <CODE> to connect.")
        return {"ok": True}

    if body in TAKEN_KEYWORDS:
        action = "taken"
    elif body in MISSED_KEYWORDS:
        action = "missed"
    else:
        from tools.dose_reminder_sender import telegram_reply
        telegram_reply(chat_id, "Sorry, reply YES or NO.")
        return {"ok": True}

    token = repo.get_pending_token_by_patient(patient.id)
    if not token:
        from tools.dose_reminder_sender import telegram_reply
        telegram_reply(chat_id, "No pending dose reminder found. Please check with your caregiver.")
        return {"ok": True}

    now = datetime.utcnow()
    rx = repo.get_prescription(token.prescription_id)
    if not rx:
        from tools.dose_reminder_sender import telegram_reply
        telegram_reply(chat_id, "Prescription not found. Please check with your caregiver.")
        return {"ok": True}

    log = DoseLog(
        prescription_id=rx.id,
        scheduled_time=token.scheduled_time,
        actual_time=now if action == "taken" else None,
        status=DoseStatus.TAKEN if action == "taken" else DoseStatus.MISSED,
        dose_amount=rx.dose_amount if action == "taken" else None,
        notes="Confirmed by patient via Telegram reply" if action == "taken"
        else "Patient reported dose not taken via Telegram reply",
        logged_by=f"patient:{patient.id}",
    )
    repo.create_dose_log(log)
    repo.mark_token_used(token.token)

    from tools.dose_reminder_sender import telegram_reply
    if action == "taken":
        telegram_reply(chat_id, f"Thank you! Your dose of {rx.medication_name} {rx.strength} has been recorded.")
    else:
        telegram_reply(chat_id, f"Noted — {rx.medication_name} {rx.strength} marked as missed. Take care!")

    return {"ok": True}


# Health check
@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)