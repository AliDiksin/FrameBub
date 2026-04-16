import os
import re

import discord

is_missing_attack_range_value = None
truncate_message = None
send_deleted_message_failsafe = None
get_frame_row_gif_links = None
get_existing_local_gif_asset_paths = None
is_deleted_message_reference_error = None
RANGE_SCROLLS_MISSING_TEXT = "the range of that move is not on the supercombo scrolls"


def configure(**deps):
    globals().update(deps)


def get_attack_range_details(row):
    raw_value = str(row.get("atkRange", "")).strip()
    if is_missing_attack_range_value(raw_value):
        return "", False
    return raw_value, True


def format_attack_range_for_table(row):
    range_value, has_numeric_range = get_attack_range_details(row)
    if has_numeric_range:
        return range_value
    return "not on supercombo scrolls"

def format_frame_data(row):
    """Format a frame data row into readable text."""
    atk_range = format_attack_range_for_table(row)
    return (
        f"Move: {row['moveName']} ({row['numCmd']})\n"
        f"Startup: {row['startup']}f | Active: {row['active']}f | Recovery: {row['recovery']}f\n"
        f"Range: {atk_range}\n"
        f"On Hit: {row['onHit']} | On Block: {row['onBlock']}\n"
        f"Damage: {row['dmg']} | Attack Type: {row['atkLvl']}\n"
        f"Notes: {row.get('extraInfo', '')}"
    )


def format_property_only_lines(lines, limit=1800):
    cleaned_lines = [str(line).strip() for line in (lines or []) if str(line).strip()]
    if not cleaned_lines:
        return ""
    return truncate_message("\n".join(cleaned_lines), limit=limit)


def format_startup_only_reply(rows):
    lines = []
    seen = set()
    for row in rows:
        key = (
            row.get("char_name", "Unknown"),
            row.get("moveName", "Unknown"),
            row.get("numCmd", "?"),
        )
        if key in seen:
            continue
        seen.add(key)
        startup_raw = str(row.get("startup", "-")).replace("*", ",").strip()
        startup = startup_raw if startup_raw else "-"
        startup_suffix = "f" if any(ch.isdigit() for ch in startup) and not startup.endswith("f") else ""
        char_name = row.get("char_name", "Unknown")
        move_name = row.get("moveName", "Unknown")
        num_cmd = row.get("numCmd", "?")
        lines.append(f"{char_name}'s {move_name} ({num_cmd}) startup is {startup}{startup_suffix}.")
    return format_property_only_lines(lines)


def format_hitconfirm_only_reply(rows):
    lines = []
    seen = set()
    for row in rows:
        key = (
            row.get("char_name", "Unknown"),
            row.get("moveName", "Unknown"),
            row.get("numCmd", "?"),
        )
        if key in seen:
            continue
        seen.add(key)
        char_name = row.get("char_name", "Unknown")
        move_name = row.get("moveName", "Unknown")
        num_cmd = row.get("numCmd", "?")
        hc_sp = str(row.get("hcWinSpCa", "-")).replace("*", ",").strip() or "-"
        hc_tc = str(row.get("hcWinTc", "-")).replace("*", ",").strip() or "-"
        hc_notes = str(row.get("hcWinNotes", "-")).replace("[", "").replace("]", "").replace('"', "").strip() or "-"
        lines.append(
            f"{char_name}'s {move_name} ({num_cmd}) hit confirm window is Sp/Su: {hc_sp}, TC: {hc_tc}. Notes: {hc_notes}"
        )
    return format_property_only_lines(lines)


def format_super_gain_only_reply(rows):
    lines = []
    seen = set()
    for row in rows:
        key = (
            row.get("char_name", "Unknown"),
            row.get("moveName", "Unknown"),
            row.get("numCmd", "?"),
        )
        if key in seen:
            continue
        seen.add(key)
        char_name = row.get("char_name", "Unknown")
        move_name = row.get("moveName", "Unknown")
        num_cmd = row.get("numCmd", "?")
        super_hit = str(row.get("SelfSoH", "-")).replace("*", ",").strip() or "-"
        super_block = str(row.get("SelfSoB", "-")).replace("*", ",").strip() or "-"
        lines.append(
            f"{char_name}'s {move_name} ({num_cmd}) super gain is Hit: {super_hit}, Block: {super_block}."
        )
    return format_property_only_lines(lines)


def format_range_only_reply(rows):
    unique_rows = []
    seen = set()
    for row in rows:
        key = (
            row.get("char_name", "Unknown"),
            row.get("moveName", "Unknown"),
            row.get("numCmd", "?"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)

    if not unique_rows:
        return ""

    if len(unique_rows) == 1:
        row = unique_rows[0]
        range_value, has_numeric_range = get_attack_range_details(row)
        if not has_numeric_range:
            return RANGE_SCROLLS_MISSING_TEXT
        char_name = row.get("char_name", "Unknown")
        move_name = row.get("moveName", "Unknown")
        num_cmd = row.get("numCmd", "?")
        return f"{char_name}'s {move_name} ({num_cmd}) range is {range_value}."

    lines = []
    for row in unique_rows:
        char_name = row.get("char_name", "Unknown")
        move_name = row.get("moveName", "Unknown")
        num_cmd = row.get("numCmd", "?")
        range_value, has_numeric_range = get_attack_range_details(row)
        if has_numeric_range:
            lines.append(f"{char_name}'s {move_name} ({num_cmd}) range is {range_value}.")
        else:
            lines.append(
                f"{char_name}'s {move_name} ({num_cmd}): {RANGE_SCROLLS_MISSING_TEXT}"
            )
    return format_property_only_lines(lines)


def truncate_embed_value(value, limit):
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + "..."


def is_missing_embed_value(value):
    text = str(value if value is not None else "").strip().lower()
    return text in {"", "-", "--", "n/a", "na", "none", "null", "nan"}


def clean_embed_value(value, default="", strip_brackets=False):
    text = str(value if value is not None else "").replace("*", ",").strip()
    if strip_brackets:
        text = text.replace("[", "").replace("]", "").replace('"', "")
    if is_missing_embed_value(text):
        text = default
    return text


def add_embed_field(embed, name, value, inline=True):
    if is_missing_embed_value(value):
        return
    safe_name = truncate_embed_value(name, 256) or "-"
    safe_value = truncate_embed_value(value, 1024)
    if is_missing_embed_value(safe_value):
        return
    embed.add_field(name=safe_name, value=safe_value, inline=inline)


def format_hit_block_value(hit_value, block_value):
    hit = clean_embed_value(hit_value)
    block = clean_embed_value(block_value)
    parts = []
    if hit:
        parts.append(f"Hit: {hit}")
    if block:
        parts.append(f"Block: {block}")
    return " / ".join(parts)


def build_frame_embed(row):
    char_name = clean_embed_value(row.get("char_name", "Unknown"), default="Unknown")
    move_name = clean_embed_value(row.get("moveName", "Unknown"), default="Unknown")
    num_cmd = clean_embed_value(row.get("numCmd", "?"), default="?")

    embed = discord.Embed(
        title=truncate_embed_value(char_name, 256),
        description=truncate_embed_value(f"{move_name} ({num_cmd})", 4096),
        colour=0x3998C6,
    )

    startup = clean_embed_value(row.get("startup", ""))
    active = clean_embed_value(row.get("active", ""))
    recovery = clean_embed_value(row.get("recovery", "")).replace("(", " (Whiff: ")
    cancel = clean_embed_value(row.get("xx", ""))
    damage = clean_embed_value(row.get("dmg", ""))
    guard = clean_embed_value(row.get("atkLvl", ""))
    atk_range = format_attack_range_for_table(row)
    on_hit = clean_embed_value(row.get("onHit", ""))
    on_block = clean_embed_value(row.get("onBlock", ""))

    drive_hit = clean_embed_value(row.get("DDoH", ""))
    drive_block = clean_embed_value(row.get("DDoB", ""))
    drive_gain = clean_embed_value(row.get("DGain", ""))
    super_hit = clean_embed_value(row.get("SelfSoH", ""))
    super_block = clean_embed_value(row.get("SelfSoB", ""))

    stun_hit = clean_embed_value(row.get("hitstun", ""))
    stun_block = clean_embed_value(row.get("blockstun", ""))

    hc_sp = clean_embed_value(row.get("hcWinSpCa", ""))
    hc_tc = clean_embed_value(row.get("hcWinTc", ""))
    hc_notes = clean_embed_value(row.get("hcWinNotes", ""), strip_brackets=True)

    add_embed_field(embed, "Startup", startup, inline=True)
    add_embed_field(embed, "Active", active, inline=True)
    add_embed_field(embed, "Recovery", recovery, inline=True)

    add_embed_field(embed, "On Hit", on_hit, inline=True)
    add_embed_field(embed, "On Block", on_block, inline=True)
    add_embed_field(embed, "Cancel", cancel, inline=True)

    add_embed_field(embed, "Damage", damage, inline=True)
    add_embed_field(embed, "Guard", guard, inline=True)
    add_embed_field(embed, "Range", atk_range, inline=True)
    add_embed_field(embed, "Drive Gain", drive_gain, inline=True)

    add_embed_field(embed, "Drive Dmg", format_hit_block_value(drive_hit, drive_block), inline=True)
    add_embed_field(embed, "Super Gain", format_hit_block_value(super_hit, super_block), inline=True)
    add_embed_field(embed, "Stun", format_hit_block_value(stun_hit, stun_block), inline=True)

    add_embed_field(embed, "Hit Confirm (Sp/Su)", hc_sp, inline=True)
    add_embed_field(embed, "Hit Confirm (TC)", hc_tc, inline=True)
    add_embed_field(embed, "Hit Confirm Notes", hc_notes, inline=False)

    extra_info = clean_embed_value(row.get("extraInfo", ""), strip_brackets=True)
    if extra_info:
        embed.set_footer(text=truncate_embed_value(extra_info, 2048))

    return embed


def iter_unique_frame_rows(rows):
    seen = set()
    unique_rows = []
    for row in rows or []:
        key = (
            row.get("char_name", "Unknown"),
            row.get("moveName", "Unknown"),
            row.get("numCmd", "?"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
    return unique_rows


def build_frame_embeds(rows):
    embeds = []
    for row in iter_unique_frame_rows(rows):
        embeds.append(build_frame_embed(row))
    return embeds


def sanitize_embed_followup_text(text):
    raw = str(text or "").strip()
    if not raw:
        return "Noted. The relevant frame data is in the embeds above."

    table_markers = [
        "Startup:",
        "Active:",
        "Recovery:",
        "Range:",
        "On Hit:",
        "On Block:",
        "Drive Dmg",
        "Super Gain",
        "Hit Confirm",
        "Stun Frames",
        "Character:",
    ]
    filtered_lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(marker in stripped for marker in table_markers):
            continue
        if stripped.startswith("**") and stripped.endswith("**"):
            continue
        filtered_lines.append(stripped)

    cleaned = "\n".join(filtered_lines).strip()
    if cleaned:
        return cleaned

    sentence_candidates = re.split(r"(?<=[.!?])\s+", raw)
    for sentence in sentence_candidates:
        sentence = sentence.strip()
        if sentence:
            return sentence
    return "Noted. The relevant frame data is in the embeds above."

class FrameDataGifButton(discord.ui.Button):
    def __init__(self, row, gif_links):
        super().__init__(label="Show GIF", style=discord.ButtonStyle.primary, disabled=not gif_links)
        self.frame_row = row
        self.gif_links = list(gif_links or [])

    async def callback(self, interaction: discord.Interaction):
        move_name = str((self.frame_row or {}).get("moveName", "This move")).strip() or "This move"
        if not self.gif_links:
            await interaction.response.send_message(
                f"I have frame data for {move_name} but no hitbox gif link yet.",
                ephemeral=True,
            )
            return

        asset_paths = get_existing_local_gif_asset_paths(self.gif_links, limit=4)
        if asset_paths:
            if len(asset_paths) == 1:
                await interaction.response.send_message(
                    file=discord.File(asset_paths[0], filename=os.path.basename(asset_paths[0]))
                )
                return

            await interaction.response.send_message(
                files=[discord.File(path, filename=os.path.basename(path)) for path in asset_paths[:4]]
            )
            return

        if len(self.gif_links) == 1:
            await interaction.response.send_message(self.gif_links[0])
            return

        await interaction.response.send_message("\n".join(self.gif_links[:4]))


class FrameDataGifView(discord.ui.View):
    def __init__(self, row):
        super().__init__(timeout=3600)
        self.add_item(FrameDataGifButton(row, get_frame_row_gif_links(row)))


async def send_frame_embeds_with_views(channel, rows, embeds=None):
    unique_rows = iter_unique_frame_rows(rows or [])
    embed_list = list(embeds or build_frame_embeds(unique_rows))
    if not embed_list:
        return False

    for index, embed in enumerate(embed_list):
        view = FrameDataGifView(unique_rows[index]) if index < len(unique_rows) else None
        await channel.send(embed=embed, view=view)
    return True


async def send_frame_table_response(message, rows, data_text):
    unique_rows = iter_unique_frame_rows(rows or [])
    if unique_rows:
        try:
            await send_frame_embeds_with_views(message.channel, unique_rows)
            return True
        except Exception as e:
            print(f"Direct frame embed send failed: {e}", flush=True)
    return False


async def send_gif_links_response(message, gif_links, wants_comparison=False):
    if not gif_links:
        return False
    try:
        asset_limit = 6 if wants_comparison else 1
        asset_paths = get_existing_local_gif_asset_paths(gif_links, limit=asset_limit)
        if asset_paths:
            if wants_comparison and len(asset_paths) > 1:
                await message.reply(
                    files=[discord.File(path, filename=os.path.basename(path)) for path in asset_paths]
                )
            else:
                await message.reply(
                    file=discord.File(asset_paths[0], filename=os.path.basename(asset_paths[0]))
                )
            return True

        if wants_comparison and len(gif_links) > 1:
            await message.reply("\n".join(gif_links))
        else:
            await message.reply(gif_links[0])
        return True
    except Exception as reply_error:
        if is_deleted_message_reference_error(reply_error):
            print("Hitbox gif reply target deleted. Triggering failsafe.", flush=True)
            await send_deleted_message_failsafe(message.channel)
        else:
            print(f"Hitbox gif reply error: {reply_error}", flush=True)
    return False
