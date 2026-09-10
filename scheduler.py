"""CareCue Scheduler - Runs daily medication checks using schedule library."""

import schedule
import time
import threading
from datetime import datetime
from typing import Optional

from agent.core import run_daily_check
from agent.state import get_agent_state
from tools.dose_reminder_sender import send_due_dose_reminders
from tools.notifier import _send_email, _format_no_response_alert
from data.repository import get_repository
from data.models import DoseToken


class CareCueScheduler:
    """Manages scheduled daily runs of the CareCue agent."""
    
    def __init__(self, run_time: str = "08:00"):
        """
        Initialize scheduler.
        
        Args:
            run_time: Time to run daily check (HH:MM 24-hour format)
        """
        self.run_time = run_time
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    def run_once(self) -> dict:
        """Run the daily check once and return results."""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Running daily check...")
        result = run_daily_check()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Run {result['run_id']}: "
              f"{result['patients_checked']} patients, "
              f"{result['alerts_sent']}/{result['alerts_generated']} alerts sent/generated")
        if result['errors']:
            for err in result['errors']:
                print(f"  ERROR: {err}")
        return result
    
    def run_dose_reminders(self) -> dict:
        """Check for due doses and send patient reminders."""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking due doses...")
        result = send_due_dose_reminders()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Dose reminders: "
              f"{result['reminders_sent']} sent, "
              f"{len(result['skipped'])} skipped, "
              f"{len(result['errors'])} errors")
        for err in result['errors']:
            print(f"  ERROR: {err}")
        return result

    def run_no_response_checks(self) -> dict:
        """Check for tokens past grace period and send caregiver escalation alerts.

        Finds pending tokens where scheduled_time + NO_RESPONSE_GRACE_MINUTES
        has elapsed, sends one informational email per token, and marks them
        as alerted to prevent duplicate sends.
        """
        repo = get_repository()
        grace_minutes = DoseToken.NO_RESPONSE_GRACE_MINUTES
        tokens = repo.get_pending_tokens_past_grace(grace_minutes)
        
        sent = 0
        skipped = 0
        errors = []
        
        for token in tokens:
            try:
                patient = repo.get_patient(token.patient_id)
                if not patient:
                    skipped += 1
                    continue
                
                caregiver = repo.get_caregiver(patient.caregiver_id)
                if not caregiver or not caregiver.email:
                    skipped += 1
                    continue
                
                prescription = repo.get_prescription(token.prescription_id)
                if not prescription:
                    skipped += 1
                    continue
                
                medication = f"{prescription.medication_name} {prescription.strength}"
                scheduled_str = token.scheduled_time.strftime("%I:%M %p on %B %d")
                
                escalation_data = {
                    "medication": medication,
                    "scheduled_time": scheduled_str,
                }
                
                subject, html_body, text_body = _format_no_response_alert(patient.name, escalation_data)
                
                success, error_msg = _send_email(caregiver.email, subject, html_body, text_body)
                
                if success:
                    repo.mark_token_alerted(token.token)
                    sent += 1
                else:
                    errors.append(f"Failed to send no-response alert for {patient.name}: {error_msg}")
            except Exception as e:
                errors.append(f"Error processing token for patient {token.patient_id}: {e}")
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] No-response checks: "
              f"{sent} alerts sent, {skipped} skipped, {len(errors)} errors")
        for err in errors:
            print(f"  ERROR: {err}")
        
        return {"alerts_sent": sent, "skipped": skipped, "errors": errors}

    def _run_loop(self):
        """Background loop that runs schedule."""
        schedule.every().day.at(self.run_time).do(self.run_once)
        schedule.every().hour.at(":05").do(self.run_dose_reminders)
        schedule.every(15).minutes.do(self.run_no_response_checks)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Scheduler started - daily run at {self.run_time}, dose reminders hourly, no-response checks every 15 min")
        
        while self._running:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    def start(self) -> None:
        """Start the scheduler in background thread."""
        if self._running:
            print("Scheduler already running")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
    
    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        schedule.clear()
        if self._thread:
            self._thread.join(timeout=5)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Scheduler stopped")


# Global scheduler instance
_scheduler: Optional[CareCueScheduler] = None


def get_scheduler(run_time: str = "08:00") -> CareCueScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = CareCueScheduler(run_time)
    return _scheduler


def run_scheduler_forever(run_time: str = "08:00") -> None:
    """
    Run scheduler in foreground (blocking).
    Use this for production deployment.
    """
    scheduler = get_scheduler(run_time)
    scheduler._run_loop()  # Run in foreground


def run_once() -> dict:
    """Convenience function for --once mode."""
    scheduler = get_scheduler()
    return scheduler.run_once()