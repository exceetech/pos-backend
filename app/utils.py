def normalize_name(name: str) -> str:
    """
    Normalize product name:
    - Remove extra spaces
    - Convert to lowercase
    - Capitalize first letter
    """
    return name.strip().lower().capitalize()


def normalize_variant(variant):
    """
    Canonical normalization for variant names. The SINGLE source of
    truth used everywhere a variant is compared or stored, so the
    (product_id, variant_name) unique constraint actually holds and the
    autofill dropdown never shows near-duplicates.

    - None / blank        -> None
    - collapse whitespace  ("5   kg" -> "5 kg")
    - consistent casing    ("5 KG" -> "5 kg")
    """
    if variant is None:
        return None
    cleaned = " ".join(variant.split()).strip()
    if not cleaned:
        return None
    return cleaned.lower().capitalize()
