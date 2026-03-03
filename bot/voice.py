"""
Voice input handler — Whisper transcription + GPT parsing → auto-log session.

Flow:
  1. User sends voice note
  2. Download OGG from Telegram
  3. Transcribe via Whisper API
  4. Parse transcript with GPT-4o-mini → JSON session fields
  5. POST to FastAPI → save to DB
  6. Confirm or ask for missing mandatory fields (date)
"""
import os
import json
import logging
import tempfile
import httpx
from openai import AsyncOpenAI
from telegram import Update
from telegram.ext import ContextTypes

from . import api

logger = logging.getLogger(__name__)

DISCIPLINES = ["BJJ", "Boxing", "Wrestling", "Kickboxing", "MMA", "Muay Thai", "Judo", "Strength"]

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


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    msg = update.message

    # Check registration
    r = await api.get(f"/athletes/{tg_id}")
    if r.status_code == 404:
        await msg.reply_text("Not registered yet. Use /start first.")
        return

    await msg.reply_text("🎙 Got it — transcribing...")

    # Download voice file
    voice = msg.voice or msg.audio
    tg_file = await ctx.bot.get_file(voice.file_id)

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        await tg_file.download_to_drive(tmp_path)

        # Transcribe via Whisper
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
        with open(tmp_path, "rb") as audio_file:
            transcript_resp = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text",
            )
        transcript = transcript_resp.strip()
        logger.info(f"Transcript [{tg_id}]: {transcript}")

        if not transcript:
            await msg.reply_text("Couldn't transcribe that. Try again with a clearer recording.")
            return

        # Parse with GPT
        from datetime import date
        today = date.today().isoformat()
        prompt = PARSE_PROMPT.format(
            today=today,
            disciplines=", ".join(DISCIPLINES),
            transcript=transcript,
        )

        parse_resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = parse_resp.choices[0].message.content
        parsed = json.loads(raw)
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

        # Fill defaults for optional fields
        discipline = parsed.get("discipline") or "MMA"
        duration = parsed.get("duration_minutes") or 60
        intensity = parsed.get("intensity") or 5
        notes_parts = []
        if parsed.get("notes"):
            notes_parts.append(parsed["notes"])
        notes_parts.append(f"[Voice log — transcript: {transcript}]")
        notes = " | ".join(notes_parts)

        # Save via API
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
            if not parsed.get("discipline"):
                flagged.append("discipline (defaulted to MMA)")
            if not parsed.get("duration_minutes"):
                flagged.append("duration (defaulted to 60 min)")
            if not parsed.get("intensity"):
                flagged.append("intensity (defaulted to 5)")

            warn = ""
            if flagged:
                warn = f"\n⚠️ Guessed: {', '.join(flagged)}"

            await msg.reply_text(
                f"✅ Session logged from voice!\n\n"
                f"📅 {session_date}\n"
                f"🥋 {d['discipline']} · {d['duration_minutes']} min · intensity {d['intensity']}/10\n"
                f"📝 {transcript}"
                f"{warn}",
            )
        else:
            detail = save_r.json().get("detail", "unknown error")
            await msg.reply_text(f"❌ Transcribed OK but couldn't save: {detail}")

    finally:
        os.unlink(tmp_path)
