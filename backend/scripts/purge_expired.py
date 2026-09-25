"""One-shot retention purge runner (G6-Q2 -> G6-Q10 wiring).

Q2 delivered the retention policy + `postgres.purge_expired`; the schedule was
deferred ("Docker/CI cron") — this script closes that. It connects through the
app's own async engine (DATABASE_URL), deletes each retention category past its
deadline, and prints per-kind deleted counts. `recordings` purges external
MinIO/S3 objects (LiveKit egress) — noted, no rows here.

Run inside the backend image (or any host with the app deps):

    python scripts/purge_expired.py [now_iso]

Scheduled by .github/workflows/purge.yml (daily 03:00 UTC) as:

    docker compose run --rm backend python scripts/purge_expired.py

Never auto-runs on import; env RETENTION_* overrides are honored by
app.services.retention. Exit code 0 on success.
"""
import asyncio
import sys
from datetime import datetime, timezone

from app.db.postgres import purge_expired
from app.services.retention import retention_categories


async def _run(now: datetime) -> int:
    total = 0
    for kind in retention_categories():
        if kind == "recordings":
            print(
                "[purge] recordings: external MinIO/S3 objects "
                "(LiveKit egress) — no rows here"
            )
            continue
        deleted = await purge_expired(kind, now=now)
        print(f"[purge] {kind}: {deleted} deleted")
        total += deleted
    return total


def main(argv: list) -> int:
    now = (
        datetime.fromisoformat(argv[1])
        if len(argv) > 1
        else datetime.now(timezone.utc)
    )
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    total = asyncio.run(_run(now))
    print(f"[purge] total: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))