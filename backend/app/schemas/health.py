"""Contract §11: Health."""

from typing import Literal

from app.schemas.common import ContractModel


class Health(ContractModel):
    status: Literal["ok"]
    version: str
    database: Literal["ok", "error"]
    llm_provider: Literal["fable", "rule_based"]
    llm_configured: bool
    llm_model: str | None
