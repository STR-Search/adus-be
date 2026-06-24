from pydantic import BaseModel, ConfigDict


class ZillowPropertyDetails(BaseModel):
    """Tolerant view over a single property object returned by the
    Zillow property-details API.

    The upstream payload is large and evolving, so unknown fields are
    allowed; we only declare the fields the mapper consumes.
    """

    model_config = ConfigDict(extra="allow")

    zpid: str | int | None = None
    price: float | None = None
    street_address: str | None = None
    city: str | None = None
    state: str | None = None
    zipcode: str | None = None
    bedrooms: int | None = None
    bathrooms: float | None = None
    living_area: int | None = None
    lot_size_sqft: float | None = None
    original_photos: list | None = None
