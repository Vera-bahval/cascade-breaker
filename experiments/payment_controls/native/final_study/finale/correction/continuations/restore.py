"""Find a genuine WAL version at a scored native P1/P4 boundary without provider calls."""

import argparse
from collections import defaultdict
from contextlib import closing
from datetime import UTC, datetime
import gzip
import json
from pathlib import Path
import sqlite3
from struct import unpack
from tempfile import TemporaryDirectory

from ...examples.continuation import digest, fields_match, record_hash


def read(path):
    return json.loads(path.read_text())


def clock_window(path, workflow, boundary):
    """Bracket the recorder clock offset with matching native SDK requests."""
    requests = defaultdict(list)
    responses = {}
    with gzip.open(path, "rt") as stream:
        for row in map(json.loads, stream):
            if row["event"] == "request":
                requests[record_hash(row["sdk_request"].get("input"))].append(row)
            if row["event"] == "response" and row["http_status"] == 200:
                responses[row["attempt_id"]] = row
    lower, upper = -float("inf"), float("inf")
    exact = 0
    for step in workflow["steps"]:
        if step["kind"] != "llm" or step["error"]:
            continue
        rows = requests[record_hash(step["messages"])]
        if len(rows) != 1 or step["messages"] != rows[0]["sdk_request"]["input"]:
            continue
        request = rows[0]
        response = responses.get(request["attempt_id"])
        if response is None:
            continue
        # Trace milliseconds are rounded to one decimal place.
        lower = max(lower, timestamp(response["utc"]) - (step["t_ms"] + .1) / 1000)
        upper = min(upper, timestamp(request["utc"]) - (step["t_start_ms"] - .1) / 1000)
        exact += 1
    if not exact or not 0 <= upper - lower < .1:
        raise ValueError("Transport and trace did not establish a stable clock bracket")
    return lower + boundary["t_ms"] / 1000, upper + boundary["t_ms"] / 1000, exact


def timestamp(value):
    parsed = datetime.fromisoformat(value)
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).timestamp()


def sql_row(db, table, namespace, ident):
    return db.execute(f"SELECT * FROM {table} WHERE namespace=? AND id=?", (namespace, ident)).fetchone()


def table_hash(db, table):
    return record_hash([tuple(row) for row in db.execute(f'SELECT * FROM "{table}" ORDER BY rowid')])



def transaction_match(row, expected):
    values = dict(row)
    values["metadata"] = json.loads(values["metadata_json"]) if values["metadata_json"] else None
    for key in ("created_at", "updated_at"):
        if timestamp(values[key]) != timestamp(expected[key]):
            return False
        values[key] = expected[key]
    return fields_match(values, expected)

def restore(source, capture_file, dest=None):
    capture = read(capture_file)
    terminal = read(source / "episode.json")
    workflow = terminal["traces"][capture["workflow_id"]]
    if any(step["kind"] == "injection" for step in workflow["steps"][:capture["trace_cutoff_seq"] + 1]):
        raise ValueError("An ordinary native continuation requires an injection-free prefix")
    point, index = capture_file.stem.split("-", 1)
    boundary = workflow["steps"][capture["trace_cutoff_seq"] + 1]
    if (boundary["kind"], boundary["point"], boundary["capture"], boundary["invoice_id"]) != (
        "finale_boundary", point, int(index), capture["invoice_id"]
    ):
        raise ValueError("Boundary event mismatch")
    low, high, exact = clock_window(source / "calls.jsonl.gz", workflow, boundary)
    prior_transfers = sum(step["kind"] == "tool" and step["name"] == "finstripe__create_transfer"
                          and step["arguments"] == capture["arguments"]
                          for step in workflow["steps"][:capture["trace_cutoff_seq"] + 1]) if point == "P4" else None
    snap = capture["snapshot"]
    iid, namespace = capture["invoice_id"], capture["namespace"]
    base = (source / "finbot.db").read_bytes()
    wal = (source / "finbot.db-wal").read_bytes()
    magic, version, page_size, _, salt1, salt2, _, _ = unpack(">8I", wal[:32])
    frame_size = 24 + page_size
    if (magic not in {0x377F0682, 0x377F0683} or version != 3007000 or len(base) != page_size
        or (len(wal) - 32) % frame_size):
        raise ValueError("Archive contains an unsupported or incomplete SQLite WAL")
    matches = []
    with TemporaryDirectory(prefix="finbot-as-of-") as temp:
        path = Path(temp) / "candidate.db"
        wp = path.with_name(path.name + "-wal")
        for frame, offset in enumerate(range(32, len(wal), frame_size), 1):
            page, db_size, s1, s2, _, _ = unpack(">6I", wal[offset:offset + 24])
            if not page or (s1, s2) != (salt1, salt2):
                raise ValueError("WAL generation changed")
            if not db_size:
                continue
            end = offset + frame_size
            path.write_bytes(base)
            wp.write_bytes(wal[:end])
            try:
                with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
                    db.row_factory = sqlite3.Row
                    tables = [row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")]
                    if not {"invoices", "vendors", "payment_transactions", "emails", "mcp_activity_log"} <= set(tables):
                        continue
                    if db.execute("PRAGMA page_count").fetchone()[0] != db_size:
                        raise ValueError("SQLite rejected a WAL commit")
                    inv = sql_row(db, "invoices", namespace, iid)
                    ven = sql_row(db, "vendors", namespace, snap["vendor"]["id"])
                    if not inv or not ven or not fields_match(inv, snap["invoice"]) or not fields_match(ven, snap["vendor"]):
                        continue
                    tx = db.execute("SELECT * FROM payment_transactions WHERE namespace=? AND invoice_id=? ORDER BY id",
                                    (namespace, iid)).fetchall()
                    if len(tx) != len(snap["transactions"]) or any(
                        not transaction_match(row, want) for row, want in zip(tx, snap["transactions"])
                    ):
                        continue
                    audit = {row[0]: timestamp(row[1]) for row in db.execute(
                        "SELECT id,created_at FROM mcp_activity_log WHERE namespace=?", (namespace,)
                    )}
                    if prior_transfers is not None:
                        # FinStripe dispatch is strictly after the capture event. Network clock uncertainty can
                        # otherwise include its first audit write among plausible states before native transfer.
                        actual = sum(json.loads(row[0])["arguments"] == capture["arguments"] for row in db.execute(
                            "SELECT payload_json FROM mcp_activity_log WHERE workflow_id=? AND namespace=? "
                            "AND server_type='finstripe' AND direction='request' AND tool_name='create_transfer'",
                            (capture["workflow_id"], namespace),
                        ))
                        if actual != prior_transfers:
                            continue
                    hashes = {table: table_hash(db, table) for table in tables}
                    matches.append((frame, end, audit, hashes))
            finally:
                for candidate in path.parent.glob(path.name + "*"):
                    candidate.unlink()
    if not matches:
        raise ValueError("No archived commit reproduces the native boundary snapshot")
    audit_times = {}
    for _, _, audit, _ in matches:
        audit_times.update(audit)
    required = {key for key, at in audit_times.items() if at < low}
    possible = {key for key, at in audit_times.items() if at <= high}
    candidates = [row for row in matches if required <= row[2].keys() <= possible]
    if not candidates or len({record_hash(row[3]) for row in candidates}) != 1:
        raise ValueError("The clock and scoped snapshot leave multiple possible full states or none")
    frame, end, _, hashes = candidates[0]
    if dest is not None:
        dest.mkdir(mode=0o700, parents=True, exist_ok=False)
        (dest / "finbot.db").write_bytes(base)
        (dest / "finbot.db-wal").write_bytes(wal[:end])
        with closing(sqlite3.connect((dest / "finbot.db").as_uri() + "?mode=ro", uri=True)) as db:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Restored SQLite integrity check failed")
    return {"assignment": source.name, "capture": capture_file.name, "workflow_id": capture["workflow_id"],
            "cutoff_seq": capture["trace_cutoff_seq"], "matching_receipt_requests": exact,
            "clock_window_ms": round((high - low) * 1000, 3), "commit_frames": [r[0] for r in candidates],
            "restored_frame": frame, "db_sha256": digest(base), "wal_prefix_sha256": digest(wal[:end]),
            "full_state_sha256": record_hash(hashes), "capture_sha256": digest(capture_file.read_bytes())}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("capture")
    parser.add_argument("--clone", type=Path)
    args = parser.parse_args()
    print(json.dumps(restore(args.source, args.source / args.capture,
                             args.clone.resolve() if args.clone else None), indent=2))
