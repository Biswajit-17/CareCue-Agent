"""Conflict Checker Tool - Cross-references prescriptions for conflicts."""

import json
import os
from typing import Any
from collections import defaultdict
from strands import tool

from data.repository import get_repository
from data.models import Prescription, Doctor

# Load drug classes from JSON reference file
_DRUG_CLASSES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "drug_classes.json")

def _load_drug_classes() -> dict:
    """Load drug class patterns from the JSON reference file."""
    try:
        with open(_DRUG_CLASSES_PATH, "r") as f:
            data = json.load(f)
        # Build a flat map: class_name -> list of generics
        classes = {}
        for key, info in data.get("drug_classes", {}).items():
            # Skip composite classes that reference other classes
            if key in ("ace_inhibitor_or_arb", "anticoagulant_or_antiplatelet", "antidiabetic"):
                continue
            classes[key] = info.get("generics", [])
        return classes
    except (FileNotFoundError, json.JSONDecodeError):
        # Fallback to minimal defaults if JSON is missing
        return {
            "statin": ["atorvastatin", "simvastatin", "rosuvastatin", "pravastatin", "lovastatin"],
            "ace_inhibitor": ["lisinopril", "enalapril", "ramipril", "captopril", "benazepril"],
            "arb": ["losartan", "valsartan", "irbesartan", "olmesartan", "telmisartan"],
            "beta_blocker": ["metoprolol", "atenolol", "propranolol", "bisoprolol", "carvedilol"],
            "diuretic": ["hydrochlorothiazide", "furosemide", "spironolactone", "chlorthalidone"],
            "levodopa": ["carbidopa-levodopa", "levodopa"],
        }

_THERAPEUTIC_PATTERNS = _load_drug_classes()


@tool
def conflict_checker(patient_id: str) -> dict[str, Any]:
    """
    Check for medication conflicts across a patient's active prescriptions.
    
    Detects:
    - Duplicate medication names (same drug, different prescriptions) from DIFFERENT doctors
    - Duplicate generic names (same active ingredient) from DIFFERENT doctors
    - Overlapping therapeutic classes from DIFFERENT doctors
    
    Args:
        patient_id: The patient ID to check conflicts for
    
    Returns:
        Dict with conflict findings
    """
    repo = get_repository()
    prescriptions = repo.get_prescriptions_by_patient(patient_id, active_only=True)
    
    # Edge case: patient with exactly 1 prescription (must never false-positive)
    if len(prescriptions) < 2:
        return {
            "patient_id": patient_id,
            "total_prescriptions": len(prescriptions),
            "conflicts_found": 0,
            "conflicts": [],
            "message": "No conflicts possible with fewer than 2 prescriptions"
        }
    
    conflicts = []
    
    # 1. Check for duplicate medication names from DIFFERENT doctors
    # Edge case: same medication from SAME doctor is not a conflict (e.g., dose adjustment)
    by_med_name = defaultdict(list)
    for rx in prescriptions:
        by_med_name[rx.medication_name.lower()].append(rx)
    
    for med_name, rx_list in by_med_name.items():
        if len(rx_list) > 1:
            # Get unique doctor IDs for these prescriptions
            doctor_ids = set(rx.doctor_id for rx in rx_list)
            # Edge case: only flag if from DIFFERENT doctors
            if len(doctor_ids) > 1:
                doctors = []
                for doc_id in doctor_ids:
                    doctor = repo.get_doctor(doc_id)
                    doctors.append(doctor.name if doctor else doc_id)
                
                conflicts.append({
                    "type": "duplicate_medication",
                    "severity": "high",
                    "medication_name": rx_list[0].medication_name,
                    "generic_name": rx_list[0].generic_name,
                    "prescription_ids": [rx.id for rx in rx_list],
                    "prescribing_doctors": doctors,
                    "message": f"Duplicate medication '{rx_list[0].medication_name}' prescribed by {len(doctors)} different doctor(s)",
                })
    
    # 2. Check for duplicate generic names (different brand, same ingredient) from DIFFERENT doctors
    # Edge case: prescriptions with missing generic_name are skipped
    # Edge case: case-insensitive matching on generic names
    by_generic = defaultdict(list)
    for rx in prescriptions:
        if rx.generic_name:
            by_generic[rx.generic_name.lower()].append(rx)
    
    for generic_name, rx_list in by_generic.items():
        if len(rx_list) > 1:
            # Check if they're actually different medications (different brand names)
            med_names = set(rx.medication_name.lower() for rx in rx_list)
            if len(med_names) > 1:
                # Edge case: only flag if from DIFFERENT doctors
                doctor_ids = set(rx.doctor_id for rx in rx_list)
                if len(doctor_ids) > 1:
                    doctors = []
                    for doc_id in doctor_ids:
                        doctor = repo.get_doctor(doc_id)
                        doctors.append(doctor.name if doctor else doc_id)
                    
                    conflicts.append({
                        "type": "duplicate_generic",
                        "severity": "high",
                        "generic_name": rx_list[0].generic_name,
                        "brand_names": list(med_names),
                        "prescription_ids": [rx.id for rx in rx_list],
                        "prescribing_doctors": doctors,
                        "message": f"Same generic ingredient '{rx_list[0].generic_name}' prescribed as different brands: {', '.join(med_names)} by different doctors",
                    })
    
    # 3. Basic therapeutic class overlap (using common patterns) - only across DIFFERENT doctors
    # Loaded from data/drug_classes.json - cross-checked against WHO ATC / RxClass
    therapeutic_patterns = _THERAPEUTIC_PATTERNS
    
    rx_by_class = defaultdict(list)
    for rx in prescriptions:
        med_lower = rx.medication_name.lower()
        generic_lower = (rx.generic_name or "").lower()
        
        for class_name, patterns in therapeutic_patterns.items():
            for pattern in patterns:
                if pattern in med_lower or pattern in generic_lower:
                    rx_by_class[class_name].append(rx)
                    break
    
    for class_name, rx_list in rx_by_class.items():
        if len(rx_list) > 1:
            # Edge case: only flag therapeutic duplication if from DIFFERENT doctors
            # Patient with 3+ prescriptions from the SAME doctor should NOT be flagged
            doctor_ids = set(rx.doctor_id for rx in rx_list)
            if len(doctor_ids) > 1:
                doctors = []
                for doc_id in doctor_ids:
                    doctor = repo.get_doctor(doc_id)
                    doctors.append(doctor.name if doctor else doc_id)
                
                conflicts.append({
                    "type": "therapeutic_duplication",
                    "severity": "medium",
                    "therapeutic_class": class_name,
                    "medications": [rx.medication_name for rx in rx_list],
                    "prescription_ids": [rx.id for rx in rx_list],
                    "prescribing_doctors": doctors,
                    "message": f"Therapeutic duplication: multiple {class_name.replace('_', ' ')} medications from different doctors",
                })
    
    return {
        "patient_id": patient_id,
        "total_prescriptions": len(prescriptions),
        "conflicts_found": len(conflicts),
        "conflicts": conflicts,
    }


@tool
def get_all_patients_conflicts() -> dict[str, Any]:
    """
    Check conflicts across ALL patients (for scheduled runs).
    
    Returns:
        Dict with per-patient conflict findings
    """
    repo = get_repository()
    
    caregivers = repo.list_caregivers()
    all_results = {}
    
    for caregiver in caregivers:
        patients = repo.get_patients_by_caregiver(caregiver.id)
        for patient in patients:
            result = conflict_checker(patient.id)
            if result["conflicts_found"] > 0:
                all_results[patient.id] = {
                    "patient_name": patient.name,
                    "caregiver_email": caregiver.email,
                    **result
                }
    
    return {
        "patients_with_conflicts": len(all_results),
        "patients": all_results,
    }