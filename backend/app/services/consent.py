"""G6-Q2 consent module — per-call recording consent (Q1=A1).

The board commits to "Call Recording ... with DPDP consent flag per-call"
(spec-multifit-healthcare.md); this module is the consent layer the LiveKit
egress gate reads:

* `RECORDING_CONSENT_STATES` — the 3-state flag carried on
  `calls.recording_consent` (unknown / granted / denied; default unknown).
* `parse_consent_response(text, language)` — in-call capture: the agent asks
  "may we record this call for quality & training?" and maps a caller's spoken
  yes/no in any of the 5 languages to granted/denied (None when unclear — the
  agent re-asks). "yes"/"no" work in every language (callers code-switch).
* `recording_allowed(consent)` — the egress gate: only "granted" recordings
  may proceed (denied/unknown -> no recording).

The flag lives on `calls` (no new table, Q1=A1); withdrawal = a later
re-POST "denied" on the same call via `POST /api/calls/{id}/consent` (and a
`consent_withdrawal` compliance_events row is the audited trail follow-on).

Stdlib-only leaf: imports the Q4 languages catalog (`SUPPORTED_LANGUAGES`) and
nothing else — safe to import anywhere.
"""
from typing import Optional

from app.services.languages import SUPPORTED_LANGUAGES

# 3-state per-call flag (default 'unknown' — no explicit answer yet).
RECORDING_CONSENT_STATES = ("unknown", "granted", "denied")

# Affirmative / negative words per language. English words are included in
# EVERY language's list because callers code-switch ("yes"/"no" is caught
# even when the operative language is hi/ta/te/bn). Match is exact-after-
# punctuation-strip (no substring matching: "haan bahut" is NOT "haan").
CONSENT_YES = {
    "hi": ("haan", "yes"),
    "en": ("yes",),
    "ta": ("aamam", "yes"),
    "te": ("avunu", "yes"),
    "bn": ("ha", "yes"),
}
CONSENT_NO = {
    "hi": ("nahin", "no"),
    "en": ("no",),
    "ta": ("illai", "no"),
    "te": ("kadu", "no"),
    "bn": ("na", "no"),
}


def parse_consent_response(text, language: str) -> Optional[str]:
    """Map a caller's spoken answer to granted/denied (or None if unclear).

    Case/whitespace/punctuation-insensitive; exact word match only. Unknown
    language codes get no word lists -> None (the agent re-asks in English).
    """
    if not isinstance(text, str):
        return None
    normalized = text.strip().strip("!.,? ").lower()
    if not normalized:
        return None
    if normalized in CONSENT_YES.get(language, ()):
        return "granted"
    if normalized in CONSENT_NO.get(language, ()):
        return "denied"
    return None


def recording_allowed(consent) -> bool:
    """Egress gate (Q1=A1): only an explicit "granted" permits recording."""
    return consent == "granted"