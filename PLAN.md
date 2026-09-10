# CareCue

**Track:** Everyday Agents — Agents for Humans Hackathon (Devpost)
**Deadline:** Sep 15, 2026, 5:30 AM GMT+5:30 (17 days from project kickoff)
**Builder:** Solo

---

## 1. Problem

Adult children who care for elderly parents remotely (or nearby) end up manually tracking medication logistics: when refills are due, whether pharmacy pickups happened, and whether instructions from different doctors conflict. This is unglamorous, easy to forget, and the failure mode is serious (missed doses, drug interactions, expired prescriptions).

## 2. Who it's for

Adult children managing an elderly parent's medications, primarily remote caregivers, but also usable by someone living nearby. Not a clinical tool — a logistics layer on top of care that already exists.

## 3. Why it matters

Nobody is building this because it isn't flashy. But it's a real, constant, low-grade burden on caregivers, and the cost of missing something (a lapsed refill, a drug conflict) is high. A quiet agent that only interrupts you when something actually needs a decision directly matches the hackathon's own framing: not another app to babysit, works in the background, surfaces only for real decisions.

## 4. What CareCue does

- Tracks a parent's prescriptions: dosage, refill cycle, prescribing doctor
- Watches refill dates and flags/initiates action before a prescription runs out
- Cross-checks instructions across multiple doctors for conflicts (duplicate meds, conflicting dosages)
- Detects missed-dose patterns from logged intake data
- Takes the safe autonomous action on its own (e.g. drafts/initiates a refill request) and only surfaces to the human caregiver when there's a real ambiguity or conflict to decide on

## 5. Architecture (draft — refine once build starts)

- **Agent layer (Strands SDK):** one primary agent to start; may split into a "Monitor" agent (watches data, tracks state) and a "Conflict-Checker" agent (cross-references instructions) if time allows, using Agents-as-Tools pattern
- **Tools (custom `@tool` functions):**
  - `refill_tracker` — checks refill dates against current date, flags upcoming/overdue
  - `conflict_checker` — cross-references multiple doctors' instructions for the same patient
  - `dose_pattern_checker` — looks for gaps in logged intake data
  - `notifier` — sends the caregiver an alert (email to start; SMS/other as stretch)
  - `refill_drafter` — drafts/initiates the refill action automatically for the non-ambiguous case
- **Data layer:** synthetic data to start — SQLite or JSON/CSV simulating prescriptions, refill history, doctor instructions, dose logs
- **Interface:** minimal — a lightweight setup UI (Streamlit or simple FastAPI+HTML) for entering a parent's prescriptions initially; primary interaction is the agent's outbound notification, not a dashboard
- **Scheduling:** cron job or `schedule` library running the agent check on an interval (daily, simulated as more frequent for demo purposes)
- **Model provider:** Anthropic direct to start (fast setup, no Bedrock approval wait); note Bedrock-compatibility as a possible stretch mention
- **Stretch:** deploy to Amazon Bedrock AgentCore for the live-demo-link bonus and Technical Implementation score boost — only attempt once core logic is solid

## 6. Judging criteria — how this project addresses each

- **Technological Implementation:** genuine multi-tool agent, state/session persistence across days, possible multi-agent split, optional AgentCore deployment
- **Design:** minimal setup UI + notification-first interaction model = a coherent product experience, not just a backend script
- **Potential Impact:** specific, credible, verifiable audience and problem — not hypothetical
- **Creativity & Originality:** unglamorous, underserved niche; genuine understanding of the caregiving logistics problem space
- **Presentation:** demo video shows the agent running on schedule, then firing a real notification — makes the "runs quietly, surfaces only when needed" behavior visible, not just described

## 7. Build timeline (17 days, solo)

- **Days 1–2:** Strands SDK basics — env setup, quickstart running, AWS Builder ID done, repo scaffolded
- **Days 3–6:** Build core tools (refill tracker, conflict-checker, notifier), synthetic data structure
- **Days 7–9:** Add dose-pattern detection + refill-drafting (the "autonomous safe action" piece); split into 2 agents if time allows; wire up state/session persistence
- **Days 10–12:** Buffer for bugs; build minimal setup UI; polish end-to-end flow
- **Days 13–15:** Record demo video (≤5 min: problem → who it's for → why it matters → live walkthrough), write text description, finalize README
- **Days 16–17:** Buffer, submit early — do not cut it to the deadline

## 8. Submission checklist

- [ ] Text description (problem, audience, mechanics)
- [ ] Public GitHub repo — code, assets, setup instructions, MIT/Apache license visible in About, README
- [ ] Architecture diagram
- [ ] Demo video (≤5 min, covers problem / who it's for / why it matters, working demo)
- [ ] AWS Builder ID
- [ ] (Optional) Live demo link — stretch goal via AgentCore or free hosting

## 9. Open questions / decisions to revisit

- Single agent vs. two-agent split — decide once core tools are working
- Notification channel: email only, or add SMS/WhatsApp if time allows
- Whether to attempt AgentCore deployment at all given solo/17-day constraint