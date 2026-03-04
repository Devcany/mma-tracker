# 🦞 MMA Training Tracker

> Voice-first training log. No forms. No app. Just talk.

An agent-first system where athletes log training sessions by sending a voice note or free text to a Telegram bot. A Claude-backed AI agent interprets natural language, extracts structure, and persists data — without ever requiring a fixed input schema.

---

## What it does

Send this to the bot:

> *"Had a brutal sparring session today, 6 rounds, couldn't finish the last one — RPE was probably an 8"*

The agent logs it as:

```
session_type: sparring
rounds:       6
intensity:    8
date:         today
notes:        "couldn't finish the last round"
raw_input:    [original message, always preserved]
```

No form. No menu. No friction.

---

## Why this architecture matters

Most training apps fail at input. Athletes don't log because logging is work.

This system inverts the problem: the AI does the work of structuring data. The user just talks.

**Stack:**
- `Telegram Bot` — interface and auth (chat_id as user identity)
- `OpenAI Whisper API` — speech-to-text with local model fallback
- `Claude (claude-sonnet)` — NLU, intent detection, field extraction
- `FastAPI` — REST backend
- `SQLite` — persistence
- `systemd` — production deployment, auto-restart on crash

**Agent behavior:**
- Accepts incomplete, unordered, conversational input
- Never blocks on missing fields — partial data is valid data
- Always preserves `raw_input` for reparse and debugging
- Scoped per user — multi-tenant via Telegram `chat_id`
- Schema-ready for group/coach features (inactive in v0.1)

---

## Queries work the same way

```
User:  "what did I do this week?"
Agent: 4 sessions — 2x sparring, 1x drilling, 1x S&C
       Total: 5h 20min | Avg RPE: 7.5
```

```
User:  "how was my last BJJ session?"
Agent: Tuesday · 75 min · RPE 6 · "focused on half guard transitions"
```

---

## Data model

```
users          — id (Telegram chat_id), name, role (athlete|coach)
sessions       — user_id, date, session_type, duration_min, rounds,
                 intensity_rpe, notes, raw_input
groups         — id, name, coach_id          [schema-ready, v0.2]
group_members  — group_id, user_id           [schema-ready, v0.2]
```

Full specification: [`docs/spec.md`](docs/spec.md)

---

## Run it

```bash
git clone https://github.com/Devcany/mma-tracker
cd mma-tracker
cp .env.example .env   # add TELEGRAM_TOKEN, ANTHROPIC_API_KEY, OPENAI_API_KEY
pip install -r requirements.txt
./run_api.sh           # FastAPI on :8000
./run_bot.sh           # Telegram bot
```

**Production (systemd):**
```bash
systemctl status mma-api mma-bot
tail -f /var/log/mma-api.log
```

---

## This is a reference implementation

The pattern here — **natural language in → structured data out → queryable over time** — applies beyond sports tracking.

The same architecture works for:
- Maintenance logs in manufacturing ("machine 4 threw an error, changed filter, back online")
- Field service reports ("visited client, replaced unit 3, follow-up needed in 2 weeks")
- Shift handover notes in production environments

If you're building something in this space or want to talk about adapting this pattern for your use case — reach out.

---

## Built with

[Claude](https://anthropic.com) · [OpenAI Whisper](https://openai.com/research/whisper) · [FastAPI](https://fastapi.tiangolo.com) · [python-telegram-bot](https://python-telegram-bot.org)

---

*v0.1.0 — spec-complete, production-deployed*
