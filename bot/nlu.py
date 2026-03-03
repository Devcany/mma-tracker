"""
KLAW NLU layer — maps free-text or voice transcripts to structured session data.

Rules (from spec §4.3):
- date:         default today; resolve relative terms
- session_type: map natural language to enum; ambiguous → "open"
- duration_min: extract only if explicit
- rounds:       extract explicit numbers only, never infer
- intensity_rpe: explicit RPE only; adjectives → notes, not rpe
- notes:        always populated; cleaned input minus extracted fields
- raw_input:    original string, always preserved unmodified
"""
import json
import logging
import os
from datetime import date
from typing import Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

SESSION_TYPES = ["sparring", "drilling", "clinch", "groundwork", "muay_thai", "wrestling", "bjj", "s&c", "open"]

SYSTEM_PROMPT = """You are KLAW, a training log interpreter for MMA athletes.

Extract structured fields from the athlete's input. Return ONLY valid JSON.

session_type mappings:
- "rolling", "grappling", "bjj", "jiu-jitsu" → "bjj"
- "sparring", "fighting", "rounds" → "sparring"  
- "drilling", "drills", "technique" → "drilling"
- "clinch", "clinchwork" → "clinch"
- "groundwork", "ground", "ground work" → "groundwork"
- "muay thai", "striking", "kicks", "elbows", "thai" → "muay_thai"
- "wrestling", "takedowns", "shots" → "wrestling"
- "lifting", "strength", "conditioning", "weights", "gym" → "s&c"
- ambiguous or multiple types → "open"

Rules:
- date: resolve relative to today ({today}). "today"=today, "yesterday"=today-1, "tuesday"=most recent past Tuesday. Default: today.
- duration_min: only from explicit statements ("90 minutes", "an hour", "45 min"). null otherwise.
- rounds: only explicit numbers ("6 rounds", "did 5"). Never infer. null otherwise.
- intensity_rpe: only explicit RPE ("RPE 8", "intensity 7", "8 out of 10"). NEVER infer from adjectives. "brutal", "hard", "easy", "solid" → null RPE, capture in notes.
- notes: cleaned summary of what was said, minus fields already extracted. Always populate.

Return JSON only:
{{
  "date": "YYYY-MM-DD",
  "session_type": "<one of the enum values>",
  "duration_min": <integer or null>,
  "rounds": <integer or null>,
  "intensity_rpe": <integer 1-10 or null>,
  "notes": "<string, never empty>"
}}"""


async def parse(text: str) -> dict:
    """Parse free text into session fields. Returns dict ready for SessionCreate."""
    today = date.today().isoformat()
    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(today=today)},
            {"role": "user", "content": text},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )

    parsed = json.loads(resp.choices[0].message.content)
    logger.info(f"NLU parsed: {parsed}")

    # Sanitise
    if not parsed.get("date"):
        parsed["date"] = today
    if parsed.get("session_type") not in SESSION_TYPES:
        parsed["session_type"] = "open"
    if not parsed.get("notes"):
        parsed["notes"] = text[:500]

    parsed["raw_input"] = text  # always the original
    return parsed


def format_confirmation(session: dict) -> str:
    """One-line confirmation per spec §8.3."""
    parts = [session["session_type"].replace("_", " ").title()]
    if session.get("rounds"):
        parts.append(f"{session['rounds']} rounds")
    if session.get("duration_min"):
        parts.append(f"{session['duration_min']} min")
    if session.get("intensity_rpe"):
        parts.append(f"RPE {session['intensity_rpe']}")
    parts.append(session["date"])
    return "Logged: " + " · ".join(parts) + "."
