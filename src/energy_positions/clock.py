"""Time as a service.

Code that needs to know what the time is asks a Clock for it, and does not call
datetime.now() itself. In production the clock is the system's. In a test it is
whatever instant the test is about, so a test can stand inside the repeated hour of
a clock-change day without waiting for October.

The settlement module takes no clock. It answers questions about instants it is
given; only code that asks "what is now?" needs one of these.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """The current instant, as an aware datetime in UTC."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True)
class FixedClock:
    """A clock stopped at one instant."""

    instant: datetime

    def __post_init__(self) -> None:
        if self.instant.tzinfo is None or self.instant.utcoffset() is None:
            raise ValueError(
                f"a clock tells an instant, so it must carry a time zone; got the naive {self.instant.isoformat()}"
            )
        object.__setattr__(self, "instant", self.instant.astimezone(UTC))

    def now(self) -> datetime:
        return self.instant


def get_clock() -> Clock:
    """The FastAPI dependency. Tests replace it through app.dependency_overrides."""
    return SystemClock()
