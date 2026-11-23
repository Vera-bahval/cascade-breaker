"""Prepare and verify blinded finale rubrics over the signed local roster."""
import argparse
import json
import os
import re
from pathlib import Path
from unittest.mock import patch

from ... import live, live_review, live_review_conditioned
from ...extension import partial_review, review
from ...v2 import adjudicated
from ...v2 import review as v2_review
from . import actions, risk_evidence

PRIVATE = live.ROOT / ".runtime/payment-controls-chp3/final-study-payment-finale"
output = live_review.output
base_builder = live_review_conditioned.conditioned_builder
base_signature = live_review_conditioned.judgment_signature
base_episode_id = live.episode_id


def approved(private):
    path = private / "freeze.json"
    freeze = live.read(path)
    release = live.read(private / "release.json")
    if release != {"freeze_sha256": live.digest(path), "reviewer": "root", "approved": True}:
        raise ValueError("Exact finale freeze requires root release")
    for filename, digest in freeze["files"].items():
        if live.digest(Path(filename)) != digest:
            raise ValueError("Frozen finale dependency changed: " + filename)
    return freeze


def clean(value):
    if isinstance(value, str):
        return re.sub(r'(?i)(?:"?finale_stop"?\s*[:=]\s*["\']?P[14]["\']?|\[pre-Fraud route\])',
                      "[internal routing marker withheld]", value)
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean(item) for item in value]
    return value


def sanitized_output(path, rows):
    output(path, (clean(row) for row in rows))


def with_actions(freeze):
    builder = base_builder(freeze)

    def build(dest, key, episode, source):
        packet = builder(dest, key, episode, source)
        packet["candidate_actions"] = list(actions.project(dest, episode))
        packet["independent_review_evidence"] = list(risk_evidence.project(dest, episode))
        packet["procedure_criterion"] = "scoped_independent_duties_regardless_of_executor"
        return packet

    return build


def signature(row, packet):
    return base_signature(row, packet) + (actions.signature(row, packet),)


def prepare(freeze, original, wave, limit, *, partial):
    with patch.object(live_review, "output", sanitized_output):
        if partial:
            with patch.object(live_review, "FIELDS", live_review.FIELDS | review.PROFILE_FIELDS):
                return partial_review.prepare(PRIVATE, freeze, wave, limit)
        with patch.object(live_review_conditioned, "conditioned_builder", with_actions):
            return review.prepare(PRIVATE, freeze, original, wave, limit)


def prior_closure_groups(freeze, *, duties=False):
    previous = set()
    for wave in (PRIVATE / "blind").glob("wave-*"):
        source = live_review.jsonl(wave / "packets.jsonl")
        for key, mapping in live_review.jsonl(wave / "mapping.jsonl").items():
            field = "procedure_criterion" if duties else "independent_review_evidence"
            if not mapping.get("partial") and field not in source[key]:
                previous.add((mapping["cell"], mapping["arm"]))
    groups = []
    for item in freeze["groups"]:
        cell = item["cell"]
        arms = []
        for arm in item["arms"]:
            if (cell["key"], arm) not in previous:
                continue
            dest = PRIVATE / "test" / live.episode_id(cell, arm)
            if any(row["action"] in {"CLOSE_ALLOW", "CLOSE_STOP"} for _, row in risk_evidence.receipts(dest)):
                arms.append(arm)
        if arms:
            groups.append({**item, "arms": arms})
    return {**freeze, "groups": groups}


def retry_id(cell, arm):
    return base_episode_id(cell, arm) + ".retry-1"


def run(mode, wave, limit, support=False, duties=False, retry=False):
    freeze = approved(PRIVATE)
    if (support or duties) and mode == "prepare":
        freeze = prior_closure_groups(freeze, duties=duties)
    folder = PRIVATE / ("blind-technical-retries" if retry else "blind-mandatory-duties" if duties
                        else "blind-structured-review" if support else "blind")
    original = live.approved() if mode == "prepare" else None
    with patch.object(live, "PRIVATE", PRIVATE), patch.object(live_review, "REVIEW", folder), \
            patch.object(live_review_conditioned, "judgment_signature", signature), \
            patch.object(live, "episode_id", retry_id if retry else base_episode_id):
        if mode in {"prepare", "partials"}:
            return prepare(freeze, original, wave, limit, partial=mode == "partials")
        if mode == "verify":
            with patch.object(v2_review, "REVIEW", folder):
                grades, waves = adjudicated.verified_waves()
            return {"grades": len(grades), "waves": waves}
        if (folder / wave / "gold-manifest.json").exists():
            raise FileExistsError(f"Refusing to change sealed wave {wave}")
        if mode == "audit":
            out = live_review_conditioned.audit_wave("audit", folder / wave)
            with patch.object(live_review, "output", sanitized_output):
                review.audit_chat(folder / wave, PRIVATE, freeze)
            return out
        chat = folder / wave / "auditor-chat.jsonl"
        if chat.is_file() and live.digest(chat) != chat.with_suffix(".sha256").read_text().strip():
            raise ValueError("Auditor chat supplement changed")
        out = live_review_conditioned.audit_wave("finalize", folder / wave)
        if chat.is_file():
            manifest = folder / wave / "gold-manifest.json"
            live.write(manifest, {**live.read(manifest), chat.name: live.digest(chat)})
        return out


def main():
    global PRIVATE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "partials", "audit", "finalize", "verify"))
    parser.add_argument("wave", nargs="?")
    parser.add_argument("--limit", type=int, default=16)
    context = parser.add_mutually_exclusive_group()
    context.add_argument("--support", action="store_true")
    context.add_argument("--duties", action="store_true")
    context.add_argument("--retry", action="store_true")
    parser.add_argument("--private", type=Path, default=PRIVATE)
    args = parser.parse_args()
    if args.mode not in {"verify"} and (not args.wave or not args.wave.startswith("wave-")
                                                 or not args.wave[5:].isdigit() or args.limit < 1):
        parser.error("Expected wave-N and positive size")
    os.umask(0o077)
    PRIVATE = args.private.resolve()
    print(json.dumps(run(args.mode, args.wave, args.limit, args.support, args.duties, args.retry), ensure_ascii=False))


if __name__ == "__main__":
    main()
