"""Freeze the remaining original retrospective packets without changing existing waves."""
import json

from .archive_review import HERE, digest, rows, verify_packets, write
from .archive_trace_wave import ROOT


def main():
    manifest = ROOT / "manifest.json"
    plan = json.loads(manifest.read_text())
    additions = {}
    corrected = rows(HERE / "archive_extended/native_reject_corrected_trajectory.jsonl")
    for folder in (HERE, HERE / "archive_channels", HERE / "archive_core"):
        _, primary, _ = verify_packets(folder)
        remaining = rows(folder / "archive_extended_trajectory_packets.jsonl")
        if primary.keys() & remaining.keys():
            raise ValueError(f"Source trajectories overlap: {folder.name}")
        if folder == HERE:
            if not corrected.keys() <= remaining.keys():
                raise ValueError("Corrected trajectory does not exist in historical source")
            remaining.update(corrected)
        for reached in (True, False):
            wave = f"{'main' if folder == HERE else folder.name}_{'additional_reached' if reached else 'no_reach'}"
            eligible = [track for _, track in sorted(remaining.items()) if bool(track["actions"]) == reached]
            entries = []
            for offset in range(0, len(eligible), 16):
                batch = eligible[offset:offset + 16]
                part = ROOT / f"{wave}_{offset // 16 + 1:02}.jsonl"
                if part.exists():
                    if list(rows(part).values()) != batch:
                        raise ValueError(f"Frozen retrospective packet differs: {part.name}")
                else:
                    write(part, batch)
                entries.append({"path": part.name, "tracks": len(batch), "sha256": digest(part)})
            if entries:
                additions[wave] = {"batches": entries, "tracks": len(eligible)}
    for name, expected in additions.items():
        if name in plan["cohorts"] and plan["cohorts"][name] != expected:
            raise ValueError(f"Frozen retrospective schedule differs: {name}")
    plan["cohorts"].update(additions)
    manifest.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    print(json.dumps({name: scope["tracks"] for name, scope in additions.items()}, sort_keys=True))


if __name__ == "__main__":
    main()
