"""
Voice input — faster-whisper (local) + GPT-4o-mini parsing → auto-log session.

Flow:
  1. User sends voice note
  2. Download OGG from Telegram
  3. Transcribe locally via faster-whisper (tiny model, CPU, int8)
  4. Parse transcript with GPT-4o-mini → JSON session fields
  5. POST to FastAPI → save to DB
  6. Confirm or ask for missing mandatory fields (date)
"""
import os
import json
import logging
import tempfile
import asyncio
from concurrent.futures import ThreadPoolExecutor
from openai import AsyncOpenAI
from faster_whisper import WhisperModel
from telegram import Update
from telegram.ext import ContextTypes

from . import api

logger = logging.getLogger(__name__)

DISCIPLINES = ["BJJ", "Boxing", "Wrestling", "Kickboxing", "MMA", "Muay Thai", "Judo", "Strength"]

# Load once at import time — stays in memory
_whisper = WhisperModel("tiny", device="cpu", compute_type="int8")
_executor = ThreadPoolExecutor(max_workers=1)

PARSE_PROMPT = """You are parsing a voice note from an MMA athlete about a training session.

Extract the following fields from the transcript. Return ONLY valid JSON, no explanation.

Fields:
- date: string "YYYY-MM-DD" — MANDATORY. Infer from relative terms like "today", "yesterday", "last Monday".
  Today's date for reference: {today}
- discipline: one of {disciplines} — pick the closest match, or null if unclear
- duration_minutes: integer minutes — infer if they say "an hour", "90 minutes", etc. null if unclear
- intensity: integer 1–10 — infer from words like "light", "hard", "war", "easy". null if unclear
- notes: string — anything else worth capturing (techniques, sparring partners, injuries, etc.)

If date cannot be determined at all, set date to null.

Transcript: "{transcript}"

Return JSON only:
{{
  "date": "YYYY-MM-DD or null",
  "discipline": "string or null",
  "duration_minutes": integer_or_null,
  "intensity": integer_or_null,
  "notes": "string or null"
}}"""


def _transcribe_sync(path: str) -> str:
    """Run faster-whisper in a thread (it's synchronous)."""
    segments, info = _whisper.transcribe(path, beam_size=5)
    logger.info(f"Detected language: {info.language} ({info.language_probability:.0%})")
    return " ".join(seg.text.strip() for seg in segments).strip()


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    msg = update.message

    r = await api.get(f"/athletes/{tg_id}")
    if r.status_code == 404:
        await msg.reply_text("Not registered yet. Use /start first.")
        return

    await msg.reply_text("🎙 Got it — transcribing locally...")

    voice = msg.voice or msg.audio
    tg_file = await ctx.bot.get_file(voice.file_id)

    tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    tmp_path = tmp.name
    tmp.close()

    try:
        await tg_file.download_to_drive(tmp_path)
        logger.info(f"Downloaded voice: {tmp_path} ({os.path.getsize(tmp_path)} bytes)")

        # Transcribe in thread so we don't block the event loop
        loop = asyncio.get_event_loop()
        transcript = await loop.run_in_executor(_executor, _transcribe_sync, tmp_path)
        logger.info(f"Transcript [{tg_id}]: {transcript}")

        if not transcript:
            await msg.reply_text("Couldn't transcribe that. Try again with a clearer recording.")
            return

        # Parse with GPT-4o-mini
        from datetime import date
        today = date.today().isoformat()
        prompt = PARSE_PROMPT.format(
            today=today,
            disciplines=", ".join(DISCIPLINES),
            transcript=transcript,
        )

        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
        parse_resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(parse_resp.choices[0].message.content)
        logger.info(f"Parsed [{tg_id}]: {parsed}")

        # Validate mandatory field
        session_date = parsed.get("date")
        if not session_date or session_date == "null":
            await msg.reply_text(
                f"📝 I heard: _{transcript}_\n\n"
                "⚠️ Couldn't determine the date. Reply with the date (e.g. `2026-03-03`) "
                "and I'll log it manually, or use /log for the guided flow.",
                parse_mode="Markdown",
            )
            return

        discipline  = parsed.get("discipline") or "MMA"
        duration    = parsed.get("duration_minutes") or 60
        intensity   = parsed.get("intensity") or 5
        notes_parts = []
        if parsed.get("notes"):
            notes_parts.append(parsed["notes"])
        notes_parts.append(f"[Voice: {transcript}]")
        notes = " | ".join(notes_parts)

        payload = {
            "discipline": discipline,
            "duration_minutes": duration,
            "intensity": intensity,
            "notes": notes,
            "date_override": session_date,
        }
        save_r = await api.post(f"/athletes/{tg_id}/sessions", payload)

        if save_r.status_code == 201:
            d = save_r.json()
            flagged = []
            if not parsed.get("discipline"):      flagged.append("discipline → MMA")
            if not parsed.get("duration_minutes"): flagged.append("duration → 60 min")
            if not parsed.get("intensity"):        flagged.append("intensity → 5")

            warn = f"\n⚠️ Guessed: {', '.join(flagged)}" if flagged else ""
            await msg.reply_text(
                f"✅ Session logged!\n\n"
                f"📅 {session_date}\n"
                f"🥋 {d['discipline']} · {d['duration_minutes']} min · intensity {d['intensity']}/10\n"
                f"📝 {transcript}"
                f"{warn}"
            )
        else:
            detail = save_r.json().get("detail", "unknown error")
            await msg.reply_text(f"❌ Transcribed OK but save failed: {detail}")

    except Exception as e:
        logger.exception(f"Voice handler error [{tg_id}]: {e}")
        await msg.reply_text(f"❌ {type(e).__name__}: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
