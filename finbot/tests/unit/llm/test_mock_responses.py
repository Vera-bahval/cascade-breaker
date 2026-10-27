"""Unit tests for the mock Responses client used by the chat assistant."""

from types import SimpleNamespace

import pytest

from finbot.agents.chat import VendorChatAssistant
from finbot.core.llm.mock_responses import MOCK_CHAT_REPLY, MockResponsesClient


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_spells_out_the_reply_without_tool_calls():
    stream = await MockResponsesClient().responses.create(model="x", input=[], stream=True)
    events = [e async for e in stream]
    text = "".join(e.delta for e in events if e.type == "response.output_text.delta")
    assert text == MOCK_CHAT_REPLY
    assert not any(e.type == "response.output_item.done" for e in events)


@pytest.mark.unit
def test_chat_assistant_uses_mock_when_provider_is_mock(monkeypatch):
    monkeypatch.setattr("finbot.agents.chat.settings.LLM_PROVIDER", "mock")
    session = SimpleNamespace(namespace="ns", user_id="u", current_vendor_id=None,
                              session_id="s")
    assistant = VendorChatAssistant(session_context=session)
    assert isinstance(assistant._client, MockResponsesClient)
