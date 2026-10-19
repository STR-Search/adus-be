"""What the agent understood about the client (spec §5.4).

The agent writes this through ``update_client_profile``; every extracted item
carries the quote it came from so the team can check the reading.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Goal(_Strict):
    metric: str = Field(description="tax_savings, cash_on_cash, one_pct_rule, appreciation, personal_use, ...")
    importance: int = Field(ge=1, le=5)
    quote: str | None = None


class Budget(_Strict):
    target_oop: float | None = None
    max_oop: float | None = None
    quote: str | None = None


class Financing(_Strict):
    down_payment_pct: float | None = Field(default=None, description="0.10 for 10% down")
    interest_rate: float | None = Field(default=None, description="0.07 for 7%; null keeps each deal's stored rate")
    cohost_fee_pct: float | None = Field(default=None, description="Display only in v1")


class Location(_Strict):
    preferred_states: list[str] = Field(default_factory=list, description="Two-letter codes")
    excluded_states: list[str] = Field(default_factory=list)
    notes: str | None = None
    quote: str | None = None


class PropertyPrefs(_Strict):
    turnkey_preference: Literal["required", "preferred", "neutral", "avoid"] | None = None
    value_add_ok: bool | None = None
    amenities_wanted: list[str] = Field(default_factory=list)
    bedrooms_min: int | None = None


class Benchmark(_Strict):
    name: str
    quote: str | None = None


class DealReaction(_Strict):
    label: str
    underwriting_id: int | None = None
    sentiment: Literal["positive", "negative", "mixed"]
    reason: str | None = None
    quote: str | None = None


class ClientProfile(_Strict):
    client_label: str
    call_date: str | None = None
    goals: list[Goal] = Field(default_factory=list)
    budget: Budget = Field(default_factory=Budget)
    financing: Financing = Field(default_factory=Financing)
    location: Location = Field(default_factory=Location)
    property: PropertyPrefs = Field(default_factory=PropertyPrefs)
    benchmarks: list[Benchmark] = Field(default_factory=list)
    deal_reactions: list[DealReaction] = Field(default_factory=list)
    already_shown: list[str] = Field(default_factory=list)
    already_shown_ids: list[int] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
