"""Refill Drafter Tool - Generates refill request drafts for pharmacy."""

from datetime import date, datetime
from typing import Any
from strands import tool

from data.repository import get_repository
from data.models import Prescription, Pharmacy, Refill, RefillStatus, Frequency


@tool
def refill_drafter(patient_id: str, days_threshold: int = 7) -> dict[str, Any]:
    """
    Generate refill request drafts for prescriptions due soon.
    
    Creates draft refill records (status=pending) for prescriptions
    where next_refill_due is within threshold days and refills_remaining > 0.
    
    Args:
        patient_id: The patient ID
        days_threshold: Days ahead to draft refills for (default: 7)
    
    Returns:
        Dict with drafted refills
    """
    repo = get_repository()
    
    # Get prescriptions due for refill
    due_prescriptions = repo.get_prescriptions_due_for_refill(days_threshold)
    
    # Filter to this patient
    due_prescriptions = [rx for rx in due_prescriptions if rx.patient_id == patient_id]
    
    drafted = []
    skipped = []
    
    for rx in due_prescriptions:
        # Edge case: Prescription with zero refills_remaining
        if rx.refills_remaining <= 0:
            skipped.append({
                "prescription_id": rx.id,
                "medication_name": rx.medication_name,
                "reason": "No refills remaining",
            })
            continue
        
        # Edge case: Already have a pending refill for this prescription
        existing_refills = repo.get_refills_by_prescription(rx.id)
        has_pending = any(r.status == RefillStatus.PENDING for r in existing_refills)
        
        if has_pending:
            skipped.append({
                "prescription_id": rx.id,
                "medication_name": rx.medication_name,
                "reason": "Pending refill already exists",
            })
            continue
        
        # Edge case: Also skip if there's a READY refill not yet picked up
        has_ready = any(r.status == RefillStatus.READY for r in existing_refills)
        if has_ready:
            skipped.append({
                "prescription_id": rx.id,
                "medication_name": rx.medication_name,
                "reason": "Ready refill already exists (not yet picked up)",
            })
            continue
        
        # Get pharmacy
        pharmacy = None
        if rx.pharmacy_id:
            pharmacy = repo.get_pharmacy(rx.pharmacy_id)
        if not pharmacy:
            # Fallback to preferred pharmacy
            pharmacies = repo.get_pharmacies_by_patient(patient_id)
            pharmacy = next((p for p in pharmacies if p.is_preferred), pharmacies[0] if pharmacies else None)
        
        if not pharmacy:
            skipped.append({
                "prescription_id": rx.id,
                "medication_name": rx.medication_name,
                "reason": "No pharmacy available",
            })
            continue
        
        # Edge case: Missing refill_cycle_days (default to 30)
        days_supply = rx.refill_cycle_days if rx.refill_cycle_days and rx.refill_cycle_days > 0 else 30
        
        # Edge case: Missing/invalid frequency for dose calculation
        doses_per_day = _get_doses_per_day(rx.frequency)
        
        quantity = doses_per_day * days_supply
        
        # Create draft refill
        refill = Refill(
            prescription_id=rx.id,
            requested_date=date.today(),
            status=RefillStatus.PENDING,
            pharmacy_id=pharmacy.id,
            quantity=quantity,
            days_supply=days_supply,
            notes=f"Auto-drafted by CareCue agent (due: {rx.next_refill_due})",
        )
        
        repo.create_refill(refill)
        
        drafted.append({
            "refill_id": refill.id,
            "prescription_id": rx.id,
            "medication_name": rx.medication_name,
            "strength": rx.strength,
            "pharmacy_name": pharmacy.name,
            "pharmacy_phone": pharmacy.phone,
            "quantity": quantity,
            "days_supply": days_supply,
            "refills_remaining_after": rx.refills_remaining - 1,
            "requested_date": refill.requested_date.isoformat(),
        })
    
    return {
        "patient_id": patient_id,
        "drafted_count": len(drafted),
        "skipped_count": len(skipped),
        "drafts": drafted,
        "skipped": skipped,
    }


def _get_doses_per_day(frequency) -> int:
    """Calculate doses per day from frequency."""
    mapping = {
        Frequency.DAILY: 1,
        Frequency.BID: 2,
        Frequency.TID: 3,
        Frequency.QID: 4,
        Frequency.WEEKLY: 1,  # Weekly but we calculate per fill
        Frequency.PRN: 1,     # As needed - estimate 1/day
    }
    # Edge case: Unknown frequency defaults to 1
    return mapping.get(frequency, 1)


@tool
def approve_refill(refill_id: str) -> dict[str, Any]:
    """
    Approve a drafted refill (mark as ready for pharmacy).
    
    Args:
        refill_id: The refill ID to approve
    
    Returns:
        Updated refill status
    """
    repo = get_repository()
    
    refill = repo.get_refill(refill_id)
    if not refill:
        return {"success": False, "error": f"Refill {refill_id} not found"}
    
    if refill.status != RefillStatus.PENDING:
        return {"success": False, "error": f"Refill is not in pending status (current: {refill.status.value})"}
    
    # Update status
    refill.status = RefillStatus.READY
    repo.update_refill(refill)
    
    # Decrement refills_remaining on prescription
    rx = repo.get_prescription(refill.prescription_id)
    if rx and rx.refills_remaining > 0:
        rx.refills_remaining -= 1
        rx.updated_at = datetime.utcnow()
        repo.update_prescription(rx)
    
    return {
        "success": True,
        "refill_id": refill_id,
        "new_status": refill.status.value,
        "refills_remaining": rx.refills_remaining if rx else None,
    }


@tool
def get_pending_refills(patient_id: str = None) -> dict[str, Any]:
    """
    Get all pending refills (optionally filtered by patient).
    
    Args:
        patient_id: Optional patient ID to filter
    
    Returns:
        List of pending refills with prescription/pharmacy details
    """
    repo = get_repository()
    
    pending = repo.get_pending_refills()
    
    if patient_id:
        # Filter by patient
        filtered = []
        for refill in pending:
            rx = repo.get_prescription(refill.prescription_id)
            if rx and rx.patient_id == patient_id:
                filtered.append(refill)
        pending = filtered
    
    results = []
    for refill in pending:
        rx = repo.get_prescription(refill.prescription_id)
        pharmacy = repo.get_pharmacy(refill.pharmacy_id) if refill.pharmacy_id else None
        
        results.append({
            "refill_id": refill.id,
            "prescription_id": refill.prescription_id,
            "medication_name": rx.medication_name if rx else "Unknown",
            "strength": rx.strength if rx else "Unknown",
            "pharmacy_name": pharmacy.name if pharmacy else "Unknown",
            "pharmacy_phone": pharmacy.phone if pharmacy else "Unknown",
            "quantity": refill.quantity,
            "days_supply": refill.days_supply,
            "requested_date": refill.requested_date.isoformat(),
        })
    
    return {
        "pending_count": len(results),
        "refills": results,
    }