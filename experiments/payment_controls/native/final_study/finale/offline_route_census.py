"""Read previously recorded FinBot route packets and print their aggregate coverage."""

import argparse
from collections import Counter
import json
from pathlib import Path

from ...overnight import route


def census(archive):
    counts = Counter()
    for filename in ("pre-fraud-packets.jsonl", "route-packets.jsonl"):
        for path in sorted(archive.rglob(filename)):
            with path.open() as source:
                for line in source:
                    if not line.strip() or "packet" not in (row := json.loads(line)):
                        continue
                    packet = row["packet"]
                    choice, reasons, _ = route.evaluate(packet)
                    veto = route.mandatory_veto(packet, reasons)
                    history = any(invoice["id"] != packet["inv"]["id"] for invoice in packet["paid"])
                    counts[path.relative_to(archive).parts[0], choice, bool(veto), history, tuple(reasons)] += 1

    print(json.dumps([
        dict(source=source, route=choice, mandatory=mandatory, other_paid_history=history,
             reasons=reasons, recorded_packets=n)
        for (source, choice, mandatory, history, reasons), n in sorted(counts.items())
    ], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    census(parser.parse_args().archive)
