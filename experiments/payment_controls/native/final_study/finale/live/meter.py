"""Authenticate and enforce the new cumulative provider limit including open reserves."""
from datetime import UTC, datetime
import math

from ...live_meter import halt


def ledger(base, stopped):
    class FinaleLedger(base):
        def reserve(self, key, phase, worst):
            if phase != "test" or not math.isfinite(worst) or worst <= 0:
                raise stopped("Invalid live phase or request reserve")
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                if (self.path.parent / "halt.json").exists():
                    raise stopped("Provider or budget halted")
                if db.execute("SELECT 1 FROM requests WHERE id=?", (key,)).fetchone():
                    raise stopped("Duplicate request identity")
                exposure, = db.execute("SELECT COALESCE(SUM(COALESCE(cost,reserve)),0) FROM requests").fetchone()
                if exposure + worst > self.cap:
                    halt(self.path.parent, "eliza exposure cap")
                    raise stopped("Eliza cumulative exposure cap")
                db.execute("INSERT INTO requests VALUES (?,?,?,?,NULL,?,NULL)",
                           (key, phase, datetime.now(UTC).date().isoformat(), worst, "reserved"))

        def complete(self, key, cost):
            try:
                super().complete(key, cost)
            except stopped:
                halt(self.path.parent, "eliza authoritative cost or reservation mismatch")
                raise

    return FinaleLedger
