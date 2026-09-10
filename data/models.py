"""Pydantic data models for CareCue."""

from datetime import date, datetime
from enum import Enum
from typing import Optional, ClassVar
from pydantic import BaseModel, Field, EmailStr, computed_field


class Frequency(str, Enum):
    DAILY = "daily"
    BID = "bid"
    TID = "tid"
    QID = "qid"
    WEEKLY = "weekly"
    PRN = "prn"


class RefillStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    PICKED_UP = "picked_up"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class DoseStatus(str, Enum):
    TAKEN = "taken"
    MISSED = "missed"
    SKIPPED = "skipped"


class AlertType(str, Enum):
    REFILL_DUE = "refill_due"
    REFILL_OVERDUE = "refill_overdue"
    CONFLICT_DETECTED = "conflict_detected"
    DOSE_PATTERN = "dose_pattern"
    REFILL_DRAFTED = "refill_drafted"
    NO_RESPONSE = "no_response"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    URGENT = "urgent"


# --- ULID helper ---
import secrets
import time
import random

def ulid() -> str:
    """Generate a ULID-like string (time-sortable, 26 chars)."""
    ms = int(time.time() * 1000)
    return f"{ms:013x}{random.randbytes(10).hex()[:13]}".upper()[:26]


# --- Core Entities ---

class Caregiver(BaseModel):
    id: str = Field(default_factory=ulid)
    name: str
    email: EmailStr
    phone: Optional[str] = None
    timezone: str = "UTC"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Patient(BaseModel):
    id: str = Field(default_factory=ulid)
    caregiver_id: str
    name: str
    date_of_birth: date
    notes: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    telegram_chat_id: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @computed_field
    def age(self) -> int:
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )


class Doctor(BaseModel):
    id: str = Field(default_factory=ulid)
    name: str
    specialty: Optional[str] = None
    practice_name: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Pharmacy(BaseModel):
    id: str = Field(default_factory=ulid)
    patient_id: str
    name: str
    phone: str
    address: Optional[str] = None
    fax: Optional[str] = None
    email: Optional[EmailStr] = None
    hours: Optional[str] = None
    is_preferred: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Prescription(BaseModel):
    id: str = Field(default_factory=ulid)
    patient_id: str
    doctor_id: str
    pharmacy_id: Optional[str] = None

    medication_name: str
    generic_name: Optional[str] = None
    strength: str
    form: Optional[str] = None
    route: Optional[str] = None

    dose_amount: float
    dose_unit: str
    frequency: Frequency
    frequency_hours: Optional[int] = None
    instructions: Optional[str] = None

    refill_cycle_days: int
    refills_remaining: int = 0
    total_refills_allowed: int = 0
    last_filled_date: Optional[date] = None
    next_refill_due: Optional[date] = None
    prescription_start_date: date
    prescription_end_date: Optional[date] = None

    is_active: bool = True
    discontinued_date: Optional[date] = None
    discontinuation_reason: Optional[str] = None

    ndc_code: Optional[str] = None
    rxnorm_cui: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    REFILL_DUE_THRESHOLD_DAYS: ClassVar[int] = 7

    @computed_field
    def days_until_refill(self) -> Optional[int]:
        if self.next_refill_due:
            delta = self.next_refill_due - date.today()
            return delta.days
        return None

    def is_refill_due_soon(self, threshold_days: int = REFILL_DUE_THRESHOLD_DAYS) -> bool:
        days = self.days_until_refill
        return days is not None and 0 <= days <= threshold_days

    @computed_field
    def is_refill_overdue(self) -> bool:
        days = self.days_until_refill
        return days is not None and days < 0


class Refill(BaseModel):
    id: str = Field(default_factory=ulid)
    prescription_id: str
    requested_date: date
    status: RefillStatus = RefillStatus.PENDING
    filled_date: Optional[date] = None
    picked_up_date: Optional[date] = None
    pharmacy_id: Optional[str] = None
    quantity: Optional[int] = None
    days_supply: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class DoseLog(BaseModel):
    id: str = Field(default_factory=ulid)
    prescription_id: str
    scheduled_time: datetime
    actual_time: Optional[datetime] = None
    status: DoseStatus = DoseStatus.MISSED
    dose_amount: Optional[float] = None
    notes: Optional[str] = None
    logged_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    ADHERENCE_WINDOW_MINUTES: ClassVar[int] = 60

    def is_on_time(self, window_minutes: int = ADHERENCE_WINDOW_MINUTES) -> bool:
        if self.actual_time and self.status == DoseStatus.TAKEN:
            diff = abs((self.actual_time - self.scheduled_time).total_seconds() / 60)
            return diff <= window_minutes
        return False


class DoseToken(BaseModel):
    """Single-use dose confirmation token for patient SMS reminders.

    Scoped to one patient + one prescription + one scheduled dose time.
    The patient_id field enables SMS reply matching (phone number → patient).
    The pending flag tracks whether a reply is still expected; it is cleared
    when the patient replies or the token expires.
    """
    token: str = Field(default_factory=lambda: secrets.token_urlsafe(24))
    patient_id: str
    prescription_id: str
    scheduled_time: datetime
    expires_at: datetime
    used: bool = False
    pending: bool = True
    no_response_alerted: bool = False
    used_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    TOKEN_VALIDITY_HOURS: ClassVar[int] = 6
    NO_RESPONSE_GRACE_MINUTES: ClassVar[int] = 90


class Alert(BaseModel):
    id: str = Field(default_factory=ulid)
    patient_id: str
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    related_prescription_ids: list[str] = Field(default_factory=list)
    related_refill_ids: list[str] = Field(default_factory=list)
    is_read: bool = False
    is_action_taken: bool = False
    action_taken: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    read_at: Optional[datetime] = None