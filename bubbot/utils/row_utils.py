"""Row-key construction and order-preserving deduplication."""

def row_key(row, fields=("char_name", "moveName", "numCmd")):
    """Build a tuple key from a frame-data row."""
    return tuple(row.get(field, "") for field in fields)


def unique_rows(rows, key_fn=row_key):
    """Return rows with duplicate keys removed while preserving order."""
    seen = set()
    result = []
    for row in rows or []:
        key = key_fn(row)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def first_unique_values(values, key_fn=None):
    """Return unique values in input order."""
    seen = set()
    result = []
    for value in values or []:
        key = key_fn(value) if key_fn else value
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
