"""Compatibility facade for the extracted Discord menu modules."""

import math

import discord

from bubbot.features import combo_menu, frame_result_ui, menu_catalog, menu_selects

_MENU_MODULES = (frame_result_ui, menu_selects, combo_menu)


def _public_values(module):
    return {
        name: value
        for name, value in vars(module).items()
        if not name.startswith("__") and name not in {"configure", "_catalog"}
    }


globals().update(_public_values(menu_catalog))
for _module in _MENU_MODULES:
    globals().update(_public_values(_module))


def configure(**deps):
    """Configure catalogs, shared dependencies, and facade helper callbacks."""
    menu_catalog.configure(**deps)
    shared = _public_values(menu_catalog)
    for module in _MENU_MODULES:
        module.configure(**shared)
        shared.update(_public_values(module))
    facade_helpers = {
        name: globals()[name]
        for name in (
            "_main_menu_embed",
            "_game_menu_embed",
            "_character_select_embed",
            "_move_select_embed",
            "_game_menu_view",
            "_open_framedata_character_select",
            "_open_sf6_stats_character_select",
            "_open_game_combos_menu",
            "_open_quiz_difficulty",
        )
        if name in globals()
    }
    facade_helpers.update(
        MainMenuView=menu_selects.MainMenuView,
        CharacterSelectView=menu_selects.CharacterSelectView,
        MoveSelectView=menu_selects.MoveSelectView,
    )
    shared.update(facade_helpers)
    for module in _MENU_MODULES:
        module.configure(**shared)
    globals().update(shared)




# Main menu and per-game submenus


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



# Quiz difficulty picker (launches quiz_module.start_quiz)


# Menu embed builders and public send entrypoints
def _main_menu_embed():
    return discord.Embed(
        title="Bub Menu",
        description="Choose a game from the dropdown below, or open Readme for a quick tutorial.",
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
            "Shared names can be ambiguous. Add tags like `sfv`, `3s`, `ggst`, `ggacr`, `bbcf`, `cotw`, "
            "`2xko`, or `mk1` when Bub needs context. Bare `guilty gear` defaults to Strive; "
            "use `+r`, `plus r`, `gg +r`, `accent core`, `acpr`, or `guilty gear accent core` for Guilty Gear Accent Core Plus R. "
            "Example: `@Bub 3s ken hadouken`."
        ),
        inline=False,
    )
    embed.add_field(
        name="3. Images, Notes, And Hitboxes",
        value=(
            "Ask for `hitbox`, `image`, `gif`, or `notes` when supported. Frame results show hitbox GIFs/images "
            "automatically when available, and notes can be toggled with the Show Notes button. Some games "
            "also expose `Show All Images` for multi-image moves."
        ),
        inline=False,
    )
    embed.add_field(
        name="4. Menus And Slash Commands",
        value=(
            "Use `/bub` for the guided menu (game picker dropdown), `@bub` alone for the main menu, "
            "or `@bub` plus a game tag only (e.g. `@bub sf6`) to open that game's menu. "
            "Slash commands include `/sf6`, `/sf6-stats` (SF6 stats), `/sf6-combos`, `/ggst`, `/ggacr`, `/bbcf`, `/cotw`, `/third-strike`, `/mk1`, `/mk1-combos`, and `/glossary`. "
            "Menus are locked to the user who opened them."
        ),
        inline=False,
    )
    embed.add_field(
        name="FG Glossary",
        value=(
            "Use `/glossary safe jump`, `@Bub glossary option select`, or the main menu Glossary button "
            "to show a local glossary definition with a source link to Infil's Fighting Game Glossary."
        ),
        inline=False,
    )
    embed.add_field(
        name="5. Quiz And Compare",
        value=(
            "Each game menu has Combos (SF6/MK1) and Quiz. The SF6 menu also has Stats between Frame Data and Combos for character stat sheets. "
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


def _combo_character_select_embed(game, page=None, total_pages=None):
    from bubbot.frame_data import combo_data

    page_text = f"\nPage {page + 1}/{total_pages}" if page is not None and total_pages else ""
    return discord.Embed(
        title=f"{combo_data.game_label(game)} - Combos",
        description=f"Select a character to see available combo routes.{page_text}",
        colour=combo_data.game_colour(game),
    )


def _combo_section_select_embed(game, char_key, page=None, total_pages=None):
    from bubbot.frame_data import combo_data

    page_text = f"\nPage {page + 1}/{total_pages}" if page is not None and total_pages and total_pages > 1 else ""
    return discord.Embed(
        title=f"{combo_data.game_label(game)} - {combo_data.display_char_name(game, char_key)}",
        description=f"Pick a combo section (headings from the SuperCombo page).{page_text}",
        colour=combo_data.game_colour(game),
    )


def _combo_subsection_select_embed(game, char_key, section_label, page=None, total_pages=None):
    from bubbot.frame_data import combo_data

    page_text = f"\nPage {page + 1}/{total_pages}" if page is not None and total_pages and total_pages > 1 else ""
    return discord.Embed(
        title=f"{combo_data.game_label(game)} - {combo_data.display_char_name(game, char_key)}",
        description=f"**{section_label}** — pick a sub-section.{page_text}",
        colour=combo_data.game_colour(game),
    )


async def send_main_menu(destination, owner_id=None):
    await destination.send(
        embed=_main_menu_embed(),
        view=MainMenuView(owner_id),
    )


async def send_game_menu(destination, game, owner_id=None):
    game_key = str(game or "").strip().lower()
    await destination.send(
        embed=_game_menu_embed(_game_label(game_key), _game_colour(game_key)),
        view=_game_menu_view(game_key, owner_id),
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
