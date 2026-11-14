"""Base class shared by every schema that mirrors the API contract."""

from pydantic import BaseModel, ConfigDict


class ContractModel(BaseModel):
    """Rejects unknown keys, so a payload that drifts from the contract fails validation."""

    model_config = ConfigDict(extra="forbid")
