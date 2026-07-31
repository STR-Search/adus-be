from app.iron_bank.schemas.underwriting import (
    MULTI_SELECT_TAG_FIELDS,
    SINGLE_SELECT_TAG_FIELDS,
)


async def apply_reference_labels(rows, reference_data_service) -> None:
    """Resolve ``<field>_label`` for each tag slug on the given rows, in place.

    Shared by the read path (``GetUnderwritingService``) and the deal-status
    webhook payload (``UpdateUnderwritingService``) so the two can't drift:
    anything carrying tag slugs gets the same labels resolved the same way.

    Fetches the ``(set_code, slug) → label`` map once for the whole batch;
    no-op when no reference-data service is configured. Single-select fields
    resolve to one label, multi-select fields to a list of labels (one per
    slug). Unknown/retired slugs simply leave the label ``None`` (single) or
    drop out of the list (multi).
    """
    if reference_data_service is None or not rows:
        return
    label_map = await reference_data_service.get_label_map(domain="iron_bank")
    for row in rows:
        for field in SINGLE_SELECT_TAG_FIELDS:
            slug = getattr(row, field, None)
            if slug is not None:
                setattr(row, f"{field}_label", label_map.get((field, slug)))
        for field in MULTI_SELECT_TAG_FIELDS:
            slugs = getattr(row, field, None)
            if slugs:
                setattr(
                    row,
                    f"{field}_label",
                    [
                        label_map[(field, slug)]
                        for slug in slugs
                        if (field, slug) in label_map
                    ],
                )
