"""Full per-run trace for the cascade-control probe.

A runner opens a recorder with `open_recorder()`; while none is open every
hook here is a no-op. Steps are appended in execution order, each with a
sequence number and a timestamp in milliseconds from the start of the run:

    llm             one LLM call: full input messages, tool names, output
    tool            one tool call: arguments, output, duration, error
    delegation      orchestrator -> agent: raw and enriched task text
    summary         an agent's task_status / task_summary as captured
    injection       a fault injected into the run (node, type, before/after)
    guard_context   what a control point saw (payload, DB snapshot)
    guard           one verifier verdict at a control point
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

_recorder: contextvars.ContextVar[RunRecorder | None] = contextvars.ContextVar(
    "probe_recorder", default=None
)


def _jsonable(value: Any) -> Any:
    """Round-trip through JSON so the trace never holds live objects."""
    return json.loads(json.dumps(value, default=str))


@dataclass
class RunRecorder:
    started: float = field(default_factory=time.perf_counter)
    steps: list[dict[str, Any]] = field(default_factory=list)
    tool_defs: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def now_ms(self) -> float:
        return round((time.perf_counter() - self.started) * 1000, 1)

    def add(self, kind: str, **fields: Any) -> dict[str, Any]:
        step = {"seq": len(self.steps), "kind": kind, "t_ms": self.now_ms()}
        step.update(_jsonable(fields))
        self.steps.append(step)
        return step

    def register_tools(self, tools: list[dict[str, Any]] | None) -> str | None:
        if not tools:
            return None
        canonical = json.dumps(tools, sort_keys=True, default=str)
        sha = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        self.tool_defs.setdefault(sha, _jsonable(tools))
        return sha


def active_recorder() -> RunRecorder | None:
    return _recorder.get()


@contextlib.contextmanager
def open_recorder() -> Iterator[RunRecorder]:
    recorder = RunRecorder()
    token = _recorder.set(recorder)
    try:
        yield recorder
    finally:
        _recorder.reset(token)


def record_llm(
    agent: str,
    request: Any,
    response: Any | None,
    started_ms: float,
    model: str | None,
    temperature: float | None,
    error: str | None = None,
) -> None:
    recorder = _recorder.get()
    if recorder is None:
        return
    tools = request.tools or []
    output = None
    usage = None
    served_model = None
    if response is not None:
        output = {"content": response.content, "tool_calls": response.tool_calls}
        metadata = response.metadata or {}
        usage = metadata.get("usage")
        served_model = metadata.get("model")
        if not response.success and error is None:
            error = response.content
    recorder.add(
        "llm",
        agent=agent,
        t_start_ms=started_ms,
        duration_ms=round(recorder.now_ms() - started_ms, 1),
        model=model,
        served_model=served_model,
        temperature=temperature,
        messages=request.messages or [],
        tools=[t.get("name") for t in tools],
        tools_sha=recorder.register_tools(tools),
        output=output,
        usage=usage,
        error=error,
    )


def record_tool(
    agent: str,
    name: str,
    source: str,
    arguments: Any,
    output: Any,
    started_ms: float,
    error: str | None = None,
) -> None:
    recorder = _recorder.get()
    if recorder is None:
        return
    recorder.add(
        "tool",
        agent=agent,
        name=name,
        source=source,
        arguments=arguments,
        output=output,
        t_start_ms=started_ms,
        duration_ms=round(recorder.now_ms() - started_ms, 1),
        error=error,
    )


def record(kind: str, **fields: Any) -> None:
    recorder = _recorder.get()
    if recorder is not None:
        recorder.add(kind, **fields)


def now_ms() -> float:
    recorder = _recorder.get()
    return recorder.now_ms() if recorder is not None else 0.0
