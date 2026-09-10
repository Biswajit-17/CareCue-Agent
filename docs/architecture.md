# CareCue System Architecture

```mermaid
flowchart TB
    subgraph External["External Services"]
        direction LR
        OR["OpenRouter<br/>LLM Provider<br/>(Claude Sonnet)"]
        TG["Telegram Bot API<br/>Patient dose reminders<br/>& confirmation replies"]
        GMAIL["Gmail SMTP<br/>Caregiver email alerts"]
    end

    subgraph Scheduler["Scheduler — scheduler.py"]
        direction LR
        SCHED["Daily: refill + conflict checks<br/>Hourly: dose reminders<br/>Every 15 min: no-response escalation"]
    end

    subgraph Agent["Strands Agent — agent/"]
        direction TB
        CORE["core.py<br/>Primary Agent<br/>Tool orchestration + dedup"]
        STATE["state.py<br/>Session state<br/>Run tracking"]
        AGENT_MAIN["agent_main.py<br/>Agent entry point"]
    end

    subgraph Tools["Agent Tools — tools/"]
        direction TB
        T1["refill_tracker<br/>Detect overdue/due-soon refills"]
        T2["conflict_checker<br/>Drug class overlap detection<br/>Uses data/drug_classes.json"]
        T3["dose_pattern_checker<br/>30-day adherence calc"]
        T4["refill_drafter<br/>Draft refill requests"]
        T5["notifier<br/>Email alerts via Gmail SMTP"]
        T6["dose_reminder_sender<br/>Telegram messages via Bot API"]
    end

    subgraph DrugRef["Reference Data"]
        DRUGS["data/drug_classes.json<br/>15 drug classes<br/>WHO ATC verified<br/>Indian brand names"]
    end

    subgraph Data["Data Layer — data/"]
        direction TB
        REPO["repository.py<br/>SQLite CRUD<br/>Telegram linking methods"]
        DB[("carecue.db<br/>SQLite Database<br/>patients, prescriptions,<br/>dose_logs, tokens,<br/>linking_codes, alerts")]
        MODELS["models.py<br/>Patient, Prescription,<br/>Refill, DoseLog,<br/>DoseToken (no_response_alerted),<br/>Doctor, Pharmacy, Alert"]
        SEED["seed.py + seed/*.json<br/>Indian-context test data"]
    end

    subgraph API["API Layer — ui/api.py"]
        direction TB
        FASTAPI["FastAPI Server<br/>Port 8000"]
        REST["REST Endpoints<br/>patients, prescriptions,<br/>doctors, pharmacies,<br/>refills, dashboard"]
        WEBHOOK["POST /telegram/webhook<br/>Inbound Telegram messages"]
        LINK["POST /api/patients/:id/telegram-link<br/>Generate linking code"]
    end

    subgraph Frontend["Frontend — ui/static/"]
        direction LR
        HTML["index.html<br/>SPA shell"]
        CSS["styles.css<br/>Dark/light theme"]
        JS["app.js<br/>Hash routing, CRUD,<br/>form validation"]
    end

    %% Scheduler triggers agent
    SCHED -->|"daily + hourly"| CORE

    %% Agent uses tools
    CORE --> T1
    CORE --> T2
    CORE --> T3
    CORE --> T4
    CORE --> T5
    CORE --> T6

    %% Agent state
    CORE <--> STATE

    %% Agent model provider
    CORE <-->|"LLM calls"| OR

    %% Tools use data layer
    T1 --> REPO
    T2 --> REPO
    T2 --> DRUGS
    T3 --> REPO
    T4 --> REPO
    T5 --> REPO
    T6 --> REPO

    %% Outbound channels
    T5 -->|"caregiver alerts"| GMAIL
    T6 -->|"patient reminders"| TG

    %% Inbound Telegram replies
    TG -->|"YES/NO replies"| WEBHOOK

    %% Data layer
    REPO <--> DB
    MODELS -.-> REPO
    SEED -.-> DB

    %% API layer
    FASTAPI --> REPO
    REST --> FASTAPI
    WEBHOOK --> FASTAPI
    LINK --> FASTAPI
    TG -->|"inbound messages"| WEBHOOK

    %% Frontend to API
    HTML --> FASTAPI
    CSS --> FASTAPI
    JS --> FASTAPI

    %% Styling
    classDef external fill:#e8d5f5,stroke:#7b2d8e,stroke-width:2px,color:#1a1a2e
    classDef agent fill:#d5e8f5,stroke:#2d5f8e,stroke-width:2px,color:#1a1a2e
    classDef tools fill:#f5e8d5,stroke:#8e5f2d,stroke-width:2px,color:#1a1a2e
    classDef data fill:#d5f5e8,stroke:#2d8e5f,stroke-width:2px,color:#1a1a2e
    classDef api fill:#f5d5d5,stroke:#8e2d2d,stroke-width:2px,color:#1a1a2e
    classDef frontend fill:#f5f5d5,stroke:#8e8e2d,stroke-width:2px,color:#1a1a2e
    classDef scheduler fill:#e0e0e0,stroke:#555,stroke-width:2px,color:#1a1a2e

    class OR,TG,GMAIL external
    class CORE,STATE,AGENT_MAIN agent
    class T1,T2,T3,T4,T5,T6 tools
    class REPO,DB,MODELS,SEED,DRUGS data
    class FASTAPI,REST,WEBHOOK,LINK api
    class HTML,CSS,JS frontend
    class SCHED scheduler
```



## Data flow summary

1. **Scheduler** triggers the Strands Agent on a daily schedule (and hourly for dose reminders)
2. **Agent** calls 6 tools to check refills, conflicts, adherence, and send notifications
3. **Tools** read/write through `data/repository.py` to the SQLite database
4. **conflict_checker** also reads `data/drug_classes.json` (15 WHO ATC-verified drug classes) for therapeutic overlap detection
5. **notifier** sends caregiver alerts via Gmail SMTP
6. **dose_reminder_sender** sends patient reminders via Telegram Bot API
7. Patients reply YES/NO on Telegram → **webhook** receives the message → records dose log
8. **No-response escalation** (every 15 min): if patient hasn't replied within 90 minutes, caregiver gets an informational email — calm tone, not alarming
9. **FastAPI** serves the REST API and frontend dashboard independently, sharing the same data layer
