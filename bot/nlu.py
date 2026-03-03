"""
KLAW NLU — rule-based parser. No external API. No quota.

Spec §4.3 rules implemented directly:
- date:         today by default; resolves relative terms
- session_type: keyword → enum mapping; ambiguous → "open"
- duration_min: explicit statements only
- rounds:       explicit numbers only, never inferred
- intensity_rpe: explicit RPE only — adjectives go to notes, not rpe
- notes:        always populated; cleaned input
- raw_input:    preserved by caller, untouched here
"""
import re
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

SESSION_TYPES = [
    "sparring", "drilling", "clinch", "groundwork",
    "muay_thai", "wrestling", "bjj", "s&c", "open"
]

# Keyword → session_type (checked in order; first match wins)
TYPE_MAP = [
    (["sparring", "spar", "fighting", "fight", "sparing"],                  "sparring"),
    (["rolling", "bjj", "jiu-jitsu", "jiu jitsu", "jiujitsu", "grappling"], "bjj"),
    (["muay thai", "muay-thai", "thai boxing", "striking", "pad work",
      "pads", "elbows", "thai"],                                             "muay_thai"),
    (["wrestling", "takedowns", "takedown", "shots", "shooting"],            "wrestling"),
    (["drilling", "drills", "drill", "technique work", "techniques"],        "drilling"),
    (["clinch", "clinchwork", "clinch work"],                                "clinch"),
    (["groundwork", "ground work", "ground game"],                           "groundwork"),
    (["lifting", "strength", "s&c", "conditioning", "weights",
      "weight training", "gym", "crossfit"],                                 "s&c"),
    (["mma", "mixed martial arts", "cage", "full contact"],                  "sparring"),
]

# Day name → weekday index (Monday=0)
WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}


# ── Date extraction ───────────────────────────────────────────────────────────

def _resolve_date(text: str) -> date:
    t = text.lower()
    today = date.today()

    if "today" in t or "tonight" in t or "just now" in t or "just did" in t:
        return today
    if "yesterday" in t:
        return today - timedelta(days=1)
    if "two days ago" in t or "2 days ago" in t:
        return today - timedelta(days=2)

    # "last monday", "on tuesday", "tuesday"
    for name, idx in WEEKDAYS.items():
        if re.search(rf"\b{name}\b", t):
            days_back = (today.weekday() - idx) % 7
            if days_back == 0:
                days_back = 7  # "tuesday" when today is tuesday → last tuesday
            return today - timedelta(days=days_back)

    # Explicit date: 2026-03-01, 01/03, 03-01 etc
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"\b(\d{1,2})[./](\d{1,2})\b", t)
    if m:
        try:
            return date(today.year, int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    return today  # default


# ── Duration extraction ───────────────────────────────────────────────────────

def _extract_duration(text: str) -> int | None:
    t = text.lower()

    # "1.5 hours", "1,5 hours"
    m = re.search(r"\b(\d+)[.,](\d+)\s*h(?:ours?)?", t)
    if m:
        return int((float(f"{m.group(1)}.{m.group(2)}")) * 60)

    # "1 hour 30 minutes", "1h30", "1h 30m"
    m = re.search(r"\b(\d+)\s*h(?:ours?)?\s*(?:and\s*)?(\d+)\s*m(?:in(?:utes?)?)?", t)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))

    # "90 minutes", "45 min", "120mins"
    m = re.search(r"\b(\d+)\s*min(?:utes?|s)?", t)
    if m:
        return int(m.group(1))

    # "two hours", "an hour and a half", "a couple of hours"
    if re.search(r"\ban?\s+hour\s+and\s+a\s+half\b", t):
        return 90
    if re.search(r"\ban?\s+hour\b", t):
        return 60
    if re.search(r"\btwo\s+hours?\b", t):
        return 120
    if re.search(r"\bhalf\s+(?:an\s+)?hour\b", t):
        return 30
    if re.search(r"\b(?:one\s+and\s+a\s+half|1\.5)\s*hours?\b", t):
        return 90
    if re.search(r"\b(\d+)\s*h\b", t):
        m = re.search(r"\b(\d+)\s*h\b", t)
        return int(m.group(1)) * 60

    return None


# ── Rounds extraction ─────────────────────────────────────────────────────────

def _extract_rounds(text: str) -> int | None:
    t = text.lower()
    # "6 rounds", "did 5 rounds", "8-round session"
    m = re.search(r"\b(\d+)\s*[- ]?rounds?\b", t)
    if m:
        return int(m.group(1))
    # "rounds: 6"
    m = re.search(r"\bround[s]?\s*[:\-]\s*(\d+)", t)
    if m:
        return int(m.group(1))
    return None


# ── RPE extraction ─────────────────────────────────────────────────────────────

def _extract_rpe(text: str) -> int | None:
    t = text.lower()
    # "RPE 8", "rpe: 9", "RPE8"
    m = re.search(r"\brpe\s*[:\-]?\s*(\d+)", t)
    if m:
        val = int(m.group(1))
        return val if 1 <= val <= 10 else None
    # "intensity 7", "intensity: 8"
    m = re.search(r"\bintensity\s*[:\-]?\s*(\d+)", t)
    if m:
        val = int(m.group(1))
        return val if 1 <= val <= 10 else None
    # "8/10", "8 out of 10"
    m = re.search(r"\b([1-9]|10)\s*(?:/|out\s+of)\s*10\b", t)
    if m:
        return int(m.group(1))
    # Explicit: "effort 8", "rate 7"
    m = re.search(r"\b(?:effort|rate|exertion)\s*[:\-]?\s*(\d+)", t)
    if m:
        val = int(m.group(1))
        return val if 1 <= val <= 10 else None
    return None  # never infer from adjectives


# ── Session type extraction ───────────────────────────────────────────────────

def _extract_type(text: str) -> str:
    t = text.lower()
    for keywords, session_type in TYPE_MAP:
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\b", t):
                return session_type
    return "open"


# ── Notes generation ──────────────────────────────────────────────────────────

_STRIP_PATTERNS = [
    r"\b\d+\s*min(?:utes?)?\b",
    r"\b\d+\s*h(?:ours?)?\b",
    r"\b\d+\s*rounds?\b",
    r"\brpe\s*[:\-]?\s*\d+",
    r"\bintensity\s*[:\-]?\s*\d+",
    r"\b\d+\s*(?:/|out of)\s*10\b",
    r"\b(today|yesterday|tonight|last\s+\w+|this\s+\w+)\b",
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\b(just did|i did|had a|did a|went to|trained|training session|session)\b",
    r"\b(sparring|spar|bjj|rolling|grappling|muay thai|wrestling|drilling|clinch|groundwork|s&c|lifting|strength|mma)\b",
]

def _generate_notes(text: str, raw_input: str) -> str:
    cleaned = raw_input
    for pattern in _STRIP_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" .,;-")
    return cleaned if cleaned else raw_input[:200]


# ── Main parse entry point ────────────────────────────────────────────────────

async def parse(text: str) -> dict:
    """Parse free text into session fields. Fully local, no API calls."""
    result = {
        "date":          _resolve_date(text).isoformat(),
        "session_type":  _extract_type(text),
        "duration_min":  _extract_duration(text),
        "rounds":        _extract_rounds(text),
        "intensity_rpe": _extract_rpe(text),
        "notes":         _generate_notes(text, text),
        "raw_input":     text,
    }
    logger.info(f"NLU parsed: {result}")
    return result


# ── Confirmation formatter ────────────────────────────────────────────────────

def format_confirmation(parsed: dict) -> str:
    """Spec §8.3: one-line confirmation."""
    parts = [parsed["session_type"].replace("_", " ").title()]
    if parsed.get("rounds"):
        parts.append(f"{parsed['rounds']} rounds")
    if parsed.get("duration_min"):
        parts.append(f"{parsed['duration_min']} min")
    if parsed.get("intensity_rpe"):
        parts.append(f"RPE {parsed['intensity_rpe']}")
    parts.append(parsed["date"])
    return "Logged: " + " · ".join(parts) + "."
