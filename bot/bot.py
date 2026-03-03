"""
MMA Training Tracker — Telegram Bot
Commands:
  /start      — register as athlete
  /log        — log a training session (guided)
  /sessions   — list last 10 sessions
  /stats      — show your training stats
  /help       — command list
"""
import os
import logging
import httpx
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, filters, ContextTypes
)
from .voice import handle_voice

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000/api/v1")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Conversation states
DISCIPLINE, DURATION, INTENSITY, NOTES = range(4)

DISCIPLINES = ["BJJ", "Boxing", "Wrestling", "Kickboxing", "MMA", "Muay Thai", "Judo"]


# ── Helpers ──────────────────────────────────────────────────────────────────

from . import api as _api

async def api_get(path: str):
    return await _api.get(path)

async def api_post(path: str, data: dict):
    return await _api.post(path, data)


# ── /start ───────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    tg_id = user.id

    r = await api_post("/athletes", {"telegram_id": tg_id, "name": user.full_name})
    if r.status_code == 201:
        await update.message.reply_text(
            f"🦞 Welcome, {user.first_name}! You're registered.\n"
            "Use /log to track a session, /stats to see your progress."
        )
    elif r.status_code == 409:
        await update.message.reply_text(
            f"Already registered, {user.first_name}. Use /log or /stats."
        )
    else:
        await update.message.reply_text("Registration failed. Try again later.")


# ── /log (ConversationHandler) ────────────────────────────────────────────────

async def log_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [[d] for d in DISCIPLINES]
    await update.message.reply_text(
        "What discipline did you train?",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return DISCIPLINE


async def log_discipline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["discipline"] = update.message.text
    await update.message.reply_text(
        "Duration in minutes?",
        reply_markup=ReplyKeyboardRemove()
    )
    return DURATION


async def log_duration(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        minutes = int(update.message.text)
        if minutes < 1 or minutes > 480:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Enter a number between 1 and 480.")
        return DURATION

    ctx.user_data["duration_minutes"] = minutes
    keyboard = [[str(i) for i in range(1, 6)], [str(i) for i in range(6, 11)]]
    await update.message.reply_text(
        "Intensity (1=easy, 10=war)?",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return INTENSITY


async def log_intensity(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        intensity = int(update.message.text)
        if intensity < 1 or intensity > 10:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Pick 1–10.")
        return INTENSITY

    ctx.user_data["intensity"] = intensity
    await update.message.reply_text(
        "Any notes? (or /skip)",
        reply_markup=ReplyKeyboardRemove()
    )
    return NOTES


async def log_notes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["notes"] = update.message.text
    return await _save_session(update, ctx)


async def log_skip_notes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["notes"] = None
    return await _save_session(update, ctx)


async def _save_session(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    payload = {
        "discipline": ctx.user_data["discipline"],
        "duration_minutes": ctx.user_data["duration_minutes"],
        "intensity": ctx.user_data["intensity"],
        "notes": ctx.user_data.get("notes"),
    }
    r = await api_post(f"/athletes/{tg_id}/sessions", payload)
    if r.status_code == 201:
        d = r.json()
        await update.message.reply_text(
            f"✅ Session logged!\n"
            f"🥋 {d['discipline']} · {d['duration_minutes']} min · intensity {d['intensity']}/10"
        )
    else:
        detail = r.json().get("detail", "Unknown error")
        await update.message.reply_text(f"❌ Failed: {detail}")
    ctx.user_data.clear()
    return ConversationHandler.END


async def log_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("Cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ── /sessions ─────────────────────────────────────────────────────────────────

async def sessions(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    r = await api_get(f"/athletes/{tg_id}/sessions?limit=10")
    if r.status_code == 404:
        await update.message.reply_text("Not registered. Use /start.")
        return
    data = r.json()
    if not data:
        await update.message.reply_text("No sessions yet. Use /log to start.")
        return

    lines = ["📋 *Last sessions:*"]
    for s in data:
        date = s["logged_at"][:10]
        lines.append(f"• {date} — {s['discipline']} {s['duration_minutes']}min intensity {s['intensity']}/10")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /stats ────────────────────────────────────────────────────────────────────

async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    r = await api_get(f"/athletes/{tg_id}/stats")
    if r.status_code == 404:
        await update.message.reply_text("Not registered. Use /start.")
        return
    s = r.json()
    if s["total_sessions"] == 0:
        await update.message.reply_text("No sessions yet. Use /log to start.")
        return

    disc_lines = "\n".join(f"  • {k}: {v}" for k, v in s["disciplines"].items())
    msg = (
        f"📊 *Your Stats*\n\n"
        f"Sessions: {s['total_sessions']}\n"
        f"Total time: {s['total_minutes']} min ({s['total_minutes']//60}h {s['total_minutes']%60}m)\n"
        f"Avg intensity: {s['avg_intensity']}/10\n\n"
        f"Disciplines:\n{disc_lines}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


# ── /help ─────────────────────────────────────────────────────────────────────

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🦞 *MMA Tracker*\n\n"
        "/start — register\n"
        "/log — log a session (guided)\n"
        "🎙 voice note — auto-log from speech\n"
        "/sessions — last 10 sessions\n"
        "/stats — your training stats\n"
        "/help — this menu",
        parse_mode="Markdown"
    )


# ── Main ──────────────────────────────────────────────────────────────────────

async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    from telegram.error import Conflict, NetworkError, TimedOut
    # These are transient infra errors — log quietly, don't alert the user
    if isinstance(ctx.error, (Conflict, NetworkError, TimedOut)):
        logger.warning(f"Transient error (ignored): {ctx.error}")
        return
    logger.exception(f"Unhandled exception: {ctx.error}", exc_info=ctx.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(f"❌ Unexpected error: {type(ctx.error).__name__}: {ctx.error}")


def main():
    token = BOT_TOKEN
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

    app = ApplicationBuilder().token(token).build()

    log_conv = ConversationHandler(
        entry_points=[CommandHandler("log", log_start)],
        states={
            DISCIPLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, log_discipline)],
            DURATION:   [MessageHandler(filters.TEXT & ~filters.COMMAND, log_duration)],
            INTENSITY:  [MessageHandler(filters.TEXT & ~filters.COMMAND, log_intensity)],
            NOTES:      [
                CommandHandler("skip", log_skip_notes),
                MessageHandler(filters.TEXT & ~filters.COMMAND, log_notes),
            ],
        },
        fallbacks=[CommandHandler("cancel", log_cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(log_conv)
    app.add_handler(CommandHandler("sessions", sessions))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_error_handler(error_handler)

    logger.info("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
