"""A fake support knowledge base that can rate-limit its first calls."""

from __future__ import annotations

from fake_services.timing import timing

ARTICLES = {
    "billing": [
        {"id": "KB-101", "title": "How refunds are processed", "body": "Refunds reach the card in 5-7 days."}
    ],
    "access": [
        {"id": "KB-204", "title": "Resetting two-factor login", "body": "Use a recovery code, then re-enrol."}
    ],
    "bug": [
        {
            "id": "KB-330",
            "title": "Reporting a reproducible bug",
            "body": "Include steps, expected and actual.",
        }
    ],
}


class RateLimited(Exception):
    """HTTP 429 from the knowledge base."""


class KnowledgeBase:
    """The first `rate_limited_calls` lookups raise `RateLimited`; later ones succeed."""

    def __init__(self, rate_limited_calls: int = 0, latency: float = 0.25) -> None:
        self.rate_limited_calls = rate_limited_calls
        self.latency = latency
        self._calls = 0

    def reset(self) -> None:
        self._calls = 0

    def lookup(self, category: str) -> dict:
        timing.wait(self.latency)
        self._calls += 1
        if self._calls <= self.rate_limited_calls:
            raise RateLimited("HTTP 429 Too Many Requests")
        return {"articles": ARTICLES.get(category, [])}
