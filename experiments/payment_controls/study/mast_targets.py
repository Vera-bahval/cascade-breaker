"""Audit prospective MAST risk targets without opening closed execution results.

The risk is incorrect verification of a known contractual gate (3.3), or failure
to clarify missing decisive evidence (2.2). These are not observed mistakes.
Creator NONE/none is preserved as an absent risk annotation, never silently
interpreted as evidence that the scenario has no verification risk.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


OUTCOMES = {"ALLOW": "pay", "BLOCK": "stop", "REVIEW": "review"}
ALIASES = {"none": "NONE", "no_failure": "NONE", "no_mast": "NONE",
           "payment_control_violation": "3.3", "incorrect_verification": "3.3",
           "insufficient_evidence": "2.2", "fail_to_ask_for_clarification": "2.2"}
STANDARD = {"1.1", "1.2", "1.3", "1.4", "1.5", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "3.1", "3.2", "3.3"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def code(value):
    if not isinstance(value, str):
        raise ValueError("MAST code must be one explicit string")
    normalized = value.strip().casefold().replace("-", "_").replace(" ", "_")
    if normalized in STANDARD:
        return normalized
    if normalized in ALIASES:
        return ALIASES[normalized]
    raise ValueError("Unknown MAST lexical variant needs curator review")


def write(path, content, private):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content)
    if private:
        temporary.chmod(0o600)
    temporary.replace(path)


def build(args):
    assert code(" NONE ") == "NONE"
    assert code("insufficient-evidence") == "2.2"
    assert code("payment_control_violation") == "3.3"
    corpus = json.loads((args.corpus / "manifest.json").read_text())
    required = ("inputs.jsonl", "inputs.p80_64.jsonl", "inputs.test.jsonl",
                "inputs.cal.jsonl", "gold.private.jsonl", "schedule.cal.csv", "schedule.p80_64.csv")
    before = {name: sha(args.corpus / name) for name in required}
    for name, digest in before.items():
        if corpus["private_artifacts_sha256"][name] != digest:
            raise ValueError("Frozen corpus artifact changed")
    references = rows(args.corpus / "gold.private.jsonl")
    if len(references) != 160 or len({row["case"] for row in references}) != 160:
        raise ValueError("Expected exactly160 admitted references")
    reconciliation = {row["case"]: row for row in rows(args.corpus / "reference_audit.private.jsonl")}
    source_files = {}
    source_cases = {}
    labels = {}
    for bank in corpus["source_banks"]:
        folder = args.banks_root / bank
        paths = [folder / "gold.jsonl", *sorted(folder.glob("ratings_*.jsonl"))]
        case_path = folder / "cases.jsonl"
        for path in [case_path, *paths]:
            name = bank + "/" + path.name
            if corpus["source_sha256"].get(name) != sha(path):
                raise ValueError("Creator/independent source version changed")
            source_files[name] = sha(path)
        source_cases[bank] = {row["family"]: row for row in rows(case_path)}
        labels[bank] = {path.name: {row["family"]: row for row in rows(path)} for path in paths}
    distributions = defaultdict(Counter)
    agreement = defaultdict(Counter)
    risk_counts = Counter()
    targets = []
    resolved_numeric_disagreements = 0
    absent_creator_risk_annotations = 0
    for reference in references:
        case = reference["case"]
        if reference["outcome"] != OUTCOMES[reference["step"]]:
            raise ValueError("Admitted reference step/outcome mismatch")
        bank, family = reference["source_bank"], reference["source_family"]
        source = source_cases[bank][family]
        if not all(isinstance(source.get(field), str) and source[field].strip()
                   for field in ("policy", "basis", "record")):
            raise ValueError("Missing original contract/evidence")
        target = "2.2" if reference["step"] == "REVIEW" else "3.3"
        risk_counts[target] += 1
        reviewer_codes = {}
        for name, table in labels[bank].items():
            annotation = table[family]
            raw = annotation["mast"]
            normalized = code(raw)
            origin = "creator" if name == "gold.jsonl" else name.removesuffix(".jsonl")
            distributions[origin][raw] += 1
            agrees = normalized == target
            if normalized == "NONE":
                # No executor observation exists here; NONE cannot erase the
                # prospective verification/clarification risk in the contract.
                resolution = "axis_resolution_absent_creator_risk"
                absent_creator_risk_annotations += int(origin == "creator")
                agreement[origin]["none_or_absent_risk_axis"] += 1
            elif agrees:
                resolution = "agrees_on_target_risk"
                agreement[origin]["agrees_on_target_risk"] += 1
            else:
                # A numeric-code difference must already have a documented
                # evidence adjudication, not an inference-driven label repair.
                audit = reconciliation[case]
                if not audit["explicit_reconciliation"] or not reference["evidence"]:
                    raise ValueError("Unresolved target-risk disagreement")
                resolution = "explicit_primary_evidence_adjudication"
                resolved_numeric_disagreements += 1
                agreement[origin]["explicitly_reconciled_target_risk"] += 1
            reviewer_codes[origin] = {"raw": raw, "normalized": normalized,
                                      "resolution": resolution}
        reason = (
            "Prospective target only; no observed executor error is asserted. "
            + ("Decisive evidence for the contractual gate is incomplete; acting without clarification is the 2.2 risk. "
               if target == "2.2" else
               "The contract and supplied primary record permit verifying the gate; an incorrect conclusion is the 3.3 risk, including on a valid control. ")
            + "Curator evidence: " + reference["evidence"]
            + " Original contract: " + source["policy"])
        targets.append({"case": case, "target_mast": target, "reason": reason,
                        "reviewer_codes": reviewer_codes})
    targets.sort(key=lambda row: row["case"])
    encoded = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in targets)
    private = args.corpus / "mast_targets.private.jsonl"
    write(private, encoded, True)
    after = {name: sha(args.corpus / name) for name in required}
    if before != after:
        raise ValueError("MAST audit modified a frozen artifact")
    manifest = {"version": 1, "candidate_id": corpus["candidates"]["p80_64"]["candidate_id"],
                "accepted_cases": len(targets), "covered_cases": len(targets), "unresolved_cases": 0,
                "axis": "prospective_contractual_target_risk", "observed_mistakes_asserted": False,
                "closed_run_results_read": False, "new_inference_calls": 0,
                "target_mast_counts": dict(risk_counts),
                "creator_and_independent_raw_codes": dict(distributions),
                "target_risk_agreement_by_source": dict(agreement),
                "absent_creator_risk_annotations_resolved_by_axis": absent_creator_risk_annotations,
                "numeric_source_target_differences_explicitly_reconciled": resolved_numeric_disagreements,
                "private_file": private.name, "private_sha256": sha(private),
                "source_sha256": source_files, "frozen_corpus_artifacts_sha256": before,
                "frozen_corpus_unchanged": True, "builder_sha256": sha(Path(__file__)),
                "limitations": ["Targets cover contractual verification and missing evidence, not all 14 MAST modes.",
                                "NONE on a creator reference is not an observed no-error result and does not negate target risk.",
                                "No model/run outcome was used to choose or repair these targets."]}
    write(args.manifest, json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", False)
    print(json.dumps({"accepted_cases": len(targets), "unresolved_cases": 0,
                      "frozen_corpus_unchanged": True, "private_sha256": sha(private)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--banks-root", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    build(parser.parse_args())
