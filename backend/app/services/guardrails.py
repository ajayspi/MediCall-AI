"""G6-Q3 clinical guardrails — stdlib-only safety layer for the voice agent.

Single source of truth for clinical safety rules, consumed by
app/services/livekit_agent.py (agent loop) and unit-tested without livekit:

* RED_FLAG_CATEGORIES — ~12 curated life-threatening symptom categories with
  stable keyword phrase tables (A3a). Never a diagnosis: a keyword match is a
  triage flag for the care team, exactly like TriageSeverity.
* match_red_flag(text) — case/accent-insensitive substring hit against the
  catalog; the second leg of the Q1/A1a escalation triggers.
* escalation_decision(severity, caller_text) — layered deterministic triggers
  (Q1=A1a): severity red/critical (reuses agent_logic.should_escalate, not
  duplicated) OR a red-flag keyword match. Reason records the trigger source
  ("severity:red" / "red_flag:cardiac").
* guard_output(text, language) — the Q2=A2a deterministic output guard: scans
  the agent's response for FORBIDDEN_CLAIMS (diagnosis / dosage directives); on
  a hit it replaces the whole response with the fixed per-language refusal
  phrase (temperature≈0 path) so a bad claim is never spoken. flag ∈
  {safe, refused}; reason ∈ {"", "diagnosis", "dosage"}.
* SAFE_REFUSALS / ESCALATE_PHRASES — fixed per-language (hi/en/ta/te/bn)

Q4=A4a: the adversarial red-team vector table lives in
backend/tests/test_guardrails_q3.py and is the acceptance gate — every vector
must hit its exact guard action.

G6-Q3 (2026-09-25): approved Q1=A1a Q2=A2a Q3=A3a Q4=A4a — pure logic, zero
env keys, no tables, no endpoints.
"""
import re
from typing import Dict, Optional, Tuple

from app.services.agent_logic import should_escalate

# The 12 life-threat categories (A3a). Phrases are lowercase substrings;
# matching is case-insensitive. Keep this table curated — these are the only
# keyword triggers that override the LLM's severity judgment.
RED_FLAG_CATEGORIES: Dict[str, Tuple[str, ...]] = {
    "cardiac": (
        "chest pain",
        "chest tightness",
        "heart attack",
        "heart racing",
        "palpitations",
    ),
    "respiratory": (
        "can't breathe",
        "cannot breathe",
        "short of breath",
        "breathing difficulty",
        "stopped breathing",
    ),
    "severe_bleeding": (
        "bleeding heavily",
        "bleeding a lot",
        "won't stop bleeding",
        "uncontrollable bleeding",
        "gushing blood",
    ),
    "stroke": (
        "face is drooping",
        "face drooping",
        "speech is slurred",
        "slurred speech",
        "weakness on one side",
        "can't move my arm",
        "numb on one side",
    ),
    "seizure": (
        "seizure",
        "fitting",
        "convulsing",
        "epileptic fit",
    ),
    "poisoning": (
        "swallowed some chemicals",
        "poisoned",
        "poison",
        "overdose",
        "took too many pills",
    ),
    "anaphylaxis": (
        "allergic reaction",
        "anaphylaxis",
        "swelling of the throat",
        "throat closing",
        "lips swelling",
    ),
    "burns": (
        "burned his hand",
        "burned her hand",
        "burned badly",
        "severe burn",
        "third degree burn",
    ),
    "head_injury": (
        "hit his head",
        "hit her head",
        "hit my head",
        "head injury",
        "unconscious",
        "passed out",
        "fainted",
    ),
    "pregnancy_emergency": (
        "during my pregnancy",
        "bleeding while pregnant",
        "labour pains",
        "labor pains",
        "baby not moving",
    ),
    "self_harm": (
        "kill myself",
        "end my life",
        "hurt myself",
        "self harm",
        "want to die",
        "suicide",
    ),
    "choking": (
        "choking",
        "can't swallow",
        "cannot swallow",
        "food stuck",
    ),
}

# Diagnosis claims — plain substrings (lowercased against lowercased text).
DIAGNOSIS_CLAIMS: Tuple[str, ...] = (
    "you have ",
    "you've got ",
    "you got ",
    "it looks like you have",
    "it looks like you've got",
    "you're suffering from",
    "you are suffering from",
    "your condition is",
)

# Dosage directives — regex patterns (applied to lowercased text).
DOSAGE_CLAIMS: Tuple[str, ...] = (
    r"\b\d+\s*mg\b",  # "500 mg" / "250 mg"
    r"\b\d+\s*ml\b",  # "10 ml"
    r"\b\d+\s*tablets?\b",  # "2 tablets"
    r"\b(?:one|two|three|four)\s*tablets?\b",  # "one/two/three/four tablets"
    r"\btwice\s+a\s+day\b",
    r"\bthrice\s+a\s+day\b",
    r"\bthree\s+times\s+a\s+day\b",
    r"\b\d+\s*times\s+a\s+day\b",
)

# Everything the output guard refuses (kept as one tuple of plain strings).
FORBIDDEN_CLAIMS: Tuple[str, ...] = DIAGNOSIS_CLAIMS + DOSAGE_CLAIMS

# Fixed per-language refusal phrase (Q2/A2a temperature≈0 path).
SAFE_REFUSALS: Dict[str, str] = {
    "hi": "मैं चिकित्सा सलाह या खुराक की जानकारी नहीं दे सकता। "
    "कृपया डॉक्टर से संपर्क करें।",
    "en": "I can't give medical advice or dosage instructions. "
    "Please consult a doctor.",
    "ta": "நான் மருத்துவ ஆலோசனை அல்லது மருந்தளவு வழிகாட்டுதலை "
    "வழங்க முடியாது. தயவுசெய்து ஒரு மருத்துவரை அணுகவும்.",
    "te": "నేను వైద్య సలహా లేదా మోతాదు సూచనలను ఇవ్వలేను. "
    "దయచేసి డాక్టర్ను సంప్రదించండి.",
    "bn": "আমি চিকিৎসা পরামর্শ বা ডোজ নির্দেশনা দিতে পারি না। "
    "অনুগ্রহ করে একজন ডাক্তারের সাথে পরামর্শ করুন।",
}

# Fixed per-language escalation handoff phrase (D2 MVP → Q3 per-language).
ESCALATE_PHRASES: Dict[str, str] = {
    "hi": "आपको विशेषज्ञ से जोड़ा जा रहा है। कृपया लाइन पर बने रहें।",
    "en": "Connecting you to a specialist. Please stay on the line.",
    "ta": "உங்களை ஒரு நிபுணரிடம் இணைக்கிறோம். தயவுசெய்து வரியில் இருங்கள்.",
    "te": "మిమ్మల్ని స్పెషలిస్ట్కు కనెక్ట్ చేస్తున్నాము. "
    "దయచేసి లైన్లో ఉండండి.",
    "bn": "আপনাকে একজন বিশেষজ্ঞের সাথে সংযুক্ত করা হচ্ছে। "
    "অনুগ্রহ করে লাইনে থাকুন।",
}


def match_red_flag(text: Optional[str]) -> Optional[Tuple[str, str]]:
    """Return (category, matched_phrase) for the first red-flag hit, else None.

    Case-insensitive substring match against RED_FLAG_CATEGORIES. None / empty
    / whitespace input never matches.
    """
    if not text:
        return None
    lowered = text.lower()
    for category, phrases in RED_FLAG_CATEGORIES.items():
        for phrase in phrases:
            if phrase in lowered:
                return category, phrase
    return None


def escalation_decision(
    severity: Optional[str], caller_text: str = ""
) -> Tuple[bool, str]:
    """Q1/A1a layered escalation triggers -> (should_escalate, reason).

    Escalates when ANY trigger fires, reason records the source:
      * severity red/critical            -> ("severity:<severity>")
      * caller text red-flag keyword hit -> ("red_flag:<category>")
    Neither fires -> (False, ""). The explicit 'escalate' intent is the
    third leg, applied by agent_logic.apply_intent in the agent loop.
    """
    if should_escalate(severity):
        return True, f"severity:{(severity or '').lower()}"
    hit = match_red_flag(caller_text)
    if hit is not None:
        return True, f"red_flag:{hit[0]}"
    return False, ""


def guard_output(text: Optional[str], language: str = "en") -> Tuple[str, str, str]:
    """Q2/A2a deterministic output guard -> (safe_text, flag, reason).

    Scans the agent's response for FORBIDDEN_CLAIMS; on a hit the response is
    replaced with SAFE_REFUSALS[language] (flag "refused", reason "diagnosis"
    or "dosage"). Clean text passes through untouched (flag "safe", reason "").
    """
    if not text:
        return ("" if text is None else text), "safe", ""
    lowered = text.lower()
    for claim in DIAGNOSIS_CLAIMS:
        if claim in lowered:
            return SAFE_REFUSALS.get(language, SAFE_REFUSALS["en"]), "refused", "diagnosis"
    for claim in DOSAGE_CLAIMS:
        if re.search(claim, lowered):
            return SAFE_REFUSALS.get(language, SAFE_REFUSALS["en"]), "refused", "dosage"
    return text, "safe", ""