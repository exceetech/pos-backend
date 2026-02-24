def normalize_name(name: str) -> str:
    """
    Normalize product name:
    - Remove extra spaces
    - Convert to lowercase
    - Capitalize first letter
    """
    return name.strip().lower().capitalize()