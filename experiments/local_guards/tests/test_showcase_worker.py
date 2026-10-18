import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cascade_guard import live


@pytest.mark.asyncio
async def test_isolated_episode_passes_own_database_and_remaining_budget(tmp_path, monkeypatch):
    seen = []
    async def spawn(*argv, **kwargs):
        directory = Path(argv[-1])
        spec = json.loads((directory / "spec.json").read_text())
        seen.append(spec)
        (directory / "result.json").write_text(json.dumps({"record": {"case_id": "case"},
            "provider_request_count": 3, "halt_reason": None}))
        async def wait(): return 0
        return SimpleNamespace(wait=wait, returncode=0)
    monkeypatch.setattr(live.asyncio, "create_subprocess_exec", spawn)
    for index in range(2):
        record, attempts, halt = await live.isolated_showcase_episode(
            {"episode_timeout_seconds": 180}, {"case_id": "case"}, {"name": "NoDefense"},
            store=SimpleNamespace(root=tmp_path / "oauth"), proof_path=tmp_path / "proof.json",
            report={"ready": True}, directory=tmp_path / ("worker" + str(index)),
            database=tmp_path / ("episode" + str(index) + ".db"), maximum_requests=7)
        assert attempts == 3 and halt is None
    assert seen[0]["database"] != seen[1]["database"]
    assert all(spec["maximum_requests"] == 7 for spec in seen)


@pytest.mark.asyncio
async def test_isolated_worker_failure_is_not_retried(tmp_path, monkeypatch):
    calls = []
    async def spawn(*argv, **kwargs):
        calls.append(argv)
        async def wait(): return 1
        return SimpleNamespace(wait=wait, returncode=1)
    monkeypatch.setattr(live.asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(RuntimeError, match="reconcile"):
        await live.isolated_showcase_episode({"episode_timeout_seconds": 180}, {}, {},
            store=SimpleNamespace(root=tmp_path), proof_path=tmp_path / "proof.json", report={},
            directory=tmp_path / "worker", database=tmp_path / "episode.db", maximum_requests=7)
    assert len(calls) == 1
