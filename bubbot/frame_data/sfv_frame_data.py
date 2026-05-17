import ast
import difflib
import os
import re

import discord
import pandas as pd

from bubbot.data.sfv_aliases import SFV_CHARACTER_ALIASES, SFV_MOVE_ALIASES
from bubbot.utils.character_lookup import find_alias_positions_in_text, resolve_alias_key
from bubbot.utils.comparison_utils import find_comparison_rows, is_comparison_query
from bubbot.utils.discord_formatting import add_embed_field, clean_value, truncate_value
from bubbot.utils.image_cache_utils import import_cache_module, merge_nested_url_cache
from bubbot.utils.row_utils import unique_rows
from bubbot.utils.text_utils import compact_key, correct_alias_typos, strip_noise_words


SFV_FRAME_DATA_FILE = "SF5 Frame Data - FAT .ods"
SFV_FRAME_DATA = {}
SFV_TRIGGER_FRAME_DATA = {}
SFV_MOVE_IMAGE_URLS = {}
SFV_HITBOX_DATA = {}
SFV_MOVE_NOTES = {}
SFV_MOVE_IMAGES_MODULE = "bubbot.data.sfv_move_images"


def normalize_key(value):
    text = str(value or "").strip().lower().replace("'", "")
    text = text.replace(".", "_")
    text = re.sub(r"\((old|young)\)", r"_\1", text)
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def normalize_move_token(value):
    text = str(value or "").lower().strip()
    text = text.replace("jumping", "j")
    text = re.sub(r"\b(?:jump|air)\s*\.?,?", "8", text)
    text = re.sub(r"\b(?:stand|standing|st)\b", "5", text)
    text = re.sub(r"\b(?:crouch|crouching|cr)\b", "2", text)
    text = re.sub(r"\b(?:forward|f)\s*\+", "6", text)
    text = re.sub(r"\b(?:back|b)\s*\+", "4", text)
    text = re.sub(r"\b(?:down|d)\s*\+", "2", text)
    text = text.replace("critical art", "ca")
    text = text.replace("v-trigger", "vtrigger")
    text = text.replace("v-skill", "vskill")
    return re.sub(r"[^a-z0-9]+", "", text)


def query_has_sfv_notation(text):
    lowered = str(text or "").lower()
    return bool(
        re.search(r"(?:^|\s)(?:[1-9][0-9]{0,5})?(?:lp|mp|hp|lk|mk|hk|pp|kk)(?:\s|$)", lowered)
        or re.search(r"\b(?:st|cr|j)\s*\.?\s*(?:lp|mp|hp|lk|mk|hk)\b", lowered)
        or re.search(r"\b(?:vt|v\s*trigger)\s*[12]\b", lowered)
    )


def query_requested_state(text):
    lowered = str(text or "").lower()
    if re.search(r"\b(?:vt|v\s*trigger|trigger)\s*1\b|\bvt1\b|\btrigger1\b", lowered):
        return "trigger1"
    if re.search(r"\b(?:vt|v\s*trigger|trigger)\s*2\b|\bvt2\b|\btrigger2\b", lowered):
        return "trigger2"
    return ""


def display_char_name(char_key):
    rows = SFV_FRAME_DATA.get(char_key) or []
    if rows:
        return str(rows[0].get("char_name") or char_key).strip()
    return str(char_key or "Unknown").replace("_", " ").title()


def _sheet_character_and_state(sheet_name):
    for suffix, state_key, state_label in (
        ("Trigger1", "trigger1", "V-Trigger 1"),
        ("Trigger2", "trigger2", "V-Trigger 2"),
        ("Normal", "", ""),
    ):
        if sheet_name.endswith(suffix):
            return sheet_name[: -len(suffix)], state_key, state_label
    return None, None, None


def _clean_cell(value):
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0") and re.fullmatch(r"-?\d+\.0", text):
        text = text[:-2]
    return text


def _parse_notes(value):
    text = _clean_cell(value)
    if not text:
        return ""
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, list):
            return "\n".join(str(item).strip() for item in parsed if str(item).strip())
    except Exception:
        pass
    return text


def _row_from_sheet(raw_row, char_name, char_key, state_key="", state_label=""):
    move_name = _clean_cell(raw_row.get("moveName"))
    num_cmd = _clean_cell(raw_row.get("numCmd"))
    if not move_name and not num_cmd:
        return None
    if move_name.lower() in {"nan", "none"}:
        return None
    row = {key: _clean_cell(value) for key, value in raw_row.items()}
    row.update(
        {
            "char_key": char_key,
            "char_name": char_name,
            "moveName": move_name,
            "numCmd": num_cmd,
            "cmnName": _clean_cell(raw_row.get("cmnName")),
            "state_key": state_key,
            "state_label": state_label,
            "extraInfo": _parse_notes(raw_row.get("extraInfo")),
            "cancel": _clean_cell(raw_row.get("xx")),
            "guardLevel": _clean_cell(raw_row.get("atkLvl")),
        }
    )
    return row


def _register_character_aliases(char_key, char_name):
    aliases = {
        char_name.lower(),
        char_name.lower().replace(".", " "),
        normalize_key(char_name).replace("_", " "),
        normalize_key(char_name),
    }
    if char_key == "m_bison":
        aliases.update({"bison", "dictator", "m bison", "mbison"})
    for alias in aliases:
        if alias:
            SFV_CHARACTER_ALIASES.setdefault(alias, char_key)


def load_frame_data(filename=None):
    global SFV_FRAME_DATA, SFV_TRIGGER_FRAME_DATA
    SFV_FRAME_DATA = {}
    SFV_TRIGGER_FRAME_DATA = {}
    filename = filename or SFV_FRAME_DATA_FILE
    if not os.path.exists(filename):
        print(f"[sfv] frame data file not found: {filename}", flush=True)
        return False
    xls = pd.ExcelFile(filename, engine="odf")
    loaded_normal = 0
    loaded_triggers = 0
    for sheet_name in xls.sheet_names:
        char_name, state_key, state_label = _sheet_character_and_state(sheet_name)
        if char_name is None:
            continue
        df = pd.read_excel(xls, sheet_name=sheet_name).fillna("")
        char_key = normalize_key(char_name)
        rows = []
        for raw_row in df.to_dict("records"):
            row = _row_from_sheet(raw_row, char_name, char_key, state_key=state_key, state_label=state_label)
            if row:
                rows.append(row)
        if not rows:
            continue
        _register_character_aliases(char_key, char_name)
        if state_key:
            SFV_TRIGGER_FRAME_DATA.setdefault(char_key, {})[state_key] = rows
            loaded_triggers += 1
        else:
            SFV_FRAME_DATA[char_key] = rows
            loaded_normal += 1
    load_move_image_urls()
    print(f"[sfv] Total characters loaded: {loaded_normal}; trigger sheets loaded: {loaded_triggers}", flush=True)
    return bool(SFV_FRAME_DATA)


def load_move_image_urls(module_name=SFV_MOVE_IMAGES_MODULE):
    image_module = import_cache_module(module_name, "sfv-images")
    if not image_module:
        return False
    normal_loaded = merge_nested_url_cache(
        SFV_MOVE_IMAGE_URLS,
        getattr(image_module, "SFV_MOVE_IMAGE_URLS", {}),
        char_key_fn=normalize_key,
        move_key_fn=normalize_move_token,
    )
    SFV_HITBOX_DATA.clear()
    hitbox_loaded = 0
    for char_key, moves in (getattr(image_module, "SFV_HITBOX_DATA", {}) or {}).items():
        if not isinstance(moves, dict):
            continue
        char_links = SFV_HITBOX_DATA.setdefault(normalize_key(char_key), {})
        for move_key, links in moves.items():
            if isinstance(links, str):
                links = [links]
            clean_links = [str(link or "").strip() for link in (links or []) if str(link or "").strip()]
            if clean_links:
                char_links[normalize_move_token(move_key)] = clean_links
                hitbox_loaded += len(clean_links)
    SFV_MOVE_NOTES.clear()
    notes_loaded = 0
    for char_key, moves in (getattr(image_module, "SFV_MOVE_NOTES", {}) or {}).items():
        if not isinstance(moves, dict):
            continue
        char_notes = SFV_MOVE_NOTES.setdefault(normalize_key(char_key), {})
        for move_key, notes in moves.items():
            clean_notes = str(notes or "").strip()
            if clean_notes:
                char_notes[normalize_move_token(move_key)] = clean_notes
                notes_loaded += 1
    print(f"[sfv-images] loaded {normal_loaded} move image links, {hitbox_loaded} hitbox links, and {notes_loaded} notes", flush=True)
    return True


def resolve_character_key(text):
    return resolve_alias_key(text, SFV_CHARACTER_ALIASES, SFV_FRAME_DATA.keys(), normalize_fn=normalize_key)


def find_characters_in_text(text):
    return [match for match in find_alias_positions_in_text(text, SFV_CHARACTER_ALIASES, SFV_FRAME_DATA.keys()) if match[0] != "sfv"]


def query_requests_plain_zeku(text):
    lowered = str(text or "").lower()
    return bool(re.search(r"(?<![a-z0-9])zeku(?![a-z0-9])", lowered)) and not bool(
        re.search(r"(?<![a-z0-9])(?:old|young)(?![a-z0-9])", lowered)
    )


def normalize_move_query(query):
    text = str(query or "").lower().strip()
    text = re.sub(r"\b(?:sfv|sf5|street\s*fighter\s*(?:v|5))\b", " ", text)
    text = re.sub(r"\b(?:framedata|frame\s*data|frames?|data|gif|gifs|hitbox(?:es)?|images?|notes?)\b", " ", text)
    text = re.sub(r"\b(?:vt|v\s*trigger|trigger)\s*[12]\b|\bvt[12]\b", " ", text)
    text = strip_noise_words(text)
    normalized_words = re.sub(r"[^a-z0-9+.,-]+", " ", text).strip()
    compact = normalize_move_token(normalized_words)
    if normalized_words in SFV_MOVE_ALIASES:
        return SFV_MOVE_ALIASES[normalized_words]
    if compact in SFV_MOVE_ALIASES:
        return SFV_MOVE_ALIASES[compact]
    corrected_words = correct_alias_typos(normalized_words, SFV_MOVE_ALIASES)
    if corrected_words != normalized_words:
        corrected_compact = normalize_move_token(corrected_words)
        if corrected_words in SFV_MOVE_ALIASES:
            return SFV_MOVE_ALIASES[corrected_words]
        if corrected_compact in SFV_MOVE_ALIASES:
            return SFV_MOVE_ALIASES[corrected_compact]
        return corrected_words
    return normalized_words


def row_match_keys(row):
    keys = set()
    for value in (row.get("numCmd"), row.get("moveName"), row.get("cmnName")):
        if str(value or "").strip():
            keys.add(normalize_move_token(value))
    return {key for key in keys if key}


def _rows_for_state(char_key, state_key=""):
    if state_key:
        return list((SFV_TRIGGER_FRAME_DATA.get(char_key) or {}).get(state_key, []) or [])
    return list(SFV_FRAME_DATA.get(char_key, []) or [])


def find_matching_rows(char_key, move_text):
    state_key = query_requested_state(move_text)
    query = normalize_move_query(move_text)
    query_key = normalize_move_token(query)
    if not query_key:
        return []
    rows = _rows_for_state(char_key, state_key)
    exact = [row for row in rows if query_key in row_match_keys(row)]
    if exact:
        return unique_rows(exact)

    normalized_query_words = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
    name_matches = []
    for row in rows:
        haystack = " ".join(
            re.sub(r"[^a-z0-9]+", " ", str(row.get(field, "")).lower()).strip()
            for field in ("moveName", "numCmd", "cmnName")
        )
        if normalized_query_words and normalized_query_words in haystack:
            name_matches.append(row)
    if name_matches:
        return unique_rows(name_matches)

    candidates = []
    for row in rows:
        for value in (row.get("moveName"), row.get("numCmd"), row.get("cmnName")):
            key = normalize_move_token(value)
            if key:
                candidates.append((key, row))
    close_keys = difflib.get_close_matches(query_key, [key for key, _row in candidates], n=4, cutoff=0.84)
    return unique_rows([row for key, row in candidates if key in close_keys])


def build_disambiguation_prompt(char_key, rows):
    lines = [f"Multiple SFV moves match {display_char_name(char_key)}. Please specify one:"]
    multiple_characters = len({str(row.get("char_key", "")).strip() for row in rows if str(row.get("char_key", "")).strip()}) > 1
    for row in rows[:12]:
        move_name = clean_value(row.get("moveName"), "Unknown")
        num_cmd = clean_value(row.get("numCmd"), "?")
        if multiple_characters:
            move_name = f"{clean_value(row.get('char_name'), display_char_name(row.get('char_key')))} - {move_name}"
        state_label = clean_value(row.get("state_label"), "")
        suffix = f" [{state_label}]" if state_label else ""
        lines.append(f"- {move_name}: `{num_cmd}`{suffix}")
    return "\n".join(lines)


def find_moves_in_text(text):
    lowered = str(text or "").lower()
    gif_query = bool(re.search(r"\b(?:gif|gifs|hitbox|hitboxes|image|images)\b", lowered))
    frame_query = bool(re.search(r"\b(?:framedata|frame\s*data|frames?|data)\b", lowered))
    notes_query = bool(re.search(r"\bnotes?\b", lowered))
    game_query = bool(re.search(r"\b(?:sfv|sf5|street\s*fighter\s*(?:v|5))\b", lowered))
    char_matches = find_characters_in_text(lowered)
    rows = []
    matched_char_key = char_matches[0][0] if char_matches else None
    if query_requests_plain_zeku(lowered) and {"zeku_old", "zeku_young"}.issubset(SFV_FRAME_DATA.keys()):
        move_text = normalize_move_query(re.sub(r"(?<![a-z0-9])zeku(?![a-z0-9])", " ", lowered))
        zeku_matches = []
        if move_text:
            for zeku_key in ("zeku_old", "zeku_young"):
                zeku_matches.extend(find_matching_rows(zeku_key, f"{move_text} {query_requested_state(lowered)}"))
        zeku_matches = unique_rows(zeku_matches)
        if len(zeku_matches) > 1:
            return {
                "mode": "options",
                "rows": zeku_matches,
                "data": build_disambiguation_prompt("zeku", zeku_matches),
                "gif_query": gif_query,
                "frame_query": frame_query,
                "notes_query": notes_query,
                "game_query": game_query,
                "needs_disambiguation": True,
                "char_found": True,
                "char_key": "zeku",
            }
        if zeku_matches:
            rows.append(zeku_matches[0])
            return {
                "mode": "gif" if gif_query else "frame",
                "rows": rows,
                "data": "\n\n".join(format_frame_data(row, include_notes=notes_query) for row in rows),
                "gif_query": gif_query,
                "frame_query": frame_query,
                "notes_query": notes_query,
                "game_query": game_query,
                "char_found": True,
                "char_key": rows[0].get("char_key"),
                "wants_comparison": False,
                "explicit_move_attempt": True,
                "missing_scrolls_query": False,
            }
        return {
            "mode": "none",
            "rows": [],
            "data": "",
            "gif_query": gif_query,
            "frame_query": frame_query,
            "notes_query": notes_query,
            "game_query": game_query,
            "char_found": True,
            "char_key": "zeku",
            "wants_comparison": False,
            "explicit_move_attempt": bool(frame_query or gif_query or notes_query or game_query or query_has_sfv_notation(lowered)),
            "missing_scrolls_query": bool(frame_query or gif_query or notes_query or game_query),
        }
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
            "gif_query": gif_query,
            "frame_query": frame_query,
            "notes_query": notes_query,
            "game_query": game_query,
            "needs_disambiguation": True,
            "char_found": True,
            "char_key": char_key,
            "wants_comparison": True,
        }
    if comparison_result:
        rows = comparison_result["rows"]
        return {
            "mode": "gif" if gif_query else "frame",
            "rows": rows,
            "data": "\n\n".join(format_frame_data(row, include_notes=notes_query) for row in rows),
            "gif_query": gif_query,
            "frame_query": frame_query,
            "notes_query": notes_query,
            "game_query": game_query,
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
        matches = find_matching_rows(char_key, f"{move_text} {query_requested_state(lowered)}")
        if len(matches) > 1:
            return {
                "mode": "options",
                "rows": matches,
                "data": build_disambiguation_prompt(char_key, matches),
                "gif_query": gif_query,
                "frame_query": frame_query,
                "notes_query": notes_query,
                "game_query": game_query,
                "needs_disambiguation": True,
                "char_found": True,
                "char_key": char_key,
            }
        if matches:
            rows.append(matches[0])
            break
    return {
        "mode": "gif" if gif_query else "frame" if rows else "none",
        "rows": rows,
        "data": "\n\n".join(format_frame_data(row, include_notes=notes_query) for row in rows),
        "gif_query": gif_query,
        "frame_query": frame_query,
        "notes_query": notes_query,
        "game_query": game_query,
        "char_found": bool(char_matches),
        "char_key": matched_char_key,
        "wants_comparison": is_comparison_query(lowered, char_matches),
        "explicit_move_attempt": bool(char_matches and (frame_query or gif_query or notes_query or game_query or query_has_sfv_notation(lowered))),
        "missing_scrolls_query": bool(char_matches and not rows and (frame_query or gif_query or notes_query or game_query)),
    }


def get_move_image_url(row):
    char_key = normalize_key(row.get("char_key") or row.get("char_name"))
    for value in (row.get("numCmd"), row.get("moveName"), row.get("cmnName")):
        url = SFV_MOVE_IMAGE_URLS.get((char_key, normalize_move_token(value)))
        if url:
            return url
    return None


def get_hitbox_links(row):
    char_key = normalize_key(row.get("char_key") or row.get("char_name"))
    links = []
    for value in (row.get("numCmd"), row.get("moveName"), row.get("cmnName")):
        links.extend(SFV_HITBOX_DATA.get(char_key, {}).get(normalize_move_token(value), []) or [])
    return links


def get_notes_text(row):
    char_key = normalize_key(row.get("char_key") or row.get("char_name"))
    cache_notes = ""
    for value in (row.get("numCmd"), row.get("moveName"), row.get("cmnName")):
        cache_notes = SFV_MOVE_NOTES.get(char_key, {}).get(normalize_move_token(value), "")
        if cache_notes:
            break
    workbook_notes = str(row.get("extraInfo") or "").strip()
    return "\n".join(part for part in (workbook_notes, cache_notes) if part)


def build_frame_embed(row, show_notes=False):
    title = f"{row.get('char_name', 'SFV')} - {row.get('moveName') or row.get('numCmd')}"
    if row.get("state_label"):
        title = f"{title} [{row.get('state_label')}]"
    embed = discord.Embed(title=title, colour=0xD0342C)
    embed.add_field(name="Input", value=truncate_value(clean_value(row.get("numCmd"), "?"), 1024), inline=True)
    embed.add_field(name="Startup", value=truncate_value(clean_value(row.get("startup"), "-"), 1024), inline=True)
    embed.add_field(name="Active", value=truncate_value(clean_value(row.get("active"), "-"), 1024), inline=True)
    embed.add_field(name="Recovery", value=truncate_value(clean_value(row.get("recovery"), "-"), 1024), inline=True)
    embed.add_field(name="On Hit", value=truncate_value(clean_value(row.get("onHit"), "-"), 1024), inline=True)
    embed.add_field(name="On Block", value=truncate_value(clean_value(row.get("onBlock"), "-"), 1024), inline=True)
    embed.add_field(name="Damage", value=truncate_value(clean_value(row.get("dmg"), "-"), 1024), inline=True)
    embed.add_field(name="Stun", value=truncate_value(clean_value(row.get("stun"), "-"), 1024), inline=True)
    embed.add_field(name="Guard", value=truncate_value(clean_value(row.get("guardLevel"), "-"), 1024), inline=True)
    cancel = clean_value(row.get("cancel"), "")
    if cancel:
        add_embed_field(embed, "Cancel", cancel, inline=False)
    if show_notes:
        notes = get_notes_text(row)
        if notes:
            add_embed_field(embed, "Notes", notes, inline=False)
    image_url = get_move_image_url(row)
    if image_url:
        embed.set_image(url=image_url)
    return embed


class SFVNotesButton(discord.ui.Button):
    def __init__(self, row):
        super().__init__(label="Show Notes", style=discord.ButtonStyle.secondary)
        self.frame_row = row

    async def callback(self, interaction):
        view = self.view
        view.show_notes = not view.show_notes
        self.label = "Hide Notes" if view.show_notes else "Show Notes"
        await interaction.response.edit_message(embed=view.build_embed(), view=view)


class SFVHitboxButton(discord.ui.Button):
    def __init__(self, row):
        super().__init__(label="Show Hitbox", style=discord.ButtonStyle.primary)
        self.frame_row = row

    async def callback(self, interaction):
        links = get_hitbox_links(self.frame_row)
        if not links:
            image_url = get_move_image_url(self.frame_row)
            if image_url:
                await interaction.response.send_message(
                    "No dedicated SFV hitbox image is cached for this move, so here is the SuperCombo move image.\n"
                    f"{image_url}",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message("No SFV image link is cached for this move yet.", ephemeral=True)
            return
        await interaction.response.send_message("\n".join(links[:4]), ephemeral=True)


class ReturnToMenuButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Back to Menu", style=discord.ButtonStyle.grey)

    async def callback(self, interaction):
        from bubbot.features import menu_system
        await interaction.response.send_message(embed=menu_system._main_menu_embed(), view=menu_system.MainMenuView(interaction.user.id))


class SFVFrameDataView(discord.ui.View):
    def __init__(self, row, include_menu_button=True):
        super().__init__(timeout=3600)
        self.row = row
        self.show_notes = False
        self.add_item(SFVNotesButton(row))
        if include_menu_button:
            self.add_item(ReturnToMenuButton())

    def build_embed(self):
        return build_frame_embed(self.row, show_notes=self.show_notes)


async def send_frame_response(message, rows):
    if not rows:
        return False
    for row in rows[:4]:
        view = SFVFrameDataView(row)
        await message.channel.send(embed=view.build_embed(), view=view)
    return True


async def send_hitbox_response(message, rows):
    if not rows:
        return False
    links = []
    fallback_links = []
    for row in rows[:4]:
        links.extend(get_hitbox_links(row))
        image_url = get_move_image_url(row)
        if image_url:
            fallback_links.append(image_url)
    if links:
        await message.reply("\n".join(links[:4]))
        return True
    if fallback_links:
        await message.reply("No dedicated SFV hitbox image found; showing the SuperCombo move image instead.\n" + "\n".join(fallback_links[:4]))
        return True
    await message.reply("I have SFV frame data for this move but no SuperCombo image link cached yet.")
    return True


def format_frame_data(row, include_notes=False):
    parts = [
        f"Move: {row.get('moveName') or row.get('numCmd')} ({row.get('numCmd') or '?'})",
        f"Startup: {row.get('startup') or '-'} | Active: {row.get('active') or '-'} | Recovery: {row.get('recovery') or '-'}",
        f"On Hit: {row.get('onHit') or '-'} | On Block: {row.get('onBlock') or '-'}",
        f"Damage: {row.get('dmg') or '-'} | Stun: {row.get('stun') or '-'} | Guard: {row.get('guardLevel') or '-'}",
    ]
    if row.get("state_label"):
        parts.insert(1, f"State: {row.get('state_label')}")
    if include_notes and get_notes_text(row):
        parts.append(f"Notes: {get_notes_text(row)}")
    return "\n".join(parts)
