import difflib
import os
import re

import discord
import pandas as pd

from bubbot.data.bbcf_aliases import BBCF_CHARACTER_ALIASES, BBCF_LOOKUP_WORDS, BBCF_MOVE_ALIASES
from bubbot.utils.character_lookup import find_alias_positions_in_text, resolve_alias_key
from bubbot.utils.comparison_utils import find_comparison_rows, is_comparison_query
from bubbot.utils.image_cache_utils import import_cache_module, merge_nested_url_cache
from bubbot.utils.row_utils import unique_rows
from bubbot.utils.text_utils import compact_key, strip_noise_words


BBCF_FRAME_DATA_FILE = "BBCF Frame Data.ods"
BBCF_FRAME_DATA = {}
BBCF_MOVE_IMAGE_URLS = {}
BBCF_HITBOX_DATA = {}
BBCF_MOVE_NOTES = {}
BBCF_MOVE_IMAGES_MODULE = "bubbot.data.bbcf_move_images"


def normalize_key(value):
    return compact_key(value).replace("the", "")


def normalize_move_token(value):
    text = str(value or "").lower().strip()
    text = text.replace("jumping", "j")
    text = re.sub(r"\b(?:jump|air)\s*\.?,?", "j.", text)
    text = text.replace("[", "hold")
    return re.sub(r"[^a-z0-9]+", "", text)


def query_has_bbcf_notation(text):
    lowered = str(text or "").lower()
    return bool(
        re.search(r"(?:^|\s)j\s*\.\s*(?:[236]?[abcd]|[0-9]{2,3}[abcd])\b", lowered)
        or re.search(r"(?:^|\s)(?:[1-9][a-d]|[0-9]{2,6}[a-d]|[1-9]?\[?[a-d](?:\+[a-d])+\]?)(?:\s|$)", lowered)
        or re.search(r"(?:^|\s)[0-9x]+(?:~[0-9x]+)*[a-d](?:~[0-9x]+[a-d])*\b", lowered)
    )


def load_move_image_urls(module_name=BBCF_MOVE_IMAGES_MODULE):
    image_module = import_cache_module(module_name, "bbcf-images")
    if not image_module:
        return False
    normal_loaded = merge_nested_url_cache(
        BBCF_MOVE_IMAGE_URLS,
        getattr(image_module, "BBCF_MOVE_IMAGE_URLS", {}),
        char_key_fn=lambda value: str(value or "").strip().lower(),
        move_key_fn=normalize_move_token,
    )
    BBCF_HITBOX_DATA.clear()
    hitbox_loaded = 0
    for char_key, moves in (getattr(image_module, "BBCF_HITBOX_DATA", {}) or {}).items():
        if not isinstance(moves, dict):
            continue
        normalized_char = str(char_key or "").strip().lower()
        char_links = BBCF_HITBOX_DATA.setdefault(normalized_char, {})
        for move_key, links in moves.items():
            if isinstance(links, str):
                links = [links]
            clean_links = [str(link or "").strip() for link in (links or []) if str(link or "").strip()]
            if clean_links:
                char_links[normalize_move_token(move_key)] = clean_links
                hitbox_loaded += len(clean_links)
    BBCF_MOVE_NOTES.clear()
    notes_loaded = 0
    for char_key, moves in (getattr(image_module, "BBCF_MOVE_NOTES", {}) or {}).items():
        if not isinstance(moves, dict):
            continue
        normalized_char = str(char_key or "").strip().lower()
        char_notes = BBCF_MOVE_NOTES.setdefault(normalized_char, {})
        for move_key, notes in moves.items():
            clean_notes = str(notes or "").strip()
            if clean_notes:
                char_notes[normalize_move_token(move_key)] = clean_notes
                notes_loaded += 1
    print(f"[bbcf-images] loaded {normal_loaded} move image links, {hitbox_loaded} hitbox links, and {notes_loaded} notes", flush=True)
    return True


def resolve_character_key(text):
    return resolve_alias_key(text, BBCF_CHARACTER_ALIASES, BBCF_FRAME_DATA.keys(), normalize_fn=normalize_key)


def display_char_name(char_key):
    rows = BBCF_FRAME_DATA.get(char_key) or []
    if rows:
        return str(rows[0].get("char_name") or char_key).strip()
    return str(char_key or "Unknown").replace("_", " ").title()


def load_frame_data(filename=None):
    global BBCF_FRAME_DATA
    BBCF_FRAME_DATA = {}
    filename = filename or BBCF_FRAME_DATA_FILE
    if not os.path.exists(filename):
        print(f"[bbcf] frame data file not found: {filename}", flush=True)
        return False
    xls = pd.ExcelFile(filename, engine="odf")
    loaded = 0
    for sheet_name in xls.sheet_names:
        if not sheet_name.endswith("Normal"):
            continue
        df = pd.read_excel(xls, sheet_name=sheet_name).fillna("")
        rows = []
        for row in df.to_dict("records"):
            char_key = str(row.get("char_key") or row.get("char_name") or sheet_name[: -len("Normal")]).strip().lower()
            move_name = str(row.get("moveName", "")).strip()
            num_cmd = str(row.get("numCmd", "")).strip()
            if not move_name and not num_cmd:
                continue
            row["char_key"] = char_key
            row["char_name"] = str(row.get("char_name") or sheet_name[: -len("Normal")]).strip()
            rows.append(row)
        if rows:
            BBCF_FRAME_DATA[rows[0]["char_key"]] = rows
            BBCF_CHARACTER_ALIASES.setdefault(rows[0]["char_key"].replace("_", " "), rows[0]["char_key"])
            BBCF_CHARACTER_ALIASES.setdefault(str(rows[0]["char_name"]).lower(), rows[0]["char_key"])
            loaded += 1
    print(f"[bbcf] Total characters loaded: {loaded}", flush=True)
    return bool(BBCF_FRAME_DATA)


def find_characters_in_text(text):
    return find_alias_positions_in_text(text, BBCF_CHARACTER_ALIASES, BBCF_FRAME_DATA.keys())


def normalize_move_query(query):
    text = str(query or "").lower().strip()
    text = re.sub(r"\b(?:bbcf|blazblue|central\s*fiction)\b", " ", text)
    text = re.sub(r"\b(?:framedata|frame\s*data|frames?|data|gif|gifs|hitbox(?:es)?|images?|notes?)\b", " ", text)
    text = strip_noise_words(text)
    compact = normalize_move_token(text)
    if text in BBCF_MOVE_ALIASES:
        return BBCF_MOVE_ALIASES[text]
    if compact in BBCF_MOVE_ALIASES:
        return BBCF_MOVE_ALIASES[compact]
    return text


def row_match_keys(row):
    keys = set()
    for value in (row.get("numCmd"), row.get("moveName")):
        if str(value or "").strip():
            keys.add(normalize_move_token(value))
    return {key for key in keys if key}


def find_matching_rows(char_key, move_text):
    query = normalize_move_query(move_text)
    query_key = normalize_move_token(query)
    if not query_key:
        return []
    rows = BBCF_FRAME_DATA.get(char_key, []) or []
    exact = [row for row in rows if query_key in row_match_keys(row)]
    if exact:
        return unique_rows(exact)

    normalized_query_words = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
    name_matches = []
    for row in rows:
        move_name = re.sub(r"[^a-z0-9]+", " ", str(row.get("moveName", "")).lower()).strip()
        num_cmd = re.sub(r"[^a-z0-9]+", " ", str(row.get("numCmd", "")).lower()).strip()
        if normalized_query_words and (normalized_query_words in move_name or normalized_query_words in num_cmd):
            name_matches.append(row)
    if name_matches:
        return unique_rows(name_matches)

    candidates = []
    for row in rows:
        for value in (row.get("moveName"), row.get("numCmd")):
            key = normalize_move_token(value)
            if key:
                candidates.append((key, row))
    close_keys = difflib.get_close_matches(query_key, [key for key, _row in candidates], n=4, cutoff=0.84)
    return unique_rows([row for key, row in candidates if key in close_keys])


def build_disambiguation_prompt(char_key, rows):
    lines = [f"Multiple BBCF moves match {display_char_name(char_key)}. Please specify one:"]
    for row in rows[:12]:
        move_name = str(row.get("moveName") or "Unknown").strip()
        num_cmd = str(row.get("numCmd") or "?").strip()
        lines.append(f"- {move_name}: `{num_cmd}`")
    return "\n".join(lines)


def find_moves_in_text(text):
    lowered = str(text or "").lower()
    hitbox_query = bool(re.search(r"\b(?:gif|gifs|hitbox|hitboxes)\b", lowered))
    frame_query = bool(re.search(r"\b(?:framedata|frame\s*data|frames?|data)\b", lowered))
    game_query = bool(re.search(r"\b(?:bbcf|blazblue|central\s*fiction)\b", lowered))
    notes_query = bool(re.search(r"\bnotes?\b", lowered))
    char_matches = find_characters_in_text(lowered)
    rows = []
    matched_char_key = char_matches[0][0] if char_matches else None
    comparison_result = find_comparison_rows(
        lowered,
        char_matches,
        find_characters_in_text=find_characters_in_text,
        find_rows_for_char=find_matching_rows,
    )
    if comparison_result and comparison_result.get("needs_disambiguation"):
        char_key = comparison_result["char_key"]
        matches = comparison_result["rows"]
        return {
            "mode": "options",
            "rows": matches,
            "data": build_disambiguation_prompt(char_key, matches),
            "gif_query": hitbox_query,
            "frame_query": frame_query,
            "game_query": game_query,
            "notes_query": notes_query,
            "needs_disambiguation": True,
            "char_found": True,
            "char_key": char_key,
            "wants_comparison": True,
        }
    if comparison_result:
        rows = comparison_result["rows"]
        return {
            "mode": "gif" if hitbox_query else "frame",
            "rows": rows,
            "data": "\n\n".join(format_frame_data(row, include_notes=notes_query) for row in rows),
            "gif_query": hitbox_query,
            "frame_query": frame_query,
            "game_query": game_query,
            "notes_query": notes_query,
            "char_found": True,
            "char_key": comparison_result.get("char_key") or matched_char_key,
            "wants_comparison": True,
            "explicit_move_attempt": True,
            "missing_scrolls_query": False,
        }
    for char_key, start, end, _alias in char_matches:
        move_text = (lowered[:start] + " " + lowered[end:]).strip() if start >= 0 and end >= 0 else lowered
        move_text = normalize_move_query(move_text)
        if not move_text:
            continue
        matches = find_matching_rows(char_key, move_text)
        if len(matches) > 1:
            return {
                "mode": "options",
                "rows": matches,
                "data": build_disambiguation_prompt(char_key, matches),
                "gif_query": hitbox_query,
                "frame_query": frame_query,
                "game_query": game_query,
                "notes_query": notes_query,
                "needs_disambiguation": True,
                "char_found": True,
                "char_key": char_key,
            }
        if matches:
            rows.append(matches[0])
            break
    return {
        "mode": "gif" if hitbox_query else "frame" if rows else "none",
        "rows": rows,
        "data": "\n\n".join(format_frame_data(row, include_notes=notes_query) for row in rows),
        "gif_query": hitbox_query,
        "frame_query": frame_query,
        "game_query": game_query,
        "notes_query": notes_query,
        "char_found": bool(char_matches),
        "char_key": matched_char_key,
        "wants_comparison": is_comparison_query(lowered, char_matches),
        "explicit_move_attempt": bool(char_matches and (frame_query or hitbox_query or game_query or query_has_bbcf_notation(lowered))),
        "missing_scrolls_query": bool(char_matches and not rows and (frame_query or hitbox_query or game_query)),
    }


def get_notes_text(row):
    char_key = str(row.get("char_key", "")).strip().lower()
    num_cmd_key = normalize_move_token(row.get("numCmd", ""))
    cached_notes = (BBCF_MOVE_NOTES.get(char_key, {}) or {}).get(num_cmd_key)
    return str(cached_notes or row.get("extraInfo") or "").strip()


def get_move_image_url(row):
    return BBCF_MOVE_IMAGE_URLS.get((str(row.get("char_key", "")).strip().lower(), normalize_move_token(row.get("numCmd", ""))))


def get_hitbox_links(row, limit=4):
    char_key = str(row.get("char_key", "")).strip().lower()
    num_cmd_key = normalize_move_token(row.get("numCmd", ""))
    links = (BBCF_HITBOX_DATA.get(char_key, {}) or {}).get(num_cmd_key, [])
    return [str(link or "").strip() for link in list(links or [])[:limit] if str(link or "").strip()]


def clean_value(value, default=""):
    text = str(value or "").strip()
    return text if text else default


def truncate_value(value, limit):
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def add_embed_field(embed, name, value, inline=True):
    clean = clean_value(value)
    if clean:
        embed.add_field(name=name, value=truncate_value(clean, 1024), inline=inline)


def add_long_embed_field(embed, name, value, inline=False):
    clean = clean_value(value)
    if not clean:
        return
    chunks = [clean[index : index + 1024] for index in range(0, len(clean), 1024)]
    for index, chunk in enumerate(chunks[:3]):
        embed.add_field(name=name if index == 0 else f"{name} cont.", value=chunk, inline=inline)


def build_frame_embed(row, show_notes=False):
    char_name = clean_value(row.get("char_name"), "Unknown")
    move_name = clean_value(row.get("moveName"), "Unknown")
    num_cmd = clean_value(row.get("numCmd"), "?")
    embed = discord.Embed(
        title=truncate_value(f"BBCF - {char_name}", 256),
        description=truncate_value(f"{move_name} ({num_cmd})", 4096),
        colour=0x1B5FA7,
    )
    add_embed_field(embed, "Startup", row.get("startup"), inline=True)
    add_embed_field(embed, "Active", row.get("active"), inline=True)
    add_embed_field(embed, "Recovery", row.get("recovery"), inline=True)
    add_embed_field(embed, "On Block", row.get("onBlock"), inline=True)
    add_embed_field(embed, "On ODR", row.get("onODR"), inline=True)
    add_embed_field(embed, "Damage", row.get("dmg"), inline=True)
    add_embed_field(embed, "Guard", row.get("guardLevel"), inline=True)
    add_embed_field(embed, "Attribute", row.get("attribute"), inline=True)
    add_embed_field(embed, "Cancel", row.get("cancel"), inline=True)
    add_embed_field(embed, "Invuln", row.get("invuln"), inline=True)
    add_embed_field(embed, "Level", row.get("level"), inline=True)
    if show_notes:
        add_long_embed_field(embed, "Notes", get_notes_text(row), inline=False)
    image_url = get_move_image_url(row)
    if image_url:
        embed.set_image(url=image_url)
    return embed


class BBCFHitboxButton(discord.ui.Button):
    def __init__(self, row, showing_hitbox=False):
        self.frame_row = row
        self.hitbox_links = get_hitbox_links(row)
        self.original_image_url = get_move_image_url(row)
        self.showing_hitbox = bool(showing_hitbox and self.hitbox_links)
        super().__init__(
            label="Show Image" if self.showing_hitbox else "Show Hitbox",
            style=discord.ButtonStyle.secondary if self.showing_hitbox else discord.ButtonStyle.primary,
            disabled=not self.hitbox_links,
        )

    async def callback(self, interaction: discord.Interaction):
        if not self.hitbox_links:
            await interaction.response.send_message("I have BBCF frame data for this move but no hitbox image link yet.", ephemeral=True)
            return
        self.showing_hitbox = not self.showing_hitbox
        self.label = "Show Image" if self.showing_hitbox else "Show Hitbox"
        self.style = discord.ButtonStyle.secondary if self.showing_hitbox else discord.ButtonStyle.primary
        embed = self.view.build_embed() if hasattr(self.view, "build_embed") else build_frame_embed(self.frame_row)
        image_url = self.hitbox_links[0] if self.showing_hitbox else self.original_image_url
        if image_url:
            embed.set_image(url=image_url)
        await interaction.response.edit_message(embed=embed, view=self.view)


class BBCFNotesButton(discord.ui.Button):
    def __init__(self, row):
        self.frame_row = row
        self.notes_text = get_notes_text(row)
        super().__init__(label="Show Notes", style=discord.ButtonStyle.primary, disabled=not self.notes_text, row=0)

    async def callback(self, interaction: discord.Interaction):
        if not hasattr(self.view, "build_embed"):
            await interaction.response.defer()
            return
        self.view.show_notes = not self.view.show_notes
        self.label = "Hide Notes" if self.view.show_notes else "Show Notes"
        self.style = discord.ButtonStyle.secondary if self.view.show_notes else discord.ButtonStyle.primary
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)


class ReturnToMenuButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Return to Menu", style=discord.ButtonStyle.secondary, custom_id="bbcf_frame_return_menu", row=0)

    async def callback(self, interaction: discord.Interaction):
        from bubbot.features import menu_system
        await interaction.response.send_message(embed=menu_system._main_menu_embed(), view=menu_system.MainMenuView(interaction.user.id))


class BBCFFrameDataView(discord.ui.View):
    def __init__(self, row, include_menu_button=True):
        super().__init__(timeout=3600)
        self.row = row
        self.show_notes = False
        self.hitbox_button = BBCFHitboxButton(row, showing_hitbox=True)
        self.notes_button = BBCFNotesButton(row)
        self.add_item(self.hitbox_button)
        self.add_item(self.notes_button)
        if include_menu_button:
            self.add_item(ReturnToMenuButton())

    def build_embed(self):
        embed = build_frame_embed(self.row, show_notes=self.show_notes)
        if self.hitbox_button.showing_hitbox and self.hitbox_button.hitbox_links:
            embed.set_image(url=self.hitbox_button.hitbox_links[0])
        return embed


async def send_frame_response(message, rows):
    if not rows:
        return False
    for row in rows[:4]:
        view = BBCFFrameDataView(row)
        await message.channel.send(embed=view.build_embed(), view=view)
    return True


async def send_hitbox_response(message, rows):
    if not rows:
        return False
    links = []
    for row in rows[:4]:
        links.extend(get_hitbox_links(row))
    if not links:
        await message.reply("BBCF hitbox images are not added yet, but the frame-data lookup is wired.")
        return True
    await message.reply("\n".join(links[:4]))
    return True


def format_frame_data(row, include_notes=False):
    text = (
        f"Move: {row.get('moveName') or row.get('numCmd')} ({row.get('numCmd') or '?'})\n"
        f"Startup: {row.get('startup') or '-'} | Active: {row.get('active') or '-'} | Recovery: {row.get('recovery') or '-'}\n"
        f"On Block: {row.get('onBlock') or '-'} | On ODR: {row.get('onODR') or '-'}\n"
        f"Damage: {row.get('dmg') or '-'} | Guard: {row.get('guardLevel') or '-'} | Attribute: {row.get('attribute') or '-'}\n"
        f"Cancel: {row.get('cancel') or '-'} | Invuln: {row.get('invuln') or '-'}"
    )
    notes = get_notes_text(row)
    if include_notes and notes:
        text += f"\nNotes: {notes}"
    return text


load_move_image_urls()
