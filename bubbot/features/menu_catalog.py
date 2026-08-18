"""Loaded game catalogs and pure menu choice helpers.

The compatibility facade injects runtime data here; view classes consume this
catalog without owning startup or parser state.
"""

import io
import math
import os
import re

import discord

from bubbot.features.fg_glossary import build_glossary_definition_embed, build_glossary_embed, build_glossary_link_button, normalize_glossary_term
from bubbot.utils.choice_utils import character_choices, move_choices
from bubbot.frame_data.frame_media_controls import ShowAllImagesButton, preferred_frame_image_url

FRAME_DATA = {}
FRAME_STATS = {}
CHARACTER_ALIASES = {}
GGST_FRAME_DATA = {}
GGST_CHARACTER_ALIASES = {}
GGST_SUPPLEMENTAL_FRAME_DATA = {}
GGST_STATE_FRAME_DATA = {}
SFV_FRAME_DATA = {}
SFV_CHARACTER_ALIASES = {}
SFV_TRIGGER_FRAME_DATA = {}
TUCO_FRAME_DATA = {}
TUCO_CHARACTER_ALIASES = {}
BBCF_FRAME_DATA = {}
BBCF_CHARACTER_ALIASES = {}
GGACR_FRAME_DATA = {}
GGACR_CHARACTER_ALIASES = {}
COTW_FRAME_DATA = {}
COTW_CHARACTER_ALIASES = {}
THIRD_STRIKE_FRAME_DATA = {}
THIRD_STRIKE_CHARACTER_ALIASES = {}
MK1_FRAME_DATA = {}
MK1_CHARACTER_ALIASES = {}

quiz_module = None
build_sf6_frame_embed = None
build_ggst_frame_embed = None
build_sfv_frame_embed = None
build_tuco_frame_embed = None
build_bbcf_frame_embed = None
build_ggacr_frame_embed = None
build_cotw_frame_embed = None
build_third_strike_frame_embed = None
send_frame_embeds_with_views = None


# Runtime injection from bot startup
def configure(
    frame_data=None,
    frame_stats=None,
    character_aliases=None,
    ggst_frame_data=None,
    ggst_character_aliases=None,
    ggst_supplemental_frame_data=None,
    ggst_state_frame_data=None,
    sfv_frame_data=None,
    sfv_character_aliases=None,
    sfv_trigger_frame_data=None,
    tuco_frame_data=None,
    tuco_character_aliases=None,
    bbcf_frame_data=None,
    bbcf_character_aliases=None,
    ggacr_frame_data=None,
    ggacr_character_aliases=None,
    cotw_frame_data=None,
    cotw_character_aliases=None,
    third_strike_frame_data=None,
    third_strike_character_aliases=None,
    mk1_frame_data=None,
    mk1_character_aliases=None,
    quiz_module_ref=None,
    build_sf6_frame_embed_fn=None,
    build_ggst_frame_embed_fn=None,
    build_sfv_frame_embed_fn=None,
    build_tuco_frame_embed_fn=None,
    build_bbcf_frame_embed_fn=None,
    build_ggacr_frame_embed_fn=None,
    build_cotw_frame_embed_fn=None,
    build_third_strike_frame_embed_fn=None,
    send_frame_embeds_with_views_fn=None,
):
    global FRAME_DATA, FRAME_STATS, CHARACTER_ALIASES, GGST_FRAME_DATA, GGST_CHARACTER_ALIASES, GGST_SUPPLEMENTAL_FRAME_DATA, GGST_STATE_FRAME_DATA, SFV_FRAME_DATA, SFV_CHARACTER_ALIASES, SFV_TRIGGER_FRAME_DATA, TUCO_FRAME_DATA, TUCO_CHARACTER_ALIASES, BBCF_FRAME_DATA, BBCF_CHARACTER_ALIASES, GGACR_FRAME_DATA, GGACR_CHARACTER_ALIASES, COTW_FRAME_DATA, COTW_CHARACTER_ALIASES, THIRD_STRIKE_FRAME_DATA, THIRD_STRIKE_CHARACTER_ALIASES, MK1_FRAME_DATA, MK1_CHARACTER_ALIASES
    global quiz_module, build_sf6_frame_embed, build_ggst_frame_embed, build_sfv_frame_embed, build_tuco_frame_embed, build_bbcf_frame_embed, build_ggacr_frame_embed, build_cotw_frame_embed, build_third_strike_frame_embed, send_frame_embeds_with_views
    FRAME_DATA = frame_data or {}
    FRAME_STATS = frame_stats or {}
    CHARACTER_ALIASES = character_aliases or {}
    GGST_FRAME_DATA = ggst_frame_data or {}
    GGST_CHARACTER_ALIASES = ggst_character_aliases or {}
    GGST_SUPPLEMENTAL_FRAME_DATA = ggst_supplemental_frame_data or {}
    GGST_STATE_FRAME_DATA = ggst_state_frame_data or {}
    SFV_FRAME_DATA = sfv_frame_data or {}
    SFV_CHARACTER_ALIASES = sfv_character_aliases or {}
    SFV_TRIGGER_FRAME_DATA = sfv_trigger_frame_data or {}
    TUCO_FRAME_DATA = tuco_frame_data or {}
    TUCO_CHARACTER_ALIASES = tuco_character_aliases or {}
    BBCF_FRAME_DATA = bbcf_frame_data or {}
    BBCF_CHARACTER_ALIASES = bbcf_character_aliases or {}
    GGACR_FRAME_DATA = ggacr_frame_data or {}
    GGACR_CHARACTER_ALIASES = ggacr_character_aliases or {}
    COTW_FRAME_DATA = cotw_frame_data or {}
    COTW_CHARACTER_ALIASES = cotw_character_aliases or {}
    THIRD_STRIKE_FRAME_DATA = third_strike_frame_data or {}
    THIRD_STRIKE_CHARACTER_ALIASES = third_strike_character_aliases or {}
    MK1_FRAME_DATA = mk1_frame_data or {}
    MK1_CHARACTER_ALIASES = mk1_character_aliases or {}
    quiz_module = quiz_module_ref
    build_sf6_frame_embed = build_sf6_frame_embed_fn
    build_ggst_frame_embed = build_ggst_frame_embed_fn
    build_sfv_frame_embed = build_sfv_frame_embed_fn
    build_tuco_frame_embed = build_tuco_frame_embed_fn
    build_bbcf_frame_embed = build_bbcf_frame_embed_fn
    build_ggacr_frame_embed = build_ggacr_frame_embed_fn
    build_cotw_frame_embed = build_cotw_frame_embed_fn
    build_third_strike_frame_embed = build_third_strike_frame_embed_fn
    send_frame_embeds_with_views = send_frame_embeds_with_views_fn


def configure_ui(**dependencies):
    """Inject facade helpers into functions that remain owned by this module."""
    globals().update(dependencies)


MENU_SELECT_LIMIT = 25

# Full display names for menu dropdown and embed titles (no abbreviations)
MENU_GAMES = (
    ("tuco", "2XKO", 0xD63C2F),
    ("bbcf", "BlazBlue Central Fiction", 0x1B5FA7),
    ("cotw", "Fatal Fury: City of the Wolves", 0xD8A234),
    ("ggacr", "Guilty Gear Accent Core Plus R", 0x5C1F8A),
    ("ggst", "Guilty Gear Strive", 0x7A2BFF),
    ("mk1", "Mortal Kombat 1", 0x7E1616),
    ("sf6", "Street Fighter 6", 0x3998C6),
    ("third_strike", "Street Fighter III: 3rd Strike", 0xC0392B),
    ("sfv", "Street Fighter V", 0xD0342C),
)
_MENU_GAME_LABELS = {key: label for key, label, _colour in MENU_GAMES}
_MENU_GAME_COLOURS = {key: colour for key, label, colour in MENU_GAMES}


# Base view: owner lock for public /bub menu
class OwnedView(discord.ui.View):
    def __init__(self, owner_id, *, menu_locked=False, timeout=None):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id
        self.menu_locked = bool(menu_locked)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not self.menu_locked:
            return True
        if self.owner_id is None or interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            "Only the person who opened this menu can control it.",
            ephemeral=True,
        )
        return False

    async def on_error(self, interaction: discord.Interaction, error: Exception, item, /) -> None:
        custom_id = getattr(item, "custom_id", None) or type(item).__name__
        print(
            f"[menu] interaction error item={custom_id}: {type(error).__name__}: {error}",
            flush=True,
        )
        try:
            message = "That menu action failed. Please open `/bub` again and retry."
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except Exception as response_error:
            print(f"[menu] failed to send interaction error response: {response_error}", flush=True)


def _menu_locked_owner_id(view):
    if getattr(view, "menu_locked", False):
        return getattr(view, "owner_id", None)
    return None


# Game rosters, colours, move lists, search filters
def _sf6_character_list():
    return character_choices(FRAME_DATA, display_fn=lambda char_key, _rows: str(char_key).title())


def _sf6_stats_character_list():
    return character_choices(
        FRAME_STATS,
        display_fn=lambda char_key, _rows: str(char_key).replace(".", " ").replace("_", " ").title(),
    )


def _game_menu_view(game, owner_id):
    if game == "sf6":
        return SF6GameMenuView(owner_id)
    return GameMenuView(game, owner_id)


async def _edit_to_game_menu(interaction, game, owner_id):
    await interaction.response.edit_message(
        embed=_game_menu_embed(_game_label(game), _game_colour(game)),
        view=_game_menu_view(game, owner_id),
        attachments=[],
    )


async def _open_framedata_character_select(interaction, game, owner_id, *, compare_row=None, compare_char_key=None):
    chars = _character_list(game)
    if not chars:
        await interaction.response.send_message("No character data loaded.", ephemeral=True)
        return
    await interaction.response.edit_message(
        embed=_character_select_embed(
            game,
            page=0,
            total_pages=max(1, math.ceil(len(chars) / MENU_SELECT_LIMIT)),
            compare_row=compare_row,
        ),
        view=CharacterSelectView(
            game,
            chars,
            owner_id,
            page=0,
            compare_row=compare_row,
            compare_char_key=compare_char_key,
        ),
        attachments=[],
    )


async def _open_sf6_stats_character_select(interaction, owner_id):
    chars = _sf6_stats_character_list()
    if not chars:
        await interaction.response.send_message("No character stats loaded.", ephemeral=True)
        return
    await interaction.response.edit_message(
        embed=_character_select_embed(
            "sf6",
            page=0,
            total_pages=max(1, math.ceil(len(chars) / MENU_SELECT_LIMIT)),
            stats_mode=True,
        ),
        view=CharacterSelectView("sf6", chars, owner_id, page=0, stats_mode=True),
        attachments=[],
    )


async def _open_quiz_difficulty(interaction, game, owner_id):
    game_label = _game_label(game)
    await interaction.response.edit_message(
        embed=_quiz_difficulty_embed(game_label),
        view=QuizDifficultyView(game, owner_id),
        attachments=[],
    )


async def _open_combo_character_select(interaction, game, owner_id):
    from bubbot.frame_data import combo_data

    chars = combo_data.combo_character_list(game)
    if not chars:
        await interaction.response.send_message(f"No {combo_data.game_label(game)} combo data loaded.", ephemeral=True)
        return
    total_pages = max(1, math.ceil(len(chars) / MENU_SELECT_LIMIT))
    await interaction.response.edit_message(
        embed=_combo_character_select_embed(game, page=0, total_pages=total_pages),
        view=ComboCharacterSelectView(game, chars, owner_id, page=0),
        attachments=[],
    )


async def _open_game_combos_menu(interaction, game, owner_id):
    from bubbot.frame_data import combo_data

    game_key = str(game or "").strip().lower()
    if game_key not in combo_data.COMBO_GAMES:
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"{_game_label(game_key)} - Combos",
                description="Combos will be added to the scrolls soon.",
                colour=_game_colour(game_key),
            ),
            view=BackToGameMenuView(game_key, owner_id),
            attachments=[],
        )
        return
    combo_data.ensure_combo_data_loaded(game_key)
    if combo_data.has_combos(game_key):
        await _open_combo_character_select(interaction, game_key, owner_id)
        return
    missing_file = combo_data.SF6_COMBOS_FILE if game_key == "sf6" else combo_data.MK1_COMBOS_FILE
    await interaction.response.edit_message(
        embed=discord.Embed(
            title=f"{combo_data.game_label(game_key)} - Combos",
            description=(
                f"Combo data did not load. Deploy `{missing_file}` next to `bot.py` on the server "
                f"and restart the `bub` service."
            ),
            colour=0xFF4444,
        ),
        view=BackToGameMenuView(game_key, owner_id),
        attachments=[],
    )


async def _show_sf6_stats_embed(interaction, char_key, owner_id, stat_keys=None):
    stats_row = FRAME_STATS.get(char_key)
    if not stats_row:
        await interaction.response.send_message("No stats loaded for this character.", ephemeral=True)
        return
    from bubbot.frame_data.sf6_character_stats import build_character_stats_embed

    embed = build_character_stats_embed(char_key, stats_row, stat_keys)
    view = StatsResultView(char_key, owner_id, stat_keys=stat_keys, menu_locked=True)
    await interaction.response.edit_message(embed=embed, view=view, attachments=[])


async def _show_sf6_stats_compare_embed(interaction, char_key_a, char_key_b, owner_id, stat_keys=None, *, menu_locked=True):
    stats_a = FRAME_STATS.get(char_key_a)
    stats_b = FRAME_STATS.get(char_key_b)
    if not stats_a or not stats_b:
        await interaction.response.send_message("No stats loaded for one of those characters.", ephemeral=True)
        return
    from bubbot.frame_data.sf6_character_stats import build_character_stats_comparison_embed

    embed = build_character_stats_comparison_embed(char_key_a, stats_a, char_key_b, stats_b, stat_keys)
    view = StatsResultView(
        char_key_a,
        owner_id,
        stat_keys=stat_keys,
        compare_char_key=char_key_b,
        menu_locked=menu_locked,
    )
    await interaction.response.edit_message(embed=embed, view=view, attachments=[])


def _ggst_character_list():
    return character_choices(GGST_FRAME_DATA)


def _sfv_character_list():
    from bubbot.frame_data.sfv_frame_data import display_char_name
    return character_choices(SFV_FRAME_DATA, display_fn=lambda char_key, _rows: display_char_name(char_key))


def _tuco_character_list():
    return character_choices(TUCO_FRAME_DATA)


def _bbcf_character_list():
    return character_choices(BBCF_FRAME_DATA)


def _ggacr_character_list():
    return character_choices(GGACR_FRAME_DATA)


def _cotw_character_list():
    return character_choices(COTW_FRAME_DATA)


def _third_strike_character_list():
    return character_choices(THIRD_STRIKE_FRAME_DATA)


def _mk1_character_list():
    from bubbot.frame_data.mk1_frame_data import display_char_name

    def display_fn(char_key, _rows):
        label = display_char_name(char_key)
        if str(char_key).startswith("kameo_"):
            label = re.sub(r"^Kameo\s+", "", label).strip()
            return f"{label} (Kameo)"
        return label

    return character_choices(MK1_FRAME_DATA, display_fn=display_fn)


_GAME_ONLY_MENTION_PATTERNS = (
    ("sf6", re.compile(r"^(?:sf6|street\s*fighter\s*6)$", re.IGNORECASE)),
    ("sfv", re.compile(r"^(?:sfv|sf5|street\s*fighter\s*(?:v|5))$", re.IGNORECASE)),
    # Guilty Gear defaults to Strive unless +R / Accent Core is explicit
    ("ggacr", None),  # resolved via match_ggacr_game_only()
    ("ggst", re.compile(r"^(?:ggst|guilty\s*gear(?:\s*strive)?|strive|guilty\s*gear)$", re.IGNORECASE)),
    ("tuco", re.compile(r"^(?:2xko|tuco)$", re.IGNORECASE)),
    ("bbcf", re.compile(r"^(?:bbcf|blazblue|central\s*fiction)$", re.IGNORECASE)),
    ("cotw", re.compile(r"^(?:cotw|city\s+of\s+the\s+wolves|fatal\s+fury)$", re.IGNORECASE)),
    (
        "third_strike",
        re.compile(r"^(?:3s|third\s*strike|street\s*fighter\s*(?:3|iii)|sf3|sfiii)$", re.IGNORECASE),
    ),
    ("mk1", re.compile(r"^(?:mk1|mortal\s+kombat(?:\s*(?:1|one))?)$", re.IGNORECASE)),
)


def parse_game_only_mention(text):
    """Return game key when message is only a game tag (e.g. '@bub sf6')."""
    from bubbot.data.ggacr_aliases import match_ggacr_game_only

    normalized = re.sub(r"\s+", " ", str(text or "").strip())
    if not normalized:
        return None
    if match_ggacr_game_only(normalized):
        return "ggacr"
    for game_key, pattern in _GAME_ONLY_MENTION_PATTERNS:
        if pattern is not None and pattern.fullmatch(normalized):
            return game_key
    return None


def _game_label(game):
    return _MENU_GAME_LABELS.get(str(game or "").strip().lower(), str(game or "").replace("_", " ").title())


def _game_colour(game):
    return _MENU_GAME_COLOURS.get(str(game or "").strip().lower(), 0xAAAAAA)


def _character_list(game):
    if game == "sf6":
        return _sf6_character_list()
    if game == "ggst":
        return _ggst_character_list()
    if game == "sfv":
        return _sfv_character_list()
    if game == "tuco":
        return _tuco_character_list()
    if game == "bbcf":
        return _bbcf_character_list()
    if game == "ggacr":
        return _ggacr_character_list()
    if game == "cotw":
        return _cotw_character_list()
    if game == "third_strike":
        return _third_strike_character_list()
    if game == "mk1":
        return _mk1_character_list()
    return []


def _sf6_move_list(char_key):
    return move_choices(FRAME_DATA.get(char_key, []))


def _ggst_move_list(char_key):
    def label_fn(row):
        move_name = str(row.get("moveName", "")).strip()
        num_cmd = str(row.get("numCmd", "")).strip()
        state_label = str(row.get("state_label", "")).strip()
        if state_label:
            return f"{move_name} ({num_cmd}) [{state_label}]"
        if num_cmd:
            return f"{move_name} ({num_cmd})"
        return move_name

    normal_rows = GGST_FRAME_DATA.get(char_key, [])
    supplemental_rows = GGST_SUPPLEMENTAL_FRAME_DATA.get(char_key, [])
    state_rows = GGST_STATE_FRAME_DATA.get(char_key, {})
    state_row_list = []
    for state_key_rows in state_rows.values():
        state_row_list.extend(state_key_rows)
    all_rows = normal_rows + supplemental_rows + state_row_list
    if not supplemental_rows and not state_row_list:
        return move_choices(normal_rows, label_fn=label_fn, key_fields=("moveName", "numCmd", "state_label"))
    seen = set()
    deduped = []
    for row in all_rows:
        key = (str(row.get("moveName", "")), str(row.get("numCmd", "")), str(row.get("state_key", "")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return move_choices(deduped, label_fn=label_fn, key_fields=("moveName", "numCmd", "state_label"))


def _tuco_move_list(char_key):
    return move_choices(TUCO_FRAME_DATA.get(char_key, []), key_fields=("moveName", "numCmd"))


def _sfv_move_list(char_key):
    def label_fn(row):
        move_name = str(row.get("moveName", "")).strip()
        num_cmd = str(row.get("numCmd", "")).strip()
        state_label = str(row.get("state_label", "")).strip()
        label = f"{move_name} ({num_cmd})" if move_name and num_cmd else move_name or num_cmd
        return f"{label} [{state_label}]" if state_label else label

    rows = list(SFV_FRAME_DATA.get(char_key, []) or [])
    for state_rows in (SFV_TRIGGER_FRAME_DATA.get(char_key, {}) or {}).values():
        rows.extend(state_rows)
    return move_choices(rows, label_fn=label_fn, key_fields=("moveName", "numCmd", "state_label"))


def _bbcf_move_list(char_key):
    return move_choices(BBCF_FRAME_DATA.get(char_key, []), key_fields=("moveName", "numCmd", "moveType"))


def _ggacr_move_list(char_key):
    return move_choices(GGACR_FRAME_DATA.get(char_key, []), key_fields=("moveName", "numCmd", "moveType"))


def _cotw_move_list(char_key):
    return move_choices(COTW_FRAME_DATA.get(char_key, []), key_fields=("moveName", "numCmd", "moveType"))


def _third_strike_move_list(char_key):
    return move_choices(THIRD_STRIKE_FRAME_DATA.get(char_key, []), key_fields=("moveName", "numCmd", "version", "moveType"))


def _mk1_move_list(char_key):
    return move_choices(MK1_FRAME_DATA.get(char_key, []), key_fields=("moveName", "numCmd", "moveType"))


def _move_list(game, char_key):
    if game == "sf6":
        return _sf6_move_list(char_key)
    if game == "ggst":
        return _ggst_move_list(char_key)
    if game == "sfv":
        return _sfv_move_list(char_key)
    if game == "tuco":
        return _tuco_move_list(char_key)
    if game == "bbcf":
        return _bbcf_move_list(char_key)
    if game == "ggacr":
        return _ggacr_move_list(char_key)
    if game == "cotw":
        return _cotw_move_list(char_key)
    if game == "third_strike":
        return _third_strike_move_list(char_key)
    if game == "mk1":
        return _mk1_move_list(char_key)
    return []


def _character_display_name(game, char_key):
    chars = _character_list(game)
    return dict(chars).get(char_key, str(char_key).title())


def _normalize_search_text(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _search_matches(label, query):
    normalized_label = _normalize_search_text(label)
    normalized_query = _normalize_search_text(query)
    if not normalized_query:
        return True
    compact_label = re.sub(r"[^a-z0-9]+", "", normalized_label)
    compact_query = re.sub(r"[^a-z0-9]+", "", normalized_query)
    if compact_query and compact_query in compact_label:
        return True
    return all(term in normalized_label for term in normalized_query.split())


def _filter_character_choices(chars, query):
    if not str(query or "").strip():
        return list(chars)
    return [(char_key, display) for char_key, display in chars if _search_matches(display, query)]


def _filter_move_choices(moves, query):
    if not str(query or "").strip():
        return list(moves)
    return [(row, label) for row, label in moves if _search_matches(label, query)]


def _row_character_key(game, row, fallback=None):
    if fallback:
        return fallback
    for key_name in ("char_key", "character_key"):
        value = str((row or {}).get(key_name, "")).strip()
        if value:
            return value
    row_name = str((row or {}).get("char_name", "")).strip().lower()
    if not row_name:
        return None
    normalized_row_name = _normalize_search_text(row_name)
    for char_key, display in _character_list(game):
        if _normalize_search_text(display) == normalized_row_name:
            return char_key
        if _normalize_search_text(char_key) == normalized_row_name:
            return char_key
    return None
