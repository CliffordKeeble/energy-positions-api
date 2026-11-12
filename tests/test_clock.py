"""The clocks. Pure: no database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from energy_positions.clock import FixedClock, SystemClock, get_clock


def test_the_system_clock_tells_an_aware_utc_instant() -> None:
    before = datetime.now(UTC)
    now = SystemClock().now()
    after = datetime.now(UTC)

    assert now.utcoffset() == timedelta(0)
    assert before <= now <= after


def test_a_fixed_clock_stays_where_it_was_put() -> None:
    instant = datetime(2026, 10, 25, 0, 15, tzinfo=UTC)
    clock = FixedClock(instant)

    assert clock.now() == instant
    assert clock.now() == clock.now()


def test_a_fixed_clock_tells_its_instant_in_utc() -> None:
    clock = FixedClock(datetime(2026, 6, 1, 13, 0, tzinfo=ZoneInfo("Europe/London")))

    assert clock.now() == datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    assert clock.now().utcoffset() == timedelta(0)


def test_a_fixed_clock_refuses_a_naive_datetime() -> None:
    with pytest.raises(ValueError, match="naive"):
        FixedClock(datetime(2026, 10, 25, 0, 15))


def test_the_dependency_hands_out_the_system_clock() -> None:
    assert isinstance(get_clock(), SystemClock)
