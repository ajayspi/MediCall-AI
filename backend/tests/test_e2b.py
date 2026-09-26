"""E2B(R3) XML generator + gateway adapter (spec-micc-pv-phase2.md slice 2A) — RED contracts.

Stdlib-only, no live Postgres, no gateway credentials, NO NETWORK: the new
service module (app/services/e2b.py) is imported and BEHAVIOUR-tested (the XML
it generates from a Phase-1 export bundle, the pretty form, the adapter
interface and the stub gateway), while the /api/pv route contracts are
structural AST + text assertions — the house pattern of test_pv_module.py,
because FastAPI is not installed in the test environment (the router is
verified by shape, never by an HTTP round-trip).

The contract under test is Phase 1's export bundle (build_e2b_case /
E2B_CASE_GROUPS): every JSON key group must appear in the XML, and nothing
else may — that is the "generate from the key-group contract, not from a fixed
vendor draft" mitigation the phase-2 spec asks for.

RED before implementation (2026-09-26): no app/services/e2b.py, no
/cases/{case_id}/e2b.xml route, no /cases/{case_id}/e2b stub route.

Run: py -3.14 -m unittest discover -s tests -p "test_e2b.py"   (from backend/)
"""
import ast
import json
import socket
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

SERVICES = BACKEND / "app" / "services"
E2B_SVC = SERVICES / "e2b.py"
PV_SVC = SERVICES / "pharmacovigilance.py"
PV_ROUTER = BACKEND / "app" / "api" / "pv.py"

# Import roots e2b.py may use: the standard library (xml/base64/json/hashlib/
# dataclasses/typing) plus exactly one sibling service, the Phase-1 PV module
# whose export bundle IS the contract being mirrored.
STDLIB_ROOTS = {
    "base64",
    "dataclasses",
    "datetime",
    "hashlib",
    "json",
    "sys",
    "typing",
    "xml",
}
ALLOWED_APP_IMPORTS = {"app.services.pharmacovigilance"}

# Nothing in this slice may open a socket: no live submission (phase-2
# non-goal — the PVOIC sends, from a validated environment, with MAH creds).
NETWORK_ROOTS = {
    "asyncio",
    "ftplib",
    "http",
    "httpx",
    "httplib",
    "requests",
    "smtplib",
    "socket",
    "ssl",
    "telnetlib",
    "urllib",
    "urllib3",
    "webbrowser",
    "xmlrpc",
}

from app.services import pharmacovigilance as pv  # noqa: E402

try:
    from app.services import e2b as e2b_mod  # noqa: E402

    HAVE_E2B = True
except ImportError:  # pragma: no cover - RED state
    e2b_mod = None
    HAVE_E2B = False


# ─── Fixtures + AST helpers ─────────────────────────────────────────────────
def sample_case() -> dict:
    """One complete AE case row, shaped exactly like api/pv.py's _case_row."""
    return {
        "id": "11111111-1111-4111-8111-111111111111",
        "case_type": "AE",
        "clinic_id": "22222222-2222-4222-8222-222222222222",
        "call_id": "33333333-3333-4333-8333-333333333333",
        "product_id": "44444444-4444-4444-8444-444444444444",
        "product_name": "Metformin 500mg",
        "product_strength": "500mg",
        "batch_no": "B-2409",
        "expiry": "2027-09",
        "reporter_type": "4",
        "reporter_contact": {"phone": "+919800000000", "name": "आरती"},
        "reporter_qualification": "consumer",
        "patient_age": "34",
        "patient_sex": "female",
        "patient_initials": "AK",
        "event_text": "गैस्ट्रिक जलन और खुजली",
        "event_onset_date": "2026-09-20",
        "outcome": "recovering",
        "expectedness": "unexpected",
        "seriousness_flags": ["hospitalisation", "medically_important"],
        "causality_reporter": "मुझे लगता है दवा से हुआ",
        "e2b_minimum_met": True,
        "status": "new",
        "received_at": "2026-09-22T04:15:00+00:00",
        "notification_deadline": "2026-10-07T04:15:00+00:00",
        "notified_at": "",
        "source_channel": "voice",
        "recording_consent": "granted",
    }


def sample_bundle() -> dict:
    """The Phase-1 export bundle — the contract the XML must mirror."""
    return pv.build_e2b_case(sample_case())


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def py_tree(path: Path):
    text = read(path)
    if not text:
        return None
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def py_tree_text(text: str):
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def fns(tree) -> dict:
    out = {}
    if tree is None:
        return out
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = node
    return out


def fn_block(text: str, name: str) -> str:
    node = fns(py_tree_text(text)).get(name)
    if node is None:
        return ""
    lines = text.splitlines(keepends=True)
    return "".join(lines[node.lineno - 1 : node.end_lineno])


def module_import_roots(text: str) -> set:
    roots = set()
    tree = py_tree_text(text)
    if tree is None:
        return roots
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def endpoints(tree) -> list:
    """[(method, path, endpoint name)] for every @router.<verb> endpoint."""
    out = []
    if tree is None:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            if (
                isinstance(deco, ast.Call)
                and isinstance(deco.func, ast.Attribute)
                and isinstance(deco.func.value, ast.Name)
                and deco.func.value.id == "router"
                and deco.args
            ):
                out.append((deco.func.attr.lower(), deco.args[0].value, node.name))
    return out


def router_prefix(tree) -> str:
    for node in ast.walk(tree or ast.Module(body=[], type_ignores=[])):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
            is_router = getattr(call.func, "id", None) == "APIRouter" or (
                isinstance(call.func, ast.Attribute) and call.func.attr == "APIRouter"
            )
            if is_router:
                for kw in call.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                        return kw.value.value
                if call.args and isinstance(call.args[0], ast.Constant):
                    return call.args[0].value
    return ""


def element_names(root) -> set:
    return {el.tag for el in root.iter()}


def contract_names(bundle: dict) -> set:
    """Every key the exporter produced (groups + their fixed leaf keys)."""
    names = set()
    for group, value in bundle.items():
        names.add(group)
        if isinstance(value, dict):
            names |= {key for key in value}
    return names


def expected_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value)


def pv_sorted(value):
    """Sets are ordered by the generator; lists/tuples keep the exporter's order."""
    if isinstance(value, (set, frozenset)):
        return sorted(str(item) for item in value)
    return list(value)


def require_e2b():
    """RED-state guard: the behaviour classes ERROR (never skip) without e2b.py."""
    if not HAVE_E2B:
        raise AssertionError("app/services/e2b.py is missing (RED state)")


# ─── A. Module shape + no-network invariant ─────────────────────────────────
class TestE2BServiceShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(E2B_SVC)
        cls.tree = py_tree(E2B_SVC)

    def test_service_module_exists(self):
        self.assertTrue(E2B_SVC.exists(), "app/services/e2b.py missing")
        self.assertIsNotNone(self.tree, "e2b.py must parse")

    def test_stdlib_only(self):
        roots = module_import_roots(self.text)
        for root in roots:
            with self.subTest(root):
                self.assertTrue(
                    root in STDLIB_ROOTS or root == "app",
                    f"e2b.py imports a non-stdlib root: {root}",
                )
        app_modules = {
            node.module
            for node in ast.walk(self.tree)
            if isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] == "app"
        }
        for module in app_modules:
            with self.subTest(module):
                self.assertIn(
                    module,
                    ALLOWED_APP_IMPORTS,
                    "e2b.py may only import the Phase-1 PV service",
                )

    def test_no_network_imports(self):
        roots = module_import_roots(self.text)
        for banned in sorted(roots & NETWORK_ROOTS):
            self.fail(f"e2b.py must not import {banned}: nothing sends in slice 2A")

    def test_uses_the_stdlib_xml_writer(self):
        self.assertIn("xml.etree.ElementTree", self.text, "stdlib XML, no lxml dep")
        self.assertNotIn("defusedxml", self.text)

    def test_public_surface(self):
        names = set(fns(self.tree))
        for name in (
            "e2b_xml_from_case",
            "format_view",
            "e2b_export_block",
            "GatewayAdapter",
            "StubGatewayAdapter",
            "GatewayReply",
        ):
            with self.subTest(name):
                self.assertIn(name, names, f"e2b.py missing {name}")


# ─── B. The export-bundle contract is mirrored 1:1 ──────────────────────────
class TestE2BContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAVE_E2B:
            require_e2b()
        cls.bundle = sample_bundle()
        cls.xml = e2b_mod.e2b_xml_from_case(cls.bundle, sample_case()["id"])
        cls.root = ET.fromstring(cls.xml)

    def test_group_list_is_the_phase1_contract(self):
        self.assertEqual(list(e2b_mod.E2B_CASE_GROUPS), list(pv.E2B_CASE_GROUPS))
        self.assertEqual(list(self.bundle.keys()), list(pv.E2B_CASE_GROUPS))

    def test_every_contract_key_is_an_element(self):
        names = element_names(self.root)
        for key in sorted(contract_names(self.bundle)):
            with self.subTest(key):
                self.assertIn(key, names, f"export key {key} missing from the XML")

    def test_element_set_is_contract_plus_declared_envelope(self):
        """Nothing invented: every non-contract element must be declared envelope."""
        declared = set(e2b_mod.ENVELOPE_ELEMENTS) | set(e2b_mod.LIST_ITEM_TAGS.values())
        self.assertFalse(
            declared & contract_names(self.bundle),
            "an envelope element name collides with a contract key",
        )
        self.assertEqual(element_names(self.root), contract_names(self.bundle) | declared)

    def test_every_contract_element_carries_an_e2b_number(self):
        report = self.root.find("safetyReport")
        for group in pv.E2B_CASE_GROUPS:
            with self.subTest(group):
                self.assertIn(group, e2b_mod.E2B_NUMBERS, f"{group} has no data element")
                self.assertTrue(e2b_mod.E2B_NUMBERS[group], f"{group} number is blank")
                node = report.find(group)
                self.assertIsNotNone(node)
                self.assertEqual(node.get("number"), e2b_mod.E2B_NUMBERS[group])

    def test_every_contract_leaf_carries_an_e2b_number(self):
        report = self.root.find("safetyReport")
        for group, value in self.bundle.items():
            if not isinstance(value, dict):
                continue
            for key in value:
                with self.subTest(f"{group}.{key}"):
                    path = f"{group}.{key}"
                    self.assertIn(path, e2b_mod.E2B_NUMBERS, f"{path} has no number")
                    node = report.find(group).find(key)
                    self.assertIsNotNone(node, f"{path} missing from the XML")
                    self.assertEqual(node.get("number"), e2b_mod.E2B_NUMBERS[path])

    def test_list_leaves_have_a_declared_item_tag(self):
        for key in ("seriousness_flags", "values"):
            with self.subTest(key):
                self.assertIn(key, e2b_mod.LIST_ITEM_TAGS)


# ─── C. XML generation ──────────────────────────────────────────────────────
class TestE2BXmlGeneration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAVE_E2B:
            require_e2b()
        cls.case = sample_case()
        cls.bundle = sample_bundle()
        cls.xml = e2b_mod.e2b_xml_from_case(cls.bundle, cls.case["id"])
        cls.root = ET.fromstring(cls.xml)

    def test_well_formed_with_declaration(self):
        self.assertTrue(self.xml.startswith('<?xml version="1.0" encoding="UTF-8"?>'))
        self.assertEqual(self.root.tag, e2b_mod.E2B_XML_ROOT)
        self.assertIsNotNone(self.root.find("ichicsrMessageHeader"))
        self.assertIsNotNone(self.root.find("safetyReport"))

    def test_sender_case_id_present(self):
        report = self.root.find("safetyReport")
        self.assertEqual(report.findtext("sender_case_id"), self.case["id"])
        self.assertEqual(report.findtext("sender_case_id"), self.bundle["sender_case_id"])
        header = self.root.find("ichicsrMessageHeader")
        self.assertEqual(header.findtext("messageNumber"), self.case["id"])

    def test_sender_case_id_argument_wins(self):
        xml = e2b_mod.e2b_xml_from_case(self.bundle, "OVERRIDE-1")
        root = ET.fromstring(xml)
        self.assertEqual(root.find("safetyReport").findtext("sender_case_id"), "OVERRIDE-1")

    def test_patient_data_present(self):
        patient = self.root.find("safetyReport/patient")
        self.assertEqual(patient.findtext("patient_age"), "34")
        self.assertEqual(patient.findtext("patient_sex"), "female")
        self.assertEqual(patient.findtext("patient_initials"), "AK")

    def test_seriousness_flags_mirrored(self):
        serious = self.root.find("safetyReport/seriousness")
        self.assertEqual(serious.findtext("is_serious"), "true")
        flags = [el.text for el in serious.find("seriousness_flags")]
        self.assertEqual(flags, self.bundle["seriousness"]["seriousness_flags"])

    def test_non_serious_flag_is_false_not_absent(self):
        case = sample_case()
        case["seriousness_flags"] = []
        bundle = pv.build_e2b_case(case)
        root = ET.fromstring(e2b_mod.e2b_xml_from_case(bundle, case["id"]))
        serious = root.find("safetyReport/seriousness")
        self.assertEqual(serious.findtext("is_serious"), "false")
        self.assertEqual([el.text for el in serious.find("seriousness_flags")], [])

    def test_primary_source_reporter_product_and_event_mirrored(self):
        report = self.root.find("safetyReport")
        for group in ("primary_source", "reporter", "suspect_product", "event"):
            node = report.find(group)
            self.assertIsNotNone(node, f"{group} missing")
            for key, value in self.bundle[group].items():
                with self.subTest(f"{group}.{key}"):
                    if isinstance(value, dict):
                        self.assertEqual(
                            node.find(key).text,
                            json.dumps(value, ensure_ascii=False, sort_keys=True, default=str),
                        )
                    elif isinstance(value, list):
                        self.assertEqual(
                            [el.text for el in node.find(key)],
                            [str(v) for v in value],
                        )
                    else:
                        self.assertEqual(node.findtext(key), expected_text(value))

    def test_dates_day_zero_and_values(self):
        dates = self.root.find("safetyReport/dates")
        self.assertEqual(dates.findtext("day_zero"), self.bundle["dates"]["day_zero"])
        self.assertEqual(
            [el.text for el in dates.find("values")], self.bundle["dates"]["values"]
        )
        self.assertIn(self.bundle["dates"]["day_zero"], dates.findtext("day_zero"))

    def test_reporter_causality_is_verbatim(self):
        causality = self.root.find("safetyReport/reporter_causality")
        self.assertEqual(causality.findtext("verbatim"), sample_case()["causality_reporter"])
        self.assertEqual(
            causality.findtext("reporter_assessment"), sample_case()["expectedness"]
        )

    def test_leaf_values_mirror_the_bundle(self):
        report = self.root.find("safetyReport")
        for group, value in self.bundle.items():
            if group == "sender_case_id" or not isinstance(value, dict):
                continue
            for key, item in value.items():
                with self.subTest(f"{group}.{key}"):
                    child = report.find(group).find(key)
                    if isinstance(item, (list, tuple, set, frozenset)):
                        tag = e2b_mod.LIST_ITEM_TAGS[key]
                        self.assertEqual(
                            [el.text for el in child.findall(tag)],
                            [str(v) for v in pv_sorted(item)],
                        )
                    else:
                        self.assertEqual(child.text or "", expected_text(item))

    def test_xml_special_characters_round_trip(self):
        case = sample_case()
        case["event_text"] = "burning & itching <severe> \"quotes\" 'apos'"
        bundle = pv.build_e2b_case(case)
        root = ET.fromstring(e2b_mod.e2b_xml_from_case(bundle, case["id"]))
        self.assertEqual(
            root.find("safetyReport/event").findtext("event_text"), case["event_text"]
        )

    def test_control_characters_cannot_break_well_formedness(self):
        case = sample_case()
        case["event_text"] = "rash\x00 and \x07itching"
        bundle = pv.build_e2b_case(case)
        root = ET.fromstring(e2b_mod.e2b_xml_from_case(bundle, case["id"]))
        self.assertEqual(
            root.find("safetyReport/event").findtext("event_text"), "rash and itching"
        )

    def test_non_ascii_verbatim_survives(self):
        text = self.root.find("safetyReport/event").findtext("event_text")
        self.assertEqual(text, sample_case()["event_text"])
        self.assertIn("खुजली", text)

    def test_generation_is_deterministic(self):
        again = e2b_mod.e2b_xml_from_case(sample_bundle(), sample_case()["id"])
        self.assertEqual(again, self.xml)
        self.assertEqual(again.encode("utf-8"), self.xml.encode("utf-8"))

    def test_key_order_of_the_input_does_not_change_the_output(self):
        bundle = sample_bundle()
        shuffled = {key: bundle[key] for key in reversed(list(bundle))}
        for group, value in shuffled.items():
            if isinstance(value, dict):
                shuffled[group] = {k: value[k] for k in reversed(list(value))}
        self.assertEqual(
            e2b_mod.e2b_xml_from_case(shuffled, sample_case()["id"]), self.xml
        )

    def test_empty_bundle_still_well_formed(self):
        root = ET.fromstring(e2b_mod.e2b_xml_from_case({}, ""))
        for group in pv.E2B_CASE_GROUPS:
            with self.subTest(group):
                self.assertIsNotNone(root.find("safetyReport").find(group))

    def test_no_case_content_in_the_envelope_beyond_the_case_id(self):
        """The envelope carries identity + case id only, never case data."""
        header = self.root.find("ichicsrMessageHeader")
        texts = " ".join((el.text or "") for el in header)
        for forbidden in ("Metformin", "AK", "hospitalisation", "गैस्ट्रिक"):
            with self.subTest(forbidden):
                self.assertNotIn(forbidden, texts)


# ─── D. Pretty form for the print/audit path ────────────────────────────────
class TestFormatView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAVE_E2B:
            require_e2b()
        cls.case = sample_case()
        cls.xml = e2b_mod.e2b_xml_from_case(pv.build_e2b_case(cls.case), cls.case["id"])

    def test_indented_form_parses(self):
        pretty = e2b_mod.format_view(self.xml)
        self.assertIn("\n  <safetyReport", pretty)
        root = ET.fromstring(pretty)
        self.assertEqual(root.find("safetyReport/event").findtext("event_text"),
                         sample_case()["event_text"])

    def test_accepts_bytes(self):
        pretty = e2b_mod.format_view(self.xml.encode("utf-8"))
        self.assertEqual(ET.fromstring(pretty).tag, e2b_mod.E2B_XML_ROOT)

    def test_is_deterministic(self):
        self.assertEqual(e2b_mod.format_view(self.xml), e2b_mod.format_view(self.xml))

    def test_empty_input_is_empty(self):
        self.assertEqual(e2b_mod.format_view(""), "")


# ─── E. Gateway adapter + stub (nothing sends) ──────────────────────────────
class TestGatewayAdapter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAVE_E2B:
            require_e2b()

    def test_base_adapter_is_an_interface(self):
        adapter = e2b_mod.GatewayAdapter()
        with self.assertRaises(NotImplementedError):
            adapter.channel()
        with self.assertRaises(NotImplementedError):
            adapter.submit(b"<ichicsrMessage/>")

    def test_stub_declares_the_interface(self):
        self.assertTrue(issubclass(e2b_mod.StubGatewayAdapter, e2b_mod.GatewayAdapter))
        for name in ("channel", "submit"):
            with self.subTest(name):
                self.assertTrue(callable(getattr(e2b_mod.StubGatewayAdapter, name, None)))

    def test_stub_channel_is_stub(self):
        self.assertEqual(e2b_mod.StubGatewayAdapter().channel(), "stub")

    def test_stub_reply_contract(self):
        reply = e2b_mod.StubGatewayAdapter().submit(b"<ichicsrMessage/>")
        self.assertIsInstance(reply, e2b_mod.GatewayReply)
        self.assertEqual(reply.status, 202)
        self.assertTrue(reply.accepted)
        self.assertEqual(reply.channel, "stub")
        self.assertEqual(reply.receipt_id, e2b_mod.STUB_RECEIPT_ID)
        self.assertIsInstance(reply.payload, bytes)
        self.assertTrue(reply.payload)

    def test_stub_reply_is_deterministic(self):
        stub = e2b_mod.StubGatewayAdapter()
        first = stub.submit(b"<ichicsrMessage/>")
        second = stub.submit(b"<ichicsrMessage/>")
        self.assertEqual(first.payload, second.payload)
        other = stub.submit(b"<ichicsrMessage><v>2</v></ichicsrMessage>")
        self.assertNotEqual(first.payload, other.payload, "receipt must name the payload")

    def test_stub_reply_echoes_no_case_content(self):
        """A stub acknowledgement must never carry patient/case text."""
        case = sample_case()
        payload = e2b_mod.StubGatewayAdapter().submit(
            e2b_mod.e2b_xml_from_case(pv.build_e2b_case(case), case["id"]).encode("utf-8")
        )
        body = payload.payload.decode("utf-8")
        for forbidden in (case["event_text"], case["patient_initials"], "Metformin"):
            with self.subTest(forbidden):
                self.assertNotIn(forbidden, body)

    def test_stub_submit_opens_no_socket(self):
        """The whole point: preparing a submission must not touch the network."""
        calls = []

        def boom(*args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("slice 2A must not open a network connection")

        saved = {
            name: getattr(socket, name)
            for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname")
        }
        for name in saved:
            setattr(socket, name, boom)
        try:
            case = sample_case()
            reply = e2b_mod.StubGatewayAdapter().submit(
                e2b_mod.e2b_xml_from_case(
                    pv.build_e2b_case(case), case["id"]
                ).encode("utf-8")
            )
        finally:
            for name, fn in saved.items():
                setattr(socket, name, fn)
        self.assertEqual(calls, [], "no network call is permitted on this path")
        self.assertIsInstance(reply, e2b_mod.GatewayReply)

    def test_no_network_module_imported_by_the_service(self):
        roots = module_import_roots(read(E2B_SVC))
        self.assertFalse(
            roots & NETWORK_ROOTS, f"network roots imported: {sorted(roots & NETWORK_ROOTS)}"
        )


# ─── F. The export gate (404 / 422) ─────────────────────────────────────────
class TestE2BExportBlock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAVE_E2B:
            require_e2b()

    def test_complete_case_is_exportable(self):
        self.assertEqual(e2b_mod.e2b_export_block(sample_case()), e2b_mod.E2B_EXPORTABLE)

    def test_missing_case_is_404(self):
        self.assertEqual(e2b_mod.CASE_NOT_FOUND_DETAIL, "case not found")
        for empty in ({}, None, {"id": "", "event_text": "rash"}):
            with self.subTest(repr(empty)):
                status, detail = e2b_mod.e2b_export_block(empty)
                self.assertEqual(status, 404)
                self.assertEqual(detail, e2b_mod.CASE_NOT_FOUND_DETAIL)

    def test_incomplete_case_is_422_naming_the_missing_elements(self):
        case = sample_case()
        case["e2b_minimum_met"] = False
        case["patient_age"] = ""
        case["patient_sex"] = ""
        case["patient_initials"] = ""
        case["reporter_contact"] = {}
        case["reporter_type"] = ""
        status, detail = e2b_mod.e2b_export_block(case)
        self.assertEqual(status, 422)
        self.assertIn("reporter", detail)
        self.assertIn("patient", detail)
        self.assertNotIn("product", detail, "a complete product is not missing")
        self.assertNotIn("event", detail)

    def test_missing_elements_follow_the_phase1_canonical_order(self):
        case = sample_case()
        case["e2b_minimum_met"] = False
        case["event_text"] = ""
        case["reporter_contact"] = {}
        case["reporter_type"] = ""
        case["product_name"] = ""
        case["product_id"] = ""
        case["patient_age"] = ""
        case["patient_sex"] = ""
        case["patient_initials"] = ""
        _status, detail = e2b_mod.e2b_export_block(case)
        order = [item.strip() for item in detail.split(":", 1)[1].split(",")]
        self.assertEqual(order, list(pv.MINIMUM_CRITERIA_ELEMENTS))


# ─── G. /api/pv routes ──────────────────────────────────────────────────────
E2B_XML_ROUTE = ("get", "/cases/{case_id}/e2b.xml")
E2B_SUBMIT_ROUTE = ("post", "/cases/{case_id}/e2b")
E2B_XML_ENDPOINT = "get_pv_case_e2b_xml_ep"
E2B_SUBMIT_ENDPOINT = "prepare_pv_case_e2b_submission_ep"
E2B_GATEWAY_HELPER = "_e2b_case"


class TestE2BRouter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(PV_ROUTER)
        cls.tree = py_tree(PV_ROUTER)

    def test_router_prefix_unchanged(self):
        self.assertEqual("/api/pv", router_prefix(self.tree))

    def test_both_e2b_routes_exist(self):
        found = {(verb, path) for verb, path, _ in endpoints(self.tree)}
        for route in (E2B_XML_ROUTE, E2B_SUBMIT_ROUTE):
            with self.subTest(route):
                self.assertIn(route, found)

    def test_e2b_xml_route_is_service_token_guarded(self):
        block = fn_block(self.text, E2B_XML_ENDPOINT)
        self.assertIn("WEBHOOK_SERVICE_TOKEN", block, "mirror the intake token check")
        self.assertIn("X-Service-Token", block)
        self.assertIn("hmac", block, "token compare must be constant-time")
        self.assertNotIn("get_current_user", block, "the XML path is service-token gated")

    def test_e2b_xml_route_returns_xml_content_type(self):
        block = fn_block(self.text, E2B_XML_ENDPOINT)
        self.assertIn("e2b_xml_from_case", block)
        self.assertIn("application/xml", block)
        self.assertIn("Response", block)

    def test_e2b_routes_reject_missing_or_incomplete_cases(self):
        for name in (E2B_XML_ENDPOINT, E2B_SUBMIT_ENDPOINT):
            with self.subTest(name):
                block = fn_block(self.text, name)
                self.assertIn("_e2b_case", block, f"{name}: must use the shared gate")
        gate = fn_block(self.text, E2B_GATEWAY_HELPER)
        self.assertIn("e2b_export_block", gate, "the gate must be the one decision")
        self.assertIn("404", gate, "a case that was never stored is 404")
        self.assertIn("422", gate, "an incomplete case is 422, not a bad request")
        self.assertIn("CASE_NOT_FOUND_DETAIL", gate, "reasons live in the e2b service")

    def test_both_routes_build_from_the_phase1_bundle(self):
        for name in (E2B_XML_ENDPOINT, E2B_SUBMIT_ENDPOINT):
            with self.subTest(name):
                block = fn_block(self.text, name)
                self.assertIn("e2b_xml_from_case", block)
                self.assertIn("build_e2b_case", block, f"{name}: use the Phase-1 exporter")

    def test_the_gate_reads_the_case_row_once(self):
        gate = fn_block(self.text, E2B_GATEWAY_HELPER)
        self.assertIn("_case_row", gate, "the gate decides on the same row the route uses")
        self.assertIn("get_adverse_event", gate)

    def test_submit_route_is_identity_gated_and_stub_only(self):
        block = fn_block(self.text, E2B_SUBMIT_ENDPOINT)
        self.assertIn("get_current_user", block, "PVOIC/staff action is identity-gated")
        self.assertNotIn("WEBHOOK_SERVICE_TOKEN", block)
        self.assertIn("StubGatewayAdapter", block, "slice 2A ships the stub adapter only")

    def test_submit_route_returns_xml_payload_and_channel(self):
        block = fn_block(self.text, E2B_SUBMIT_ENDPOINT)
        self.assertIn(".submit(", block)
        self.assertIn("payload", block)
        self.assertIn("channel()", block)
        self.assertIn("base64", block)
        self.assertIn("create_compliance_event", block, "an audit row per artifact built")

    def test_router_imports_the_e2b_service(self):
        self.assertIn("from app.services.e2b import", self.text)
        self.assertIn("e2b_xml_from_case", self.text)

    def test_no_router_imports_a_network_client(self):
        roots = module_import_roots(self.text)
        for banned in ("requests", "httpx", "urllib"):
            with self.subTest(banned):
                self.assertNotIn(banned, roots, "no live submission in slice 2A")
