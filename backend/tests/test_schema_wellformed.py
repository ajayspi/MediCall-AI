"""Structural well-formedness guard for backend/postgres_schema.sql.

Regression guard for the defect found during PV Phase 1 (spec-micc-pv-module.md
final state): `CREATE TABLE call_sessions (` was never terminated, so
`CREATE TABLE payments (` was nested inside it — invalid SQL that breaks any
live `psql -f` run (incl. the parked Docker walkthrough). The check is
deliberately mechanical and dumb: statements must start at column 0, and every
CREATE TABLE must reach a paren-balanced close before the next statement or
EOF. Mirrors test_g5_reqs.py's file-reading style; never touches a database.
"""
import unittest
from pathlib import Path

SCHEMA = Path(__file__).resolve().parents[1] / "postgres_schema.sql"


def _strip_comment(line: str) -> str:
    return line.split("--", 1)[0]


def schema_lines():
    with SCHEMA.open(encoding="utf-8") as fh:
        return fh.read().splitlines()


class TestSchemaWellFormed(unittest.TestCase):

    def test_create_tables_are_top_level_and_paren_closed(self):
        lines = schema_lines()
        problems = []
        block = None  # line no of the open CREATE TABLE
        depth = 0
        for i, raw in enumerate(lines, 1):
            line = _strip_comment(raw).rstrip()
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("CREATE TABLE"):
                if block is not None:
                    problems.append(f"line {i}: CREATE TABLE while line {block} still open")
                if stripped != line:
                    problems.append(f"line {i}: CREATE TABLE not at column 0")
                block = i
                depth += stripped.count("(") - stripped.count(")")
                continue
            if block is not None:
                depth += stripped.count("(") - stripped.count(")")
                if depth <= 0:
                    if stripped.endswith(";"):
                        # The line directly before the closer must not end with a
                        # dangling comma (e.g. "col ...,\n);" is invalid SQL).
                        # Scan back past blanks/comments to the last content line.
                        j = i - 2  # 0-based index of the line above the closer
                        while j >= 0:
                            prev = _strip_comment(lines[j]).rstrip()
                            if prev.strip():
                                break
                            j -= 1
                        if j >= 0 and prev.endswith(","):
                            problems.append(f"line {i}: trailing comma before ');'")
                        block = None
                        depth = 0
                    else:
                        problems.append(
                            f"line {i}: table parens closed but statement lacks trailing ';'"
                        )
                        block = None
                        depth = 0
        if block is not None:
            problems.append(f"EOF: CREATE TABLE at line {block} never closed")
        self.assertEqual([], problems, "schema structure problems:\n" + "\n".join(problems))


if __name__ == "__main__":
    unittest.main()