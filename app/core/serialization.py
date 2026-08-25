"""Shared Pydantic serialization helpers usable from any domain's schemas."""

from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer


def serialize_plain_decimal(value: Decimal | None) -> str | None:
    """Render a Decimal without scientific notation, preserving its scale."""
    if value is None:
        return None
    return format(value, "f")


PlainDecimal = Annotated[
    Decimal,
    PlainSerializer(serialize_plain_decimal, return_type=str, when_used="json"),
]
"""Decimal field that serializes to a plain (non-exponent) string in JSON.

Use in place of an explicit ``field_serializer``::

    class Foo(BaseResponse):
        price: PlainDecimal | None = None
"""
