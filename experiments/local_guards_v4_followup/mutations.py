"""Five fixed faulty evaluators; prediction never opens labels or model files.

Mutations compile private function copies. Target/frozen modules and observations
are never patched. This module is research instrumentation, not a guard method.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import nullcontext
import gzip
import hashlib
import json
from pathlib import Path
from types import FunctionType

from experiments.local_guards_v4_followup import guard as target

HERE = Path(__file__).resolve().parent
MUTANTS = ("no_currency", "human_every_amount", "no_hold", "unknown_first",
           "no_origin_parent_binding")


def _has(node, value):
    return any(isinstance(n, ast.Constant) and n.value == value for n in ast.walk(node))


def _assigned(node, name):
    return isinstance(node, ast.Assign) and any(
        isinstance(n, ast.Name) and n.id == name for n in node.targets)


class _Mutation(ast.NodeTransformer):
    def __init__(self, name, layer):
        self.name, self.layer = name, layer

    def visit_Assign(self, node):
        self.generic_visit(node)
        if self.layer == "v3":
            if self.name == "no_hold" and _assigned(node, "hold"):
                node.value = ast.Constant(False)
            if (self.name in {"no_currency", "no_hold"} and _assigned(node, "missing")
                    and isinstance(node.value, ast.ListComp)):
                omitted = "invoice_currency" if self.name == "no_currency" else "binding_hold"
                node.value.generators[0].ifs.append(ast.Compare(
                    ast.Name("key", ast.Load()), [ast.NotEq()], [ast.Constant(omitted)]))
        if (self.layer == "core" and self.name == "unknown_first"
                and _assigned(node, "decision")):
            node.value = ast.parse("'UNKNOWN' if 'unknown' in states else 'BLOCK' if 'violated' in states else 'ALLOW'", mode="eval").body
        if (self.layer == "origin" and _assigned(node, "valid")
                and any(isinstance(n, ast.Name) and n.id == "origin_valid" for n in ast.walk(node))):
            node.value = ast.parse("bool(newest)", mode="eval").body
        return node

    def visit_Compare(self, node):
        self.generic_visit(node)
        if (self.layer == "v3" and self.name == "human_every_amount"
                and isinstance(node.left, ast.Name) and node.left.id == "invoice"
                and len(node.ops) == 1 and isinstance(node.ops[0], ast.Gt)
                and isinstance(node.comparators[0], ast.Name)
                and node.comparators[0].id == "automatic"):
            return ast.Constant(True)
        return node

    def visit_If(self, node):
        self.generic_visit(node)
        if self.layer == "v3" and self.name == "no_currency":
            if any(_has(part, "policy_currency_required") or _has(part, "proposal.currency") for part in node.body):
                return None
        if (self.layer == "v3" and self.name == "unknown_first"
                and isinstance(node.test, ast.Name) and node.test.id == "blocked"
                and len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If)
                and isinstance(node.orelse[0].test, ast.Name)
                and node.orelse[0].test.id == "missing"):
            following = node.orelse[0]
            return ast.If(test=following.test, body=following.body,
                          orelse=[ast.If(test=node.test, body=node.body, orelse=following.orelse)])
        if self.layer == "origin" and _has(node.test, "delegation_subject_matches"):
            return None
        return node

    def visit_Expr(self, node):
        self.generic_visit(node)
        if (self.layer == "core" and self.name == "no_hold"
                and _has(node, "binding_hold") and _has(node, "human_cleared")):
            return None
        return node

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        if self.layer == "core" and self.name == "unknown_first" and node.name == "combine":
            node.body = [ast.Return(ast.parse("'unknown' if 'unknown' in states else 'violated' if 'violated' in states else 'satisfied'", mode="eval").body)]
        return node

    def visit_Subscript(self, node):
        self.generic_visit(node)
        if self.layer == "origin" and isinstance(node.slice, ast.Constant) and node.slice.value == "evidence_kind":
            # Missing legacy origin is intentionally accepted by this mutant.
            return ast.Call(ast.Attribute(node.value, "get", ast.Load()), [node.slice], [])
        return node


def _compile(path, function, namespace, mutation, layer):
    tree = ast.parse(path.read_text(), filename=str(path))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
    node = _Mutation(mutation, layer).visit(node)
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[function]


def mutate_guard(name):
    """Return the real guard control flow with one named faulty behavior."""
    if name not in MUTANTS:
        raise ValueError("unknown mutation: " + str(name))
    namespace = dict(target.guard.__globals__)
    legacy = dict(namespace["_v3"])
    for key, value in list(legacy.items()):
        if isinstance(value, FunctionType):
            legacy[key] = FunctionType(value.__code__, legacy, value.__name__, value.__defaults__)
    namespace["_v3"] = legacy
    if name != "no_origin_parent_binding":
        _compile(target.frozen._V3_PATH, "_evaluate", legacy, name, "v3")
        if name == "unknown_first":
            _compile(target.frozen._V3_PATH, "guard", legacy, name, "v3")
    else:
        origin_namespace = dict(vars(target))
        namespace["_proofs"] = _compile(HERE / "guard.py", "_proofs", origin_namespace, name, "origin")
    return _compile(Path(target.frozen.__file__), "guard", namespace, name, "core")


def configurations(profile="A"):
    if profile not in {"A", "B"}:
        raise ValueError("profile must be A or B")
    return [dict(name="v42_mutant_" + name + "_" + profile, mutation=name,
                 kind="v42_mutant", points=["P0", "P1", "P2", "P3", "P4"],
                 requirements=list(target._REGISTRY["profiles"][profile]), payment_only=False)
            for name in MUTANTS]


def predict_rows(observations, profile="A", metadata=None):
    """Read only prefix identity and observation; no expected answer is consulted."""
    from experiments.local_guards_v4_followup.evaluate import routing_envelope
    identities = [row["prefix_id"] for row in observations]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate prefix_id")
    meta = {} if metadata is None else {row["prefix_id"]: row for row in metadata}
    if metadata is not None and (len(meta) != len(metadata) or set(meta) != set(identities)):
        raise ValueError("observation/metadata coverage mismatch or duplicates")
    envelopes = {row["prefix_id"]: routing_envelope(row, meta.get(row["prefix_id"], {}))
                 for row in observations}
    predictions = []
    for config in configurations(profile):
        guard = mutate_guard(config["mutation"])
        for row in observations:
            obj = row["observation"]
            envelope = envelopes[row["prefix_id"]]
            cp, seq = envelope["checkpoint"], envelope["event_seq"]
            checked = cp in config["points"]
            result = guard(obj, profile) if checked else dict(decision=None, stop=False, reasons=[], requirements=[])
            proposal = obj.get("proposal") if isinstance(obj, dict) else None
            predictions.append(dict(prefix_id=row["prefix_id"], method=config["name"],
                checkpoint=cp, event_seq=seq, tool=proposal.get("tool") if isinstance(proposal, dict) else None,
                metadata_routing_fallback=envelope["metadata_fallback_fields"],
                checked=checked, eligible=checked, routing="v42_mutant" if checked else "no_check",
                **{k: v for k, v in result.items() if k not in {"evidence", "timing_ms"}}))
    return predictions


def _digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, help="Optional canonical identity/routing metadata; never labels")
    parser.add_argument("--profile", choices=("A", "B"), default="A")
    args = parser.parse_args()
    if args.predictions.exists() or args.receipt.exists():
        parser.error("predictions and receipt must be new paths")
    with (gzip.open(args.observations, "rt") if args.observations.suffix == ".gz" else args.observations.open()) as stream:
        observations = [json.loads(line) for line in stream if line.strip()]
    metadata = None
    if args.metadata is not None:
        with (gzip.open(args.metadata, "rt") if args.metadata.suffix == ".gz" else args.metadata.open()) as stream:
            metadata = [json.loads(line) for line in stream if line.strip()]
    sources = [Path(__file__), HERE / "guard.py", HERE / "schema.json", HERE / "policy.json",
               HERE / "evaluate.py", Path(target.frozen.__file__), target.frozen._V3_PATH,
               Path(target.frozen.__file__).with_name("schema.json"),
               Path(target.frozen.__file__).with_name("policy.json")]
    source_hashes = {str(path): _digest(path) for path in sources}
    input_hashes = {str(path): _digest(path) for path in (args.observations, args.metadata) if path is not None}
    predictions = predict_rows(observations, args.profile, metadata)
    args.predictions.parent.mkdir(parents=True, exist_ok=True)
    with args.predictions.open("xb") as raw:
        with (gzip.GzipFile(fileobj=raw, filename="", mode="wb", mtime=0) if args.predictions.suffix == ".gz" else nullcontext(raw)) as stream:
            for row in predictions:
                stream.write((json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode())
    if any(_digest(path) != expected for path, expected in {**source_hashes, **input_hashes}.items()):
        raise ValueError("mutation source or input changed during prediction; receipt withheld")
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x") as stream:
        json.dump(dict(version="v4.2-mutations", profile=args.profile,
            methods=configurations(args.profile), observations_sha256=_digest(args.observations),
            predictions_sha256=_digest(args.predictions), prediction_rows=len(predictions),
            sources=source_hashes, inputs=input_hashes, gold_opened=False,
            new_inference=False, fit_called=False), stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
