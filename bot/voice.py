"""
Voice handler — faster-whisper (local STT) → KLAW NLU → session log.
raw_input is always the original unmodified transcript.
"""
import os
import asyncio
import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor

from faster_whisper import WhisperModel
from telegram import Update
from telegram.ext import ContextTypes

from . import api, nlu

logger = logging.getLogger(__name__)

_whisper = WhisperModel("tiny", device="cpu", compute_type="int8")
_executor = ThreadPoolExecutor(max_workers=1)


def _transcribe_sync(path: str) -> str:
    segments, info = _whisper.transcribe(path, beam_size=5)
    logger.info(f"Whisper: lang={info.language} ({info.language_probability:.0%})")
    return " ".join(seg.text.strip() for seg in segments).strip()


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    msg = update.message

    r = await api.get(f"/users/{uid}")
    if r.status_code == 404:
        await msg.reply_text("Not registered. Send /start first.")
        return

    await msg.reply_text("🎙 Transcribing...")

    voice = msg.voice or msg.audio
    tg_file = await ctx.bot.get_file(voice.file_id)

    tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    tmp_path = tmp.name
    tmp.close()

    try:
        await tg_file.download_to_drive(tmp_path)
        logger.info(f"Voice downloaded: {tmp_path} ({os.path.getsize(tmp_path)}B)")

        loop = asyncio.get_event_loop()
        transcript = await loop.run_in_executor(_executor, _transcribe_sync, tmp_path)
        logger.info(f"Transcript [{uid}]: {transcript}")

        if not transcript:
            await msg.reply_text("Couldn't transcribe. Try again with a clearer recording.")
            return

        # NLU parse — raw_input is always the original transcript
        parsed = await nlu.parse(transcript)

        payload = {
            "user_id": uid,
            "date": parsed["date"],
            "session_type": parsed["session_type"],
            "duration_min": parsed.get("duration_min"),
            "rounds": parsed.get("rounds"),
            "intensity_rpe": parsed.get("intensity_rpe"),
            "notes": parsed.get("notes", ""),
            "raw_input": transcript,  # original, unmodified
        }

        save_r = await api.post("/sessions", payload)
        if save_r.status_code == 201:
            confirmation = nlu.format_confirmation(parsed)
            flagged = []
            if not parsed.get("duration_min"): flagged.append("duration unknown")
            if not parsed.get("intensity_rpe"): flagged.append("RPE unknown")
            warn = f" ({', '.join(flagged)})" if flagged else ""
            await msg.reply_text(f"{confirmation}{warn}")
        else:
            detail = save_r.json().get("detail", "unknown error")
            await msg.reply_text(f"❌ Transcribed OK but save failed: {detail}")

    except Exception as e:
        logger.exception(f"Voice handler error [{uid}]: {e}")
        await msg.reply_text(f"❌ {type(e).__name__}: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
