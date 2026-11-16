"""The provider that needs no network: it proposes nothing beyond what the signatures established.

A rule-based report therefore contains the facts and the signature-based hypotheses only.
"""

from typing import Any, Literal

from app.providers.llm.base import Proposal, ProviderResult


class RuleBasedProvider:
    name: Literal["rule_based"] = "rule_based"

    def investigate(
        self, facts: list[dict[str, Any]], digest: dict[str, Any], confirmed: list[dict[str, Any]]
    ) -> ProviderResult:
        return ProviderResult(proposal=Proposal(), model=None)
