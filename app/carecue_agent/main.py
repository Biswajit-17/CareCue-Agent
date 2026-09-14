"""CareCue AgentCore Runtime Entrypoint.

Deterministic email dispatch: the LLM analyzes patient data and generates
a summary. After the agent completes, we check each patient for issues
using the tool functions directly and send emails ourselves. This ensures
emails are always sent when issues exist, regardless of LLM tool-calling.
"""

import sys
import io
import re
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel

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
from tools.notifier import get_and_clear_email_results, _track_email_result, _send_email, ALERT_FORMATTERS
from data.repository import get_repository
from data.models import AlertType, Alert, AlertSeverity

app = BedrockAgentCoreApp()

model = BedrockModel(model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0")

SYSTEM_PROMPT = """You are CareCue, a medication logistics agent for caregivers managing elderly parents' prescriptions.

Your role: Run quietly in the background, monitor medications, and ONLY surface to the caregiver when there's a real decision needed.

Tools available:
1. refill_tracker / get_all_patients_refill_status - Check refill dates, flag upcoming/overdue
2. conflict_checker / get_all_patients_conflicts - Detect duplicate meds, therapeutic duplication across doctors
3. dose_pattern_checker / get_all_patients_dose_patterns - Analyze adherence, find missed streaks
4. refill_drafter / approve_refill / get_pending_refills - Draft and manage refill requests

Operating principles:
- Check all patients on each run
- For refills due within 7 days: draft refill request
- For conflicts: note the details (duplicate generic, therapeutic duplication)
- For dose patterns: note if adherence < 80% or 2+ consecutive missed doses

When you run:
1. Get all patients with issues (refills due, conflicts, dose patterns)
2. For each patient, collect all alert data
3. Draft refills where appropriate
4. Generate a clear summary of all findings per patient

CRITICAL RULES - FOLLOW EXACTLY:
- Only report facts that come directly from tool results. Never infer, assume, or generalize.
- If a patient has NO conflicts, say exactly "None detected" for that patient. Do NOT claim they have conflicts.
- Do NOT add a "Summary", "Next Steps", "Actions Pending", or "Overall Status" section at the end. Just present each patient's findings.
- Do NOT include any section about email/alert delivery status in your response. That will be appended automatically.
- Do NOT call send_alert_email or send_test_email. Email dispatch is handled automatically after your analysis."""

agent = Agent(
    model=model,
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
    ],
)


def _strip_email_status(text: str) -> str:
    """Remove any LLM-generated email/alert status lines from the response."""
    patterns = [
        r'\*\*Alert Notifications?:?\*\*.*?(?=\n\n|\n###|\Z)',
        r'\*\*Alert Delivery Status:?\*\*.*?(?=\n\n|\n###|\Z)',
        r'\*\*Email Status:?\*\*.*?(?=\n\n|\n###|\Z)',
        r'Alert emails?:?.*?(?=\n\n|\n###|\Z)',
        r'Email alerts?:?.*?(?=\n\n|\n###|\Z)',
        r'Unable to send.*?(?=\n\n|\n###|\Z)',
        r'Failed to send.*?(?=\n\n|\n###|\Z)',
        r'database write.*?(?=\n\n|\n###|\Z)',
        r'Manual.*?notification.*?(?=\n\n|\n###|\Z)',
    ]
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()


def _strip_llm_summaries(text: str) -> str:
    """Remove LLM-generated summary/conclusion sections that may contain hallucinations."""
    patterns = [
        # Summary sections
        r'###?\s*Summary.*?(?=###|\Z)',
        r'###?\s*Overall Status.*?(?=###|\Z)',
        r'###?\s*Overview.*?(?=###|\Z)',
        # Action/Next Steps sections
        r'###?\s*Next Steps.*?(?=###|\Z)',
        r'###?\s*Actions? Pending.*?(?=###|\Z)',
        r'###?\s*Action Items.*?(?=###|\Z)',
        r'###?\s*Recommendations.*?(?=###|\Z)',
        # Cross-patient generalizations
        r'\*\*Critical Actions? Needed:?\*\*.*?(?=\n\n|\n###|\Z)',
        r'Both patients.*?(?=\n\n|\n###|\Z)',
    ]
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
    # Clean up excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _check_patient_issues(patient_id: str) -> dict:
    """Check a single patient for all issue types. Returns dict of issues."""
    issues = {"refill": None, "conflict": None, "dose_pattern": None}
    
    try:
        refill_data = refill_tracker.__wrapped__(patient_id=patient_id)
        if refill_data.get("overdue") or refill_data.get("upcoming"):
            issues["refill"] = refill_data
    except Exception as e:
        print(f"[CHECK] Refill check failed for {patient_id}: {e}")
    
    try:
        conflict_data = conflict_checker.__wrapped__(patient_id=patient_id)
        if conflict_data.get("conflicts"):
            issues["conflict"] = conflict_data
    except Exception as e:
        print(f"[CHECK] Conflict check failed for {patient_id}: {e}")
    
    try:
        pattern_data = dose_pattern_checker.__wrapped__(patient_id=patient_id)
        if pattern_data.get("missed_streaks") or (pattern_data.get("adherence_rate") is not None and pattern_data["adherence_rate"] < 80):
            issues["dose_pattern"] = pattern_data
    except Exception as e:
        print(f"[CHECK] Dose pattern check failed for {patient_id}: {e}")
    
    return issues


def _send_alert_email_direct(patient_id: str, alert_type: str, alert_data: dict) -> dict:
    """Send alert email directly using underlying functions (bypasses Strands tool wrapper)."""
    repo = get_repository()
    
    patient = repo.get_patient(patient_id)
    if not patient:
        return {"success": False, "error": f"Patient {patient_id} not found"}
    
    caregiver = repo.get_caregiver(patient.caregiver_id)
    if not caregiver:
        return {"success": False, "error": f"Caregiver for patient {patient_id} not found"}
    
    try:
        alert_type_enum = AlertType(alert_type)
    except ValueError:
        return {"success": False, "error": f"Unknown alert type: {alert_type}"}
    
    formatter = ALERT_FORMATTERS.get(alert_type_enum)
    if not formatter:
        return {"success": False, "error": f"No formatter for alert type: {alert_type}"}
    
    subject, html_body, text_body = formatter(patient.name, alert_data)
    
    success, error_msg = _send_email(caregiver.email, subject, html_body, text_body)
    
    alert = Alert(
        patient_id=patient_id,
        alert_type=alert_type_enum,
        severity=AlertSeverity.WARNING if alert_type_enum in [AlertType.REFILL_OVERDUE, AlertType.CONFLICT_DETECTED] else AlertSeverity.INFO,
        title=subject,
        message=text_body,
        related_prescription_ids=alert_data.get("related_prescription_ids", []),
        related_refill_ids=alert_data.get("related_refill_ids", []),
    )
    repo.create_alert(alert)
    
    _track_email_result(patient_id, patient.name, success, error_msg)
    
    return {"success": success, "patient_id": patient_id, "caregiver_email": caregiver.email, "alert_type": alert_type, "alert_id": alert.id}


def _send_consolidated_email(patient_id: str, patient_name: str, issues: dict) -> dict:
    """Send ONE consolidated email for a patient with all issue types."""
    results = []
    
    if issues.get("refill"):
        result = _send_alert_email_direct(patient_id=patient_id, alert_type="refill_due", alert_data=issues["refill"])
        results.append(("refill", result))
        print(f"[EMAIL] Refill email for {patient_name}: success={result.get('success')}")
    
    if issues.get("conflict"):
        result = _send_alert_email_direct(patient_id=patient_id, alert_type="conflict_detected", alert_data=issues["conflict"])
        results.append(("conflict", result))
        print(f"[EMAIL] Conflict email for {patient_name}: success={result.get('success')}")
    
    if issues.get("dose_pattern"):
        result = _send_alert_email_direct(patient_id=patient_id, alert_type="dose_pattern", alert_data=issues["dose_pattern"])
        results.append(("dose_pattern", result))
        print(f"[EMAIL] Dose pattern email for {patient_name}: success={result.get('success')}")
    
    return {"patient_id": patient_id, "patient_name": patient_name, "email_results": results}


def _build_deterministic_email_status() -> str:
    """Build email status section from actual tool results."""
    results = get_and_clear_email_results()
    if not results:
        return ""
    
    lines = ["**Alert Delivery Status:**"]
    for r in results:
        if r["success"]:
            lines.append(f"- {r['patient_name']}: [OK] Email sent successfully")
        else:
            lines.append(f"- {r['patient_name']}: [FAILED] {r['error_detail']}")
    return "\n".join(lines)


@app.entrypoint
def invoke(payload):
    """AgentCore calls this with {"prompt": "..."}."""
    prompt = payload.get("prompt", "Run daily check for all patients")
    
    get_and_clear_email_results()
    
    result = agent(prompt)
    llm_text = str(result)
    
    # Strip LLM-generated summaries (may contain hallucinations) and email status
    cleaned_text = _strip_email_status(llm_text)
    cleaned_text = _strip_llm_summaries(cleaned_text)
    
    try:
        repo = get_repository()
        caregiver = repo.get_caregiver_by_email("biswajitrk123@gmail.com")
        if not caregiver:
            return {"result": cleaned_text}
        patients = repo.get_patients_by_caregiver(caregiver.id)
        
        email_summaries = []
        for patient in patients:
            issues = _check_patient_issues(patient.id)
            has_issues = any(v is not None for v in issues.values())
            
            if has_issues:
                try:
                    summary = _send_consolidated_email(patient.id, patient.name, issues)
                    email_summaries.append(summary)
                except Exception as e:
                    print(f"[EMAIL] Error sending email for {patient.name}: {type(e).__name__}: {e}")
        
        email_status = _build_deterministic_email_status()
        
        # Build response
        parts = [cleaned_text]
        
        if email_status:
            parts.append(email_status)
        
        if email_summaries:
            email_summary_lines = ["**Email Dispatch:**"]
            for s in email_summaries:
                sent = sum(1 for _, r in s["email_results"] if r.get("success"))
                total = len(s["email_results"])
                email_summary_lines.append(f"- {s['patient_name']}: {sent}/{total} emails sent")
            parts.append("\n".join(email_summary_lines))
        
        return {"result": "\n\n".join(parts)}
    except Exception as e:
        print(f"[ENTRYPOINT] Error in post-processing: {type(e).__name__}: {e}")
        return {"result": cleaned_text}


if __name__ == "__main__":
    app.run()
