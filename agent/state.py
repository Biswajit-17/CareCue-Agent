"""Agent State Persistence - Tracks agent runs, alerts sent, and checkpoints."""

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from data.models import Alert


STATE_DB_PATH = Path(__file__).parent.parent / "data" / "agent_state.db"


# Agent state schema
STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_runs (
    id TEXT PRIMARY KEY,
    run_type TEXT NOT NULL,  -- 'scheduled', 'manual', 'test'
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,  -- 'running', 'completed', 'failed'
    patients_checked INTEGER DEFAULT 0,
    alerts_generated INTEGER DEFAULT 0,
    alerts_sent INTEGER DEFAULT 0,
    errors TEXT,  -- JSON array
    metadata TEXT  -- JSON
);

CREATE TABLE IF NOT EXISTS alert_history (
    id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES agent_runs(id),
    patient_id TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    alert_severity TEXT NOT NULL,
    alert_id TEXT REFERENCES alerts(id),
    sent_at TEXT,
    delivery_status TEXT,  -- 'sent', 'failed', 'skipped'
    error TEXT
);

CREATE TABLE IF NOT EXISTS checkpoints (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,  -- JSON
    updated_at TEXT NOT NULL
);
"""


def get_state_connection():
    """Get connection to state database."""
    conn = sqlite3.connect(STATE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_state_db() -> None:
    """Initialize the agent state database."""
    with get_state_connection() as conn:
        conn.executescript(STATE_SCHEMA)
        conn.commit()


class AgentState:
    """Manages agent run state and history."""
    
    def __init__(self):
        init_state_db()
    
    def start_run(self, run_type: str = "scheduled", metadata: dict = None) -> str:
        """Start a new agent run, return run_id."""
        import uuid
        run_id = str(uuid.uuid4())[:8]
        
        with get_state_connection() as conn:
            conn.execute("""
                INSERT INTO agent_runs (id, run_type, started_at, status, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (run_id, run_type, datetime.utcnow().isoformat(), "running", 
                  json.dumps(metadata or {})))
            conn.commit()
        
        return run_id
    
    def complete_run(self, run_id: str, status: str = "completed", 
                     patients_checked: int = 0, alerts_generated: int = 0,
                     alerts_sent: int = 0, errors: list = None) -> None:
        """Mark a run as completed."""
        with get_state_connection() as conn:
            conn.execute("""
                UPDATE agent_runs SET
                    completed_at = ?,
                    status = ?,
                    patients_checked = ?,
                    alerts_generated = ?,
                    alerts_sent = ?,
                    errors = ?
                WHERE id = ?
            """, (datetime.utcnow().isoformat(), status, patients_checked,
                  alerts_generated, alerts_sent, json.dumps(errors or []), run_id))
            conn.commit()
    
    def record_alert(self, run_id: str, patient_id: str, alert_type: str,
                     alert_severity: str, alert_id: str, 
                     delivery_status: str = "sent", error: str = None) -> None:
        """Record an alert sent during a run."""
        import uuid
        history_id = str(uuid.uuid4())[:8]
        
        with get_state_connection() as conn:
            conn.execute("""
                INSERT INTO alert_history 
                (id, run_id, patient_id, alert_type, alert_severity, alert_id, sent_at, delivery_status, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (history_id, run_id, patient_id, alert_type, alert_severity,
                  alert_id, datetime.utcnow().isoformat(), delivery_status, error))
            conn.commit()
    
    def get_recent_runs(self, limit: int = 10) -> list[dict]:
        """Get recent agent runs."""
        with get_state_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM agent_runs ORDER BY started_at DESC LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]
    
    def get_alert_history(self, patient_id: str = None, limit: int = 50) -> list[dict]:
        """Get alert delivery history."""
        with get_state_connection() as conn:
            if patient_id:
                rows = conn.execute("""
                    SELECT * FROM alert_history WHERE patient_id = ? ORDER BY sent_at DESC LIMIT ?
                """, (patient_id, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM alert_history ORDER BY sent_at DESC LIMIT ?
                """, (limit,)).fetchall()
            return [dict(r) for r in rows]
    
    def set_checkpoint(self, key: str, value: Any) -> None:
        """Set a checkpoint value (JSON serializable)."""
        with get_state_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO checkpoints (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, json.dumps(value), datetime.utcnow().isoformat()))
            conn.commit()
    
    def get_checkpoint(self, key: str, default: Any = None) -> Any:
        """Get a checkpoint value."""
        with get_state_connection() as conn:
            row = conn.execute("SELECT value FROM checkpoints WHERE key = ?", (key,)).fetchone()
            if row:
                return json.loads(row["value"])
            return default
    
    def get_last_run_summary(self) -> dict:
        """Get summary of last completed run."""
        with get_state_connection() as conn:
            row = conn.execute("""
                SELECT * FROM agent_runs WHERE status = 'completed' ORDER BY completed_at DESC LIMIT 1
            """).fetchone()
            if row:
                return dict(row)
            return {}


# Singleton
_agent_state: Optional[AgentState] = None


def get_agent_state() -> AgentState:
    global _agent_state
    if _agent_state is None:
        _agent_state = AgentState()
    return _agent_state