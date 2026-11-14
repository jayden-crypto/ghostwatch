"""Time for the fake services: real when a scenario runs live, simulated when history is seeded.

Each fake service call takes a fixed base latency with a small seeded variation. Live, that is a
real `time.sleep`. While seeding, the same latency advances a simulated clock instead, so a week
of backdated history is produced in seconds and has the same durations a live run would have.
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timedelta, timezone


class Timing:
    def __init__(self) -> None:
        self._simulated: datetime | None = None
        self._random = random.Random(0)

    def use_real_time(self) -> None:
        self._simulated = None

    def use_simulated_time(self, start: datetime) -> None:
        self._simulated = start

    def reseed(self, seed: int) -> None:
        """Fix the latency variation, so the same seed always gives the same durations."""
        self._random = random.Random(seed)

    def now(self) -> datetime:
        if self._simulated is None:
            return datetime.now(timezone.utc)
        self._simulated += timedelta(milliseconds=1)  # reading the clock is never free
        return self._simulated

    def wait(self, base_seconds: float) -> None:
        """Take as long as a call with this base latency would."""
        seconds = base_seconds * self._random.uniform(0.85, 1.15)
        if self._simulated is None:
            time.sleep(seconds)
        else:
            self._simulated += timedelta(seconds=seconds)


timing = Timing()
