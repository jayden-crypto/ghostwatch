"""What an execution cost, from the tokens its steps reported and a table of published prices.

Unknown is None, never 0 and never a partial sum (API contract §0, Money). The cost of an execution
is None when no step reported tokens, and when any step that reported tokens cannot be priced:
its model is missing from the table, it has no model, or it reported only one of input and output.

What the number is: the reported input and output tokens at the standard (list) price of the
model, each step taken as one request. Ghostwatch is not told about prompt-cache reads and writes,
batch or fast-mode requests, US-only inference or server-tool fees, so none of those are in it.

Prices: Anthropic first-party API, USD per million tokens, "Base input tokens" and "Output tokens"
columns of https://platform.claude.com/docs/en/about-claude/pricing, read on 2026-11-15. Model ids
are the ones Anthropic publishes; a model reached through Amazon Bedrock or Vertex AI has a
different id and its own price list, so it is not priced here. Models that are retired or about to
be (Claude Opus 4.1, Opus 4, Sonnet 4.5, Sonnet 4) are left out. When prices change, update the
table and the date together.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

MILLION = Decimal(1_000_000)
MICRO_DOLLAR = Decimal("0.000001")  # executions.cost_usd is NUMERIC(12, 6)

# Claude Haiku 5.5 is priced per request by prompt length: over this many input tokens, the higher
# prices apply to the whole request. A step's reported input tokens stand in for the prompt length.
HAIKU_5_5_LONG_PROMPT_TOKENS = 100_000


@dataclass(frozen=True)
class Price:
    """USD per million tokens."""

    input: Decimal
    output: Decimal


def _price(input: str, output: str) -> Price:
    return Price(Decimal(input), Decimal(output))


PRICES: dict[str, Price] = {
    "claude-fable-5-2": _price("8", "40"),
    "claude-mythos-5-2": _price("8", "40"),
    "claude-fable-5-1": _price("10", "50"),
    "claude-mythos-5-1": _price("10", "50"),
    "claude-fable-5": _price("10", "50"),
    "claude-mythos-5": _price("10", "50"),
    "claude-opus-5-5": _price("4", "20"),
    "claude-opus-5": _price("5", "25"),
    "claude-opus-4-8": _price("5", "25"),
    "claude-opus-4-7": _price("5", "25"),
    "claude-opus-4-6": _price("5", "25"),
    "claude-opus-4-5": _price("5", "25"),
    "claude-opus-4-5-20251101": _price("5", "25"),
    "claude-sonnet-5-5": _price("2", "10"),
    "claude-sonnet-5": _price("2", "10"),
    "claude-sonnet-4-6": _price("3", "15"),
    "claude-haiku-5-5": _price("0.10", "0.50"),  # prompts up to 100,000 tokens
    "claude-haiku-4-5": _price("1", "5"),
    "claude-haiku-4-5-20251001": _price("1", "5"),
}
LONG_PROMPT_PRICES: dict[str, Price] = {
    "claude-haiku-5-5": _price("0.50", "2.50"),  # prompts over 100,000 tokens
}


def price_for(model: str | None, tokens_input: int) -> Price | None:
    """The price of one request to `model` with this many input tokens, or None if it is not known."""
    if model is None:
        return None
    if model in LONG_PROMPT_PRICES and tokens_input > HAIKU_5_5_LONG_PROMPT_TOKENS:
        return LONG_PROMPT_PRICES[model]
    return PRICES.get(model)


def step_cost(model: str | None, tokens_input: int | None, tokens_output: int | None) -> Decimal | None:
    """The exact cost in USD of a step that reported tokens, or None if it cannot be priced."""
    if tokens_input is None or tokens_output is None:
        return None
    price = price_for(model, tokens_input)
    if price is None:
        return None
    return (tokens_input * price.input + tokens_output * price.output) / MILLION


def execution_cost(usage: Iterable[tuple[str | None, int | None, int | None]]) -> Decimal | None:
    """The cost in USD of an execution, to the micro-dollar.

    `usage` is (model, tokens_input, tokens_output) for every step that reported any tokens.
    None if there is no such step, or if any one of them cannot be priced.
    """
    total = None
    for model, tokens_input, tokens_output in usage:
        cost = step_cost(model, tokens_input, tokens_output)
        if cost is None:
            return None
        total = cost if total is None else total + cost
    return None if total is None else total.quantize(MICRO_DOLLAR, rounding=ROUND_HALF_UP)
