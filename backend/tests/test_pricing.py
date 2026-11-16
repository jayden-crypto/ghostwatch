"""B14: an execution's cost comes from per-step tokens and a table of published prices, or is unknown."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Execution
from app.services import pricing
from tests import events as ev
from tests.events import new_step_id, post_events
from tests.factories import make_agent, make_execution

Usage = tuple[str | None, int | None, int | None]


def test_a_step_is_priced_per_million_tokens_of_its_model() -> None:
    assert pricing.step_cost("claude-opus-5-5", 1_000_000, 100_000) == Decimal("6")  # $4 + $2
    assert pricing.step_cost("claude-fable-5-2", 1200, 300) == Decimal("0.0216")
    assert pricing.step_cost("claude-haiku-4-5-20251001", 1000, 1000) == Decimal("0.006")
    assert pricing.step_cost("claude-sonnet-5-5", 0, 0) == 0  # a known zero, not an unknown


@pytest.mark.parametrize(
    "usage",
    [
        ("demo-llm-1", 100, 20),  # no published price
        ("gpt-9", 100, 20),
        ("anthropic.claude-opus-5-5", 100, 20),  # the Bedrock id: partner pricing, not this table
        ("Claude-Opus-5-5", 100, 20),  # not the published id
        (None, 100, 20),  # tokens without a model
        ("claude-opus-5-5", 100, None),  # half the usage is unknown
        ("claude-opus-5-5", None, 20),
    ],
)
def test_a_step_that_cannot_be_priced_has_no_cost(usage: Usage) -> None:
    assert pricing.step_cost(*usage) is None
    # ...and it makes the whole execution's cost unknown, however much of the rest is known.
    assert pricing.execution_cost([("claude-opus-5-5", 1000, 1000), usage]) is None
    assert pricing.execution_cost([usage, ("claude-opus-5-5", 1000, 1000)]) is None


def test_haiku_5_5_costs_more_per_token_once_the_prompt_passes_100k_tokens() -> None:
    assert pricing.step_cost("claude-haiku-5-5", 100_000, 1000) == Decimal("0.0105")  # $0.10 / $0.50
    assert pricing.step_cost("claude-haiku-5-5", 100_001, 1000) == Decimal("0.0525005")  # $0.50 / $2.50
    # Only that model has a second price: a long prompt elsewhere costs the usual rate.
    assert pricing.step_cost("claude-sonnet-5-5", 500_000, 0) == Decimal("1")


def test_an_execution_costs_the_sum_of_its_steps_to_the_micro_dollar() -> None:
    assert pricing.execution_cost([]) is None  # no usage data is unknown, not free
    assert pricing.execution_cost([("claude-sonnet-5-5", 2000, 500), ("claude-haiku-4-5", 1000, 1000)]) == (
        Decimal("0.015000")
    )
    # Summed exactly, rounded once: three steps of $0.0000004 are $0.000001, not three zeroes.
    assert pricing.execution_cost([("claude-haiku-5-5", 4, 0)] * 3) == Decimal("0.000001")
    assert pricing.execution_cost([("claude-haiku-5-5", 100_001, 1000)]) == Decimal("0.052501")  # half up
    assert pricing.execution_cost([("claude-haiku-5-5", 1, 0)]) == Decimal("0.000000")


def test_every_price_is_positive_and_output_costs_more_than_input() -> None:
    for model, price in {
        **pricing.PRICES,
        **{f"{m} (long)": p for m, p in pricing.LONG_PROMPT_PRICES.items()},
    }.items():
        assert 0 < price.input < price.output, model
    assert set(pricing.LONG_PROMPT_PRICES) <= set(pricing.PRICES)


@pytest.fixture
def execution(db_session: Session) -> Execution:
    return make_execution(db_session, make_agent(db_session))


def run(
    client: TestClient, auth: dict, execution: Execution, usage: list[Usage], *, fail: bool = False
) -> dict:
    """Send one llm_call step per usage entry (plus a tool call that reports nothing), then end the run."""
    events, seq = [], 0
    for model, tokens_input, tokens_output in usage:
        step = new_step_id()
        tokens = {
            key: value
            for key, value in (("tokens_input", tokens_input), ("tokens_output", tokens_output))
            if value is not None
        }
        events.append(ev.step_started(seq + 1, step, seq, name="call", step_type="llm_call", model=model))
        events.append(ev.step_completed(seq + 2, step, seq + 1, **tokens))
        seq += 2
    tool = new_step_id()
    events.append(ev.step_started(seq + 1, tool, seq, name="web_search", step_type="tool_call"))
    events.append(ev.step_completed(seq + 2, tool, seq + 1))
    error = {"type": "ValueError", "message": "boom", "stacktrace": None}
    last = (
        ev.execution_failed(seq + 3, seq + 2, error=error)
        if fail
        else ev.execution_completed(seq + 3, seq + 2)
    )
    post_events(client, auth, execution.id, [*events, last])
    return client.get(f"/api/v1/executions/{execution.id}").json()


def test_cost_is_stored_when_the_execution_ends(
    db_client: TestClient, auth: dict, execution: Execution
) -> None:
    detail = run(
        db_client, auth, execution, [("claude-sonnet-5-5", 2000, 500), ("claude-opus-5-5", 1000, 100)]
    )
    assert (detail["tokens_input"], detail["tokens_output"], detail["tokens_total"]) == (3000, 600, 3600)
    assert detail["cost_usd"] == 0.015  # 0.004 + 0.005 + 0.004 + 0.002
    assert isinstance(detail["cost_usd"], float)  # a JSON number, not a string

    (listed,) = db_client.get("/api/v1/executions").json()["items"]
    assert listed["cost_usd"] == 0.015


def test_a_failed_execution_still_cost_what_its_steps_used(
    db_client: TestClient, auth: dict, execution: Execution
) -> None:
    detail = run(db_client, auth, execution, [("claude-fable-5-2", 10_000, 1000)], fail=True)
    assert (detail["status"], detail["cost_usd"]) == ("failed", 0.12)


@pytest.mark.parametrize(
    ("usage", "tokens_total"),
    [
        ([], None),  # no step reported tokens
        ([("demo-llm-1", 100, 20)], 120),  # a model with no published price
        ([("claude-opus-5-5", 1000, 100), ("demo-llm-1", 100, 20)], 1220),  # known and unknown mixed
        ([("claude-opus-5-5", 1000, 100), (None, 100, 20)], 1220),  # tokens with no model
        ([("claude-opus-5-5", 1000, None)], 1000),  # input reported, output not
    ],
)
def test_cost_is_unknown_rather_than_partial_or_zero(
    db_client: TestClient, auth: dict, execution: Execution, usage: list[Usage], tokens_total: int | None
) -> None:
    detail = run(db_client, auth, execution, usage)
    assert detail["tokens_total"] == tokens_total  # the tokens are still counted
    assert detail["cost_usd"] is None


def test_steps_that_report_no_tokens_do_not_make_the_cost_unknown(
    db_client: TestClient, auth: dict, execution: Execution
) -> None:
    # The tool call in every run() reports no tokens, and so does this model call: neither has a
    # cost to be missing. Only the step that reported usage is priced.
    detail = run(db_client, auth, execution, [("demo-llm-1", None, None), ("claude-haiku-4-5", 1000, 1000)])
    assert (detail["tokens_total"], detail["cost_usd"]) == (2000, 0.006)
