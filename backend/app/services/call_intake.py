"""In-call voice capture for pharmacovigilance (spec-micc-pv-phase2.md, slice 2B).

A STDLIB-ONLY leaf, the same house pattern as app/services/pharmacovigilance.py
and app/services/guardrails.py: no FastAPI, no SQLAlchemy, no HTTP client, no
voice SDK. Everything here is a pure function over a transcript, so the whole
in-call pipeline is headless-testable while the LiveKit worker / Docker resume
is parked.

The pipeline, in the order the agent runs it:

1. detect_intent            route the call to AE / PQC / MI / none
2. extract_case_fields      capture the ICH E2B minimum from what was said
3. question_script          ask, in-language, for exactly what is still missing
4. special_situation_flags  name the reportable special situations (§2.7/§4.3
                            of the research doc: pregnancy, overdose, medication
                            error, off-label use, lack of effect, death)
5. build_case_payload       assemble the exact POST /api/pv/cases body

THE CALL CENTRE IS A COLLECTOR, NOT A CLINICIAN, AND NOT A CAUSE ANALYST.
Nothing here diagnoses, advises, codes (no MedDRA - that is slice 2C) or
judges. Three consequences are visible in the code:

- classification is NOT reimplemented: detect_intent wraps the Phase-1
  classify_contact_type, so the in-call route and the endpoint route can never
  disagree about what a call is;
- completeness is NOT claimed: build_case_payload returns the request body and
  nothing else, and intake_minimum_criteria applies the SAME
  validate_minimum_criteria call the endpoint makes, so an incomplete call is
  still posted and still stored (ABPI store-and-forward);
- `expectedness` is NEVER filled. It is a judgement against the approved label
  and belongs to the pharmacovigilance officer. `causality_reporter` is only
  ever the caller's own sentence, sliced verbatim - never generated.

EXTRACTION IS HEURISTIC AND DETERMINISTIC: phrase tables per language plus
regexes, with a fixed scan order, so the same transcript always yields the same
dict. It is a capture aid for a PVOIC who reviews the case - it is not a
clinical record and it never guesses. Two deliberate limits: structured values
are matched case-insensitively but returned as the caller said them (a batch
number's case is significant), and native digits (Devanagari / Tamil / Telugu /
Bengali) are folded to ASCII because the API stores ISO dates and plain numbers.

ONE CONTRACT DELIBERATE HERE. A special situation is not the same thing as an
ICH E2A seriousness criterion: a pregnancy or an overdose is reportable, but
neither is a seriousness criterion, and inferring one would be a judgement the
module is not allowed to make. `death` is the one flag that IS a criterion, so
it - and only it - is folded into the payload's `seriousness_flags`, where
classify_seriousness accepts it verbatim. The other five are reportable
situations carried by the caller's own words in the verbatim columns, and they
drive the extra in-call prompts. The router therefore cannot be handed a flag
it would silently drop, and nothing is invented to make room for it.
"""
import functools
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.services.pharmacovigilance import (
    CONTACT_PHRASES,
    MINIMUM_CRITERIA_ELEMENTS,
    PV_LANGUAGES,
    SERIOUSNESS_CRITERIA,
    SPECIAL_SITUATION_TERMS,
    classify_contact_type,
    classify_seriousness,
    validate_minimum_criteria,
)

# ─── The intake contract ────────────────────────────────────────────────────
# The router this module writes for. app/api/pv.py's `router` is mounted at
# PV_INTAKE_PREFIX, and its intake route is the only `post` on "/cases".
PV_INTAKE_PREFIX = "/api/pv"
PV_INTAKE_ROUTE = "/cases"
PV_INTAKE_PATH = PV_INTAKE_PREFIX + PV_INTAKE_ROUTE

# A call is captured from the phone, never typed into a form.
PV_SOURCE_CHANNEL = "voice"

# In-call intents. `none` is the honest default: a booking call is not a PV
# case, and posting one would only add noise to the compliance audit trail.
INTAKE_INTENTS = ("ae", "pqc", "mi", "none")

CONTACT_TO_INTENT = {
    "AE": "ae",
    "PQC": "pqc",
    "MI": "mi",
    "OTHER": "none",
}

# The LLM function each intent routes to. Same shape as the
# MEDICAL_FUNCTIONS entries in app/services/agent_logic.py; kept in its own
# list so the pinned 5-name medical schema stays untouched (adding to it would
# silently change the single source app/services/llm.py ships), and so this
# list can be merged into it when that pin is deliberately lifted.
INTENT_FUNCTIONS = {
    "ae": "report_adverse_event",
    "pqc": "report_quality_complaint",
    "mi": "log_medical_information",
    "none": "",
}

PV_FUNCTIONS: List[Dict[str, Any]] = [
    {
        "name": "report_adverse_event",
        "description": "Record what the caller reported about a suspected adverse "
        "event. Verbatim capture only - no cause, no diagnosis, no advice.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_text": {"type": "string"},
                "product_name": {"type": "string"},
                "patient_age": {"type": "string"},
                "patient_sex": {"type": "string"},
                "patient_initials": {"type": "string"},
                "event_onset_date": {"type": "string"},
                "outcome": {"type": "string"},
                "reporter_type": {"type": "string"},
            },
            "required": ["event_text"],
        },
    },
    {
        "name": "report_quality_complaint",
        "description": "Record a product quality complaint: the product, the batch "
        "or lot number, and the defect as described.",
        "parameters": {
            "type": "object",
            "properties": {
                "defect_description": {"type": "string"},
                "product_name": {"type": "string"},
                "batch_no": {"type": "string"},
                "expiry": {"type": "string"},
                "reporter_type": {"type": "string"},
            },
            "required": ["defect_description"],
        },
    },
    {
        "name": "log_medical_information",
        "description": "Log a medical information question for Medical Affairs. The "
        "question is recorded verbatim; no answer and no advice is given here.",
        "parameters": {
            "type": "object",
            "properties": {
                "question_text": {"type": "string"},
                "product_name": {"type": "string"},
                "language": {"type": "string"},
                "reporter_type": {"type": "string"},
            },
            "required": ["question_text"],
        },
    },
]

# The canonical key set, read once. It mirrors PvCaseCreate in app/api/pv.py 1:1
# (asserted by the test suite against the router's own pydantic model), and both
# the extractor and the builder are constrained to it, so a payload can never
# carry a column the endpoint would drop.
def _blank_fields() -> Dict[str, Any]:
    return {
        "clinic_id": "",
        "call_id": "",
        "language": "en",
        "event_text": "",
        "question_text": "",
        "defect_description": "",
        "seriousness_flags": [],
        "product_id": "",
        "product_name": "",
        "product_strength": "",
        "batch_no": "",
        "expiry": "",
        "photos_url": [],
        "reporter_type": "",
        "reporter_contact": {},
        "patient": {},
        "event_onset_date": "",
        "outcome": "",
        "expectedness": "",
        "causality_reporter": "",
    }


CASE_FIELD_KEYS: Tuple[str, ...] = tuple(_blank_fields())

# Which verbatim column carries the complaint for each intent, and therefore
# which column the endpoint's own `text` fallback reads first.
INTENT_TEXT_COLUMNS = {
    "ae": "event_text",
    "pqc": "defect_description",
    "mi": "question_text",
    "none": "",
}

# The elements a follow-up script covers per intent. A complaint has no patient
# (the complainant IS the reporter), and a batch/lot number is mandatory for it
# even though it is not one of the four E2B minimum elements - so it is asked
# from EXTRA_REQUIRED_ELEMENTS rather than smuggled into the E2B list.
INTENT_REQUIRED_ELEMENTS: Dict[str, Tuple[str, ...]] = {
    "ae": tuple(MINIMUM_CRITERIA_ELEMENTS),
    "pqc": ("reporter", "product", "batch", "event"),
    "mi": ("reporter", "product", "event"),
    "none": (),
}
EXTRA_REQUIRED_ELEMENTS: Dict[str, Tuple[str, ...]] = {"pqc": ("batch",)}

# ICH E2A criteria among the special situations: `death` only. See the module
# docstring - the rest are reportable, not serious.
E2A_SPECIAL_SITUATIONS = ("death",)

# ─── Special situations (research doc §2 / §4.3) ────────────────────────────
# The Phase-1 SPECIAL_SITUATION_TERMS table is the ROUTING subset (a mention of
# any of them routes the call to AE). This is the flag-bearing table: the six
# reportable situations, so an in-call agent knows which extra question to ask.
SPECIAL_SITUATION_FLAGS: Tuple[str, ...] = (
    "pregnancy",
    "overdose",
    "medication_error",
    "off_label",
    "no_effect",
    "death",
)

SPECIAL_SITUATION_PHRASES: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "pregnancy": {
        "hi": ("गर्भवती", "गर्भावस्था", "प्रेग्नेंट", "स्तनपान"),
        "en": ("pregnant", "pregnancy", "breastfeeding", "breast feeding"),
        "ta": ("கர்ப்பநிலை", "கர்ப்பம்", "பாலூட்டல்"),
        "te": ("గర్భధారిణి", "గర్భం", "తల్లిపాల"),
        "bn": ("গর্ভবতী", "গর্ভাবস্থা", "স্তন্যদান"),
    },
    "overdose": {
        "hi": ("बहुत ज्यादा गोली", "ज्यादा दवा", "ज़्यादा दवा", "अधिक मात्रा"),
        "en": ("too many", "overdose", "extra tablets", "double dose"),
        "ta": ("அதிக மாத்திரை", "அதிகமாக", "ஓவர்டோஸ்"),
        "te": ("అధిక మాత్తిరాలు", "ఎక్కువ మాత్తిరాలు", "ఓవర్ డోజ్"),
        "bn": ("অতিরিক্ত ট্যাবলেট", "অনেক বেশি ওষুধ", "ওভারডোজ"),
    },
    "medication_error": {
        "hi": ("गलत दवा", "दूसरी दवा", "गलती से"),
        "en": ("wrong medicine", "wrong tablet", "wrong drug", "by mistake", "mixed up"),
        "ta": ("தவறான மருந்து", "தவறாக"),
        "te": ("తప్పు మందు", "తప్పుగా"),
        "bn": ("ভুল ওষুধ", "ভুল করে"),
    },
    "off_label": {
        "hi": ("बिना डॉक्टर", "डॉक्टर की सलाह के बिना", "प्रिस्क्रिप्शन के बिना"),
        "en": ("without prescription", "off label", "not prescribed", "without my doctor"),
        "ta": ("மருத்துவர் அறிவின்றி", "பரிந்துரை இல்லாமல்"),
        "te": ("వైద్యుని సూచన లేకుండా", "సలహా లేకుండా"),
        "bn": ("প্রেসক্রিপশন ছাড়া", "চিকিৎসকের পরামর্শ ছাড়া"),
    },
    "no_effect": {
        "hi": ("काम नहीं कर रही", "काम नहीं कर रहा", "असर नहीं हो रहा"),
        "en": ("not working", "stopped working", "no effect", "no relief", "did not help"),
        "ta": ("வேலை செய்யவில்லை", "தொழிற்படவில்லை", "பயன் இல்லை"),
        "te": ("పనిచేయడం లేదు", "మారలేదు", "ఫలితం లేదు"),
        "bn": ("কাজ করছে না", "কোনো কাজ হচ্ছে না", "উপকার হচ্ছে না"),
    },
    "death": {
        "hi": ("मृत्यु", "मर गया", "मर गई", "इंतकाल"),
        "en": ("died", "passed away", "death", "deceased"),
        "ta": ("இறந்தார்", "இறந்துவிட்டார்", "இறப்பு"),
        "te": ("మరణించారు", "చనిపోయారు"),
        "bn": ("মারা গেছেন", "মারা গেলেন", "মৃত্যু"),
    },
}

# Outcome vocabulary (ICH E2B shaped, canonical slugs). A spoken "still not
# better" is a fact, not a causality claim.
OUTCOME_VALUES: Tuple[str, ...] = ("fatal", "not_recovered", "recovering", "recovered")
OUTCOME_TERMS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "hi": {
        "fatal": ("मृत्यु", "मर गया", "मर गई", "इंतकाल"),
        "not_recovered": ("ठीक नहीं", "नहीं हुई", "नहीं हुआ", "सुधार नहीं"),
        "recovering": ("थोड़ा बेहतर", "सुधार हो रहा"),
        "recovered": ("पूरी तरह ठीक", "ठीक हो गए", "ठीक हो गई"),
    },
    "en": {
        "fatal": ("died", "passed away", "death", "deceased"),
        "not_recovered": (
            "still suffering",
            "not better",
            "no change",
            "not recovered",
            "still unwell",
        ),
        "recovering": ("getting better", "improving", "a bit better", "better now"),
        "recovered": ("fully recovered", "recovered", "back to normal", "fine now"),
    },
    "ta": {
        "fatal": ("இறந்தார்", "இறந்துவிட்டார்", "இறப்பு"),
        "not_recovered": ("இன்னும் சரியாக இல்லை", "மாறவில்லை", "குறையவில்லை"),
        "recovering": ("குறைந்துவிட்டது", "சற்று மேலும்"),
        "recovered": ("முழுமையாக சரியாக", "சரியாகிட்டது"),
    },
    "te": {
        "fatal": ("మరణించారు", "చనిపోయారు"),
        "not_recovered": ("ఇంకా కోల్కోలేదు", "మారలేదు"),
        "recovering": ("కొంత మెరుగైంది"),
        "recovered": ("పూర్తిగా కోల్కొన్నాడు", "కోల్కొన్నారు"),
    },
    "bn": {
        "fatal": ("মারা গেছেন", "মারা গেলেন", "মৃত্যু"),
        "not_recovered": ("এখনও সুস্থ নন", "উন্নতি হয়নি", "মারেনি"),
        "recovering": ("কিছুটা উন্নতি"),
        "recovered": ("সুস্থ হয়ে গেছেন", "ঠিক হয়ে গেছে"),
    },
}

# ─── Extraction tables ──────────────────────────────────────────────────────
# A product name is spoken in Latin script in every one of these languages
# ("Dolo", "Telma"), so the native word for medicine/tablet is the LABEL and
# the name itself is matched as Latin tokens.
PRODUCT_LABEL_PHRASES: Dict[str, Tuple[str, ...]] = {
    "hi": ("दवा", "दवाई", "गोली", "टैबलेट"),
    "en": ("medicine", "tablet", "tab", "drug", "pill", "capsule"),
    "ta": ("மருந்து", "மாத்திரை"),
    "te": ("మందు", "టాబ్లెట్"),
    "bn": ("ওষুধ", "ট্যাবলেট"),
}

# A STARTER hint list, not a product dictionary: the products table is
# authoritative and joins on product_id. It only fills product_name when the
# caller named a medicine this list happens to know, which beats a bare capture
# after the label word.
SEED_PRODUCT_NAMES: Tuple[str, ...] = (
    "amoxicillin",
    "amoxycillin",
    "azithromycin",
    "levofloxacin",
    "paracetamol",
    "ondansetron",
    "pantoprazole",
    "metformin",
    "telmisartan",
    "glimepiride",
    "atorvastatin",
    "ibuprofen",
    "cetirizine",
    "augmentin",
    "azithral",
    "allegra",
    "cetralgin",
    "glycomet",
    "amlodipine",
    "ondem",
    "crocin",
    "brufen",
    "disprin",
    "daonil",
    "aspirin",
    "dolo",
    "losar",
    "moxicip",
    "calpol",
    "oflox",
    "combiflam",
)

# Batch / lot. A captured value must contain a digit, so the English word "lot"
# can never harvest "a lot of tablets".
BATCH_LABEL_PHRASES: Dict[str, Tuple[str, ...]] = {
    "hi": ("बैच नंबर", "बैच नम्बर", "बैच", "लॉट"),
    "en": ("batch number", "batch no", "batch", "lot number", "lot"),
    "ta": ("தொகை எண்", "இலாச் எண்", "தொகை"),
    "te": ("బ్యాచ్ నంబర్", "బ్యాచ్"),
    "bn": ("ব্যাচ নাম্বার", "ব্যাচ", "লট নম্বার"),
}

EXPIRY_LABEL_PHRASES: Dict[str, Tuple[str, ...]] = {
    "hi": ("एक्सपायरी", "मियाद"),
    "en": ("expiry date", "expiry", "expires", "exp date", "exp."),
    "ta": ("காலாவதி தேதி", "காலாவதி"),
    "te": ("ముగుదురు తేదీ", "ముగుదురు"),
    "bn": ("মেয়াদ শেষ", "মেয়াদ"),
}

SEX_TERMS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "hi": {"male": ("पुरुष", "आदमी", "लड़का"), "female": ("महिला", "स्त्री", "लड़की", "औरत")},
    "en": {"male": ("male", "man", "boy"), "female": ("female", "woman", "girl")},
    "ta": {"male": ("ஆண்", "சிறுவன்"), "female": ("பெண்", "செல்வி")},
    "te": {"male": ("పురుషుడు", "అబ్బరు", "అబ్బ"), "female": ("స్త్రీ", "బాటి")},
    "bn": {"male": ("பুরুষ", "ছেলে"), "female": ("মহিলা", "মেয়ে", "স্ত্রী")},
}

# Reporter self-description. An empty string (never "other") when nobody
# described themselves: "other" is a CATEGORY, and validate_minimum_criteria
# treats any non-blank reporter field as an identifiable reporter, so guessing a
# category would manufacture a reportable case.
REPORTER_HCP_TERMS: Dict[str, Tuple[str, ...]] = {
    "hi": ("मैं डॉक्टर", "डॉक्टर हूँ", "मैं नर्स"),
    "en": ("i am a doctor", "i am a physician", "i am a nurse", "i am a pharmacist", "this is doctor"),
    "ta": ("நான் மருத்துவர்", "மருத்துவர் நான்", "நான் நர்ஸ்"),
    "te": ("నేను వైద్యుడు", "నేను వైద్యుడను"),
    "bn": ("আমি ডাক্তার", "আমি একজন ডাক্তার", "আমি নার্স"),
}
REPORTER_PATIENT_TERMS: Dict[str, Tuple[str, ...]] = {
    "hi": ("मैं मरीज", "मेरा बेटा", "मेरी बेटी", "मेरी माँ", "मेरी पत्नी", "मैं बीमार"),
    "en": (
        "i am the patient",
        "i am a patient",
        "i am suffering",
        "this is my mother",
        "this is my father",
        "my mother",
        "my father",
        "my son",
        "my daughter",
        "my wife",
        "my husband",
        "my brother",
        "my sister",
    ),
    "ta": ("நான் நோயாளி", "என் மகன்", "என் மகள்"),
    "te": ("నేను రోగి", "నా కొడుకు", "నా కుమార్తె"),
    "bn": ("আমি রোগী", "আমার ছেলে", "রোগীর ছেলে", "আমার মেয়ে", "রোগীর মেয়ে"),
}

# Cues that the reporter is LINKING the product to the event. The sentence is
# stored verbatim; the module draws no conclusion from it.
CAUSALITY_CUES: Dict[str, Tuple[str, ...]] = {
    "hi": ("इस दवा की वजह", "इसकी वजह", "इसके कारण", "कारण बत"),
    "en": ("caused", "because of", "due to", "after taking", "made it worse"),
    "ta": ("இதனால்", "காரணமாக", "இப்பிறகு"),
    "te": ("దీని వల్ల", "కారణంగా", "తర్వాత"),
    "bn": ("এর কারণে", "কারণে", "এর পরে"),
}

# Age: (pattern, unit). "years" -> the number; "months" keeps its unit so a
# downstream analyst never reads a converted 0.5 as a decimal age.
AGE_PATTERNS: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "hi": (
        (r"(\d+)\s*(?:साल|वर्ष)", "years"),
        (r"उम्र\s*(\d+)", "years"),
        (r"(\d+)\s*(?:महीना|महीने|महीनों)", "months"),
    ),
    "en": (
        (r"(\d+)\s*years?\s*old", "years"),
        (r"(\d+)\s*year\s*old", "years"),
        (r"aged?\s*(\d+)", "years"),
        (r"\bage\s*(\d+)", "years"),
        (r"(\d+)\s*,?\s*(?:male|female|man|woman|boy|girl)", "years"),
        (r"(\d+)\s*months?(?:\s*old)?", "months"),
    ),
    "ta": (
        (r"(\d+)\s*(?:வயது|வயதுள்ள)", "years"),
        (r"(\d+)\s*(?:மாதங்கள்|மாதம்)", "months"),
    ),
    "te": (
        (r"(\d+)\s*(?:సంవత్సరాలు|ఏళ్లు|సంవత్సరం)", "years"),
        (r"(\d+)\s*(?:నెలలు|నెల)", "months"),
    ),
    "bn": (
        (r"(\d+)\s*(?:বছর|বছরের)", "years"),
        (r"বয়স\s*(\d+)", "years"),
        (r"(\d+)\s*(?:মাস|মাসের)", "months"),
    ),
}

# English number words, spoken far more often than digits on a phone call.
ENGLISH_NUMBERS: Dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_NUMBER_ALTERNATION = "|".join(ENGLISH_NUMBERS)

ONSET_TODAY_TERMS: Dict[str, Tuple[str, ...]] = {
    "hi": ("आज",),
    "en": ("today",),
    "ta": ("இன்று",),
    "te": ("ఇవాజు",),
    "bn": ("আজ",),
}
ONSET_YESTERDAY_TERMS: Dict[str, Tuple[str, ...]] = {
    "hi": ("कल",),
    "en": ("yesterday",),
    "ta": ("நேற்று",),
    "te": ("నిన్న",),
    "bn": ("গতকাল",),
}
# A count of days / months back from today ("two days ago", "3 दिन पहले").
ONSET_AGO_PATTERN = (
    r"(?:(\d+)|(" + _NUMBER_ALTERNATION + r"))\s*"
    r"(?:days?|दिन(?:ों)?|దిన(?:ాలు)?|నెలలు|మాసం|months?|மாதங்கள்|দিন(?:গুলো)?|మాసాలు)"
)

MONTH_NAMES: Dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

# Devanagari / Tamil / Telugu / Bengali digits -> ASCII. The API stores ISO
# dates and plain numbers, so a native-digit transcript must not produce a
# 422 or a string the officer has to re-type.
#
# `str.translate` silently IGNORES a mapping keyed by 1-character STRINGS - it
# only honours ORDINAL keys - so a str-keyed table reads fine in a REPL and
# leaves every digit untouched at runtime. `str.maketrans` builds the
# ordinal-keyed table, which is the only reason this is not one line shorter.
_NATIVE_DIGIT_RANGES = ("\u0966", "\u0be6", "\u0c66", "\u09e6")
DIGIT_TRANSLATION = str.maketrans(
    {
        chr(ord(base) + offset): str(offset)
        for base in _NATIVE_DIGIT_RANGES
        for offset in range(10)
    }
)

# Letters across the 5 scripts (an Indic "initial" is a whole akshara).
_LETTER = r"[A-Za-z\u0900-\u097f\u0b80-\u0bff\u0c00-\u0c7f\u0980-\u09ff]"
# An akshara is a consonant PLUS a matra/virama, so "के" or "கே" is two
# codepoints, not one. One-or-three codepoints per token is what a spoken
# initial looks like in all 5 scripts, and the upper bound is what keeps a
# sentence ("Dr. Kumar. She ...") from being read as a pair of initials.
_INITIAL_TOKEN = rf"{_LETTER}{{1,3}}"
INITIALS_DOTTED_RE = re.compile(
    rf"({_INITIAL_TOKEN}\.\s?{_INITIAL_TOKEN}\.)", re.IGNORECASE
)
INITIALS_MARKER_RE = re.compile(
    r"(?:initials?|initial|प्रथमाक्षर|आद्याक्षर|முதல் எழுத்து|ప్రథమ అక్షరం|প্রথম অক্ষর)"
    r"\s*(?:are|is)?\s*([A-Za-z]{2,4})",
    re.IGNORECASE,
)
# "e.g." / "i.e." are dotted pairs, not patient initials.
_NOT_INITIALS = ("eg", "ie", "mrc", "vs")
# "Mr. R." is a title and an initial, never a patient's initials. Checked per
# token, because the joined form of "Mr. R." is not a recognisable word.
_NOT_TITLES = ("mr", "mrs", "ms", "dr", "shri", "smt", "prof")

PRODUCT_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9'+]*(?:[ ][A-Za-z0-9'+]+)?")
BATCH_VALUE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-/]{1,15}")
# Longest alternative first: mc/g pairs would otherwise capture the "g" of
# "500 mg". The unit is matched inside a WORD boundary so an abbreviation
# ("A.K.") is never read as a dose.
STRENGTH_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*\b(mcg|mg|ml|iu|units?|%|g)\b",
    re.IGNORECASE,
)
EXPIRY_ISO_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
EXPIRY_DMY_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
EXPIRY_MY_RE = re.compile(r"(\d{1,2})/(\d{4})")
EXPIRY_MONTH_NAME_RE = re.compile(
    r"(" + "|".join(MONTH_NAMES) + r")\s+(\d{4})", re.IGNORECASE
)
ONSET_ISO_RE = EXPIRY_ISO_RE
ONSET_DMY_RE = EXPIRY_DMY_RE
# A dotted initials run and a decimal must never end a sentence. Both run on
# `_INITIAL_TOKEN`, not on a single codepoint, or "ஆர்.கே." would be split at its
# own first dot and the sentence holding it would be cut in half.
_ABBREV_RE = re.compile(rf"{_INITIAL_TOKEN}\.(?:\s?{_INITIAL_TOKEN}\.)+")
_INITIAL_TOKEN_RE = re.compile(_INITIAL_TOKEN, re.IGNORECASE)
_DECIMAL_RE = re.compile(r"\d+\.\d+")
_SENTENCE_END_RE = re.compile(r"[.!?।॥\n]+")
_TRAILING_NOISE_RE = re.compile(r"^[\s\-–—:;,.]+")
# Whether a phrase table entry is written in Latin script.
_ASCII_PHRASE_RE = re.compile(r"^[\x20-\x7e]+$")

# Lookback window after a label word, and where a value may stop (a sentence
# boundary). Bounded so a label can never harvest the rest of the call.
_VALUE_WINDOW = 48


# ─── In-language follow-up questions ────────────────────────────────────────
# One question per element, in the caller's own language. Each one ASKS for a
# fact the caller may simply not have volunteered; none of them assesses,
# diagnoses, advises or suggests. A caller who declines is recorded and the
# case is still stored (ABPI store-and-forward).
# Exactly one entry per (intent, element a caller can be asked for, language):
# 11 elements x 5 languages = 55. An element an intent does not cover has no
# question at all, so a missing key is a real bug rather than a silent blank.
QUESTION_BANK: Dict[Tuple[str, str, str], str] = {
    ("ae", "reporter", "en"): (
        "Before I record this, may I take your name, and are you the patient, "
        "a family member or a doctor?"
    ),
    ("ae", "patient", "en"): (
        "May I have the patient's age, gender and initials, as far as you know them?"
    ),
    ("ae", "product", "en"): (
        "Which medicine is it - the name and strength printed on the pack?"
    ),
    ("ae", "event", "en"): (
        "Can you tell me exactly what happened, and when did it start?"
    ),
    ("pqc", "reporter", "en"): (
        "Before I record this, may I take your name, and are you the patient, "
        "a family member or a doctor?"
    ),
    ("pqc", "product", "en"): "Which medicine is it - the name on the pack?",
    ("pqc", "batch", "en"): (
        "Could you read out the batch or lot number printed on the pack?"
    ),
    ("pqc", "event", "en"): "Can you tell me exactly what is wrong with the pack?",
    ("mi", "reporter", "en"): (
        "Before I note your question, may I take your name, and are you the "
        "patient, a family member or a doctor?"
    ),
    ("mi", "product", "en"): (
        "Which medicine is your question about - the name on the pack?"
    ),
    ("mi", "event", "en"): (
        "May I read back the question so I record it exactly as you asked it?"
    ),
    ("ae", "reporter", "hi"): (
        "रिकॉर्ड करने से पहले क्या आप अपना नाम बता सकते हैं, और आप मरीज हैं, "
        "परिवार के सदस्य हैं या डॉक्टर?"
    ),
    ("ae", "patient", "hi"): "कृपया मरीज की उम्र, लिंग और प्रथमाक्षर बताइए?",
    ("ae", "product", "hi"): "यह कौन सी दवा है - पैक पर लिखा नाम और मात्रा?",
    ("ae", "event", "hi"): "कृपया बताइए कि हुआ क्या था और शुरुआत कब हुई?",
    ("pqc", "reporter", "hi"): (
        "रिकॉर्ड करने से पहले क्या आप अपना नाम बता सकते हैं, और आप मरीज हैं, "
        "परिवार के सदस्य हैं या डॉक्टर?"
    ),
    ("pqc", "product", "hi"): "यह कौन सी दवा है - पैक पर लिखा नाम?",
    ("pqc", "batch", "hi"): "कृपया पैक पर छपा बैच या लॉट नंबर पढ़िए?",
    ("pqc", "event", "hi"): "कृपया बताइए कि पैक में ठीक से क्या कमी है?",
    ("mi", "reporter", "hi"): (
        "आपका सवाल दर्ज करने से पहले क्या आप अपना नाम बता सकते हैं, और आप मरीज हैं, "
        "परिवार के सदस्य हैं या डॉक्टर?"
    ),
    ("mi", "product", "hi"): "आपका सवाल किस दवा के बारे में है - पैक पर लिखा नाम?",
    ("mi", "event", "hi"): "क्या मैं आपका सवाल दोहरा दूँ ताकि वही दर्ज हो?",
    ("ae", "reporter", "ta"): (
        "பதிவு செய்வதற்கு முன் உங்கள் பெயரையும், நீங்கள் நோயாளியா குடும்ப "
        "உறுப்பினரா அல்லது மருத்துவரா என்பதையும் தயவுசெய்து சொல்லுங்கள்?"
    ),
    ("ae", "patient", "ta"): (
        "நோயாளியின் வயது, பாலினம் மற்றும் முதல் எழுத்துகளைத் தயவுசெய்து சொல்லுங்கள்?"
    ),
    ("ae", "product", "ta"): "எது மருந்து - பொதியில் எழுதப்பட்ட பெயர் மற்றும் அளவு?",
    ("ae", "event", "ta"): "சரியாக என்ன நடந்தது, எப்போது தொடங்கியது என்று சொல்லுங்கள்?",
    ("pqc", "reporter", "ta"): (
        "பதிவு செய்வதற்கு முன் உங்கள் பெயரையும், நீங்கள் நோயாளியா குடும்ப "
        "உறுப்பினரா அல்லது மருத்துவரா என்பதையும் தயவுசெய்து சொல்லுங்கள்?"
    ),
    ("pqc", "product", "ta"): "எது மருந்து - பொதியில் எழுதப்பட்ட பெயர்?",
    ("pqc", "batch", "ta"): "பொதியில் அச்சிடப்பட்ட தொகை எண்ணைப் படித்துச் சொல்லுங்கள்?",
    ("pqc", "event", "ta"): "பொதியில் உள்ள குறைபாடு என்ன என்று சொல்லுங்கள்?",
    ("mi", "reporter", "ta"): (
        "உங்கள் கேள்வியைப் பதிவு செய்வதற்கு முன் பெயரையும், நீங்கள் நோயாளியா "
        "குடும்ப உறுப்பினரா அல்லது மருத்துவரா என்பதையும் சொல்லுங்கள்?"
    ),
    ("mi", "product", "ta"): (
        "உங்கள் கேள்வி எந்த மருந்து பற்றியது - பொதியில் எழுதப்பட்ட பெயர்?"
    ),
    ("mi", "event", "ta"): "கேள்வியை நீங்கள் கேட்டபடி சரியாக சொல்லுங்கள்?",
    ("ae", "reporter", "te"): (
        "నమోదు చేయడానికి ముందు మీ పేరు, మరియు మీరు రోగిలా, కుటుంబ సభ్యులా లేదా "
        "వైద్యుడా అనేది చెప్పగలరా?"
    ),
    ("ae", "patient", "te"): "రోగి వయస్సు, లింగం మరియు ప్రథమ అక్షరాలను చెప్పగలరా?",
    ("ae", "product", "te"): "ఇది ఏ మందు - ప్యాకెట్ మీద ఉన్న పేరు మరియు మోతాదు?",
    ("ae", "event", "te"): "ఖచ్చితంగా ఏమి జరిగింది, ఎప్పుడు మొదలైంది అనేది చెప్పగలరా?",
    ("pqc", "reporter", "te"): (
        "నమోదు చేయడానికి ముందు మీ పేరు, మరియు మీరు రోగిలా, కుటుంబ సభ్యులా లేదా "
        "వైద్యుడా అనేది చెప్పగలరా?"
    ),
    ("pqc", "product", "te"): "ఇది ఏ మందు - ప్యాకెట్ మీద ఉన్న పేరు?",
    ("pqc", "batch", "te"): "ప్యాకెట్ మీద ఉన్న బ్యాచ్ నంబర్ చదివి చెప్పండి?",
    ("pqc", "event", "te"): "ప్యాకెట్‌లో ఏ లోపం ఉందో చెప్పగలరా?",
    ("mi", "reporter", "te"): (
        "మీ ప్రశ్నను నమోదు చేయడానికి ముందు పేరు, మరియు మీరు రోగిలా, కుటుంబ "
        "సభ్యులా లేదా వైద్యుడా అనేది చెప్పగలరా?"
    ),
    ("mi", "product", "te"): "మీ ప్రశ్న ఏ మందు గురించి - ప్యాకెట్ మీద ఉన్న పేరు?",
    ("mi", "event", "te"): "మీరు అడిగిన ప్రశ్నను అలాగేనే రికార్డు చేయాలా?",
    ("ae", "reporter", "bn"): (
        "রেকর্ড করার আগে আপনার নাম বলুন, এবং আপনি রোগী, পরিবারের সদস্য "
        "নাকি ডাক্তার তা জানাবেন?"
    ),
    ("ae", "patient", "bn"): "রোগীর বয়স, লিঙ্গ ও প্রথম অক্ষরগুলো জানাবেন?",
    ("ae", "product", "bn"): "এটি কোন ওষুধ - প্যাকেটে লেখা নাম ও মাত্রা?",
    ("ae", "event", "bn"): "ঠিক কী হয়েছিল এবং কখন শুরু হয়েছিল জানাবেন?",
    ("pqc", "reporter", "bn"): (
        "রেকর্ড করার আগে আপনার নাম বলুন, এবং আপনি রোগী, পরিবারের সদস্য "
        "নাকি ডাক্তার তা জানাবেন?"
    ),
    ("pqc", "product", "bn"): "এটি কোন ওষুধ - প্যাকেটে লেখা নাম?",
    ("pqc", "batch", "bn"): "প্যাকেটে ছাপা ব্যাচ বা লট নম্বরটি পড়ে জানাবেন?",
    ("pqc", "event", "bn"): "প্যাকেটে ঠিক কী সমস্যা তা জানাবেন?",
    ("mi", "reporter", "bn"): (
        "আপনার প্রশ্নটি লিখে রাখার আগে নাম বলুন, এবং আপনি রোগী, পরিবারের সদস্য "
        "নাকি ডাক্তার তা জানাবেন?"
    ),
    ("mi", "product", "bn"): "আপনার প্রশ্ন কোন ওষুধ সম্পর্কে - প্যাকেটে লেখা নাম?",
    ("mi", "event", "bn"): "আমি কি আপনার প্রশ্নটি হুবহু বলে লিখে রাখি?",
}

# The extra in-call prompt for each reportable special situation. They ask for
# the fact and stop there: a prompt that told the caller to stop the medicine or
# to see a doctor would be medical advice, which this module may never give.
SPECIAL_SITUATION_PROMPTS: Dict[Tuple[str, str], str] = {
    ("pregnancy", "en"): (
        "You mentioned a pregnancy - is the patient pregnant, or was the medicine "
        "taken during pregnancy or breastfeeding? I only record what you tell me."
    ),
    ("overdose", "en"): (
        "You mentioned more than the recommended amount - roughly how many, and "
        "when?"
    ),
    ("medication_error", "en"): (
        "You mentioned a wrong or mixed-up medicine - which one was taken, and "
        "which one was meant to be?"
    ),
    ("off_label", "en"): (
        "You mentioned use outside the prescription - was the medicine taken "
        "without a doctor's advice?"
    ),
    ("no_effect", "en"): (
        "You mentioned the medicine is not working - how long has it been taken, "
        "and has anything changed?"
    ),
    ("death", "en"): (
        "I'm very sorry for your loss. You mentioned a death - when did the "
        "person pass away, and was the medicine still being taken?"
    ),
    ("pregnancy", "hi"): (
        "आपने गर्भावस्था का ज़िक्र किया - क्या मरीज गर्भवती है, या गर्भावस्था के दौरान "
        "दवा ली गई थी? मैं केवल आपने जो कहा वही दर्ज करता हूँ?"
    ),
    ("overdose", "hi"): (
        "आपने बताया कि ज़्यादा दवा ली गई - लगभग कितनी गोली, और कब?"
    ),
    ("medication_error", "hi"): (
        "आपने गलत दवा का ज़िक्र किया - कौन सी दवा ली गई, और कौन सी लेनी थी?"
    ),
    ("off_label", "hi"): (
        "आपने डॉक्टर की सलाह के बिना दवा लेने का ज़िक्र किया - क्या दवा बिना डॉक्टर "
        "की सलाह के ली गई थी?"
    ),
    ("no_effect", "hi"): (
        "आपने कहा कि दवा काम नहीं कर रही - कितने दिन से ली जा रही है, और क्या बदला है?"
    ),
    ("death", "hi"): (
        "आपके दुख की बात है। आपने मृत्यु का ज़िक्र किया - कब हुई, और क्या तब तक दवा "
        "चल रही थी?"
    ),
    ("pregnancy", "ta"): (
        "நீங்கள் கர்ப்பத்தை குறிப்பிட்டீர்கள் - நோயாளி கர்ப்பமுடையவரா, அல்லது "
        "கர்ப்பகாலத்தில் மருந்து எடுக்கப்பட்டதா? நான் நீங்கள் சொன்னதையே பதிவு செய்கிறேன்?"
    ),
    ("overdose", "ta"): (
        "நீங்கள் பரிந்துரையை விட அதிகம் எடுத்ததாக சொன்னீர்கள் - எத்தனை, எப்போது?"
    ),
    ("medication_error", "ta"): (
        "நீங்கள் தவறான மருந்து என்று சொன்னீர்கள் - எது எடுக்கப்பட்டது, எது எடுக்க வேண்டியிருந்தது?"
    ),
    ("off_label", "ta"): (
        "நீங்கள் மருத்துவர் அறிவின்றி எடுத்ததாக சொன்னீர்கள் - மருந்து மருத்துவர் "
        "அறிவின்றி எடுக்கப்பட்டதா?"
    ),
    ("no_effect", "ta"): (
        "மருந்து வேலை செய்யவில்லை என்று சொன்னீர்கள் - எத்தனை நாள் எடுக்கிறீர்கள், "
        "ஏதாவது மாற்றம் இருக்கிறதா?"
    ),
    ("death", "ta"): (
        "உங்கள் இழப்பு குறிப்பாக வருத்தமானது. மரணம் குறிப்பிட்டீர்கள் - எப்போது "
        "இறந்தார், அப்போது மருந்து தொடர்ந்து எடுக்கப்பட்டிருந்ததா?"
    ),
    ("pregnancy", "te"): (
        "మీరు గర్భం గురించి చెప్పారు - రోగి గర్భవతియా, లేక గర్భకాలంలో మందు తీసుకున్నారా? "
        "నేను మీరు చెప్పినదాన్ని మాత్రమే నమోదు చేస్తాను?"
    ),
    ("overdose", "te"): (
        "మీరు సిఫార్సు కంటే ఎక్కువ తీసుకున్నట్లు చెప్పారు - సుమారు ఎన్ని, ఎప్పుడు?"
    ),
    ("medication_error", "te"): (
        "మీరు తప్పు మందు అని చెప్పారు - ఏది తీసుకున్నారు, ఏది తీసుకోవాలనుకున్నారు?"
    ),
    ("off_label", "te"): (
        "మీరు వైద్యుని సూచన లేకుండా తీసుకున్నట్లు చెప్పారు - వైద్యుని సూచన లేకుండా "
        "తీసుకున్నారా?"
    ),
    ("no_effect", "te"): (
        "మందు పనిచేయడం లేదని చెప్పారు - ఎన్ని రోజులుగా తీసుకుంటున్నారు, ఏమైనా మార్పు ఉందా?"
    ),
    ("death", "te"): (
        "మీ కష్టం గురించి విచారం. మరణం గురించి చెప్పారు - ఎప్పుడు చనిపోయారు, అప్పటికే "
        "మందు తీసుకుంటున్నారా?"
    ),
    ("pregnancy", "bn"): (
        "আপনি গর্ভাবস্থার কথা বলেছেন - রোগী কি গর্ভবতী, নাকি গর্ভাবস্থায় ওষুধ খাওয়া হয়েছে? "
        "আমি আপনি যা বলেছেন তাই রেকর্ড করি?"
    ),
    ("overdose", "bn"): (
        "আপনি বেশি ওষুধ খাওয়ার কথা বলেছেন - আনুমানিক কতটি, কখন?"
    ),
    ("medication_error", "bn"): (
        "আপনি ভুল ওষুধের কথা বলেছেন - কোনটি খাওয়া হয়েছিল, আর কোনটি খাওয়ার কথা ছিল?"
    ),
    ("off_label", "bn"): (
        "আপনি চিকিৎসকের পরামর্শ ছাড়া ওষুধ খাওয়ার কথা বলেছেন - চিকিৎসকের পরামর্শ ছাড়াই "
        "খাওয়া হয়েছিল?"
    ),
    ("no_effect", "bn"): (
        "আপনি বলেছেন ওষুধ কাজ করছে না - কতদিন ধরে খাচ্ছেন, কিছু বদলেছে কি?"
    ),
    ("death", "bn"): (
        "আপনার দুঃখের বিষয়। আপনি মৃত্যুর কথা বলেছেন - কখন হয়েছে, তখন কি ওষুধ চলছিল?"
    ),
}


# ─── Normalization helpers ──────────────────────────────────────────────────
def _language(language: Any) -> str:
    """A supported PV language code, or English."""
    code = str(language or "").strip().lower()
    return code if code in PV_LANGUAGES else "en"


def _search_languages(language: Any) -> Tuple[str, ...]:
    """The caller's language first, then English.

    Indian calls are code-switched in practice - a Hindi caller says "batch
    number", a Bengali caller says "Dolo" - so an English-labelled fact is
    searched for in every language. The order is fixed, so the result is not.
    """
    code = str(language or "").strip().lower()
    if code in PV_LANGUAGES:
        return (code, "en") if code != "en" else ("en",)
    return ("en",)


def _normalize(text: Any) -> str:
    """Native digits -> ASCII, whitespace collapsed. Case is PRESERVED.

    Case has to survive: a batch number's case is significant, and a product
    name is matched case-insensitively but stored the way the caller said it.
    """
    if text is None:
        return ""
    return " ".join(str(text).translate(DIGIT_TRANSLATION).split())


def _contains(haystack: str, needle: str) -> bool:
    """Plain substring, case-folded - the Phase-1 `_phrase_hits` rule.

    Reserved for ROUTING evidence, where mirroring Phase-1's own substring
    semantics is the whole point: a phrase this module claims decided the route
    must be a phrase the endpoint's classifier actually matched. Every other
    lookup wants `_mentions` instead.
    """
    return bool(needle) and needle.casefold() in haystack.casefold()


@functools.lru_cache(maxsize=2048)
def _phrase_re(phrase: str) -> "re.Pattern[str]":
    """A word-aware matcher for one phrase-table entry, built once.

    `\b` is a LATIN rule. It fires between a word character and a non-word
    character, and an Indic script is full of non-word characters that are part
    of a word - a matra or a virama. So `\b` around "மருந்து" (the last
    codepoint is a matra) or "బ్యాచ్" (a virama) can NEVER match, however
    correct the label is, and a naive `\b` silently makes those languages
    unfindable.

    So the rule is split by script rather than by guesswork: a Latin phrase gets
    `\b...\b` (so "man" stops matching inside "too many"), and a native-script
    phrase falls back to a plain substring - the only form that works there.
    """
    if _ASCII_PHRASE_RE.match(phrase):
        return re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
    return re.compile(re.escape(phrase), re.IGNORECASE)


def _label_match(text: str, phrase: str):
    """The first word-aware match of a label word, or None.

    The label tables (medicine / batch / expiry) need the POSITION, not just a
    yes/no, because the value is what follows the label.
    """
    return _phrase_re(phrase).search(text) if phrase else None


def _mentions(text: str, phrase: str) -> bool:
    """Is `phrase` in `text` as a whole word (see `_phrase_re` for the split)?"""
    return _label_match(text, phrase) is not None


def _masked(text: str) -> str:
    """Blank out dotted initials and decimals so they cannot end a sentence.

    Same length as the input, so a span in the masked text is the same span in
    the original - the caller's own sentence can be sliced verbatim.
    """
    masked = _ABBREV_RE.sub(lambda m: "_" * len(m.group(0)), text)
    return _DECIMAL_RE.sub(lambda m: "_" * len(m.group(0)), masked)


def _sentences(text: Any) -> List[str]:
    """The caller's utterances, in order, each with its own words intact."""
    raw = str(text or "")
    if not raw.strip():
        return []
    masked = _masked(raw)
    out: List[str] = []
    start = 0
    for match in _SENTENCE_END_RE.finditer(masked):
        chunk = raw[start : match.end()].strip()
        if chunk:
            out.append(chunk)
        start = match.end()
    tail = raw[start:].strip()
    if tail:
        out.append(tail)
    return out


def _window_after(text: str, end: int) -> str:
    """The bounded look-ahead after a label word, stopping at a sentence end."""
    raw = text[end : end + _VALUE_WINDOW]
    masked = _masked(raw)
    stop = _SENTENCE_END_RE.search(masked)
    return masked[: stop.start()] if stop else masked


# ─── Field extractors (fixed scan order = deterministic output) ──────────────
def _extract_age(text: str, languages: Tuple[str, ...]) -> str:
    for language in languages:
        for pattern, unit in AGE_PATTERNS.get(language, ()):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1) if unit == "years" else f"{match.group(1)} months"
    return ""


def _extract_sex(text: str, languages: Tuple[str, ...]) -> str:
    # Word-aware, not substring: "too many tablets" contains "man", and a
    # substring match would record the sex of a caller who never said it.
    for language in languages:
        terms = SEX_TERMS.get(language, {})
        for value in ("male", "female"):
            if any(_mentions(text, phrase) for phrase in terms.get(value, ())):
                return value
    return ""


def _is_initials(candidate: str) -> bool:
    """Is a dotted pair a patient's initials, or a title / known abbreviation?

    Checked per token, because the joined form of "Mr. R." is not a recognisable
    word: comparing "mr r" against a list of two-letter abbreviations would let
    a doctor's honorific into a patient's initials column.
    """
    tokens = [token.casefold() for token in _INITIAL_TOKEN_RE.findall(candidate)]
    if not tokens:
        return False
    if any(token in _NOT_INITIALS or token in _NOT_TITLES for token in tokens):
        return False
    return "".join(tokens) not in _NOT_INITIALS


def _extract_initials(text: str, languages: Tuple[str, ...]) -> str:
    for match in INITIALS_DOTTED_RE.finditer(text):
        if _is_initials(match.group(1)):
            return match.group(1)
    for language in languages:
        match = INITIALS_MARKER_RE.search(text)
        if match and language:
            return match.group(2)
    return ""


def _extract_product_name(text: str, languages: Tuple[str, ...]) -> str:
    # (1) a known name, earliest mention wins, longest name breaks a tie.
    best: Tuple[int, int, str] = (len(text) + 1, 0, "")
    for name in SEED_PRODUCT_NAMES:
        for match in re.finditer(rf"\b{re.escape(name)}\b", text, re.IGNORECASE):
            candidate = (match.start(), -len(name), match.group(0))
            if candidate < best:
                best = candidate
    if best[2]:
        return best[2]
    # (2) the word for medicine/tablet, then the Latin name the caller used.
    for language in languages:
        for label in PRODUCT_LABEL_PHRASES.get(language, ()):
            match = _label_match(text, label)
            if not match:
                continue
            tail = PRODUCT_NAME_RE.match(_window_after(text, match.end()).lstrip())
            if not tail:
                continue
            tokens = tail.group(0).split()
            # A trailing number is a strength ("Telma 40"), never part of the name.
            if len(tokens) > 1 and tokens[-1].isdigit():
                tokens = tokens[:-1]
            if tokens:
                return " ".join(tokens)
    return ""


def _extract_strength(text: str) -> str:
    match = STRENGTH_RE.search(text)
    if not match:
        return ""
    return f"{match.group(1)} {match.group(2)}"


def _extract_batch(text: str, languages: Tuple[str, ...]) -> str:
    for language in languages:
        for label in BATCH_LABEL_PHRASES.get(language, ()):
            match = _label_match(text, label)
            if not match:
                continue
            value = BATCH_VALUE_RE.match(_window_after(text, match.end()).lstrip())
            if value and re.search(r"\d", value.group(0)):
                return value.group(0)
    return ""


def _iso_date(year: int, month: int, day: int) -> str:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def _day_month(text: str) -> str:
    """`d/m/yyyy` or `m/d/y`: the first number wins unless one is impossible."""
    match = EXPIRY_DMY_RE.search(text)
    if not match:
        return ""
    first, second, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    day, month = (first, second) if second <= 12 else (second, first)
    return _iso_date(year, month, day)


def _extract_expiry(text: str, languages: Tuple[str, ...]) -> str:
    for language in languages:
        for label in EXPIRY_LABEL_PHRASES.get(language, ()):
            match = _label_match(text, label)
            if not match:
                continue
            window = _window_after(text, match.end())
            iso = EXPIRY_ISO_RE.search(window)
            if iso:
                value = _iso_date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
                if value:
                    return value
            full = _day_month(window)
            if full:
                return full
            named = EXPIRY_MONTH_NAME_RE.search(window)
            if named:
                value = _iso_date(int(named.group(2)), MONTH_NAMES[named.group(1).lower()], 1)
                if value:
                    return value
            month = EXPIRY_MY_RE.search(window)
            if month:
                value = _iso_date(int(month.group(2)), int(month.group(1)), 1)
                if value:
                    return value
    return ""


def _extract_onset(text: str, languages: Tuple[str, ...], today: Optional[date]) -> str:
    # An absolute date in the speech needs no reference day.
    iso = ONSET_ISO_RE.search(text)
    if iso:
        value = _iso_date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        if value:
            return value
    absolute = _day_month(text)
    if absolute:
        return absolute
    if today is None:
        # A relative phrase cannot become a date without a reference day, and a
        # guessed date would either 422 at the endpoint or be recorded as fact.
        return ""
    for language in languages:
        if any(_mentions(text, term) for term in ONSET_TODAY_TERMS.get(language, ())):
            return today.isoformat()
    for language in languages:
        if any(_mentions(text, term) for term in ONSET_YESTERDAY_TERMS.get(language, ())):
            return (today - timedelta(days=1)).isoformat()
    ago = re.search(ONSET_AGO_PATTERN, text, re.IGNORECASE)
    if ago:
        digits, word = ago.group(1), (ago.group(2) or "").casefold()
        count = int(digits) if digits else ENGLISH_NUMBERS.get(word, 0)
        if count:
            tail = text[ago.end() :].casefold()
            step = 30 if ("month" in tail or "மாத" in tail or "మాస" in tail or "মাস" in tail) else 1
            return (today - timedelta(days=count * step)).isoformat()
    return ""


def _extract_outcome(text: str, languages: Tuple[str, ...]) -> str:
    for language in languages:
        terms = OUTCOME_TERMS.get(language, {})
        for value in OUTCOME_VALUES:
            if any(_mentions(text, phrase) for phrase in terms.get(value, ())):
                return value
    return ""


def _extract_reporter_type(text: str, languages: Tuple[str, ...]) -> str:
    # A clinician reporting on a patient is the more reportable reporter, so the
    # HCP phrases are checked first.
    for value, table in (("hcp", REPORTER_HCP_TERMS), ("patient", REPORTER_PATIENT_TERMS)):
        for language in languages:
            if any(_mentions(text, phrase) for phrase in table.get(language, ())):
                return value
    return ""


def _extract_reporter_words(text: str, languages: Tuple[str, ...]) -> str:
    """The caller's own sentence linking the product to the event - verbatim.

    The module records it; it concludes nothing. With no cue in the call, the
    field stays empty rather than gaining a generated sentence.
    """
    for sentence in _sentences(text):
        for language in languages:
            if any(_mentions(sentence, cue) for cue in CAUSALITY_CUES.get(language, ())):
                return sentence
    return ""


# ─── 1. Intent routing ──────────────────────────────────────────────────────
def _routing_evidence(text: str, contact: str, language: Any) -> List[str]:
    """The phrases that decided the route, in table order (an auditable reason)."""
    if contact not in ("AE", "PQC", "MI"):
        return []
    code = str(language or "").strip().lower()
    languages = (code,) if code in PV_LANGUAGES else PV_LANGUAGES
    hits: List[str] = []
    for candidate in languages:
        phrases = CONTACT_PHRASES.get(candidate, {}).get(contact, ())
        specials = SPECIAL_SITUATION_TERMS.get(candidate, ()) if contact == "AE" else ()
        for phrase in (*phrases, *specials):
            if _contains(text, phrase) and phrase not in hits:
                hits.append(phrase)
    return hits


def detect_intent(transcript: Any, language: str = "en") -> Dict[str, Any]:
    """Route a call to an in-call intent: ae / pqc / mi / none.

    A thin wrapper over the Phase-1 classify_contact_type, so the voice route and
    the intake endpoint can never disagree about what the call is. The result
    carries the evidence (which phrases decided it) and the LLM function the
    agent would call, so a routing decision is auditable after the fact.
    """
    contact = classify_contact_type(transcript, language)
    intent = CONTACT_TO_INTENT.get(contact, "none")
    return {
        "intent": intent,
        "contact_type": contact,
        "function": INTENT_FUNCTIONS[intent],
        "language": _language(language),
        "is_pv_intent": intent != "none",
        "matched_phrases": _routing_evidence(_normalize(transcript), contact, language),
    }


# ─── 2. Structured capture ──────────────────────────────────────────────────
def extract_case_fields(
    transcript: Any,
    intent: str = "ae",
    language: str = "en",
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Capture the minimum-criteria fields for `intent` from what was said.

    Returns EXACTLY the intake schema's key set (same keys, same types as
    app/api/pv.py's PvCaseCreate), so the dict can be handed straight to
    build_case_payload. `clinic_id` / `call_id` stay blank here: identity comes
    from the call row, never from a transcript.

    `today` is the reference day for a relative onset ("yesterday", "two days
    ago"). It is a parameter, not a clock read, so the result is reproducible -
    and with no reference day a relative phrase yields no date at all.

    Fields that need judgement are left alone on purpose: `expectedness` (a
    PVOIC decision against the approved label), `product_id` (the products table
    is authoritative) and `seriousness_flags` (folded in by the builder from the
    special-situation flags, never read out of speech).
    """
    fields = _blank_fields()
    fields["language"] = _language(language)
    text = _normalize(transcript)
    if not text:
        return fields

    languages = _search_languages(language)
    fields["patient"] = {
        "age": _extract_age(text, languages),
        "sex": _extract_sex(text, languages),
        "initials": _extract_initials(text, languages),
    }
    fields["product_name"] = _extract_product_name(text, languages)
    fields["product_strength"] = _extract_strength(text)
    fields["batch_no"] = _extract_batch(text, languages)
    fields["expiry"] = _extract_expiry(text, languages)
    fields["event_onset_date"] = _extract_onset(text, languages, today)
    fields["outcome"] = _extract_outcome(text, languages)
    fields["reporter_type"] = _extract_reporter_type(text, languages)
    fields["causality_reporter"] = _extract_reporter_words(transcript, languages)

    column = INTENT_TEXT_COLUMNS.get(intent, "")
    if column:
        # The caller's own words, verbatim: the endpoint's `text` fallback reads
        # this same column first.
        fields[column] = str(transcript).strip()
    return fields


# ─── 3. In-language follow-up questions ─────────────────────────────────────
def pending_elements(intent: str, fields: Any) -> List[str]:
    """The elements this call is still missing, in the intent's own order.

    Built on the endpoint's OWN validate_minimum_criteria call, so the agent can
    never ask for something the case already has, nor skip something the case
    still lacks. An element an intent does not cover (a patient for a
    complaint) is not "pending" just because the E2B minimum lists it.
    """
    required = INTENT_REQUIRED_ELEMENTS.get(intent, ())
    if not required:
        return []
    _met, missing = intake_minimum_criteria(fields)
    needed = set(missing) | set(EXTRA_REQUIRED_ELEMENTS.get(intent, ()))
    return [element for element in required if element in needed]


def question_script(
    intent: str,
    language: str = "en",
    fields: Any = None,
    missing: Optional[List[str]] = None,
) -> List[str]:
    """The follow-up questions to ask, in the caller's language, in order.

    One question per still-missing element - pass `fields` and the list is
    derived from validate_minimum_criteria itself, or pass an explicit `missing`
    list when the caller has already validated the case. A complete case gets an
    empty script, and `none` (a non-PV call) is never questioned about a
    medicine: a booking call must not be turned into a safety interview.
    """
    required = INTENT_REQUIRED_ELEMENTS.get(intent, ())
    if not required:
        return []
    code = _language(language)
    pending = (
        [element for element in required if element in set(missing)]
        if missing is not None
        else pending_elements(intent, fields or {})
    )
    return [QUESTION_BANK[(intent, element, code)] for element in required if element in pending]


# ─── 4. Special situations ──────────────────────────────────────────────────
def special_situation_flags(
    fields: Any, transcript: Any = "", language: str = "en"
) -> List[str]:
    """The reportable special situations in this call, in canonical order.

    Pregnancy, overdose, medication error, off-label use, lack of effect and
    death (research doc §2 / §4.3) are reportable without a clinician deciding
    anything, so an in-call agent asks the extra prompt for each one. A captured
    outcome of "fatal" counts as `death` too, because that is the same fact
    spoken differently. Closed vocabulary: nothing else can be returned.
    """
    row = fields if isinstance(fields, dict) else {}
    text = _normalize(transcript) or _normalize(row.get("event_text"))
    hits = set()
    if text:
        languages = _search_languages(language)
        for flag in SPECIAL_SITUATION_FLAGS:
            for candidate in languages:
                if any(
                    _mentions(text, phrase)
                    for phrase in SPECIAL_SITUATION_PHRASES[flag].get(candidate, ())
                ):
                    hits.add(flag)
                    break
    if str(row.get("outcome", "")).strip().lower() == "fatal":
        hits.add("death")
    return [flag for flag in SPECIAL_SITUATION_FLAGS if flag in hits]


def special_situation_prompts(flags: Any, language: str = "en") -> List[str]:
    """The in-call prompt for each flagged situation, in the caller's language."""
    code = _language(language)
    out: List[str] = []
    for flag in flags or []:
        prompt = SPECIAL_SITUATION_PROMPTS.get((flag, code))
        if prompt and prompt not in out:
            out.append(prompt)
    return out


# ─── 5. The intake body ─────────────────────────────────────────────────────
def intake_minimum_criteria(payload: Any) -> Tuple[bool, List[str]]:
    """Apply the ICH E2B minimum to an intake body, exactly as the endpoint does.

    A mirror of app/api/pv.py's own call: the text is the first non-blank of the
    three verbatim columns, the reporter is the contact (falling back to the
    self-described role), and the suspect product is the name (or the dictionary
    id). Committing to the same primitive is the point - a false "complete" here
    would be a false "complete" in the stored case.
    """
    data = payload if isinstance(payload, dict) else {}
    text = ""
    for column in ("event_text", "question_text", "defect_description"):
        if str(data.get(column, "")).strip():
            text = str(data[column])
            break
    reporter = data.get("reporter_contact") or data.get("reporter_type")
    return validate_minimum_criteria(
        data.get("event_text") or text,
        reporter,
        data.get("patient"),
        data.get("product_name") or data.get("product_id"),
    )


def build_case_payload(
    intent: str,
    fields: Any,
    special_flags: Any = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble the exact POST /api/pv/cases body. PURE - no HTTP, no clock.

    Returns EXACTLY the intake schema's keys: a field the schema does not
    declare is dropped rather than posted, so a payload can never carry a
    column the endpoint would ignore. The `intent` decides which verbatim column
    carries the complaint; `metadata` (the call row) is the only source of
    identity, the language and the callback number.

    `seriousness_flags` receives the special-situation flags that are ICH E2A
    criteria (`death` only) - a pregnancy or an overdose is reportable but is
    NOT a seriousness criterion, and inflating a case's seriousness from a
    keyword would be exactly the judgement this module must not make.

    The body makes NO completeness claim: `intake_minimum_criteria` (the
    endpoint's own check) decides that, and an incomplete case is still posted
    and still stored.
    """
    row = fields if isinstance(fields, dict) else {}
    meta = metadata if isinstance(metadata, dict) else {}

    payload = _blank_fields()
    for key in CASE_FIELD_KEYS:
        if key in row:
            payload[key] = row[key]

    column = INTENT_TEXT_COLUMNS.get(intent, "")
    if not column:
        for other in ("event_text", "question_text", "defect_description"):
            payload[other] = ""
    elif not str(payload.get(column, "")).strip():
        # The intent's own column is the complaint; a dict built for a different
        # intent would otherwise leave the endpoint with nothing to classify.
        for other in ("event_text", "question_text", "defect_description"):
            if other != column and str(payload.get(other, "")).strip():
                payload[column] = payload[other]
            if other != column:
                payload[other] = ""
    else:
        for other in ("event_text", "question_text", "defect_description"):
            if other != column:
                payload[other] = ""

    contact = dict(payload.get("reporter_contact") or {})
    if meta.get("phone_suffix"):
        contact.setdefault("phone_suffix", str(meta["phone_suffix"]))
    if meta.get("role"):
        contact.setdefault("role", str(meta["role"]))
    payload["reporter_contact"] = contact

    payload["language"] = _language(meta.get("language") or payload.get("language"))
    payload["clinic_id"] = str(meta.get("clinic_id") or payload.get("clinic_id") or "")
    payload["call_id"] = str(meta.get("call_id") or payload.get("call_id") or "")
    if meta.get("product_id"):
        payload["product_id"] = str(meta["product_id"])
    payload["photos_url"] = list(payload.get("photos_url") or [])
    payload["seriousness_flags"] = [
        flag
        for flag in (special_flags or [])
        if flag in SERIOUSNESS_CRITERIA and flag in E2A_SPECIAL_SITUATIONS
    ]
    return payload


def is_serious_payload(payload: Any) -> Tuple[bool, List[str]]:
    """(is_serious, criteria) for a body this module built, via Phase-1 logic."""
    data = payload if isinstance(payload, dict) else {}
    return classify_seriousness(data.get("seriousness_flags"))
