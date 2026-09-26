"""Pharmacovigilance / MICC intake logic (spec-micc-pv-module.md Phase 1).

A STDLIB-ONLY leaf (csv / datetime / html / io / json / math) so every rule is
headless-testable with no database, no network and no gateway keys - the house
pattern of app/services/guardrails.py and app/services/telephony.py. The
/api/pv router stays thin and imports this module; nothing here imports FastAPI,
SQLAlchemy or a provider SDK.

The four service functions the spec names:
- classify_contact_type       - AE / PQC / MI / OTHER from a caller's words in
  5 Indian languages (phrase tables, not ML). Special situations (overdose,
  wrong medicine, product not working, a change the caller noticed) always
  route to AE, and a safety signal outranks a defect mention (EU GMP Ch. 8.7:
  complaints that indicate a suspected adverse reaction go to PV).
- validate_minimum_criteria   - the ICH E2B minimum (reporter, patient,
  product, event). An incomplete case is STORED with e2b_minimum_met=false,
  never dropped - a follow-up call can complete it.
- classify_seriousness        - FLAG-DRIVEN only, across the six ICH E2A
  criteria. The call centre records what the caller reported; it never infers
  seriousness from free text, because that judgement belongs to the
  pharmacovigilance officer.
- compute_reporting_deadline  - the India clock (Pharmacovigilance Programme
  of India, MoHFW): 15 calendar days serious, 90 non-serious, counted from
  the day the report reaches the company. Calendar days, no weekend/holiday
  skipping. An unknown jurisdiction falls back to India rather than zeroing
  the clock.

Also here, because they are the same pure-logic family: the quality-complaint
state machine, the E2B-minimum export bundle (JSON + flat CSV), the print view
and the product-CSV seed parser.

THE CALL CENTRE IS A COLLECTOR, NOT A CLINICIAN. Nothing in this module
reasons about causes, and the print view carries PRINT_BANNER so a printed
case can never be read as an assessment.
"""

import csv
import html
import io
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ─── Catalogs ───────────────────────────────────────────────────────────────

# The four intake buckets. OTHER is the honest default: a call that is not a
# safety signal, a defect or a medicine question is simply not a PV case.
CONTACT_TYPES = ("AE", "PQC", "MI", "OTHER")

# The 5 languages the call centre runs (same tuple as services/languages.py).
PV_LANGUAGES = ("hi", "en", "ta", "te", "bn")

# ─── Contact classification tables (per language) ────────────────────────────
# Phrase tables, not inference: a call-centre agent needs an auditable reason
# for every routing decision, in the caller's own script. AE is matched FIRST
# so a safety signal wins over a defect mention in the same sentence.
CONTACT_PHRASES: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "hi": {
        "AE": (
            "बुखार",
            "उल्टी",
            "दर्द",
            "एलर्जी",
            "खुजली",
            "चकत्ते",
            "सांस नहीं",
            "साँस नहीं",
            "जी मना",
            "बेहोशी",
            "दौरा",
            "रक्तस्राव",
            "side effect",
        ),
        "PQC": (
            "पैकेट टूटा",
            "पैकेट फटा",
            "टूटा हुआ",
            "रंग बदल",
            "पिघला",
            "गीला",
            "खाली है",
            "क्षतिग्रस्त",
            "खराब दवा",
        ),
        "MI": (
            "कितनी बार",
            "कब लेनी",
            "दूध के साथ",
            "कितनी गोली",
            "मात्रा बताइए",
            "सेवन कैसे",
        ),
    },
    "en": {
        "AE": (
            "rash",
            "side effect",
            "vomit",
            "vomiting",
            "fever",
            "swelling",
            "allergic",
            "seizure",
            "bleeding",
            "dizzy",
            "cannot breathe",
            "chest pain",
        ),
        "PQC": (
            "broken",
            "cracked",
            "leaking",
            "leaked",
            "loose",
            "torn",
            "damaged",
            "discoloured",
            "discolored",
            "expired",
            "seal is",
        ),
        "MI": (
            "how often",
            "how many",
            "how to take",
            "with milk",
            "can i take",
            "what is the dose",
            "safe to take",
        ),
    },
    "ta": {
        "AE": (
            "வலி",
            "வாந்தி",
            "காய்ச்சல்",
            "வற்றல்",
            "சொறி",
            "கண்புழி",
            "மூச்சு",
            "அறிவிழப்பு",
            "side effect",
        ),
        "PQC": (
            "உடைந்து",
            "பாக்கெட்",
            "ஊறல்",
            "நிறம் மாறி",
            "வெறுமையாக",
            "சேதம்",
        ),
        "MI": (
            "எவ்வளவு",
            "எப்போது",
            "மருந்து எடுக்க",
            "மாதிரி எடுக்க",
            "எப்படி உண்க",
        ),
    },
    "te": {
        "AE": (
            "జ్వరం",
            "వాంతి",
            "నోపు",
            "వదురు",
            "చిగుర్లు",
            "ఊపిరి",
            "మర్మాక్షం",
            "రక్తస్రావం",
            "side effect",
        ),
        "PQC": (
            "పగిలి",
            "ప్యాకెట్",
            "లీక్",
            "రంగు మారి",
            "ఖాళీగా",
            "దెబ్బతిన్న",
        ),
        "MI": (
            "ఎంత",
            "ఎప్పుడు",
            "మోతాదు",
            "ఎలా తీసుకోవాలి",
        ),
    },
    "bn": {
        "AE": (
            "জ্বর",
            "বমি",
            "ব্যথা",
            "অ্যালার্জি",
            "চুলকানি",
            "শ্বাসকষ্ট",
            "অচেতন",
            "খিঁচুনি",
            "রক্তপাত",
            "side effect",
        ),
        "PQC": (
            "ছিঁড়ে",
            "প্যাকেট",
            "ভেঙে",
            "রং বদলে",
            "খালি",
            "ক্ষতিগ্রস্ত",
        ),
        "MI": (
            "কতটুকু",
            "কতবার",
            "কখন খাব",
            "কীভাবে খাব",
            "মাত্রা",
        ),
    },
}

# ICH E2A "special situations" / listed situations: an overdose, a wrong
# medicine, a product reported as not working, or a change the caller noticed.
# These are reportable without a clinician deciding anything, so they always
# route to AE in every script.
SPECIAL_SITUATION_TERMS: Dict[str, Tuple[str, ...]] = {
    "hi": (
        "गलत दवा",
        "ज्यादा दवा",
        "काम नहीं कर रही",
        "काम नहीं कर रहा",
        "माहिली चले गई",
    ),
    "en": (
        "too many",
        "by mistake",
        "wrong medicine",
        "wrong tablet",
        "leftover",
        "not working",
        "stopped working",
        "no longer works",
        "changed my periods",
        "mixed up",
        "died",
        "passed away",
        "death",
    ),
    "ta": ("அதிக", "தவறு", "சாப்பிட்டேன்", "வேலை செய்யவில்லை", "தொழிற்படவில்லை"),
    "te": ("తప్పు", "అధికం", "పనిచేయడం లేదు", "మారలేదు"),
    "bn": ("ভুল ওষুধ", "অতিরিক্ত", "কাজ করছে না", "মিশিয়ে"),
}

# ─── ICH E2B minimum criteria ───────────────────────────────────────────────
# The four data elements without which an individual case is not reportable.
# Order is canonical: the intake endpoint reports the missing list in this order
# so the agent hears a consistent follow-up list.
MINIMUM_CRITERIA_ELEMENTS = ("reporter", "patient", "product", "event")

# Any one of these non-blank fields identifies the reporter (WHO E2B: name,
# designation or a contact detail is enough - the call centre records the
# callback, not the full identity).
_REPORTER_KEYS = (
    "reporter_type",
    "reporter_name",
    "reporter_qualification",
    "role",
    "designation",
    "phone",
    "phone_suffix",
    "email",
    "name",
)

# A patient is identifiable by age OR sex OR initials (E2B: any one of the
# three patient characteristics is enough to start a case).
_PATIENT_KEYS = ("age", "sex", "initials", "patient_initials", "patient_id")

# ─── ICH E2A seriousness ────────────────────────────────────────────────────
# The six seriousness criteria, in canonical report order. The router passes
# FLAGS (booleans the agent ticks from the caller's own words); this module
# never reads free text to decide seriousness.
SERIOUSNESS_CRITERIA = (
    "death",
    "life_threatening",
    "hospitalisation",
    "disability",
    "congenital_anomaly",
    "medically_important",
)

# Spelling variants a field agent may type, normalised to the canonical slug.
SERIOUSNESS_ALIASES = {
    "life threatening": "life_threatening",
    "lifethreatening": "life_threatening",
    "hospitalization": "hospitalisation",
    "hospital admission": "hospitalisation",
    "admission": "hospitalisation",
    "congenital": "congenital_anomaly",
    "birth defect": "congenital_anomaly",
    "medically important": "medically_important",
    "medically significant": "medically_important",
}

# ─── Reporting clock (India) ────────────────────────────────────────────────
# Pharmacovigilance Programme of India (MoHFW): a serious case is submitted to
# the centre within 15 calendar days of receipt, a non-serious case within 90.
# An unknown jurisdiction key falls back to "india" - never to zero days.
REPORTING_CLOCK_DAYS = {
    "india": {"serious": 15, "non_serious": 90},
}
DEFAULT_JURISDICTION = "india"

# ─── Quality complaint state machine ────────────────────────────────────────
# Strictly forward-only: captured -> investigating -> disposition -> capa.
# capa is terminal. A complaint is never silently re-opened; a late finding is
# a NEW complaint, which keeps the audit trail honest.
PQC_STATUSES = ("captured", "investigating", "disposition", "capa")
PQC_TRANSITIONS = {
    "captured": ("investigating",),
    "investigating": ("disposition",),
    "disposition": ("capa",),
    "capa": (),
}

# ─── E2B(R3) export ─────────────────────────────────────────────────────────
# The nine data-element groups the PViCi / E2B-minimum interchange needs. A
# group is a fixed vocabulary, never an ad-hoc key, so an export consumer can
# rely on the shape. Nothing outside this list is exported.
E2B_CASE_GROUPS = (
    "sender_case_id",
    "primary_source",
    "reporter",
    "patient",
    "suspect_product",
    "event",
    "seriousness",
    "reporter_causality",
    "dates",
)

# The flat CSV column order - one column per E2B field, no free text columns
# beyond the verbatim event and the reporter's own words.
CSV_COLUMNS = (
    "sender_case_id",
    "case_type",
    "clinic_id",
    "call_id",
    "source_channel",
    "recording_consent",
    "status",
    "reporter_type",
    "reporter_contact",
    "reporter_qualification",
    "patient_age",
    "patient_sex",
    "patient_initials",
    "product_id",
    "product_name",
    "product_strength",
    "batch_no",
    "expiry",
    "event_text",
    "event_onset_date",
    "outcome",
    "expectedness",
    "is_serious",
    "seriousness_flags",
    "reporter_causality_verbatim",
    "day_zero",
    "date_values",
)

# Printed/stuck-on cases carry this banner. The words are deliberately chosen:
# NO_MEDICAL_ADVICE is underscore-joined so the string can never be read as
# "medical advice", and the banner states no assessment is being made.
PRINT_BANNER = (
    "SOURCE DATA ONLY - NO_MEDICAL_ADVICE: captured as spoken by the caller. "
    "Not a clinical assessment. Triage and reporting are decided by a "
    "qualified pharmacovigilance officer."
)

# Product CSV seed columns (case-insensitive header match).
PRODUCT_CSV_FIELDS = (
    "name",
    "generic_name",
    "strength",
    "dosage_form",
    "manufacturer",
)

_LIST_JOIN = "; "


# ─── Contact classification ─────────────────────────────────────────────────
def _alias_key(value: Any) -> str:
    """Separator-insensitive lookup key: case/underscore/hyphen/spacing folded."""
    return " ".join(
        str(value or "").strip().lower().replace("-", " ").replace("_", " ").split()
    )


# Built once: every alias and every canonical slug, keyed by _alias_key, so
# classify_seriousness never has to guess a separator spelling.
_SERIOUSNESS_LOOKUP = {
    **{_alias_key(alias): slug for alias, slug in SERIOUSNESS_ALIASES.items()},
    **{_alias_key(slug): slug for slug in SERIOUSNESS_CRITERIA},
}


def _normalize_text(value: Any) -> str:
    """Casefolded, whitespace-collapsed text (None -> empty string)."""
    if value is None:
        return ""
    return " ".join(str(value).lower().split())


def _phrase_hits(text: str, phrases: Iterable[str]) -> Tuple[str, ...]:
    return tuple(p for p in phrases if p and p in text)


def classify_contact_type(text: Any, language: str = "en") -> str:
    """Classify a caller's words as AE / PQC / MI / OTHER.

    Phrase-table matching in the caller's language, case-insensitive. An
    unrecognised language code searches EVERY language's table rather than
    guessing - a mislabelled call must not be dropped from safety triage.

    Precedence: AE (including special situations) > PQC > MI > OTHER. A caller
    describing both a leaking bottle and a child's rash is an AE.
    """
    normalized = _normalize_text(text)
    if not normalized:
        return "OTHER"

    lang = str(language or "").lower()
    languages = PV_LANGUAGES if lang not in PV_LANGUAGES else (lang,)

    for candidate in languages:
        phrases = CONTACT_PHRASES.get(candidate, {})
        specials = SPECIAL_SITUATION_TERMS.get(candidate, ())
        if _phrase_hits(normalized, phrases.get("AE", ()) + specials):
            return "AE"
    for candidate in languages:
        if _phrase_hits(normalized, CONTACT_PHRASES.get(candidate, {}).get("PQC", ())):
            return "PQC"
    for candidate in languages:
        if _phrase_hits(normalized, CONTACT_PHRASES.get(candidate, {}).get("MI", ())):
            return "MI"
    return "OTHER"


# ─── ICH E2B minimum criteria ───────────────────────────────────────────────
def _identifiable(payload: Any, keys: Sequence[str]) -> bool:
    """True when payload carries at least one non-blank identifying field."""
    if payload is None:
        return False
    if isinstance(payload, dict):
        return any(_normalize_text(payload.get(key)) for key in keys)
    if isinstance(payload, (list, tuple, set)):
        return any(_normalize_text(item) for item in payload)
    return bool(_normalize_text(payload))


def validate_minimum_criteria(
    event_text: Any,
    reporter: Any,
    patient: Any,
    product: Any,
) -> Tuple[bool, List[str]]:
    """Check the ICH E2B minimum. Returns (met, missing_elements).

    `missing_elements` follows MINIMUM_CRITERIA_ELEMENTS order so the agent
    hears the same follow-up list every time. A False result is NOT a
    rejection: the row is stored with e2b_minimum_met=false and chased.
    """
    missing: List[str] = []
    if not _identifiable(reporter, _REPORTER_KEYS):
        missing.append("reporter")
    if not _identifiable(patient, _PATIENT_KEYS):
        missing.append("patient")
    if not _identifiable(product, ("name", "product_name", "brand", "generic_name")):
        missing.append("product")
    if not _normalize_text(event_text):
        missing.append("event")
    return (not missing), missing


# ─── ICH E2A seriousness ────────────────────────────────────────────────────
def _canonical_criterion(raw: Any) -> Optional[str]:
    """Normalise one raw flag to a canonical criterion slug, or None.

    Separators are irrelevant: "life-threatening", "life threatening" and
    "life_threatening" all resolve to life_threatening. Anything not in the
    lookup is dropped, so a free-text note can never invent a criterion.
    """
    return _SERIOUSNESS_LOOKUP.get(_alias_key(raw))


def classify_seriousness(flags: Any) -> Tuple[bool, List[str]]:
    """Flag-driven ICH E2A seriousness. Returns (is_serious, criteria).

    Accepts a dict of {criterion: truthy}, or a list/tuple/set of criterion
    names (spelling variants normalised). Anything unrecognised is ignored, so
    a stray note can never inflate a case to "serious". The returned criteria
    are in canonical SERIOUSNESS_CRITERIA order, de-duplicated.
    """
    hits = set()
    if isinstance(flags, dict):
        for name, value in flags.items():
            if value:
                canonical = _canonical_criterion(name)
                if canonical:
                    hits.add(canonical)
    elif isinstance(flags, (list, tuple, set, frozenset)):
        for name in flags:
            canonical = _canonical_criterion(name)
            if canonical:
                hits.add(canonical)
    elif flags is not None and not isinstance(flags, str):
        canonical = _canonical_criterion(flags)
        if canonical:
            hits.add(canonical)
    criteria = [c for c in SERIOUSNESS_CRITERIA if c in hits]
    return (bool(criteria), criteria)


# ─── Reporting clock (India 15/90 calendar days) ────────────────────────────
def _as_aware(value: Optional[datetime]) -> Optional[datetime]:
    """Naive datetimes are treated as UTC; an aware value keeps its offset."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def compute_reporting_deadline(
    is_serious: Any,
    received_at: datetime,
    jurisdiction: str = DEFAULT_JURISDICTION,
    now: Optional[datetime] = None,
) -> Tuple[datetime, int]:
    """Return (submission_deadline, days_remaining) for a received case.

    Day zero is received_at. Calendar days only - a Friday receipt with a
    15-day clock is due the following Saturday, and no holiday calendar is
    consulted (the Indian programme counts calendar days).

    days_remaining is 0 on the deadline day, negative once overdue, and
    defaults to the full window when `now` is omitted. An unknown jurisdiction
    falls back to the India clock so the deadline can never be zeroed.
    """
    received = _as_aware(received_at)
    if received is None:
        raise ValueError("received_at is required")

    key = str(jurisdiction or "").strip().lower()
    clock = REPORTING_CLOCK_DAYS.get(key)
    if not clock:
        clock = REPORTING_CLOCK_DAYS[DEFAULT_JURISDICTION]
    days = int(clock["serious"] if is_serious else clock["non_serious"])

    deadline = received + timedelta(days=days)
    reference = _as_aware(now) or received
    remaining = math.ceil((deadline - reference).total_seconds() / 86400.0)
    return deadline, remaining


# ─── Quality complaint state machine ────────────────────────────────────────
def is_legal_complaint_transition(current: str, target: str) -> bool:
    """True only for a forward step declared in PQC_TRANSITIONS.

    A self-transition, an unknown state, a skip (captured -> capa) and every
    backward step are illegal - the endpoint answers 409, never 500.
    """
    if not current or not target:
        return False
    if current not in PQC_TRANSITIONS or target not in PQC_STATUSES:
        return False
    if current == target:
        return False
    return target in PQC_TRANSITIONS[current]


def next_pqc_status(current: str, target: str) -> Optional[str]:
    """The new complaint status, or None when the transition is illegal."""
    return target if is_legal_complaint_transition(current, target) else None


# ─── E2B export bundle ──────────────────────────────────────────────────────
def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _flags_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        return [k for k, v in value.items() if v]
    try:
        return [v for v in value if v]
    except TypeError:
        return []


def _date_values(case: Dict[str, Any]) -> List[str]:
    values = []
    for key in ("received_at", "event_onset_date", "notification_deadline", "notified_at"):
        raw = case.get(key)
        if raw is None or raw == "":
            continue
        if isinstance(raw, datetime):
            values.append(raw.isoformat())
        else:
            values.append(_text(raw))
    return values


def build_e2b_case(case: Any) -> Dict[str, Any]:
    """Build the E2B(R3) minimum bundle from a stored PV case row.

    Exactly the nine E2B_CASE_GROUPS, each a fixed data-element group. The
    reporter's causal words are carried VERBATIM under reporter_causality -
    this module records them, it never produces them. Tolerates a bare
    minimum case dict (missing keys become empty), because a case can be
    captured before it is complete.
    """
    row: Dict[str, Any] = dict(case or {})
    is_serious, criteria = classify_seriousness(row.get("seriousness_flags"))

    return {
        "sender_case_id": _text(row.get("id")),
        "primary_source": {
            "case_type": _text(row.get("case_type")),
            "clinic_id": _text(row.get("clinic_id")),
            "call_id": _text(row.get("call_id")),
            "source_channel": _text(row.get("source_channel")),
            "recording_consent": _text(row.get("recording_consent")),
            "status": _text(row.get("status")),
        },
        "reporter": {
            "reporter_type": _text(row.get("reporter_type")),
            "reporter_contact": row.get("reporter_contact") or {},
            "reporter_qualification": _text(row.get("reporter_qualification")),
        },
        "patient": {
            "patient_age": _text(row.get("patient_age")),
            "patient_sex": _text(row.get("patient_sex")),
            "patient_initials": _text(row.get("patient_initials")),
        },
        "suspect_product": {
            "product_id": _text(row.get("product_id")),
            "product_name": _text(row.get("product_name")),
            "product_strength": _text(row.get("product_strength")),
            "batch_no": _text(row.get("batch_no")),
            "expiry": _text(row.get("expiry")),
        },
        "event": {
            "event_text": _text(row.get("event_text")),
            "event_onset_date": _text(row.get("event_onset_date")),
            "outcome": _text(row.get("outcome")),
            "expectedness": _text(row.get("expectedness")),
        },
        "seriousness": {
            "is_serious": is_serious,
            "seriousness_flags": criteria,
        },
        "reporter_causality": {
            "verbatim": _text(row.get("causality_reporter")),
            "reporter_assessment": _text(row.get("expectedness")),
        },
        "dates": {
            "day_zero": _text(row.get("received_at")),
            "values": _date_values(row),
        },
    }


def _flat_value(value: Any) -> str:
    """One CSV cell from a bundle value: lists join, bools become yes/no."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple, set)):
        return _LIST_JOIN.join(_text(v) for v in value if v is not None and v != "")
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return _text(value)


def flatten_case(bundle: Dict[str, Any]) -> Dict[str, str]:
    """Flatten an E2B bundle to the CSV_COLUMNS shape (all values strings)."""
    group = bundle if isinstance(bundle, dict) else {}
    source = group.get("primary_source") or {}
    reporter = group.get("reporter") or {}
    patient = group.get("patient") or {}
    product = group.get("suspect_product") or {}
    event = group.get("event") or {}
    serious = group.get("seriousness") or {}
    causality = group.get("reporter_causality") or {}
    dates = group.get("dates") or {}

    return {
        "sender_case_id": _flat_value(group.get("sender_case_id")),
        "case_type": _flat_value(source.get("case_type")),
        "clinic_id": _flat_value(source.get("clinic_id")),
        "call_id": _flat_value(source.get("call_id")),
        "source_channel": _flat_value(source.get("source_channel")),
        "recording_consent": _flat_value(source.get("recording_consent")),
        "status": _flat_value(source.get("status")),
        "reporter_type": _flat_value(reporter.get("reporter_type")),
        "reporter_contact": _flat_value(reporter.get("reporter_contact")),
        "reporter_qualification": _flat_value(reporter.get("reporter_qualification")),
        "patient_age": _flat_value(patient.get("patient_age")),
        "patient_sex": _flat_value(patient.get("patient_sex")),
        "patient_initials": _flat_value(patient.get("patient_initials")),
        "product_id": _flat_value(product.get("product_id")),
        "product_name": _flat_value(product.get("product_name")),
        "product_strength": _flat_value(product.get("product_strength")),
        "batch_no": _flat_value(product.get("batch_no")),
        "expiry": _flat_value(product.get("expiry")),
        "event_text": _flat_value(event.get("event_text")),
        "event_onset_date": _flat_value(event.get("event_onset_date")),
        "outcome": _flat_value(event.get("outcome")),
        "expectedness": _flat_value(event.get("expectedness")),
        "is_serious": _flat_value(serious.get("is_serious")),
        "seriousness_flags": _flat_value(serious.get("seriousness_flags")),
        "reporter_causality_verbatim": _flat_value(causality.get("verbatim")),
        "day_zero": _flat_value(dates.get("day_zero")),
        "date_values": _flat_value(dates.get("values")),
    }


def export_csv_text(bundles: Any) -> str:
    """Render E2B bundles as CSV text (header + one row per case).

    An empty list still yields the header, so a consumer can always read the
    column set. Every cell is exactly the flattened value, so the CSV always
    mirrors the JSON bundle field for field.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(list(CSV_COLUMNS))
    for bundle in bundles or []:
        flat = flatten_case(bundle)
        writer.writerow([flat.get(column, "") for column in CSV_COLUMNS])
    return buffer.getvalue()


# ─── Print view ─────────────────────────────────────────────────────────────
_PRINT_CSS = (
    "body{font-family:sans-serif;margin:24px;color:#1b1b1b}"
    ".banner{border:2px solid #8a1c1c;padding:10px;font-weight:bold}"
    "h1{font-size:18px}"
    "table{border-collapse:collapse;width:100%}"
    "th,td{border:1px solid #ccc;padding:6px;text-align:left;"
    "vertical-align:top;font-size:13px}"
    "th{width:34%;background:#f4f4f4}"
)


def _print_row(label: str, value: Any) -> str:
    return (
        "<tr><th>" + html.escape(label) + "</th><td>"
        + html.escape(_text(value) or "-") + "</td></tr>"
    )


def render_case_html(case: Any) -> str:
    """Self-contained printable case sheet - captured facts only.

    Inline CSS, no script, no external asset, every value HTML-escaped. The
    sheet deliberately carries no assessment: no cause, no diagnosis, no
    advice, and the group label for the reporter's own words never uses the
    word "causality". PRINT_BANNER is printed at the top of every sheet.
    """
    row: Dict[str, Any] = dict(case or {})
    serious, criteria = classify_seriousness(row.get("seriousness_flags"))
    product = row.get("product_name") or ""
    strength = row.get("product_strength") or ""
    title = ("Adverse event case" if row.get("case_type") == "AE" else "PV case")
    if product:
        title += " - " + product

    rows = [
        _print_row("Case id", row.get("id")),
        _print_row("Case type", row.get("case_type")),
        _print_row("Status", row.get("status")),
        _print_row("Received at (day zero)", row.get("received_at")),
        _print_row("Submission deadline", row.get("notification_deadline")),
        _print_row("Notified at", row.get("notified_at")),
        _print_row("Source channel", row.get("source_channel")),
        _print_row("Recording consent", row.get("recording_consent")),
        _print_row("Clinic", row.get("clinic_id")),
        _print_row("Call", row.get("call_id")),
        _print_row("Reporter type", row.get("reporter_type")),
        _print_row(
            "Reporter contact", json.dumps(row.get("reporter_contact") or {}, sort_keys=True)
        ),
        _print_row("Patient age", row.get("patient_age")),
        _print_row("Patient sex", row.get("patient_sex")),
        _print_row("Patient initials", row.get("patient_initials")),
        _print_row("Suspect product", product),
        _print_row("Strength", strength),
        _print_row("Batch number", row.get("batch_no")),
        _print_row("Expiry", row.get("expiry")),
        _print_row("Event as reported", row.get("event_text")),
        _print_row("Event onset date", row.get("event_onset_date")),
        _print_row("Outcome", row.get("outcome")),
        _print_row("Expectedness", row.get("expectedness")),
        _print_row("Serious", "yes" if serious else "no"),
        _print_row("Seriousness criteria", _LIST_JOIN.join(criteria)),
        _print_row("Reporter own words", row.get("causality_reporter")),
        _print_row("E2B minimum met", "yes" if row.get("e2b_minimum_met") else "no"),
    ]

    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        "<title>" + html.escape(title) + "</title>\n"
        "<style>" + _PRINT_CSS + "</style>\n"
        "</head>\n"
        "<body>\n"
        '<p class="banner">' + html.escape(PRINT_BANNER) + "</p>\n"
        "<h1>" + html.escape(title) + "</h1>\n"
        "<table>\n" + "\n".join(rows) + "\n</table>\n"
        "</body>\n"
        "</html>\n"
    )


# ─── Product CSV seed ───────────────────────────────────────────────────────
def parse_product_csv(text: Any) -> Tuple[List[Dict[str, str]], List[str]]:
    """Parse a product-dictionary CSV into (rows, errors).

    Blank lines are skipped. A row with no product name is reported as an
    error (line number + the missing field) and is NOT imported - a nameless
    product cannot be referenced by a case. An empty or header-only CSV is
    simply no rows and no errors.
    """
    if not text or not str(text).strip():
        return [], []

    reader = csv.reader(io.StringIO(str(text)))
    records = [row for row in reader if any((cell or "").strip() for cell in row)]
    if not records:
        return [], []

    header = [(cell or "").strip().lower() for cell in records[0]]
    rows: List[Dict[str, str]] = []
    errors: List[str] = []
    for offset, record in enumerate(records[1:], start=2):
        values = {
            header[i]: (record[i].strip() if i < len(record) else "")
            for i in range(len(header))
            if header[i] and header[i] != ""
        }
        if not values.get("name", ""):
            errors.append(f"line {offset}: name is required")
            continue
        rows.append({key: values.get(key, "") for key in PRODUCT_CSV_FIELDS})
    return rows, errors
