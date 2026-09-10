"""CareCue Scheduler - Runs daily medication checks using schedule library."""

import schedule
import time
import threading
from datetime import datetime
from typing import Optional

from agent.core import run_daily_check
from agent.state import get_agent_state
from tools.dose_reminder_sender import send_due_dose_reminders


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

    def _run_loop(self):
        """Background loop that runs schedule."""
        schedule.every().day.at(self.run_time).do(self.run_once)
        schedule.every().hour.at(":05").do(self.run_dose_reminders)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Scheduler started - daily run at {self.run_time}, dose reminders hourly")
        
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