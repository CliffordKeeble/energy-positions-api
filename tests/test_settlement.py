"""The settlement-period rules. Pure: no database, no clock, no Docker.

2026 is the year under test. In Great Britain its clocks go forward on 29 March and
back on 25 October, both at 01:00 UTC.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import TypeAdapter, ValidationError

from energy_positions.settlement import HALF_HOUR, SettlementPeriod, count_in, periods_in

SPRING = date(2026, 3, 29)  # clocks go forward: a 23-hour day
AUTUMN = date(2026, 10, 25)  # clocks go back: a 25-hour day
ORDINARY = date(2026, 11, 12)

BST = timedelta(hours=1)
GMT = timedelta(0)


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


def every_date_of(year: int) -> list[date]:
    first = date(year, 1, 1)
    return [first + timedelta(days=i) for i in range((date(year + 1, 1, 1) - first).days)]


# --- how many periods a day has ---------------------------------------------------


@pytest.mark.parametrize(
    ("settlement_date", "expected"),
    [(SPRING, 46), (AUTUMN, 50), (ORDINARY, 48)],
    ids=["clocks-forward", "clocks-back", "ordinary"],
)
def test_count_in(settlement_date: date, expected: int) -> None:
    assert count_in(settlement_date) == expected
    assert len(periods_in(settlement_date)) == expected


def test_the_periods_of_2026_add_up_to_365_days_of_48() -> None:
    # The year starts and ends in GMT, so the short day and the long day cancel.
    assert sum(count_in(day) for day in every_date_of(2026)) == 17_520


# --- 25 October 2026: the clocks go back, and 01:00 to 02:00 happens twice ---------


def test_autumn_periods_1_to_6_start_at_these_instants() -> None:
    starts = [SettlementPeriod.from_settlement(AUTUMN, n).start_utc for n in range(1, 7)]

    assert starts == [
        utc(2026, 10, 24, 23, 0),  # period 1 is local midnight, still on BST
        utc(2026, 10, 24, 23, 30),
        utc(2026, 10, 25, 0, 0),
        utc(2026, 10, 25, 0, 30),
        utc(2026, 10, 25, 1, 0),
        utc(2026, 10, 25, 1, 30),
    ]


def test_autumn_periods_share_a_wall_time_and_differ_in_offset() -> None:
    p3, p4, p5, p6 = (SettlementPeriod.from_settlement(AUTUMN, n) for n in (3, 4, 5, 6))

    # The UK clock reads the same for 3 and 5, and for 4 and 6...
    assert p3.local_start.time() == p5.local_start.time() == time(1, 0)
    assert p4.local_start.time() == p6.local_start.time() == time(1, 30)
    # ...and only the offset says which is which.
    assert p3.local_start.utcoffset() == p4.local_start.utcoffset() == BST
    assert p5.local_start.utcoffset() == p6.local_start.utcoffset() == GMT
    # They are different periods all the same.
    assert len({p3, p4, p5, p6}) == 4
    assert p5.start_utc - p3.start_utc == timedelta(hours=1)


def test_autumn_has_a_period_50_and_no_period_51() -> None:
    assert SettlementPeriod.from_settlement(AUTUMN, 50).end_utc == utc(2026, 10, 26, 0, 0)
    with pytest.raises(ValueError):
        SettlementPeriod.from_settlement(AUTUMN, 51)


# --- 29 March 2026: the clocks go forward, and 01:00 to 02:00 never happens --------


def test_spring_period_3_starts_at_two_in_the_morning_local() -> None:
    p2 = SettlementPeriod.from_settlement(SPRING, 2)
    p3 = SettlementPeriod.from_settlement(SPRING, 3)

    assert p2.start_utc == utc(2026, 3, 29, 0, 30)
    assert p2.local_start.time() == time(0, 30)
    assert p3.start_utc == utc(2026, 3, 29, 1, 0)
    assert p3.local_start.time() == time(2, 0)
    assert p3.local_start.utcoffset() == BST


def test_spring_day_ends_at_23_00_utc() -> None:
    assert periods_in(SPRING)[-1].end_utc == utc(2026, 3, 29, 23, 0)


def test_spring_has_no_period_47() -> None:
    assert SettlementPeriod.from_settlement(SPRING, 46).number == 46
    with pytest.raises(ValueError):
        SettlementPeriod.from_settlement(SPRING, 47)


# --- the two faces agree, for every period of the year -----------------------------


def test_every_period_of_2026_round_trips_from_utc_to_label_and_back() -> None:
    instant = utc(2026, 1, 1)
    labels = set()

    while instant < utc(2027, 1, 1):
        period = SettlementPeriod(instant)
        label = (period.settlement_date, period.number)
        labels.add(label)

        assert SettlementPeriod.from_settlement(*label).start_utc == instant, label
        instant += HALF_HOUR

    assert len(labels) == 17_520  # no two instants were given the same label


def test_periods_in_agrees_with_the_labels() -> None:
    for day in (SPRING, AUTUMN, ORDINARY):
        for number, period in enumerate(periods_in(day), start=1):
            assert (period.settlement_date, period.number) == (day, number)


# --- what is refused ---------------------------------------------------------------


def test_refuses_a_naive_datetime() -> None:
    with pytest.raises(ValueError, match="naive"):
        SettlementPeriod(datetime(2026, 11, 12, 10, 0))


@pytest.mark.parametrize(
    "instant",
    [utc(2026, 11, 12, 0, 15), utc(2026, 11, 12, 0, 30, 1), utc(2026, 11, 12, 0, 0).replace(microsecond=1)],
    ids=["00:15Z", "a-second-late", "a-microsecond-late"],
)
def test_refuses_an_instant_off_the_half_hour(instant: datetime) -> None:
    with pytest.raises(ValueError, match="half-hour"):
        SettlementPeriod(instant)


@pytest.mark.parametrize("number", [0, -1, 49])
def test_refuses_a_number_outside_the_day(number: int) -> None:
    with pytest.raises(ValueError):
        SettlementPeriod.from_settlement(ORDINARY, number)


# --- a value type: arithmetic, order, equality -------------------------------------


@pytest.mark.parametrize("day", [SPRING, AUTUMN, ORDINARY])
def test_next_and_previous_are_always_thirty_minutes_of_utc(day: date) -> None:
    for period in periods_in(day):
        assert period.next().start_utc - period.start_utc == HALF_HOUR
        assert period.start_utc - period.previous().start_utc == HALF_HOUR
        assert period.next().previous() == period
        assert period.end_utc == period.next().start_utc


def test_the_last_period_of_a_day_is_followed_by_period_1_of_the_next() -> None:
    following = periods_in(AUTUMN)[-1].next()

    assert (following.settlement_date, following.number) == (date(2026, 10, 26), 1)


def test_orders_and_hashes_by_the_instant() -> None:
    periods = periods_in(AUTUMN)

    assert sorted(reversed(periods)) == periods
    assert periods[2] < periods[4]  # 01:00 BST comes before 01:00 GMT
    assert SettlementPeriod(utc(2026, 10, 25, 1, 0)) == periods[4]
    assert hash(SettlementPeriod(utc(2026, 10, 25, 1, 0))) == hash(periods[4])


def test_the_same_instant_in_another_zone_is_the_same_period() -> None:
    in_london = datetime(2026, 6, 1, 1, 0, tzinfo=ZoneInfo("Europe/London"))

    period = SettlementPeriod(in_london)

    assert period == SettlementPeriod(utc(2026, 6, 1, 0, 0))
    assert period.start_utc.utcoffset() == GMT  # held in UTC whatever it was given


def test_is_immutable() -> None:
    period = SettlementPeriod(utc(2026, 11, 12))

    with pytest.raises(AttributeError):
        period.start_utc = utc(2026, 11, 13)  # type: ignore[misc]


# --- the period in progress at an instant ------------------------------------------


@pytest.mark.parametrize(
    ("instant", "start"),
    [
        (utc(2026, 10, 25, 0, 15), utc(2026, 10, 25, 0, 0)),
        (utc(2026, 10, 25, 0, 30), utc(2026, 10, 25, 0, 30)),
        (utc(2026, 10, 25, 0, 59, 59), utc(2026, 10, 25, 0, 30)),
    ],
)
def test_containing_floors_to_the_half_hour(instant: datetime, start: datetime) -> None:
    assert SettlementPeriod.containing(instant).start_utc == start


def test_containing_refuses_a_naive_datetime() -> None:
    with pytest.raises(ValueError, match="naive"):
        SettlementPeriod.containing(datetime(2026, 10, 25, 0, 15))


# --- Pydantic ----------------------------------------------------------------------


def test_pydantic_writes_both_faces() -> None:
    period = SettlementPeriod.from_settlement(AUTUMN, 5)

    assert TypeAdapter(SettlementPeriod).dump_python(period, mode="json") == {
        "settlement_date": "2026-10-25",
        "period": 5,
        "start_utc": "2026-10-25T01:00:00Z",
    }


def test_pydantic_reads_a_period_from_its_utc_start() -> None:
    adapter = TypeAdapter(SettlementPeriod)
    expected = SettlementPeriod.from_settlement(AUTUMN, 5)

    assert adapter.validate_python("2026-10-25T01:00:00Z") == expected
    assert adapter.validate_json('"2026-10-25T02:00:00+01:00"') == expected
    assert adapter.validate_python(expected) is expected


@pytest.mark.parametrize("text", ["2026-10-25T01:00:00", "2026-10-25T01:15:00Z"], ids=["naive", "off-grid"])
def test_pydantic_passes_on_the_refusals(text: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(SettlementPeriod).validate_python(text)
