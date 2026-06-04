import io
import math
import os
import re

import discord

from bubbot.utils.choice_utils import character_choices, move_choices

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
COTW_FRAME_DATA = {}
COTW_CHARACTER_ALIASES = {}
THIRD_STRIKE_FRAME_DATA = {}
THIRD_STRIKE_CHARACTER_ALIASES = {}
MK1_FRAME_DATA = {}
MK1_CHARACTER_ALIASES = {}
MK1_COMBO_DATA = {}

quiz_module = None
build_sf6_frame_embed = None
build_ggst_frame_embed = None
build_sfv_frame_embed = None
build_tuco_frame_embed = None
build_bbcf_frame_embed = None
build_cotw_frame_embed = None
build_third_strike_frame_embed = None
send_frame_embeds_with_views = None


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
    cotw_frame_data=None,
    cotw_character_aliases=None,
    third_strike_frame_data=None,
    third_strike_character_aliases=None,
    mk1_frame_data=None,
    mk1_character_aliases=None,
    mk1_combo_data=None,
    quiz_module_ref=None,
    build_sf6_frame_embed_fn=None,
    build_ggst_frame_embed_fn=None,
    build_sfv_frame_embed_fn=None,
    build_tuco_frame_embed_fn=None,
    build_bbcf_frame_embed_fn=None,
    build_cotw_frame_embed_fn=None,
    build_third_strike_frame_embed_fn=None,
    send_frame_embeds_with_views_fn=None,
):
    global FRAME_DATA, FRAME_STATS, CHARACTER_ALIASES, GGST_FRAME_DATA, GGST_CHARACTER_ALIASES, GGST_SUPPLEMENTAL_FRAME_DATA, GGST_STATE_FRAME_DATA, SFV_FRAME_DATA, SFV_CHARACTER_ALIASES, SFV_TRIGGER_FRAME_DATA, TUCO_FRAME_DATA, TUCO_CHARACTER_ALIASES, BBCF_FRAME_DATA, BBCF_CHARACTER_ALIASES, COTW_FRAME_DATA, COTW_CHARACTER_ALIASES, THIRD_STRIKE_FRAME_DATA, THIRD_STRIKE_CHARACTER_ALIASES, MK1_FRAME_DATA, MK1_CHARACTER_ALIASES, MK1_COMBO_DATA
    global quiz_module, build_sf6_frame_embed, build_ggst_frame_embed, build_sfv_frame_embed, build_tuco_frame_embed, build_bbcf_frame_embed, build_cotw_frame_embed, build_third_strike_frame_embed, send_frame_embeds_with_views
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
    COTW_FRAME_DATA = cotw_frame_data or {}
    COTW_CHARACTER_ALIASES = cotw_character_aliases or {}
    THIRD_STRIKE_FRAME_DATA = third_strike_frame_data or {}
    THIRD_STRIKE_CHARACTER_ALIASES = third_strike_character_aliases or {}
    MK1_FRAME_DATA = mk1_frame_data or {}
    MK1_CHARACTER_ALIASES = mk1_character_aliases or {}
    MK1_COMBO_DATA = mk1_combo_data or {}
    quiz_module = quiz_module_ref
    build_sf6_frame_embed = build_sf6_frame_embed_fn
    build_ggst_frame_embed = build_ggst_frame_embed_fn
    build_sfv_frame_embed = build_sfv_frame_embed_fn
    build_tuco_frame_embed = build_tuco_frame_embed_fn
    build_bbcf_frame_embed = build_bbcf_frame_embed_fn
    build_cotw_frame_embed = build_cotw_frame_embed_fn
    build_third_strike_frame_embed = build_third_strike_frame_embed_fn
    send_frame_embeds_with_views = send_frame_embeds_with_views_fn


MENU_SELECT_LIMIT = 25


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


def _menu_locked_owner_id(view):
    if getattr(view, "menu_locked", False):
        return getattr(view, "owner_id", None)
    return None


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


def _mk1_combo_character_list():
    return character_choices(MK1_COMBO_DATA)


def _game_label(game):
    if game == "sf6":
        return "Street Fighter 6"
    if game == "ggst":
        return "Guilty Gear Strive"
    if game == "sfv":
        return "Street Fighter V"
    if game == "tuco":
        return "2XKO"
    if game == "bbcf":
        return "BlazBlue Central Fiction"
    if game == "cotw":
        return "City of the Wolves"
    if game == "third_strike":
        return "Third Strike"
    if game == "mk1":
        return "Mortal Kombat 1"
    return str(game).upper()


def _game_colour(game):
    if game == "sf6":
        return 0x3998C6
    if game == "ggst":
        return 0x7A2BFF
    if game == "sfv":
        return 0xD0342C
    if game == "tuco":
        return 0xD63C2F
    if game == "bbcf":
        return 0x1B5FA7
    if game == "cotw":
        return 0xD8A234
    if game == "third_strike":
        return 0xC0392B
    if game == "mk1":
        return 0x7E1616
    return 0xAAAAAA


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


class StatsCompareButton(discord.ui.Button):
    def __init__(self, char_key, owner_id, stat_keys=None):
        super().__init__(label="Compare", style=discord.ButtonStyle.success)
        self.char_key = char_key
        self.owner_id = owner_id
        self.stat_keys = tuple(stat_keys) if stat_keys else None

    async def callback(self, interaction: discord.Interaction):
        if getattr(self.view, "menu_locked", False) and interaction.user.id != getattr(self.view, "owner_id", None):
            await interaction.response.send_message(
                "Only the person who opened this menu can control it.",
                ephemeral=True,
            )
            return
        chars = _sf6_stats_character_list()
        if not chars:
            await interaction.response.send_message("No character stats loaded.", ephemeral=True)
            return
        from bubbot.frame_data.sf6_character_stats import display_character_name

        stats_row = FRAME_STATS.get(self.char_key) or {}
        compare_label = display_character_name(self.char_key, stats_row)
        await interaction.response.edit_message(
            embed=_character_select_embed(
                "sf6",
                page=0,
                total_pages=max(1, math.ceil(len(chars) / MENU_SELECT_LIMIT)),
                stats_mode=True,
                compare_char_key=self.char_key,
                compare_stat_label=compare_label,
            ),
            view=CharacterSelectView(
                "sf6",
                chars,
                _menu_locked_owner_id(self.view) or interaction.user.id,
                page=0,
                stats_mode=True,
                compare_char_key=self.char_key,
                compare_stat_keys=self.stat_keys,
                menu_locked=getattr(self.view, "menu_locked", False),
            ),
            attachments=[],
        )


class CompareFrameButton(discord.ui.Button):
    def __init__(self, game, row, owner_id, char_key=None):
        super().__init__(label="Compare", style=discord.ButtonStyle.success)
        self.game = game
        self.frame_row = row
        self.owner_id = owner_id
        self.char_key = char_key

    async def callback(self, interaction: discord.Interaction):
        if getattr(self.view, "menu_locked", False) and interaction.user.id != getattr(self.view, "owner_id", None):
            await interaction.response.send_message(
                "Only the person who opened this menu can control it.",
                ephemeral=True,
            )
            return
        char_key = _row_character_key(self.game, self.frame_row, self.char_key)
        if not char_key:
            await interaction.response.send_message("I could not find that character's move list.", ephemeral=True)
            return
        chars = _character_list(self.game)
        if not chars:
            await interaction.response.send_message("No characters found for this game.", ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=_character_select_embed(
                self.game,
                page=0,
                total_pages=max(1, math.ceil(len(chars) / MENU_SELECT_LIMIT)),
                compare_row=self.frame_row,
            ),
            view=CharacterSelectView(
                self.game,
                chars,
                _menu_locked_owner_id(self.view) or interaction.user.id,
                page=0,
                compare_row=self.frame_row,
                compare_char_key=char_key,
                menu_locked=getattr(self.view, "menu_locked", False),
            ),
            attachments=[],
        )


class FrameReturnMenuButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Return to Menu", style=discord.ButtonStyle.primary, custom_id="frame_return_menu", row=1)

    async def callback(self, interaction: discord.Interaction):
        menu_owner = getattr(self.view, "owner_id", None) if getattr(self.view, "menu_locked", False) else interaction.user.id
        await interaction.response.edit_message(
            embed=_main_menu_embed(),
            view=MainMenuView(menu_owner),
            attachments=[],
        )


class FrameBackToMovesButton(discord.ui.Button):
    def __init__(self, game, char_key):
        super().__init__(label="Back to Moves", style=discord.ButtonStyle.danger, custom_id="frame_back_moves", row=1)
        self.game = game
        self.char_key = char_key

    async def callback(self, interaction: discord.Interaction):
        moves = _move_list(self.game, self.char_key)
        display = _character_display_name(self.game, self.char_key)
        owner_id = _menu_locked_owner_id(self.view) or interaction.user.id
        await interaction.response.edit_message(
            embed=_move_select_embed(display, page=0, total_pages=max(1, math.ceil(len(moves) / MENU_SELECT_LIMIT))),
            view=MoveSelectView(self.game, self.char_key, moves, owner_id, page=0, menu_locked=True),
            attachments=[],
        )


def build_frame_result_view(game, row, owner_id=None, char_key=None, *, menu_locked=False, show_back_to_moves=None):
    resolved_char_key = char_key or _row_character_key(game, row)
    if show_back_to_moves is None:
        show_back_to_moves = menu_locked
    return FrameResultView(
        game,
        resolved_char_key,
        row,
        owner_id,
        menu_locked=menu_locked,
        show_back_to_moves=show_back_to_moves,
        show_return_menu=True,
    )


async def prepare_cotw_frame_view(view):
    if getattr(view, "game", None) != "cotw":
        return
    from bubbot.frame_data.cotw_frame_data import build_image_attachment

    file, attachment_url = await build_image_attachment(view.row)
    if file and attachment_url:
        view.image_url_override = attachment_url
        view.cotw_image_bytes = file.fp.getvalue()
        view.cotw_image_filename = file.filename


async def send_frame_result_messages(channel, game, rows, *, owner_id=None, menu_locked=False):
    sent_ids = []
    for row in rows or []:
        view = build_frame_result_view(
            game,
            row,
            owner_id=owner_id,
            menu_locked=menu_locked,
        )
        await prepare_cotw_frame_view(view)
        sent = await channel.send(embed=view.build_embed(), view=view, files=view.initial_files())
        sent_ids.append(sent.id)
    return sent_ids


def attach_compare_button(view, game, row, owner_id=None, char_key=None):
    resolved_char_key = _row_character_key(game, row, char_key)
    if not resolved_char_key or not _move_list(game, resolved_char_key):
        return
    view.add_item(CompareFrameButton(game, row, owner_id, char_key=resolved_char_key))


class MainMenuView(OwnedView):
    def __init__(self, owner_id):
        super().__init__(owner_id=owner_id, menu_locked=True, timeout=None)

    @discord.ui.button(label="Street Fighter 6", style=discord.ButtonStyle.primary, custom_id="menu_sf6", row=0)
    async def sf6_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_game_menu_embed("Street Fighter 6", 0x3998C6),
            view=SF6GameMenuView(self.owner_id),
            attachments=[],
        )

    @discord.ui.button(label="Guilty Gear Strive", style=discord.ButtonStyle.danger, custom_id="menu_ggst", row=0)
    async def ggst_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_game_menu_embed("Guilty Gear Strive", 0x7A2BFF),
            view=GameMenuView("ggst", self.owner_id),
            attachments=[],
        )

    @discord.ui.button(label="COTW", style=discord.ButtonStyle.primary, custom_id="menu_cotw", row=0)
    async def cotw_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_game_menu_embed("City of the Wolves", 0xD8A234),
            view=GameMenuView("cotw", self.owner_id),
            attachments=[],
        )

    @discord.ui.button(label="BBCF", style=discord.ButtonStyle.primary, custom_id="menu_bbcf", row=1)
    async def bbcf_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_game_menu_embed("BlazBlue Central Fiction", 0x1B5FA7),
            view=GameMenuView("bbcf", self.owner_id),
            attachments=[],
        )

    @discord.ui.button(label="2XKO", style=discord.ButtonStyle.success, custom_id="menu_tuco", row=1)
    async def tuco_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_game_menu_embed("2XKO", 0xD63C2F),
            view=GameMenuView("tuco", self.owner_id),
            attachments=[],
        )

    @discord.ui.button(label="Third Strike", style=discord.ButtonStyle.danger, custom_id="menu_third_strike", row=1)
    async def third_strike_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_game_menu_embed("Third Strike", 0xC0392B),
            view=GameMenuView("third_strike", self.owner_id),
            attachments=[],
        )

    @discord.ui.button(label="MK1", style=discord.ButtonStyle.danger, custom_id="menu_mk1", row=2)
    async def mk1_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_game_menu_embed("Mortal Kombat 1", 0x7E1616),
            view=GameMenuView("mk1", self.owner_id),
            attachments=[],
        )

    @discord.ui.button(label="SFV", style=discord.ButtonStyle.primary, custom_id="menu_sfv", row=2)
    async def sfv_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_game_menu_embed("Street Fighter V", 0xD0342C),
            view=GameMenuView("sfv", self.owner_id),
            attachments=[],
        )

    @discord.ui.button(label="Readme", style=discord.ButtonStyle.success, custom_id="menu_readme", row=2)
    async def readme_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=build_readme_embed(),
            view=ReadmeView(self.owner_id),
            attachments=[],
        )


class ReadmeView(OwnedView):
    def __init__(self, owner_id):
        super().__init__(owner_id=owner_id, menu_locked=True, timeout=None)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, custom_id="readme_back")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_main_menu_embed(),
            view=MainMenuView(self.owner_id),
            attachments=[],
        )


class GameMenuView(OwnedView):
    def __init__(self, game, owner_id):
        super().__init__(owner_id=owner_id, menu_locked=True, timeout=None)
        self.game = game

    @discord.ui.button(label="Frame Data", style=discord.ButtonStyle.primary, custom_id="game_framedata", row=0)
    async def framedata_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_framedata_character_select(interaction, self.game, self.owner_id)

    @discord.ui.button(label="Quiz", style=discord.ButtonStyle.success, custom_id="game_quiz", row=0)
    async def quiz_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_quiz_difficulty(interaction, self.game, self.owner_id)

    @discord.ui.button(label="Combos", style=discord.ButtonStyle.primary, custom_id="game_combos", row=0)
    async def combos_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game == "mk1":
            chars = _mk1_combo_character_list()
            if not chars:
                await interaction.response.send_message("No MK1 combo data loaded.", ephemeral=True)
                return
            await interaction.response.edit_message(
                embed=_combo_character_select_embed(page=0, total_pages=max(1, math.ceil(len(chars) / MENU_SELECT_LIMIT))),
                view=ComboCharacterSelectView(chars, self.owner_id, page=0),
                attachments=[],
            )
            return
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Combos",
                description="Combos will be added to the scrolls soon.",
                colour=0xAAAAAA,
            ),
            view=BackToGameMenuView(self.game, self.owner_id),
            attachments=[],
        )

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, custom_id="game_back", row=0)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_main_menu_embed(),
            view=MainMenuView(self.owner_id),
            attachments=[],
        )


class SF6GameMenuView(OwnedView):
    def __init__(self, owner_id):
        super().__init__(owner_id=owner_id, menu_locked=True, timeout=None)
        self.game = "sf6"

    @discord.ui.button(label="Frame Data", style=discord.ButtonStyle.primary, custom_id="sf6_game_framedata", row=0)
    async def framedata_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_framedata_character_select(interaction, self.game, self.owner_id)

    @discord.ui.button(label="Stats", style=discord.ButtonStyle.primary, custom_id="sf6_game_stats", row=0)
    async def stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_sf6_stats_character_select(interaction, self.owner_id)

    @discord.ui.button(label="Quiz", style=discord.ButtonStyle.success, custom_id="sf6_game_quiz", row=0)
    async def quiz_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_quiz_difficulty(interaction, self.game, self.owner_id)

    @discord.ui.button(label="Combos", style=discord.ButtonStyle.primary, custom_id="sf6_game_combos", row=0)
    async def combos_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Combos",
                description="Combos will be added to the scrolls soon.",
                colour=0xAAAAAA,
            ),
            view=BackToGameMenuView(self.game, self.owner_id),
            attachments=[],
        )

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, custom_id="sf6_game_back", row=0)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_main_menu_embed(),
            view=MainMenuView(self.owner_id),
            attachments=[],
        )


class CharacterSelectView(OwnedView):
    def __init__(
        self,
        game,
        chars,
        owner_id,
        page=0,
        compare_row=None,
        compare_char_key=None,
        stats_mode=False,
        compare_stat_keys=None,
        menu_locked=True,
    ):
        super().__init__(owner_id=owner_id, menu_locked=menu_locked, timeout=None)
        self.game = game
        self.chars = chars
        self.page = page
        self.compare_row = compare_row
        self.compare_char_key = compare_char_key
        self.stats_mode = stats_mode
        self.compare_stat_keys = compare_stat_keys
        self._add_select()
        self._update_page_buttons()

    def _page_count(self):
        return max(1, math.ceil(len(self.chars) / MENU_SELECT_LIMIT))

    def _update_page_buttons(self):
        page_count = self._page_count()
        previous_page = self.page - 1 if self.page > 0 else page_count - 1
        next_page = self.page + 1 if self.page < page_count - 1 else 0
        self.previous_button.label = f"Previous ({previous_page + 1}/{page_count})"
        self.next_button.label = f"Next ({next_page + 1}/{page_count})"
        if self.compare_row is not None:
            self.back_button.label = "Back to Moves"
        elif self.stats_mode and self.compare_char_key:
            self.back_button.label = "Back to Stats"

    def _add_select(self):
        start = self.page * MENU_SELECT_LIMIT
        page_chars = self.chars[start : start + MENU_SELECT_LIMIT]
        options = [
            discord.SelectOption(label=display, value=char_key)
            for char_key, display in page_chars
        ]
        select = CharacterSelect(
            self.game,
            self.chars,
            self.page,
            self.owner_id,
            options,
            compare_row=self.compare_row,
            compare_char_key=self.compare_char_key,
            stats_mode=self.stats_mode,
            compare_stat_keys=self.compare_stat_keys,
        )
        self.add_item(select)

    def _child_character_select_view(self, page):
        return CharacterSelectView(
            self.game,
            self.chars,
            self.owner_id,
            page=page,
            compare_row=self.compare_row,
            compare_char_key=self.compare_char_key,
            stats_mode=self.stats_mode,
            compare_stat_keys=self.compare_stat_keys,
            menu_locked=self.menu_locked,
        )

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, row=4)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, math.ceil(len(self.chars) / MENU_SELECT_LIMIT) - 1)
        new_page = self.page - 1 if self.page > 0 else max_page
        await interaction.response.edit_message(
            embed=_character_select_embed(
                self.game,
                page=new_page,
                total_pages=max_page + 1,
                compare_row=self.compare_row,
                stats_mode=self.stats_mode,
                compare_char_key=self.compare_char_key,
                compare_stat_label=self._stats_compare_label(),
            ),
            view=self._child_character_select_view(new_page),
            attachments=[],
        )

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, row=4)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, math.ceil(len(self.chars) / MENU_SELECT_LIMIT) - 1)
        new_page = self.page + 1 if self.page < max_page else 0
        await interaction.response.edit_message(
            embed=_character_select_embed(
                self.game,
                page=new_page,
                total_pages=max_page + 1,
                compare_row=self.compare_row,
                stats_mode=self.stats_mode,
                compare_char_key=self.compare_char_key,
                compare_stat_label=self._stats_compare_label(),
            ),
            view=self._child_character_select_view(new_page),
            attachments=[],
        )

    def _stats_compare_label(self):
        if not self.stats_mode or not self.compare_char_key:
            return None
        from bubbot.frame_data.sf6_character_stats import display_character_name

        stats_row = FRAME_STATS.get(self.compare_char_key) or {}
        return display_character_name(self.compare_char_key, stats_row)

    @discord.ui.button(label="Search", style=discord.ButtonStyle.primary, row=4)
    async def search_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            CharacterSearchModal(
                self.game,
                self.owner_id,
                compare_row=self.compare_row,
                compare_char_key=self.compare_char_key,
                stats_mode=self.stats_mode,
                compare_stat_keys=self.compare_stat_keys,
                menu_locked=self.menu_locked,
            )
        )

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, row=4)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.stats_mode and self.compare_char_key:
            await _show_sf6_stats_embed(
                interaction,
                self.compare_char_key,
                self.owner_id,
                stat_keys=self.compare_stat_keys,
            )
            return
        if self.compare_row is not None:
            moves = _move_list(self.game, self.compare_char_key or self.chars[0][0])
            display = _character_display_name(self.game, self.compare_char_key or self.chars[0][0])
            await interaction.response.edit_message(
                embed=_move_select_embed(
                    display,
                    page=0,
                    total_pages=max(1, math.ceil(len(moves) / MENU_SELECT_LIMIT)),
                    compare_row=self.compare_row,
                ),
                view=MoveSelectView(
                    self.game,
                    self.compare_char_key or self.chars[0][0],
                    moves,
                    self.owner_id,
                    page=0,
                    compare_row=self.compare_row,
                    compare_char_key=self.compare_char_key,
                    menu_locked=self.menu_locked,
                ),
                attachments=[],
            )
            return
        game_label = _game_label(self.game)
        colour = _game_colour(self.game)
        await interaction.response.edit_message(
            embed=_game_menu_embed(game_label, colour),
            view=_game_menu_view(self.game, self.owner_id),
            attachments=[],
        )


class CharacterSearchModal(discord.ui.Modal):
    def __init__(
        self,
        game,
        owner_id,
        compare_row=None,
        compare_char_key=None,
        stats_mode=False,
        compare_stat_keys=None,
        menu_locked=True,
    ):
        super().__init__(title="Search Characters")
        self.game = game
        self.owner_id = owner_id
        self.compare_row = compare_row
        self.compare_char_key = compare_char_key
        self.stats_mode = stats_mode
        self.compare_stat_keys = compare_stat_keys
        self.menu_locked = menu_locked
        self.query = discord.ui.TextInput(
            label="Character search",
            placeholder="Example: ryu, sol, happy chaos",
            required=False,
            max_length=80,
        )
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction):
        if self.menu_locked and interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the person who opened this menu can search it.", ephemeral=True)
            return
        chars = _sf6_stats_character_list() if self.stats_mode else _character_list(self.game)
        filtered = _filter_character_choices(chars, str(self.query.value))
        if not filtered:
            await interaction.response.send_message("No characters matched that search.", ephemeral=True)
            return
        compare_stat_label = None
        if self.stats_mode and self.compare_char_key:
            from bubbot.frame_data.sf6_character_stats import display_character_name

            stats_row = FRAME_STATS.get(self.compare_char_key) or {}
            compare_stat_label = display_character_name(self.compare_char_key, stats_row)
        await interaction.response.edit_message(
            embed=_character_select_embed(
                self.game,
                page=0,
                total_pages=max(1, math.ceil(len(filtered) / MENU_SELECT_LIMIT)),
                search_query=str(self.query.value).strip(),
                compare_row=self.compare_row,
                stats_mode=self.stats_mode,
                compare_char_key=self.compare_char_key,
                compare_stat_label=compare_stat_label,
            ),
            view=CharacterSelectView(
                self.game,
                filtered,
                self.owner_id,
                page=0,
                compare_row=self.compare_row,
                compare_char_key=self.compare_char_key,
                stats_mode=self.stats_mode,
                compare_stat_keys=self.compare_stat_keys,
                menu_locked=self.menu_locked,
            ),
            attachments=[],
        )


class CharacterSelect(discord.ui.Select):
    def __init__(
        self,
        game,
        chars,
        page,
        owner_id,
        options,
        compare_row=None,
        compare_char_key=None,
        stats_mode=False,
        compare_stat_keys=None,
    ):
        self.game = game
        self.chars = chars
        self.page = page
        self.compare_row = compare_row
        self.compare_char_key = compare_char_key
        self.stats_mode = stats_mode
        self.compare_stat_keys = compare_stat_keys
        placeholder = "Select a character"
        super().__init__(placeholder=placeholder, options=options, custom_id=f"char_select:{game}:{page}:{owner_id}")

    async def callback(self, interaction: discord.Interaction):
        char_key = self.values[0]
        display = char_key.title()
        for opt in self.options:
            if opt.value == char_key:
                display = opt.label
                break
        if self.stats_mode:
            if self.compare_char_key:
                await _show_sf6_stats_compare_embed(
                    interaction,
                    self.compare_char_key,
                    char_key,
                    self.view.owner_id,
                    stat_keys=self.compare_stat_keys,
                    menu_locked=getattr(self.view, "menu_locked", True),
                )
            else:
                await _show_sf6_stats_embed(interaction, char_key, self.view.owner_id)
            return
        moves = _move_list(self.game, char_key)
        if not moves:
            await interaction.response.send_message("No moves found for this character.", ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=_move_select_embed(
                display,
                page=0,
                total_pages=max(1, math.ceil(len(moves) / MENU_SELECT_LIMIT)),
                compare_row=self.compare_row,
            ),
            view=MoveSelectView(
                self.game,
                char_key,
                moves,
                self.view.owner_id,
                page=0,
                compare_row=self.compare_row,
                compare_char_key=self.compare_char_key,
                menu_locked=getattr(self.view, "menu_locked", True),
            ),
            attachments=[],
        )


class MoveSelectView(OwnedView):
    def __init__(self, game, char_key, moves, owner_id, page=0, compare_row=None, compare_char_key=None, menu_locked=True):
        super().__init__(owner_id=owner_id, menu_locked=menu_locked, timeout=None)
        self.game = game
        self.char_key = char_key
        self.moves = moves
        self.page = page
        self.compare_row = compare_row
        self.compare_char_key = compare_char_key
        self._add_select()
        self._update_page_buttons()

    def _page_count(self):
        return max(1, math.ceil(len(self.moves) / MENU_SELECT_LIMIT))

    def _update_page_buttons(self):
        page_count = self._page_count()
        previous_page = self.page - 1 if self.page > 0 else page_count - 1
        next_page = self.page + 1 if self.page < page_count - 1 else 0
        self.previous_button.label = f"Previous ({previous_page + 1}/{page_count})"
        self.next_button.label = f"Next ({next_page + 1}/{page_count})"
        if self.compare_row is not None:
            self.back_button.label = "Back to Characters"

    def _add_select(self):
        start = self.page * MENU_SELECT_LIMIT
        page_moves = self.moves[start : start + MENU_SELECT_LIMIT]
        options = []
        for i, (row, label) in enumerate(page_moves):
            truncated = label[:100] if len(label) > 100 else label
            options.append(discord.SelectOption(label=truncated, value=f"{self.char_key}|{start + i}"))
        select = MoveSelect(
            self.game,
            self.char_key,
            self.moves,
            self.page,
            options,
            compare_row=self.compare_row,
            compare_char_key=self.compare_char_key,
        )
        self.add_item(select)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, row=4)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, math.ceil(len(self.moves) / MENU_SELECT_LIMIT) - 1)
        new_page = self.page - 1 if self.page > 0 else max_page
        await interaction.response.edit_message(
            embed=_move_select_embed(
                _character_display_name(self.game, self.char_key),
                page=new_page,
                total_pages=max_page + 1,
                compare_row=self.compare_row,
            ),
            view=MoveSelectView(
                self.game,
                self.char_key,
                self.moves,
                self.owner_id,
                page=new_page,
                compare_row=self.compare_row,
                compare_char_key=self.compare_char_key,
                menu_locked=self.menu_locked,
            ),
            attachments=[],
        )

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, row=4)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, math.ceil(len(self.moves) / MENU_SELECT_LIMIT) - 1)
        new_page = self.page + 1 if self.page < max_page else 0
        await interaction.response.edit_message(
            embed=_move_select_embed(
                _character_display_name(self.game, self.char_key),
                page=new_page,
                total_pages=max_page + 1,
                compare_row=self.compare_row,
            ),
            view=MoveSelectView(
                self.game,
                self.char_key,
                self.moves,
                self.owner_id,
                page=new_page,
                compare_row=self.compare_row,
                compare_char_key=self.compare_char_key,
                menu_locked=self.menu_locked,
            ),
            attachments=[],
        )

    @discord.ui.button(label="Search", style=discord.ButtonStyle.primary, row=4)
    async def search_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            MoveSearchModal(
                self.game,
                self.char_key,
                self.owner_id,
                compare_row=self.compare_row,
                compare_char_key=self.compare_char_key,
                menu_locked=self.menu_locked,
            )
        )

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, row=4)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        chars = _character_list(self.game)
        await interaction.response.edit_message(
            embed=_character_select_embed(
                self.game,
                page=0,
                total_pages=max(1, math.ceil(len(chars) / MENU_SELECT_LIMIT)),
                compare_row=self.compare_row,
            ),
            view=CharacterSelectView(
                self.game,
                chars,
                self.owner_id,
                page=0,
                compare_row=self.compare_row,
                compare_char_key=self.compare_char_key,
                menu_locked=self.menu_locked,
            ),
            attachments=[],
        )


class MoveSearchModal(discord.ui.Modal):
    def __init__(self, game, char_key, owner_id, compare_row=None, compare_char_key=None, menu_locked=True):
        super().__init__(title="Search Moves")
        self.game = game
        self.char_key = char_key
        self.owner_id = owner_id
        self.compare_row = compare_row
        self.compare_char_key = compare_char_key
        self.menu_locked = menu_locked
        self.query = discord.ui.TextInput(
            label="Move search",
            placeholder="Example: 5hp, fireball, volcanic viper",
            required=False,
            max_length=80,
        )
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction):
        if self.menu_locked and interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the person who opened this menu can search it.", ephemeral=True)
            return
        moves = _move_list(self.game, self.char_key)
        filtered = _filter_move_choices(moves, str(self.query.value))
        if not filtered:
            await interaction.response.send_message("No moves matched that search.", ephemeral=True)
            return
        display = _character_display_name(self.game, self.char_key)
        await interaction.response.edit_message(
            embed=_move_select_embed(
                display,
                page=0,
                total_pages=max(1, math.ceil(len(filtered) / MENU_SELECT_LIMIT)),
                search_query=str(self.query.value).strip(),
                compare_row=self.compare_row,
            ),
            view=MoveSelectView(
                self.game,
                self.char_key,
                filtered,
                self.owner_id,
                page=0,
                compare_row=self.compare_row,
                compare_char_key=self.compare_char_key,
                menu_locked=self.menu_locked,
            ),
            attachments=[],
        )


class MoveSelect(discord.ui.Select):
    def __init__(self, game, char_key, moves, page, options, compare_row=None, compare_char_key=None):
        self.game = game
        self.char_key = char_key
        self.moves = moves
        self.page = page
        self.compare_row = compare_row
        self.compare_char_key = compare_char_key
        placeholder = "Select a move"
        safe_char_key = re.sub(r"[^a-z0-9_.-]", "", str(char_key).lower())[:32]
        super().__init__(placeholder=placeholder, options=options, custom_id=f"move_select:{game}:{safe_char_key}:{page}")

    async def callback(self, interaction: discord.Interaction):
        selected_char, raw_idx = self.values[0].split("|", 1)
        if selected_char != self.char_key:
            await interaction.response.send_message("That move list is stale. Pick the character again.", ephemeral=True)
            return
        idx = int(raw_idx)
        row, label = self.moves[idx]
        if self.compare_row is not None:
            await interaction.response.defer()
            await _edit_frame_result_message(
                interaction.message,
                self.game,
                self.compare_char_key or self.char_key,
                self.compare_row,
                self.view.owner_id,
            )
            sent = await _send_frame_result_message(
                interaction.channel,
                self.game,
                self.char_key,
                row,
                self.view.owner_id,
            )
            return
        view = build_frame_result_view(self.game, row, self.view.owner_id, self.char_key, menu_locked=True)
        await prepare_cotw_frame_view(view)
        await interaction.response.edit_message(embed=view.build_embed(), view=view, attachments=view.initial_files())


async def _send_frame_result_message(channel, game, char_key, row, owner_id):
    view = build_frame_result_view(game, row, owner_id, char_key, menu_locked=True)
    await prepare_cotw_frame_view(view)
    embed = view.build_embed()
    sent = await channel.send(embed=embed, view=view, files=view.initial_files())
    return sent


async def _edit_frame_result_message(message, game, char_key, row, owner_id):
    view = build_frame_result_view(game, row, owner_id, char_key, menu_locked=True)
    await prepare_cotw_frame_view(view)
    await message.edit(embed=view.build_embed(), view=view, attachments=view.initial_files())


class StatsShowFramedataButton(discord.ui.Button):
    def __init__(self, char_key, owner_id):
        super().__init__(label="Show Framedata", style=discord.ButtonStyle.primary)
        self.char_key = char_key
        self.owner_id = owner_id

    async def callback(self, interaction: discord.Interaction):
        if getattr(self.view, "menu_locked", False) and interaction.user.id != getattr(self.view, "owner_id", None):
            await interaction.response.send_message(
                "Only the person who opened this menu can control it.",
                ephemeral=True,
            )
            return
        moves = _move_list("sf6", self.char_key)
        if not moves:
            await interaction.response.send_message("No moves found for this character.", ephemeral=True)
            return
        display = _character_display_name("sf6", self.char_key)
        await interaction.response.edit_message(
            embed=_move_select_embed(
                display,
                page=0,
                total_pages=max(1, math.ceil(len(moves) / MENU_SELECT_LIMIT)),
            ),
            view=MoveSelectView(
                "sf6",
                self.char_key,
                moves,
                getattr(self.view, "owner_id", self.owner_id),
                page=0,
                menu_locked=getattr(self.view, "menu_locked", True),
            ),
            attachments=[],
        )


class StatsResultView(OwnedView):
    def __init__(self, char_key, owner_id, stat_keys=None, compare_char_key=None, *, menu_locked=False):
        super().__init__(owner_id=owner_id, menu_locked=menu_locked, timeout=None)
        self.char_key = char_key
        self.stat_keys = tuple(stat_keys) if stat_keys else None
        self.compare_char_key = compare_char_key
        self.add_item(StatsCompareButton(char_key, owner_id, stat_keys=self.stat_keys))
        self.add_item(StatsShowFramedataButton(char_key, owner_id))
        self.add_item(FrameReturnMenuButton())
        if menu_locked:
            self.add_item(StatsBackToCharactersButton(char_key, owner_id))


class StatsBackToCharactersButton(discord.ui.Button):
    def __init__(self, char_key, owner_id):
        super().__init__(label="Back to Characters", style=discord.ButtonStyle.danger, custom_id="stats_back_characters", row=1)
        self.char_key = char_key
        self.owner_id = owner_id

    async def callback(self, interaction: discord.Interaction):
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
            view=CharacterSelectView("sf6", chars, self.owner_id, page=0, stats_mode=True, menu_locked=True),
            attachments=[],
        )


class FrameResultView(OwnedView):
    def __init__(
        self,
        game,
        char_key,
        row,
        owner_id,
        *,
        menu_locked=False,
        show_back_to_moves=False,
        show_return_menu=True,
    ):
        super().__init__(owner_id=owner_id, menu_locked=menu_locked, timeout=None)
        self.game = game
        self.char_key = char_key
        self.row = row
        self.show_notes = False
        self.show_stats = False
        if game == "sf6":
            from bubbot.frame_data.frame_output import FrameDataGifButton, SF6NotesButton, SF6ShowStatsButton
            from bubbot.frame_data.gif_lookup import get_existing_local_gif_asset_paths, get_frame_row_gif_links
            self.gif_links = list(get_frame_row_gif_links(row) or [])
            asset_paths = get_existing_local_gif_asset_paths(self.gif_links, limit=1) if self.gif_links else []
            self.default_gif_asset_path = asset_paths[0] if asset_paths else None
            self.character_stats = FRAME_STATS.get(char_key) or {}
            self.gif_button = FrameDataGifButton(row, self.gif_links, showing_gif=bool(self.default_gif_asset_path))
            self.stats_button = SF6ShowStatsButton(disabled=not self.character_stats)
            self.notes_button = SF6NotesButton(row)
            self.add_item(self.gif_button)
            self.add_item(self.stats_button)
            self.add_item(self.notes_button)
        elif game == "ggst":
            from bubbot.frame_data.ggst_frame_data import GGSTAllHitboxImagesButton, GGSTHitboxButton, GGSTNotesButton
            self.all_hitbox_images_button = GGSTAllHitboxImagesButton(row)
            if len(self.all_hitbox_images_button.hitbox_links) > 1:
                self.add_item(self.all_hitbox_images_button)
            else:
                self.hitbox_button = GGSTHitboxButton(row, showing_hitbox=True)
                self.add_item(self.hitbox_button)
            self.notes_button = GGSTNotesButton(row)
            self.add_item(self.notes_button)
        elif game == "sfv":
            from bubbot.frame_data.sfv_frame_data import SFVNotesButton
            self.notes_button = SFVNotesButton(row)
            self.add_item(self.notes_button)
        elif game == "tuco":
            from bubbot.frame_data.tuco_frame_data import TUCONotesButton
            self.notes_button = TUCONotesButton(row)
            self.add_item(self.notes_button)
        elif game == "bbcf":
            from bubbot.frame_data.bbcf_frame_data import BBCFAllHitboxImagesButton, BBCFHitboxButton, BBCFNotesButton
            self.all_hitbox_images_button = BBCFAllHitboxImagesButton(row)
            if len(self.all_hitbox_images_button.hitbox_links) > 1:
                self.add_item(self.all_hitbox_images_button)
            else:
                self.hitbox_button = BBCFHitboxButton(row, showing_hitbox=True)
                self.add_item(self.hitbox_button)
            self.notes_button = BBCFNotesButton(row)
            self.add_item(self.notes_button)
        elif game == "third_strike":
            from bubbot.frame_data.third_strike_frame_data import ThirdStrikeAllHitboxImagesButton, ThirdStrikeHitboxButton, ThirdStrikeNotesButton
            self.all_hitbox_images_button = ThirdStrikeAllHitboxImagesButton(row)
            if len(self.all_hitbox_images_button.hitbox_links) > 1:
                self.add_item(self.all_hitbox_images_button)
            else:
                self.hitbox_button = ThirdStrikeHitboxButton(row, showing_hitbox=True)
                self.add_item(self.hitbox_button)
            self.notes_button = ThirdStrikeNotesButton(row)
            self.add_item(self.notes_button)
        elif game == "mk1":
            from bubbot.frame_data.mk1_frame_data import MK1NotesButton
            self.notes_button = MK1NotesButton(row)
            self.add_item(self.notes_button)
        else:
            from bubbot.frame_data.cotw_frame_data import COTWNotesButton
            self.image_url_override = ""
            self.cotw_image_bytes = None
            self.cotw_image_filename = None
            self.notes_button = COTWNotesButton(row)
            self.add_item(self.notes_button)
        attach_compare_button(self, game, row, owner_id=owner_id, char_key=char_key)
        if show_return_menu:
            self.add_item(FrameReturnMenuButton())
        if show_back_to_moves:
            self.add_item(FrameBackToMovesButton(game, char_key))

    def build_embed(self):
        if self.game == "sf6":
            if getattr(self, "show_stats", False) and getattr(self, "character_stats", None):
                from bubbot.frame_data.sf6_character_stats import build_character_stats_embed

                return build_character_stats_embed(self.char_key, self.character_stats)
            if getattr(self, "default_gif_asset_path", None) and getattr(self, "gif_button", None) and self.gif_button.showing_gif:
                filename = os.path.basename(self.default_gif_asset_path)
                return build_sf6_frame_embed(
                    self.row,
                    image_url_override=f"attachment://{filename}",
                    show_notes=getattr(self, "show_notes", False),
                )
            return build_sf6_frame_embed(self.row, show_notes=getattr(self, "show_notes", False))
        if self.game == "ggst":
            from bubbot.frame_data.ggst_frame_data import build_frame_embed
        elif self.game == "sfv":
            from bubbot.frame_data.sfv_frame_data import build_frame_embed
        elif self.game == "tuco":
            from bubbot.frame_data.tuco_frame_data import build_frame_embed
        elif self.game == "bbcf":
            from bubbot.frame_data.bbcf_frame_data import build_frame_embed
        elif self.game == "third_strike":
            from bubbot.frame_data.third_strike_frame_data import build_frame_embed
        elif self.game == "mk1":
            from bubbot.frame_data.mk1_frame_data import build_frame_embed
        else:
            from bubbot.frame_data.cotw_frame_data import build_frame_embed
        embed = build_frame_embed(self.row, show_notes=getattr(self, "show_notes", False))
        all_hitbox_button = getattr(self, "all_hitbox_images_button", None)
        all_hitbox_links = getattr(all_hitbox_button, "hitbox_links", None)
        if all_hitbox_button and len(all_hitbox_links or []) > 1:
            embed.set_image(url=all_hitbox_links[0])
            return embed
        hitbox_button = getattr(self, "hitbox_button", None)
        hitbox_links = getattr(hitbox_button, "hitbox_links", None)
        if hitbox_button and getattr(hitbox_button, "showing_hitbox", False) and hitbox_links:
            embed.set_image(url=hitbox_links[0])
        if self.game == "cotw" and getattr(self, "image_url_override", ""):
            embed.set_image(url=self.image_url_override)
        return embed

    def initial_files(self):
        return self.active_files()

    def active_files(self):
        if self.game == "cotw" and getattr(self, "cotw_image_bytes", None) and getattr(self, "cotw_image_filename", None):
            return [discord.File(io.BytesIO(self.cotw_image_bytes), filename=self.cotw_image_filename)]
        if self.game != "sf6" or not getattr(self, "default_gif_asset_path", None):
            return []
        gif_button = getattr(self, "gif_button", None)
        if not gif_button or not gif_button.showing_gif:
            return []
        filename = os.path.basename(self.default_gif_asset_path)
        return [discord.File(self.default_gif_asset_path, filename=filename)]


class QuizDifficultyView(OwnedView):
    def __init__(self, game, owner_id):
        super().__init__(owner_id=owner_id, menu_locked=True, timeout=None)
        self.game = game

    @discord.ui.button(label="Easy", style=discord.ButtonStyle.success, custom_id="quiz_easy")
    async def easy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._start_quiz(interaction, "easy")

    @discord.ui.button(label="Medium", style=discord.ButtonStyle.primary, custom_id="quiz_medium")
    async def medium_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._start_quiz(interaction, "medium")

    @discord.ui.button(label="Hard", style=discord.ButtonStyle.danger, custom_id="quiz_hard")
    async def hard_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._start_quiz(interaction, "hard")

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, custom_id="quiz_back")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_label = _game_label(self.game)
        colour = _game_colour(self.game)
        await interaction.response.edit_message(
            embed=_game_menu_embed(game_label, colour),
            view=_game_menu_view(self.game, self.owner_id),
            attachments=[],
        )

    async def _start_quiz(self, interaction, difficulty):
        if quiz_module is None:
            await interaction.response.send_message("Quiz system is not available.", ephemeral=True)
            return
        game_label = _game_label(self.game)
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Quiz Started",
                description=f"Starting **{difficulty}** quiz for **{game_label}**.\nGood luck!",
                colour=0x00FF00,
            ),
            view=None,
            attachments=[],
        )
        fake_message = QuizFakeMessage(interaction)
        await quiz_module.start_quiz(fake_message, mode=difficulty, game=self.game)


class BackToGameMenuView(OwnedView):
    def __init__(self, game, owner_id):
        super().__init__(owner_id=owner_id, menu_locked=True, timeout=None)
        self.game = game

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, custom_id="combos_back")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_label = _game_label(self.game)
        colour = _game_colour(self.game)
        await interaction.response.edit_message(
            embed=_game_menu_embed(game_label, colour),
            view=_game_menu_view(self.game, self.owner_id),
            attachments=[],
        )


class ComboCharacterSelectView(OwnedView):
    def __init__(self, chars, owner_id, page=0):
        super().__init__(owner_id=owner_id, menu_locked=True, timeout=None)
        self.chars = chars
        self.page = page
        self._add_select()
        self._update_page_buttons()

    def _page_count(self):
        return max(1, math.ceil(len(self.chars) / MENU_SELECT_LIMIT))

    def _update_page_buttons(self):
        page_count = self._page_count()
        previous_page = self.page - 1 if self.page > 0 else page_count - 1
        next_page = self.page + 1 if self.page < page_count - 1 else 0
        self.previous_button.label = f"Previous ({previous_page + 1}/{page_count})"
        self.next_button.label = f"Next ({next_page + 1}/{page_count})"

    def _add_select(self):
        start = self.page * MENU_SELECT_LIMIT
        options = [discord.SelectOption(label=display, value=char_key) for char_key, display in self.chars[start : start + MENU_SELECT_LIMIT]]
        self.add_item(ComboCharacterSelect(self.chars, self.page, options))

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, row=4)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, math.ceil(len(self.chars) / MENU_SELECT_LIMIT) - 1)
        new_page = self.page - 1 if self.page > 0 else max_page
        await interaction.response.edit_message(
            embed=_combo_character_select_embed(page=new_page, total_pages=max_page + 1),
            view=ComboCharacterSelectView(self.chars, self.owner_id, page=new_page),
            attachments=[],
        )

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, row=4)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, math.ceil(len(self.chars) / MENU_SELECT_LIMIT) - 1)
        new_page = self.page + 1 if self.page < max_page else 0
        await interaction.response.edit_message(
            embed=_combo_character_select_embed(page=new_page, total_pages=max_page + 1),
            view=ComboCharacterSelectView(self.chars, self.owner_id, page=new_page),
            attachments=[],
        )

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, row=4)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_game_menu_embed("Mortal Kombat 1", 0x7E1616),
            view=GameMenuView("mk1", self.owner_id),
            attachments=[],
        )


class ComboCharacterSelect(discord.ui.Select):
    def __init__(self, chars, page, options):
        self.chars = chars
        self.page = page
        super().__init__(placeholder="Select a character", options=options, custom_id=f"mk1_combo_char_select:{page}")

    async def callback(self, interaction: discord.Interaction):
        from bubbot.frame_data.mk1_frame_data import build_combo_embed
        char_key = self.values[0]
        rows = MK1_COMBO_DATA.get(char_key, [])[:8]
        await interaction.response.edit_message(
            embed=build_combo_embed(char_key, rows),
            view=BackToGameMenuView("mk1", self.view.owner_id),
            attachments=[],
        )


class QuizFakeMessage:
    def __init__(self, interaction):
        self.channel = interaction.channel
        self.author = interaction.user
        self.content = ""
        self.id = interaction.id
        self.reference = None
        self.embeds = []
        self.attachments = []

    async def reply(self, content=None, **kwargs):
        return await self.channel.send(content, **kwargs)





def _main_menu_embed():
    return discord.Embed(
        title="Bub Menu",
        description="Select a game to get started, or open Readme for a quick tutorial.",
        colour=0xFFD700,
    )


def build_readme_embed():
    embed = discord.Embed(
        title="Bub Readme",
        description="A quick guide to using Bub for fighting-game frame data, images, menus, and quizzes.",
        colour=0xFFD700,
    )
    embed.add_field(
        name="1. Ask Naturally",
        value=(
            "Mention Bub, then type a character and move. Examples: `@Bub ryu 5hp`, "
            "`@Bub ky far slash`, `@Bub amane 5b`, `@Bub ashrah heavens palm`. "
            "You can add `framedata`, but most direct character+move queries do not need it."
            "Disclaimer: Natural language processing is a WIP for games other than SF6. I recommend using the menu or slash commands for anything esoteric such as installs or stances"

        ),
        inline=False,
    )
    embed.add_field(
        name="2. Use Game Tags When Needed",
        value=(
            "Shared names can be ambiguous. Add tags like `sfv`, `3s`, `ggst`, `bbcf`, `cotw`, "
            "`2xko`, or `mk1` when Bub needs context. Example: `@Bub 3s ken hadouken`."
        ),
        inline=False,
    )
    embed.add_field(
        name="3. Images, Notes, And Hitboxes",
        value=(
            "Ask for `hitbox`, `image`, `gif`, or `notes` when supported. Frame-result buttons can also "
            "toggle images/notes, and some games expose `Show All Images` for multi-image moves."
        ),
        inline=False,
    )
    embed.add_field(
        name="4. Menus And Slash Commands",
        value=(
            "Use `/bub` for the guided menu, or direct commands like `/sf6`, `/sf6-stats` (SF6 stats), `/ggst`, `/bbcf`, "
            "`/cotw`, `/third-strike`, `/mk1`, and `/mk1-combos`. Menus are locked to the user who opened them."
        ),
        inline=False,
    )
    embed.add_field(
        name="5. Quiz And Compare",
        value=(
            "Each game menu has Quiz. The SF6 menu also has Stats between Frame Data and Quiz for character stat sheets. "
            "Frame-data results can include a Compare button that lets you choose another move from the same game "
            "and place the results side by side."
        ),
        inline=False,
    )
    embed.add_field(
        name="Need Help?",
        value="If a valid fighting-game syntax query fails, contact `yimbo3560` with the exact query you used.",
        inline=False,
    )
    return embed


def _game_menu_embed(game_label, colour):
    return discord.Embed(
        title=f"{game_label}",
        description="Select a feature.",
        colour=colour,
    )


def _row_move_label(row):
    move_name = str((row or {}).get("moveName", "")).strip()
    num_cmd = str((row or {}).get("numCmd", "")).strip()
    if move_name and num_cmd:
        return f"{move_name} ({num_cmd})"
    return move_name or num_cmd or "selected move"


def _character_select_embed(
    game,
    page=None,
    total_pages=None,
    search_query=None,
    compare_row=None,
    stats_mode=False,
    compare_char_key=None,
    compare_stat_label=None,
):
    label = _game_label(game)
    page_text = f"\nPage {page + 1}/{total_pages}" if page is not None and total_pages else ""
    search_text = f"\nSearch: `{search_query}`" if search_query else ""
    compare_text = f"\nComparing against: `{_row_move_label(compare_row)}`" if compare_row else ""
    if stats_mode and compare_char_key and compare_stat_label:
        compare_text = f"\nComparing stats against: `{compare_stat_label}`"
    if stats_mode:
        title = f"{label} - {'Compare Stats' if compare_char_key else 'Character Stats'}"
        description = (
            "Select another character to compare stats."
            if compare_char_key
            else "Select a character to view their stats sheet."
        )
    elif compare_row:
        title = f"{label} - Compare"
        description = "Select a character from the dropdown below."
    else:
        title = f"{label} - Frame Data"
        description = "Select a character from the dropdown below."
    return discord.Embed(
        title=title,
        description=f"{description}{page_text}{search_text}{compare_text}",
        colour=_game_colour(game),
    )


def _move_select_embed(char_display, page=None, total_pages=None, search_query=None, compare_row=None):
    page_text = f"\nPage {page + 1}/{total_pages}" if page is not None and total_pages else ""
    search_text = f"\nSearch: `{search_query}`" if search_query else ""
    compare_text = f"\nComparing against: `{_row_move_label(compare_row)}`" if compare_row else ""
    return discord.Embed(
        title=f"{char_display} - {'Compare Move' if compare_row else 'Moves'}",
        description=f"Select a move from the dropdown below.{page_text}{search_text}{compare_text}",
        colour=0x3998C6,
    )


def _quiz_difficulty_embed(game_label):
    return discord.Embed(
        title=f"{game_label} - Quiz",
        description="Select a difficulty level.",
        colour=0x00FF00,
    )


def _combo_character_select_embed(page=None, total_pages=None):
    page_text = f"\nPage {page + 1}/{total_pages}" if page is not None and total_pages else ""
    return discord.Embed(
        title="Mortal Kombat 1 - Combos",
        description=f"Select a character to see available combo routes.{page_text}",
        colour=0x7E1616,
    )


async def send_main_menu(destination, owner_id=None):
    await destination.send(
        embed=_main_menu_embed(),
        view=MainMenuView(owner_id),
    )


async def send_character_moves_menu(destination, game, char_key, owner_id=None):
    moves = _move_list(game, char_key)
    if not moves:
        await destination.send("No moves found for that character.")
        return False
    chars = dict(_character_list(game))
    display = chars.get(char_key, str(char_key).title())
    await destination.send(
        embed=_move_select_embed(display, page=0, total_pages=max(1, math.ceil(len(moves) / MENU_SELECT_LIMIT))),
        view=MoveSelectView(game, char_key, moves, owner_id, page=0, menu_locked=True),
    )
    return True
