"""A fake language model: deterministic text and token counts, no network."""

from __future__ import annotations

import math

from fake_services.timing import timing

MODEL = "demo-llm-1"


def _tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


class FakeLLM:
    def __init__(self, latency: float = 0.45) -> None:
        self.latency = latency

    def complete(self, prompt: str, *, reply: str) -> dict:
        """Return `reply` as the model's text, with usage in the shape model APIs report it."""
        timing.wait(self.latency)
        return {"text": reply, "usage": {"input_tokens": _tokens(prompt), "output_tokens": _tokens(reply)}}
