"""GGST Discord formatting, embeds, and response helpers."""
# Output formatting stays separate from GGST parsing so source rows remain reusable by menus and slash commands.

import json

import discord

from bubbot.utils.discord_formatting import (
    add_embed_field as shared_add_embed_field,
    add_long_embed_field as shared_add_long_embed_field,
    clean_value as shared_clean_value,
    truncate_value as shared_truncate_value,
)

GGST_MOVE_IMAGE_URLS = {}
GGST_HITBOX_DATA = {}
GGST_MOVE_NOTES = {}
normalize_move_token = None
resize_mediawiki_thumb_url = None


def configure(**deps):
    globals().update(deps)
def clean_value(value, default=""):
    return shared_clean_value(value, default)


def truncate_value(value, limit):
    return shared_truncate_value(value, limit)


def add_embed_field(embed, name, value, inline=True):
    shared_add_embed_field(embed, name, clean_value(value), inline=inline)


def add_long_embed_field(embed, name, value, inline=False, chunk_limit=1024):
    shared_add_long_embed_field(embed, name, clean_value(value), inline=inline, chunk_limit=chunk_limit)


def format_jsonish_list(value):
    text = clean_value(value)
    if not text:
        return ""
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        try:
            parts = json.loads(text)
            if isinstance(parts, list):
                return ", ".join(str(part).strip() for part in parts if str(part).strip())
        except Exception:
            pass
        text = text.strip("[]")
        parts = [part.strip().strip('"\'') for part in text.split(",")]
        return ", ".join(part for part in parts if part)
    return text


def get_notes_text(row):
    char_key = str(row.get("char_key", "")).strip().lower()
    num_cmd_key = normalize_move_token(row.get("numCmd", ""))
    cached_notes = (GGST_MOVE_NOTES.get(char_key, {}) or {}).get(num_cmd_key)
    if cached_notes:
        return cached_notes
    return format_jsonish_list(row.get("extraInfo"))


def format_frame_data(row, include_notes=False):
    text = (
        f"Move: {clean_value(row.get('moveName'))} ({clean_value(row.get('numCmd'))})\n"
        f"Startup: {clean_value(row.get('startup'), '-')}f | Active: {clean_value(row.get('active'), '-')}f | Recovery: {clean_value(row.get('recovery'), '-')}f\n"
        f"On Hit: {clean_value(row.get('onHit'), '-')} | On Block: {clean_value(row.get('onBlock'), '-')}\n"
        f"Damage: {clean_value(row.get('dmg'), '-')} | Guard: {clean_value(row.get('guardLevel'), '-')} | Attack Level: {clean_value(row.get('atkLvl'), '-')}\n"
        f"RISC Gain: {clean_value(row.get('riscGain'), '-')} | Proration: {clean_value(row.get('prorate'), '-')} | Knockdown Adv: {clean_value(row.get('kda'), '-')}"
    )
    notes = get_notes_text(row)
    if include_notes and notes:
        text += f"\nNotes: {notes}"
    return text


def get_move_image_url(row):
    return resize_mediawiki_thumb_url(
        GGST_MOVE_IMAGE_URLS.get(
            (str(row.get("char_key", "")).strip().lower(), normalize_move_token(row.get("numCmd", "")))
        )
    )


def build_frame_embed(row, show_notes=False):
    char_name = clean_value(row.get("char_name"), "Unknown")
    move_name = clean_value(row.get("moveName"), "Unknown")
    num_cmd = clean_value(row.get("numCmd"), "?")
    embed = discord.Embed(
        title=truncate_value(f"GGST - {char_name}", 256),
        description=truncate_value(f"{move_name} ({num_cmd})", 4096),
        colour=0x7A2BFF,
    )
    add_embed_field(embed, "Startup", row.get("startup"), inline=True)
    add_embed_field(embed, "Active", row.get("active"), inline=True)
    add_embed_field(embed, "Recovery", row.get("recovery"), inline=True)
    add_embed_field(embed, "Total", row.get("total"), inline=True)
    add_embed_field(embed, "On Hit", row.get("onHit"), inline=True)
    add_embed_field(embed, "On Block", row.get("onBlock"), inline=True)
    add_embed_field(embed, "Damage", row.get("dmg"), inline=True)
    add_embed_field(embed, "RISC Gain", row.get("riscGain"), inline=True)
    add_embed_field(embed, "Knockdown Adv", row.get("kda"), inline=True)
    add_embed_field(embed, "Counter Hit Adv", row.get("chAdv"), inline=True)
    add_embed_field(embed, "Guard", row.get("guardLevel"), inline=True)
    add_embed_field(embed, "Attack Level", row.get("atkLvl"), inline=True)
    add_embed_field(embed, "Cancel", format_jsonish_list(row.get("xx")), inline=True)
    add_embed_field(embed, "Gatling", format_jsonish_list(row.get("gatling")), inline=True)
    if show_notes:
        add_long_embed_field(embed, "Notes", get_notes_text(row), inline=False)
    image_url = get_move_image_url(row)
    if image_url:
        embed.set_image(url=image_url)
    return embed


def get_hitbox_links(row, limit=None):
    char_key = str(row.get("char_key", "")).strip().lower()
    num_cmd_key = normalize_move_token(row.get("numCmd", ""))
    char_links = GGST_HITBOX_DATA.get(char_key, {})
    links = char_links.get(num_cmd_key, []) if isinstance(char_links, dict) else []
    clean_links = [resize_mediawiki_thumb_url(link) for link in list(links or []) if str(link or "").strip()]
    return clean_links[:limit] if limit is not None else clean_links


def get_media_links(row, limit=None):
    links = get_hitbox_links(row, limit=None)
    image_url = get_move_image_url(row)
    if image_url and image_url not in links:
        links.append(image_url)
    return links[:limit] if limit is not None else links






class GGSTNotesButton(discord.ui.Button):
    def __init__(self, row):
        self.frame_row = row
        self.notes_text = get_notes_text(row)
        super().__init__(
            label="Show Notes",
            style=discord.ButtonStyle.primary,
            disabled=not self.notes_text,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if not hasattr(self.view, "build_embed"):
            await interaction.response.defer()
            return
        self.view.show_notes = not self.view.show_notes
        self.label = "Hide Notes" if self.view.show_notes else "Show Notes"
        self.style = discord.ButtonStyle.danger if self.view.show_notes else discord.ButtonStyle.primary
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view, attachments=self.view.initial_files())


async def send_frame_response(message, rows):
    from bubbot.features.menu_system import send_frame_result_messages

    return await send_frame_result_messages(
        message.channel,
        "ggst",
        rows,
        owner_id=getattr(message.author, "id", None),
        menu_locked=False,
        source_message=message,
        prompt=str(getattr(message, "content", "") or ""),
    )


async def send_hitbox_response(message, rows):
    if not rows:
        return []
    links = []
    for row in rows:
        links.extend(get_media_links(row))
    if not links:
        sent = await message.reply("I have GGST frame data for this move but no image link yet.")
        return [sent.id]
    sent = await message.reply("\n".join(links))
    return [sent.id]
