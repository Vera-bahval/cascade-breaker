"""Single authorized showcase episode in a fresh SQLite worker process."""
import asyncio
import json
import sys
from pathlib import Path

from .harness import initialize, run_episode, write_record
from .live import SemanticGuard, showcase_permit
from .ml import FrozenSemanticStackDetector
from .oauth import OAuthStore
from .transport import SIWCClient


async def execute(directory):
    spec = json.loads((directory / "spec.json").read_text())
    config, arm = spec["config"], spec["arm"]
    initialize(Path(spec["database"]))
    store = OAuthStore(Path(spec["runtime"]))
    client = SIWCClient(store, model="gpt-6-luna",
        permit=showcase_permit(store, spec["report"], Path(spec["proof_path"])),
        max_requests=spec["maximum_requests"],
        max_generated_characters=config["max_generated_characters_per_request"],
        reasoning_effort=config["reasoning_effort"],
        event_sink=lambda event: write_record(directory / "stream-diagnostics.jsonl", event))
    client.start_episode(spec["maximum_requests"])
    detectors = {} if arm["name"] == "NoDefense" else {
        arm["name"]: SemanticGuard(config["secjev_url"], FrozenSemanticStackDetector(Path(config["semantic_artifact_dir"]))) }
    try:
        record = await run_episode(spec["scenario"], client=client, detectors=detectors,
            placement=arm["placement"], mode=arm["mode"], questions=config["questions"],
            timeout_seconds=config["episode_timeout_seconds"])
        record["database_file"] = Path(spec["database"]).name
        (directory / "result.json").write_text(json.dumps({"record": record,
            "provider_request_count": client.request_count, "halt_reason": client.halt_reason}))
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(execute(Path(sys.argv[1])))
