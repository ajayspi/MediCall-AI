"""E2B(R3) XML generation + the gateway adapter seam (phase-2 slice 2A).

spec-micc-pv-phase2.md slice 2A: Phase 1 built the E2B-minimum export BUNDLE
(nine fixed data-element groups in app/services/pharmacovigilance.py). This
module turns that bundle into E2B(R3)-shaped XML, and declares the seam a real
regulator gateway would plug into.

THE CONTRACT IS THE PHASE-1 BUNDLE, NOT A VENDOR DRAFT. The phase-2 spec names
the drift risk (a generated file the gateway rejects) and the mitigation:
generate from the key-group contract, not from a fixed vendor sample. So the
element names here ARE the exporter's keys — `sender_case_id`, `primary_source`,
`patient.patient_age`, `seriousness.seriousness_flags`, … — and every key group
the exporter produces is emitted, in a deterministic order, with the ICH E2B(R3)
data-element number attached as a `number` attribute. Nothing else is invented:
the only non-contract elements are the declared ENVELOPE_ELEMENTS (the ICH
message header + the sender identity block), and a test asserts the emitted
element set equals the contract plus exactly those.

E2B_NUMBERS is the ONE place the numbering is reconciled. The section letters
follow the slice brief (C.1 sender, C.2 primary source/reporter, C.5 patient,
D suspect product, E event + seriousness) and the leaf numbers are the
E2B(R3) elements the data actually belongs to; where no published element
exists (an intake-provenance field such as the call id) the entry carries the
section letter only, deliberately, rather than a fabricated precision. PvPI's
published E2B-XML example is the acceptance fixture for the final numbering pass
and touches this one table — not the generator.

NOTHING IN HERE SENDS ANYTHING. The gateway is a seam, not a client: this
module imports no socket, http, urllib, requests or ssl, and the only adapter
that exists is a stub that returns a canned acknowledgement. A real adapter
(the PvPI/NCC-PvPI E2B-XML endpoint, its TLS client, the MAH credentials, the
transmission schedule) is DEPLOYMENT CONFIGURATION for a validated environment
(GVP Module I QMS) and is out of scope for the slice — and out of scope for the
system: a PVOIC signs off and sends. Slice 2A generates; it never submits.

A STDLIB-ONLY leaf (json / hashlib / xml.etree.ElementTree / dataclasses /
typing) like app/services/pharmacovigilance.py, so every rule here is
headless-testable with no database, no network and no keys. It imports exactly
two siblings — the Phase-1 exporter whose group list is the contract, imported
rather than copied so a group added there surfaces HERE as a failing test
instead of as a silently missing element; and slice 2C's coding service, which
owns the human-in-the-loop rule (app/services/coding.py). Both imports exist so
the export gate is ONE decision: a second copy of "an expedited case needs a
reviewer stamp" would be free to drift from the one the PVOIC's screen enforces.
"""

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Dict, Tuple

from app.services.coding import (
    REVIEW_GATE_DETAIL,
    REVIEW_GATE_STATUS,
    missing_review_stamp,
)
from app.services.pharmacovigilance import E2B_CASE_GROUPS, validate_minimum_criteria

# ─── The envelope (every non-contract element, declared) ────────────────────
# An ICH E2B(R3) message is a message header (N.1) around one or more safety
# reports (N.2.r). The header plus the sender identity block are the ENVELOPE:
# transport/identity facts, not case data. The sender values are placeholders —
# the real sender organisation, its PvPI sender identifier and the receiver
# identifier come from deployment configuration, and the transmission date is
# stamped by the PVOIC at sign-off, so it is EMPTY by default (which is also
# what keeps generation byte-for-byte deterministic).
E2B_XML_ROOT = "ichicsrMessage"
E2B_MESSAGE_TYPE = "ichicsr"
E2B_SENDER_IDENTIFIER = "MEDICALL-AI-PVOIC"
E2B_RECEIVER_IDENTIFIER = "NCC-PVPI"
E2B_SENDER_TYPE = "1"  # C.1.4: 1 = manufacturer / marketing-authorisation holder
E2B_SENDER_ORGANIZATION = "MediCall-AI Pharmacovigilance"
E2B_SENDER_COUNTRY = "IN"  # ISO 3166-1 alpha-2, India (NCC-PvPI)
XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>'

# Declared, so the "no invented fields" test can hold the generator to it: every
# element the XML contains is either a contract key, one of these, or a
# repeated-item tag from LIST_ITEM_TAGS.
ENVELOPE_ELEMENTS = (
    E2B_XML_ROOT,
    "ichicsrMessageHeader",
    "messageType",
    "messageSenderIdentifier",
    "messageReceiverIdentifier",
    "messageDateOfTransmission",
    "messageNumber",
    "safetyReport",
    "sender",
    "sendertype",
    "senderorganization",
    "sendercountry",
)

# A list leaf becomes ONE container element (named by the contract key) holding
# repeated items of the tag below, in the order the exporter produced them
# (seriousness criteria are already canonical-ordered; dates are in the
# fixed received/onset/deadline/notified order).
LIST_ITEM_TAGS = {
    "seriousness_flags": "seriousness_flag",
    "values": "value",
}
DEFAULT_ITEM_TAG = "item"

# ─── ICH E2B(R3) data-element numbers, one table ────────────────────────────
# Keyed by the contract path. Section letters follow the slice brief; a section
# letter on its own means "this field is provenance we record, not an element
# E2B(R3) defines", which is stated rather than papered over with a fake number.
E2B_NUMBERS: Dict[str, str] = {
    "sender_case_id": "C.1.8.1",
    "primary_source": "C.2",
    "primary_source.case_type": "N.2.r.4",
    "primary_source.clinic_id": "C.2.r.3",
    "primary_source.call_id": "C.2",
    "primary_source.source_channel": "C.2",
    "primary_source.recording_consent": "C.2",
    "primary_source.status": "C.2",
    "reporter": "C.2.r",
    "reporter.reporter_type": "C.2.r.2",
    "reporter.reporter_contact": "C.2.r.1",
    "reporter.reporter_qualification": "C.2.r.2",
    "patient": "C.5",
    "patient.patient_age": "D.2",
    "patient.patient_sex": "D.3",
    "patient.patient_initials": "D.1",
    "suspect_product": "D",
    "suspect_product.product_id": "D.9.3",
    "suspect_product.product_name": "D.9.1",
    "suspect_product.product_strength": "D.9.1",
    "suspect_product.batch_no": "D.9.4",
    "suspect_product.expiry": "D.9.5",
    "event": "E",
    "event.event_text": "E.i.1",
    "event.event_onset_date": "E.i.3.1",
    "event.outcome": "E.i.7",
    "event.expectedness": "E",
    "seriousness": "E.i.3",
    "seriousness.is_serious": "E.i.3.2",
    "seriousness.seriousness_flags": "E.i.3.2",
    "reporter_causality": "C.2.r",
    "reporter_causality.verbatim": "C.2",
    "reporter_causality.reporter_assessment": "C.2",
    "dates": "C.1.8",
    "dates.day_zero": "C.1.8",
    "dates.values": "C.1.8",
}

# ─── The export gate (why a case may or may not become XML) ─────────────────
# An incomplete case is STORED, never dropped (Phase 1) and an ICSR is never
# generated from one: the four E2B minimum elements must be there. The gate is
# a pure function so the reason is testable without a database, and so the
# router's status codes are a lookup rather than a judgement.
E2B_EXPORTABLE: Tuple[int, str] = (0, "")
CASE_NOT_FOUND_DETAIL = "case not found"
E2B_MINIMUM_DETAIL = "e2b_minimum_met is false"

# ─── Stub gateway vocabulary ────────────────────────────────────────────────
STUB_CHANNEL = "stub"
STUB_STATUS = 202
STUB_RECEIPT_ID = "STUB-RECEIPT-0001"
STUB_MESSAGE = "prepared by stub adapter; no network call, nothing was submitted"

# XML 1.0 forbids most C0 control characters outright; a verbatim caller phrase
# that happens to contain one must not be able to produce a document that will
# not parse (the gateway would reject the whole batch, not just that field).
_ILLEGAL_XML_CODES = list(range(0x00, 0x09)) + [0x0B, 0x0C] + list(range(0x0E, 0x20))
_ILLEGAL_XML_CHARS = frozenset(chr(code) for code in _ILLEGAL_XML_CODES)


# ─── Value helpers ──────────────────────────────────────────────────────────
def _ordered(value: Any) -> list:
    """A repeatable leaf in a deterministic order (sets sorted, else as given)."""
    if isinstance(value, (set, frozenset)):
        return sorted(str(item) for item in value)
    return list(value)


def _clean(value: Any) -> str:
    """Text for an XML node: no illegal control characters, nothing collapsed."""
    if value is None:
        return ""
    return "".join(char for char in str(value) if char not in _ILLEGAL_XML_CHARS)


def _scalar(value: Any) -> str:
    """One scalar leaf as text. Booleans are lower-case, as XML expects."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return _clean(value)


def _json_text(value: Any) -> str:
    """A free-form dict as deterministic JSON text.

    reporter_contact is caller-supplied and free-form, so its keys can be any
    text at all. Turning a caller's key into an ELEMENT NAME would be inventing
    structure from unvalidated input (an illegal XML name would break
    well-formedness for the whole message), so the group travels as one
    deterministic JSON payload with sorted keys.
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _number(path: str) -> str:
    return E2B_NUMBERS.get(path, "")


def _node(parent, name: str, text: str, number: str = ""):
    """One element: contract key name, optional E2B number, optional text."""
    element = ET.SubElement(parent, name, {"number": number} if number else {})
    if text:
        element.text = text
    return element


def _append(parent, name: str, value: Any, number: str = ""):
    """One contract key -> one element (a container when the value is a list)."""
    if isinstance(value, dict):
        return _node(parent, name, _json_text(value), number)
    if isinstance(value, (list, tuple, set, frozenset)):
        node = _node(parent, name, "", number)
        item_tag = LIST_ITEM_TAGS.get(name, DEFAULT_ITEM_TAG)
        for item in _ordered(value):
            _append(node, item_tag, item)
        return node
    return _node(parent, name, _scalar(value), number)


# ─── The generator ──────────────────────────────────────────────────────────
def e2b_xml_from_case(
    export_bundle: Dict[str, Any],
    sender_case_id: str = "",
    transmitted_at: str = "",
) -> str:
    """Render a Phase-1 E2B bundle as E2B(R3)-shaped XML text.

    `sender_case_id` is the sender's own case identifier (the row id); a blank
    argument falls back to the bundle's, and either way the SAME value is echoed
    in the C.1.8.1 element and the message number, so a gateway receipt can be
    tied back to a case.

    `transmitted_at` is deliberately empty by default: the PVOIC stamps the real
    transmission time at sign-off, and a generated-but-unsigned artifact must
    not claim to have been sent. Leaving it unset is also what makes the output
    byte-for-byte deterministic.

    Determinism: the group order is E2B_CASE_GROUPS (imported from Phase 1, not
    the caller's dict order), the leaf order inside a group is sorted, set-valued
    leaves are sorted, and JSON sub-payloads are dumped with sort_keys. The same
    bundle therefore always yields the same bytes, whatever order the exporter
    happened to build its dicts in.
    """
    bundle: Dict[str, Any] = dict(export_bundle or {})
    case_id = _clean(sender_case_id) or _scalar(bundle.get("sender_case_id"))

    root = ET.Element(E2B_XML_ROOT)
    header = _node(root, "ichicsrMessageHeader", "", "N.1.r")
    _node(header, "messageType", E2B_MESSAGE_TYPE, "N.1.1")
    _node(header, "messageSenderIdentifier", E2B_SENDER_IDENTIFIER, "N.1.2")
    _node(header, "messageReceiverIdentifier", E2B_RECEIVER_IDENTIFIER, "N.1.3")
    _node(header, "messageDateOfTransmission", _clean(transmitted_at), "N.1.4")
    _node(header, "messageNumber", case_id, "N.2.r.2")

    report = _node(root, "safetyReport", "", "N.2.r")
    sender = _node(report, "sender", "", "C.1.r")
    _node(sender, "sendertype", E2B_SENDER_TYPE, "C.1.4")
    _node(sender, "senderorganization", E2B_SENDER_ORGANIZATION, "C.1.6.1")
    _node(sender, "sendercountry", E2B_SENDER_COUNTRY, "C.1.7")
    _node(report, "sender_case_id", case_id, _number("sender_case_id"))

    for group in E2B_CASE_GROUPS:
        if group == "sender_case_id":
            continue
        value = bundle.get(group)
        number = _number(group)
        if isinstance(value, dict):
            node = _node(report, group, "", number)
            for key in sorted(value):
                _append(node, key, value[key], _number(f"{group}.{key}"))
        elif isinstance(value, (list, tuple, set, frozenset)):
            _append(report, group, value, number)
        else:
            _node(report, group, _scalar(value), number)

    return XML_DECLARATION + "\n" + ET.tostring(root, encoding="unicode") + "\n"


def format_view(xml: Any) -> str:
    """Indented form of the same document, for the print/audit path.

    Whitespace only — the element set, the `number` attributes and every text
    value are preserved, so a pretty-printed artifact and the generated one are
    the same message. Accepts the str, bytes or bytearray the route produces.
    Input is parsed as UTF-8 bytes, which is what a stored artifact would be.
    """
    if isinstance(xml, (bytes, bytearray)):
        data = bytes(xml)
    else:
        data = str(xml or "").encode("utf-8")
    if not data.strip():
        return ""
    root = ET.fromstring(data)
    ET.indent(root, space="  ")
    return XML_DECLARATION + "\n" + ET.tostring(root, encoding="unicode") + "\n"


# ─── The export gate ────────────────────────────────────────────────────────
def e2b_export_block(case: Any) -> Tuple[int, str]:
    """Why a stored case may not become an ICSR yet, as (http_status, detail).

    E2B_EXPORTABLE (0, "") means it may. A case with no id was never stored —
    (404, "case not found"). A case stored with e2b_minimum_met=false is
    (422, ...) naming the elements still missing, recomputed with the Phase-1
    validator so the PVOIC sees the same list intake reported, in the same
    canonical order. The day-zero clock is unaffected: a serious case is already
    running, and chasing the missing elements is the fastest way to stop it.

    An EXPEDITED case (serious, and not expected per the label) is
    (REVIEW_GATE_STATUS, ...) naming the reviewer-stamp fields still missing —
    slice 2C's human-in-the-loop gate, whose rule, field list and status live in
    app/services/coding.py and are asked for here rather than restated. That
    check comes after the minimum, never before it: an incomplete case is not an
    ICSR at all, whatever its stamp says. A non-expedited case exports
    unstamped — blocking one would train the desk to stamp cases reflexively.
    """
    row = dict(case or {})
    if not _clean(row.get("id")):
        return 404, CASE_NOT_FOUND_DETAIL
    if row.get("e2b_minimum_met"):
        unstamped = missing_review_stamp(row)
        if unstamped:
            detail = f"{REVIEW_GATE_DETAIL}; missing: {', '.join(unstamped)}"
            return REVIEW_GATE_STATUS, detail
        return E2B_EXPORTABLE

    _met, missing = validate_minimum_criteria(
        row.get("event_text"),
        row.get("reporter_contact") or row.get("reporter_type"),
        {
            "age": row.get("patient_age"),
            "sex": row.get("patient_sex"),
            "initials": row.get("patient_initials"),
        },
        row.get("product_name") or row.get("product_id"),
    )
    detail = E2B_MINIMUM_DETAIL + (f"; missing: {', '.join(missing)}" if missing else "")
    return 422, detail


# ─── Gateway seam ───────────────────────────────────────────────────────────
@dataclass(frozen=True)
class GatewayReply:
    """A gateway's answer: an HTTP-shaped status plus the acknowledgement body.

    Deliberately a value, not a response object: an adapter must not hand the
    caller a live client/connection, and a PVOIC reading the receipt must be
    able to see the whole acknowledgement in the audit trail.
    """

    status: int
    payload: bytes
    receipt_id: str = ""
    accepted: bool = True
    channel: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "receipt_id": self.receipt_id,
            "accepted": self.accepted,
            "channel": self.channel,
            "payload_bytes": len(self.payload),
        }


class GatewayAdapter:
    """The seam a regulator gateway plugs into: channel() + submit(payload).

    The base class is an INTERFACE and refuses to do anything, so a caller
    cannot accidentally believe a message was delivered by using the abstract
    type. No method here opens a connection; the network client, the PvPI
    endpoint and the MAH credentials belong to a deployment-specific
    implementation, which is out of scope for this slice.
    """

    def channel(self) -> str:
        """Short name of the channel this adapter speaks (e.g. "stub")."""
        raise NotImplementedError("a gateway adapter must name its channel")

    def submit(self, payload: bytes) -> GatewayReply:
        """Hand a generated artifact to the gateway. No default implementation."""
        raise NotImplementedError(
            "slice 2A does not submit: sign off and send from a validated environment"
        )


class StubGatewayAdapter(GatewayAdapter):
    """Offline adapter: returns a canned receipt, never touches the network.

    This is the placeholder for the NCC-PvPI E2B-XML endpoint. The real
    endpoint URL, the MAH/PvPI credentials, the TLS client and the
    acknowledgement parsing are deployment configuration for a validated
    environment (GVP Module I QMS) — deliberately not code in this repository,
    and deliberately not this module: nothing in slice 2A opens a socket.

    The receipt names the payload by LENGTH and SHA-256 only, so an audit trail
    can prove which artifact was prepared without copying patient text into a
    second store.
    """

    def __init__(
        self,
        status: int = STUB_STATUS,
        receipt_id: str = STUB_RECEIPT_ID,
        message: str = STUB_MESSAGE,
    ):
        self.status = status
        self.receipt_id = receipt_id
        self.message = message

    def channel(self) -> str:
        return STUB_CHANNEL

    def submit(self, payload: bytes) -> GatewayReply:
        body = bytes(payload or b"")
        receipt = {
            "accepted": True,
            "channel": self.channel(),
            "message": self.message,
            "payload_bytes": len(body),
            "payload_sha256": sha256(body).hexdigest(),
            "receipt_id": self.receipt_id,
            "status": self.status,
        }
        return GatewayReply(
            status=self.status,
            payload=json.dumps(receipt, sort_keys=True).encode("utf-8"),
            receipt_id=self.receipt_id,
            accepted=True,
            channel=self.channel(),
        )
