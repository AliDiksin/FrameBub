"""Frame result, stats, and compare controls for the menu system."""

import discord

from bubbot.features import menu_catalog as _catalog
from bubbot.frame_data.frame_media_controls import ShowAllImagesButton, preferred_frame_image_url

globals().update({name: value for name, value in vars(_catalog).items() if not name.startswith("__")})


def configure(**deps):
    globals().update(deps)
# Frame result helpers and compare buttons
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


def build_frame_result_view(
    game,
    row,
    owner_id=None,
    char_key=None,
    *,
    menu_locked=False,
    show_back_to_moves=None,
    source_message=None,
    prompt="",
):
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
        source_message=source_message,
        prompt=prompt,
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


async def send_frame_result_messages(
    channel,
    game,
    rows,
    *,
    owner_id=None,
    menu_locked=False,
    source_message=None,
    prompt="",
    client=None,
):
    from bubbot.features.failed_prompt_report import stamp_report_context_on_sent

    sent_ids = []
    for row in rows or []:
        view = build_frame_result_view(
            game,
            row,
            owner_id=owner_id,
            menu_locked=menu_locked,
            source_message=source_message,
            prompt=prompt,
        )
        await prepare_cotw_frame_view(view)
        sent = await channel.send(embed=view.build_embed(), view=view, files=view.initial_files())
        stamp_report_context_on_sent(view, sent, client=client)
        sent_ids.append(sent.id)
    return sent_ids


def attach_compare_button(view, game, row, owner_id=None, char_key=None):
    resolved_char_key = _row_character_key(game, row, char_key)
    if not resolved_char_key or not _move_list(game, resolved_char_key):
        return
    view.add_item(CompareFrameButton(game, row, owner_id, char_key=resolved_char_key))
# SF6 stats compare flow
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
    def __init__(
        self,
        char_key,
        owner_id,
        stat_keys=None,
        compare_char_key=None,
        *,
        menu_locked=False,
        source_message=None,
        prompt="",
    ):
        super().__init__(owner_id=owner_id, menu_locked=menu_locked, timeout=None)
        self.char_key = char_key
        self.stat_keys = tuple(stat_keys) if stat_keys else None
        self.compare_char_key = compare_char_key
        self.add_item(StatsCompareButton(char_key, owner_id, stat_keys=self.stat_keys))
        self.add_item(StatsShowFramedataButton(char_key, owner_id))
        self.add_item(FrameReturnMenuButton())
        if menu_locked:
            self.add_item(StatsBackToCharactersButton(char_key, owner_id))
        from bubbot.features.failed_prompt_report import attach_frame_report_button

        attach_frame_report_button(
            self,
            game="sf6",
            row={"char_key": char_key, "char_name": char_key, "moveName": "Character Stats"},
            source_message=source_message,
            prompt=prompt,
            failure_reason="stats_response",
        )


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



# FrameResultView: per-game notes, hitbox, gif buttons
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
        source_message=None,
        prompt="",
    ):
        super().__init__(owner_id=owner_id, menu_locked=menu_locked, timeout=None)
        self.game = game
        self.char_key = char_key
        self.row = row
        self.source_message = source_message
        self.prompt = prompt
        self.show_notes = False
        self.show_stats = False
        if game == "sf6":
            from bubbot.frame_data.frame_output import SF6NotesButton, SF6ShowStatsButton
            from bubbot.frame_data.gif_lookup import get_existing_local_gif_asset_paths, get_frame_row_gif_links
            self.gif_links = list(get_frame_row_gif_links(row) or [])
            asset_paths = get_existing_local_gif_asset_paths(self.gif_links, limit=1) if self.gif_links else []
            self.default_gif_asset_path = asset_paths[0] if asset_paths else None
            self.character_stats = FRAME_STATS.get(char_key) or {}
            self.stats_button = SF6ShowStatsButton(disabled=not self.character_stats)
            self.notes_button = SF6NotesButton(row)
            self.add_item(self.stats_button)
            self.add_item(self.notes_button)
        elif game == "ggst":
            from bubbot.frame_data.ggst_frame_data import GGSTNotesButton, get_media_links
            self.all_hitbox_images_button = ShowAllImagesButton(get_media_links(row, limit=None))
            if len(self.all_hitbox_images_button.media_links) > 1:
                self.add_item(self.all_hitbox_images_button)
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
            from bubbot.frame_data.bbcf_frame_data import BBCFNotesButton, get_media_links
            self.all_hitbox_images_button = ShowAllImagesButton(get_media_links(row, limit=None))
            if len(self.all_hitbox_images_button.media_links) > 1:
                self.add_item(self.all_hitbox_images_button)
            self.notes_button = BBCFNotesButton(row)
            self.add_item(self.notes_button)
        elif game == "ggacr":
            from bubbot.frame_data.ggacr_frame_data import GGACRNotesButton, get_media_links
            self.all_hitbox_images_button = ShowAllImagesButton(get_media_links(row, limit=None))
            if len(self.all_hitbox_images_button.media_links) > 1:
                self.add_item(self.all_hitbox_images_button)
            self.notes_button = GGACRNotesButton(row)
            self.add_item(self.notes_button)
        elif game == "third_strike":
            from bubbot.frame_data.third_strike_frame_data import ThirdStrikeNotesButton, get_media_links
            self.all_hitbox_images_button = ShowAllImagesButton(get_media_links(row, limit=None))
            if len(self.all_hitbox_images_button.media_links) > 1:
                self.add_item(self.all_hitbox_images_button)
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
        from bubbot.features.failed_prompt_report import attach_frame_report_button

        attach_frame_report_button(
            self,
            game=game,
            row=row,
            source_message=source_message,
            prompt=prompt,
        )

    def build_embed(self):
        from bubbot.utils.embed_source_utils import apply_game_source_footer
        if self.game == "sf6":
            if getattr(self, "show_stats", False) and getattr(self, "character_stats", None):
                from bubbot.frame_data.sf6_character_stats import build_character_stats_embed

                return apply_game_source_footer(
                    build_character_stats_embed(self.char_key, self.character_stats),
                    self.game,
                )
            if getattr(self, "default_gif_asset_path", None):
                filename = os.path.basename(self.default_gif_asset_path)
                return apply_game_source_footer(
                    build_sf6_frame_embed(
                        self.row,
                        image_url_override=f"attachment://{filename}",
                        show_notes=getattr(self, "show_notes", False),
                    ),
                    self.game,
                )
            return apply_game_source_footer(
                build_sf6_frame_embed(self.row, show_notes=getattr(self, "show_notes", False)),
                self.game,
            )
        if self.game == "ggst":
            from bubbot.frame_data.ggst_frame_data import build_frame_embed
        elif self.game == "sfv":
            from bubbot.frame_data.sfv_frame_data import build_frame_embed
        elif self.game == "tuco":
            from bubbot.frame_data.tuco_frame_data import build_frame_embed
        elif self.game == "bbcf":
            from bubbot.frame_data.bbcf_frame_data import build_frame_embed
        elif self.game == "ggacr":
            from bubbot.frame_data.ggacr_frame_data import build_frame_embed
        elif self.game == "third_strike":
            from bubbot.frame_data.third_strike_frame_data import build_frame_embed
        elif self.game == "mk1":
            from bubbot.frame_data.mk1_frame_data import build_frame_embed
        else:
            from bubbot.frame_data.cotw_frame_data import build_frame_embed
        embed = build_frame_embed(self.row, show_notes=getattr(self, "show_notes", False))
        preferred_image_url = preferred_frame_image_url(self.game, self.row)
        if preferred_image_url:
            embed.set_image(url=preferred_image_url)
        if self.game == "cotw" and getattr(self, "image_url_override", ""):
            embed.set_image(url=self.image_url_override)
        return apply_game_source_footer(embed, self.game)

    def initial_files(self):
        return self.active_files()

    def active_files(self):
        from bubbot.utils.embed_source_utils import source_icon_files

        files = source_icon_files(self.game, kind="frame")
        if self.game == "cotw" and getattr(self, "cotw_image_bytes", None) and getattr(self, "cotw_image_filename", None):
            files.append(discord.File(io.BytesIO(self.cotw_image_bytes), filename=self.cotw_image_filename))
            return files
        if self.game == "sf6" and getattr(self, "default_gif_asset_path", None):
            filename = os.path.basename(self.default_gif_asset_path)
            files.append(discord.File(self.default_gif_asset_path, filename=filename))
        return files

