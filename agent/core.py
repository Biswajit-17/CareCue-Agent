"""CareCue Primary Agent - Monitors medications, detects issues, sends alerts."""

from datetime import date
from typing import Any
from strands import Agent, tool
from strands.models.openai import OpenAIModel

from tools import (
    refill_tracker,
    get_all_patients_refill_status,
    conflict_checker,
    get_all_patients_conflicts,
    dose_pattern_checker,
    get_all_patients_dose_patterns,
    refill_drafter,
    approve_refill,
    get_pending_refills,
    send_alert_email,
    send_test_email,
)

from data.repository import get_repository
from agent.state import get_agent_state


# Model configuration - uses OpenRouter via OpenAI-compatible API
def get_model():
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set in environment")
    
    return OpenAIModel(
        model_id="anthropic/claude-sonnet-4",
        api_key=api_key,
        api_base="https://openrouter.ai/api/v1",
    )


# System prompt for the primary agent
SYSTEM_PROMPT = """You are CareCue, a medication logistics agent for caregivers managing elderly parents' prescriptions.

Your role: Run quietly in the background, monitor medications, and ONLY surface to the caregiver when there's a real decision needed.

Tools available:
1. refill_tracker / get_all_patients_refill_status - Check refill dates, flag upcoming/overdue
2. conflict_checker / get_all_patients_conflicts - Detect duplicate meds, therapeutic duplication across doctors
3. dose_pattern_checker / get_all_patients_dose_patterns - Analyze adherence, find missed streaks
4. refill_drafter / approve_refill / get_pending_refills - Draft and manage refill requests
5. send_alert_email / send_test_email - Notify caregiver via email

Operating principles:
- Check all patients on each run
- For refills due within 7 days: draft refill request, alert caregiver
- For conflicts: alert caregiver with details (duplicate generic, therapeutic duplication)
- For dose patterns: alert if adherence < 80% or 2+ consecutive missed doses
- Only send ONE consolidated email per patient per run (combine alert types)
- Track everything in agent state for audit trail

When you run:
1. Get all patients with issues (refills due, conflicts, dose patterns)
2. For each patient, collect all alert data
3. Draft refills where appropriate
4. Send ONE consolidated alert email per patient
4. Record results in agent state

Be concise. Focus on actionable information. Don't explain your reasoning unless asked."""


def create_agent() -> Agent:
    """Create the primary CareCue agent with all tools."""
    return Agent(
        model=get_model(),
        system_prompt=SYSTEM_PROMPT,
        tools=[
            refill_tracker,
            get_all_patients_refill_status,
            conflict_checker,
            get_all_patients_conflicts,
            dose_pattern_checker,
            get_all_patients_dose_patterns,
            refill_drafter,
            approve_refill,
            get_pending_refills,
            send_alert_email,
            send_test_email,
        ],
    )


# Top-level imports for email formatting
from tools.notifier import _format_refill_alert, _format_conflict_alert, _format_dose_pattern_alert, _format_refill_drafted_alert
from data.models import Alert, AlertType, AlertSeverity
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import hashlib
import json
from dotenv import load_dotenv
load_dotenv()

SMTP_USER = os.getenv("GMAIL_SMTP_USER")
SMTP_PASSWORD = os.getenv("GMAIL_SMTP_APP_PASSWORD")


def _make_alert_fingerprint(patient_id: str, alert_data_by_type: dict) -> str:
    """Create a fingerprint of current alert conditions to detect changes."""
    # Extract key identifying data from each alert type
    fingerprint_parts = {"patient_id": patient_id}
    
    if "refill" in alert_data_by_type:
        refill_data = alert_data_by_type["refill"]
        # Sort by prescription_id for consistent ordering
        upcoming = sorted(refill_data.get("upcoming", []), key=lambda x: x["prescription_id"])
        overdue = sorted(refill_data.get("overdue", []), key=lambda x: x["prescription_id"])
        fingerprint_parts["refill"] = {
            "upcoming": [(r["prescription_id"], r["days_until_refill"]) for r in upcoming],
            "overdue": [(r["prescription_id"], r["days_overdue"]) for r in overdue],
        }
    
    if "conflict" in alert_data_by_type:
        conflicts = alert_data_by_type["conflict"].get("conflicts", [])
        # Sort by type + prescription_ids for consistency
        conflicts_sorted = sorted(conflicts, key=lambda c: (c["type"], str(c.get("prescription_ids", []))))
        fingerprint_parts["conflict"] = [
            (c["type"], tuple(sorted(c.get("prescription_ids", [])))) for c in conflicts_sorted
        ]
    
    if "pattern" in alert_data_by_type:
        pattern_data = alert_data_by_type["pattern"]
        streaks = pattern_data.get("missed_streaks", [])
        streaks_sorted = sorted(streaks, key=lambda s: s["medication"])
        fingerprint_parts["pattern"] = [
            (s["medication"], s["consecutive_missed"]) for s in streaks_sorted
        ]
        fingerprint_parts["pattern_adherence"] = pattern_data.get("adherence_rate", 0)
    
    return hashlib.sha256(json.dumps(fingerprint_parts, sort_keys=True).encode()).hexdigest()[:16]


def _should_send_alert(state, patient_id: str, alert_data_by_type: dict) -> tuple[bool, str]:
    """Check if alert should be sent (new or changed). Returns (should_send, fingerprint)."""
    fingerprint = _make_alert_fingerprint(patient_id, alert_data_by_type)
    last_fingerprint = state.get_checkpoint(f"last_alert_fingerprint_{patient_id}")
    
    if last_fingerprint == fingerprint:
        return False, fingerprint  # No change, don't send
    
    return True, fingerprint  # New or changed, send it


@tool
def run_daily_check() -> dict[str, Any]:
    """
    Run the complete daily medication check for all patients.
    
    This is the main entry point for scheduled runs.
    """
    repo = get_repository()
    state = get_agent_state()
    
    # Start run tracking
    run_id = state.start_run("scheduled", {"trigger": "daily_cron"})
    
    caregivers = repo.list_caregivers()
    total_patients = 0
    total_alerts_sent = 0
    total_alerts_generated = 0
    errors = []
    
    for caregiver in caregivers:
        patients = repo.get_patients_by_caregiver(caregiver.id)
        total_patients += len(patients)
        
        for patient in patients:
            try:
                alert_data_by_type = {}
                
                # 1. Check refills
                refill_result = refill_tracker(patient.id, days_threshold=7)
                if refill_result["summary"]["overdue_count"] > 0 or refill_result["summary"]["upcoming_count"] > 0:
                    alert_data_by_type["refill"] = refill_result
                    total_alerts_generated += refill_result["summary"]["overdue_count"] + refill_result["summary"]["upcoming_count"]
                
                # 2. Check conflicts
                conflict_result = conflict_checker(patient.id)
                if conflict_result["conflicts_found"] > 0:
                    alert_data_by_type["conflict"] = conflict_result
                    total_alerts_generated += conflict_result["conflicts_found"]
                
                # 3. Check dose patterns
                pattern_result = dose_pattern_checker(patient.id, lookback_days=30)
                if pattern_result.get("has_concerning_patterns", False):
                    alert_data_by_type["pattern"] = pattern_result
                    total_alerts_generated += len(pattern_result.get("missed_streaks", []))
                
                # 4. Draft refills for due prescriptions
                if "refill" in alert_data_by_type:
                    draft_result = refill_drafter(patient.id, days_threshold=7)
                    if draft_result["drafted_count"] > 0:
                        alert_data_by_type["refill_drafted"] = draft_result
                
                # 5. Send consolidated alert if any issues
                if alert_data_by_type:
                    # Check deduplication
                    should_send, fingerprint = _should_send_alert(state, patient.id, alert_data_by_type)
                    
                    if not should_send:
                        print(f"  Skipping alert for {patient.name} - no changes since last run")
                    else:
                        patient_name = patient.name
                        
                        # Build combined email content
                        html_parts = [f"<h2>CareCue Daily Check — {patient_name}</h2>"]
                        text_parts = [f"CareCue Daily Check — {patient_name}\n"]
                        
                        if "refill" in alert_data_by_type:
                            subj, html, text = _format_refill_alert(patient_name, alert_data_by_type["refill"])
                            html_parts.append(html)
                            text_parts.append(text)
                        
                        if "conflict" in alert_data_by_type:
                            subj, html, text = _format_conflict_alert(patient_name, alert_data_by_type["conflict"])
                            html_parts.append(html)
                            text_parts.append(text)
                        
                        if "pattern" in alert_data_by_type:
                            subj, html, text = _format_dose_pattern_alert(patient_name, alert_data_by_type["pattern"])
                            html_parts.append(html)
                            text_parts.append(text)
                        
                        if "refill_drafted" in alert_data_by_type:
                            subj, html, text = _format_refill_drafted_alert(patient_name, alert_data_by_type["refill_drafted"])
                            html_parts.append(html)
                            text_parts.append(text)
                        
                        combined_html = "\n".join(html_parts)
                        combined_text = "\n\n".join(text_parts)
                        
                        # Send single consolidated email
                        if SMTP_USER and SMTP_PASSWORD:
                            try:
                                msg = MIMEMultipart("alternative")
                                msg["From"] = SMTP_USER
                                msg["To"] = caregiver.email
                                msg["Subject"] = f"CareCue: Daily Medication Update for {patient_name}"
                                
                                msg.attach(MIMEText(combined_text, "plain"))
                                msg.attach(MIMEText(combined_html, "html"))
                                
                                with smtplib.SMTP("smtp.gmail.com", 587) as server:
                                    server.starttls()
                                    server.login(SMTP_USER, SMTP_PASSWORD)
                                    server.send_message(msg)
                                
                                # Record alert in DB
                                alert = Alert(
                                    patient_id=patient.id,
                                    alert_type=AlertType.REFILL_DUE,
                                    severity=AlertSeverity.WARNING if "conflict" in alert_data_by_type else AlertSeverity.INFO,
                                    title=f"Daily Medication Update for {patient_name}",
                                    message=combined_text,
                                    related_prescription_ids=[],
                                    related_refill_ids=[],
                                )
                                repo.create_alert(alert)
                                
                                # Record in state
                                state.record_alert(run_id, patient.id, "consolidated", 
                                                 "warning" if "conflict" in alert_data_by_type else "info",
                                                 alert.id, "sent")
                                
                                # Save fingerprint to suppress future duplicate alerts
                                state.set_checkpoint(f"last_alert_fingerprint_{patient.id}", fingerprint)
                                
                                total_alerts_sent += 1
                            except Exception as e:
                                errors.append(f"Failed to send email for {patient.name}: {e}")
                                state.record_alert(run_id, patient.id, "consolidated", "error", 
                                                 "", "failed", str(e))
                        else:
                            errors.append("SMTP not configured")
                    
            except Exception as e:
                errors.append(f"Error checking patient {patient.name}: {e}")
    
    # Complete run
    state.complete_run(run_id, "completed" if not errors else "completed_with_errors",
                      total_patients, total_alerts_generated, total_alerts_sent, errors)
    
    return {
        "run_id": run_id,
        "patients_checked": total_patients,
        "alerts_generated": total_alerts_generated,
        "alerts_sent": total_alerts_sent,
        "errors": errors,
    }


@tool
def run_patient_check(patient_id: str) -> dict[str, Any]:
    """Run check for a single patient (for testing/on-demand)."""
    repo = get_repository()
    patient = repo.get_patient(patient_id)
    
    if not patient:
        return {"error": f"Patient {patient_id} not found"}
    
    caregiver = repo.get_caregiver(patient.caregiver_id)
    
    results = {
        "patient_id": patient_id,
        "patient_name": patient.name,
        "caregiver_email": caregiver.email if caregiver else None,
        "refills": refill_tracker(patient_id),
        "conflicts": conflict_checker(patient_id),
        "dose_patterns": dose_pattern_checker(patient_id),
    }
    
    return results