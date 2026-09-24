"""UML diagrams acceptance tests — 6 diagrams + index under docs/uml/ (stdlib only).

RED before implementation (2026-09-25, spec-uml-diagrams.md D1/D2/D3 approved:
Mermaid-in-Markdown, docs/uml/ one file per diagram, five G7 diagrams + a 6th
call-lifecycle sequence diagram): docs/uml/ does not exist.

GREEN after implementation:
- 00-index.md links all six diagrams and points at the single sources
  (postgres_schema.sql, models/call.py, the routers, docker-compose.yml).
- 01-er.md erDiagram: the 9 tables from postgres_schema.sql with FK edges
  matching the schema exactly (incl. the API-phase payments table).
- 02-state-machine.md stateDiagram-v2: the mermaid transition edge set EQUALS
  STATE_TRANSITIONS parsed from app/models/call.py via ast (load-bearing
  cross-check — the diagram cannot drift from the code).
- 03-api-contracts.md: all 6 router prefixes + the endpoint paths from
  test_api_routes.py EXPECTED_ENDPOINTS + voice.py, and the 409/422/404
  contract annotations.
- 04-data-flow.md: Exotel/Knowlarity/Twilio-India -> voice.py webhooks ->
  LiveKit agent -> Deepgram STT / ElevenLabs TTS (hi/en/ta/te/bn) ->
  /call-completed -> update_call_transcript (Docker/CI TODO marked).
- 05-deployment.md: the docker-compose.yml stack (frontend/backend/postgres/
  redis) + external SaaS (LiveKit, Deepgram, ElevenLabs, OpenAI, telephony).
- 06-call-lifecycle.md: sequenceDiagram of one inbound call through the state
  machine including the PAYMENT_SENT/PAYMENT_EXPIRED loop.
- No restaurant/TalkByte leftovers in any of the 7 new files.

Run: python3 tests/test_uml_diagrams.py  (exit 0 = green)
"""
import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND = ROOT / "backend"
UML_DIR = ROOT / "docs" / "uml"
CALL_MODEL = BACKEND / "app" / "models" / "call.py"
COMPOSE = ROOT / "docker-compose.yml"

DIAGRAMS = ("01-er", "02-state-machine", "03-api-contracts", "04-data-flow", "05-deployment", "06-call-lifecycle")

TABLES = (
    "clinics",
    "clinic_users",
    "calls",
    "appointments",
    "prescriptions",
    "call_embeddings",
    "language_codes",
    "call_sessions",
    "payments",
)

# (lhs, relation, rhs, label) — one per FK in postgres_schema.sql
ER_EDGES = (
    ("clinics", "||--o{", "clinic_users", "clinic_id"),
    ("clinics", "||--o{", "calls", "clinic_id"),
    ("clinics", "||--o{", "appointments", "clinic_id"),
    ("clinics", "||--o{", "prescriptions", "clinic_id"),
    ("clinics", "||--o{", "call_sessions", "clinic_id (SET NULL)"),
    ("clinics", "||--o{", "payments", "clinic_id"),
    ("calls", "||--o|", "appointments", "caller_id (SET NULL)"),
    ("calls", "||--o|", "prescriptions", "caller_id (SET NULL)"),
    ("calls", "||--o|", "call_embeddings", "call_id (UNIQUE)"),
    ("calls", "||--o|", "call_sessions", "call_id (UNIQUE)"),
    ("calls", "||--o{", "payments", "call_id (SET NULL)"),
    ("appointments", "||--o{", "payments", "appointment_id (SET NULL)"),
    ("calls", "||--o|", "calls", "appointment_id (SET NULL)"),
)

ER_SPOT_COLUMNS = {
    "calls": ("JSONB transcript", "TEXT state", "TEXT caller_language"),
    "clinic_users": ("UUID user_id", "TEXT role"),
    "call_embeddings": ("VECTOR(1536)",),
    "language_codes": ("TEXT code UK",),
    "payments": ("NUMERIC(10,2) amount", "TEXT gateway"),
    "call_sessions": ("TEXT livekit_room",),
}

# Full-path endpoint strings (router prefix + path) that must appear in 03-api-contracts.md
API_PATHS = (
    "/api/voice",
    "/webhook/exotel",
    "/webhook/knowlarity",
    "/webhook/twilio",
    "/livekit-agent-start",
    "/call-completed",
    "/api/clinics",
    "/api/clinics/{clinic_id}",
    "/api/calls",
    "/api/calls/{call_id}",
    "/api/calls/{call_id}/state",
    "/api/calls/{call_id}/transcript",
    "/api/appointments",
    "/api/appointments/{appointment_id}",
    "/api/appointments/{appointment_id}/status",
    "/api/prescriptions",
    "/api/prescriptions/{prescription_id}",
    "/api/prescriptions/{prescription_id}/status",
    "/api/payments",
    "/api/payments/{payment_id}",
    "/api/payments/{payment_id}/status",
)

DATA_FLOW_TOKENS = (
    "Exotel",
    "Knowlarity",
    "Twilio",
    "Deepgram",
    "ElevenLabs",
    "LiveKit",
    "call-completed",
    "update_call_transcript",
    "PostgreSQL",
)
LANGUAGES = ("hi", "en", "ta", "te", "bn")

DEPLOYMENT_TOKENS = (
    "frontend",
    "backend",
    "postgres",
    "redis",
    "docker-compose",
    "LiveKit",
    "Deepgram",
    "ElevenLabs",
    "OpenAI",
    "pgvector",
)

SEQUENCE_TOKENS = (
    "Caller",
    "Telephony",
    "voice.py",
    "agent",
    "Deepgram",
    "ElevenLabs",
    "PostgreSQL",
    "GREETING",
    "TRIAGE",
    "PAYMENT_EXPIRED",
)

RESTAURANT_LEFTOVERS = (
    "talkbyte",
    "chain",
    "mama's",
    "margherita",
    "ord-0",
    "australia",
    "telnyx",
    "square",
    "stripe",
    "restaurant",
)

MERMAID_EDGE_RE = re.compile(r"^\s*([A-Z_]+)\s*-->\s*([A-Z_]+)\s*$")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def diagram_header(text: str) -> str:
    """The mermaid type line: first non-empty line after the opening fence."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("```mermaid"):
            for j in range(i + 1, len(lines)):
                if lines[j].strip():
                    return lines[j].strip()
            break
    return ""


def norm(s: str) -> str:
    return "".join(s.split())


def er_line(edge) -> str:
    lhs, rel, rhs, label = edge
    return f'{lhs} {rel} {rhs} : "{label}"'


def state_transitions_from_code(tree) -> set:
    """{(from_state, to_state)} edge set from the STATE_TRANSITIONS dict."""
    edges = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "STATE_TRANSITIONS"
            and isinstance(node.value, ast.Dict)
        ):
            continue
        for key, val in zip(node.value.keys, node.value.values):
            # key is `CallState.GREETING` -> Attribute(value=Name("CallState"), attr="GREETING")
            if not (
                isinstance(key, ast.Attribute)
                and isinstance(key.value, ast.Name)
                and key.value.id == "CallState"
            ):
                continue
            src = key.attr
            if not isinstance(val, ast.List):
                continue
            for elt in val.elts:
                if isinstance(elt, ast.Attribute) and isinstance(elt.value, ast.Name) and elt.value.id == "CallState":
                    edges.add((src, elt.attr))
    return edges


def mermaid_edges(text: str) -> set:
    """{(from, to)} from `X --> Y` lines in the state diagram file."""
    return {m.groups() for m in MERMAID_EDGE_RE.finditer(text)}


def table_block(text: str, name: str) -> str:
    """The attribute block of an erDiagram table (between `NAME {` and the closing `}`)."""
    m = re.search(rf"^\s*{name} \{{(.*?)^\s*\}}", text, re.M | re.S)
    return m.group(1) if m else ""


class TestDiagramFilesExist(unittest.TestCase):
    def test_all_seven_files_present(self):
        for name in ("00-index",) + DIAGRAMS:
            path = UML_DIR / f"{name}.md"
            self.assertTrue(path.is_file(), f"docs/uml/{name}.md missing")

    def test_mermaid_fence_and_type_header(self):
        headers = {
            "01-er": "erDiagram",
            "02-state-machine": "stateDiagram-v2",
            "03-api-contracts": "flowchart",
            "04-data-flow": "flowchart",
            "05-deployment": "flowchart",
            "06-call-lifecycle": "sequenceDiagram",
        }
        for name, header in headers.items():
            text = read(UML_DIR / f"{name}.md")
            self.assertIn("```mermaid", text, f"{name}.md missing mermaid fence")
            self.assertTrue(
                diagram_header(text).startswith(header),
                f"{name}.md must open the mermaid block with {header}",
            )

    def test_no_restaurant_leftovers_anywhere(self):
        files = [UML_DIR / f"{name}.md" for name in ("00-index",) + DIAGRAMS]
        for path in files:
            low = read(path).lower()
            for token in RESTAURANT_LEFTOVERS:
                self.assertNotIn(token, low, f"{path.name} contains leftover {token!r}")


class TestIndex(unittest.TestCase):
    def test_index_lists_all_diagrams(self):
        text = read(UML_DIR / "00-index.md")
        for name in DIAGRAMS:
            self.assertIn(name, text, f"00-index.md missing {name}")

    def test_index_points_at_single_sources(self):
        text = read(UML_DIR / "00-index.md")
        for src in ("postgres_schema.sql", "models/call.py", "docker-compose.yml"):
            self.assertIn(src, text, f"00-index.md missing source pointer {src}")


class TestERDiagram(unittest.TestCase):
    def test_all_nine_tables_present(self):
        text = read(UML_DIR / "01-er.md")
        for name in TABLES:
            self.assertRegex(text, rf"^\s*{name} \{{", f"ER missing table {name}")

    def test_all_fk_edges_present(self):
        text = norm(read(UML_DIR / "01-er.md"))
        for edge in ER_EDGES:
            self.assertIn(norm(er_line(edge)), text, f"ER missing edge {er_line(edge)}")

    def test_key_columns_per_table(self):
        text = read(UML_DIR / "01-er.md")
        for table, cols in ER_SPOT_COLUMNS.items():
            block = table_block(text, table)
            for col in cols:
                self.assertIn(col, block, f"ER table {table} missing column {col}")


class TestStateMachineDiagram(unittest.TestCase):
    def test_edge_set_matches_code(self):
        """Load-bearing: mermaid edges == STATE_TRANSITIONS from models/call.py."""
        tree = ast.parse(read(CALL_MODEL))
        code_edges = state_transitions_from_code(tree)
        self.assertTrue(code_edges, "no STATE_TRANSITIONS edges parsed from call.py")
        text = read(UML_DIR / "02-state-machine.md")
        diagram_edges = mermaid_edges(text)
        self.assertEqual(code_edges, diagram_edges)

    def test_all_nine_states_present(self):
        text = read(UML_DIR / "02-state-machine.md")
        for state in (
            "GREETING",
            "TRIAGE",
            "APPOINTMENT",
            "PRESCRIPTION",
            "COMPLETE",
            "ESCALATED",
            "DROPPED",
            "PAYMENT_SENT",
            "PAYMENT_EXPIRED",
        ):
            self.assertIn(state, text, f"state diagram missing {state}")

    def test_invalid_transition_note(self):
        text = read(UML_DIR / "02-state-machine.md")
        self.assertIn("409", text, "state diagram should note 409 on invalid transition")


class TestAPIContractsDiagram(unittest.TestCase):
    def test_all_endpoint_paths_present(self):
        text = read(UML_DIR / "03-api-contracts.md")
        for path in API_PATHS:
            self.assertIn(path, text, f"API contracts missing {path}")

    def test_all_six_router_prefixes_present(self):
        text = read(UML_DIR / "03-api-contracts.md")
        for prefix in (
            "/api/voice",
            "/api/clinics",
            "/api/calls",
            "/api/appointments",
            "/api/prescriptions",
            "/api/payments",
        ):
            self.assertIn(prefix, text, f"API contracts missing prefix {prefix}")

    def test_contract_behaviors_annotated(self):
        text = read(UML_DIR / "03-api-contracts.md")
        for code, behavior in (("409", "invalid transition"), ("422", "invalid status"), ("404", "missing row")):
            self.assertIn(code, text, f"API contracts missing {code}")
            self.assertIn(behavior, text, f"API contracts missing {behavior} behaviour note")


class TestDataFlowDiagram(unittest.TestCase):
    def test_pipeline_tokens_present(self):
        text = read(UML_DIR / "04-data-flow.md")
        for token in DATA_FLOW_TOKENS:
            self.assertIn(token, text, f"data flow missing {token}")

    def test_five_languages(self):
        text = read(UML_DIR / "04-data-flow.md")
        for lang in LANGUAGES:
            self.assertIn(lang, text, f"data flow missing language {lang}")

    def test_docker_ci_todo_marked(self):
        text = read(UML_DIR / "04-data-flow.md")
        self.assertIn("Docker/CI", text, "data flow should mark the postgres write as Docker/CI-owned")


class TestDeploymentDiagram(unittest.TestCase):
    def test_stack_tokens_present(self):
        text = read(UML_DIR / "05-deployment.md")
        for token in DEPLOYMENT_TOKENS:
            self.assertIn(token, text, f"deployment missing {token}")

    def test_ports_match_compose(self):
        text = read(UML_DIR / "05-deployment.md")
        compose = read(COMPOSE)
        for port in ("8001", "3000", "5432", "6379"):
            self.assertIn(port, text, f"deployment missing port {port}")
            self.assertIn(port, compose, f"docker-compose.yml missing port {port}")


class TestCallLifecycleSequence(unittest.TestCase):
    def test_participants_and_flow_present(self):
        text = read(UML_DIR / "06-call-lifecycle.md")
        for token in SEQUENCE_TOKENS:
            self.assertIn(token, text, f"sequence diagram missing {token}")

    def test_payment_loop_drawn(self):
        text = read(UML_DIR / "06-call-lifecycle.md")
        self.assertIn("PAYMENT_SENT", text, "sequence missing PAYMENT_SENT")
        self.assertIn("PAYMENT_EXPIRED", text, "sequence missing PAYMENT_EXPIRED")


if __name__ == "__main__":
    unittest.main(verbosity=2)