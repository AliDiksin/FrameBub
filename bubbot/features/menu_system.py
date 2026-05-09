import io
import math
import os
import re

import discord

from bubbot.utils.choice_utils import character_choices, move_choices

FRAME_DATA = {}
CHARACTER_ALIASES = {}
GGST_FRAME_DATA = {}
GGST_CHARACTER_ALIASES = {}
TUCO_FRAME_DATA = {}
TUCO_CHARACTER_ALIASES = {}
BBCF_FRAME_DATA = {}
BBCF_CHARACTER_ALIASES = {}
COTW_FRAME_DATA = {}
COTW_CHARACTER_ALIASES = {}
THIRD_STRIKE_FRAME_DATA = {}
THIRD_STRIKE_CHARACTER_ALIASES = {}

quiz_module = None
build_sf6_frame_embed = None
build_ggst_frame_embed = None
build_tuco_frame_embed = None
build_bbcf_frame_embed = None
build_cotw_frame_embed = None
build_third_strike_frame_embed = None
send_frame_embeds_with_views = None


def configure(
    frame_data=None,
    character_aliases=None,
    ggst_frame_data=None,
    ggst_character_aliases=None,
    tuco_frame_data=None,
    tuco_character_aliases=None,
    bbcf_frame_data=None,
    bbcf_character_aliases=None,
    cotw_frame_data=None,
    cotw_character_aliases=None,
    third_strike_frame_data=None,
    third_strike_character_aliases=None,
    quiz_module_ref=None,
    build_sf6_frame_embed_fn=None,
    build_ggst_frame_embed_fn=None,
    build_tuco_frame_embed_fn=None,
    build_bbcf_frame_embed_fn=None,
    build_cotw_frame_embed_fn=None,
    build_third_strike_frame_embed_fn=None,
    send_frame_embeds_with_views_fn=None,
):
    global FRAME_DATA, CHARACTER_ALIASES, GGST_FRAME_DATA, GGST_CHARACTER_ALIASES, TUCO_FRAME_DATA, TUCO_CHARACTER_ALIASES, BBCF_FRAME_DATA, BBCF_CHARACTER_ALIASES, COTW_FRAME_DATA, COTW_CHARACTER_ALIASES, THIRD_STRIKE_FRAME_DATA, THIRD_STRIKE_CHARACTER_ALIASES
    global quiz_module, build_sf6_frame_embed, build_ggst_frame_embed, build_tuco_frame_embed, build_bbcf_frame_embed, build_cotw_frame_embed, build_third_strike_frame_embed, send_frame_embeds_with_views
    FRAME_DATA = frame_data or {}
    CHARACTER_ALIASES = character_aliases or {}
    GGST_FRAME_DATA = ggst_frame_data or {}
    GGST_CHARACTER_ALIASES = ggst_character_aliases or {}
    TUCO_FRAME_DATA = tuco_frame_data or {}
    TUCO_CHARACTER_ALIASES = tuco_character_aliases or {}
    BBCF_FRAME_DATA = bbcf_frame_data or {}
    BBCF_CHARACTER_ALIASES = bbcf_character_aliases or {}
    COTW_FRAME_DATA = cotw_frame_data or {}
    COTW_CHARACTER_ALIASES = cotw_character_aliases or {}
    THIRD_STRIKE_FRAME_DATA = third_strike_frame_data or {}
    THIRD_STRIKE_CHARACTER_ALIASES = third_strike_character_aliases or {}
    quiz_module = quiz_module_ref
    build_sf6_frame_embed = build_sf6_frame_embed_fn
    build_ggst_frame_embed = build_ggst_frame_embed_fn
    build_tuco_frame_embed = build_tuco_frame_embed_fn
    build_bbcf_frame_embed = build_bbcf_frame_embed_fn
    build_cotw_frame_embed = build_cotw_frame_embed_fn
    build_third_strike_frame_embed = build_third_strike_frame_embed_fn
    send_frame_embeds_with_views = send_frame_embeds_with_views_fn


MENU_SELECT_LIMIT = 25


class OwnedView(discord.ui.View):
    def __init__(self, owner_id, timeout=300):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only the person who opened this menu can control it.",
                ephemeral=True,
            )
            return False
        return True


def _sf6_character_list():
    return character_choices(FRAME_DATA, display_fn=lambda char_key, _rows: str(char_key).title())


def _ggst_character_list():
    return character_choices(GGST_FRAME_DATA)


def _tuco_character_list():
    return character_choices(TUCO_FRAME_DATA)


def _bbcf_character_list():
    return character_choices(BBCF_FRAME_DATA)


def _cotw_character_list():
    return character_choices(COTW_FRAME_DATA)


def _third_strike_character_list():
    return character_choices(THIRD_STRIKE_FRAME_DATA)


def _game_label(game):
    if game == "sf6":
        return "Street Fighter 6"
    if game == "ggst":
        return "Guilty Gear Strive"
    if game == "tuco":
        return "2XKO"
    if game == "bbcf":
        return "BlazBlue Central Fiction"
    if game == "cotw":
        return "City of the Wolves"
    if game == "third_strike":
        return "Third Strike"
    return str(game).upper()


def _game_colour(game):
    if game == "sf6":
        return 0x3998C6
    if game == "ggst":
        return 0x7A2BFF
    if game == "tuco":
        return 0xD63C2F
    if game == "bbcf":
        return 0x1B5FA7
    if game == "cotw":
        return 0xD8A234
    if game == "third_strike":
        return 0xC0392B
    return 0xAAAAAA


def _character_list(game):
    if game == "sf6":
        return _sf6_character_list()
    if game == "ggst":
        return _ggst_character_list()
    if game == "tuco":
        return _tuco_character_list()
    if game == "bbcf":
        return _bbcf_character_list()
    if game == "cotw":
        return _cotw_character_list()
    if game == "third_strike":
        return _third_strike_character_list()
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

    return move_choices(GGST_FRAME_DATA.get(char_key, []), label_fn=label_fn, key_fields=("moveName", "numCmd", "state_label"))


def _tuco_move_list(char_key):
    return move_choices(TUCO_FRAME_DATA.get(char_key, []), key_fields=("moveName", "numCmd"))


def _bbcf_move_list(char_key):
    return move_choices(BBCF_FRAME_DATA.get(char_key, []), key_fields=("moveName", "numCmd", "moveType"))


def _cotw_move_list(char_key):
    return move_choices(COTW_FRAME_DATA.get(char_key, []), key_fields=("moveName", "numCmd", "moveType"))


def _third_strike_move_list(char_key):
    return move_choices(THIRD_STRIKE_FRAME_DATA.get(char_key, []), key_fields=("moveName", "numCmd", "version", "moveType"))


def _move_list(game, char_key):
    if game == "sf6":
        return _sf6_move_list(char_key)
    if game == "ggst":
        return _ggst_move_list(char_key)
    if game == "tuco":
        return _tuco_move_list(char_key)
    if game == "bbcf":
        return _bbcf_move_list(char_key)
    if game == "cotw":
        return _cotw_move_list(char_key)
    if game == "third_strike":
        return _third_strike_move_list(char_key)
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


class MainMenuView(OwnedView):
    def __init__(self, owner_id):
        super().__init__(owner_id=owner_id, timeout=300)

    @discord.ui.button(label="Street Fighter 6", style=discord.ButtonStyle.primary, custom_id="menu_sf6", row=0)
    async def sf6_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_game_menu_embed("Street Fighter 6", 0x3998C6),
            view=GameMenuView("sf6", self.owner_id),
            attachments=[],
        )

    @discord.ui.button(label="Guilty Gear Strive", style=discord.ButtonStyle.danger, custom_id="menu_ggst", row=0)
    async def ggst_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_game_menu_embed("Guilty Gear Strive", 0x7A2BFF),
            view=GameMenuView("ggst", self.owner_id),
            attachments=[],
        )

    @discord.ui.button(label="COTW", style=discord.ButtonStyle.secondary, custom_id="menu_cotw", row=0)
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


class GameMenuView(OwnedView):
    def __init__(self, game, owner_id):
        super().__init__(owner_id=owner_id, timeout=300)
        self.game = game

    @discord.ui.button(label="Frame Data", style=discord.ButtonStyle.primary, custom_id="game_framedata")
    async def framedata_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        chars = _character_list(self.game)
        if not chars:
            await interaction.response.send_message("No character data loaded.", ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=_character_select_embed(self.game, page=0, total_pages=max(1, math.ceil(len(chars) / MENU_SELECT_LIMIT))),
            view=CharacterSelectView(self.game, chars, self.owner_id, page=0),
            attachments=[],
        )

    @discord.ui.button(label="Quiz", style=discord.ButtonStyle.success, custom_id="game_quiz")
    async def quiz_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_label = _game_label(self.game)
        await interaction.response.edit_message(
            embed=_quiz_difficulty_embed(game_label),
            view=QuizDifficultyView(self.game, self.owner_id),
            attachments=[],
        )

    @discord.ui.button(label="Combos", style=discord.ButtonStyle.secondary, custom_id="game_combos")
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

    @discord.ui.button(label="Back", style=discord.ButtonStyle.grey, custom_id="game_back")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_main_menu_embed(),
            view=MainMenuView(self.owner_id),
            attachments=[],
        )


class CharacterSelectView(OwnedView):
    def __init__(self, game, chars, owner_id, page=0):
        super().__init__(owner_id=owner_id, timeout=300)
        self.game = game
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
        page_chars = self.chars[start : start + MENU_SELECT_LIMIT]
        options = [
            discord.SelectOption(label=display, value=char_key)
            for char_key, display in page_chars
        ]
        select = CharacterSelect(self.game, self.chars, self.page, self.owner_id, options)
        self.add_item(select)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, row=4)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, math.ceil(len(self.chars) / MENU_SELECT_LIMIT) - 1)
        new_page = self.page - 1 if self.page > 0 else max_page
        await interaction.response.edit_message(
            embed=_character_select_embed(self.game, page=new_page, total_pages=max_page + 1),
            view=CharacterSelectView(self.game, self.chars, self.owner_id, page=new_page),
            attachments=[],
        )

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=4)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, math.ceil(len(self.chars) / MENU_SELECT_LIMIT) - 1)
        new_page = self.page + 1 if self.page < max_page else 0
        await interaction.response.edit_message(
            embed=_character_select_embed(self.game, page=new_page, total_pages=max_page + 1),
            view=CharacterSelectView(self.game, self.chars, self.owner_id, page=new_page),
            attachments=[],
        )

    @discord.ui.button(label="Search", style=discord.ButtonStyle.primary, row=4)
    async def search_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CharacterSearchModal(self.game, self.owner_id))

    @discord.ui.button(label="Back", style=discord.ButtonStyle.grey, row=4)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_label = _game_label(self.game)
        colour = _game_colour(self.game)
        await interaction.response.edit_message(
            embed=_game_menu_embed(game_label, colour),
            view=GameMenuView(self.game, self.owner_id),
            attachments=[],
        )


class CharacterSearchModal(discord.ui.Modal):
    def __init__(self, game, owner_id):
        super().__init__(title="Search Characters")
        self.game = game
        self.owner_id = owner_id
        self.query = discord.ui.TextInput(
            label="Character search",
            placeholder="Example: ryu, sol, happy chaos",
            required=False,
            max_length=80,
        )
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the person who opened this menu can search it.", ephemeral=True)
            return
        chars = _character_list(self.game)
        filtered = _filter_character_choices(chars, str(self.query.value))
        if not filtered:
            await interaction.response.send_message("No characters matched that search.", ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=_character_select_embed(
                self.game,
                page=0,
                total_pages=max(1, math.ceil(len(filtered) / MENU_SELECT_LIMIT)),
                search_query=str(self.query.value).strip(),
            ),
            view=CharacterSelectView(self.game, filtered, self.owner_id, page=0),
            attachments=[],
        )


class CharacterSelect(discord.ui.Select):
    def __init__(self, game, chars, page, owner_id, options):
        self.game = game
        self.chars = chars
        self.page = page
        placeholder = "Select a character"
        super().__init__(placeholder=placeholder, options=options, custom_id=f"char_select:{game}:{page}:{owner_id}")

    async def callback(self, interaction: discord.Interaction):
        char_key = self.values[0]
        moves = _move_list(self.game, char_key)
        if not moves:
            await interaction.response.send_message("No moves found for this character.", ephemeral=True)
            return
        display = char_key.title()
        for opt in self.options:
            if opt.value == char_key:
                display = opt.label
                break
        await interaction.response.edit_message(
            embed=_move_select_embed(display, page=0, total_pages=max(1, math.ceil(len(moves) / MENU_SELECT_LIMIT))),
            view=MoveSelectView(self.game, char_key, moves, self.view.owner_id, page=0),
            attachments=[],
        )


class MoveSelectView(OwnedView):
    def __init__(self, game, char_key, moves, owner_id, page=0):
        super().__init__(owner_id=owner_id, timeout=300)
        self.game = game
        self.char_key = char_key
        self.moves = moves
        self.page = page
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

    def _add_select(self):
        start = self.page * MENU_SELECT_LIMIT
        page_moves = self.moves[start : start + MENU_SELECT_LIMIT]
        options = []
        for i, (row, label) in enumerate(page_moves):
            truncated = label[:100] if len(label) > 100 else label
            options.append(discord.SelectOption(label=truncated, value=f"{self.char_key}|{start + i}"))
        select = MoveSelect(self.game, self.char_key, self.moves, self.page, options)
        self.add_item(select)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, row=4)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, math.ceil(len(self.moves) / MENU_SELECT_LIMIT) - 1)
        new_page = self.page - 1 if self.page > 0 else max_page
        await interaction.response.edit_message(
            embed=_move_select_embed(self.char_key.title(), page=new_page, total_pages=max_page + 1),
            view=MoveSelectView(self.game, self.char_key, self.moves, self.owner_id, page=new_page),
            attachments=[],
        )

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=4)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, math.ceil(len(self.moves) / MENU_SELECT_LIMIT) - 1)
        new_page = self.page + 1 if self.page < max_page else 0
        await interaction.response.edit_message(
            embed=_move_select_embed(self.char_key.title(), page=new_page, total_pages=max_page + 1),
            view=MoveSelectView(self.game, self.char_key, self.moves, self.owner_id, page=new_page),
            attachments=[],
        )

    @discord.ui.button(label="Search", style=discord.ButtonStyle.primary, row=4)
    async def search_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MoveSearchModal(self.game, self.char_key, self.owner_id))

    @discord.ui.button(label="Back", style=discord.ButtonStyle.grey, row=4)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        chars = _character_list(self.game)
        await interaction.response.edit_message(
            embed=_character_select_embed(self.game, page=0, total_pages=max(1, math.ceil(len(chars) / MENU_SELECT_LIMIT))),
            view=CharacterSelectView(self.game, chars, self.owner_id, page=0),
            attachments=[],
        )


class MoveSearchModal(discord.ui.Modal):
    def __init__(self, game, char_key, owner_id):
        super().__init__(title="Search Moves")
        self.game = game
        self.char_key = char_key
        self.owner_id = owner_id
        self.query = discord.ui.TextInput(
            label="Move search",
            placeholder="Example: 5hp, fireball, volcanic viper",
            required=False,
            max_length=80,
        )
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
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
            ),
            view=MoveSelectView(self.game, self.char_key, filtered, self.owner_id, page=0),
            attachments=[],
        )


class MoveSelect(discord.ui.Select):
    def __init__(self, game, char_key, moves, page, options):
        self.game = game
        self.char_key = char_key
        self.moves = moves
        self.page = page
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
        view = FrameResultView(self.game, self.char_key, row, self.view.owner_id)
        files = view.initial_files()
        if self.game == "cotw":
            from bubbot.frame_data.cotw_frame_data import build_image_attachment
            file, attachment_url = await build_image_attachment(row)
            if file and attachment_url:
                view.image_url_override = attachment_url
                view.cotw_image_bytes = file.fp.getvalue()
                view.cotw_image_filename = file.filename
                files = [file]
        await interaction.response.edit_message(embed=view.build_embed(), view=view, attachments=files)


class FrameResultView(OwnedView):
    def __init__(self, game, char_key, row, owner_id):
        super().__init__(owner_id=owner_id, timeout=300)
        self.game = game
        self.char_key = char_key
        self.row = row
        self.show_notes = False
        if game == "sf6":
            from bubbot.frame_data.frame_output import FrameDataGifButton, SF6NotesButton
            from bubbot.frame_data.gif_lookup import get_existing_local_gif_asset_paths, get_frame_row_gif_links
            self.gif_links = list(get_frame_row_gif_links(row) or [])
            asset_paths = get_existing_local_gif_asset_paths(self.gif_links, limit=1) if self.gif_links else []
            self.default_gif_asset_path = asset_paths[0] if asset_paths else None
            self.gif_button = FrameDataGifButton(row, self.gif_links, showing_gif=bool(self.default_gif_asset_path))
            self.notes_button = SF6NotesButton(row)
            self.add_item(self.gif_button)
            self.add_item(self.notes_button)
        elif game == "ggst":
            from bubbot.frame_data.ggst_frame_data import GGSTHitboxButton, GGSTNotesButton
            self.hitbox_button = GGSTHitboxButton(row, showing_hitbox=True)
            self.notes_button = GGSTNotesButton(row)
            self.add_item(self.hitbox_button)
            self.add_item(self.notes_button)
        elif game == "tuco":
            from bubbot.frame_data.tuco_frame_data import TUCOHitboxButton, TUCONotesButton
            self.hitbox_button = TUCOHitboxButton(row, showing_hitbox=True)
            self.notes_button = TUCONotesButton(row)
            self.add_item(self.hitbox_button)
            self.add_item(self.notes_button)
        elif game == "bbcf":
            from bubbot.frame_data.bbcf_frame_data import BBCFHitboxButton, BBCFNotesButton
            self.hitbox_button = BBCFHitboxButton(row, showing_hitbox=True)
            self.notes_button = BBCFNotesButton(row)
            self.add_item(self.hitbox_button)
            self.add_item(self.notes_button)
        elif game == "third_strike":
            from bubbot.frame_data.third_strike_frame_data import ThirdStrikeHitboxButton, ThirdStrikeNotesButton
            self.hitbox_button = ThirdStrikeHitboxButton(row, showing_hitbox=True)
            self.notes_button = ThirdStrikeNotesButton(row)
            self.add_item(self.hitbox_button)
            self.add_item(self.notes_button)
        else:
            from bubbot.frame_data.cotw_frame_data import COTWNotesButton
            self.image_url_override = ""
            self.cotw_image_bytes = None
            self.cotw_image_filename = None
            self.notes_button = COTWNotesButton(row)
            self.add_item(self.notes_button)

    def build_embed(self):
        if self.game == "sf6":
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
        elif self.game == "tuco":
            from bubbot.frame_data.tuco_frame_data import build_frame_embed
        elif self.game == "bbcf":
            from bubbot.frame_data.bbcf_frame_data import build_frame_embed
        elif self.game == "third_strike":
            from bubbot.frame_data.third_strike_frame_data import build_frame_embed
        else:
            from bubbot.frame_data.cotw_frame_data import build_frame_embed
        embed = build_frame_embed(self.row, show_notes=getattr(self, "show_notes", False))
        hitbox_button = getattr(self, "hitbox_button", None)
        if hitbox_button and hitbox_button.showing_hitbox and hitbox_button.hitbox_links:
            embed.set_image(url=hitbox_button.hitbox_links[0])
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

    @discord.ui.button(label="Return to Menu", style=discord.ButtonStyle.primary, custom_id="frame_return_menu")
    async def return_menu_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_main_menu_embed(),
            view=MainMenuView(self.owner_id),
            attachments=[],
        )

    @discord.ui.button(label="Back to Moves", style=discord.ButtonStyle.grey, custom_id="frame_back_moves")
    async def back_moves_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        moves = _move_list(self.game, self.char_key)
        display = _character_display_name(self.game, self.char_key)
        await interaction.response.edit_message(
            embed=_move_select_embed(display, page=0, total_pages=max(1, math.ceil(len(moves) / MENU_SELECT_LIMIT))),
            view=MoveSelectView(self.game, self.char_key, moves, self.owner_id, page=0),
            attachments=[],
        )


class QuizDifficultyView(OwnedView):
    def __init__(self, game, owner_id):
        super().__init__(owner_id=owner_id, timeout=300)
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

    @discord.ui.button(label="Back", style=discord.ButtonStyle.grey, custom_id="quiz_back")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_label = _game_label(self.game)
        colour = _game_colour(self.game)
        await interaction.response.edit_message(
            embed=_game_menu_embed(game_label, colour),
            view=GameMenuView(self.game, self.owner_id),
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
        super().__init__(owner_id=owner_id, timeout=300)
        self.game = game

    @discord.ui.button(label="Back", style=discord.ButtonStyle.grey, custom_id="combos_back")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_label = _game_label(self.game)
        colour = _game_colour(self.game)
        await interaction.response.edit_message(
            embed=_game_menu_embed(game_label, colour),
            view=GameMenuView(self.game, self.owner_id),
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
        description="Select a game to get started.",
        colour=0xFFD700,
    )


def _game_menu_embed(game_label, colour):
    return discord.Embed(
        title=f"{game_label}",
        description="Select a feature.",
        colour=colour,
    )


def _character_select_embed(game, page=None, total_pages=None, search_query=None):
    label = _game_label(game)
    page_text = f"\nPage {page + 1}/{total_pages}" if page is not None and total_pages else ""
    search_text = f"\nSearch: `{search_query}`" if search_query else ""
    return discord.Embed(
        title=f"{label} - Frame Data",
        description=f"Select a character from the dropdown below.{page_text}{search_text}",
        colour=_game_colour(game),
    )


def _move_select_embed(char_display, page=None, total_pages=None, search_query=None):
    page_text = f"\nPage {page + 1}/{total_pages}" if page is not None and total_pages else ""
    search_text = f"\nSearch: `{search_query}`" if search_query else ""
    return discord.Embed(
        title=f"{char_display} - Moves",
        description=f"Select a move from the dropdown below.{page_text}{search_text}",
        colour=0x3998C6,
    )


def _quiz_difficulty_embed(game_label):
    return discord.Embed(
        title=f"{game_label} - Quiz",
        description="Select a difficulty level.",
        colour=0x00FF00,
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
        view=MoveSelectView(game, char_key, moves, owner_id, page=0),
    )
    return True
