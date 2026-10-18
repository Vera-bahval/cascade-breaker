"""Replay the pinned independent count algorithm into a NEW output file."""
from pathlib import Path
import argparse
import ast
import hashlib
import json

EXPECTED = "e9d00c181f4d3fd0c16b9b2108dd2ef4f9c3c5edfa4f493b191b856ef7fe4910"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Choose a new output; existing artifacts are never replaced")
    source = Path(__file__).with_name("audit_guard_v2_final_recount_05.py")
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError("Independent recount source changed")
    # The reviewed algorithm ends before its exclusive publication statements.
    # Execute every check; omit only that original output-publication tail.
    marker = "\nfor suffix in ('json','md'):"
    text = data.decode("utf-8")
    if text.count(marker) != 1:
        raise ValueError("Unexpected publication boundary")
    algorithm = text.partition(marker)[0]
    ast.parse(algorithm)
    namespace = {"__name__": "__guard_v2_recount_replay__", "__file__": str(source)}
    exec(compile(algorithm, str(source), "exec"), namespace)
    result = namespace["result"]
    if result["status"] != "PASS_EXACT_RECOUNT":
        raise ValueError("Recount did not finish")
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
