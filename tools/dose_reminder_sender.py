"""Dose Reminder Sender Tool — sends Telegram reminders.

Sends an outbound Telegram message to the PATIENT at each scheduled dose
time. The patient replies YES or NO directly — no links, no dashboard, no app.
Each token is scoped to one patient + one prescription + one scheduled dose
time, expires after 6 hours, and is invalidated on reply.

Requires TELEGRAM_BOT_TOKEN in .env. During development, use ngrok to expose
a public webhook URL for Telegram inbound message delivery.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError
from dotenv import load_dotenv
from strands import tool

from data.repository import get_repository
from data.models import DoseToken, Frequency

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def _send_telegram(chat_id: int, text: str) -> tuple[bool, Optional[str]]:
    """Send a Telegram message via Bot API. Returns (success, error_msg)."""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("12345"):
        return False, "Telegram bot token not configured — set TELEGRAM_BOT_TOKEN in .env"
    try:
        payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
        req = Request(
            f"{TELEGRAM_API}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data.get("ok"):
                return True, None
            return False, data.get("description", "Unknown Telegram API error")
    except URLError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)


def telegram_reply(chat_id: int, text: str) -> bool:
    """Send a Telegram reply. Used by the webhook handler for confirmations."""
    success, _ = _send_telegram(chat_id, text)
    return success


# Default dose times per frequency (local time, 24h HH:MM).
# WEEKLY and PRN have no fixed daily schedule and are skipped.
DOSE_TIMES = {
    Frequency.DAILY: ["08:00"],
    Frequency.BID: ["08:00", "20:00"],
    Frequency.TID: ["08:00", "13:00", "21:00"],
    Frequency.QID: ["08:00", "13:00", "18:00", "22:00"],
}


def dose_times_for_day(frequency: Frequency, day) -> list[datetime]:
    """Scheduled datetimes for one calendar day, or [] if unschedulable."""
    times = DOSE_TIMES.get(frequency)
    if not times:
        return []
    result = []
    for t in times:
        hour, minute = map(int, t.split(":"))
        result.append(datetime(day.year, day.month, day.day, hour, minute))
    return result


@tool
def send_dose_reminder(prescription_id: str, scheduled_time: Optional[str] = None) -> dict[str, Any]:
    """
    Send a Telegram dose reminder to the patient for one scheduled dose.

    Creates a pending confirmation token scoped to this patient + prescription
    + scheduled time (expires 6 hours after), then sends a Telegram message
    with instructions to reply YES or NO.

    One pending reminder per patient: if the patient already has a pending
    reminder for a different prescription, this call is skipped.

    Args:
        prescription_id: The prescription ID.
        scheduled_time: ISO datetime of the scheduled dose.
            Defaults to today at the prescription's first dose time.

    Returns:
        Dict with success status, details, and any Telegram error.
    """
    repo = get_repository()

    rx = repo.get_prescription(prescription_id)
    if not rx:
        return {"success": False, "error": f"Prescription {prescription_id} not found", "telegram_error": None}
    if not rx.is_active:
        return {"success": False, "error": f"Prescription {prescription_id} is not active", "telegram_error": None}

    patient = repo.get_patient(rx.patient_id)
    if not patient:
        return {"success": False, "error": f"Patient for prescription {prescription_id} not found", "telegram_error": None}
    if not patient.telegram_chat_id:
        return {
            "success": False,
            "error": f"No Telegram linked for patient {patient.name} — cannot send reminder",
            "telegram_error": None,
        }

    # Clean up any expired pending tokens for this patient first.
    repo.expire_pending_tokens(patient.id)

    # One pending reminder per patient — skip if one already exists.
    existing_pending = repo.get_pending_token_by_patient(patient.id)
    if existing_pending:
        return {
            "success": False,
            "error": "Patient already has a pending reminder — skipping",
            "prescription_id": rx.id,
            "patient_id": patient.id,
            "existing_pending_token": existing_pending.token,
            "telegram_error": None,
        }

    if scheduled_time:
        try:
            scheduled = datetime.fromisoformat(scheduled_time)
        except ValueError:
            return {"success": False, "error": f"Invalid scheduled_time: {scheduled_time}", "patient_id": patient.id, "telegram_error": None}
    else:
        times = dose_times_for_day(rx.frequency, datetime.now().date())
        if not times:
            return {
                "success": False,
                "error": f"Frequency {rx.frequency.value} has no fixed daily schedule",
                "patient_id": patient.id,
                "telegram_error": None,
            }
        scheduled = times[0]

    token = DoseToken(
        patient_id=patient.id,
        prescription_id=rx.id,
        scheduled_time=scheduled,
        expires_at=scheduled + timedelta(hours=DoseToken.TOKEN_VALIDITY_HOURS),
    )
    repo.create_dose_token(token)

    when = scheduled.strftime("%I:%M %p").lstrip("0")
    message_body = (
        f"CareCue: Time for your {rx.medication_name} {rx.strength} ({when}). "
        f"Reply YES if taken, NO if not."
    )
    success, error_msg = _send_telegram(patient.telegram_chat_id, message_body)

    return {
        "success": success,
        "prescription_id": rx.id,
        "patient_id": patient.id,
        "patient_name": patient.name,
        "medication_name": rx.medication_name,
        "strength": rx.strength,
        "scheduled_time": scheduled.isoformat(),
        "token": token.token,
        "telegram_error": error_msg,
    }


@tool
def send_due_dose_reminders(now: Optional[str] = None, window_minutes: int = 30) -> dict[str, Any]:
    """
    Send Telegram reminders for every dose due within the check window.

    Intended to run on a frequent schedule (e.g. hourly). For each active
    prescription with a fixed daily frequency, any dose time that has passed
    within the last `window_minutes` gets exactly one reminder — re-runs are
    safe because pending tokens are skipped.

    One pending reminder per patient: if a patient already has a pending
    reminder (for any prescription), all other due reminders for that patient
    are skipped.

    Args:
        now: ISO datetime to check against (defaults to current time).
        window_minutes: How far back from `now` a dose may be and still trigger.

    Returns:
        Dict summary of the run.
    """
    repo = get_repository()
    check_time = datetime.fromisoformat(now) if now else datetime.now()
    window_start = check_time - timedelta(minutes=window_minutes)

    sent = []
    skipped_pending = []
    skipped_no_schedule = []
    errors = []
    patients_checked = 0

    for caregiver in repo.list_caregivers():
        for patient in repo.get_patients_by_caregiver(caregiver.id):
            patients_checked += 1

            # Expire stale tokens for this patient before checking.
            repo.expire_pending_tokens(patient.id)

            # One pending reminder per patient — skip all if one exists.
            if repo.get_pending_token_by_patient(patient.id):
                skipped_pending.append({
                    "patient_id": patient.id,
                    "patient_name": patient.name,
                    "reason": "patient already has a pending reminder",
                })
                continue

            for rx in repo.get_prescriptions_by_patient(patient.id, active_only=True):
                for scheduled in dose_times_for_day(rx.frequency, check_time.date()):
                    if not (window_start <= scheduled <= check_time):
                        continue
                    result = send_dose_reminder(rx.id, scheduled.isoformat())
                    if result["success"]:
                        sent.append({
                            "prescription_id": rx.id,
                            "patient_id": patient.id,
                            "medication_name": rx.medication_name,
                            "scheduled_time": scheduled.isoformat(),
                        })
                        break  # Sent one for this patient — stop iterating prescriptions.
                    elif "already has a pending" in result.get("error", ""):
                        skipped_pending.append({
                            "patient_id": patient.id,
                            "patient_name": patient.name,
                            "prescription_id": rx.id,
                            "reason": result["error"],
                        })
                        break
                    elif "no fixed daily schedule" in result.get("error", ""):
                        skipped_no_schedule.append({
                            "prescription_id": rx.id,
                            "medication_name": rx.medication_name,
                        })
                    else:
                        errors.append({
                            "prescription_id": rx.id,
                            "medication_name": rx.medication_name,
                            "error": result.get("error"),
                        })

    return {
        "checked_at": check_time.isoformat(),
        "window_minutes": window_minutes,
        "patients_checked": patients_checked,
        "reminders_sent": len(sent),
        "sent": sent,
        "skipped_pending": skipped_pending,
        "skipped_no_schedule": skipped_no_schedule,
        "errors": errors,
    }
