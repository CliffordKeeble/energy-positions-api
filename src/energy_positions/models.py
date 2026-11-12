"""What goes over the wire.

Volumes and prices are Decimal from the database to the JSON, where they are written
as strings ("12.500"), so no figure passes through a binary float on the way.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field

from energy_positions.settlement import SettlementPeriod

# The same shapes as the columns in sql/schema.sql.
Volume = Annotated[Decimal, Field(max_digits=12, decimal_places=3)]
Price = Annotated[Decimal, Field(max_digits=10, decimal_places=2)]

ZERO_MWH = Decimal("0.000")


class Position(BaseModel):
    """A portfolio's net volume in one settlement period."""

    settlement_period: SettlementPeriod
    net_mwh: Decimal


class DailyTotal(BaseModel):
    """A portfolio's net volume over one settlement date."""

    settlement_date: date
    net_mwh: Decimal


class TradeIn(BaseModel):
    portfolio_id: int = Field(gt=0)
    period_start: SettlementPeriod = Field(
        description="The settlement period, named by the UTC instant it starts at: "
        "on the hour or the half-hour, with a time zone.",
        examples=["2026-10-25T01:00:00Z"],
    )
    volume_mwh: Volume = Field(description="Positive is bought, negative is sold.", examples=["12.500"])
    price: Price = Field(description="Per MWh.", examples=["84.20"])


class Trade(BaseModel):
    id: int
    portfolio_id: int
    settlement_period: SettlementPeriod
    volume_mwh: Decimal
    price: Decimal
    traded_at: datetime
