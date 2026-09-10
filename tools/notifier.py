"""Notifier Tool - Sends email alerts via Gmail SMTP."""

import os
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any
from strands import tool

from data.repository import get_repository
from data.models import Alert, AlertType, AlertSeverity

# Load .env file
load_dotenv()

# Gmail SMTP configuration
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("GMAIL_SMTP_USER")  # Gmail address
SMTP_PASSWORD = os.getenv("GMAIL_SMTP_APP_PASSWORD")  # App password


def _send_email(to_email: str, subject: str, html_body: str, text_body: str = None) -> tuple[bool, str | None]:
    """
    Send email via Gmail SMTP.
    
    Returns:
        Tuple of (success: bool, error_message: str | None)
        On success: (True, None)
        On failure: (False, error_message)
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        error_msg = "Gmail SMTP credentials not configured (GMAIL_SMTP_USER, GMAIL_SMTP_APP_PASSWORD)"
        print(f"WARNING: {error_msg}")
        return False, error_msg
    
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = SMTP_USER
        msg["To"] = to_email
        msg["Subject"] = subject
        
        if text_body:
            msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))
        
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        return True, None
    except smtplib.SMTPAuthenticationError as e:
        error_msg = f"SMTP authentication failed: {e}"
        print(f"ERROR: {error_msg}")
        return False, error_msg
    except smtplib.SMTPRecipientsRefused as e:
        error_msg = f"Recipient refused: {e}"
        print(f"ERROR: {error_msg}")
        return False, error_msg
    except smtplib.SMTPServerDisconnected as e:
        error_msg = f"SMTP server disconnected: {e}"
        print(f"ERROR: {error_msg}")
        return False, error_msg
    except smtplib.SMTPException as e:
        error_msg = f"SMTP error: {e}"
        print(f"ERROR: {error_msg}")
        return False, error_msg
    except Exception as e:
        # Catch-all for any unexpected errors (network issues, etc.)
        error_msg = f"Unexpected error sending email to {to_email}: {type(e).__name__}: {e}"
        print(f"ERROR: {error_msg}")
        return False, error_msg


def _format_refill_alert(patient_name: str, refill_data: dict) -> tuple[str, str, str]:
    """Format refill due/overdue alert."""
    subject = f"CareCue: Refill Alert for {patient_name}"
    
    overdue = refill_data.get("overdue", [])
    upcoming = refill_data.get("upcoming", [])
    
    html_parts = [f"<h2>Refill Alert for {patient_name}</h2>"]
    text_parts = [f"Refill Alert for {patient_name}\n"]
    
    if overdue:
        html_parts.append("<h3 style='color: #dc2626;'>⚠️ OVERDUE REFILLS</h3>")
        html_parts.append("<ul>")
        text_parts.append("\nOVERDUE REFILLS:")
        for rx in overdue:
            html_parts.append(f"<li><strong>{rx['medication_name']} {rx['strength']}</strong> — "
                            f"{rx['days_overdue']} days overdue (refills left: {rx['refills_remaining']})</li>")
            text_parts.append(f"  - {rx['medication_name']} {rx['strength']} — {rx['days_overdue']} days overdue")
        html_parts.append("</ul>")
    
    if upcoming:
        html_parts.append("<h3 style='color: #ea580c;'>📅 UPCOMING REFILLS (within 7 days)</h3>")
        html_parts.append("<ul>")
        text_parts.append("\nUPCOMING REFILLS:")
        for rx in upcoming:
            html_parts.append(f"<li><strong>{rx['medication_name']} {rx['strength']}</strong> — "
                            f"due in {rx['days_until_refill']} days (refills left: {rx['refills_remaining']})</li>")
            text_parts.append(f"  - {rx['medication_name']} {rx['strength']} — due in {rx['days_until_refill']} days")
        html_parts.append("</ul>")
    
    html_parts.append("<p>Log in to CareCue to review and take action.</p>")
    text_parts.append("\nLog in to CareCue to review and take action.")
    
    return subject, "\n".join(html_parts), "\n".join(text_parts)


def _format_conflict_alert(patient_name: str, conflict_data: dict) -> tuple[str, str, str]:
    """Format medication conflict alert."""
    subject = f"CareCue: Medication Conflict Alert for {patient_name}"
    
    conflicts = conflict_data.get("conflicts", [])
    
    html_parts = [f"<h2>Medication Conflict Alert for {patient_name}</h2>"]
    text_parts = [f"Medication Conflict Alert for {patient_name}\n"]
    
    # Plain-language conflict type labels
    conflict_labels = {
        'duplicate_medication': 'Same medicine, different brand names',
        'duplicate_generic': 'Same medicine, different brand names',
        'therapeutic_duplication': 'Similar medicines from different doctors',
        'drug_interaction': 'These medicines may not work well together',
    }
    
    for conflict in conflicts:
        severity_color = {"high": "#dc2626", "medium": "#ea580c", "low": "#2563eb"}.get(conflict["severity"], "#2563eb")
        conflict_label = conflict_labels.get(conflict['type'], conflict['type'].replace('_', ' ').title())
        
        # Rewrite message to plain language
        msg = conflict.get('message', '')
        msg = msg.replace("Duplicate generic", "Same medicine (different brands)")
        msg = msg.replace("Duplicate medication", "Same medicine (different brands)")
        msg = msg.replace("Therapeutic duplication:", "Similar medicines:")
        msg = msg.replace("from different doctors", "from different doctors — check with them")
        
        html_parts.append(f"<h3 style='color: {severity_color};'>{conflict_label}</h3>")
        html_parts.append(f"<p>{msg}</p>")
        
        if "medication_name" in conflict:
            html_parts.append(f"<p><strong>Medicine:</strong> {conflict['medication_name']}</p>")
        if "prescribing_doctors" in conflict:
            html_parts.append(f"<p><strong>Prescribed by:</strong> {', '.join(conflict['prescribing_doctors'])}</p>")
        
        text_parts.append(f"\n{conflict_label}: {msg}")
    
    html_parts.append("<p>Check with the prescribing doctors if needed.</p>")
    text_parts.append("\nPlease review with the prescribing doctors.")
    
    return subject, "\n".join(html_parts), "\n".join(text_parts)


def _format_dose_pattern_alert(patient_name: str, pattern_data: dict) -> tuple[str, str, str]:
    """Format dose pattern alert."""
    subject = f"CareCue: Dose Pattern Alert for {patient_name}"
    
    html_parts = [f"<h2>Dose Pattern Alert for {patient_name}</h2>"]
    text_parts = [f"Dose Pattern Alert for {patient_name}\n"]
    
    missed_streaks = pattern_data.get("missed_streaks", [])
    adherence_rate = pattern_data.get("adherence_rate")
    
    if adherence_rate is not None:
        html_parts.append(f"<p><strong>Adherence Rate (30 days):</strong> {adherence_rate:.1f}%</p>")
        text_parts.append(f"Adherence Rate (30 days): {adherence_rate:.1f}%")
    else:
        html_parts.append("<p><strong>Adherence Rate (30 days):</strong> Insufficient data</p>")
        text_parts.append("Adherence Rate (30 days): Insufficient data")
    
    if missed_streaks:
        html_parts.append("<h3 style='color: #dc2626;'>Missed Dose Streaks</h3>")
        html_parts.append("<ul>")
        text_parts.append("\nMissed Dose Streaks:")
        for streak in missed_streaks:
            html_parts.append(f"<li>{streak['medication']}: {streak['consecutive_missed']} consecutive missed doses "
                            f"(last taken: {streak['last_taken']})</li>")
            text_parts.append(f"  - {streak['medication']}: {streak['consecutive_missed']} consecutive missed")
        html_parts.append("</ul>")
    
    html_parts.append("<p>Consider checking in on medication routine.</p>")
    text_parts.append("\nConsider checking in on medication routine.")
    
    return subject, "\n".join(html_parts), "\n".join(text_parts)


def _format_refill_drafted_alert(patient_name: str, draft_data: dict) -> tuple[str, str, str]:
    """Format refill drafted alert."""
    subject = f"CareCue: Refill Request Drafted for {patient_name}"
    
    drafts = draft_data.get("drafts", [])
    
    html_parts = [f"<h2>Refill Request Drafted for {patient_name}</h2>"]
    text_parts = [f"Refill Request Drafted for {patient_name}\n"]
    
    html_parts.append("<p>The following refill requests have been prepared:</p>")
    html_parts.append("<ul>")
    text_parts.append("\nPrepared Refills:")
    for draft in drafts:
        html_parts.append(f"<li><strong>{draft['medication_name']} {draft['strength']}</strong> — "
                        f"to {draft['pharmacy_name']} (qty: {draft['quantity']}, days supply: {draft['days_supply']})</li>")
        text_parts.append(f"  - {draft['medication_name']} {draft['strength']} to {draft['pharmacy_name']}")
    html_parts.append("</ul>")
    
    html_parts.append("<p>Review and approve to send to pharmacy.</p>")
    text_parts.append("\nReview and approve to send to pharmacy.")
    
    return subject, "\n".join(html_parts), "\n".join(text_parts)


ALERT_FORMATTERS = {
    AlertType.REFILL_DUE: _format_refill_alert,
    AlertType.REFILL_OVERDUE: _format_refill_alert,
    AlertType.CONFLICT_DETECTED: _format_conflict_alert,
    AlertType.DOSE_PATTERN: _format_dose_pattern_alert,
    AlertType.REFILL_DRAFTED: _format_refill_drafted_alert,
}


@tool
def send_alert_email(patient_id: str, alert_type: str, alert_data: dict) -> dict[str, Any]:
    """
    Send an alert email to the patient's caregiver.
    
    Args:
        patient_id: The patient ID
        alert_type: Type of alert (refill_due, refill_overdue, conflict_detected, dose_pattern, refill_drafted)
        alert_data: Data specific to the alert type
    
    Returns:
        Dict with success status and details. Never raises exceptions - always returns a result dict.
    """
    repo = get_repository()
    
    # Get patient and caregiver info
    patient = repo.get_patient(patient_id)
    if not patient:
        return {"success": False, "error": f"Patient {patient_id} not found", "alert_id": None}
    
    caregiver = repo.get_caregiver(patient.caregiver_id)
    if not caregiver:
        return {"success": False, "error": f"Caregiver for patient {patient_id} not found", "alert_id": None}
    
    # Format the alert
    try:
        alert_type_enum = AlertType(alert_type)
    except ValueError:
        return {"success": False, "error": f"Unknown alert type: {alert_type}", "alert_id": None}
    
    formatter = ALERT_FORMATTERS.get(alert_type_enum)
    if not formatter:
        return {"success": False, "error": f"No formatter for alert type: {alert_type}", "alert_id": None}
    
    subject, html_body, text_body = formatter(patient.name, alert_data)
    
    # Send email - never raise, always return result
    success, error_msg = _send_email(caregiver.email, subject, html_body, text_body)
    
    # Always create alert record in DB for audit trail, even if email fails
    # This ensures the agent run state is correctly recorded
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
    
    return {
        "success": success,
        "patient_id": patient_id,
        "caregiver_email": caregiver.email,
        "alert_type": alert_type,
        "alert_id": alert.id,
        "email_error": error_msg,  # None on success, error message on failure
    }


@tool
def send_test_email(to_email: str) -> dict[str, Any]:
    """Send a test email to verify SMTP configuration."""
    subject = "CareCue Test Email"
    html_body = "<h2>CareCue Test Email</h2><p>If you receive this, SMTP is configured correctly!</p>"
    text_body = "CareCue Test Email\n\nIf you receive this, SMTP is configured correctly!"
    
    success, error_msg = _send_email(to_email, subject, html_body, text_body)
    
    return {
        "success": success,
        "to": to_email,
        "message": "Test email sent" if success else f"Failed to send test email: {error_msg}",
        "error": error_msg,
    }