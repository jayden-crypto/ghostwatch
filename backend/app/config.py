"""Application settings, loaded from the environment and the repo-root .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://ghostwatch:ghostwatch@localhost:5432/ghostwatch"
    ghostwatch_api_key: str = Field(min_length=1)
    cors_origins: str = "http://localhost:3000"

    llm_provider: Literal["fable", "rule_based"] = "rule_based"
    anthropic_api_key: str = ""
    llm_model: str = "claude-fable-5-2"
    llm_timeout_seconds: float = 60

    sweeper_interval_seconds: float = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def llm_configured(self) -> bool:
        """Whether the configured investigation provider can actually run."""
        return self.llm_provider == "rule_based" or bool(self.anthropic_api_key)

    @property
    def llm_model_in_use(self) -> str | None:
        """The model the configured provider calls; the rule-based provider uses none."""
        return self.llm_model if self.llm_provider == "fable" else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
