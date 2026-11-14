"""The Claude provider with a fake client: what it sends, and every way the call can fail."""

import json
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest

from app.config import Settings
from app.providers.llm.base import ProviderError
from app.providers.llm.fable import FableProvider
from app.providers.llm.rule_based import RuleBasedProvider
from app.services.investigation.engine import make_provider
from app.services.investigation.prompts import PROPOSAL_SCHEMA, SYSTEM_PROMPT

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
FACTS = [{"id": "F1", "statement": "Step 3 parse_results failed with KeyError: 'results'.", "evidence": []}]
DIGEST = {
    "execution": {"status": "failed"},
    "steps": [{"step_id": "stp_" + "1" * 32, "name": "parse_results"}],
}
GOOD = {
    "hypotheses": [
        {"statement": "The search API changed.", "confidence": "medium", "reasoning": "F1.", "supporting_fact_ids": ["F1"],
         "contradicting_fact_ids": [], "relevant_step_ids": []}
    ],
    "recommendations": [{"action": "Pin the API version.", "rationale": "Stops drift.", "hypothesis_index": 0}],
    "root_cause": {"hypothesis_index": 0, "status": "probable"},
    "evidence_gaps": ["Response headers were not recorded."],
}  # fmt: skip


def settings(**overrides: Any) -> Settings:
    values = {
        "ghostwatch_api_key": "k",
        "llm_provider": "fable",
        "anthropic_api_key": "placeholder-not-a-real-key",
    }
    return Settings(_env_file=None, **{**values, **overrides})


def message(
    text: str | None, *, stop_reason: str = "end_turn", model: str = "claude-fable-5-2"
) -> SimpleNamespace:
    content = [SimpleNamespace(type="thinking", thinking="")]
    if text is not None:
        content.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(
        content=content, stop_reason=stop_reason, model=model,
        model_dump=lambda mode="json": {"id": "msg_1", "model": model, "stop_reason": stop_reason},
    )  # fmt: skip


class FakeClient:
    """Stands in for anthropic.Anthropic: returns queued responses (or raises queued errors) in order."""

    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.messages = SimpleNamespace(create=lambda **kwargs: self._create("messages", kwargs))
        self.beta = SimpleNamespace(
            messages=SimpleNamespace(create=lambda **kwargs: self._create("beta.messages", kwargs))
        )

    def _create(self, endpoint: str, kwargs: dict[str, Any]) -> Any:
        self.calls.append((endpoint, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def provider(client: FakeClient, **overrides: Any) -> FableProvider:
    return FableProvider(settings(**overrides), client=client)


def status_error(cls: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
    return cls("nope", response=httpx2.Response(status, request=REQUEST), body=None)


def test_request_uses_structured_output_and_the_reviewed_prompt() -> None:
    client = FakeClient(message(json.dumps(GOOD)))
    result = provider(client).investigate(FACTS, DIGEST, [{"signature": "x", "statement": "y"}])

    ((endpoint, request),) = client.calls
    assert endpoint == "beta.messages"  # Fable can decline; the server-side fallback is opted into
    assert (request["betas"], request["fallbacks"]) == (["server-side-fallback-2026-07-01"], "default")
    assert (request["model"], request["max_tokens"], request["system"]) == (
        "claude-fable-5-2",
        16000,
        SYSTEM_PROMPT,
    )
    assert request["output_config"] == {
        "effort": "medium",
        "format": {"type": "json_schema", "schema": PROPOSAL_SCHEMA},
    }
    # Not sent: thinking config, forced tool use and sampling parameters are rejected by this model.
    assert not {"thinking", "tools", "tool_choice", "temperature", "top_p"} & set(request)
    (user,) = request["messages"]
    assert user["role"] == "user"
    assert (
        '"id": "F1"' in user["content"]
        and "stp_" + "1" * 32 in user["content"]
        and '"signature": "x"' in user["content"]
    )

    assert result.model == "claude-fable-5-2"
    assert result.raw == {"id": "msg_1", "model": "claude-fable-5-2", "stop_reason": "end_turn"}
    assert result.proposal.hypotheses[0].supporting_fact_ids == ["F1"]
    assert result.proposal.root_cause.status == "probable"
    assert result.proposal.evidence_gaps == ["Response headers were not recorded."]


def test_the_model_that_actually_answered_is_reported() -> None:
    client = FakeClient(
        message(json.dumps(GOOD), model="claude-opus-4-8")
    )  # a server-side fallback served it
    assert provider(client).investigate(FACTS, DIGEST, []).model == "claude-opus-4-8"


def test_models_without_server_side_fallback_use_the_plain_endpoint() -> None:
    client = FakeClient(message(json.dumps(GOOD), model="claude-haiku-5-5"))
    provider(client, llm_model="claude-haiku-5-5").investigate(FACTS, DIGEST, [])
    ((endpoint, request),) = client.calls
    assert endpoint == "messages" and request["model"] == "claude-haiku-5-5"
    assert "fallbacks" not in request and "betas" not in request


@pytest.mark.parametrize(
    "bad",
    [
        "not json at all",
        json.dumps({**GOOD, "hypotheses": [{"statement": "no other fields"}]}),
        json.dumps({**GOOD, "surprise": 1}),
        json.dumps({**GOOD, "hypotheses": [{**GOOD["hypotheses"][0], "confidence": "certain"}]}),
        json.dumps([GOOD]),
        None,  # no text block
    ],
    ids=["not-json", "missing-fields", "extra-key", "bad-enum", "wrong-shape", "no-text"],
)
def test_malformed_output_is_retried_once_then_gives_up(bad: str | None) -> None:
    recovered = FakeClient(message(bad), message(json.dumps(GOOD)))
    assert len(provider(recovered).investigate(FACTS, DIGEST, []).proposal.hypotheses) == 1
    assert len(recovered.calls) == 2

    twice = FakeClient(message(bad), message(bad))
    with pytest.raises(ProviderError, match="did not match the schema twice"):
        provider(twice).investigate(FACTS, DIGEST, [])
    assert len(twice.calls) == 2  # exactly one retry


def test_a_cut_off_answer_counts_as_malformed() -> None:
    client = FakeClient(
        message(json.dumps(GOOD)[:40], stop_reason="max_tokens"),
        message(json.dumps(GOOD)[:40], stop_reason="max_tokens"),
    )
    with pytest.raises(ProviderError, match="cut off at the token limit"):
        provider(client).investigate(FACTS, DIGEST, [])


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (anthropic.APITimeoutError(request=REQUEST), "timed out after 60 s"),
        (status_error(anthropic.RateLimitError, 429), "was rate limited"),
        (status_error(anthropic.AuthenticationError, 401), "rejected the API key"),
        (status_error(anthropic.BadRequestError, 400), "returned HTTP 400"),
        (status_error(anthropic.InternalServerError, 529), "returned HTTP 529"),
        (anthropic.APIConnectionError(request=REQUEST), "could not be reached"),
    ],
    ids=["timeout", "rate-limit", "bad-key", "bad-request", "overloaded", "network"],
)
def test_api_failures_become_provider_errors_with_a_plain_reason(error: Exception, reason: str) -> None:
    client = FakeClient(error)
    with pytest.raises(ProviderError) as caught:
        provider(client).investigate(FACTS, DIGEST, [])
    assert caught.value.reason == reason
    assert len(client.calls) == 1  # API failures are not retried here; the SDK already retried once


def test_a_refusal_is_a_provider_error_not_a_parse_attempt() -> None:
    client = FakeClient(message("I can't help with that.", stop_reason="refusal"))
    with pytest.raises(ProviderError) as caught:
        provider(client).investigate(FACTS, DIGEST, [])
    assert caught.value.reason == "declined to analyse this trace"
    assert len(client.calls) == 1


def test_the_timeout_setting_is_used() -> None:
    client = FakeClient(anthropic.APITimeoutError(request=REQUEST))
    with pytest.raises(ProviderError, match="timed out after 7.5 s"):
        provider(client, llm_timeout_seconds=7.5).investigate(FACTS, DIGEST, [])
    real = FableProvider(settings(llm_timeout_seconds=12))
    assert (real.client.timeout, real.client.max_retries) == (12, 1)


def test_make_provider_follows_the_settings() -> None:
    chosen, unavailable = make_provider(settings(llm_provider="rule_based"))
    assert isinstance(chosen, RuleBasedProvider) and unavailable is None

    chosen, unavailable = make_provider(settings(llm_provider="fable", anthropic_api_key=""))
    assert isinstance(chosen, RuleBasedProvider)
    assert unavailable == "LLM_PROVIDER is fable but no ANTHROPIC_API_KEY is configured"

    chosen, unavailable = make_provider(settings(llm_provider="fable", llm_model="claude-opus-5-5"))
    assert isinstance(chosen, FableProvider) and unavailable is None
    assert (chosen.name, chosen.model) == ("fable", "claude-opus-5-5")
