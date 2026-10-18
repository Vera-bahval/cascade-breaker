import json
from types import SimpleNamespace

import httpx
import pytest

from cascade_guard.transport import SIWCClient, TransportError, completed_response, request_payload
from cascade_guard.transport import diagnostic_event


def test_diagnostic_event_excludes_content_credentials_and_opaque_history():
    value = diagnostic_event({"type": "response.output_item.done", "output_index": 0,
        "authorization": "Bearer secret-token", "delta": "private-text",
        "item": {"type": "function_call", "name": "transfer", "arguments": '{"bank":"private-bank"}',
                 "encrypted_content": "private-opaque", "client_id": "private-client"},
        "response": {"status": "completed", "model": "gpt-6-luna", "usage": {"input_tokens": 12},
                     "output": [], "instructions": "private-instructions"}})
    serialized = json.dumps(value)
    assert not any(secret in serialized for secret in ("secret-token", "private-text", "private-bank", "private-opaque", "private-client", "private-instructions"))
    assert value["item"]["arguments_characters"] == 23
    assert value["response"]["usage"]["input_tokens"] == 12


@pytest.mark.asyncio
async def test_event_sink_records_completed_stream_and_usage_before_release():
    value = final()
    events = [{"type": "response.output_item.done", "output_index": index, "item": item}
              for index, item in enumerate(value["output"])]
    events.append({"type": "response.completed", "response": value})
    async def handler(req):
        return httpx.Response(200, text="".join("data: " + json.dumps(e) + "\n\n" for e in events))
    journal = []
    client = SIWCClient(SimpleNamespace(access_token=lambda: "test-access"), permit=lambda: None,
                        event_sink=journal.append, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = await client.chat(request())
    assert result.tool_calls and len(journal) == 4
    assert journal[-1]["response"]["usage"] == {"input_tokens": 8}
    assert all(event["provider_request_index"] == 1 for event in journal)
    assert "opaque-do-not-interpret" not in json.dumps(journal)
    await client.aclose()


def request(**kwargs):
    return SimpleNamespace(messages=[{"role": "system", "content": "Policy"}, {"role": "user", "content": "Do task"}],
                           model=None, tools=[{"type": "function", "name": "transfer", "parameters": {"type": "object"}}],
                           output_json_schema=None, temperature=0, previous_response_id="old", **kwargs)


def final():
    return {"id": "r", "status": "completed", "model": "gpt-5-nano", "usage": {"input_tokens": 8}, "output": [
        {"type": "reasoning", "id": "opaque", "encrypted_content": "opaque-do-not-interpret", "summary": []},
        {"type": "message", "role": "assistant", "phase": "commentary", "content": [{"type": "output_text", "text": "Checking"}]},
        {"type": "function_call", "namespace": "finbot", "name": "transfer", "call_id": "call_1", "arguments": '{"amount":12}'}]}


def test_payload_allowlist_and_complete_history():
    req = request()
    payload = request_payload(req, "gpt-5-nano")
    assert payload["input"][0]["role"] == "developer"
    assert req.messages[0]["role"] == "system"
    assert payload["store"] is False and payload["stream"] is True
    assert payload["tools"][0]["type"] == "namespace"
    assert not {"temperature", "max_output_tokens", "previous_response_id", "metadata"} & payload.keys()
    response = completed_response(final(), req, "gpt-5-nano")
    assert response.tool_calls[0]["arguments"] == {"amount": 12}
    assert response.messages[-3]["encrypted_content"] == "opaque-do-not-interpret"
    assert response.messages[-2]["phase"] == "commentary"


@pytest.mark.parametrize("change", ["incomplete", "refusal", "bad_args", "different_model"])
def test_terminal_response_rejections(change):
    value = final()
    if change == "incomplete": value["status"] = "incomplete"
    if change == "refusal": value["output"][1]["content"] = [{"type": "refusal", "refusal": "No"}]
    if change == "bad_args": value["output"][2]["arguments"] = "{"
    if change == "different_model": value["model"] = "gpt-other"
    with pytest.raises(TransportError): completed_response(value, request(), "gpt-5-nano")


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["completed", "incomplete", "failed", "interrupted"])
async def test_split_arguments_and_terminal_gate(terminal):
    events = [{"type": "response.function_call_arguments.delta", "delta": '{"amount":'},
              {"type": "response.function_call_arguments.delta", "delta": '12}'}]
    if terminal != "interrupted":
        events.append({"type": "response." + terminal, "response": final()})
    sse = "".join("data: " + json.dumps(e) + "\n\n" for e in events)
    captured = []
    async def handler(req):
        captured.append(json.loads(req.content))
        return httpx.Response(200, text=sse, headers={"Content-Type": "text/event-stream"})
    store = SimpleNamespace(access_token=lambda: "dummy-test-access")
    client = SIWCClient(store, permit=lambda: None, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    if terminal == "completed":
        response = await client.chat(request())
        assert response.tool_calls == [{"name": "transfer", "call_id": "call_1", "arguments": {"amount": 12}}]
    else:
        with pytest.raises(TransportError): await client.chat(request())
        with pytest.raises(TransportError, match="halted"): await client.chat(request())
        assert len(captured) == 1
    assert captured[0]["stream"] is True
    await client.aclose()


@pytest.mark.asyncio
async def test_unverified_cap_prevents_network():
    async def handler(_): raise AssertionError("No network is allowed")
    client = SIWCClient(SimpleNamespace(access_token=lambda: "x"), client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(TransportError, match="blocked"):
        await client.chat(request())


@pytest.mark.asyncio
@pytest.mark.parametrize("bound", ["total", "episode", "stream_text", "terminal_text", "served_model"])
async def test_showcase_bounds_permanently_halt_without_extra_attempts(bound):
    value = final()
    value["model"] = "gpt-6-luna"
    if bound == "served_model": value["model"] = "gpt-5-nano"
    events = [{"type": "response.completed", "response": value}]
    if bound == "stream_text": events.insert(0, {"type": "response.output_text.delta", "delta": "x" * 11})
    captured = []
    async def handler(req):
        captured.append(json.loads(req.content))
        return httpx.Response(200, text="".join("data: " + json.dumps(e) + "\n\n" for e in events))
    client = SIWCClient(SimpleNamespace(access_token=lambda: "test-access"), model="gpt-6-luna", permit=lambda: None,
                        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), reasoning_effort="none",
                        max_requests=1 if bound == "total" else 3,
                        max_generated_characters=10 if bound in {"stream_text", "terminal_text"} else 16000)
    if bound == "episode": client.start_episode(1)
    if bound in {"total", "episode"}:
        await client.chat(request())
    with pytest.raises(TransportError): await client.chat(request())
    with pytest.raises(TransportError, match="halted"): await client.chat(request())
    assert client.request_count == len(captured) == 1
    assert captured[0]["reasoning"] == {"effort": "none"}
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["completed", "missing", "incomplete", "contradictory_args", "unfinished_item"])
async def test_stream_done_items_assembled_only_after_completed_terminal(terminal):
    # Synthetic reference-schema fixture, not a recovered live SSE transcript.
    reasoning={"id":"reasoning_1","type":"reasoning","status":"completed","encrypted_content":"final-opaque","summary":[]}
    call={"id":"fc_1","type":"function_call","status":"completed","namespace":"finbot","name":"transfer","call_id":"call_1","arguments":'{"amount":12}'}
    events=[{"type":"response.output_item.added","output_index":0,"item":dict(reasoning,status="in_progress",encrypted_content="partial-opaque")},
            {"type":"response.output_item.done","output_index":0,"item":reasoning},
            {"type":"response.output_item.added","output_index":1,"item":dict(call,status="in_progress",arguments="")},
            {"type":"response.function_call_arguments.delta","output_index":1,"delta":'{"amount":'},
            {"type":"response.function_call_arguments.delta","output_index":1,"delta":'12}'},
            {"type":"response.output_item.done","output_index":1,"item":call}]
    if terminal == "contradictory_args": events[-1]["item"]=dict(call,arguments='{"amount":13}')
    if terminal == "unfinished_item": events.pop()
    if terminal != "missing":
        events.append({"type":"response.incomplete" if terminal=="incomplete" else "response.completed",
                       "response":{"id":"r","model":"gpt-5-nano","status":"completed","usage":{},"output":[]}})
    async def handler(req):
        return httpx.Response(200,text="".join("data: "+json.dumps(e)+"\n\n" for e in events))
    client=SIWCClient(SimpleNamespace(access_token=lambda:"test-access"),permit=lambda:None,
                      client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    if terminal=="completed":
        response=await client.chat(request())
        assert response.tool_calls[0]["arguments"]=={"amount":12}
        assert response.messages[-2]["encrypted_content"]=="final-opaque"
        assert response.metadata["terminal_output_item_count"]==0
        assert response.metadata["assembled_output_item_count"]==2
    else:
        with pytest.raises(TransportError): await client.chat(request())
        assert client.halt_reason is not None
    await client.aclose()
