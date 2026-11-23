"""Print a verified blind retrospective packet in chronological pages."""
import argparse
import json

from .archive_review import digest, rows
from .archive_trace_wave import ROOT


def main(batch, index, start, page_bytes, deduplicate_text=False):
    plan = json.loads((ROOT / "manifest.json").read_text())
    entries = {entry["path"]: entry["sha256"] for lane in plan["cohorts"].values() for entry in lane["batches"]}
    path = ROOT / f"{batch}.jsonl"
    if path.name not in entries or digest(path) != entries[path.name]:
        raise ValueError("The requested blind batch differs from the frozen manifest")
    tracks = list(rows(path).values())
    if not 1 <= index <= len(tracks):
        raise ValueError(f"Choose row 1 through {len(tracks)}")
    packet = tracks[index - 1]
    events = packet["events"]
    if not 0 <= start < len(events):
        raise ValueError(f"Choose event index 0 through {len(events) - 1}")
    print(json.dumps({"id": packet["id"], "actions": packet["actions"],
                      "events_total": len(events), "start_index": start}, ensure_ascii=False))
    used = 0
    first_text = {}
    for offset, event in enumerate(events):
        item = event
        if deduplicate_text and event.get("text"):
            text = event["text"]
            prior = first_text.setdefault(text, event["seq"])
            if prior != event["seq"]:
                item = {k: v for k, v in event.items() if k != "text"}
                item["identical_text_at_seq"] = prior
        if offset < start:
            continue
        line = json.dumps(item, ensure_ascii=False)
        size = len(line.encode("utf-8")) + 1
        if used and used + size > page_bytes:
            print(json.dumps({"next_index": offset}))
            return
        print(line)
        used += size
    print(json.dumps({"next_index": None}))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("batch")
    cli.add_argument("row", type=int)
    cli.add_argument("--start", type=int, default=0)
    cli.add_argument("--page-bytes", type=int, default=5500)
    cli.add_argument("--deduplicate-text", action="store_true")
    args = cli.parse_args()
    main(args.batch, args.row, args.start, args.page_bytes, args.deduplicate_text)
