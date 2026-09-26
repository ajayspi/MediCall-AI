"""MI approved-content knowledge base (spec-micc-pv-phase2.md slice 2D) - PURE.

A STDLIB-ONLY leaf, the same shape as app/services/pharmacovigilance.py,
app/services/e2b.py and app/services/pv_dashboard.py: it takes rows that have
ALREADY been fetched and answers a medical information inquiry from them, so
every answer is unit-testable with no database, no FastAPI and no network. The
/api/pv router fetches through the repository helpers and passes the rows in;
nothing here knows about HTTP, SQLAlchemy or sessions.

THE ONE RULE, AND IT IS NOT NEGOTIABLE. Research doc 8.01: a medical
information desk answers factual product questions from APPROVED CONTENT (the
label / PI / PIL and the company's own standard responses) and never gives
personal medical advice. So an answer here has exactly three possible sources:

  1. approved_content  - a versioned response in the product_responses
                         knowledge base, returned VERBATIM with its version.
  2. label             - the section of the product's own approved label
                         (products.approved_label_json) for this category,
                         returned verbatim. It is approved content too, just
                         held on the product row rather than the KB.
  3. no_medical_advice - a knowledge-base gap. The answer is one fixed refusal
                         phrase, so a gap can never be improvised round: the
                         system says nothing rather than something plausible.

A caller asking about their own treatment ("can I take two of these?", "is it
safe in pregnancy?") is not answered by any of the three; those stay in
category `other` / `pregnancy` with no approved section and fall to the refusal,
which is exactly the PIPA / ABPI MI-desk position: route to Medical Affairs,
never advise.

REGULATORY NET, NOT A SECOND INTAKE. When the question carries adverse-event or
product-quality content (Phase-1 classify_contact_type says AE / PQC), the
answer ALSO sets suggest_report_to_pv and names what it saw, and the refusal
carries the reportable hint. This module only FLAGS: the ABPI one-business-day
clock is owned by the intake path (POST /api/pv/cases), and a second writer
would be a second, competing source of truth for the same case. The flag is the
hand-off.

VERSION SEMANTICS. Only the highest is_active version per (product, language,
category) is answerable. Pushing a new version supersedes the old one by
deactivating it, never by deleting it: MI answers are read back in audits and in
quality review, so a withdrawn response has to remain visible. next_version() is
the only place a version number is minted.

DETERMINISM: no clock, no randomness, no mutation of the input rows, and every
candidate is ordered on a stable key - the same rows always produce the same
answer, which is what makes a stored answer defensible later.
"""

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.services.pharmacovigilance import classify_contact_type

# ─── Catalogs ───────────────────────────────────────────────────────────────

# The three things an answer can be. A new source of "information" is a change
# to this tuple and to answer_medical_inquiry, not a new branch in a caller.
ANSWER_SOURCES = ("approved_content", "label", "no_medical_advice")

# How a KB hit was matched, for the audit trail: the caller's own language, a
# language the product is approved in, or the English fallback.
LANGUAGE_MATCHES = ("exact", "product_available", "fallback")

# Canonical order the "other language this product is approved in" step walks.
# English first because it IS the fallback, so a product with both English and
# Tamil approved resolves to the fallback rather than by insertion order.
KB_LANGUAGE_ORDER = ("en", "hi", "ta", "te", "bn")

# Inquiry category -> the keys an approved label may use for that section. The
# first key present with non-blank text wins, so a label JSON written in either
# spelling answers; the value is returned verbatim and never rewritten.
# `other` has no label section by design: "other" is what a question nobody can
# map to a section is filed under, and it must not pick up an arbitrary one.
LABEL_SECTIONS: Dict[str, Tuple[str, ...]] = {
    "dosing": ("dosage", "dosing", "posology", "dose"),
    "indication": ("indication", "indications", "therapeutic_indication"),
    "side_effect": (
        "adverse_reactions",
        "adverse_reaction",
        "side_effects",
        "side_effect",
    ),
    "interactions": ("interactions", "drug_interactions", "interaction"),
    "storage": ("storage", "storage_conditions", "shelf_life"),
    "pregnancy": ("pregnancy", "pregnancy_lactation", "use_in_pregnancy"),
    "other": (),
}

# The refusal. ONE constant, asserted by the tests, so the phrase a caller can
# ever receive cannot drift into free text (and so a reader can grep for it).
# NO_MEDICAL_ADVICE is underscore-joined so the string can never be misread as
# medical advice - the same convention as the Phase-1 print banner.
NO_MEDICAL_ADVICE_PHRASE = (
    "NO_MEDICAL_ADVICE: this question cannot be answered from the approved "
    "content for this product. A qualified Medical Affairs officer will follow "
    "up with the enquirer."
)

# Appended to the refusal when the question also carried something reportable.
# The decision to open a case is the PVOIC's, not this module's.
REPORTABLE_HINT = (
    " Reportable content detected in the enquirer's own words: pass this to the "
    "pharmacovigilance officer, who decides whether a case is opened."
)


# ─── Row / value helpers (ORM row or dict, no SQLAlchemy import) ────────────
def _get(row: Any, key: str, default: Any = None) -> Any:
    """Read a field from a dict OR an ORM row, without importing SQLAlchemy."""
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _key(value: Any) -> str:
    """Comparison key: casefolded, separator-folded, whitespace-collapsed."""
    return " ".join(
        _text(value).lower().replace("-", " ").replace("_", " ").split()
    )


def _version(value: Any) -> int:
    """A row's version as an int; an unreadable version sorts lowest."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _is_active(row: Any) -> bool:
    """Only an explicitly active row is approved content (fail closed)."""
    return _get(row, "is_active") is True or _get(row, "is_active") == "true"


def _same_id(left: Any, right: Any) -> bool:
    """Product ids compare as strings; a missing id matches nothing."""
    if left in (None, "") or right in (None, ""):
        return False
    return _text(left) == _text(right)


# ─── Version semantics ─────────────────────────────────────────────────────
def next_version(existing_versions: Sequence[Any]) -> int:
    """The version number a new response must carry: max(existing) + 1.

    Pure and gap-tolerant. A first response is version 1; a non-numeric entry
    (a malformed row, a string in a fixture) is ignored rather than allowed to
    lower or break the sequence, because the UNIQUE constraint on
    (product, language, category, version) would turn a wrong number into a
    failed insert at the worst possible moment - while a clinician is waiting.
    """
    highest = 0
    for value in existing_versions or ():
        version = _version(value)
        if version > highest:
            highest = version
    return highest + 1


# ─── Knowledge-base lookup ──────────────────────────────────────────────────
def _answerable(responses: Iterable[Any], product_id: Any, category: str) -> List[Any]:
    """Active, non-blank rows for this (product, category), newest version first.

    Deactivated rows are excluded here rather than in the caller, so NO path
    can reach a withdrawn response: the check sits between the rows and the
    answer. A blank body is not approved content either - an empty response row
    is a work in progress, not a withdrawal of the medicine's approved wording.
    """
    matches = [
        row
        for row in (responses or ())
        if _same_id(_get(row, "product_id"), product_id)
        and _key(_get(row, "category")) == _key(category)
        and _is_active(row)
        and _text(_get(row, "response_body")).strip()
    ]
    # Total order (version desc, then id) so the pick never depends on the order
    # the database happened to return rows in.
    return sorted(
        matches,
        key=lambda row: (-_version(_get(row, "version")), _text(_get(row, "id"))),
    )


def _language_candidates(
    requested: str, available: Sequence[str], fallback_language: str
) -> List[Tuple[str, str]]:
    """[(language, match_kind)] in resolution order, de-duplicated.

    The chain is: the caller's own language, then any other language this
    product is approved in (canonical order), then English. Preferred content
    beats a fallback, and a fallback beats a refusal - but only content that was
    actually approved for THIS product.
    """
    wanted = _key(requested) or _key(fallback_language)
    fallback = _key(fallback_language)
    available_steps = [
        (lang, "fallback" if lang == fallback else "product_available")
        for lang in KB_LANGUAGE_ORDER
        if lang in available
    ]
    order: List[Tuple[str, str]] = []
    seen = set()
    for language, kind in (
        (wanted, "exact"),
        *available_steps,
        (fallback, "fallback"),
    ):
        if language and language not in seen:
            seen.add(language)
            order.append((language, kind))
    return order


def _empty_hit() -> Dict[str, Any]:
    return {
        "found": False,
        "response_body": "",
        "version": None,
        "source": "none",
        "language": "",
        "language_match": "",
        "response_id": "",
    }


def lookup_approved_response(
    responses: List[dict],
    product_id: Any,
    category: Any,
    language: Any,
    fallback_language: str = "en",
) -> Dict[str, Any]:
    """The approved response for (product, category) in the best available language.

    Returns found=False - never a guess - when this product has no active
    response for the category in any language. `version` is the KB version that
    answered, so the caller can record exactly which approved wording was used
    on the day of the call; that is the number an MI quality audit reads back.
    """
    wanted_category = _key(category) or "other"
    candidates = _answerable(responses, product_id, wanted_category)
    if not candidates:
        return _empty_hit()

    available = {_key(_get(row, "language")) for row in candidates} - {""}
    for code, kind in _language_candidates(
        language, sorted(available), fallback_language
    ):
        in_language = [
            row for row in candidates if _key(_get(row, "language")) == code
        ]
        if not in_language:
            continue
        row = in_language[0]  # already ordered: highest active version first
        return {
            "found": True,
            "response_body": _text(_get(row, "response_body")),
            "version": _version(_get(row, "version")),
            "source": "approved_content",
            "language": _text(_get(row, "language")),
            "language_match": kind,
            "response_id": _text(_get(row, "id")),
        }
    return _empty_hit()


# ─── Label fallback ─────────────────────────────────────────────────────────
def label_section(label: Optional[dict], category: Any) -> Tuple[str, str]:
    """(label key, text) for an inquiry category, or ("", "") when absent.

    The label is a per-product artefact, so the caller must know WHICH product's
    label it is (answer_medical_inquiry enforces that) and the text is returned
    verbatim: the label is already approved wording, and paraphrasing it is the
    failure mode this module exists to prevent.
    """
    if not isinstance(label, dict):
        return "", ""
    for key in LABEL_SECTIONS.get(_key(category), ()):
        if key in label:
            text = _text(label.get(key)).strip()
            if text:
                return key, text
    return "", ""


# ─── Reportable content on an information question ──────────────────────────
def reportable_reasons(text: Any, language: Any = "en") -> List[str]:
    """Reportable signals in the enquirer's own words, in canonical order.

    Reuses the Phase-1 classifier rather than owning a second phrase table: a
    question that reads as an adverse event or a defect must reach the PV net
    through the same words the intake path would have routed. Empty list means
    "nothing reportable seen" - which is a statement about THIS text, not a
    clearance of the caller.
    """
    if not _text(text).strip():
        return []
    contact = classify_contact_type(text, _key(language) or "en")
    return [contact] if contact in ("AE", "PQC") else []


# ─── The answer ─────────────────────────────────────────────────────────────
def answer_medical_inquiry(
    inquiry_fields: dict,
    approved_responses: List[dict],
    product_label: Optional[dict] = None,
) -> Dict[str, Any]:
    """Answer one medical information inquiry from approved content only.

    `inquiry_fields` is the medical_inquiries row (dict or ORM): product_id,
    category, language, question_text. `approved_responses` is the product's
    product_responses rows; `product_label` is the product's
    approved_label_json. The return is the answer plus everything an audit needs
    to reconstruct it: which source, which version, in which language, and
    whether the enquirer's words also carried something reportable.
    """
    product_id = _get(inquiry_fields, "product_id")
    category = _key(_get(inquiry_fields, "category")) or "other"
    language = _key(_get(inquiry_fields, "language")) or "en"
    question = _text(_get(inquiry_fields, "question_text"))
    reasons = reportable_reasons(question, language)

    hit = lookup_approved_response(approved_responses, product_id, category, language)
    if hit["found"]:
        return {
            "answer": hit["response_body"],
            "source": "approved_content",
            "version": hit["version"],
            "reasoning": (
                f"answered verbatim from the approved knowledge base: "
                f"product={_text(product_id)} category={category} "
                f"language={hit['language']} (match={hit['language_match']}) "
                f"version={hit['version']}"
            ),
            "suggest_report_to_pv": bool(reasons),
            "report_reasons": reasons,
            "category": category,
            "language": language,
            "response_id": hit["response_id"],
            "label_field": "",
        }

    # The label may only speak for a product the inquiry actually names: a label
    # with nothing to attribute it to is not approved content for this question.
    label_key, label_text = (
        label_section(product_label, category) if product_id else ("", "")
    )
    if label_text:
        return {
            "answer": label_text,
            "source": "label",
            "version": None,
            "reasoning": (
                f"no approved response in the knowledge base; answered verbatim "
                f"from the product's approved label section "
                f"'approved_label_json.{label_key}' for category={category}"
            ),
            "suggest_report_to_pv": bool(reasons),
            "report_reasons": reasons,
            "category": category,
            "language": language,
            "response_id": "",
            "label_field": label_key,
        }

    answer = NO_MEDICAL_ADVICE_PHRASE + (REPORTABLE_HINT if reasons else "")
    return {
        "answer": answer,
        "source": "no_medical_advice",
        "version": None,
        "reasoning": (
            f"no approved response and no approved label section for "
            f"category={category} on product={_text(product_id) or 'none'}; "
            f"refused rather than improvised, Medical Affairs follow-up required"
            + (f"; reportable content seen: {','.join(reasons)}" if reasons else "")
        ),
        "suggest_report_to_pv": bool(reasons),
        "report_reasons": reasons,
        "category": category,
        "language": language,
        "response_id": "",
        "label_field": "",
    }
