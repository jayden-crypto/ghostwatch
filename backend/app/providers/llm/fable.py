"""The Claude provider: asks the model for hypotheses as schema-constrained JSON.

The model only proposes. Its answer is validated here and every citation in it is checked by
`services/investigation/verify.py`. Any failure (timeout, rate limit, refusal, malformed output)
raises ProviderError, and the engine then reports the deterministic findings on their own.
"""

import json
import logging
from typing import Any, Literal

import anthropic
from pydantic import ValidationError

from app.config import Settings
from app.providers.llm.base import Proposal, ProviderError, ProviderResult
from app.services.investigation.prompts import PROPOSAL_SCHEMA, SYSTEM_PROMPT, build_user_message

logger = logging.getLogger("ghostwatch")

MAX_TOKENS = 16000
# The analysis runs over a few kilobytes of facts and digest; medium effort keeps it quick.
EFFORT = "medium"
# On these models a safety classifier can decline a request. The server-side fallback re-runs it on
# another model inside the same call; the report then names the model that actually answered.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MODELS_WITH_SERVER_SIDE_FALLBACK = (
    "claude-fable-5-1",
    "claude-fable-5-2",
    "claude-opus-5",
    "claude-sonnet-5-5",
)


class FableProvider:
    name: Literal["fable"] = "fable"

    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None) -> None:
        self.model = settings.llm_model
        self.timeout = settings.llm_timeout_seconds
        self.client = client or anthropic.Anthropic(
            api_key=settings.anthropic_api_key, timeout=self.timeout, max_retries=1
        )

    def investigate(
        self, facts: list[dict[str, Any]], digest: dict[str, Any], confirmed: list[dict[str, Any]]
    ) -> ProviderResult:
        message = build_user_message(facts, digest, confirmed)
        last_problem = ""
        for _attempt in range(2):  # one retry when the answer does not validate
            response = self._call(message)
            try:
                return ProviderResult(
                    proposal=self._parse(response), model=response.model, raw=response.model_dump(mode="json")
                )
            except (ValueError, ValidationError) as exc:
                last_problem = str(exc).splitlines()[0]
                logger.warning("Model output did not match the proposal schema: %s", last_problem)
        raise ProviderError(f"returned output that did not match the schema twice ({last_problem})")

    def _call(self, message: str) -> Any:
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": message}],
            "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": PROPOSAL_SCHEMA}},
        }
        try:
            if self.model.startswith(MODELS_WITH_SERVER_SIDE_FALLBACK):
                response = self.client.beta.messages.create(
                    betas=[FALLBACK_BETA], fallbacks="default", **request
                )
            else:
                response = self.client.messages.create(**request)
        except anthropic.APITimeoutError:
            raise ProviderError(f"timed out after {self.timeout:g} s") from None
        except anthropic.RateLimitError:
            raise ProviderError("was rate limited") from None
        except anthropic.AuthenticationError:
            raise ProviderError("rejected the API key") from None
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"returned HTTP {exc.status_code}") from None
        except anthropic.APIConnectionError:
            raise ProviderError("could not be reached") from None
        if response.stop_reason == "refusal":
            raise ProviderError("declined to analyse this trace")
        return response

    @staticmethod
    def _parse(response: Any) -> Proposal:
        if response.stop_reason == "max_tokens":
            raise ValueError("the answer was cut off at the token limit")
        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is None:
            raise ValueError("the answer contained no text block")
        return Proposal.model_validate(json.loads(text))
