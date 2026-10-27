"""Mock of the OpenAI Responses streaming API, used by the chat assistant when LLM_PROVIDER=mock."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

MOCK_CHAT_REPLY = "This is a mock chat response."


class _MockResponses:
    def __init__(self, reply: str):
        self._reply = reply

    async def create(self, **_params: Any) -> AsyncIterator[SimpleNamespace]:
        return self._stream()

    async def _stream(self) -> AsyncIterator[SimpleNamespace]:
        # Word by word, like a real stream; never asks for a tool call.
        for i, word in enumerate(self._reply.split(" ")):
            yield SimpleNamespace(type="response.output_text.delta",
                                  delta=word if i == 0 else f" {word}")
        yield SimpleNamespace(type="response.completed")


class MockResponsesClient:
    """Drop-in for AsyncOpenAI as far as `client.responses.create(stream=True)` goes."""

    def __init__(self, reply: str = MOCK_CHAT_REPLY):
        self.responses = _MockResponses(reply)
