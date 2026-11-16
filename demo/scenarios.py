"""The demo scenarios: which agent runs, with what input, and what the outside world does to it.

A scenario never changes the agent or what gets recorded. It only changes how a fake service
behaves, exactly as a real dependency would change underneath a real agent.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType

from agents import invoice_processor, research_assistant, support_triage

QUESTIONS = [
    "How do teams trace what an AI agent did?",
    "Why do agents report success after skipping a step?",
    "What is a good retry strategy for rate-limited tools?",
    "How does schema drift break API consumers?",
    "How can a failed agent run be replayed safely?",
    "How are latency baselines used to catch regressions?",
]
INVOICES = [
    "Invoice: INV-2041\nVendor: Northwind Paper\nTotal: 1280.50\nCurrency: USD",
    "Invoice: INV-2042\nVendor: Contoso Cloud\nTotal: 9400.00\nCurrency: USD",
    "Invoice: INV-2043\nVendor: Fabrikam Freight\nTotal: 312.75\nCurrency: EUR",
    "Invoice: INV-2044\nVendor: Adatum Legal\nTotal: 5600.00\nCurrency: GBP",
    "Invoice: INV-2045\nVendor: Tailspin Catering\nTotal: 845.20\nCurrency: USD",
]
TICKETS = [
    "I was charged twice for my subscription and need a refund.",
    "I can't login after changing my password.",
    "The export button does nothing when I click it.",
    "My invoice shows the wrong company address.",
    "Two-factor login keeps rejecting my code.",
    "The dashboard crashes when I filter by date.",
]

AGENTS: dict[str, ModuleType] = {
    "research-assistant": research_assistant,
    "invoice-processor": invoice_processor,
    "support-triage": support_triage,
}


def healthy_input(slug: str, index: int) -> dict:
    """The input of the agent's `index`-th routine run (they cycle through a fixed list)."""
    if slug == "research-assistant":
        return {"question": QUESTIONS[index % len(QUESTIONS)]}
    if slug == "invoice-processor":
        return {"document": INVOICES[index % len(INVOICES)]}
    return {"ticket": TICKETS[index % len(TICKETS)]}


def reset_services() -> None:
    """Put every fake service back to its normal behaviour."""
    research_assistant.search.schema_version = 1
    invoice_processor.invoices.validation_outage = False
    support_triage.kb.rate_limited_calls = 0
    support_triage.kb.latency = 0.25


def _schema_change() -> None:
    research_assistant.search.schema_version = 2


def _validation_outage() -> None:
    invoice_processor.invoices.validation_outage = True


def _rate_limit() -> None:
    support_triage.kb.rate_limited_calls = 2


def _slow_kb() -> None:
    support_triage.kb.latency = 6.0


@dataclass(frozen=True)
class Scenario:
    name: str
    agent: str
    input: dict
    disturb: Callable[[], None]
    description: str


SCENARIOS = {
    scenario.name: scenario
    for scenario in [
        Scenario(
            "schema-change",
            "research-assistant",
            {"question": QUESTIONS[0]},
            _schema_change,
            'The search API now answers {"data": ..., "meta": ...} instead of {"results": ...}.',
        ),
        Scenario(
            "ghost-invoice",
            "invoice-processor",
            {"document": INVOICES[1]},
            _validation_outage,
            "The validation service is down; the agent swallows the error and still reports success.",
        ),
        Scenario(
            "rate-limit",
            "support-triage",
            {"ticket": TICKETS[0]},
            _rate_limit,
            "The knowledge base answers HTTP 429 twice before it succeeds.",
        ),
        Scenario(
            "slow",
            "support-triage",
            {"ticket": TICKETS[1]},
            _slow_kb,
            "The knowledge base takes about 6 seconds to answer.",
        ),
    ]
}
