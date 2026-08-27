def parse_minor_units(value: object) -> int:
    """Parse a money amount that must already be integer paise.

    Rejects floats and bools so JSON cannot silently coerce 4999.50 or true.
    """
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("amounts must be integer paise")
    if isinstance(value, int):
        if value < 0:
            raise ValueError("amounts must be >= 0")
        return value
    raise ValueError("amounts must be integer paise")
