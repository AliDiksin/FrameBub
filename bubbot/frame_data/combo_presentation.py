"""Discord combo embeds, pagination views, and response senders."""
# Combo rendering preserves source headings while pagination enforces Discord embed limits.

import discord

from bubbot.utils.discord_formatting import add_embed_field, clean_value, truncate_value

DISCORD_EMBED_CHAR_BUDGET = 5800
DISCORD_EMBED_MAX_FIELDS = 25
GROUP_SEPARATOR = " — "
SUBHEADER_DIVIDER = "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"


def configure(**deps):
    globals().update(deps)
def _row_subheader(row, section):
    """The label shown as a sub-heading above a combo in the list."""
    parsed_section, subsection = _split_group(row.get("group"))
    position = str(row.get("position") or "").strip()
    if section is not None:
        if subsection:
            sub_parts = [part.strip() for part in subsection.split(GROUP_SEPARATOR) if part.strip()]
            if position and (not sub_parts or sub_parts[-1].lower() != position.lower()):
                return position
            if len(sub_parts) > 1:
                return ""
            return subsection
        return position or "General"
    full = str(row.get("group") or "").strip()
    return full or parsed_section or "General"


def _combo_field_name(row, index):
    position = clean_value(row.get("position"))
    difficulty = clean_value(row.get("difficulty"))
    meta = " · ".join(part for part in (position, difficulty) if part)
    label = f"{index}. {meta}" if meta else f"{index}. Combo"
    return truncate_value(label, 256)


def _combo_field_value(game, row):
    lines = []
    title = clean_value(row.get("title"))
    if title:
        lines.append(f"**{title}**")
    recipe = clean_value(row.get("recipe"))
    if recipe:
        lines.append(f"`{recipe}`")
    detail_parts = []
    damage = clean_value(row.get("damage"))
    if damage:
        detail_parts.append(f"Damage: **{damage}**")
    drive = clean_value(row.get("drive"))
    if drive:
        detail_parts.append(f"Drive: **{drive}**")
    meter = clean_value(row.get("meter"))
    if meter:
        meter_label = "Super" if game == "sf6" else "Meter"
        detail_parts.append(f"{meter_label}: **{meter}**")
    kameo = clean_value(row.get("kameo"))
    if kameo:
        detail_parts.append(f"Kameo: **{kameo}**")
    kameo_meter = clean_value(row.get("kameo_meter"))
    if kameo_meter:
        detail_parts.append(f"Kameo meter: **{kameo_meter}**")
    tags = clean_value(row.get("tags"))
    if tags:
        detail_parts.append(f"Tags: {tags}")
    if detail_parts:
        lines.append(" | ".join(detail_parts))
    notes = clean_value(row.get("notes"))
    if notes:
        lines.append(notes)
    video = clean_value(row.get("video"))
    if video and video != notes:
        lines.append(video)
    return truncate_value("\n".join(line for line in lines if line), 1024)


def _embed_size(embed):
    total = len(str(embed.title or "")) + len(str(embed.description or ""))
    for field in embed.fields:
        total += len(str(field.name or "")) + len(str(field.value or ""))
    return total


def _clone_embed(embed):
    clone = discord.Embed(title=embed.title, description=embed.description, colour=embed.colour)
    for field in embed.fields:
        clone.add_field(name=field.name, value=field.value, inline=field.inline)
    return clone


def build_combo_pages(game, char_key, rows, *, section=None, subsection=None, group=None):
    rows = list(rows or [])
    char_display = display_char_name(game, char_key)
    if subsection and section is not None:
        heading_label = f"{section}{GROUP_SEPARATOR}{subsection}"
    else:
        heading_label = section if section is not None else group
    description = char_display if not heading_label else f"{char_display} — {heading_label}"
    base_title = f"{game_label(game)} Combos"

    if not rows:
        return [
            discord.Embed(
                title=truncate_value(base_title, 256),
                description=truncate_value(description or "No combos found for that filter.", 4096),
                colour=game_colour(game),
            )
        ]

    def make_embed(continued=False):
        return discord.Embed(
            title=truncate_value(base_title + (" (cont.)" if continued else ""), 256),
            description=truncate_value(description, 4096),
            colour=game_colour(game),
        )

    pages = []
    current = make_embed()
    current_subheader = None
    index = 0
    for row in rows:
        index += 1
        subheader = _row_subheader(row, section)
        field_name = _combo_field_name(row, index)
        field_value = _combo_field_value(game, row)
        need_header = bool(subheader) and subheader != current_subheader

        candidate = _clone_embed(current)
        if need_header:
            add_embed_field(candidate, truncate_value(subheader, 256), SUBHEADER_DIVIDER, inline=False)
        add_embed_field(candidate, field_name, field_value, inline=False)

        if len(candidate.fields) > DISCORD_EMBED_MAX_FIELDS or _embed_size(candidate) > DISCORD_EMBED_CHAR_BUDGET:
            if current.fields:
                pages.append(current)
            current = make_embed(continued=True)
            if subheader:
                add_embed_field(current, truncate_value(subheader, 256), SUBHEADER_DIVIDER, inline=False)
                current_subheader = subheader
            add_embed_field(current, field_name, field_value, inline=False)
        else:
            if need_header:
                current_subheader = subheader
            current = candidate

    if current.fields or not pages:
        pages.append(current)

    if len(pages) > 1:
        for page_index, embed in enumerate(pages):
            embed.set_footer(text=f"Page {page_index + 1}/{len(pages)} · {len(rows)} combos")
    from bubbot.utils.embed_source_utils import apply_source_footer_to_pages

    apply_source_footer_to_pages(pages, game, kind="combo")
    return pages


class ComboListView(discord.ui.View):
    def __init__(
        self,
        game,
        char_key,
        pages,
        owner_id,
        *,
        page=0,
        menu_locked=False,
        group=None,
        section=None,
        subsection=None,
        back_to="character_select",
        source_message=None,
        prompt="",
    ):
        super().__init__(timeout=None)
        self.game = game
        self.char_key = char_key
        self.pages = list(pages or [])
        self.page = max(0, min(page, max(0, len(self.pages) - 1)))
        self.owner_id = owner_id
        self.menu_locked = bool(menu_locked)
        self.group = group
        self.section = section
        self.subsection = subsection
        self.back_to = back_to
        self.source_message = source_message
        self.prompt = prompt
        self._sync_buttons()

    def _sync_buttons(self):
        self.clear_items()
        if len(self.pages) > 1:
            self.add_item(ComboListPreviousButton())
            self.add_item(ComboListNextButton())
        self.add_item(ComboListBackButton())
        from bubbot.features.failed_prompt_report import attach_combo_report_button

        attach_combo_report_button(
            self,
            game=self.game,
            char_key=self.char_key,
            source_message=self.source_message,
            prompt=self.prompt,
            section=self.section,
            subsection=self.subsection,
        )

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

    def current_embed(self):
        return self.pages[self.page]

    def message_attachments(self):
        from bubbot.utils.embed_source_utils import source_icon_files

        return source_icon_files(self.game, kind="combo")


class ComboListPreviousButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Previous", style=discord.ButtonStyle.primary, row=0)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.page = view.page - 1 if view.page > 0 else len(view.pages) - 1
        await interaction.response.edit_message(
            embed=view.current_embed(),
            view=view,
            attachments=view.message_attachments(),
        )


class ComboListNextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Next", style=discord.ButtonStyle.primary, row=0)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.page = view.page + 1 if view.page < len(view.pages) - 1 else 0
        await interaction.response.edit_message(
            embed=view.current_embed(),
            view=view,
            attachments=view.message_attachments(),
        )


class ComboListBackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Back", style=discord.ButtonStyle.danger, row=1)

    async def callback(self, interaction: discord.Interaction):
        from bubbot.features import menu_system

        view = self.view
        if view.menu_locked and view.section is not None and view.subsection is not None:
            subsections = combo_subsections(view.game, view.char_key, view.section)
            await interaction.response.edit_message(
                embed=menu_system._combo_subsection_select_embed(view.game, view.char_key, view.section),
                view=menu_system.ComboSubsectionView(
                    view.game,
                    view.char_key,
                    view.section,
                    subsections,
                    view.owner_id,
                    page=0,
                    back_to=view.back_to,
                ),
                attachments=[],
            )
            return
        if view.menu_locked and view.section is not None:
            sections = combo_sections(view.game, view.char_key)
            await interaction.response.edit_message(
                embed=menu_system._combo_section_select_embed(
                    view.game,
                    view.char_key,
                    page=0,
                    total_pages=menu_system.ComboSectionView.page_count(sections),
                ),
                view=menu_system.ComboSectionView(
                    view.game,
                    view.char_key,
                    sections,
                    view.owner_id,
                    page=0,
                    back_to=view.back_to,
                ),
                attachments=[],
            )
            return
        if getattr(view, "back_to", None) == "game_menu":
            await menu_system._edit_to_game_menu(interaction, view.game, view.owner_id)
            return
        if view.menu_locked:
            chars = combo_character_list(view.game)
            await interaction.response.edit_message(
                embed=menu_system._combo_character_select_embed(view.game, page=0, total_pages=max(1, (len(chars) + 24) // 25)),
                view=menu_system.ComboCharacterSelectView(view.game, chars, view.owner_id, page=0),
                attachments=[],
            )
            return
        await menu_system._edit_to_game_menu(interaction, view.game, view.owner_id)


async def send_combo_section_menu(
    destination,
    game,
    char_key,
    owner_id=None,
    *,
    menu_locked=True,
    back_to="game_menu",
):
    """Open the per-character section button screen (same as menu after picking a character)."""
    from bubbot.features import menu_system

    sections = combo_sections(game, char_key)
    if not sections:
        return []
    embed = menu_system._combo_section_select_embed(
        game,
        char_key,
        page=0,
        total_pages=menu_system.ComboSectionView.page_count(sections),
    )
    view = menu_system.ComboSectionView(
        game,
        char_key,
        sections,
        owner_id,
        page=0,
        back_to=back_to,
    )
    send_kwargs = {"embed": embed, "view": view}
    if hasattr(destination, "response") and hasattr(destination.response, "is_done"):
        if not destination.response.is_done():
            sent = await destination.response.send_message(**send_kwargs)
        else:
            sent = await destination.followup.send(**send_kwargs)
        return [sent.id]
    if hasattr(destination, "reply"):
        sent = await destination.reply(**send_kwargs)
        return [sent.id]
    sent = await destination.send(**send_kwargs)
    return [sent.id]


async def send_combo_entry(
    destination,
    game,
    char_key,
    payload,
    owner_id=None,
    *,
    back_to="game_menu",
    source_message=None,
    prompt="",
    client=None,
):
    """Route NL/slash combo queries to the section menu or a filtered list."""
    if source_message is None and hasattr(destination, "content"):
        source_message = destination
    if not prompt and source_message is not None:
        prompt = str(getattr(source_message, "content", "") or "")
    nav, details = combo_entry_nav(
        game,
        char_key,
        group=payload.get("group"),
        rows=payload.get("rows"),
    )
    if nav == "section_menu":
        return await send_combo_section_menu(
            destination,
            game,
            char_key,
            owner_id,
            menu_locked=True,
            back_to=back_to,
        )
    if nav == "empty":
        return []
    if nav == "section_list":
        return await send_combo_response(
            destination,
            game,
            char_key,
            details["rows"],
            owner_id=owner_id,
            menu_locked=True,
            section=details["section"],
            back_to=back_to,
            source_message=source_message,
            prompt=prompt,
            client=client,
        )
    return await send_combo_response(
        destination,
        game,
        char_key,
        details["rows"],
        owner_id=owner_id,
        menu_locked=True,
        group=details["group"],
        back_to=back_to,
        source_message=source_message,
        prompt=prompt,
        client=client,
    )


async def send_combo_response(
    destination,
    game,
    char_key,
    rows,
    *,
    owner_id=None,
    menu_locked=False,
    group=None,
    section=None,
    subsection=None,
    back_to="character_select",
    source_message=None,
    prompt="",
    client=None,
):
    from bubbot.utils.embed_source_utils import source_icon_files

    pages = build_combo_pages(game, char_key, rows, group=group, section=section, subsection=subsection)
    if not pages:
        return []
    view = ComboListView(
        game,
        char_key,
        pages,
        owner_id,
        menu_locked=menu_locked,
        group=group,
        section=section,
        subsection=subsection,
        back_to=back_to,
        source_message=source_message,
        prompt=prompt,
    )
    send_kwargs = {"embed": pages[0], "view": view, "files": source_icon_files(game, kind="combo")}
    if hasattr(destination, "response") and hasattr(destination.response, "is_done"):
        if not destination.response.is_done():
            sent = await destination.response.send_message(**send_kwargs)
        else:
            sent = await destination.followup.send(**send_kwargs)
    elif hasattr(destination, "reply"):
        sent = await destination.reply(**send_kwargs)
    else:
        sent = await destination.send(**send_kwargs)
    from bubbot.features.failed_prompt_report import stamp_report_context_on_sent

    stamp_report_context_on_sent(view, sent, client=client)
    return [sent.id]


def build_combo_embed(game, char_key, rows, *, group=None, section=None, subsection=None):
    pages = build_combo_pages(game, char_key, rows, group=group, section=section, subsection=subsection)
    return pages[0] if pages else discord.Embed(description="No combos found.")
