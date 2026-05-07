def truncate_value(value, limit):
    """Safely truncate text to a Discord field/name limit."""
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + "..."


def is_missing_value(value):
    text = str(value if value is not None else "").strip().lower()
    return text in {"", "-", "--", "n/a", "na", "none", "null", "nan"}


def clean_value(value, default="", *, strip_brackets=False):
    """Clean spreadsheet/Discord display values while preserving existing project behavior."""
    text = str(value if value is not None else "").replace("*", ",").strip()
    if strip_brackets:
        text = text.replace("[", "").replace("]", "").replace('"', "")
    if is_missing_value(text):
        return default
    return text


def add_embed_field(embed, name, value, *, inline=True):
    if is_missing_value(value):
        return
    safe_name = truncate_value(name, 256) or "-"
    safe_value = truncate_value(value, 1024)
    if is_missing_value(safe_value):
        return
    embed.add_field(name=safe_name, value=safe_value, inline=inline)


def add_long_embed_field(embed, name, value, *, inline=False, chunk_limit=1024):
    text = clean_value(value)
    if not text:
        return
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= chunk_limit:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n\n", 0, chunk_limit)
        if split_at <= 0:
            split_at = remaining.rfind("\n", 0, chunk_limit)
        if split_at <= 0:
            split_at = remaining.rfind(" ", 0, chunk_limit)
        if split_at <= 0:
            split_at = chunk_limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    for index, chunk in enumerate(chunks[:3]):
        field_name = name if index == 0 else f"{name} (cont.)"
        add_embed_field(embed, field_name, chunk, inline=inline)
