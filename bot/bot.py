"""
MMA Training Tracker — Telegram Bot (KLAW)

Design (spec §4):
- Any text message = potential session intent → NLU parse → log or query
- Voice note → faster-whisper → NLU parse → log
- No guided flows. No fixed schemas. Accept anything.

Commands (minimal — most interaction is free text):
  /start  — register (idempotent)
  /last   — last session, optionally: /last sparring
  /week   — this week's sessions
  /help   — brief usage
"""
import os
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)
from telegram.error import Conflict, NetworkError, TimedOut

from . import api
from . import nlu
from .voice import handle_voice

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")


# ── Helpers ───────────────────────────────────────────────────────────────────

async def ensure_registered(update: Update) -> bool:
    """Auto-register user if not present. Returns True if ready to proceed."""
    user = update.effective_user
    uid = str(user.id)
    r = await api.get(f"/users/{uid}")
    if r.status_code == 404:
        r2 = await api.post("/users", {"id": uid, "name": user.full_name, "role": "athlete"})
        if r2.status_code == 201:
            await update.message.reply_text(
                f"🦞 Registered as {user.first_name}. Send me a session — voice note or free text."
            )
        else:
            await update.message.reply_text("Registration failed. Try again.")
            return False
    return True


# ── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    r = await api.get(f"/users/{uid}")
    if r.status_code == 200:
        await update.message.reply_text(
            f"Already registered, {user.first_name}.\n"
            "Send a voice note or type a session — I'll handle the rest."
        )
    else:
        await ensure_registered(update)


# ── Free text → NLU → log ─────────────────────────────────────────────────────

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await ensure_registered(update):
        return

    uid = str(update.effective_user.id)
    text = update.message.text.strip()

    # Simple query intents
    lower = text.lower()
    if any(q in lower for q in ["this week", "what did i do", "my sessions", "show sessions"]):
        await _handle_query_week(update, uid)
        return
    if any(q in lower for q in ["last session", "last sparring", "last bjj", "last wrestling",
                                  "last muay", "last drilling", "last clinch"]):
        await _handle_query_last(update, uid, lower)
        return

    # Default: treat as session log
    await _log_from_text(update, uid, text)


async def _log_from_text(update: Update, uid: str, text: str):
    try:
        parsed = await nlu.parse(text)
    except Exception as e:
        logger.exception(f"NLU error: {e}")
        await update.message.reply_text(f"❌ Couldn't parse that: {e}")
        return

    payload = {
        "user_id": uid,
        "date": parsed["date"],
        "session_type": parsed["session_type"],
        "duration_min": parsed.get("duration_min"),
        "rounds": parsed.get("rounds"),
        "intensity_rpe": parsed.get("intensity_rpe"),
        "notes": parsed.get("notes", ""),
        "raw_input": parsed["raw_input"],
    }

    r = await api.post("/sessions", payload)
    if r.status_code == 201:
        await update.message.reply_text(nlu.format_confirmation(parsed))
    else:
        detail = r.json().get("detail", "unknown error")
        await update.message.reply_text(f"❌ Save failed: {detail}")


# ── Query handlers ────────────────────────────────────────────────────────────

async def _handle_query_week(update: Update, uid: str):
    from datetime import date, timedelta
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    r = await api.get(f"/sessions/{uid}?from={monday.isoformat()}&to={today.isoformat()}")
    if r.status_code != 200:
        await update.message.reply_text("Couldn't fetch sessions.")
        return
    sessions = r.json()
    if not sessions:
        await update.message.reply_text("No sessions logged this week.")
        return
    lines = [f"📋 This week ({len(sessions)} sessions):"]
    for s in sessions:
        parts = [s["session_type"].replace("_", " ").title()]
        if s.get("duration_min"): parts.append(f"{s['duration_min']}min")
        if s.get("rounds"):       parts.append(f"{s['rounds']} rounds")
        if s.get("intensity_rpe"): parts.append(f"RPE {s['intensity_rpe']}")
        lines.append(f"• {s['date']} — {' · '.join(parts)}")
    await update.message.reply_text("\n".join(lines))


async def _handle_query_last(update: Update, uid: str, lower: str):
    type_filter = None
    for t in ["sparring", "bjj", "wrestling", "muay_thai", "muay thai", "drilling", "clinch", "groundwork", "s&c"]:
        if t in lower:
            type_filter = t.replace(" ", "_")
            break

    url = f"/sessions/{uid}/last"
    if type_filter:
        url += f"?type={type_filter}"

    r = await api.get(url)
    if r.status_code == 404:
        label = f"{type_filter} " if type_filter else ""
        await update.message.reply_text(f"No {label}sessions logged yet.")
        return
    s = r.json()
    parts = [s["session_type"].replace("_", " ").title()]
    if s.get("duration_min"):  parts.append(f"{s['duration_min']}min")
    if s.get("rounds"):        parts.append(f"{s['rounds']} rounds")
    if s.get("intensity_rpe"): parts.append(f"RPE {s['intensity_rpe']}")
    msg = f"Last session: {s['date']} — {' · '.join(parts)}"
    if s.get("notes"):
        msg += f"\n📝 {s['notes']}"
    await update.message.reply_text(msg)


# ── /last ─────────────────────────────────────────────────────────────────────

async def cmd_last(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await ensure_registered(update):
        return
    uid = str(update.effective_user.id)
    type_filter = ctx.args[0] if ctx.args else None
    url = f"/sessions/{uid}/last"
    if type_filter:
        url += f"?type={type_filter}"
    r = await api.get(url)
    if r.status_code == 404:
        await update.message.reply_text("No sessions logged yet.")
        return
    s = r.json()
    parts = [s["session_type"].replace("_", " ").title()]
    if s.get("duration_min"):  parts.append(f"{s['duration_min']}min")
    if s.get("rounds"):        parts.append(f"{s['rounds']} rounds")
    if s.get("intensity_rpe"): parts.append(f"RPE {s['intensity_rpe']}")
    msg = f"Last: {s['date']} — {' · '.join(parts)}"
    if s.get("notes"):
        msg += f"\n📝 {s['notes']}"
    await update.message.reply_text(msg)


# ── /week ─────────────────────────────────────────────────────────────────────

async def cmd_week(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await ensure_registered(update):
        return
    await _handle_query_week(update, str(update.effective_user.id))


# ── /help ─────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🦞 *KLAW — MMA Training Tracker*\n\n"
        "Just talk to me. Examples:\n"
        "• _\"6 rounds of sparring, RPE 8, Tuesday\"_\n"
        "• _\"had a solid BJJ drilling session today, 90 minutes\"_\n"
        "• _\"lifting session yesterday, 45 min\"_\n"
        "• 🎙 Send a voice note\n\n"
        "*Commands:*\n"
        "/last — last session\n"
        "/last sparring — last sparring session\n"
        "/week — this week's sessions\n"
        "/help — this message",
        parse_mode="Markdown"
    )


# ── Error handler ─────────────────────────────────────────────────────────────

async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    if isinstance(ctx.error, (Conflict, NetworkError, TimedOut)):
        logger.warning(f"Transient error (ignored): {ctx.error}")
        return
    logger.exception(f"Unhandled exception: {ctx.error}", exc_info=ctx.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            f"❌ {type(ctx.error).__name__}: {ctx.error}"
        )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("last", cmd_last))
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    logger.info("KLAW bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
