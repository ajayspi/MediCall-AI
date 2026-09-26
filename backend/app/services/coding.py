"""Coding layer + WHO-UMC causality capture + the expedited export gate (2C).

spec-micc-pv-phase2.md slice 2C. MedDRA and WHODrug are LICENSED dictionaries:
the codes ship with a subscription and may not be redistributed, so nothing in
this file is one. What is here is the SEAM and the parts that need no licence —
which is the whole of the slice's value, because a licensed backend can then be
dropped in without editing a single call site:

  * `DictionaryBackend` — `lookup_pt` / `lookup_drug`, the two operations a
    safety case actually needs, plus `name` for the audit trail;
  * `FixtureDictionary` — a tiny synthetic lexicon so coding is unit-testable
    today. Every code it returns is FIX-prefixed, so licensed content cannot
    ship here by accident;
  * `register_dictionary` — the ONE swap point. Call it once at startup
    (`register_dictionary(LicensedMedDraWhodrugClient(...))`) and every case
    routed through `code_case` is coded by the licensed backend;
  * `causality_capture` — the WHO-UMC causality assessment, CAPTURED from the
    two humans who own it (the reporter and the reviewer) and validated against
    the scale. Never computed, never defaulted, never inferred from seriousness;
  * `is_expedited` / `reviewer_stamp` / `missing_review_stamp` — the
    human-in-the-loop gate: an EXPEDITED case (serious, and not expected per
    the approved label) cannot become an ICSR without a reviewer's own
    causality category, their identity and the moment they said it.

THE GATE LIVES HERE, NOT IN THE ROUTER. e2b.py asks this module whether a case
may be exported, so the rule, the missing-field list and the HTTP status the
export routes surface are one decision — a test can hold all three together, and
a second copy of the rule cannot drift from the first.

STDLIB-ONLY (datetime / typing) plus the Phase-1 service, whose seriousness
classifier is imported rather than copied: re-listing the ICH E2A criteria here
would be a second definition of "serious" free to disagree with the first. No
socket, no http, no vendor SDK — a licensed dictionary client is deployment
configuration, and the module that decides a case is exportable must be provably
offline.

This module has no clock. `causality_capture` validates the review moment the
CLIENT supplies and refuses an unreadable one, because a service that stamped
its own `reviewed_at` would let a late, back-dated review look contemporaneous —
and the review is exactly the fact the gate exists to protect.
"""

from datetime import date, datetime
from typing import Any, Dict, Optional

from app.services.pharmacovigilance import classify_seriousness

# ─── The dictionary seam ────────────────────────────────────────────────────
# A coded entry is a fixed shape, never an ad-hoc dict: an export consumer and
# a test can both rely on the keys. PT = Preferred Term, SOC = System Organ
# Class, HLT = High Level Term (the MedDRA hierarchy a case is grouped under).
PT_ENTRY_FIELDS = ("code", "pt", "soc", "hlt")
DRUG_ENTRY_FIELDS = ("code", "name")

CODING_NOT_IN_DICTIONARY = "not_in_dictionary"


class DictionaryBackend:
    """What a coding dictionary must answer. Two lookups, nothing more.

    Deliberately this small. A licensed MedDRA/WHODrug client, an in-house
    product dictionary and the fixture lexicon are all the same object from the
    caller's side, so nothing in the system needs to know which one it has.
    """

    def name(self) -> str:
        """Short identifier for the audit trail ("which dictionary coded this")."""
        raise NotImplementedError("a DictionaryBackend must name itself")

    def lookup_pt(self, term: str) -> Optional[Dict[str, str]]:
        """Preferred Term for free text, or None when the lexicon has no match.

        NEVER a near-match, a suggestion or a stem. A miss is the correct
        answer for a term the licence does not cover; inventing a code is the
        one thing a coding layer must not do.
        """
        raise NotImplementedError("lookup_pt is not implemented")

    def lookup_drug(self, term: str) -> Optional[Dict[str, str]]:
        """Suspect-product entry for free text, or None. Same no-guessing rule."""
        raise NotImplementedError("lookup_drug is not implemented")


# The fixture lexicon. Synthetic on purpose: the terms are invented, the
# hierarchy is three made-up codes, and every code carries the FIX prefix, so
# nothing in here can be mistaken for — or quietly become — licensed content.
FIXTURE_DICTIONARY_NAME = "fixture"
FIXTURE_PT_TERMS: Dict[str, Dict[str, str]] = {
    "itching": {
        "code": "FIXPT-1001",
        "pt": "Itching (fixture term)",
        "soc": "FIXSOC-1001",
        "hlt": "FIXHLT-1001",
    },
    "skin rash": {
        "code": "FIXPT-1002",
        "pt": "Skin rash (fixture term)",
        "soc": "FIXSOC-1001",
        "hlt": "FIXHLT-1001",
    },
    "dizziness": {
        "code": "FIXPT-1003",
        "pt": "Dizziness (fixture term)",
        "soc": "FIXSOC-1002",
        "hlt": "FIXHLT-1002",
    },
    "nausea": {
        "code": "FIXPT-1004",
        "pt": "Nausea (fixture term)",
        "soc": "FIXSOC-1002",
        "hlt": "FIXHLT-1002",
    },
    "breathing difficulty": {
        "code": "FIXPT-1005",
        "pt": "Breathing difficulty (fixture term)",
        "soc": "FIXSOC-1003",
        "hlt": "FIXHLT-1003",
    },
}
FIXTURE_DRUG_TERMS: Dict[str, Dict[str, str]] = {
    "fixamet": {"code": "FIXDRUG-2001", "name": "Fixamet (fixture product)"},
    "fixturecillin": {"code": "FIXDRUG-2002", "name": "Fixturecillin (fixture product)"},
    "fixazole": {"code": "FIXDRUG-2003", "name": "Fixazole (fixture product)"},
    "fixadol": {"code": "FIXDRUG-2004", "name": "Fixadol (fixture product)"},
}


def _normalise_term(value: Any) -> str:
    """Casefolded, whitespace-collapsed term. Separator-insensitive."""
    return " ".join(str(value or "").lower().replace("-", " ").replace("_", " ").split())


def _clean_str(value: Any) -> str:
    """A non-empty, whitespace-trimmed string, or "" — never None, never a cast."""
    if value is None or isinstance(value, bool):
        return ""
    text = str(value).strip()
    return text if text else ""


def _normalised_lexicon(terms: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    """Lookup key -> canonical term, built once so case/spacing cannot miss."""
    return {_normalise_term(term): term for term in terms}


_FIXTURE_PT_LOOKUP = _normalised_lexicon(FIXTURE_PT_TERMS)
_FIXTURE_DRUG_LOOKUP = _normalised_lexicon(FIXTURE_DRUG_TERMS)


class FixtureDictionary(DictionaryBackend):
    """The built-in, unlicensed lexicon. Enough to code a test case, no more."""

    def name(self) -> str:
        return FIXTURE_DICTIONARY_NAME

    def lookup_pt(self, term: str) -> Optional[Dict[str, str]]:
        key = _normalise_term(term)
        if not key:
            return None
        canonical = _FIXTURE_PT_LOOKUP.get(key)
        if canonical is None:
            return None
        return dict(FIXTURE_PT_TERMS[canonical])

    def lookup_drug(self, term: str) -> Optional[Dict[str, str]]:
        key = _normalise_term(term)
        if not key:
            return None
        canonical = _FIXTURE_DRUG_LOOKUP.get(key)
        if canonical is None:
            return None
        return dict(FIXTURE_DRUG_TERMS[canonical])


# ─── The registry: one call site installs a licensed dictionary ─────────────
_DICTIONARY: Optional[DictionaryBackend] = None


def register_dictionary(backend: Optional[DictionaryBackend]) -> DictionaryBackend:
    """Install the process-wide coding dictionary; returns it.

    `None` restores the built-in fixture, which is the documented way back to
    a known state. A non-backend raises TypeError rather than being stored: a
    typo'd import that only surfaced at the first case would be a coding outage
    discovered on the first real report.
    """
    global _DICTIONARY
    if backend is None:
        _DICTIONARY = None
        return get_dictionary()
    if not isinstance(backend, DictionaryBackend):
        raise TypeError(
            "register_dictionary needs a DictionaryBackend (or None to restore "
            f"the fixture); got {type(backend).__name__}"
        )
    _DICTIONARY = backend
    return _DICTIONARY


def get_dictionary() -> DictionaryBackend:
    """The installed dictionary, or the fixture. Same object every call."""
    if _DICTIONARY is None:
        return FixtureDictionary()
    return _DICTIONARY


# ─── Expectedness (for the expedited rule) ──────────────────────────────────
# A stored case says whether the event was expected per the approved label.
# Both spellings resolve to the same canonical value, so "Expected" from an
# agent and "expected" from a label compare equal.
EXPECTEDNESS_VALUES = ("expected", "unexpected")
EXPECTEDNESS_ALIASES = {
    "expected": "expected",
    "expected per label": "expected",
    "listed": "expected",
    "unexpected": "unexpected",
    "unlisted": "unexpected",
    "not expected": "unexpected",
    "not listed": "unexpected",
}
_EXPECTEDNESS_LOOKUP = {
    **{_normalise_term(alias): value for alias, value in EXPECTEDNESS_ALIASES.items()},
    **{value: value for value in EXPECTEDNESS_VALUES},
}


def _canonical_expectedness(raw: Any) -> str:
    """Canonical expectedness, or "" when nobody has compared it with the label.

    "" is the fail-closed answer, not a third category: the gate treats an
    unassessed serious case as expedited rather than waving it through.
    """
    return _EXPECTEDNESS_LOOKUP.get(_normalise_term(raw), "")


# ─── WHO-UMC causality scale (capture, not inference) ───────────────────────
# The WHO-UMC categories, most to least causal. This is a CAPTURE vocabulary:
# the reporter's own assessment and the reviewer's own assessment are recorded
# as they were given and validated against these values. The system never
# derives a category from seriousness, from the event text or from a drug
# dictionary — that judgement belongs to the two named humans, and a code path
# that filled the slot for them would make the causality assessment unfalsifiable.
WHO_UMC_SCALE_NAME = "WHO-UMC"
WHO_UMC_CAUSALITY_CATEGORIES = (
    "certain",
    "probable",
    "possible",
    "unlikely",
    "conditional",
    "unassessable",
    "not_related",
)
# Spellings people actually type, mapped to the canonical category. "likely" is
# on this list because it is the ordinary English synonym of "probable" — not
# because it is a second category.
WHO_UMC_ALIASES = {
    "certain": "certain",
    "definite": "certain",
    "probable": "probable",
    "likely": "probable",
    "possible": "possible",
    "possibly related": "possible",
    "unlikely": "unlikely",
    "unrelated": "not_related",
    "not related": "not_related",
    "not_related": "not_related",
    "conditional": "conditional",
    "unassessable": "unassessable",
    "not assessable": "unassessable",
}
_WHO_UMC_LOOKUP = {
    **{_normalise_term(alias): value for alias, value in WHO_UMC_ALIASES.items()},
    **{category: category for category in WHO_UMC_CAUSALITY_CATEGORIES},
}

# Why a capture was refused. A machine-readable code plus a human detail: the
# code is what the route logs, the detail is what the reviewer reads.
CAUSALITY_NO_ASSESSMENT = "no_causality_assessment"
CAUSALITY_REPORTER_NOT_ON_SCALE = "reporters_assessment_not_on_scale"
CAUSALITY_REVIEWER_NOT_ON_SCALE = "reviewer_assessment_not_on_scale"
CAUSALITY_REVIEWER_UNATTRIBUTED = "reviewer_assessment_unattributed"
CAUSALITY_REVIEWED_AT_NOT_ISO = "reviewed_at_not_iso8601"

_CAUSALITY_REFUSED: Dict[str, str] = {
    CAUSALITY_NO_ASSESSMENT: (
        "no causality assessment was supplied: pass reporters_assessment, "
        "reviewer_assessment, or both"
    ),
    CAUSALITY_REPORTER_NOT_ON_SCALE: (
        f"reporters_assessment is not a {WHO_UMC_SCALE_NAME} category; allowed: "
        + ", ".join(WHO_UMC_CAUSALITY_CATEGORIES)
    ),
    CAUSALITY_REVIEWER_NOT_ON_SCALE: (
        f"reviewer_assessment is not a {WHO_UMC_SCALE_NAME} category; allowed: "
        + ", ".join(WHO_UMC_CAUSALITY_CATEGORIES)
    ),
    CAUSALITY_REVIEWER_UNATTRIBUTED: (
        "an unattributed review is never stored: a reviewer_assessment needs "
        "both reviewer (their identity) and reviewed_at (an ISO-8601 moment)"
    ),
    CAUSALITY_REVIEWED_AT_NOT_ISO: (
        "reviewed_at must be the reviewer's own ISO-8601 moment; this service "
        "has no clock and will not substitute one"
    ),
}


def _causality_result(
    valid: bool,
    error: str = "",
    reporters_assessment: str = "",
    reviewer_assessment: str = "",
    reporters_verbatim: str = "",
    reviewed_by: str = "",
    reviewed_at: str = "",
) -> Dict[str, Any]:
    """The capture result — ONE shape, valid or refused.

    A refused capture returns every assessment field as "", so a caller cannot
    accidentally persist half of a capture it was told was invalid. The keys
    are identical either way: a shape that changes on failure is a shape a
    caller can get wrong.
    """
    return {
        "valid": bool(valid),
        "captured": bool(valid),
        "error": error,
        "detail": "" if valid else _CAUSALITY_REFUSED.get(error, ""),
        "scale": WHO_UMC_SCALE_NAME,
        "reporters_assessment": reporters_assessment if valid else "",
        "reporters_assessment_verbatim": reporters_verbatim if valid else "",
        "reviewer_assessment": reviewer_assessment if valid else "",
        "reviewed_by": reviewed_by if valid else "",
        "reviewed_at": reviewed_at if valid else "",
        # Always false, and asserted as such: no code path may fill a causality
        # slot the human did not fill. The field exists so an auditor can see
        # that the fact was never true, rather than having to infer it.
        "system_assigned": False,
    }


def _iso_moment(value: Any) -> str:
    """A readable ISO-8601 date/time, or "" — never a substitute."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return _clean_str(value)


def _readable_moment(value: str) -> bool:
    """True when the string is a date or a datetime ISO-8601 will actually parse.

    Parsing is validation, not conversion: the caller keeps the moment it sent
    (an offset, a date, a full timestamp) because a service that reformatted it
    would be recording a slightly different fact from the one it was given.
    """
    text = _clean_str(value)
    if not text:
        return False
    for parser in (datetime.fromisoformat, date.fromisoformat):
        try:
            parser(text)
        except (TypeError, ValueError):
            continue
        return True
    return False


def causality_capture(
    reporters_assessment: Any = None,
    reviewer_assessment: Any = None,
    reviewer: Any = None,
    reviewed_at: Any = None,
) -> Dict[str, Any]:
    """Capture the WHO-UMC causality assessment as the humans stated it.

    Atomic on purpose: if ANY field is invalid the whole capture is refused and
    every assessment comes back empty, so a rejected reviewer can never leave
    the reporter's half of the assessment behind as a partial record.

    An unattributed review is a REFUSAL, not a default. `reviewer_assessment`
    without a `reviewer` and a `reviewed_at` is a category with no accountable
    author and no moment, and storing it would let a causality assessment exist
    on a case that no identified human ever signed.
    """
    reporter_raw = _clean_str(reporters_assessment)
    reviewer_raw = _clean_str(reviewer_assessment)
    reviewer_by = _clean_str(reviewer)
    reviewed_moment = _iso_moment(reviewed_at)

    if not reporter_raw and not reviewer_raw:
        return _causality_result(False, CAUSALITY_NO_ASSESSMENT)

    canonical_reporter = ""
    if reporter_raw:
        canonical_reporter = _WHO_UMC_LOOKUP.get(_normalise_term(reporter_raw), "")
        if not canonical_reporter:
            return _causality_result(False, CAUSALITY_REPORTER_NOT_ON_SCALE)

    canonical_reviewer = ""
    if reviewer_raw:
        canonical_reviewer = _WHO_UMC_LOOKUP.get(_normalise_term(reviewer_raw), "")
        if not canonical_reviewer:
            return _causality_result(False, CAUSALITY_REVIEWER_NOT_ON_SCALE)
        if not reviewer_by or not reviewed_moment:
            return _causality_result(False, CAUSALITY_REVIEWER_UNATTRIBUTED)
        if not _readable_moment(reviewed_moment):
            return _causality_result(False, CAUSALITY_REVIEWED_AT_NOT_ISO)

    return _causality_result(
        True,
        reporters_assessment=canonical_reporter,
        reviewer_assessment=canonical_reviewer,
        reporters_verbatim=reporter_raw,
        reviewed_by=reviewer_by if reviewer_raw else "",
        reviewed_at=reviewed_moment if reviewer_raw else "",
    )


# ─── Coding a case ──────────────────────────────────────────────────────────
def _entry(dictionary: DictionaryBackend, lookup: str, term: str) -> Optional[Dict[str, str]]:
    """A complete, non-empty entry from the backend, or None.

    Fail-closed: a backend that answers with a partial, mistyped or empty
    entry is treated as a miss. Storing half an entry would put a code on a
    case with no hierarchy (or an empty code with a hierarchy) — the shape
    downstream consumers trust is the shape they will get.
    """
    try:
        raw = getattr(dictionary, lookup)(term)
    except Exception:  # a broken backend must not take a case down with it
        return None
    if not isinstance(raw, dict):
        return None
    required = PT_ENTRY_FIELDS if lookup == "lookup_pt" else DRUG_ENTRY_FIELDS
    entry: Dict[str, str] = {}
    for field in required:
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            return None
        entry[field] = value.strip()
    return entry


def _named(dictionary: DictionaryBackend) -> str:
    try:
        return _clean_str(dictionary.name()) or "unknown"
    except Exception:
        return "unknown"


def _lookup_terms(text: Any) -> list:
    """The whole string first, then a trailing 'X <strength> <form>' head.

    A caller reports the product they were dispensed, not the INN, so
    "fixamet 500 mg" is one free-text field and a dictionary has to cope. The
    WHO-DDMP product-name search order is: the whole string, then the name
    without a strength/dosage qualifier. Two probes, no stemming and no
    truncated 2-3 character prefixes, so nothing can be matched by accident.
    """
    whole = _clean_str(text)
    if not whole:
        return []
    head = _normalise_term(whole).split(" ")
    trimmed = head[0] if len(head) > 1 else ""
    return [whole] if not trimmed else [whole, trimmed]


def _dictionary_lookup(
    dictionary: DictionaryBackend, lookup: str, text: Any
) -> Optional[Dict[str, str]]:
    """First complete entry the backend answers for any accepted spelling."""
    for term in _lookup_terms(text):
        entry = _entry(dictionary, lookup, term)
        if entry is not None:
            return entry
    return None


def code_case(case_fields: Any, dictionary: Optional[DictionaryBackend] = None) -> Dict[str, Any]:
    """Map one case's event term and suspect product through a dictionary.

    Pure: the row is never mutated, the same row always gives the same result,
    and nothing is inferred. A hit is reported (`coded` / `drug_coded`) with the
    entry that was found; a miss carries NO code at all — `reason` explains the
    refusal, and the caller stores nothing. No code, anywhere: when the event
    term misses, the product is not reported either, because a half-coded case
    is exactly the record that invites someone downstream to read a code that
    was never actually looked up. Once the event is coded the product is looked
    up in its own right, and a product miss leaves the event code standing.

    `dictionary` is the injection point for a test or a licensed client; left
    out, the process-wide registered dictionary is used.
    """
    row = dict(case_fields or {})
    lexicon = dictionary if dictionary is not None else get_dictionary()

    event = _dictionary_lookup(lexicon, "lookup_pt", row.get("event_text"))
    if event is None:
        return {
            "coded": False,
            "reason": CODING_NOT_IN_DICTIONARY,
            "dictionary": _named(lexicon),
            "event": None,
            "drug": None,
            "drug_coded": False,
        }

    drug = _dictionary_lookup(lexicon, "lookup_drug", row.get("product_name"))
    return {
        "coded": True,
        "reason": "",
        "dictionary": _named(lexicon),
        "event": event,
        "drug": drug,
        "drug_coded": drug is not None,
    }


# ─── The expedited export gate (the rule, in one place) ─────────────────────
# EXPEDITED = serious, AND not expected per the approved label. That is the
# India 15-calendar-day expedited-submission case: exactly the cases a
# regulator expects to have been through a human review first. A non-serious
# case, or a serious case expected per the label, needs no stamp.
#
# FAIL-CLOSED on expectedness: a serious case whose expectedness is blank or
# unrecognised has not been compared with the label, so it is treated as
# expedited and gated. "Nobody checked" is not "expected".
REVIEWER_STAMP_FIELDS = ("reviewer_causality", "reviewed_by", "reviewed_at")
# 409 Conflict: the case is valid and exportable-in-principle, but its current
# state does not allow this — the same class the complaint state machine uses.
REVIEW_GATE_STATUS = 409
REVIEW_GATE_DETAIL = (
    "expedited case (serious and not expected per the label) requires a "
    "reviewer stamp before export"
)


def is_expedited(case: Any) -> bool:
    """True when this case needs a human review before it can be an ICSR.

    Seriousness comes from the Phase-1 ICH E2A classifier, imported not copied,
    so this rule cannot drift from the one intake used to tick the flags.
    """
    row = dict(case or {})
    serious, _criteria = classify_seriousness(row.get("seriousness_flags"))
    if not serious:
        return False
    return _canonical_expectedness(row.get("expectedness")) != "expected"


def _stamped_category(raw: Any) -> str:
    """The stored reviewer category, but only if it is genuinely on the scale.

    An off-scale value is not a stamp: it means the column was hand-edited or
    written by something other than `causality_capture`, and the gate must not
    be unlockable with free text.
    """
    text = _clean_str(raw)
    if not text:
        return ""
    return _WHO_UMC_LOOKUP.get(_normalise_term(text), "")


def reviewer_stamp(case: Any) -> Dict[str, Any]:
    """The case's reviewer stamp, and what is missing from it.

    A complete stamp is the reviewer's own causality category on the WHO-UMC
    scale, their identity, and the moment they said it — all three or nothing.
    The stored category is canonicalised in the output so a caller sees the
    value that was actually accepted.
    """
    row = dict(case or {})
    expedited = is_expedited(row)
    stamp = {
        "expedited": expedited,
        "stamped": False,
        "missing": [],
        "reviewer_causality": "",
        "reviewed_by": "",
        "reviewed_at": "",
    }
    if not expedited:
        stamp["stamped"] = True
        return stamp

    category = _stamped_category(row.get("reviewer_causality"))
    identity = _clean_str(row.get("reviewed_by"))
    moment = _iso_moment(row.get("reviewed_at"))
    present = {
        "reviewer_causality": category,
        "reviewed_by": identity,
        "reviewed_at": moment,
    }
    missing = [field for field in REVIEWER_STAMP_FIELDS if not present[field]]
    stamp.update(present)
    stamp["missing"] = missing
    stamp["stamped"] = not missing
    return stamp


def missing_review_stamp(case: Any) -> list:
    """The stamp fields still missing, in canonical order.

    This is what the export routes surface, so it is a list of FIELD NAMES and
    never a statement that a field holds a value it does not hold. Empty for a
    case that needs no stamp, which is how a non-expedited export stays
    unstamped rather than being blocked by a rule that does not apply to it.
    """
    return list(reviewer_stamp(case)["missing"])
