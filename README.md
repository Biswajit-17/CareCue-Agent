# CareCue — Medication Logistics Agent

CareCue tracks prescriptions, detects conflicts, monitors adherence, and sends Telegram reminders for Indian-context elderly care. Patients confirm doses by replying YES or NO directly on Telegram — no links, no dashboard, no app.

## Quick Start

### 1. Install dependencies

```bash
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create a Telegram bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`, follow the prompts
3. Choose a name (e.g. `CareCue`) and username (e.g. `CareCueBot`)
4. BotFather gives you a bot token — copy it

### 3. Configure environment

Copy `.env.example` to `.env` and fill in:

```env
OPENROUTER_API_KEY="sk-or-v1-..."       # LLM provider
GMAIL_SMTP_USER="you@gmail.com"         # Caregiver email alerts
GMAIL_SMTP_APP_PASSWORD="xxxx"          # Gmail app password
APP_URL="http://127.0.0.1:8000"         # Dashboard URL
TELEGRAM_BOT_TOKEN="123456789:ABC..."   # From BotFather
```

### 4. Seed the database

```bash
python -m data.seed --reset
```

### 5. Start the server

```bash
uvicorn ui.api:app --host 127.0.0.1 --port 8000
```

### 6. Expose a public webhook URL (ngrok)

Telegram needs a public HTTPS URL to deliver inbound messages.

```bash
# Install ngrok: https://ngrok.com/download
ngrok http 8000
```

Copy the `https://xxxx.ngrok-free.app` URL.

### 7. Register the webhook with Telegram

```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=https://xxxx.ngrok-free.app/telegram/webhook"
```

You should get: `{"ok":true,"result":...,"description":"Webhook was set"}`

### 8. Link a patient to Telegram

1. Open the dashboard at `http://127.0.0.1:8000`
2. Go to Patients → select a patient → Manage Medications
3. Click **Generate linking code** in the Telegram section
4. On the patient's phone, open Telegram and send:
   ```
   /start A1B2C3D4
   ```
   to `@CareCueBot` (replace `A1B2C3D4` with the code shown)
5. The bot replies: "Linked! You will now receive dose reminders for Meenakshi."

### 9. Test the flow

1. Trigger a reminder (see below)
2. The patient receives a Telegram message
3. Reply YES or NO
4. Check the dashboard — the DoseLog appears

#### Trigger a reminder manually

```bash
python -c "
from tools.dose_reminder_sender import send_dose_reminder
from datetime import datetime
slot = datetime.now().replace(second=0, microsecond=0).isoformat()
r = send_dose_reminder('01ARZ3NDEKTSV4RRFFQ69G5FB0', slot)
print(r)
"
```

Or run the full scheduler:

```bash
python main.py --once
```

## How Telegram Dose Confirmation Works

```
┌─────────────────┐      ┌─────────┐      ┌────────────┐
│  Scheduler runs  │─────>│Telegram │─────>│  Patient   │
│  every hour      │      │  Bot    │      │  receives  │
│                  │      │  API    │      │  Telegram  │
└─────────────────┘      └─────────┘      └─────┬──────┘
                                                │
                                          Reply YES / NO
                                                │
                                          ┌─────v──────┐
                                          │  Telegram  │
                                          │  webhook   │
                                          │  POST      │
                                          │  /telegram │
                                          │  /webhook  │
                                          └─────┬──────┘
                                                │
                                          ┌─────v──────┐
                                          │  CareCue   │
                                          │  records   │
                                          │  DoseLog   │
                                          └────────────┘
```

- **One pending reminder per patient**: if a patient already has an unanswered reminder, new ones are skipped until the patient replies or the reminder expires (6 hours).
- **No token in Telegram**: the patient's Telegram `chat_id` IS the identifier. The webhook extracts `chat_id` from the inbound message and matches it to the patient.
- **Unrecognized replies**: auto-responds with "Sorry, reply YES or NO."
- **Patient linking**: each patient gets a unique linking code. They send `/start <CODE>` to the bot once to connect their Telegram account.

## Architecture

| Layer | Technology | File |
|-------|-----------|------|
| Agent | Strands SDK + OpenRouter | `agent/core.py` |
| Tools | refill_tracker, conflict_checker, dose_reminder_sender, notifier, dose_pattern_checker, refill_drafter | `tools/` |
| API | FastAPI | `ui/api.py` |
| Frontend | Vanilla JS, Figtree/Noto Sans | `ui/static/` |
| Database | SQLite | `data/carecue.db` |
| Scheduler | `schedule` library | `scheduler.py` |
| Messaging | Telegram Bot API | `tools/dose_reminder_sender.py` |

## CLI Usage

```bash
# Run daily check once (demo mode)
python main.py --once

# Run continuous scheduler (production)
python main.py --schedule

# Check specific patient
python main.py --patient <id>

# Show recent run history
python main.py --history

# Send test email to caregiver
python main.py --test-email you@example.com
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET/POST | `/api/caregivers` | List/create caregivers |
| GET/PUT/DELETE | `/api/caregivers/{id}` | Caregiver CRUD |
| GET/POST | `/api/patients` | List/create patients |
| GET/PUT/DELETE | `/api/patients/{id}` | Patient CRUD |
| POST | `/api/patients/{id}/telegram-link` | Generate Telegram linking code |
| GET/POST | `/api/doctors` | List/create doctors |
| GET/PUT/DELETE | `/api/doctors/{id}` | Doctor CRUD |
| GET/POST | `/api/pharmacies` | List/create pharmacies |
| GET/PUT/DELETE | `/api/pharmacies/{id}` | Pharmacy CRUD |
| GET/POST | `/api/prescriptions` | List/create prescriptions |
| GET/PUT/DELETE | `/api/prescriptions/{id}` | Prescription CRUD |
| GET/POST | `/api/refills` | List/create refills |
| PUT/DELETE | `/api/refills/{id}` | Refill update/delete |
| GET | `/api/dashboard` | Dashboard data |
| GET | `/api/medications` | All medications (cross-patient) |
| POST | `/telegram/webhook` | Telegram inbound webhook |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No Telegram message received | Check ngrok is running, webhook is registered, bot token is correct |
| "No CareCue account linked" | Patient hasn't linked yet — generate a code and send `/start <CODE>` to the bot |
| "Invalid linking code" | Code was already used or doesn't exist — generate a new one |
| "No pending dose reminder" | The reminder expired (6 hours) or you already replied — trigger a new one |
| Webhook registration fails | Make sure ngrok is running and the URL is correct; check with `curl` |
| Bot doesn't respond | Verify `TELEGRAM_BOT_TOKEN` in `.env` matches what BotFather gave you |
