"""OpenRouter request fields: provider pin, seed and reasoning."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from finbot.core.data.models import LLMRequest
from finbot.core.llm.openai_client import OpenAIClient, openrouter_extra_body


def _settings(ms, pin=None, seed=None, reasoning=None):
    ms.LLM_DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash-1017"
    ms.LLM_DEFAULT_TEMPERATURE = 0
    ms.OPENAI_API_KEY = "test-key"
    ms.OPENAI_BASE_URL = "https://openrouter.ai/api/v1"
    ms.LLM_MAX_TOKENS = 5000
    ms.LLM_TIMEOUT = 60
    ms.LLM_PROVIDER_PIN = pin
    ms.LLM_SEED = seed
    ms.LLM_REASONING = reasoning


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, {}),
        ({"reasoning": "off"}, {"reasoning": {"enabled": False}}),
        ({"reasoning": "low"}, {"reasoning": {"effort": "low"}}),
        ({"pin": "deepinfra/fp8", "seed": 7, "reasoning": "off"},
         {"provider": {"order": ["deepinfra/fp8"], "allow_fallbacks": False}, "seed": 7,
          "reasoning": {"enabled": False}}),
        ({"seed": True}, {}),
    ],
)
def test_extra_body(kwargs, expected):
    with patch("finbot.core.llm.openai_client.settings") as ms:
        _settings(ms, **kwargs)
        assert openrouter_extra_body() == expected


@pytest.mark.asyncio
@pytest.mark.unit
async def test_agent_request_carries_extra_body_and_temperature():
    response = MagicMock(id="r1", output_text="", output=[], usage=None, model="m")
    with patch("finbot.core.llm.openai_client.settings") as ms, \
            patch("finbot.core.llm.openai_client.AsyncOpenAI") as openai:
        _settings(ms, seed=7, reasoning="off")
        openai.return_value.responses.create = AsyncMock(return_value=response)
        await OpenAIClient().chat(LLMRequest(messages=[{"role": "user", "content": "hi"}]))
        sent = openai.return_value.responses.create.call_args.kwargs
    assert sent["model"] == "deepseek/deepseek-v4.1-flash-1017"
    assert sent["temperature"] == 0
    assert sent["extra_body"] == {"seed": 7, "reasoning": {"enabled": False}}

