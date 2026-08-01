"""Quiz launch and combo menu navigation controls."""

import discord

from bubbot.features import menu_catalog as _catalog

globals().update({name: value for name, value in vars(_catalog).items() if not name.startswith("__")})


def configure(**deps):
    globals().update(deps)
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


# Combo section and subsection navigation
class ComboCharacterSelectView(OwnedView):
    def __init__(self, game, chars, owner_id, page=0):
        super().__init__(owner_id=owner_id, menu_locked=True, timeout=None)
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
        options = [
            discord.SelectOption(label=display[:100], value=char_key)
            for char_key, display in self.chars[start : start + MENU_SELECT_LIMIT]
        ]
        self.add_item(ComboCharacterSelect(self.game, self.chars, self.page, options))

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, row=4)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, math.ceil(len(self.chars) / MENU_SELECT_LIMIT) - 1)
        new_page = self.page - 1 if self.page > 0 else max_page
        await interaction.response.edit_message(
            embed=_combo_character_select_embed(self.game, page=new_page, total_pages=max_page + 1),
            view=ComboCharacterSelectView(self.game, self.chars, self.owner_id, page=new_page),
            attachments=[],
        )

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, row=4)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, math.ceil(len(self.chars) / MENU_SELECT_LIMIT) - 1)
        new_page = self.page + 1 if self.page < max_page else 0
        await interaction.response.edit_message(
            embed=_combo_character_select_embed(self.game, page=new_page, total_pages=max_page + 1),
            view=ComboCharacterSelectView(self.game, self.chars, self.owner_id, page=new_page),
            attachments=[],
        )

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, row=4)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_game_menu_embed(_game_label(self.game), _game_colour(self.game)),
            view=_game_menu_view(self.game, self.owner_id),
            attachments=[],
        )


class ComboCharacterSelect(discord.ui.Select):
    def __init__(self, game, chars, page, options):
        self.game = game
        self.chars = chars
        self.page = page
        super().__init__(placeholder="Select a character", options=options, custom_id=f"combo_char_select:{game}:{page}")

    async def callback(self, interaction: discord.Interaction):
        from bubbot.frame_data import combo_data

        char_key = self.values[0]
        sections = combo_data.combo_sections(self.game, char_key)
        if not sections:
            await interaction.response.send_message("No combos found for that character.", ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=_combo_section_select_embed(self.game, char_key, page=0, total_pages=ComboSectionView.page_count(sections)),
            view=ComboSectionView(self.game, char_key, sections, self.view.owner_id, page=0),
            attachments=[],
        )


class ComboSectionView(OwnedView):
    """Buttons (one per SuperCombo page heading) that open that heading's combo list."""

    SECTIONS_PER_PAGE = 20

    def __init__(self, game, char_key, sections, owner_id, page=0, back_to="character_select"):
        super().__init__(owner_id=owner_id, menu_locked=True, timeout=None)
        self.game = game
        self.char_key = char_key
        self.sections = list(sections or [])
        self.page = page
        self.back_to = back_to
        self._build()

    @classmethod
    def page_count(cls, sections):
        return max(1, math.ceil(len(sections) / cls.SECTIONS_PER_PAGE))

    def _build(self):
        page_count = self.page_count(self.sections)
        start = self.page * self.SECTIONS_PER_PAGE
        page_sections = self.sections[start : start + self.SECTIONS_PER_PAGE]
        for offset, (section_label, count) in enumerate(page_sections):
            label = f"{section_label} ({count})"
            self.add_item(
                ComboSectionButton(
                    section_label,
                    label[:80],
                    row=offset // 5,
                )
            )
        if page_count > 1:
            self.add_item(ComboSectionPageButton(self.game, self.char_key, self.sections, "prev", self.page))
            self.add_item(ComboSectionPageButton(self.game, self.char_key, self.sections, "next", self.page))
        self.add_item(ComboSectionBackButton())


class ComboSectionButton(discord.ui.Button):
    def __init__(self, section_label, label, row):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=row)
        self.section_label = section_label

    async def callback(self, interaction: discord.Interaction):
        from bubbot.frame_data import combo_data

        view = self.view
        if combo_data.section_needs_subsection_menu(view.game, view.char_key, self.section_label):
            subsections = combo_data.combo_subsections(view.game, view.char_key, self.section_label)
            await interaction.response.edit_message(
                embed=_combo_subsection_select_embed(view.game, view.char_key, self.section_label),
                view=ComboSubsectionView(
                    view.game,
                    view.char_key,
                    self.section_label,
                    subsections,
                    view.owner_id,
                    page=0,
                    back_to=view.back_to,
                ),
                attachments=[],
            )
            return
        rows = combo_data.rows_for_section(view.game, view.char_key, self.section_label)
        pages = combo_data.build_combo_pages(view.game, view.char_key, rows, section=self.section_label)
        list_view = combo_data.ComboListView(
            view.game,
            view.char_key,
            pages,
            view.owner_id,
            menu_locked=True,
            section=self.section_label,
            back_to=view.back_to,
        )
        await interaction.response.edit_message(embed=pages[0], view=list_view, attachments=[])


class ComboSectionPageButton(discord.ui.Button):
    def __init__(self, game, char_key, sections, direction, page):
        page_count = ComboSectionView.page_count(sections)
        if direction == "prev":
            target = page - 1 if page > 0 else page_count - 1
            label = f"Previous ({target + 1}/{page_count})"
        else:
            target = page + 1 if page < page_count - 1 else 0
            label = f"Next ({target + 1}/{page_count})"
        super().__init__(label=label, style=discord.ButtonStyle.primary, row=4)
        self.game = game
        self.char_key = char_key
        self.sections = sections
        self.target = target

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=_combo_section_select_embed(
                self.game,
                self.char_key,
                page=self.target,
                total_pages=ComboSectionView.page_count(self.sections),
            ),
            view=ComboSectionView(
                self.game,
                self.char_key,
                self.sections,
                self.view.owner_id,
                page=self.target,
                back_to=self.view.back_to,
            ),
            attachments=[],
        )


class ComboSectionBackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Back", style=discord.ButtonStyle.danger, row=4)

    async def callback(self, interaction: discord.Interaction):
        from bubbot.frame_data import combo_data

        view = self.view
        if view.back_to == "game_menu":
            await _edit_to_game_menu(interaction, view.game, view.owner_id)
            return
        chars = combo_data.combo_character_list(view.game)
        await interaction.response.edit_message(
            embed=_combo_character_select_embed(
                view.game,
                page=0,
                total_pages=max(1, math.ceil(len(chars) / MENU_SELECT_LIMIT)),
            ),
            view=ComboCharacterSelectView(view.game, chars, view.owner_id, page=0),
            attachments=[],
        )


class ComboSubsectionView(OwnedView):
    """Sub-heading buttons when a section has more than 10 combos."""

    SUBSECTIONS_PER_PAGE = 20

    def __init__(self, game, char_key, section_label, subsections, owner_id, page=0, back_to="character_select"):
        super().__init__(owner_id=owner_id, menu_locked=True, timeout=None)
        self.game = game
        self.char_key = char_key
        self.section_label = section_label
        self.subsections = list(subsections or [])
        self.page = page
        self.back_to = back_to
        self._build()

    @classmethod
    def page_count(cls, subsections):
        return max(1, math.ceil(len(subsections) / cls.SUBSECTIONS_PER_PAGE))

    def _build(self):
        page_count = self.page_count(self.subsections)
        start = self.page * self.SUBSECTIONS_PER_PAGE
        page_subsections = self.subsections[start : start + self.SUBSECTIONS_PER_PAGE]
        for offset, (subsection_label, count) in enumerate(page_subsections):
            label = f"{subsection_label} ({count})"
            self.add_item(
                ComboSubsectionButton(
                    self.section_label,
                    subsection_label,
                    label[:80],
                    row=offset // 5,
                )
            )
        if page_count > 1:
            self.add_item(
                ComboSubsectionPageButton(
                    self.game,
                    self.char_key,
                    self.section_label,
                    self.subsections,
                    "prev",
                    self.page,
                )
            )
            self.add_item(
                ComboSubsectionPageButton(
                    self.game,
                    self.char_key,
                    self.section_label,
                    self.subsections,
                    "next",
                    self.page,
                )
            )
        self.add_item(ComboSubsectionBackButton())


class ComboSubsectionButton(discord.ui.Button):
    def __init__(self, section_label, subsection_label, label, row):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=row)
        self.section_label = section_label
        self.subsection_label = subsection_label

    async def callback(self, interaction: discord.Interaction):
        from bubbot.frame_data import combo_data

        view = self.view
        rows = combo_data.rows_for_subsection(view.game, view.char_key, self.section_label, self.subsection_label)
        pages = combo_data.build_combo_pages(
            view.game,
            view.char_key,
            rows,
            section=self.section_label,
            subsection=self.subsection_label,
        )
        list_view = combo_data.ComboListView(
            view.game,
            view.char_key,
            pages,
            view.owner_id,
            menu_locked=True,
            section=self.section_label,
            subsection=self.subsection_label,
            back_to=view.back_to,
        )
        await interaction.response.edit_message(embed=pages[0], view=list_view, attachments=[])


class ComboSubsectionPageButton(discord.ui.Button):
    def __init__(self, game, char_key, section_label, subsections, direction, page):
        page_count = ComboSubsectionView.page_count(subsections)
        if direction == "prev":
            target = page - 1 if page > 0 else page_count - 1
            label = f"Previous ({target + 1}/{page_count})"
        else:
            target = page + 1 if page < page_count - 1 else 0
            label = f"Next ({target + 1}/{page_count})"
        super().__init__(label=label, style=discord.ButtonStyle.primary, row=4)
        self.game = game
        self.char_key = char_key
        self.section_label = section_label
        self.subsections = subsections
        self.target = target

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=_combo_subsection_select_embed(self.game, self.char_key, self.section_label),
            view=ComboSubsectionView(
                self.game,
                self.char_key,
                self.section_label,
                self.subsections,
                self.view.owner_id,
                page=self.target,
                back_to=self.view.back_to,
            ),
            attachments=[],
        )


class ComboSubsectionBackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Back", style=discord.ButtonStyle.danger, row=4)

    async def callback(self, interaction: discord.Interaction):
        from bubbot.frame_data import combo_data

        view = self.view
        sections = combo_data.combo_sections(view.game, view.char_key)
        await interaction.response.edit_message(
            embed=_combo_section_select_embed(view.game, view.char_key, page=0, total_pages=ComboSectionView.page_count(sections)),
            view=ComboSectionView(view.game, view.char_key, sections, view.owner_id, page=0, back_to=view.back_to),
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
