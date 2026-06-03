import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ScheduledListingDetailSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    zpid: str
    preset_id: uuid.UUID
    city: str | None = None
    state: str | None = None
    home_status: str | None = None
    address: dict | None = None
    bedrooms: int | None = None
    bathrooms: float | None = None
    price: float | None = None
    year_built: int | None = None
    street_address: str | None = None
    zipcode: str | None = None
    home_type: str | None = None
    monthly_hoa_fee: float | None = None
    living_area: int | None = None
    living_area_value: float | None = None
    zestimate: float | None = None
    rent_zestimate: float | None = None
    schools: list | None = None
    tax_history: list | None = None
    price_history: list | None = None
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    broker_name: str | None = None
    lot_size_sqft: float | None = None
    lot_size_acre: float | None = None
    original_photos: list | None = None
    photo_count: int | None = None
    mortgage_rates: dict | None = None
    price_change: float | None = None
    price_change_date: date | None = None
    last_sold_price: float | None = None
    reso_facts: dict | None = None
    home_insights: str | None = None
    view: str | None = None
    sewer: str | None = None
    cooling: str | None = None
    heating: str | None = None
    furnished: bool | None = None
    parking_capacity: float | None = None
    has_garage: bool | None = None
    fencing: str | None = None
    flooring: str | None = None
    pool_features: str | None = None
    agent_name: str | None = None
    agent_contact_info: str | None = None
    broker_contact_info: str | None = None
    mlsid: str | None = None
    mls_name: str | None = None
    neighborhood_name: str | None = None
    parcel_id: str | None = None
    tax_assessed_value: float | None = None
    last_updated_in_zillow: datetime | None = None
    keep_updated: bool | None = None
    remove_listing: bool | None = None
    updated_at: datetime | None = None


class PaginatedScheduledListingDetails(BaseModel):
    items: list[ScheduledListingDetailSchema]
    total: int
    pages: int
