import math
import re

import discord

FRAME_DATA = {}
CHARACTER_ALIASES = {}
GGST_FRAME_DATA = {}
GGST_CHARACTER_ALIASES = {}

quiz_module = None
build_sf6_frame_embed = None
build_ggst_frame_embed = None
send_frame_embeds_with_views = None


def configure(
    frame_data=None,
    character_aliases=None,
    ggst_frame_data=None,
    ggst_character_aliases=None,
    quiz_module_ref=None,
    build_sf6_frame_embed_fn=None,
    build_ggst_frame_embed_fn=None,
    send_frame_embeds_with_views_fn=None,
):
    global FRAME_DATA, CHARACTER_ALIASES, GGST_FRAME_DATA, GGST_CHARACTER_ALIASES
    global quiz_module, build_sf6_frame_embed, build_ggst_frame_embed, send_frame_embeds_with_views
    FRAME_DATA = frame_data or {}
    CHARACTER_ALIASES = character_aliases or {}
    GGST_FRAME_DATA = ggst_frame_data or {}
    GGST_CHARACTER_ALIASES = ggst_character_aliases or {}
    quiz_module = quiz_module_ref
    build_sf6_frame_embed = build_sf6_frame_embed_fn
    build_ggst_frame_embed = build_ggst_frame_embed_fn
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
    seen = set()
    chars = []
    for char_key in sorted(FRAME_DATA.keys()):
        display = char_key.title()
        if display.lower() not in seen:
            seen.add(display.lower())
            chars.append((char_key, display))
    return chars


def _ggst_character_list():
    seen = set()
    chars = []
    for char_key in sorted(GGST_FRAME_DATA.keys()):
        rows = GGST_FRAME_DATA.get(char_key, [])
        display = str(rows[0].get("char_name", char_key)).strip() if rows else char_key.title()
        if display.lower() not in seen:
            seen.add(display.lower())
            chars.append((char_key, display))
    return chars


def _sf6_move_list(char_key):
    seen = set()
    moves = []
    for row in FRAME_DATA.get(char_key, []):
        move_name = str(row.get("moveName", "")).strip()
        num_cmd = str(row.get("numCmd", "")).strip()
        if not move_name and not num_cmd:
            continue
        label = f"{move_name} ({num_cmd})" if num_cmd else move_name
        key = (move_name, num_cmd)
        if key not in seen:
            seen.add(key)
            moves.append((row, label))
    return moves


def _ggst_move_list(char_key):
    seen = set()
    moves = []
    for row in GGST_FRAME_DATA.get(char_key, []):
        move_name = str(row.get("moveName", "")).strip()
        num_cmd = str(row.get("numCmd", "")).strip()
        state_label = str(row.get("state_label", "")).strip()
        if not move_name and not num_cmd:
            continue
        if state_label:
            label = f"{move_name} ({num_cmd}) [{state_label}]"
        elif num_cmd:
            label = f"{move_name} ({num_cmd})"
        else:
            label = move_name
        key = (move_name, num_cmd, state_label)
        if key not in seen:
            seen.add(key)
            moves.append((row, label))
    return moves


class MainMenuView(OwnedView):
    def __init__(self, owner_id):
        super().__init__(owner_id=owner_id, timeout=300)

    @discord.ui.button(label="Street Fighter 6", style=discord.ButtonStyle.primary, custom_id="menu_sf6")
    async def sf6_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_game_menu_embed("Street Fighter 6", 0x3998C6),
            view=GameMenuView("sf6", self.owner_id),
        )

    @discord.ui.button(label="Guilty Gear Strive", style=discord.ButtonStyle.danger, custom_id="menu_ggst")
    async def ggst_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_game_menu_embed("Guilty Gear Strive", 0x7A2BFF),
            view=GameMenuView("ggst", self.owner_id),
        )


class GameMenuView(OwnedView):
    def __init__(self, game, owner_id):
        super().__init__(owner_id=owner_id, timeout=300)
        self.game = game
        if self.game == "ggst":
            self.remove_item(self.quiz_button)

    @discord.ui.button(label="Frame Data", style=discord.ButtonStyle.primary, custom_id="game_framedata")
    async def framedata_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        chars = _sf6_character_list() if self.game == "sf6" else _ggst_character_list()
        if not chars:
            await interaction.response.send_message("No character data loaded.", ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=_character_select_embed(self.game, page=0, total_pages=max(1, math.ceil(len(chars) / MENU_SELECT_LIMIT))),
            view=CharacterSelectView(self.game, chars, self.owner_id, page=0),
        )

    @discord.ui.button(label="Quiz", style=discord.ButtonStyle.success, custom_id="game_quiz")
    async def quiz_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_label = "Street Fighter 6" if self.game == "sf6" else "Guilty Gear Strive"
        await interaction.response.edit_message(
            embed=_quiz_difficulty_embed(game_label),
            view=QuizDifficultyView(self.game, self.owner_id),
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
        )

    @discord.ui.button(label="Back", style=discord.ButtonStyle.grey, custom_id="game_back")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_main_menu_embed(),
            view=MainMenuView(self.owner_id),
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
        )

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=4)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, math.ceil(len(self.chars) / MENU_SELECT_LIMIT) - 1)
        new_page = self.page + 1 if self.page < max_page else 0
        await interaction.response.edit_message(
            embed=_character_select_embed(self.game, page=new_page, total_pages=max_page + 1),
            view=CharacterSelectView(self.game, self.chars, self.owner_id, page=new_page),
        )

    @discord.ui.button(label="Back", style=discord.ButtonStyle.grey, row=4)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_label = "Street Fighter 6" if self.game == "sf6" else "Guilty Gear Strive"
        colour = 0x3998C6 if self.game == "sf6" else 0x7A2BFF
        await interaction.response.edit_message(
            embed=_game_menu_embed(game_label, colour),
            view=GameMenuView(self.game, self.owner_id),
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
        moves = _sf6_move_list(char_key) if self.game == "sf6" else _ggst_move_list(char_key)
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
        )

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=4)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, math.ceil(len(self.moves) / MENU_SELECT_LIMIT) - 1)
        new_page = self.page + 1 if self.page < max_page else 0
        await interaction.response.edit_message(
            embed=_move_select_embed(self.char_key.title(), page=new_page, total_pages=max_page + 1),
            view=MoveSelectView(self.game, self.char_key, self.moves, self.owner_id, page=new_page),
        )

    @discord.ui.button(label="Back", style=discord.ButtonStyle.grey, row=4)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        chars = _sf6_character_list() if self.game == "sf6" else _ggst_character_list()
        await interaction.response.edit_message(
            embed=_character_select_embed(self.game, page=0, total_pages=max(1, math.ceil(len(chars) / MENU_SELECT_LIMIT))),
            view=CharacterSelectView(self.game, chars, self.owner_id, page=0),
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
        embed = build_sf6_frame_embed(row) if self.game == "sf6" else build_ggst_frame_embed(row)
        view = FrameResultView(self.game, self.char_key, row, self.view.owner_id)
        await interaction.response.edit_message(embed=embed, view=view)


class FrameResultView(OwnedView):
    def __init__(self, game, char_key, row, owner_id):
        super().__init__(owner_id=owner_id, timeout=300)
        self.game = game
        self.char_key = char_key
        if game == "sf6":
            from frame_output import FrameDataGifButton
            from gif_lookup import get_frame_row_gif_links
            self.add_item(FrameDataGifButton(row, get_frame_row_gif_links(row)))
        else:
            from ggst_frame_data import GGSTHitboxButton
            self.add_item(GGSTHitboxButton(row))

    @discord.ui.button(label="Return to Menu", style=discord.ButtonStyle.primary, custom_id="frame_return_menu")
    async def return_menu_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_main_menu_embed(),
            view=MainMenuView(self.owner_id),
        )

    @discord.ui.button(label="Back to Moves", style=discord.ButtonStyle.grey, custom_id="frame_back_moves")
    async def back_moves_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        moves = _sf6_move_list(self.char_key) if self.game == "sf6" else _ggst_move_list(self.char_key)
        display = self.char_key.title()
        await interaction.response.edit_message(
            embed=_move_select_embed(display, page=0, total_pages=max(1, math.ceil(len(moves) / MENU_SELECT_LIMIT))),
            view=MoveSelectView(self.game, self.char_key, moves, self.owner_id, page=0),
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
        game_label = "Street Fighter 6" if self.game == "sf6" else "Guilty Gear Strive"
        colour = 0x3998C6 if self.game == "sf6" else 0x7A2BFF
        await interaction.response.edit_message(
            embed=_game_menu_embed(game_label, colour),
            view=GameMenuView(self.game, self.owner_id),
        )

    async def _start_quiz(self, interaction, difficulty):
        if quiz_module is None:
            await interaction.response.send_message("Quiz system is not available.", ephemeral=True)
            return
        game_label = "Street Fighter 6" if self.game == "sf6" else "Guilty Gear Strive"
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Quiz Started",
                description=f"Starting **{difficulty}** quiz for **{game_label}**.\nGood luck!",
                colour=0x00FF00,
            ),
            view=None,
        )
        fake_message = QuizFakeMessage(interaction)
        await quiz_module.start_quiz(fake_message, mode=difficulty)


class BackToGameMenuView(OwnedView):
    def __init__(self, game, owner_id):
        super().__init__(owner_id=owner_id, timeout=300)
        self.game = game

    @discord.ui.button(label="Back", style=discord.ButtonStyle.grey, custom_id="combos_back")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_label = "Street Fighter 6" if self.game == "sf6" else "Guilty Gear Strive"
        colour = 0x3998C6 if self.game == "sf6" else 0x7A2BFF
        await interaction.response.edit_message(
            embed=_game_menu_embed(game_label, colour),
            view=GameMenuView(self.game, self.owner_id),
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


def _character_select_embed(game, page=None, total_pages=None):
    label = "Street Fighter 6" if game == "sf6" else "Guilty Gear Strive"
    page_text = f"\nPage {page + 1}/{total_pages}" if page is not None and total_pages else ""
    return discord.Embed(
        title=f"{label} - Frame Data",
        description=f"Select a character from the dropdown below.{page_text}",
        colour=0x3998C6 if game == "sf6" else 0x7A2BFF,
    )


def _move_select_embed(char_display, page=None, total_pages=None):
    page_text = f"\nPage {page + 1}/{total_pages}" if page is not None and total_pages else ""
    return discord.Embed(
        title=f"{char_display} - Moves",
        description=f"Select a move from the dropdown below.{page_text}",
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
