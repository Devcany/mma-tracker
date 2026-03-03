# 🦞 MMA Training Tracker

FastAPI + SQLite + Telegram bot for tracking MMA training sessions.

## Stack

- **Backend:** FastAPI + SQLAlchemy + SQLite
- **Bot:** python-telegram-bot
- **Python:** 3.11+

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install fastapi uvicorn sqlalchemy python-telegram-bot aiohttp httpx

cp .env.example .env  # add your bot token
```

## Run

```bash
# API
./run_api.sh

# Bot (separate terminal)
./run_bot.sh
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/athletes` | Register athlete |
| GET | `/api/v1/athletes/{tg_id}` | Get athlete |
| POST | `/api/v1/athletes/{tg_id}/sessions` | Log session |
| GET | `/api/v1/athletes/{tg_id}/sessions` | List sessions |
| GET | `/api/v1/athletes/{tg_id}/stats` | Get stats |

## Bot Commands

- `/start` — register
- `/log` — guided session logging
- `/sessions` — last 10 sessions
- `/stats` — training stats
- `/help` — command list

## Systemd Services

Both processes run as systemd services with auto-restart.

```bash
# Install (one-time)
cp mma-api.service mma-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable mma-api mma-bot
systemctl start mma-api mma-bot

# Manage
systemctl status mma-api mma-bot
systemctl restart mma-bot
journalctl -u mma-bot -f      # or: tail -f /var/log/mma-bot.log
```
