"""Runtime configuration for BidBox.

Every setting has a sensible default so the demo runs without any
environment configuration. Production deployments override via the
environment (or a `.env` file loaded by python-dotenv).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str) -> str:
    """Read an environment variable, returning the default if unset."""
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


@dataclass(frozen=True)
class LLMConfig:
    """Provider-agnostic LLM configuration.

    BidBox uses the `openai` SDK pointed at any OpenAI-compatible endpoint.
    The default works with OpenAI, Qwen via ModelScope, OpenRouter, or a
    local Llama server (e.g. `vllm serve`).
    """

    api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY", ""))
    base_url: str = field(default_factory=lambda: _env("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    model: str = field(default_factory=lambda: _env("OPENAI_MODEL", "gpt-4o-mini"))

    #: When True, the gateway returns deterministic canned responses and
    #: never makes a network call. Useful for offline demos and tests.
    stub_mode: bool = field(default_factory=lambda: not _env("OPENAI_API_KEY", ""))

    #: Per-request token cap. The orchestrator refuses to exceed this.
    max_tokens_per_call: int = field(default_factory=lambda: _env_int("LLM_MAX_TOKENS", 1024))

    #: Per-request cost cap in USD cents. The orchestrator refuses to exceed.
    max_cost_cents_per_call: Decimal = field(
        default_factory=lambda: Decimal(_env("LLM_MAX_COST_CENTS", "5"))
    )


@dataclass(frozen=True)
class StorageConfig:
    """SQLite storage configuration."""

    db_path: Path = field(default_factory=lambda: Path(_env("BIDBOX_DB_PATH", "./bidbox.db")))


@dataclass(frozen=True)
class MCPConfig:
    """MCP server transport configuration."""

    transport: str = field(default_factory=lambda: _env("MCP_TRANSPORT", "stdio"))
    sse_host: str = field(default_factory=lambda: _env("MCP_SSE_HOST", "127.0.0.1"))
    sse_port: int = field(default_factory=lambda: _env_int("MCP_SSE_PORT", 8765))


@dataclass(frozen=True)
class ReviewUIConfig:
    """FastAPI review UI configuration."""

    host: str = field(default_factory=lambda: _env("REVIEW_UI_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("REVIEW_UI_PORT", 8000))


@dataclass(frozen=True)
class HumanInTheLoopConfig:
    """The procurement officer principal.

    In production, this comes from OIDC. For the demo, we hardcode.
    The MCP tool `record_officer_decision` refuses any request where
    `principal.kind='agent'` — see ARCHITECTURE.md §5.
    """

    officer_principal_id: str = field(
        default_factory=lambda: _env("OFFICER_PRINCIPAL_ID", "officer-demo")
    )
    officer_principal_kind: str = field(
        default_factory=lambda: _env("OFFICER_PRINCIPAL_KIND", "human")
    )


@dataclass(frozen=True)
class CitationConfig:
    """Citation validator configuration."""

    #: Minimum embedding cosine similarity between a claim and the cited
    #: paragraph for the citation to count as "supportive". 0.75 is the
    #: default — high enough to catch hallucinated citations, low enough
    #: to allow paraphrased evidence.
    min_similarity: float = field(default_factory=lambda: _env_float("CITATION_MIN_SIMILARITY", 0.75))


@dataclass(frozen=True)
class Settings:
    """Root settings — passed through the application."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    review_ui: ReviewUIConfig = field(default_factory=ReviewUIConfig)
    human_in_the_loop: HumanInTheLoopConfig = field(default_factory=HumanInTheLoopConfig)
    citation: CitationConfig = field(default_factory=CitationConfig)
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))


def get_settings() -> Settings:
    """Return the singleton settings instance.

    BidBox does not need hot-reloadable config — settings are read at
    process startup. Tests override by constructing their own Settings.
    """
    return Settings()
