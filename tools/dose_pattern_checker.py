"""Dose Pattern Checker Tool - Analyzes dose logs for adherence patterns."""

from datetime import date, datetime, timedelta
from typing import Any
from collections import defaultdict
from strands import tool

from data.repository import get_repository
from data.models import DoseLog, Prescription, DoseStatus


@tool
def dose_pattern_checker(patient_id: str, lookback_days: int = 30) -> dict[str, Any]:
    """
    Analyze dose adherence patterns for a patient.
    
    Detects:
    - Overall adherence rate (only for prescriptions with dose logs)
    - Consecutive missed dose streaks per medication
    - Medications with concerning patterns
    
    Args:
        patient_id: The patient ID to check
        lookback_days: How many days back to analyze (default: 30)
    
    Returns:
        Dict with adherence analysis
    """
    repo = get_repository()
    
    # Get all dose logs for patient in lookback period
    dose_logs = repo.get_recent_dose_logs(patient_id, lookback_days)
    
    # Get all active prescriptions for this patient
    all_prescriptions = repo.get_prescriptions_by_patient(patient_id, active_only=True)
    
    if not dose_logs:
        # Edge case: no dose logs at all for this patient
        # Mark all prescriptions as "no data" rather than 0% adherence
        medication_adherence = {}
        for rx in all_prescriptions:
            medication_adherence[rx.medication_name] = {
                "prescription_id": rx.id,
                "strength": rx.strength,
                "frequency": rx.frequency.value,
                "total_doses": 0,
                "taken": 0,
                "missed": 0,
                "skipped": 0,
                "adherence_rate": None,  # null = no data, not 0%
                "data_status": "no_logs",
            }
        
        return {
            "patient_id": patient_id,
            "lookback_days": lookback_days,
            "period_start": (date.today() - timedelta(days=lookback_days)).isoformat(),
            "period_end": date.today().isoformat(),
            "total_scheduled_doses": 0,
            "total_taken": 0,
            "adherence_rate": None,  # null = no data to compute
            "missed_streaks": [],
            "medication_adherence": medication_adherence,
            "has_concerning_patterns": False,
            "message": "No dose logs found in period",
        }
    
    # Group by prescription
    logs_by_rx = defaultdict(list)
    for log in dose_logs:
        logs_by_rx[log.prescription_id].append(log)
    
    # Get prescription details for each
    medication_adherence = {}
    all_streaks = []
    prescriptions_with_logs = set(logs_by_rx.keys())
    
    for rx_id, logs in logs_by_rx.items():
        rx = repo.get_prescription(rx_id)
        if not rx:
            continue
        
        # Sort by scheduled time
        logs.sort(key=lambda l: l.scheduled_time)
        
        total = len(logs)
        taken = sum(1 for l in logs if l.status == DoseStatus.TAKEN)
        missed = sum(1 for l in logs if l.status == DoseStatus.MISSED)
        skipped = sum(1 for l in logs if l.status == DoseStatus.SKIPPED)
        
        # Edge case: very sparse data (1-2 logs) - mark as insufficient data
        if total <= 2:
            adherence = None  # null = insufficient data
            data_status = "insufficient_data"
        else:
            adherence = (taken / total * 100) if total > 0 else 0
            data_status = "ok"
        
        # Find consecutive missed streaks (only for medications with sufficient data)
        streaks = []
        if data_status == "ok":
            current_streak = 0
            streak_start = None
            
            for log in logs:
                if log.status == DoseStatus.MISSED:
                    if current_streak == 0:
                        streak_start = log.scheduled_time
                    current_streak += 1
                else:
                    if current_streak >= 2:  # Only report streaks of 2+
                        streaks.append({
                            "medication": rx.medication_name,
                            "strength": rx.strength,
                            "consecutive_missed": current_streak,
                            "streak_start": streak_start.isoformat() if streak_start else None,
                            "streak_end": log.scheduled_time.isoformat(),
                            "last_taken": _get_last_taken_before(logs, log.scheduled_time),
                        })
                    current_streak = 0
                    streak_start = None
            
            # Check if streak continues to end
            if current_streak >= 2:
                streaks.append({
                    "medication": rx.medication_name,
                    "strength": rx.strength,
                    "consecutive_missed": current_streak,
                    "streak_start": streak_start.isoformat() if streak_start else None,
                    "streak_end": logs[-1].scheduled_time.isoformat() if logs else None,
                    "last_taken": _get_last_taken_before(logs, logs[-1].scheduled_time) if logs else None,
                })
        
        medication_adherence[rx.medication_name] = {
            "prescription_id": rx_id,
            "strength": rx.strength,
            "frequency": rx.frequency.value,
            "total_doses": total,
            "taken": taken,
            "missed": missed,
            "skipped": sum(1 for l in logs if l.status == DoseStatus.SKIPPED),
            "adherence_rate": round(adherence, 1) if adherence is not None else None,
            "data_status": data_status,
        }
        
        all_streaks.extend(streaks)
    
    # Edge case: Handle prescriptions with NO dose logs at all
    # Mark them as "no_logs" rather than including in 0% adherence
    for rx in repo.get_prescriptions_by_patient(patient_id, active_only=True):
        if rx.id not in prescriptions_with_logs:
            medication_adherence[rx.medication_name] = {
                "prescription_id": rx.id,
                "strength": rx.strength,
                "frequency": rx.frequency.value,
                "total_doses": 0,
                "taken": 0,
                "missed": 0,
                "skipped": 0,
                "adherence_rate": None,
                "data_status": "no_logs",
            }
    
    # Overall adherence: only compute from prescriptions WITH sufficient data
    # (exclude "no_logs" and "insufficient_data")
    valid_adherences = [
        m["adherence_rate"] 
        for m in medication_adherence.values() 
        if m["adherence_rate"] is not None and m["data_status"] == "ok"
    ]
    overall_adherence = (sum(valid_adherences) / len(valid_adherences)) if valid_adherences else None
    
    total_doses = sum(m["total_doses"] for m in medication_adherence.values())
    total_taken = sum(m["taken"] for m in medication_adherence.values())
    
    return {
        "patient_id": patient_id,
        "lookback_days": lookback_days,
        "period_start": (date.today() - timedelta(days=lookback_days)).isoformat(),
        "period_end": date.today().isoformat(),
        "total_scheduled_doses": total_doses,
        "total_taken": total_taken,
        "adherence_rate": round(overall_adherence, 1) if overall_adherence is not None else None,
        "missed_streaks": all_streaks,
        "medication_adherence": medication_adherence,
        "has_concerning_patterns": len(all_streaks) > 0 or (overall_adherence is not None and overall_adherence < 80),
    }


def _get_last_taken_before(logs: list[DoseLog], before_time: datetime) -> str | None:
    """Find the last 'taken' dose before a given time."""
    for log in reversed(logs):
        if log.scheduled_time < before_time and log.status == DoseStatus.TAKEN:
            return log.actual_time.isoformat() if log.actual_time else log.scheduled_time.isoformat()
    return None


@tool
def get_all_patients_dose_patterns(lookback_days: int = 30) -> dict[str, Any]:
    """
    Check dose patterns across ALL patients (for scheduled runs).
    
    Returns:
        Dict with per-patient pattern findings
    """
    repo = get_repository()
    
    caregivers = repo.list_caregivers()
    all_results = {}
    
    for caregiver in caregivers:
        patients = repo.get_patients_by_caregiver(caregiver.id)
        for patient in patients:
            result = dose_pattern_checker(patient.id, lookback_days)
            if result.get("has_concerning_patterns", False):
                all_results[patient.id] = {
                    "patient_name": patient.name,
                    "caregiver_email": caregiver.email,
                    **result
                }
    
    return {
        "lookback_days": lookback_days,
        "patients_with_concerns": len(all_results),
        "patients": all_results,
    }