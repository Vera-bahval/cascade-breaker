"""Check scenario files against scenarios/schema.json and the references the schema cannot express."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schema.json").read_text(encoding="utf-8"))
PLACEHOLDER = re.compile(r"\{([A-Za-z0-9_]+)\}")


def _validator(definition: str) -> Draft202012Validator:
    return Draft202012Validator({**SCHEMA, "$ref": f"#/$defs/{definition}"})


VALIDATORS = {name: _validator(name) for name in ("scenario", "simple_case", "base_list", "additions_list")}


def schema_errors(data: Any, definition: str) -> list[str]:
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in VALIDATORS[definition].iter_errors(data)]


def reference_errors(case: dict[str, Any]) -> list[str]:
    """Every invoice and file a scenario names must be created in its setup or trigger."""
    setup = case.get("setup") or {}
    trigger = case["trigger"]
    invoices = {spec["ref"] for spec in setup.get("invoices") or []}
    if trigger.get("kind") == "invoice":
        invoices.add("T")
    files = {spec["ref"] for spec in setup.get("files") or []}
    turns = [*(setup.get("prepare_turns") or []), *(setup.get("prepare_turns_after_filler") or []),
             *(trigger.get("turns") or [])]
    named = {ref for turn in turns for ref in PLACEHOLDER.findall(turn["message"])}
    named |= {ref for spec in setup.get("files") or [] for ref in PLACEHOLDER.findall(spec["text"])}
    checks = [*(case.get("precondition") or {}).get("checks", []), *case["oracle"]["checks"]]
    named |= {check["invoice"] for check in checks if "invoice" in check}
    named |= {edit["ref"] for edit in setup.get("edits") or [] if edit["target"] == "invoice"}
    attached = {a["ref"] for turn in turns for a in turn.get("attachments") or []}
    errors = [f"invoice {ref} is used but never created" for ref in sorted(named - invoices)]
    errors += [f"file {ref} is attached but never uploaded" for ref in sorted(attached - files)]
    if "direct" in (case["via"] if isinstance(case["via"], list) else [case["via"]]):
        if trigger.get("kind") != "invoice" or "profile" not in setup:
            errors.append("via direct runs invoice cases with a vendor profile only")
    return errors


def check_all() -> list[str]:
    """Every scenario file and list in scenarios/; returns readable errors, empty when all is well."""
    from runner import mast_mode

    errors: list[str] = []
    ids: dict[str, str] = {}

    def scenario(case: Any, where: str) -> None:
        found = schema_errors(case, "scenario")
        if not found:
            found = reference_errors(case)
            if case["id"] in ids:
                found.append(f"id {case['id']} repeats {ids[case['id']]}")
            ids[case["id"]] = where
        errors.extend(f"{where}: {e}" for e in found)

    for path in mast_mode.mast_paths():
        case = mast_mode.read_json(path)
        scenario(case, path.name)
        if case.get("id") != path.stem:
            errors.append(f"{path.name}: id {case.get('id')} does not match the file name")
    for path in sorted(mast_mode.SUITES_DIR.glob("*.json")):
        for n, case in enumerate(mast_mode.read_json(path)):
            scenario(case, f"suites/{path.name}[{n}]")
    for path in sorted((ROOT / "cases").glob("*.json")):
        errors.extend(f"cases/{path.name}: {e}" for e in schema_errors(mast_mode.read_json(path), "simple_case"))
    for name, definition in (("base.json", "base_list"), ("api_additions.json", "additions_list")):
        data = mast_mode.read_json(mast_mode.UNIFIED_DIR / name)
        found = schema_errors(data, definition)
        if not found:
            named = ([n for m in data["modes"] for n in (m["scenario"], m["positive"])] if name == "base.json"
                     else [f"{p}_{v}" for m in data["modes"] for p in m["pairs"] + m["cross_workflow"] for v in "np"])
            found = [f"{n} is not a scenario" for n in named if n not in ids]
        errors.extend(f"unified/{name}: {e}" for e in found)
    additions = mast_mode.read_json(mast_mode.UNIFIED_DIR / "api_additions.json")
    excluded = set((additions.get("excluded") or {}).get("pairs", []))
    used = {p for m in additions["modes"] for p in m["pairs"]}
    used |= {n.split("_")[0] for m in mast_mode.read_json(mast_mode.UNIFIED_DIR / "base.json")["modes"]
             for n in (m["scenario"], m["positive"]) if "@" not in n}
    errors.extend(f"unified: excluded pair {p} is still used" for p in sorted(excluded & used))
    return errors
