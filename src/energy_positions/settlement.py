"""GB settlement periods.

Electricity in Great Britain is traded and settled in half-hours called settlement
periods. A period has two faces:

* its identity is the instant it starts, in UTC;
* its business label is (settlement date, period number). The settlement date is
  the UK local calendar day, and period 1 starts at local midnight.

Because the label follows the UK clock and the identity does not, a settlement
date has 48 periods on most days, 46 on the day the clocks go forward and 50 on
the day they go back. On that last day two different periods start at the local
wall time 01:00, and two more at 01:30. Only the UTC instant tells them apart,
which is why it is the identity, and why it is what the database stores.

This module is pure. It reads no clock and no database, and every conversion
between the two faces goes through the Europe/London rules in the time zone
database, never through a fixed offset.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, TypedDict
from zoneinfo import ZoneInfo

from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema

LONDON = ZoneInfo("Europe/London")
HALF_HOUR = timedelta(minutes=30)


def _local_midnight_utc(day: date) -> datetime:
    """The instant, in UTC, at which the UK local calendar day `day` starts.

    The answer is deliberately returned in UTC. Python subtracts two datetimes that
    share a tzinfo by their wall clocks, so "next local midnight minus this local
    midnight" is 24 hours on every day of the year, clock change or not. Subtracting
    the UTC instants gives the 23, 24 or 25 hours that really pass.
    """
    return datetime(day.year, day.month, day.day, tzinfo=LONDON).astimezone(UTC)


class LabelledSettlementPeriod(TypedDict):
    """A settlement period as it is written to JSON, showing both faces: the business
    label (settlement date and period number) and the identity (the UTC start)."""

    settlement_date: date
    period: int
    start_utc: datetime


@dataclass(frozen=True, order=True, slots=True)
class SettlementPeriod:
    """One half-hour, known by the UTC instant at which it starts.

    Immutable. Two periods are equal when they start at the same instant, and they
    sort and hash by that instant.
    """

    start_utc: datetime

    def __post_init__(self) -> None:
        start = self.start_utc
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError(
                "a settlement period starts at an instant, so its datetime must carry "
                f"a time zone; got the naive {start.isoformat()}"
            )
        start = start.astimezone(UTC)
        if start.minute not in (0, 30) or start.second or start.microsecond:
            raise ValueError(
                "a settlement period starts on the hour or the half-hour; "
                f"got {start.isoformat()}"
            )
        # Frozen, so the normalised value goes in the way dataclasses does it itself.
        object.__setattr__(self, "start_utc", start)

    @classmethod
    def from_settlement(cls, settlement_date: date, number: int) -> SettlementPeriod:
        """The period with the business label (settlement date, period number)."""
        count = count_in(settlement_date)
        if not 1 <= number <= count:
            raise ValueError(
                f"settlement date {settlement_date.isoformat()} has periods 1 to "
                f"{count}; there is no period {number}"
            )
        return cls(_local_midnight_utc(settlement_date) + (number - 1) * HALF_HOUR)

    @classmethod
    def containing(cls, instant: datetime) -> SettlementPeriod:
        """The period in progress at `instant`.

        UK offsets from UTC are whole hours, so the half-hour grid is the same grid
        in UTC and in local time, and the instant can be floored in UTC.
        """
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError(
                f"an instant must carry a time zone; got the naive {instant.isoformat()}"
            )
        utc = instant.astimezone(UTC)
        return cls(utc.replace(minute=0 if utc.minute < 30 else 30, second=0, microsecond=0))

    @property
    def end_utc(self) -> datetime:
        return self.start_utc + HALF_HOUR

    @property
    def local_start(self) -> datetime:
        """The start as the UK clock shows it: an aware datetime in Europe/London."""
        return self.start_utc.astimezone(LONDON)

    @property
    def settlement_date(self) -> date:
        return self.local_start.date()

    @property
    def number(self) -> int:
        """The period number within its settlement date, counted from 1.

        Counted in elapsed half-hours since local midnight, not read off the wall
        clock: on the autumn clock-change day the wall clock shows 01:00 twice.
        """
        return (self.start_utc - _local_midnight_utc(self.settlement_date)) // HALF_HOUR + 1

    def next(self) -> SettlementPeriod:
        return SettlementPeriod(self.start_utc + HALF_HOUR)

    def previous(self) -> SettlementPeriod:
        return SettlementPeriod(self.start_utc - HALF_HOUR)

    def __str__(self) -> str:
        return f"{self.settlement_date.isoformat()} period {self.number} ({self.start_utc:%Y-%m-%dT%H:%MZ})"

    # --- Pydantic -----------------------------------------------------------------

    def _both_faces(self) -> LabelledSettlementPeriod:
        return {
            "settlement_date": self.settlement_date,
            "period": self.number,
            "start_utc": self.start_utc,
        }

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """Teach Pydantic this type, so that models and FastAPI can carry it.

        Read: from the identity alone, an aware datetime, which then passes through
        the same refusals as any other construction.
        Written: as both faces, {"settlement_date", "period", "start_utc"}.
        """
        from_instant = core_schema.no_info_after_validator_function(
            cls, core_schema.datetime_schema(tz_constraint="aware")
        )
        return core_schema.json_or_python_schema(
            json_schema=from_instant,
            python_schema=core_schema.union_schema(
                [core_schema.is_instance_schema(cls), from_instant]
            ),
            serialization=core_schema.plain_serializer_function_ser_schema(
                cls._both_faces, return_schema=handler.generate_schema(LabelledSettlementPeriod)
            ),
        )


def count_in(settlement_date: date) -> int:
    """How many settlement periods the date has: 48, or 46, or 50."""
    day_length = _local_midnight_utc(settlement_date + timedelta(days=1)) - _local_midnight_utc(
        settlement_date
    )
    return day_length // HALF_HOUR


def periods_in(settlement_date: date) -> list[SettlementPeriod]:
    """The date's periods in order, from local midnight to the next local midnight."""
    first = _local_midnight_utc(settlement_date)
    return [SettlementPeriod(first + i * HALF_HOUR) for i in range(count_in(settlement_date))]
