import difflib


def autocomplete_values(current, values, limit=25, cutoff=0.55):
    current_norm = str(current or "").lower().strip()
    clean_values = [str(value) for value in values or [] if str(value or "").strip()]
    if not current_norm:
        return clean_values[:limit]
    starts = [value for value in clean_values if value.lower().startswith(current_norm)]
    contains = [value for value in clean_values if current_norm in value.lower() and value not in starts]
    fuzzy = [
        value for value in clean_values
        if value not in starts
        and value not in contains
        and difflib.SequenceMatcher(None, current_norm, value.lower()).ratio() >= cutoff
    ]
    return (starts + contains + fuzzy)[:limit]


def character_choices(frame_data, display_fn=None):
    seen = set()
    choices = []
    for char_key in sorted((frame_data or {}).keys()):
        rows = (frame_data or {}).get(char_key, [])
        if display_fn:
            display = display_fn(char_key, rows)
        else:
            display = str(rows[0].get("char_name", char_key)).strip() if rows else str(char_key).title()
        display = display or str(char_key).title()
        key = display.lower()
        if key in seen:
            continue
        seen.add(key)
        choices.append((char_key, display))
    return choices


def move_choices(rows, *, label_fn=None, key_fields=("moveName", "numCmd")):
    seen = set()
    choices = []
    for row in rows or []:
        move_name = str(row.get("moveName", "")).strip()
        num_cmd = str(row.get("numCmd", "")).strip()
        if not move_name and not num_cmd:
            continue
        label = label_fn(row) if label_fn else (f"{move_name} ({num_cmd})" if num_cmd else move_name)
        key = tuple(str(row.get(field, "")).strip() for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        choices.append((row, label))
    return choices
