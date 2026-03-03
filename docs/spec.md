# MMA Training Tracker – Product Specification
**Version:** 0.1 MVP  
**Date:** 2026-03-03  
**Repo:** github.com/Devcany/mma-tracker  
**Agent:** KLAW (OpenClaw)  
**Status:** MVP Reactive – Schema future-proof for proactive features

---

## 1. Vision

A voice-first, agent-driven training tracker for MMA athletes and coaches. No forms. No fixed input schema. The user speaks or types naturally – KLAW interprets intent, extracts structure, and persists data. The system is as frictionless as sending a Telegram message.

**Primary User:** The athlete who is also their own coach. Ambitious, time-poor, post-training exhausted. They will not fill out forms. They will send a voice note.

**Secondary User:** The coach managing multiple athletes and training groups. Needs aggregated views, group formation, and per-athlete trend analysis – on demand, no dashboard required.

---

## 2. Architecture

```
Whisper (local STT)
      ↓
Telegram Bot (Interface + Auth via chat_id)
      ↓
KLAW / OpenClaw (NLU + Intent Resolution + Tool Calls)
      ↓
FastAPI (Business Logic + REST endpoints)
      ↓
SQLite (Persistence – Hetzner Server)
```

**Key principle:** KLAW is the interpreter layer. It must handle ambiguous, incomplete, unordered natural language input and map it to structured database operations. Raw input is always preserved for reparse.

---

## 3. Data Model

### 3.1 `users`
| Field | Type | Notes |
|---|---|---|
| `id` | TEXT PK | Telegram `chat_id` |
| `name` | TEXT | Display name |
| `role` | TEXT | `athlete` \| `coach` |
| `created_at` | DATETIME | Auto |

### 3.2 `sessions`
| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `user_id` | TEXT FK | → `users.id` |
| `date` | DATE | Parsed by KLAW, default: today |
| `session_type` | TEXT | `sparring` \| `drilling` \| `clinch` \| `groundwork` \| `muay_thai` \| `wrestling` \| `bjj` \| `s&c` \| `open` |
| `duration_min` | INTEGER | Nullable |
| `rounds` | INTEGER | Nullable |
| `intensity_rpe` | INTEGER | 1–10, nullable |
| `notes` | TEXT | Cleaned/interpreted text |
| `raw_input` | TEXT | **Always stored.** Original voice transcript or message. For debugging and reparse. |
| `created_at` | DATETIME | Auto |

### 3.3 `groups`
| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `name` | TEXT | e.g. "MT→MMA Transition Q1 2026" |
| `coach_id` | TEXT FK | → `users.id` |
| `created_at` | DATETIME | Auto |

### 3.4 `group_members` *(Many-to-Many)*
| Field | Type | Notes |
|---|---|---|
| `group_id` | INTEGER FK | → `groups.id` |
| `user_id` | TEXT FK | → `users.id` |
| `joined_at` | DATETIME | Auto |

**Entity Relationships:**
```
users ──< group_members >── groups
  |                              |
  └──────────< sessions          └── coach_id → users
```

One athlete can belong to multiple groups. One group can have multiple coaches (via multiple `group_members` records with coach role). Sessions are always user-scoped, never group-scoped – group queries are resolved by joining through `group_members`.

---

## 4. KLAW Behavior Specification

### 4.1 Core Principle
KLAW must **never require** a fixed input order or schema from the user. The user is an athlete who just finished training. Inputs will be:
- Incomplete ("did sparring, was brutal")
- Unordered ("6 rounds, muay thai, RPE 9, tuesday")
- Conversational ("had a solid drilling session today, maybe 90 minutes, nothing crazy")
- Voice transcripts with filler words and imprecision

### 4.2 Intent Types (MVP)

| Intent | Example Input | Action |
|---|---|---|
| `log_session` | "just did 6 rounds of sparring, RPE 8" | Extract fields → INSERT session |
| `query_recent` | "what did I do this week?" | SELECT sessions WHERE user + date range |
| `query_last` | "how was my last sparring?" | SELECT last session WHERE type = sparring |
| `query_summary` | "how many sessions this month?" | COUNT + GROUP BY |
| `unknown` | anything unclear | Ask one clarifying question, never two |

### 4.3 Field Extraction Rules

- `date`: If not stated → today. If "yesterday" / "tuesday" → resolve relative to now.
- `session_type`: Map natural language to enum. "rolling" → `bjj`. "striking" → `muay_thai`. "lifting" → `s&c`. When ambiguous → store as `open`, log raw.
- `duration_min`: Extract from "90 minutes", "an hour and a half", "45 min".
- `rounds`: Extract explicit numbers only. Never infer.
- `intensity_rpe`: Extract explicit RPE. "was brutal" → do not hallucinate a number. Store null, note in `notes`.
- `notes`: Always populated. Cleaned version of user input minus extracted fields.
- `raw_input`: Always the original string, unmodified.

### 4.4 Partial Data Policy
**Log always. Never block on missing fields.** A session with only `session_type` and `date` is better than no session. Nullable fields are nullable by design.

### 4.5 Auth
User identity = Telegram `chat_id`. Every KLAW call includes `user_id`. KLAW must scope all reads and writes to the authenticated user. Coach role unlocks group and cross-user queries.

---

## 5. User Stories

### Athlete
- As an athlete, I want to log a session by sending a voice note or free text immediately after training, without opening an app or following a schema.
- As an athlete, I want to ask "what did I do this week?" and get a human-readable summary.
- As an athlete, I want to ask "how was my last sparring session?" and get the relevant entry.

### Coach
- As a coach, I want to form training groups and assign athletes to them.
- As a coach, I want to query a group's training activity ("how has the MT→MMA group trained this week?").
- As a coach, I want to view an individual athlete's session history.

*Note: Group management UI/commands are schema-ready but NOT in MVP scope. MVP = athlete logging + personal queries only.*

---

## 6. MVP Scope

### In Scope
- Session logging via Telegram (text + voice via Whisper)
- KLAW NLU parsing → structured DB insert
- Personal query: this week / last session / by type
- Multi-tenant via Telegram `chat_id`
- Full schema including groups (inactive in MVP)

### Out of Scope (Later)
- Proactive insights / push notifications
- Group management commands
- Coach cross-athlete views
- Whisper stabilization
- Trend analysis / RPE charts
- Weekly auto-reports

---

## 7. API Endpoints (FastAPI – MVP)

```
POST   /sessions              – Create session (called by KLAW after parse)
GET    /sessions/{user_id}    – List sessions for user (optional: ?from=&to=&type=)
GET    /sessions/{user_id}/last – Last session, optionally filtered by type
GET    /users/{user_id}       – Get user profile
POST   /users                 – Register new user
```

---

## 8. KLAW System Prompt Directives

KLAW must internalize the following when processing any message:

1. **You are a training log interpreter, not a form validator.** Accept anything. Extract what you can. Store the rest in `raw_input` and `notes`.
2. **Never ask more than one clarifying question.** If critical info is missing and cannot be inferred, ask once, concisely.
3. **Always confirm what you logged.** After insert, respond with a one-line confirmation: "Logged: Sparring · 6 rounds · RPE 8 · Tuesday."
4. **Scope all operations to the authenticated user.** Never expose or reference other users' data unless the requester has `role: coach` and explicitly requests group/athlete data.
5. **Date resolution:** Assume user's local timezone. "Today" = query date. "Yesterday" = query date - 1. Named days = most recent past occurrence.
6. **session_type mapping:** Use the enum. When input is ambiguous, prefer `open` over hallucinating a type.
7. **RPE is subjective.** Never infer RPE from adjectives. "Brutal", "easy", "solid" go into `notes`, not `intensity_rpe`.
8. **Autonomous execution:** Work through all assigned tasks independently without interrupting the user for confirmation. Only pause when you hit: (a) an item explicitly marked "Open Question" in the spec, or (b) a decision point with two valid approaches where the choice is irreversible. When pausing: state what you completed, what you're blocked on, and ask exactly one question.

---

## 9. Open Questions (To Resolve)

- Whisper integration: local vs. Telegram voice → forwarded as file → transcribed on server?
- Coach role assignment: manual DB entry for MVP or Telegram command?
- Group commands syntax: when implemented, slash commands (`/group create`) or natural language?
- Timezone handling: store UTC + user timezone offset in `users` table?

---

*This document is the single source of truth for KLAW's operating context. Update it as the system evolves.*
