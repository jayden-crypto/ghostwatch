"""A fake web search API over a small fixed corpus."""

from __future__ import annotations

from fake_services.timing import timing

CORPUS = [
    {
        "title": "Agent observability: tracing every step",
        "url": "https://example.test/agent-observability",
        "snippet": "Tracing records each tool call and model call an agent makes, with inputs and outputs.",
    },
    {
        "title": "Why silent failures are the hardest agent bugs",
        "url": "https://example.test/silent-failures",
        "snippet": "An agent can report success while skipping the step that mattered.",
    },
    {
        "title": "Retry strategies for rate-limited tools",
        "url": "https://example.test/retry-strategies",
        "snippet": "Exponential backoff with a retry budget keeps rate limits from cascading.",
    },
    {
        "title": "Schema drift in upstream APIs",
        "url": "https://example.test/schema-drift",
        "snippet": "A renamed response field breaks every consumer that indexes it directly.",
    },
    {
        "title": "Replaying agent runs against recorded inputs",
        "url": "https://example.test/replay",
        "snippet": "Deterministic replay turns a production failure into a local test case.",
    },
    {
        "title": "Baselines for agent latency and token use",
        "url": "https://example.test/baselines",
        "snippet": "Comparing a run with the agent's own history catches regressions early.",
    },
]


class SearchApi:
    """`schema_version` 1 answers `{"results": [...]}`; version 2 answers `{"data": [...], "meta": {...}}`."""

    def __init__(self, schema_version: int = 1, latency: float = 0.35) -> None:
        self.schema_version = schema_version
        self.latency = latency

    def search(self, query: str, max_results: int = 3) -> dict:
        timing.wait(self.latency)
        words = [word for word in query.lower().split() if len(word) > 3]
        scored = sorted(
            CORPUS,
            key=lambda doc: -sum(word in (doc["title"] + " " + doc["snippet"]).lower() for word in words),
        )
        hits = scored[:max_results]
        if self.schema_version == 1:
            return {"results": hits, "total": len(hits)}
        return {"data": hits, "meta": {"total": len(hits), "api_version": "2026-11"}}
