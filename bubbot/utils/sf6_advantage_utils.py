"""SF6 on-hit advantage helpers for property-only replies."""

import re

SF6_COUNTER_HIT_HIT_BONUS = 2
SF6_PUNISH_COUNTER_HIT_BONUS = 4


def clean_advantage_value(value):
    if value is None:
        return "-"
    text = str(value).replace("*", ",").strip()
    return text if text else "-"


def apply_sf6_hit_advantage_bonus(on_hit_raw, bonus):
    if not bonus:
        return clean_advantage_value(on_hit_raw)

    text = clean_advantage_value(on_hit_raw)
    if text in {"", "-", "~"}:
        return text

    def add_bonus(match):
        sign = match.group(1) or ""
        num = int(match.group(2))
        new_num = num + bonus
        if sign == "-":
            return str(new_num)
        if new_num > 0 and sign == "+":
            return f"+{new_num}"
        return str(new_num)

    return re.sub(r"(?<![\d])(\+|-)?(\d+)", add_bonus, text)


def format_sf6_frame_advantage_value(row, *, mode="frame_advantage"):
    on_hit = clean_advantage_value(row.get("onHit"))
    on_block = clean_advantage_value(row.get("onBlock"))
    counter_hit = apply_sf6_hit_advantage_bonus(on_hit, SF6_COUNTER_HIT_HIT_BONUS)
    punish_counter = apply_sf6_hit_advantage_bonus(on_hit, SF6_PUNISH_COUNTER_HIT_BONUS)

    if mode == "counter_hit":
        return counter_hit
    if mode == "punish_counter":
        return punish_counter
    if mode == "counter_hit_adv":
        return counter_hit
    return f"On Hit: {on_hit}, On Block: {on_block}"
