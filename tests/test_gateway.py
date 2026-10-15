"""Tests for model-gateway safety limits."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from uwazi.config import LLMConfig
from uwazi.gateway import Gateway


class _Completions:
    def __init__(self) -> None:
        self.max_tokens: int | None = None

    async def create(self, **kwargs: Any) -> Any:
        self.max_tokens = kwargs["max_tokens"]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )


@pytest.mark.asyncio
async def test_gateway_enforces_configured_token_cap() -> None:
    gateway = Gateway(
        LLMConfig(
            api_key="test-key",
            base_url="https://example.invalid/v1",
            model="test-model",
            stub_mode=False,
            max_tokens_per_call=128,
            max_cost_cents_per_call=Decimal("5"),
        )
    )
    completions = _Completions()
    gateway._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    await gateway.complete("system", "user", max_tokens=2048)

    assert completions.max_tokens == 128
