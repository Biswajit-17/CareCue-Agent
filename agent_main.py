"""CareCue Agent - Main entry point."""

import sys
import argparse
from dotenv import load_dotenv

load_dotenv()

from agent.core import create_agent, run_daily_check, run_patient_check
from agent.state import get_agent_state


def main():
    parser = argparse.ArgumentParser(description="CareCue Medication Agent")
    parser.add_argument("--once", action="store_true", help="Run daily check once and exit")
    parser.add_argument("--patient", type=str, help="Run check for specific patient ID")
    parser.add_argument("--test-email", type=str, help="Send test email to address")
    parser.add_argument("--history", action="store_true", help="Show recent run history")
    parser.add_argument("--schedule", action="store_true", help="Run scheduler (daily)")
    
    args = parser.parse_args()
    
    if args.test_email:
        from tools.notifier import send_test_email
        result = send_test_email(args.test_email)
        print(f"Test email: {result}")
        return
    
    if args.history:
        state = get_agent_state()
        import json
        runs = state.get_recent_runs(10)
        print("Recent Agent Runs:")
        for run in runs:
            errors = json.loads(run['errors']) if run['errors'] else []
            print(f"  {run['id']} | {run['run_type']} | {run['started_at'][:19]} | {run['status']} | "
                  f"patients: {run['patients_checked']} | alerts: {run['alerts_sent']}/{run['alerts_generated']}")
            if errors:
                for err in errors:
                    print(f"    ERROR: {err}")
        return
    
    if args.patient:
        result = run_patient_check(args.patient)
        print(f"Patient Check Results for {result.get('patient_name', 'Unknown')}:")
        print(f"  Refills: {result['refills']['summary']}")
        print(f"  Conflicts: {result['conflicts']['conflicts_found']} found")
        for c in result['conflicts']['conflicts']:
            print(f"    - {c['type']} ({c['severity']}): {c['message']}")
        print(f"  Dose Patterns: adherence={result['dose_patterns']['adherence_rate']}%, "
              f"streaks={len(result['dose_patterns']['missed_streaks'])}")
        return
    
    if args.once:
        print("Running daily check once...")
        result = run_daily_check()
        print(f"Run ID: {result['run_id']}")
        print(f"Patients checked: {result['patients_checked']}")
        print(f"Alerts generated: {result['alerts_generated']}")
        print(f"Alerts sent: {result['alerts_sent']}")
        if result['errors']:
            print("Errors:")
            for err in result['errors']:
                print(f"  - {err}")
        return
    
    if args.schedule:
        print("Starting scheduler... (not implemented yet, use --once for now)")
        return
    
    # Default: interactive agent
    print("Starting CareCue Agent (interactive mode)...")
    agent = create_agent()
    print("Agent ready. Type 'help' for commands or 'exit' to quit.")
    
    while True:
        try:
            user_input = input("\n> ").strip()
            if user_input.lower() in ('exit', 'quit'):
                break
            if user_input.lower() == 'help':
                print("Commands:")
                print("  run daily check    - Run full daily check for all patients")
                print("  check patient <id> - Run check for specific patient")
                print("  history            - Show recent run history")
                print("  exit               - Quit")
                continue
            
            if user_input.startswith("check patient"):
                parts = user_input.split()
                if len(parts) >= 3:
                    result = run_patient_check(parts[2])
                    print(f"Patient: {result.get('patient_name', 'Unknown')}")
                    print(f"  Refills: {result['refills']['summary']}")
                    print(f"  Conflicts: {result['conflicts']['conflicts_found']}")
                    for c in result['conflicts']['conflicts']:
                        print(f"    - {c['type']} ({c['severity']}): {c['message']}")
                continue
            
            if user_input == "run daily check":
                result = run_daily_check()
                print(f"Run ID: {result['run_id']}")
                print(f"Patients: {result['patients_checked']}, Alerts: {result['alerts_sent']}/{result['alerts_generated']}")
                continue
            
            if user_input == "history":
                state = get_agent_state()
                runs = state.get_recent_runs(5)
                for run in runs:
                    print(f"  {run['id']} | {run['started_at']} | {run['status']} | {run['alerts_sent']} alerts")
                continue
            
            # Otherwise, let the agent handle it
            response = agent(user_input)
            print(response)
            
        except KeyboardInterrupt:
            break
        except EOFError:
            break
        except Exception as e:
            print(f"Error: {e}")
    
    print("Goodbye!")


if __name__ == "__main__":
    main()