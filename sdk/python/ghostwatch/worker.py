"""The replay worker: runs replays requested in Ghostwatch, in the process that has the agent's code.

    worker = gw.ReplayWorker()
    worker.register(gw.Agent(slug="research-assistant", name="Research Assistant"), run_research_assistant)
    worker.run_forever()

A handler takes the original execution's input and runs the agent exactly as it normally would
(opening `gw.execution(...)` itself). The worker makes that execution the run of the replay and
applies the sandbox rule to every `@gw.tool` and `@gw.llm_call` inside it.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from ghostwatch.replay import ReplayNotPossible, ReplaySession, replaying

logger = logging.getLogger("ghostwatch")


class ReplayWorker:
    def __init__(
        self, *, api_url: str | None = None, api_key: str | None = None, timeout: float = 10.0
    ) -> None:
        import os

        self.api_url = (
            api_url or os.environ.get("GHOSTWATCH_API_URL", "http://localhost:8000/api/v1")
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("GHOSTWATCH_API_KEY", "")
        self.timeout = timeout
        self._agents: dict[str, tuple[Any, Callable[[Any], Any]]] = {}

    def register(self, agent: Any, handler: Callable[[Any], Any]) -> None:
        """`handler(input)` runs the agent for one execution input. `agent` is its `gw.Agent`."""
        self._agents[agent.slug] = (agent, handler)

    def run_forever(self, poll_interval: float = 1.0) -> None:
        logger.info("Replay worker polling %s for %s", self.api_url, ", ".join(sorted(self._agents)))
        while True:
            try:
                self.run_once()
            except OSError as exc:  # Ghostwatch unreachable: keep polling, never crash the worker
                logger.warning("Replay worker could not reach Ghostwatch: %s", exc)
            time.sleep(poll_interval)

    def run_once(self) -> list[str]:
        """Claim and run every pending replay of a registered agent. Returns the ids of the replays run."""
        ran = []
        pending = self._request("GET", "/replays?status=pending&sort=requested_at&limit=50")["items"]
        for replay in pending:
            original = self._request("GET", f"/executions/{replay['original_execution_id']}")
            slug = self._request("GET", f"/agents/{original['agent_id']}")["slug"]
            if slug not in self._agents:
                continue  # another worker has this agent's code
            try:
                claim = self._request("POST", f"/replays/{replay['id']}/claim")
            except urllib.error.HTTPError as exc:
                if exc.code == 409:
                    continue  # another worker claimed it first
                raise
            self._run(claim, *self._agents[slug])
            ran.append(replay["id"])
        return ran

    def _run(self, claim: dict[str, Any], agent: Any, handler: Callable[[Any], Any]) -> None:
        import ghostwatch as gw

        session = ReplaySession(claim)
        gw.init(agent=agent, api_url=self.api_url, api_key=self.api_key)
        logger.info("Replaying %s (%s) as replay %s", session.original["id"], session.mode, session.replay_id)
        with replaying(session):
            problem = session.problem()
            try:
                if problem is not None:
                    # Recorded as a failed execution, so the replay ends with the reason visible.
                    with gw.execution(input=None, tags=["replay"]):
                        raise ReplayNotPossible(problem)
                handler(session.original["input"])
            except Exception as exc:  # the agent failing is a result of the replay, not of the worker
                logger.info("Replay %s: the agent raised %s: %s", session.replay_id, type(exc).__name__, exc)
        if not session.started:
            logger.warning(
                "Replay %s: the handler did not open gw.execution(), so nothing was recorded",
                session.replay_id,
            )
        if not gw.flush(timeout=30):
            logger.warning("Replay %s: its events could not be delivered to Ghostwatch", session.replay_id)

    def _request(self, method: str, path: str) -> dict[str, Any]:
        request = urllib.request.Request(
            self.api_url + path,
            data=b"" if method == "POST" else None,
            headers={"Authorization": f"Bearer {self.api_key}"},
            method=method,
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read())
