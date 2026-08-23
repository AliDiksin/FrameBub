"""Main, character, and move menu navigation controls."""

import discord

from bubbot.features import menu_catalog as _catalog

globals().update({name: value for name, value in vars(_catalog).items() if not name.startswith("__")})


def configure(**deps):
    globals().update(deps)
class MainGameSelect(discord.ui.Select):
    def __init__(self, owner_id):
        options = [
            discord.SelectOption(label=label, value=game_key)
            for game_key, label, _colour in MENU_GAMES
        ]
        super().__init__(
            placeholder="Choose a game...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="menu_game_select",
        )
        self.owner_id = owner_id

    async def callback(self, interaction: discord.Interaction):
        game = self.values[0]
        label = _game_label(game)
        colour = _game_colour(game)
        view = SF6GameMenuView(self.owner_id) if game == "sf6" else GameMenuView(game, self.owner_id)
        await interaction.response.edit_message(
            embed=_game_menu_embed(label, colour),
            view=view,
            attachments=[],
        )


class MainMenuView(OwnedView):
    def __init__(self, owner_id):
        super().__init__(owner_id=owner_id, menu_locked=True, timeout=None)
        self.add_item(MainGameSelect(owner_id))

    @discord.ui.button(label="Readme", style=discord.ButtonStyle.success, custom_id="menu_readme", row=1)
    async def readme_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=build_readme_embed(),
            view=ReadmeView(self.owner_id),
            attachments=[],
        )

    @discord.ui.button(label="Glossary", style=discord.ButtonStyle.primary, custom_id="menu_glossary", row=1)
    async def glossary_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=build_glossary_embed(),
            view=GlossaryMenuView(self.owner_id),
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


class GlossaryMenuView(OwnedView):
    def __init__(self, owner_id, term=None):
        super().__init__(owner_id=owner_id, menu_locked=True, timeout=None)
        self.term = normalize_glossary_term(term)
        self.add_item(build_glossary_link_button(self.term))

    @discord.ui.button(label="Search Term", style=discord.ButtonStyle.primary, custom_id="glossary_search", row=1)
    async def search_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GlossarySearchModal(self.owner_id))

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, custom_id="glossary_back", row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_main_menu_embed(),
            view=MainMenuView(self.owner_id),
            attachments=[],
        )


class GlossarySearchModal(discord.ui.Modal):
    def __init__(self, owner_id):
        super().__init__(title="Search Glossary")
        self.owner_id = owner_id
        self.query = discord.ui.TextInput(
            label="Glossary term",
            placeholder="Example: safe jump, option select, meaty",
            required=False,
            max_length=100,
        )
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the person who opened this menu can search it.", ephemeral=True)
            return
        term = normalize_glossary_term(self.query.value)
        await interaction.response.edit_message(
            embed=build_glossary_definition_embed(term),
            view=GlossaryMenuView(self.owner_id, term),
            attachments=[],
        )


class GameMenuView(OwnedView):
    def __init__(self, game, owner_id):
        super().__init__(owner_id=owner_id, menu_locked=True, timeout=None)
        self.game = game

    @discord.ui.button(label="Frame Data", style=discord.ButtonStyle.primary, custom_id="game_framedata", row=0)
    async def framedata_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_framedata_character_select(interaction, self.game, self.owner_id)

    @discord.ui.button(label="Combos", style=discord.ButtonStyle.primary, custom_id="game_combos", row=0)
    async def combos_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_game_combos_menu(interaction, self.game, self.owner_id)

    @discord.ui.button(label="Quiz", style=discord.ButtonStyle.success, custom_id="game_quiz", row=0)
    async def quiz_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_quiz_difficulty(interaction, self.game, self.owner_id)

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

    @discord.ui.button(label="Combos", style=discord.ButtonStyle.primary, custom_id="sf6_game_combos", row=0)
    async def combos_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_game_combos_menu(interaction, self.game, self.owner_id)

    @discord.ui.button(label="Quiz", style=discord.ButtonStyle.success, custom_id="sf6_game_quiz", row=0)
    async def quiz_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_quiz_difficulty(interaction, self.game, self.owner_id)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, custom_id="sf6_game_back", row=0)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_main_menu_embed(),
            view=MainMenuView(self.owner_id),
            attachments=[],
        )


# Character and move select views (paginated Discord selects)
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
