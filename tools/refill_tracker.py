"""Refill Tracker Tool - Checks refill dates and flags upcoming/overdue prescriptions."""

from datetime import date
from typing import Any
from strands import tool

from data.repository import get_repository
from data.models import Prescription


@tool
def refill_tracker(patient_id: str, days_threshold: int = 7) -> dict[str, Any]:
    """
    Check refill status for all active prescriptions for a patient.
    
    Args:
        patient_id: The patient ID to check refills for
        days_threshold: Days ahead to flag as "due soon" (default: 7)
    
    Returns:
        Dict with 'upcoming', 'overdue', and 'ok' prescription lists
    """
    repo = get_repository()
    
    # Get all active prescriptions for the patient
    # Edge case: patient with zero prescriptions, or only discontinued prescriptions
    prescriptions = repo.get_prescriptions_by_patient(patient_id, active_only=True)
    
    upcoming = []
    overdue = []
    ok = []
    skipped = []  # Track prescriptions we couldn't evaluate
    
    for rx in prescriptions:
        # Edge case: prescription with missing/null next_refill_due or refill_cycle_days
        # days_until_refill returns None if next_refill_due is None
        days = rx.days_until_refill
        
        rx_info = {
            "prescription_id": rx.id,
            "medication_name": rx.medication_name,
            "strength": rx.strength,
            "frequency": rx.frequency.value,
            "next_refill_due": rx.next_refill_due.isoformat() if rx.next_refill_due else None,
            "days_until_refill": days,
            "refills_remaining": rx.refills_remaining,
            "pharmacy_id": rx.pharmacy_id,
        }
        
        if days is None:
            # Edge case: missing next_refill_due (e.g., never filled, or refill_cycle_days not set)
            # Cannot determine refill status, skip from alerting but include in skipped
            rx_info["status"] = "unknown"
            rx_info["reason"] = "Missing next_refill_due date"
            skipped.append(rx_info)
            continue
        
        if days < 0:
            rx_info["status"] = "overdue"
            rx_info["days_overdue"] = abs(days)
            overdue.append(rx_info)
        elif 0 <= days <= days_threshold:
            rx_info["status"] = "due_soon"
            upcoming.append(rx_info)
        else:
            rx_info["status"] = "ok"
            ok.append(rx_info)
    
    return {
        "patient_id": patient_id,
        "checked_at": date.today().isoformat(),
        "threshold_days": days_threshold,
        "summary": {
            "total_active": len(prescriptions),
            "overdue_count": len(overdue),
            "upcoming_count": len(upcoming),
            "ok_count": len(ok),
            "skipped_count": len(skipped),
        },
        "overdue": overdue,
        "upcoming": upcoming,
        "ok": ok,
        "skipped": skipped,
    }


@tool
def get_all_patients_refill_status(days_threshold: int = 7) -> dict[str, Any]:
    """
    Check refill status across ALL patients (for scheduled runs).
    
    Args:
        days_threshold: Days ahead to flag as "due soon" (default: 7)
    
    Returns:
        Dict with per-patient refill status
    """
    repo = get_repository()
    
    # Get all patients
    caregivers = repo.list_caregivers()
    all_results = {}
    
    for caregiver in caregivers:
        patients = repo.get_patients_by_caregiver(caregiver.id)
        for patient in patients:
            result = refill_tracker(patient.id, days_threshold)
            # Only include patients with actual alerts (overdue or due soon)
            # Edge case: don't include patients with only skipped/unknown prescriptions
            has_real_alerts = (
                result["summary"]["overdue_count"] > 0 or 
                result["summary"]["upcoming_count"] > 0
            )
            if has_real_alerts:
                all_results[patient.id] = {
                    "patient_name": patient.name,
                    "caregiver_email": caregiver.email,
                    **result
                }
    
    return {
        "checked_at": date.today().isoformat(),
        "threshold_days": days_threshold,
        "patients_with_alerts": len(all_results),
        "patients": all_results,
    }