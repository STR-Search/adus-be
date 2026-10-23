from pydantic import BaseModel

from app.core.analytics.schemas import Breakdown
from app.iron_bank.schemas.underwriting_analytics import (
    JobTypeHealth,
    UnderwritingCompleteness,
)
from app.zillow.schemas.listing_analytics import PresetRun, StaleListings


class Automation(BaseModel):
    # Metric 3: automated / manual / unknown underwritings.
    underwritings: Breakdown
    # Metric 4: batch job outcomes per job type.
    jobs: list[JobTypeHealth]
    # Metric 4: last run per active saved search, most in need of attention first.
    presets: list[PresetRun]


class DataCompleteness(BaseModel):
    underwritings: UnderwritingCompleteness
    stale_listings: StaleListings
