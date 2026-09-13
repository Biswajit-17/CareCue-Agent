"""CareCue AgentCore Runtime Entrypoint.

Thin wrapper that imports the existing Strands agent and exposes it
via AgentCore's @app.entrypoint contract. Uses BedrockModel instead
of OpenRouter since AgentCore runs on AWS with native Bedrock access.
"""

import sys
import io
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

CRITICAL - Status reporting:
- ONLY report facts that appear in tool results. Never invent, assume, or fabricate error messages.
- If the tool returns success, say it succeeded. If the tool returns an error, quote the exact error from the tool result.
- Never add hedging language like "manual review recommended" unless the tool result explicitly says so.
- Never say emails failed if the tool result shows email_status: "SENT".
- Example CORRECT: "Email sent to caregiver@example.com" (tool returned email_status: "SENT")
- Example WRONG: "Email failed due to database error" (tool did NOT return this - you fabricated it)

Be concise. Focus on actionable information. Don't explain your reasoning unless asked."""

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


@app.entrypoint
def invoke(payload):
    """AgentCore calls this with {"prompt": "..."}."""
    prompt = payload.get("prompt", "Run daily check for all patients")
    result = agent(prompt)
    return {"result": str(result)}


if __name__ == "__main__":
    app.run()
