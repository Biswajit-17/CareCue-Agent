"""CareCue AgentCore Runtime Entrypoint.

Thin wrapper that imports the existing Strands agent and exposes it
via AgentCore's @app.entrypoint contract. Uses BedrockModel instead
of OpenRouter since AgentCore runs on AWS with native Bedrock access.
"""

import sys
import io
import re
from pathlib import Path

# Fix Windows cp1252 encoding issue for emoji in model responses
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add project root to path so we can import our existing modules
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
from tools.notifier import get_and_clear_email_results

app = BedrockAgentCoreApp()

# Use Bedrock model - AWS credentials are available in AgentCore Runtime
# Claude Haiku 4.5: $1.00/$5.00 per 1M tokens
model = BedrockModel(model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0")

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

Do NOT include any section about email/alert delivery status in your response. That will be appended automatically."""

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
        send_alert_email,
        send_test_email,
    ],
)


def _strip_email_status(text: str) -> str:
    """Remove any LLM-generated email/alert status lines from the response."""
    # Patterns that Haiku uses to describe email status (varies each run)
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


def _build_deterministic_email_status() -> str:
    """Build email status section from actual tool results, not LLM output."""
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
    
    # Clear any previous email results
    get_and_clear_email_results()
    
    # Run agent - LLM generates patient summary, tools send emails
    result = agent(prompt)
    llm_text = str(result)
    
    # Strip any fabricated email status from LLM output
    cleaned_text = _strip_email_status(llm_text)
    
    # Build deterministic email status from actual tool results
    email_status = _build_deterministic_email_status()
    
    # Combine: LLM patient summary + deterministic email status
    if email_status:
        final_response = f"{cleaned_text}\n\n{email_status}"
    else:
        final_response = cleaned_text
    
    return {"result": final_response}


if __name__ == "__main__":
    app.run()
