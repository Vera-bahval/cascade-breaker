"""Official SIWC public Responses transport; tool execution waits for completion."""
from __future__ import annotations

import asyncio
import copy
import json
import hashlib
from dataclasses import dataclass
from dataclasses import asdict
from typing import Any, Callable

import httpx

from .oauth import OAuthStore, RESOURCE


class TransportError(RuntimeError):
    pass


def diagnostic_event(event: dict) -> dict:
    """Allowlisted stream structure; never persist model text or opaque state."""
    result = {key: event[key] for key in ("type", "sequence_number", "output_index", "content_index") if key in event}
    for field in ("delta", "text", "arguments"):
        if isinstance(event.get(field), str):
            result[field + "_characters"] = len(event[field])
            result[field + "_sha256"] = hashlib.sha256(event[field].encode()).hexdigest()
    item = event.get("item")
    if isinstance(item, dict):
        result["item"] = {key: item[key] for key in ("type", "status", "namespace", "name", "role", "phase") if key in item}
        for field in ("arguments", "encrypted_content"):
            if isinstance(item.get(field), str):
                result["item"][field + "_characters"] = len(item[field])
                result["item"][field + "_sha256"] = hashlib.sha256(item[field].encode()).hexdigest()
        result["item"]["content_types"] = [part.get("type") for part in item.get("content", []) if isinstance(part, dict)]
    response = event.get("response")
    if isinstance(response, dict):
        result["response"] = {key: response[key] for key in ("status", "model", "usage") if key in response}
        result["response"]["output_item_count"] = len(response.get("output", []))
    return result


@dataclass
class CompletedResponse:
    content: str
    tool_calls: list[dict]
    messages: list[dict]
    metadata: dict
    success: bool = True
    provider: str = "openai"

    def model_dump_json(self):
        return json.dumps(asdict(self))


def request_payload(request: Any, model: str) -> dict:
    history = copy.deepcopy(request.messages or [])
    for item in history:
        if item.get("role") == "system":
            item["role"] = "developer"
    payload = {"model": request.model or model, "input": history, "store": False, "stream": True}
    if request.tools:
        if any(tool.get("type") != "function" for tool in request.tools):
            raise TransportError("Only client-executed function tools are supported")
        payload["tools"] = [{"type": "namespace", "name": "finbot",
                             "description": "Local simulated FinBot research tools.",
                             "tools": copy.deepcopy(request.tools)}]
    schema = getattr(request, "output_json_schema", None)
    if schema:
        payload["text"] = {"format": {"type": "json_schema", "name": schema["name"],
                                         "schema": schema["schema"], "strict": True}}
    # Explicit allowlist above omits all unsupported preview fields, including
    # temperature, max_output_tokens, metadata and previous_response_id.
    return payload


def completed_response(response: dict, request: Any, selected_model: str) -> CompletedResponse:
    if not isinstance(response, dict) or response.get("status") != "completed" or not isinstance(response.get("output"), list):
        raise TransportError("Terminal response is not completed")
    served = response.get("model")
    if served != selected_model:
        raise TransportError("Served model differs from the explicitly selected model")
    texts, calls = [], []
    call_ids = set()
    tool_names = {t["name"] for t in (request.tools or [])}
    for item in response["output"]:
        if not isinstance(item, dict) or item.get("type") not in {"reasoning", "message", "function_call"}:
            raise TransportError("Unexpected completed output item")
        if item.get("type") == "message":
            if not isinstance(item.get("content"), list) or any(not isinstance(part, dict) for part in item["content"]):
                raise TransportError("Malformed completed message")
            if any(part.get("type") == "refusal" for part in item.get("content", [])):
                raise TransportError("Model refused the request")
            if any(not isinstance(part.get("text"), str) for part in item["content"] if part.get("type") == "output_text"):
                raise TransportError("Malformed completed text")
            texts.extend(part["text"] for part in item.get("content", []) if part.get("type") == "output_text")
        elif item.get("type") == "function_call":
            name = item.get("name", "")
            if name.startswith("finbot."):
                name = name[len("finbot."):]
            if name not in tool_names or item.get("namespace") not in {None, "finbot"}:
                raise TransportError("Model returned an unavailable tool")
            try:
                args = json.loads(item["arguments"])
            except (ValueError, KeyError, TypeError):
                raise TransportError("Malformed function arguments") from None
            if not isinstance(args, dict) or not isinstance(item.get("call_id"), str) or not item["call_id"] or item["call_id"] in call_ids:
                raise TransportError("Invalid function call")
            call_ids.add(item["call_id"])
            calls.append({"name": name, "call_id": item["call_id"], "arguments": args})
    # Keep every output item intact, including encrypted_content and phase.
    messages = copy.deepcopy(request.messages or []) + copy.deepcopy(response["output"])
    return CompletedResponse("".join(texts), calls, messages,
                             {"response_id": response.get("id"), "model": served or selected_model,
                              "usage": response.get("usage", {}), "status": "completed",
                              "transport": "siwc_public_responses", "cost_usd": None})


async def sse_events(lines):
    data: list[str] = []
    async for line in lines:
        if line == "":
            if data:
                value = "\n".join(data)
                data = []
                if value != "[DONE]":
                    try:
                        yield json.loads(value)
                    except ValueError:
                        raise TransportError("Malformed SSE event") from None
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())
    if data:
        raise TransportError("Interrupted SSE frame")


class OutputItems:
    """Collect completed SSE items; release them only after response.completed.

    The public SIWC route may leave the terminal output array empty. The done
    item also carries the final encrypted reasoning, unlike the added item.
    """
    def __init__(self):
        self.added, self.done, self.arguments, self.event_counts = {}, {}, {}, {}

    def observe(self, event):
        kind = event.get("type")
        self.event_counts[kind] = self.event_counts.get(kind, 0) + 1
        if kind in {"response.output_item.added", "response.output_item.done"}:
            index, item = event.get("output_index"), event.get("item")
            if not isinstance(index, int) or isinstance(index, bool) or index < 0 or not isinstance(item, dict):
                raise TransportError("Malformed SSE output item")
            target = self.added if kind.endswith("added") else self.done
            if index in target:
                raise TransportError("Duplicate SSE output item")
            if kind.endswith("done") and item.get("status") not in {None, "completed"}:
                raise TransportError("SSE output item is not completed")
            target[index] = copy.deepcopy(item)
        elif kind == "response.function_call_arguments.delta":
            index = event.get("output_index")
            if isinstance(index, int) and not isinstance(index, bool):
                if not isinstance(event.get("delta"), str):
                    raise TransportError("Malformed SSE argument delta")
                self.arguments[index] = self.arguments.get(index, "") + event["delta"]

    def assemble(self, final):
        if not isinstance(final, dict) or not isinstance(final.get("output"), list):
            raise TransportError("Malformed terminal output array")
        original_count = len(final["output"])
        final = copy.deepcopy(final)
        if self.done:
            if set(self.done) != set(range(len(self.done))) or set(self.added) - self.done.keys():
                raise TransportError("Incomplete SSE output item sequence")
            for index, item in self.done.items():
                added = self.added.get(index)
                if added and (added.get("id") != item.get("id") or added.get("type") != item.get("type")):
                    raise TransportError("SSE output item identity changed")
                if index in self.arguments and item.get("arguments") != self.arguments[index]:
                    raise TransportError("SSE argument deltas differ from the completed item")
            if original_count:
                if original_count != len(self.done):
                    raise TransportError("Terminal and SSE output item counts differ")
                for index, item in self.done.items():
                    terminal = final["output"][index]
                    if terminal.get("id") != item.get("id") or terminal.get("type") != item.get("type"):
                        raise TransportError("Terminal and SSE output identities differ")
                    if item.get("type") == "function_call" and any(terminal.get(key) != item.get(key) for key in ("name", "namespace", "call_id", "arguments")):
                        raise TransportError("Terminal and SSE function calls differ")
                    # The completed done item is authoritative for final opaque
                    # reasoning and full message content; retain terminal extras.
                    final["output"][index] = dict(terminal, **item)
            else:
                final["output"] = [self.done[index] for index in range(len(self.done))]
        elif not original_count and (self.added or self.arguments):
            raise TransportError("Terminal response has no completed SSE output items")
        return final, {"terminal_output_item_count": original_count, "assembled_output_item_count": len(final["output"]),
                       "output_assembly": "completed_stream_items" if self.done else "terminal_response", "sse_event_counts": self.event_counts}


class SIWCClient:
    """Duck-types FinBot's internal LLMClient; credentials never enter traces."""
    def __init__(self, store: OAuthStore, *, model: str = "gpt-5-nano",
                 permit: Callable[[], None] | None = None,
                 client: httpx.AsyncClient | None = None,
                 max_requests: int | None = None,
                 max_generated_characters: int | None = None, reasoning_effort: str | None = None,
                 event_sink: Callable[[dict], None] | None = None):
        self.store, self.default_model = store, model
        self.default_temperature = None
        self.permit = permit or self._deny
        self.halt_reason = None
        self.event_sink = event_sink
        if max_requests is not None and (not isinstance(max_requests, int) or isinstance(max_requests, bool) or max_requests < 1):
            raise ValueError("A provider-request limit must be a positive integer")
        self.max_requests, self.request_count = max_requests, 0
        if max_generated_characters is not None and (not isinstance(max_generated_characters, int) or isinstance(max_generated_characters, bool) or max_generated_characters < 1):
            raise ValueError("A generated-character limit must be a positive integer")
        if reasoning_effort is not None and (model != "gpt-6-luna" or reasoning_effort != "none"):
            raise ValueError("Only the explicit Luna showcase changes reasoning effort")
        self.max_generated_characters, self.reasoning_effort = max_generated_characters, reasoning_effort
        self._episode_start, self._episode_limit = 0, None
        self.http = client or httpx.AsyncClient(timeout=httpx.Timeout(180, connect=30), follow_redirects=False)

    def start_episode(self, maximum_requests: int):
        if not isinstance(maximum_requests, int) or isinstance(maximum_requests, bool) or maximum_requests < 1:
            raise ValueError("An episode request limit must be a positive integer")
        self._episode_start, self._episode_limit = self.request_count, maximum_requests

    def _request_limit(self):
        if self.max_requests is not None and self.request_count >= self.max_requests:
            self.halt_reason = "Total provider-request limit reached"
        if self._episode_limit is not None and self.request_count - self._episode_start >= self._episode_limit:
            self.halt_reason = "Episode provider-request limit reached"
        if self.halt_reason:
            raise TransportError(self.halt_reason)

    @staticmethod
    def _deny():
        raise TransportError("Inference blocked: backend credit cap and exact model entitlement are unverified")

    async def chat(self, request: Any) -> CompletedResponse:
        if self.halt_reason is not None:
            raise TransportError("Responses transport permanently halted after an unsuccessful request")
        self.permit()
        model = request.model or self.default_model
        if model != self.default_model:
            raise TransportError("Model substitution is disabled")
        token = await asyncio.to_thread(self.store.access_token)
        payload = request_payload(request, model)
        if self.reasoning_effort is not None:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        final = None
        generated = 0
        items = OutputItems()
        try:
            self.permit()
            self._request_limit()
            self.request_count += 1
            async with self.http.stream("POST", RESOURCE + "/responses", json=payload,
                                        headers={"Authorization": "Bearer " + token}) as response:
                if response.status_code != 200:
                    raise TransportError("Responses request rejected (HTTP " + str(response.status_code) + ")")
                async for event in sse_events(response.aiter_lines()):
                    if self.event_sink is not None:
                        self.event_sink({"provider_request_index": self.request_count, **diagnostic_event(event)})
                    kind = event.get("type")
                    if final is not None and kind in {"response.output_item.added", "response.output_item.done", "response.function_call_arguments.delta"}:
                        raise TransportError("Output item arrived after response.completed")
                    items.observe(event)
                    if kind in {"response.output_text.delta", "response.function_call_arguments.delta", "response.reasoning_text.delta", "response.reasoning_summary_text.delta"}:
                        generated += len(event.get("delta", ""))
                        if self.max_generated_characters is not None and generated > self.max_generated_characters:
                            raise TransportError("Generated-character limit reached; stream closed before any tool execution")
                    if kind in {"response.failed", "response.incomplete", "error"}:
                        raise TransportError("Responses stream ended with " + kind)
                    if kind == "response.completed":
                        if final is not None:
                            raise TransportError("Duplicate terminal response")
                        final = event.get("response")
        except asyncio.CancelledError:
            self.halt_reason = "Responses request was cancelled; reconcile before further inference"
            raise
        except TransportError as exc:
            self.halt_reason = str(exc)
            raise
        except Exception:
            self.halt_reason = "Responses stream unavailable or interrupted"
            raise TransportError("Responses stream unavailable or interrupted") from None
        if final is None:
            self.halt_reason = "Stream ended without response.completed"
            raise TransportError("Stream ended without response.completed")
        try:
            final, assembly = items.assemble(final)
            if self.max_generated_characters is not None:
                terminal_characters = 0
                for item in final.get("output", []):
                    if item.get("type") == "function_call":
                        terminal_characters += len(item.get("arguments", ""))
                    for part in item.get("content", []) + item.get("summary", []):
                        terminal_characters += len(part.get("text", ""))
                if terminal_characters > self.max_generated_characters:
                    raise TransportError("Completed output exceeded the generated-character limit")
            completed = completed_response(final, request, model)
            completed.metadata.update(assembly)
            return completed
        except TransportError as exc:
            self.halt_reason = str(exc)
            raise
        except Exception:
            self.halt_reason = "Malformed completed output"
            raise TransportError(self.halt_reason) from None

    async def aclose(self):
        await self.http.aclose()
