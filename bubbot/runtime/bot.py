import discord
import os
import asyncio
import random
import datetime
import json
import difflib
import re
import pandas as pd
from dotenv import load_dotenv
from bubbot.data.aliases import (
    CHARACTER_ALIASES,
    CHARACTER_INPUT_ALIASES,
    DP_PREFIX_EXCEPTIONS,
    INPUT_ALIASES,
)
try:
    from bubbot.features.bub_llm import (
        ENCOURAGEMENT_ANECDOTE_PROMPT,
        ENCOURAGEMENT_CONTEXT_CHANCE,
        ENCOURAGEMENT_CONTEXT_SOURCE,
        ENCOURAGEMENT_PROMPTS,
        GEMINI_ENABLED,
        IMPROVEMENT_PROMPT,
        LLM_ENABLED,
        LLM_PROVIDER_ERROR,
        MEMORY_PROMPT,
        MIMO_ENABLED,
        MOVE_DEFINITIONS,
        OPENROUTER_ENABLED,
        SYSTEM_PROMPT,
        build_memory_context,
        build_reminder_ack_text,
        build_reminder_fire_text,
        build_streetfighterdle_reminder_text,
        build_gemini_media_parts,
        build_llm_context_history,
        build_mimo_media_parts,
        build_prompting_user_identity,
        capture_discord_memory,
        capture_message_exchange_memory,
        estimate_llm_context_history_char_budget,
        ensure_memory_file_exists,
        get_llm_response,
        get_media_context,
        get_message_media_items,
        get_selected_figures_str,
        load_memory_entries,
        log_llm_provider_status,
        rewrite_ggst_lookup_query_with_llm,
        rewrite_sf_lookup_query_with_llm,
        send_deleted_message_failsafe,
        send_generated_encouragement,
        should_use_search,
    )
except ModuleNotFoundError as import_error:
    if import_error.name != "bub_llm":
        raise
    from bubbot.features.bub_llm_fallback import (
        ENCOURAGEMENT_ANECDOTE_PROMPT,
        ENCOURAGEMENT_CONTEXT_CHANCE,
        ENCOURAGEMENT_CONTEXT_SOURCE,
        ENCOURAGEMENT_PROMPTS,
        GEMINI_ENABLED,
        IMPROVEMENT_PROMPT,
        LLM_ENABLED,
        LLM_PROVIDER_ERROR,
        MEMORY_PROMPT,
        MIMO_ENABLED,
        MOVE_DEFINITIONS,
        OPENROUTER_ENABLED,
        SYSTEM_PROMPT,
        build_memory_context,
        build_reminder_ack_text,
        build_reminder_fire_text,
        build_streetfighterdle_reminder_text,
        build_gemini_media_parts,
        build_llm_context_history,
        build_mimo_media_parts,
        build_prompting_user_identity,
        capture_discord_memory,
        capture_message_exchange_memory,
        estimate_llm_context_history_char_budget,
        ensure_memory_file_exists,
        get_llm_response,
        get_media_context,
        get_message_media_items,
        get_selected_figures_str,
        load_memory_entries,
        log_llm_provider_status,
        rewrite_ggst_lookup_query_with_llm,
        rewrite_sf_lookup_query_with_llm,
        send_deleted_message_failsafe,
        send_generated_encouragement,
        should_use_search,
    )
from bubbot.features.reminders import ReminderManager
from bubbot.features.scheduler import SchedulerManager
import bubbot.features.quiz as quiz_module
import bubbot.frame_data.gif_lookup as gif_lookup_module
import bubbot.frame_data.frame_output as frame_output_module
import bubbot.frame_data.ggst_frame_data as ggst_module
import bubbot.frame_data.tuco_frame_data as tuco_module
import bubbot.frame_data.bbcf_frame_data as bbcf_module
import bubbot.frame_data.cotw_frame_data as cotw_module
import bubbot.frame_data.third_strike_frame_data as third_strike_module
import bubbot.frame_data.mk1_frame_data as mk1_module
import bubbot.features.menu_system as menu_system
from bubbot.frame_data.frame_output import send_frame_embeds_with_views, send_frame_table_response, send_gif_links_response
from bubbot.frame_data.gif_lookup import get_frame_row_gif_links
from bubbot.utils.character_lookup import find_aliases_in_text, resolve_alias_key, text_mentions_alias
from bubbot.utils.choice_utils import autocomplete_values as shared_autocomplete_values
from bubbot.utils.choice_utils import character_choices as shared_character_choices
from bubbot.utils.choice_utils import move_choices as shared_move_choices
from bubbot.utils.slash_frame_flow import send_slash_frame_result
from bubbot.utils.text_utils import compact_key, contains_token_sequence, word_tokens

load_dotenv()
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TOKEN = os.getenv('DISCORD_TOKEN')
try:
    CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
except (TypeError, ValueError):
    print("Error: CHANNEL_ID not found or invalid in .env")
    CHANNEL_ID = None

DAILY_VIDEO_URL = (
    "https://cdn.discordapp.com/attachments/1345474577316319265/1467924199996915918/l3.mp4?ex=69822671&is=6980d4f1&hm=7e1208fa08199a25f9cac3dc8132696f2a9374fac61bfb2b5ae75e31f6695bea&"
)
STREETFIGHTERDLE_URL = "https://www.streetfighterdle.net/"
STREETFIGHTERDLE_SCORE_SOURCE_CHANNEL_ID = 1439264736494489761
STREETFIGHTERDLE_SCORES_FILE = os.getenv('STREETFIGHTERDLE_SCORES_FILE', 'streetfighterdle_scores.json')
DAILY_ENCOURAGEMENT_MESSAGES = 5
DAILY_DAMN_GG_MESSAGES = 1
DAILY_STREETFIGHTERDLE_MESSAGES = 1
DAILY_DAMN_GG_TEXT = "damn gg"
MEMORY_FILE = os.getenv('MEMORY_FILE', 'memory.md')
MEMORY_MAX_ENTRIES = max(10, int(os.getenv('MEMORY_MAX_ENTRIES', '200')))
MEMORY_CONTEXT_MAX_MESSAGES = max(4, int(os.getenv('MEMORY_CONTEXT_MAX_MESSAGES', '12')))
MEMORY_CONTEXT_CHAR_BUDGET = max(600, int(os.getenv('MEMORY_CONTEXT_CHAR_BUDGET', '2200')))
SCROLLS_MAINTAINER_USER_ID = 427263312217243668
SCROLLS_FIX_REQUEST_TEXT = "please fix this or add this to my scrolls"
RANGE_SCROLLS_MISSING_TEXT = "the range of that move is not on the supercombo scrolls"
RANGE_MISSING_PLACEHOLDERS = {"{{{atkrange}}}"}


def is_missing_attack_range_value(raw_value):
    text = str(raw_value or "").strip()
    if not text:
        return True
    normalized = re.sub(r"\s+", "", text).lower()
    return normalized in RANGE_MISSING_PLACEHOLDERS

MENTION_PATTERN = re.compile(r"<@!?\d+>|<@&\d+>|<#\d+>")


def strip_url_like_text(text):
    cleaned = str(text or "")
    cleaned = re.sub(r"https?://\S+", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bwww\.\S+\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\S+\.gif(?:\?\S*)?\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\S+\.gifv(?:\?\S*)?\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def has_explicit_gif_lookup_intent(text):
    cleaned = strip_url_like_text(strip_discord_mentions(text).lower())
    return bool(
        re.search(r"\bgif(?:s)?\b", cleaned)
        or re.search(r"\bhit\s*box(?:es)?\b", cleaned)
        or re.search(r"\bhitbox(?:es)?\b", cleaned)
    )

log_llm_provider_status()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)


def _slash_choices(values):
    return [discord.app_commands.Choice(name=str(value)[:100], value=str(value)[:100]) for value in values[:25]]


def _move_type_sort_key(row):
    move_type = str(row.get("moveType", "")).strip().lower()
    move_name = str(row.get("moveName", "")).strip().lower()
    num_cmd = str(row.get("numCmd", "")).strip().lower()
    if "super" in move_type or "super" in move_name or re.search(r"\bsa[123]\b", num_cmd):
        bucket = 0
    elif "special" in move_type:
        bucket = 1
    elif "unique" in move_type or "target" in move_type:
        bucket = 2
    elif "throw" in move_type:
        bucket = 3
    else:
        bucket = 4
    return (bucket, move_name, num_cmd)


def _move_choice_label(row):
    move_name = str(row.get("moveName", "")).strip()
    num_cmd = str(row.get("numCmd", "")).strip()
    move_type = str(row.get("moveType", "")).strip().lower()
    label = f"{move_name} ({num_cmd})" if move_name and num_cmd else move_name or num_cmd
    if move_type and move_type not in {"normal", ""}:
        label = f"{label} [{move_type}]"
    return label


def _autocomplete_values(current, values):
    return shared_autocomplete_values(current, values)


def _sf6_character_choice_values():
    return sorted(display for _char_key, display in shared_character_choices({key: rows for key, rows in FRAME_DATA.items() if rows}))


def _ggst_character_choice_values():
    return sorted(display for _char_key, display in shared_character_choices({key: rows for key, rows in ggst_module.GGST_FRAME_DATA.items() if rows}))


def _tuco_character_choice_values():
    return sorted(display for _char_key, display in shared_character_choices({key: rows for key, rows in tuco_module.TUCO_FRAME_DATA.items() if rows}))


def _bbcf_character_choice_values():
    return sorted(display for _char_key, display in shared_character_choices({key: rows for key, rows in bbcf_module.BBCF_FRAME_DATA.items() if rows}))


def _cotw_character_choice_values():
    return sorted(display for _char_key, display in shared_character_choices({key: rows for key, rows in cotw_module.COTW_FRAME_DATA.items() if rows}))


def _third_strike_character_choice_values():
    return sorted(display for _char_key, display in shared_character_choices({key: rows for key, rows in third_strike_module.THIRD_STRIKE_FRAME_DATA.items() if rows}))


def _mk1_character_choice_values():
    return sorted(display for _char_key, display in shared_character_choices({key: rows for key, rows in mk1_module.MK1_FRAME_DATA.items() if rows}, display_fn=lambda char_key, _rows: mk1_module.display_char_name(char_key)))


def _sf6_move_choice_values(char_name):
    char_key = resolve_character_key(char_name)
    if not char_key:
        return []
    values = []
    for _row, label in shared_move_choices(FRAME_DATA.get(char_key, []), label_fn=_move_choice_label, key_fields=("moveName", "numCmd", "moveType")):
        if label:
            values.append(label)
    return values


def _sf6_char_state_choice_values(char_name):
    char_key = resolve_character_key(char_name)
    state_map = {
        "ryu": ["denjin"],
        "jamie": ["drink 1", "drink 2", "drink 3", "drink 4"],
        "lily": ["stocked"],
        "mai": ["stocked"],
        "juri": ["stocked"],
    }
    return state_map.get(char_key, [])


def _ggst_move_choice_values(char_name):
    char_key = ggst_module.resolve_character_key(char_name)
    if not char_key:
        return []
    values = []
    seen = set()
    rows = []
    rows.extend(ggst_module.GGST_FRAME_DATA.get(char_key, []))
    rows.extend(ggst_module.GGST_SUPPLEMENTAL_FRAME_DATA.get(char_key, []))
    for state_rows in ggst_module.GGST_STATE_FRAME_DATA.get(char_key, {}).values():
        rows.extend(state_rows)
    for _row, label in shared_move_choices(rows, label_fn=_move_choice_label, key_fields=("moveName", "numCmd", "moveType")):
        if label and label not in seen:
            seen.add(label)
            values.append(label)
    return values


def _tuco_move_choice_values(char_name):
    char_key = tuco_module.resolve_character_key(char_name)
    if not char_key:
        return []
    values = []
    for _row, label in shared_move_choices(tuco_module.TUCO_FRAME_DATA.get(char_key, []), label_fn=_move_choice_label, key_fields=("moveName", "numCmd")):
        if label:
            values.append(label)
    return values


def _bbcf_move_choice_values(char_name):
    char_key = bbcf_module.resolve_character_key(char_name)
    if not char_key:
        return []
    values = []
    for _row, label in shared_move_choices(bbcf_module.BBCF_FRAME_DATA.get(char_key, []), label_fn=_move_choice_label, key_fields=("moveName", "numCmd", "moveType")):
        if label:
            values.append(label)
    return values


def _cotw_move_choice_values(char_name):
    char_key = cotw_module.resolve_character_key(char_name)
    if not char_key:
        return []
    values = []
    for _row, label in shared_move_choices(cotw_module.COTW_FRAME_DATA.get(char_key, []), label_fn=_move_choice_label, key_fields=("moveName", "numCmd", "moveType")):
        if label:
            values.append(label)
    return values


def _third_strike_move_choice_values(char_name):
    char_key = third_strike_module.resolve_character_key(char_name)
    if not char_key:
        return []
    values = []
    for _row, label in shared_move_choices(third_strike_module.THIRD_STRIKE_FRAME_DATA.get(char_key, []), label_fn=_move_choice_label, key_fields=("moveName", "numCmd", "version", "moveType")):
        if label:
            values.append(label)
    return values


def _mk1_move_choice_values(char_name):
    char_key = mk1_module.resolve_character_key(char_name)
    if not char_key:
        return []
    values = []
    for _row, label in shared_move_choices(mk1_module.MK1_FRAME_DATA.get(char_key, []), label_fn=_move_choice_label, key_fields=("moveName", "numCmd", "moveType")):
        if label:
            values.append(label)
    return values


def _mk1_combo_character_choice_values():
    return sorted(display for _char_key, display in shared_character_choices({key: rows for key, rows in mk1_module.MK1_COMBO_DATA.items() if rows}))


def _ggst_char_state_choice_values(char_name):
    char_key = ggst_module.resolve_character_key(char_name)
    if not char_key:
        return []
    values = []
    seen = set()
    for row_map in ggst_module.GGST_STATE_FRAME_DATA.get(char_key, {}).values():
        for row in row_map:
            state_label = str(row.get("state_label", "")).strip()
            state_key = str(row.get("state_key", "")).strip()
            for value in (state_label, state_key):
                if value and value not in seen:
                    seen.add(value)
                    values.append(value)
    for row in ggst_module.GGST_SUPPLEMENTAL_FRAME_DATA.get(char_key, []):
        state_label = str(row.get("state_label", "")).strip()
        state_key = str(row.get("state_key", "")).strip()
        for value in (state_label, state_key):
            if value and value not in seen:
                seen.add(value)
                values.append(value)
    return values


def _strip_autocomplete_label(value):
    text = str(value or "").strip()
    text = re.sub(r"\s+\[[^\]]+\]$", "", text).strip()
    match = re.match(r"^(.+)\s+\(([^()]*)\)$", text)
    if match:
        return match.group(2).strip() or match.group(1).strip()
    return text


async def _send_sf6_slash_frame(interaction, char_name, move_name, char_state=None):
    if char_state and char_state not in _sf6_char_state_choice_values(char_name):
        await interaction.response.send_message(f"{char_name} does not use the `{char_state}` state for SF6 lookups.")
        return
    query = f"{char_name} {char_state or ''} {_strip_autocomplete_label(move_name)} framedata".strip().lower()
    await send_slash_frame_result(
        interaction,
        char_name=char_name,
        move_name=move_name,
        query=query,
        parse_fn=find_moves_in_text,
        embed_fn=build_frame_embed,
        view_fn=frame_output_module.FrameDataGifView,
        game_label="SF6",
        prompt_predicate=lambda payload: "Special Strength Options" in str(payload.get("data", "") or "") or "Target Combo Options" in str(payload.get("data", "") or ""),
    )


async def _send_ggst_slash_frame(interaction, char_name, move_name, char_state=None):
    query = f"ggst {char_name} {char_state or ''} {_strip_autocomplete_label(move_name)} framedata".strip().lower()
    await send_slash_frame_result(
        interaction,
        char_name=char_name,
        move_name=move_name,
        query=query,
        parse_fn=ggst_module.find_moves_in_text,
        embed_fn=ggst_module.build_frame_embed,
        view_fn=ggst_module.GGSTFrameDataView,
        game_label="GGST",
        disambiguation_predicate=lambda payload: payload.get("needs_disambiguation"),
    )


async def _send_tuco_slash_frame(interaction, char_name, move_name):
    query = f"2xko {char_name} {_strip_autocomplete_label(move_name)} framedata".strip().lower()
    await send_slash_frame_result(
        interaction,
        char_name=char_name,
        move_name=move_name,
        query=query,
        parse_fn=tuco_module.find_moves_in_text,
        embed_fn=tuco_module.build_frame_embed,
        view_fn=tuco_module.TUCOFrameDataView,
        game_label="2XKO",
        disambiguation_predicate=lambda payload: payload.get("needs_disambiguation"),
    )


async def _send_bbcf_slash_frame(interaction, char_name, move_name):
    query = f"bbcf {char_name} {_strip_autocomplete_label(move_name)} framedata".strip().lower()
    await send_slash_frame_result(
        interaction,
        char_name=char_name,
        move_name=move_name,
        query=query,
        parse_fn=bbcf_module.find_moves_in_text,
        embed_fn=bbcf_module.build_frame_embed,
        view_fn=bbcf_module.BBCFFrameDataView,
        game_label="BBCF",
        disambiguation_predicate=lambda payload: payload.get("needs_disambiguation"),
    )


async def _send_cotw_slash_frame(interaction, char_name, move_name):
    query = f"cotw {char_name} {_strip_autocomplete_label(move_name)} framedata".strip().lower()
    payload = cotw_module.find_moves_in_text(query)
    rows = payload.get("rows", []) or []
    if payload.get("needs_disambiguation"):
        await interaction.response.send_message(str(payload.get("data", "Please specify which COTW move you mean."))[:2000])
        return
    if not rows:
        await interaction.response.send_message(f"{char_name} with {move_name} is not a valid character/move combination for COTW")
        return
    row = rows[0]
    view = cotw_module.COTWFrameDataView(row)
    file, attachment_url = await cotw_module.build_image_attachment(row)
    if file and attachment_url:
        view.image_url_override = attachment_url
        view.cotw_image_bytes = file.fp.getvalue()
        view.cotw_image_filename = file.filename
    files = view.active_files()
    await interaction.response.send_message(embed=view.build_embed(), view=view, files=files)


async def _send_third_strike_slash_frame(interaction, char_name, move_name):
    query = f"3s {char_name} {_strip_autocomplete_label(move_name)} framedata".strip().lower()
    await send_slash_frame_result(
        interaction,
        char_name=char_name,
        move_name=move_name,
        query=query,
        parse_fn=third_strike_module.find_moves_in_text,
        embed_fn=third_strike_module.build_frame_embed,
        view_fn=third_strike_module.ThirdStrikeFrameDataView,
        game_label="Third Strike",
        disambiguation_predicate=lambda payload: payload.get("needs_disambiguation"),
    )


async def _send_mk1_slash_frame(interaction, char_name, move_name):
    query = f"mk1 {char_name} {_strip_autocomplete_label(move_name)} framedata".strip().lower()
    await send_slash_frame_result(
        interaction,
        char_name=char_name,
        move_name=move_name,
        query=query,
        parse_fn=mk1_module.find_moves_in_text,
        embed_fn=mk1_module.build_frame_embed,
        view_fn=mk1_module.MK1FrameDataView,
        game_label="MK1",
        disambiguation_predicate=lambda payload: payload.get("needs_disambiguation"),
    )


async def _send_mk1_slash_combos(interaction, char_name, difficulty=None, position=None):
    query_parts = ["mk1", char_name, difficulty or "", position or "", "combos"]
    payload = mk1_module.find_moves_in_text(" ".join(part for part in query_parts if part).lower())
    rows = payload.get("combo_rows", []) or []
    char_key = mk1_module.resolve_character_key(char_name)
    if not rows or not char_key:
        await interaction.response.send_message(f"No MK1 combos found for {char_name} with those filters.")
        return
    await interaction.response.send_message(embed=mk1_module.build_combo_embed(char_key, rows))


@tree.command(name="bub", description="Open Bub's menu")
async def bub_slash_command(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=menu_system._main_menu_embed(),
        view=menu_system.MainMenuView(interaction.user.id),
    )


@tree.command(name="ggst")
@discord.app_commands.describe(
    char_name="The characters name",
    move_name="The move name",
    char_state="Optional char specific states like Installs.",
)
async def ggst(interaction: discord.Interaction, char_name: str, move_name: str, char_state: str = None):
    """Get Guilty Gear Strive frame data for the specific char and move.

    Also works with stats of the char like fdash, bdash, throw range etc."""
    return await _send_ggst_slash_frame(interaction, char_name, move_name, char_state)


@tree.command(name="2xko")
@discord.app_commands.describe(
    char_name="The champion name",
    move_name="The move name or input",
)
async def tuco(interaction: discord.Interaction, char_name: str, move_name: str):
    """Get 2XKO frame data for the specific champion and move."""
    return await _send_tuco_slash_frame(interaction, char_name, move_name)


@tree.command(name="bbcf")
@discord.app_commands.describe(
    char_name="The character name",
    move_name="The move name or input",
)
async def bbcf(interaction: discord.Interaction, char_name: str, move_name: str):
    """Get BlazBlue Central Fiction frame data for the specific character and move."""
    return await _send_bbcf_slash_frame(interaction, char_name, move_name)


@tree.command(name="cotw")
@discord.app_commands.describe(
    char_name="The character name",
    move_name="The move name or input",
)
async def cotw(interaction: discord.Interaction, char_name: str, move_name: str):
    """Get Fatal Fury: City of the Wolves frame data for the specific character and move."""
    return await _send_cotw_slash_frame(interaction, char_name, move_name)


@tree.command(name="third-strike")
@discord.app_commands.describe(
    char_name="The character name",
    move_name="The move name or input",
)
async def third_strike(interaction: discord.Interaction, char_name: str, move_name: str):
    """Get Street Fighter III: 3rd Strike frame data for the specific character and move."""
    return await _send_third_strike_slash_frame(interaction, char_name, move_name)


@tree.command(name="mk1")
@discord.app_commands.describe(
    char_name="The character or kameo name",
    move_name="The move name or input",
)
async def mk1(interaction: discord.Interaction, char_name: str, move_name: str):
    """Get Mortal Kombat 1 frame data for the specific character or kameo move."""
    return await _send_mk1_slash_frame(interaction, char_name, move_name)


@tree.command(name="mk1-combos")
@discord.app_commands.describe(
    char_name="The character name",
    difficulty="Optional difficulty filter: easy, medium, or hard",
    position="Optional position filter: midscreen or corner",
)
async def mk1_combos(interaction: discord.Interaction, char_name: str, difficulty: str = None, position: str = None):
    """Get Mortal Kombat 1 combo routes for a character."""
    return await _send_mk1_slash_combos(interaction, char_name, difficulty, position)


@tree.command(name="sf6")
@discord.app_commands.describe(
    char_name="The characters name",
    move_name="The move name",
    char_state="Optional char specific states like Installs.",
)
async def sf6(
    interaction: discord.Interaction,
    char_name: str,
    move_name: str,
    char_state: str = None,
):
    """Get SF6 frame data for the specific char and move.

    Also works with stats of the char like fdash, bdash, throw range etc."""
    return await _send_sf6_slash_frame(interaction, char_name, move_name, char_state)


@sf6.autocomplete("char_state")
async def sf6_char_state_autocomplete(interaction: discord.Interaction, current: str):
    if not interaction.namespace.char_name:
        return _slash_choices([])
    return _slash_choices(_autocomplete_values(current, _sf6_char_state_choice_values(interaction.namespace.char_name)))


@sf6.autocomplete("char_name")
async def sf6_char_autocomplete(interaction: discord.Interaction, current: str):
    return _slash_choices(_autocomplete_values(current, _sf6_character_choice_values()))


@sf6.autocomplete("move_name")
async def sf6_move_autocomplete(interaction: discord.Interaction, current: str):
    if not interaction.namespace.char_name:
        return _slash_choices([])
    return _slash_choices(_autocomplete_values(current, _sf6_move_choice_values(interaction.namespace.char_name)))


@ggst.autocomplete("char_name")
async def ggst_char_autocomplete(interaction: discord.Interaction, current: str):
    return _slash_choices(_autocomplete_values(current, _ggst_character_choice_values()))


@ggst.autocomplete("char_state")
async def ggst_char_state_autocomplete(interaction: discord.Interaction, current: str):
    if not interaction.namespace.char_name:
        return _slash_choices([])
    return _slash_choices(_autocomplete_values(current, _ggst_char_state_choice_values(interaction.namespace.char_name)))


@ggst.autocomplete("move_name")
async def ggst_move_autocomplete(interaction: discord.Interaction, current: str):
    if not interaction.namespace.char_name:
        return _slash_choices([])
    return _slash_choices(_autocomplete_values(current, _ggst_move_choice_values(interaction.namespace.char_name)))


@tuco.autocomplete("char_name")
async def tuco_char_autocomplete(interaction: discord.Interaction, current: str):
    return _slash_choices(_autocomplete_values(current, _tuco_character_choice_values()))


@tuco.autocomplete("move_name")
async def tuco_move_autocomplete(interaction: discord.Interaction, current: str):
    if not interaction.namespace.char_name:
        return _slash_choices([])
    return _slash_choices(_autocomplete_values(current, _tuco_move_choice_values(interaction.namespace.char_name)))


@bbcf.autocomplete("char_name")
async def bbcf_char_autocomplete(interaction: discord.Interaction, current: str):
    return _slash_choices(_autocomplete_values(current, _bbcf_character_choice_values()))


@bbcf.autocomplete("move_name")
async def bbcf_move_autocomplete(interaction: discord.Interaction, current: str):
    if not interaction.namespace.char_name:
        return _slash_choices([])
    return _slash_choices(_autocomplete_values(current, _bbcf_move_choice_values(interaction.namespace.char_name)))


@cotw.autocomplete("char_name")
async def cotw_char_autocomplete(interaction: discord.Interaction, current: str):
    return _slash_choices(_autocomplete_values(current, _cotw_character_choice_values()))


@cotw.autocomplete("move_name")
async def cotw_move_autocomplete(interaction: discord.Interaction, current: str):
    if not interaction.namespace.char_name:
        return _slash_choices([])
    return _slash_choices(_autocomplete_values(current, _cotw_move_choice_values(interaction.namespace.char_name)))


@third_strike.autocomplete("char_name")
async def third_strike_char_autocomplete(interaction: discord.Interaction, current: str):
    return _slash_choices(_autocomplete_values(current, _third_strike_character_choice_values()))


@third_strike.autocomplete("move_name")
async def third_strike_move_autocomplete(interaction: discord.Interaction, current: str):
    if not interaction.namespace.char_name:
        return _slash_choices([])
    return _slash_choices(_autocomplete_values(current, _third_strike_move_choice_values(interaction.namespace.char_name)))


@mk1.autocomplete("char_name")
async def mk1_char_autocomplete(interaction: discord.Interaction, current: str):
    return _slash_choices(_autocomplete_values(current, _mk1_character_choice_values()))


@mk1.autocomplete("move_name")
async def mk1_move_autocomplete(interaction: discord.Interaction, current: str):
    if not interaction.namespace.char_name:
        return _slash_choices([])
    return _slash_choices(_autocomplete_values(current, _mk1_move_choice_values(interaction.namespace.char_name)))


@mk1_combos.autocomplete("char_name")
async def mk1_combo_char_autocomplete(interaction: discord.Interaction, current: str):
    return _slash_choices(_autocomplete_values(current, _mk1_combo_character_choice_values()))


@mk1_combos.autocomplete("difficulty")
async def mk1_combo_difficulty_autocomplete(interaction: discord.Interaction, current: str):
    return _slash_choices(_autocomplete_values(current, ["easy", "medium", "hard"]))


@mk1_combos.autocomplete("position")
async def mk1_combo_position_autocomplete(interaction: discord.Interaction, current: str):
    return _slash_choices(_autocomplete_values(current, ["midscreen", "corner"]))


def truncate_message(text, limit=1800):
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."




def _streetfighterdle_scores_file_path():
    path_text = str(STREETFIGHTERDLE_SCORES_FILE or "streetfighterdle_scores.json").strip()
    if os.path.isabs(path_text):
        return path_text
    return os.path.join(os.path.dirname(__file__), path_text)


def load_streetfighterdle_score_history():
    file_path = _streetfighterdle_scores_file_path()
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        print(f"[streetfighterdle] score history load error: {e}", flush=True)
        return {}
    if not isinstance(payload, dict):
        return {}
    days = payload.get("days") or {}
    return dict(days) if isinstance(days, dict) else {}


def save_streetfighterdle_score_snapshot(snapshot_date_utc, entries, source_channel_id=None):
    history = load_streetfighterdle_score_history()
    normalized_entries = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        normalized_entries.append(
            {
                "user_id": int(entry.get("user_id", 0) or 0),
                "display_name": str(entry.get("display_name", "Unknown")).strip() or "Unknown",
                "score_text": str(entry.get("score_text", "")).strip(),
                "total_points": int(entry.get("total_points", 0) or 0),
                "per_game": [int(value) for value in list(entry.get("per_game") or [])[:4]],
                "message_id": int(entry.get("message_id", 0) or 0),
                "created_at_utc": str(entry.get("created_at_utc", "")).strip(),
            }
        )

    snapshot_key = str(snapshot_date_utc)
    history[snapshot_key] = {
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_channel_id": int(source_channel_id or STREETFIGHTERDLE_SCORE_SOURCE_CHANNEL_ID),
        "entries": normalized_entries,
    }

    file_path = _streetfighterdle_scores_file_path()
    payload = {
        "version": 1,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "days": history,
    }
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, indent=2)
    except Exception as e:
        print(f"[streetfighterdle] score history save error: {e}", flush=True)


def parse_streetfighterdle_score_text(text):
    match = re.search(
        r"(?<![\d/])(\d{1,3})\s*/\s*(\d{1,3})\s*/\s*(\d{1,3})\s*/\s*(\d{1,3})(?![\d/])",
        str(text or ""),
    )
    if not match:
        return None
    per_game = [int(match.group(index)) for index in range(1, 5)]
    return {
        "score_text": "/".join(str(value) for value in per_game),
        "per_game": per_game,
        "total_points": sum(per_game),
    }


def build_streetfighterdle_leaderboard_text(entries, snapshot_date_utc):
    if not entries:
        return (
            "By decree of Bub, no Streetfighterdle scores were posted in the last 24 hours.\n"
            f"Window ending {snapshot_date_utc} UTC."
        )

    lines = [
        "By decree of Bub, the Streetfighterdle ledger for the last 24 hours stands thus.",
        f"Window ending {snapshot_date_utc} UTC. Lowest total wins.",
        "",
    ]
    for index, entry in enumerate(entries, start=1):
        lines.append(
            f"{index}. {entry['display_name']} - {entry['total_points']} points ({entry['score_text']})"
        )
    return truncate_message("\n".join(lines), limit=1800)


async def collect_streetfighterdle_daily_scores(channel, window_end_utc=None, lookback_hours=24):
    end_utc = window_end_utc or datetime.datetime.now(datetime.timezone.utc)
    cutoff_utc = end_utc - datetime.timedelta(hours=lookback_hours)
    latest_scores = {}

    async for msg in channel.history(limit=None, after=cutoff_utc):
        if msg.author == client.user or getattr(msg.author, "bot", False):
            continue
        parsed_score = parse_streetfighterdle_score_text(msg.content or "")
        if not parsed_score:
            continue

        user_id = int(getattr(msg.author, "id", 0) or 0)
        if user_id <= 0:
            continue

        created_at = getattr(msg, "created_at", None) or end_utc
        existing = latest_scores.get(user_id)
        if existing and existing.get("created_at") and existing["created_at"] >= created_at:
            continue

        display_name = getattr(msg.author, "display_name", None) or getattr(msg.author, "name", None) or f"User {user_id}"
        latest_scores[user_id] = {
            "user_id": user_id,
            "display_name": str(display_name).strip() or f"User {user_id}",
            "score_text": parsed_score["score_text"],
            "per_game": parsed_score["per_game"],
            "total_points": parsed_score["total_points"],
            "message_id": int(getattr(msg, "id", 0) or 0),
            "created_at": created_at,
            "created_at_utc": created_at.astimezone(datetime.timezone.utc).isoformat(),
        }

    entries = list(latest_scores.values())
    entries.sort(
        key=lambda entry: (
            int(entry.get("total_points", 0)),
            list(entry.get("per_game") or []),
            str(entry.get("display_name", "")).lower(),
        )
    )
    return entries
















def strip_discord_mentions(content):
    if not content:
        return ""
    stripped = MENTION_PATTERN.sub(" ", content)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped


def normalize_jump_normal_text(text):
    if not text:
        return ""
    strength_map = {
        "light": "l",
        "medium": "m",
        "heavy": "h",
    }
    button_map = {
        "punch": "p",
        "kick": "k",
    }

    def replace_named_jump(match):
        prefix = match.group(1) or ""
        strength = match.group(2)
        button = match.group(3)
        short = f"{strength_map[strength]}{button_map[button]}"
        if prefix:
            return f"neutral jump {short}"
        return f"jump {short}"

    text = re.sub(
        r"\b(?:(neutral|n)\s+)?jump\s+(light|medium|heavy)\s+(punch|kick)\b",
        replace_named_jump,
        text,
    )
    text = re.sub(r"\bneutral\s+j\s*\.?\s*([lmh][pk])\b", r"neutral jump \1", text)
    text = re.sub(r"\bn\.?j\s*([lmh][pk])\b", r"neutral jump \1", text)
    text = re.sub(r"\bnj\s*([lmh][pk])\b", r"neutral jump \1", text)
    text = re.sub(r"\bj\s*\.?\s*([lmh][pk])\b", r"jump \1", text)
    text = re.sub(r"\bn\.?j\s*\.?\s*([1-9][0-9]*[a-z]{1,3})\b", r"neutral j\1", text)
    text = re.sub(r"\bnj\s*([1-9][0-9]*[a-z]{1,3})\b", r"neutral j\1", text)
    text = re.sub(r"\bj\s*\.?\s*([1-9][0-9]*[a-z]{1,3})\b", r"j\1", text)
    return text










FRAME_DATA = {}
FRAME_STATS = {}
BNB_DATA = {}
OKI_DATA = {}
CHARACTER_INFO = {}
HITBOX_GIF_DATA = {}
RANGE_DATA = {}
LOCAL_HITBOX_GIF_ROOT = os.path.join(BASE_DIR, "sf6frames", "files")
LOCAL_HITBOX_GIF_EXTENSIONS = {".webp", ".gif", ".png", ".jpg", ".jpeg"}

def normalize_char_name(name: str) -> str:
    """Normalize character name to lowercase alphanumeric."""
    return compact_key(name)


def resolve_character_key(name: str):
    """Resolve free-form character text to a FRAME_DATA key."""
    return resolve_alias_key(name, CHARACTER_ALIASES, FRAME_DATA.keys(), normalize_fn=normalize_char_name)


def text_mentions_character_from_aliases(text, aliases, valid_keys):
    return text_mentions_alias(text, aliases, valid_keys)


def resolve_character_from_aliases_in_text(text, aliases, valid_keys):
    matches = find_aliases_in_text(text, aliases, valid_keys)
    return matches[0] if matches else None


def format_sheet_text(df: pd.DataFrame) -> str:
    """Convert DataFrame rows to pipe-separated text lines."""
    df = df.fillna("")
    lines = []
    for _, row in df.iterrows():
        values = []
        for val in row.tolist():
            text = str(val).strip()
            if text.lower() == "nan":
                text = ""
            values.append(text)
        while values and values[0] == "":
            values.pop(0)
        while values and values[-1] == "":
            values.pop()
        if not values:
            continue
        lines.append(" | ".join(values))
    return "\n".join(lines)

def load_frame_data():
    """Load frame data, stats, combos, oki, and character info from ODS."""
    global FRAME_DATA, FRAME_STATS, BNB_DATA, OKI_DATA, CHARACTER_INFO, HITBOX_GIF_DATA, RANGE_DATA
    filename = "FAT - SF6 Frame Data.ods"
    quiz_module.QUIZ_CHARACTER_TERMS_CACHE = None
    quiz_module.QUIZ_MOVE_NAME_TERMS_CACHE = None
    quiz_module.QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE = None
    if os.path.exists(filename):
        try:
            print(f"Loading ODS file: {filename} (This may take a moment)...")
            # Load the entire workbook
            xls = pd.ExcelFile(filename, engine='odf')
            
            # Iterate through all sheet names
            for sheet_name in xls.sheet_names:
                # Look for sheets ending in "Normal" (e.g. "ManonNormal", "RyuNormal")
                if sheet_name.endswith("Normal"):
                    # Extract character name (ManonNormal -> manon)
                    char_name = sheet_name.replace("Normal", "").rstrip(".").lower()
                    
                    # Parse the sheet
                    df = pd.read_excel(xls, sheet_name=sheet_name)
                    
                    # Convert to list of dicts (replace NaN with empty string)
                    records = df.fillna("").to_dict('records')
                    
                    # Inject character name into each record for reverse lookup context
                    for r in records: r['char_name'] = char_name.capitalize()
                    
                    FRAME_DATA[char_name] = records
                    # print(f"Loaded {len(records)} moves for {char_name}")
                
                # Look for sheets ending in "Stats" (e.g. "ManonStats", "RyuStats")
                elif sheet_name.endswith("Stats") and not sheet_name.startswith("_OLD"):
                    char_name = sheet_name.replace("Stats", "").rstrip(".").lower()
                    df = pd.read_excel(xls, sheet_name=sheet_name)
                
                    stats_dict = dict(zip(df['name'], df['stat']))
                    FRAME_STATS[char_name] = stats_dict
                    # print(f"Loaded stats for {char_name}")

            def normalize_loader_move_key(move_name, num_cmd):
                normalized_name = re.sub(r"[^a-z0-9]+", "", str(move_name or "").lower())
                normalized_num_cmd = re.sub(r"\([^)]*\)", "", str(num_cmd or "").lower())
                normalized_num_cmd = re.sub(r"\s+", "", normalized_num_cmd)
                normalized_num_cmd = re.sub(r"[^a-z0-9>]", "", normalized_num_cmd)
                return normalized_name, normalized_num_cmd

            # Jamie's drink-gated moves live on the drink-level sheets rather than JamieNormal.
            # Merge unique rows so parser/lookup sees the full ODS moveset from one character key.
            if "jamie" in FRAME_DATA:
                jamie_extra_sheets = [
                    name for name in xls.sheet_names
                    if re.fullmatch(r"JamieD[1-4]", str(name or ""), re.IGNORECASE)
                ]
                existing_jamie_keys = {
                    normalize_loader_move_key(row.get("moveName", ""), row.get("numCmd", ""))
                    for row in FRAME_DATA["jamie"]
                    if str(row.get("moveName", "")).strip() and str(row.get("numCmd", "")).strip()
                }
                for sheet_name in sorted(jamie_extra_sheets, key=str.lower):
                    df = pd.read_excel(xls, sheet_name=sheet_name)
                    records = df.fillna("").to_dict("records")
                    for row in records:
                        move_name = str(row.get("moveName", "")).strip()
                        num_cmd = str(row.get("numCmd", "")).strip()
                        if not move_name or not num_cmd:
                            continue
                        row_key = normalize_loader_move_key(move_name, num_cmd)
                        if row_key in existing_jamie_keys:
                            continue
                        row["char_name"] = "Jamie"
                        FRAME_DATA["jamie"].append(row)
                        existing_jamie_keys.add(row_key)
            
            print(f"Total characters loaded: {len(FRAME_DATA)}")
            print(f"Total stats loaded: {len(FRAME_STATS)}")
            
            BNB_DATA = {}
            OKI_DATA = {}
            CHARACTER_INFO = {}
            HITBOX_GIF_DATA = {}
            RANGE_DATA = {}
            normalized_chars = {
                normalize_char_name(name): name
                for name in FRAME_DATA.keys()
            }

            character_lookup = dict(normalized_chars)
            for alias, canonical in CHARACTER_ALIASES.items():
                if canonical in FRAME_DATA:
                    character_lookup[normalize_char_name(alias)] = canonical
                    character_lookup[normalize_char_name(canonical)] = canonical

            def normalize_range_cmd_token(value):
                raw_text = str(value or "").lower()
                is_air_context = bool(
                    "(air" in raw_text
                    or raw_text.startswith("j.")
                    or raw_text.startswith("j ")
                    or raw_text.startswith("j")
                    or "jump" in raw_text
                )
                text = raw_text
                text = text.replace("->", ">")
                text = text.replace("~", ">")
                text = text.replace("|", "/")
                text = re.sub(r"\bor\b", "/", text)
                text = re.sub(r"\([^)]*\)", "", text)
                text = re.sub(r"\s+", "", text)
                text = re.sub(r"[^a-z0-9>/+]", "", text)
                text = text.replace("+", "")
                text = re.sub(r"^j42684268", "j720", text)
                text = re.sub(r"^42684268", "720", text)
                text = re.sub(r"^j4268", "j360", text)
                text = re.sub(r"^4268", "360", text)
                if is_air_context and re.match(r"^(360|720)", text):
                    text = f"j{text}"
                return text

            def build_range_cmd_tokens(value):
                normalized = normalize_range_cmd_token(value)
                if not normalized:
                    return []
                tokens = []
                for part in normalized.split("/"):
                    token = part.strip()
                    if not token:
                        continue
                    if token not in tokens:
                        tokens.append(token)
                    if token.startswith("5") and len(token) > 1:
                        token_without_five = token[1:]
                        if token_without_five and token_without_five not in tokens:
                            tokens.append(token_without_five)
                return tokens

            def choose_preferred_range(values):
                cleaned_values = [str(value).strip() for value in values if str(value).strip()]
                if not cleaned_values:
                    return ""
                for value in cleaned_values:
                    if not is_missing_attack_range_value(value):
                        return value
                return ""

            range_sheet_name = next(
                (name for name in xls.sheet_names if name.lower() in {"range", "ranges"}),
                None,
            )
            if range_sheet_name:
                range_df = pd.read_excel(xls, sheet_name=range_sheet_name, dtype=str).fillna("")
                for range_row in range_df.to_dict("records"):
                    char_raw = str(range_row.get("chara", "")).strip()
                    input_raw = str(range_row.get("input", "")).strip()
                    atk_range_raw = str(range_row.get("atkRange", "")).strip()
                    if not char_raw or not input_raw:
                        continue
                    char_key = character_lookup.get(normalize_char_name(char_raw))
                    if not char_key:
                        continue
                    for token in build_range_cmd_tokens(input_raw):
                        RANGE_DATA.setdefault(char_key, {}).setdefault(token, []).append(atk_range_raw)
            else:
                print("Range sheet not found: ranges")

            for char_key, records in FRAME_DATA.items():
                char_ranges = RANGE_DATA.get(char_key, {})
                for row in records:
                    row_tokens = []
                    for token in build_range_cmd_tokens(row.get("numCmd", "")):
                        if token not in row_tokens:
                            row_tokens.append(token)
                    for token in build_num_cmd_candidates_for_gif(row):
                        for variant in build_range_cmd_tokens(token):
                            if variant not in row_tokens:
                                row_tokens.append(variant)

                    selected_range = ""
                    for token in row_tokens:
                        if token not in char_ranges:
                            continue
                        selected_range = choose_preferred_range(char_ranges[token])
                        if selected_range:
                            break
                    row["atkRange"] = selected_range

            configure_extracted_modules()
            HITBOX_GIF_DATA = load_local_hitbox_gif_data(character_lookup)
            configure_extracted_modules()

            combo_sheets = [
                name for name in xls.sheet_names
                if name.lower().endswith(" combos")
            ]
            oki_sheets = [
                name for name in xls.sheet_names
                if name.lower().endswith(" okisetups")
                or name.lower().endswith(" setupsoki")
            ]

            for sheet_name in combo_sheets:
                char_label = sheet_name[:-len(" combos")]
                char_key = normalized_chars.get(normalize_char_name(char_label))
                if not char_key:
                    continue
                df = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=str)
                combo_text = format_sheet_text(df)
                if combo_text:
                    BNB_DATA[char_key] = combo_text

            for sheet_name in oki_sheets:
                suffix = " okisetups" if sheet_name.lower().endswith(" okisetups") else " setupsoki"
                char_label = sheet_name[:-len(suffix)]
                char_key = normalized_chars.get(normalize_char_name(char_label))
                if not char_key:
                    continue
                df = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=str)
                oki_text = format_sheet_text(df)
                if oki_text:
                    OKI_DATA[char_key] = oki_text

            for sheet_name in xls.sheet_names:
                lower_name = sheet_name.lower()
                if lower_name.endswith(" combos"):
                    continue
                if lower_name.endswith(" okisetups") or lower_name.endswith(" setupsoki"):
                    continue
                if lower_name.endswith(" frame data"):
                    continue
                normalized_name = normalize_char_name(sheet_name)
                char_key = normalized_chars.get(normalized_name)
                if not char_key:
                    continue
                df = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=str)
                info_text = format_sheet_text(df)
                if info_text:
                    CHARACTER_INFO[char_key] = info_text

            print(f"Total combo sheets loaded: {len(BNB_DATA)} characters")
            print(f"Total oki sheets loaded: {len(OKI_DATA)} characters")
            print(f"Total character info sheets loaded: {len(CHARACTER_INFO)} characters")
            total_hitbox_gifs = sum(len(entries) for entries in HITBOX_GIF_DATA.values())
            total_ranges = sum(len(entries) for entries in RANGE_DATA.values())
            print(f"Total hitbox gif links loaded: {total_hitbox_gifs}")
            print(f"Total range inputs loaded: {total_ranges}")
            quiz_module.configure(
                FRAME_DATA=FRAME_DATA,
                CHARACTER_ALIASES=CHARACTER_ALIASES,
                resolve_character_key=resolve_character_key,
                normalize_char_name=normalize_char_name,
                lookup_frame_data=lookup_frame_data,
                find_moves_in_text=find_moves_in_text,
                is_missing_attack_range_value=is_missing_attack_range_value,
                clean_embed_value=frame_output_module.clean_embed_value,
                truncate_embed_value=frame_output_module.truncate_embed_value,
                build_frame_embed=frame_output_module.build_frame_embed,
                strip_discord_mentions=strip_discord_mentions,
            )
            
        except Exception as e:
            print(f"Error loading {filename}: {e}")
    else:
        print(f"File not found: {filename}")

def find_moves_in_text(text):
    """Extract character/move mentions and return context payload with mode."""
    found_data = []
    text_lower = strip_discord_mentions(text).lower()
    text_lower = normalize_jump_normal_text(text_lower)
    text_lower = re.sub(r"\bdivekick\b", "dive kick", text_lower)
    tc_prompt_blocks = []
    special_prompt_blocks = []
    tc_ambiguous_inputs = set()
    text_tokens = word_tokens(text_lower)

    def tokens_in_haystack(haystack_tokens, needle_tokens):
        return contains_token_sequence(haystack_tokens, needle_tokens)

    def tokens_in_text(needle_tokens):
        return tokens_in_haystack(text_tokens, needle_tokens)
    
    # 1. Identify which characters are mentioned
    mentioned_chars = []
    
    # First check for character aliases and normalize them
    for alias, canonical in CHARACTER_ALIASES.items():
        alias_tokens = word_tokens(alias)
        if tokens_in_text(alias_tokens):
            if canonical in FRAME_DATA and canonical not in mentioned_chars:
                mentioned_chars.append(canonical)
    
    # Then check for direct character name matches
    for char in FRAME_DATA.keys():
        char_tokens = word_tokens(char)
        if tokens_in_text(char_tokens) and char not in mentioned_chars:
            mentioned_chars.append(char)

    if not mentioned_chars and (
        re.search(r"\braging\s+demon\b", text_lower)
        or re.search(r"\bshun\s+goku\s+satsu\b", text_lower)
    ):
        if "akuma" in FRAME_DATA:
            mentioned_chars.append("akuma")
    
    # Check for BNB/Combo requests
    bnb_keywords = ["combo", "combos", "bnb", "bnbs", "bread and butter", "route", "routes"]
    oki_keywords = ["oki", "okizeme", "setup", "setups", "meaty", "meaties"]
    info_keywords = [
        "playstyle",
        "gameplan",
        "archetype",
        "overview",
        "tell me about",
        "who is",
        "strengths",
        "weaknesses",
        "moveset",
        "toolkit",
        "role",
        "how to play",
        "character synopsis",
        "summary",
        "anti air",
        "anti-air",
        "neutral",
        "win condition",
    ]
    frame_keywords = [
        "frame data",
        "framedata",
        "startup",
        "start up",
        "recovery",
        "active",
        "on block",
        "on hit",
        "hitstun",
        "blockstun",
        "frames",
    ]
    gif_query = has_explicit_gif_lookup_intent(text_lower)
    startup_alias_query = bool(
        re.search(r"\bhow\s+fast\b", text_lower)
        or re.search(r"\bhow\s+quick\b", text_lower)
        or re.search(r"\bspeed\s+of\b", text_lower)
        or (
            re.search(r"\bfast\b", text_lower)
            and re.search(r"\b[1-9][0-9]*[a-zA-Z]{1,3}\b", text_lower)
        )
    )
    hitconfirm_alias_query = bool(
        re.search(r"\bhit\s*-?\s*confirm\b", text_lower)
        or re.search(r"\bhitconfirm\b", text_lower)
        or re.search(r"\bhc\b", text_lower)
        or re.search(r"\bconfirm\s+window\b", text_lower)
        or re.search(r"\bconfirm\s+timing\b", text_lower)
        or re.search(r"\bconfirmable\b", text_lower)
        or re.search(r"\bconfirm\b", text_lower)
    )
    super_gain_alias_query = bool(
        re.search(r"\bsuper\s*gain\b", text_lower)
        or re.search(r"\bsuper\s*meter\s*gain\b", text_lower)
        or re.search(r"\bmeter\s*gain\b", text_lower)
        or re.search(r"\bsuper\s*build\b", text_lower)
        or re.search(r"\bsa\s*gain\b", text_lower)
    )
    range_alias_query = bool(
        (
            re.search(r"\brange\b", text_lower)
            or re.search(r"\blength\b", text_lower)
        )
        and not re.search(r"\bin\s+range\b", text_lower)
    )
    property_alias_flags = {
        "startup": startup_alias_query
        or bool(re.search(r"\bstart\s*up\b|\bstartup\b", text_lower)),
        "active": bool(re.search(r"\bactive\b|\bactive\s+frames?\b", text_lower)),
        "recovery": bool(re.search(r"\brecovery\b", text_lower)),
        "on_hit": bool(re.search(r"\bon\s+hit\b", text_lower)),
        "on_block": bool(re.search(r"\bon\s+block\b|\bplus\s+on\s+block\b|\bminus\s+on\s+block\b", text_lower)),
        "cancel": bool(re.search(r"\bcancel(?:l?able)?\b", text_lower)),
        "damage": bool(re.search(r"\bdamage\b|\bdmg\b", text_lower)),
        "drive_chip": bool(re.search(r"\bdrive\s+chip\b|\bdrive\s+dmg\b|\bdrive\s+damage\b", text_lower)),
        "drive_gain": bool(re.search(r"\bdrive\s+gain\b", text_lower)),
        "stun": bool(re.search(r"\bhitstun\b|\bblockstun\b|\bstun\b", text_lower)),
        "hitconfirm": hitconfirm_alias_query,
        "super_gain": super_gain_alias_query,
        "range": range_alias_query,
    }
    property_match_count = sum(1 for matched in property_alias_flags.values() if matched)
    table_intent_query = bool(
        re.search(r"\ball\s+frames?\b", text_lower)
        or re.search(r"\bfull\s+frames?\b", text_lower)
        or re.search(r"\bfull\s+frame\s*data\b", text_lower)
        or re.search(r"\btable\b", text_lower)
    )
    property_only_query = bool(property_match_count == 1 and not table_intent_query)
    comparison_keywords = [
        "which is better",
        "which is faster",
        "compare",
        "comparison",
        "versus",
    ]
    punish_keywords = ["punish", "punishable", "can i punish", "is it punishable"]
    target_combo_query = bool(re.search(r"\b(tc|target\s+combo|targetcombo)\b", text_lower))
    special_grab_query = bool(re.search(r"\b(command\s+grab|spd|piledriver|typhoon)\b", text_lower))
    wants_bnb = any(kw in text_lower for kw in bnb_keywords) and not target_combo_query
    wants_oki = any(kw in text_lower for kw in oki_keywords)
    wants_info = any(kw in text_lower for kw in info_keywords)
    wants_comparison = (
        any(kw in text_lower for kw in comparison_keywords)
        or re.search(r"\bvs\b", text_lower)
        or (len(mentioned_chars) >= 2 and re.search(r"\band\b", text_lower))
    )
    wants_frame_data = (
        any(kw in text_lower for kw in frame_keywords)
        or any(kw in text_lower for kw in punish_keywords)
        or wants_comparison
        or startup_alias_query
        or hitconfirm_alias_query
        or super_gain_alias_query
        or range_alias_query
        or target_combo_query
        or gif_query
    )
    bnb_context = ""
    info_blocks = []
    if wants_bnb or wants_oki:
        for char in mentioned_chars:
            if wants_bnb and char in BNB_DATA:
                bnb_context += f"\n\n**{char.capitalize()} Combos:**\n{BNB_DATA[char]}"
            if (wants_bnb or wants_oki) and char in OKI_DATA:
                bnb_context += f"\n\n**{char.capitalize()} Oki/Setups:**\n{OKI_DATA[char]}"
    results = []
    tc_selected_combos = set()
    tc_base_tokens = set()
    query_has_explicit_strength = False
    explicit_move_attempt = False
    missing_scrolls_query = False
    comparison_char_inputs = {}
    if wants_frame_data:
        # 2. Heuristic: For each mentioned character, search for moves mentioned nearby?
        # Simpler approach: Check if any move inputs are present in the text
        # that map to these characters.

        query_requires_denjin = "denjin" in text_tokens
        query_requires_charged = any(token in text_tokens for token in ("charged", "hold", "held"))
        query_requests_sa1 = bool(
            re.search(r"\b(?:sa\s*1|super\s*art\s*1|super\s*1|level\s*1)\b", text_lower)
        )
        query_requests_sa2 = bool(
            re.search(r"\b(?:sa\s*2|super\s*art\s*2|super\s*2|level\s*2)\b", text_lower)
        )
        query_requests_sa3 = bool(
            re.search(r"\b(?:sa\s*3|super\s*art\s*3|super\s*3|level\s*3)\b", text_lower)
        )
        query_requests_ca = bool(
            re.search(r"\b(?:ca|critical\s+art)\b", text_lower)
        )
        stock_hint_tokens = ("stock", "stocked", "enhanced", "windclad")

        def token_is_stock_hint(token):
            token_norm = str(token or "").lower().strip()
            if not token_norm:
                return False
            if token_norm in stock_hint_tokens:
                return True
            return any(
                difflib.SequenceMatcher(None, token_norm, hint_token).ratio() >= 0.82
                for hint_token in stock_hint_tokens
            )

        query_requires_stocked = any(
            token in text_tokens for token in ("stock", "stocked", "enhanced", "windclad")
        ) or bool(re.search(r"\bwind\s+clad\b", text_lower)) or any(
            token_is_stock_hint(token) for token in text_tokens
        )

        def row_is_denjin_variant(row):
            move_name = str(row.get("moveName", "")).lower()
            cmn_name = str(row.get("cmnName", "")).lower()
            num_cmd = str(row.get("numCmd", "")).lower()
            return (
                "denjin" in move_name
                or "denjin" in cmn_name
                or "charged" in move_name
                or "charged" in cmn_name
                or "(charged)" in num_cmd
            )

        def row_is_charged_variant(row):
            move_name = str(row.get("moveName", "")).lower()
            cmn_name = str(row.get("cmnName", "")).lower()
            num_cmd = str(row.get("numCmd", "")).lower()
            return (
                "charged" in move_name
                or "charged" in cmn_name
                or "hold" in move_name
                or "hold" in cmn_name
                or "(charged" in num_cmd
                or "(hold" in num_cmd
            )

        def row_is_od_variant(row):
            move_name = str(row.get("moveName", "")).lower().strip()
            cmn_name = str(row.get("cmnName", "")).lower().strip()
            num_cmd_compact = re.sub(r"[^a-z0-9]", "", str(row.get("numCmd", "")).lower())
            return (
                move_name.startswith(("od ", "ex "))
                or cmn_name.startswith(("od ", "ex "))
                or num_cmd_compact.endswith(("pp", "kk"))
            )

        def row_matches_explicit_strength(row, strength_query_text):
            row_move_name = str(row.get("moveName", "")).lower().strip()
            row_cmn_name = str(row.get("cmnName", "")).lower().strip()
            row_num_cmd = str(row.get("numCmd", "")).lower().strip()
            row_num_cmd_compact = re.sub(r"[^a-z0-9]", "", row_num_cmd)

            if re.search(r"\b(?:od|ex)\b", strength_query_text):
                return row_is_od_variant(row)

            strength_groups = [
                ({"light", "l", "lp", "lk"}, {"lp", "lk"}),
                ({"medium", "m", "mp", "mk"}, {"mp", "mk"}),
                ({"heavy", "h", "hp", "hk"}, {"hp", "hk"}),
            ]

            requested_suffixes = set()
            for token_group, suffixes in strength_groups:
                if any(re.search(rf"\b{re.escape(token)}\b", strength_query_text) for token in token_group):
                    requested_suffixes.update(suffixes)

            if not requested_suffixes:
                return False

            if any(row_move_name.startswith(f"{suffix} ") or row_cmn_name.startswith(f"{suffix} ") for suffix in requested_suffixes):
                return True
            if any(
                row_move_name.startswith(f"{word} ") or row_cmn_name.startswith(f"{word} ")
                for word in ("light", "medium", "heavy")
                if word[0] in {suffix[0] for suffix in requested_suffixes}
            ):
                return True
            return row_num_cmd_compact.endswith(tuple(requested_suffixes))

        def row_matches_query_move_terms(row):
            ignored_tokens = {
                "framedata", "frame", "frames", "data", "gif", "gifs", "hitbox", "hitboxes",
                "light", "medium", "heavy", "l", "m", "h",
                "lp", "mp", "hp", "lk", "mk", "hk", "pp", "kk",
                "od", "ex", "charged", "hold", "held",
                "startup", "active", "recovery", "range",
                "on", "hit", "block", "damage", "cancel",
            }
            for char in mentioned_chars:
                ignored_tokens.update(re.findall(r"[a-z0-9]+", str(char).lower()))
            for alias, canonical in CHARACTER_ALIASES.items():
                if canonical in mentioned_chars:
                    ignored_tokens.update(re.findall(r"[a-z0-9]+", str(alias).lower()))

            significant_tokens = [
                token for token in text_tokens
                if token not in ignored_tokens and len(token) >= 3
            ]
            if not significant_tokens:
                return True

            row_text = " ".join(
                str(row.get(field, "")).lower()
                for field in ("moveName", "cmnName", "numCmd", "plnCmd")
            )
            row_text_compact = re.sub(r"[^a-z0-9]", "", row_text)
            for token in significant_tokens:
                token_compact = re.sub(r"[^a-z0-9]", "", token)
                if not token_compact:
                    continue
                if token in row_text or token_compact in row_text_compact:
                    continue
                return False
            return True

        def row_is_ca_variant(row):
            move_name = str(row.get("moveName", "")).lower()
            cmn_name = str(row.get("cmnName", "")).lower()
            num_cmd = str(row.get("numCmd", "")).lower()
            return (
                "critical art" in move_name
                or "critical art" in cmn_name
                or bool(re.search(r"\(\s*ca\s*\)", num_cmd))
            )

        def row_is_stocked_variant(row):
            move_name = str(row.get("moveName", "")).lower()
            cmn_name = str(row.get("cmnName", "")).lower()
            num_cmd = str(row.get("numCmd", "")).lower()
            combined = f"{move_name} {cmn_name} {num_cmd}"
            if re.search(r"\b0\s*stocks?\b", combined):
                return False

            has_stock_count = bool(re.search(r"\b[1-9]\d*\s*stocks?\b", combined))
            has_stock_tag = "(stock" in move_name or "(stock" in cmn_name or "(stock" in num_cmd
            has_enhanced_tag = (
                "enhanced" in move_name
                or "enhanced" in cmn_name
                or "(enhanced" in num_cmd
            )
            has_windclad_tag = "windclad" in move_name or "windclad" in cmn_name
            has_wind_stock_hold = "wind stock" in cmn_name and (
                "(" in cmn_name or "(hold" in num_cmd
            )
            return (
                has_stock_count
                or has_stock_tag
                or has_enhanced_tag
                or has_windclad_tag
                or has_wind_stock_hold
            )

    
        move_regex = r"\b([1-9][0-9]*[a-zA-Z]+|stand\s+[a-zA-Z]+|crouch\s+[a-zA-Z]+|(?:neutral\s+|n\s+)?jump\s+[a-zA-Z]+|(?:neutral\s+|n\s+)?jump\s+[1-9][0-9]*[a-zA-Z]+|(?:neutral\s+|n\s+)?j(?:\s+|\.)[a-zA-Z]+|(?:neutral\s+|n\s+)?j(?:\s+|\.)[1-9][0-9]*[a-zA-Z]+|(?:neutral\s+|n\s+)?j\.?[1-9][0-9]*[a-zA-Z]+|(?:lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\s+[a-zA-Z]+(?:\s+[a-zA-Z]+)?|[a-zA-Z]+\s+kick|[a-zA-Z]+\s+punch)\b"
        potential_inputs = re.findall(move_regex, text_lower)
        compact_motion_inputs = []
        motion_button_matches = re.findall(
            r"\b([1-9][0-9]{1,4})\s*(?:\+)?\s*(lp|mp|hp|lk|mk|hk|pp|kk|p|k)\b",
            text_lower,
        )
        for motion_digits, button_suffix in motion_button_matches:
            compact_motion = f"{motion_digits}{button_suffix}"
            if compact_motion not in compact_motion_inputs:
                compact_motion_inputs.append(compact_motion)

        boomer_normal_matches = re.findall(
            r"\b(st|cr)\s*\.?\s*(lp|mp|hp|lk|mk|hk|l\s*p|m\s*p|h\s*p|l\s*k|m\s*k|h\s*k)\b",
            text_lower,
        )
        for stance_token, button_token in boomer_normal_matches:
            stance_prefix = "5" if stance_token == "st" else "2"
            normalized_button = re.sub(r"\s+", "", button_token)
            compact_motion = f"{stance_prefix}{normalized_button}"
            if compact_motion not in compact_motion_inputs:
                compact_motion_inputs.append(compact_motion)

        if compact_motion_inputs:
            potential_inputs = compact_motion_inputs + potential_inputs
        strength_prefix_pattern = re.compile(r"^(lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b")
        strength_prefixes_for_filter = [
            "lp", "mp", "hp", "lk", "mk", "hk",
            "light", "medium", "heavy", "l", "m", "h",
        ]
        filtered_inputs = []
        for inp in potential_inputs:
            if not inp:
                continue
            original_inp = str(inp).strip().lower()
            cleaned_inp = re.sub(r"\s+framedata$", "", inp).strip()
            cleaned_inp = re.sub(r"\s+frame\s*data$", "", cleaned_inp).strip()
            cleaned_inp = re.sub(r"\s+frame$", "", cleaned_inp).strip()
            cleaned_inp = re.sub(
                r"\s+(?:gif|gifs|hitbox|hitboxes)(?:\s+link)?$",
                "",
                cleaned_inp,
            ).strip()
            if not cleaned_inp:
                continue
            if cleaned_inp in strength_prefixes_for_filter and re.search(
                r"\b(frame\s*data|framedata|frame|data|gif|gifs|hitbox|hitboxes|startup|recovery|active|stats|punish|punishable)\b",
                original_inp,
            ):
                continue
            if not strength_prefix_pattern.match(cleaned_inp):
                if any(
                    re.search(
                        rf"\b{re.escape(prefix)}\s+{re.escape(cleaned_inp)}\b",
                        text_lower,
                    )
                    for prefix in strength_prefixes_for_filter
                ):
                    continue
            filtered_inputs.append(cleaned_inp)
        potential_inputs = filtered_inputs
        extra_inputs = []
        query_strength_tokens = {
            "lp", "mp", "hp", "lk", "mk", "hk",
            "light", "medium", "heavy", "l", "m", "h",
            "od", "ex",
        }
        compact_strength_motion_present = bool(
            re.search(
                r"\b(?:lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\s*(?:dp|srk|shoryu|shoryuken)\b"
                r"|\b(?:dp|srk|shoryu|shoryuken)\s*(?:lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b",
                text_lower,
            )
        )
        compact_od_motion_present = bool(
            re.search(
                r"\b(?:od|ex)\s*(?:dp|srk|shoryu|shoryuken)\b"
                r"|\b(?:dp|srk|shoryu|shoryuken)\s*(?:od|ex)\b",
                text_lower,
            )
        )
        compact_num_cmd_strength_present = bool(
            re.search(
                r"\b(?:j\.?\s*)?[1-9][0-9]{1,5}\s*(?:\+)?\s*(?:lp|mp|hp|lk|mk|hk|pp|kk)\b",
                text_lower,
            )
        )
        query_has_explicit_strength = bool(
            any(token in query_strength_tokens for token in text_tokens)
            or compact_strength_motion_present
            or compact_od_motion_present
            or compact_num_cmd_strength_present
        )
        query_wants_od_strength = bool(re.search(r"\b(od|ex)\b", text_lower))
        query_wants_non_od_strength = bool(
            re.search(r"\b(lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b", text_lower)
        )
        akuma_followup_alias = None
        deejay_sway_followup_alias = None
        ken_jinrai_followup_alias = None
        jamie_drink_alias = None
        query_requests_air_context = bool(re.search(r"\b(?:air|aerial)\b", text_lower))
        air_fireball_context = bool(
            re.search(
                r"\b(?:air|aerial)\s+fireball\b|\bair\s+hadoken\b",
                text_lower,
            )
        )
        air_sa1_context = bool(
            re.search(
                r"\b(?:air|aerial)\s*(?:sa\s*1|super\s*art\s*1|super\s*1|level\s*1)\b"
                r"|\b(?:sa\s*1|super\s*art\s*1|super\s*1|level\s*1)\s*(?:air|aerial)\b",
                text_lower,
            )
        )
        air_sa2_context = bool(
            re.search(
                r"\b(?:air|aerial)\s*(?:sa\s*2|super\s*art\s*2|super\s*2|level\s*2)\b"
                r"|\b(?:sa\s*2|super\s*art\s*2|super\s*2|level\s*2)\s*(?:air|aerial)\b",
                text_lower,
            )
        )
        zangief_borscht_context = bool(
            re.search(r"\bborscht\b", text_lower)
            or re.search(r"\bj\.?\s*360\s*\+?\s*k{1,2}\b", text_lower)
            or re.search(r"\bj\s+360\s*\+?\s*k{1,2}\b", text_lower)
        )
        alex_stance_followup_context = bool(
            re.search(
                r"\bstance\s+(?:lp|mp|hp|lk|mk|hk|6p|6|4|lplk|5lplk|2lplk|"
                r"jab|shoulder|lariat|hop|stomp|throw|command\s+grab|hk\s+hk)\b",
                text_lower,
            )
        )
        air_sa3_context = bool(
            re.search(
                r"\b(?:air|aerial)\s*(?:sa\s*3|super\s*art\s*3|super\s*3|level\s*3|critical\s+art|ca)\b"
                r"|\b(?:sa\s*3|super\s*art\s*3|super\s*3|level\s*3|critical\s+art|ca)\s*(?:air|aerial)\b",
                text_lower,
            )
        )
        air_tatsu_context = bool(
            re.search(
                r"\b(?:air|aerial)\s+tatsu\b|\b(?:air|aerial)\s+tatsumaki\b|\btatsu\s*\(air\)\b|\bj\.?\s*214k\b",
                text_lower,
            )
        )
        ken_run_followup_context = bool(
            "ken" in mentioned_chars
            and re.search(r"\brun\s+(?:dp|shoryu|shoryuken|tatsu|dragonlash|dragon\s+lash|lash)\b", text_lower)
        )

        if "ken" in mentioned_chars:
            if re.search(
                r"\b(?:(?:od|ex)\s+)?(?:jinrai|236k)\s*(?:>\s*)?(?:low|lk|6lk)\b"
                r"|\b(?:low|lk|6lk)\s+(?:(?:od|ex)\s+)?jinrai\b",
                text_lower,
            ):
                ken_jinrai_followup_alias = "od jinrai low" if query_wants_od_strength else "jinrai low"
            elif re.search(
                r"\b(?:(?:od|ex)\s+)?(?:jinrai|236k)\s*(?:>\s*)?(?:overhead|mk|6mk)\b"
                r"|\b(?:overhead|mk|6mk)\s+(?:(?:od|ex)\s+)?jinrai\b",
                text_lower,
            ):
                ken_jinrai_followup_alias = "od jinrai overhead" if query_wants_od_strength else "jinrai overhead"
            elif re.search(
                r"\b(?:(?:od|ex)\s+)?(?:jinrai|236k)\s*(?:>\s*)?(?:heavy|launcher|hk|6hk)\b"
                r"|\b(?:heavy|launcher|hk|6hk)\s+(?:(?:od|ex)\s+)?jinrai\b",
                text_lower,
            ):
                ken_jinrai_followup_alias = "od jinrai hk" if query_wants_od_strength else "jinrai hk"

            ken_run_alias_tokens = [
                (r"\brun\s+stop\b", "emergency stop"),
                (r"\brun\s+overhead\b", "thunder kick"),
                (r"\brun\s+step\s*kick\b", "forward step kick"),
                (r"\brun\s+step\b", "forward step kick"),
                (r"\brun\s+(?:dp|shoryu|shoryuken)\b", "run > shoryuken"),
                (r"\brun\s+tatsu\b", "run > tatsumaki senpukyaku"),
                (r"\brun\s+(?:dragonlash|dragon\s+lash|lash)\b", "run > dragonlash"),
            ]  # Random parser note: Ken really does have a follow-up for everything.
            for pattern, alias_token in ken_run_alias_tokens:
                if re.search(pattern, text_lower) and alias_token not in extra_inputs:
                    extra_inputs.append(alias_token)
            if not ken_run_followup_context:
                ken_lash_alias_tokens = [
                    (r"\b(?:od|ex)\s+(?:dragonlash|dragon\s+lash|lash)\b", "od lash"),
                    (r"\b(?:l|light|lk)\s+(?:dragonlash|dragon\s+lash|lash)\b", "l lash"),
                    (r"\b(?:m|medium|mk)\s+(?:dragonlash|dragon\s+lash|lash)\b", "m lash"),
                    (r"\b(?:h|heavy|hk)\s+(?:dragonlash|dragon\s+lash|lash)\b", "h lash"),
                    (r"\b(?:dragonlash|dragon\s+lash|lash)\b", "lash"),
                ]
                selected_lash_alias = None
                for pattern, alias_token in ken_lash_alias_tokens:
                    if re.search(pattern, text_lower):
                        selected_lash_alias = alias_token
                        break
                if selected_lash_alias and selected_lash_alias not in extra_inputs:
                    extra_inputs.append(selected_lash_alias)
            if ken_jinrai_followup_alias and ken_jinrai_followup_alias not in extra_inputs:
                extra_inputs.insert(0, ken_jinrai_followup_alias)
            if re.search(r"\brun\b", text_lower) and not re.search(
                r"\brun\s+(?:stop|overhead|step|dp|shoryu|shoryuken|tatsu|dragonlash|dragon\s+lash|lash)\b",
                text_lower,
            ):
                if "quick dash" not in extra_inputs:
                    extra_inputs.append("quick dash")

        if "mai" in mentioned_chars:
            mai_fan_aliases = [
                (r"\b(?:od|ex)\s+(?:stocked|stock)\s+(?:hold|held|charged)\s+fan\b", "od stocked hold fan"),
                (r"\b(?:stocked|stock)\s+(?:od|ex)\s+(?:hold|held|charged)\s+fan\b", "od stocked hold fan"),
                (r"\b(?:stocked|stock)\s+(?:hold|held|charged)\s+fan\b", "stocked hold fan"),
                (r"\b(?:od|ex)\s+(?:hold|held|charged)\s+fan\b", "od hold fan"),
                (r"\b(?:hold|held|charged)\s+fan\b", "hold fan"),
                (r"\b(?:od|ex)\s+(?:stocked|stock)\s+fan\b", "od stocked fan"),
                (r"\b(?:stocked|stock)\s+(?:od|ex)\s+fan\b", "od stocked fan"),
                (r"\b(?:stocked|stock)\s+fan\b", "stocked fan"),
                (r"\b(?:od|ex)\s+fan\b", "od fan"),
                (r"\b(?:l|light|lp)\s+fan\b", "l fan"),
                (r"\b(?:m|medium|mp)\s+fan\b", "m fan"),
                (r"\b(?:h|heavy|hp)\s+fan\b", "h fan"),
                (r"\bfan\b", "fan"),
            ]
            for pattern, alias_token in mai_fan_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break
            if air_sa2_context and "air sa2" not in extra_inputs:
                extra_inputs.append("air sa2")

        if "jamie" in mentioned_chars:
            if re.search(
                r"\b(?:drink|dr\s*4)\s+activation\b|\blevel\s*4\s+activation\b|\bactivation\s+drink\b",
                text_lower,
            ):
                jamie_drink_alias = "drink activation"
            elif re.search(r"\b(?:drink\s*(?:level\s*)?4|level\s*4\s*drink|4\s*drinks?|four\s+drinks?)\b", text_lower):
                jamie_drink_alias = "drink level 4"
            elif re.search(r"\b(?:drink\s*(?:level\s*)?3|level\s*3\s*drink|3\s*drinks?|three\s+drinks?)\b", text_lower):
                jamie_drink_alias = "drink level 3"
            elif re.search(r"\b(?:drink\s*(?:level\s*)?2|level\s*2\s*drink|2\s*drinks?|two\s+drinks?)\b", text_lower):
                jamie_drink_alias = "drink level 2"
            elif re.search(r"\b(?:drink\s*(?:level\s*)?1|level\s*1\s*drink|1\s*drink|one\s+drink)\b", text_lower):
                jamie_drink_alias = "drink level 1"
            elif re.search(r"\bdrink\b", text_lower):
                jamie_drink_alias = "drink"

            if jamie_drink_alias and jamie_drink_alias not in extra_inputs:
                extra_inputs.insert(0, jamie_drink_alias)

            jamie_palm_aliases = [
                (r"\b(?:od|ex)\s+(?:palm|swagger(?:\s+step)?)\b", "od palm"),
                (r"\b(?:l|light|lp)\s+(?:palm|swagger(?:\s+step)?)\b", "lp palm"),
                (r"\b(?:m|medium|mp)\s+(?:palm|swagger(?:\s+step)?)\b", "mp palm"),
                (r"\b(?:h|heavy|hp)\s+(?:palm|swagger(?:\s+step)?)\b", "hp palm"),
                (r"\b(?:palm|swagger(?:\s+step)?)\b", "palm"),
            ]
            for pattern, alias_token in jamie_palm_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

            jamie_rekka_aliases = [
                (r"\b(?:od|ex)\s+(?:rekka|freeflow(?:\s+strikes)?)\b", "od rekka"),
                (r"\b(?:l|light|lp)\s+(?:rekka|freeflow(?:\s+strikes)?)\b", "lp rekka"),
                (r"\b(?:m|medium|mp)\s+(?:rekka|freeflow(?:\s+strikes)?)\b", "mp rekka"),
                (r"\b(?:h|heavy|hp)\s+(?:rekka|freeflow(?:\s+strikes)?)\b", "hp rekka"),
                (r"\b(?:rekka|freeflow(?:\s+strikes)?)\b", "rekka"),
            ]
            for pattern, alias_token in jamie_rekka_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

            jamie_arrow_aliases = [
                (r"\b(?:od|ex)\s+(?:arrow\s+kick|up\s*kicks?|upkicks?)\b", "od arrow kick"),
                (r"\b(?:l|light|lk)\s+(?:arrow\s+kick|up\s*kicks?|upkicks?)\b", "l arrow kick"),
                (r"\b(?:m|medium|mk)\s+(?:arrow\s+kick|up\s*kicks?|upkicks?)\b", "m arrow kick"),
                (r"\b(?:h|heavy|hk)\s+(?:arrow\s+kick|up\s*kicks?|upkicks?)\b", "h arrow kick"),
                (r"\b(?:arrow\s+kick|up\s*kicks?|upkicks?)\b", "arrow kick"),
            ]
            for pattern, alias_token in jamie_arrow_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

            jamie_bakkai_aliases = [
                (r"\b(?:od|ex)\s+(?:bakkai|break\s*dance)\b|\b236kk\b", "od bakkai"),
                (r"\b(?:l|light|lk)\s+(?:bakkai|break\s*dance)\b|\b236lk\b", "lk bakkai"),
                (r"\b(?:m|medium|mk)\s+(?:bakkai|break\s*dance)\b|\b236mk\b", "mk bakkai"),
                (r"\b(?:h|heavy|hk)\s+(?:bakkai|break\s*dance)\b|\b236hk\b", "hk bakkai"),
                (r"\b(?:bakkai|break\s*dance)\b|\b236k\b", "bakkai"),
            ]
            for pattern, alias_token in jamie_bakkai_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

            jamie_divekick_aliases = [
                (
                    r"\b(?:od|ex)\s+(?:luminous\s+)?dive\s+kick\b|\b(?:od|ex)\s+divekick\b|\b214kk\b|\bj\.?214kk\b",
                    "od dive kick",
                ),
                (
                    r"\b(?:l|light|lk)\s+(?:luminous\s+)?dive\s+kick\b|\b(?:l|light|lk)\s+divekick\b|\b214lk\b|\bj\.?214lk\b",
                    "dive kick",
                ),
                (
                    r"\b(?:m|medium|mk)\s+(?:luminous\s+)?dive\s+kick\b|\b(?:m|medium|mk)\s+divekick\b|\b214mk\b|\bj\.?214mk\b",
                    "dive kick",
                ),
                (
                    r"\b(?:h|heavy|hk)\s+(?:luminous\s+)?dive\s+kick\b|\b(?:h|heavy|hk)\s+divekick\b|\b214hk\b|\bj\.?214hk\b",
                    "dive kick",
                ),
                (
                    r"\b(?:luminous\s+)?dive\s+kick\b|\bdivekick\b|\b214k\b|\bj\.?214k\b",
                    "dive kick",
                ),
            ]
            for pattern, alias_token in jamie_divekick_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

            jamie_tenshin_aliases = [
                (r"\b(?:od|ex)\s+(?:tenshin|command\s+grab)\b", "od tenshin"),
                (r"\b(?:tenshin|command\s+grab)\b", "tenshin"),
            ]
            for pattern, alias_token in jamie_tenshin_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

            jamie_hermit_aliases = [
                (
                    r"\b(?:od|ex)\s+(?:swagger\s+hermit\s+punch|hermit\s+punch|palm\s+follow(?:-?up)?)\b",
                    "od swagger hermit punch",
                ),
                (
                    r"\b(?:l|light|lp)\s+(?:swagger\s+hermit\s+punch|hermit\s+punch|palm\s+follow(?:-?up)?)\b",
                    "lp swagger hermit punch",
                ),
                (
                    r"\b(?:m|medium|mp)\s+(?:swagger\s+hermit\s+punch|hermit\s+punch|palm\s+follow(?:-?up)?)\b",
                    "mp swagger hermit punch",
                ),
                (
                    r"\b(?:h|heavy|hp)\s+(?:swagger\s+hermit\s+punch|hermit\s+punch|palm\s+follow(?:-?up)?)\b",
                    "hp swagger hermit punch",
                ),
                (
                    r"\b(?:swagger\s+hermit\s+punch|hermit\s+punch|palm\s+follow(?:-?up)?)\b",
                    "swagger hermit punch",
                ),
            ]
            for pattern, alias_token in jamie_hermit_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

        if "akuma" in mentioned_chars:
            has_od_strength = bool(re.search(r"\b(od|ex)\b", text_lower))

            if air_sa1_context and "tenma gozanku" not in extra_inputs:
                extra_inputs.append("tenma gozanku")

            if re.search(r"\b(?:demon\s+)?gou\s+rasen\b", text_lower):
                akuma_followup_alias = "od demon gou rasen"
            elif re.search(r"\b(?:demon\s+)?gou\s+zanku\b", text_lower):
                akuma_followup_alias = "od demon gou zanku"
            elif re.search(r"\b(?:demon\s+)?(?:low(?:\s+slash)?|slide)\b", text_lower):
                akuma_followup_alias = "od demon low" if has_od_strength else "demon low"
            elif re.search(r"\b(?:demon\s+)?(?:guillotine|chop|overhead)\b", text_lower):
                akuma_followup_alias = "od chop" if has_od_strength else "chop"
            elif (
                re.search(r"\b(?:blade\s+kick|divekick|dive\s+kick)\b", text_lower)
                and re.search(r"\b(?:demon|flip|raid)\b", text_lower)
            ):
                akuma_followup_alias = (
                    "od demon flip divekick" if has_od_strength else "demon flip divekick"
                )
            elif re.search(r"\b(?:demon\s+)?(?:swoop|empty|stop|feint)\b", text_lower):
                akuma_followup_alias = "od empty" if has_od_strength else "empty"

            if akuma_followup_alias:
                if akuma_followup_alias not in extra_inputs:
                    extra_inputs.append(akuma_followup_alias)
                potential_inputs = [
                    token for token in potential_inputs
                    if token not in {"dive kick", "divekick"}
                ]

        if "jp" in mentioned_chars:
            jp_swipe_aliases = [
                (r"\b(?:od|ex)\s+swipe\b", "od swipe"),
                (r"\b(?:l|light|lp)\s+swipe\b", "l swipe"),
                (r"\b(?:m|medium|mp)\s+swipe\b", "m swipe"),
                (r"\b(?:h|heavy|hp)\s+swipe\b", "h swipe"),
                (r"\bswipe\b", "swipe"),
            ]
            for pattern, alias_token in jp_swipe_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

        if "a.k.i" in mentioned_chars:
            aki_whip_aliases = [
                (r"\b(?:od|ex)\s+whip\b", "od whip"),
                (r"\b(?:l|light|lp)\s+whip\b", "l whip"),
                (r"\b(?:m|medium|mp)\s+whip\b", "m whip"),
                (r"\b(?:h|heavy|hp)\s+whip\b", "h whip"),
                (r"\bwhip\b", "whip"),
            ]
            for pattern, alias_token in aki_whip_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

        if "luke" in mentioned_chars:
            luke_knuckle_aliases = [
                (r"\b(?:charged|hold|held)\s+(?:l|light|lp)\s+(?:flash\s+)?knuckle\b", "charged light knuckle"),
                (r"\b(?:l|light|lp)\s+(?:charged|hold|held)\s+(?:flash\s+)?knuckle\b", "charged light knuckle"),
                (r"\b(?:charged|hold|held)\s+(?:m|medium|mp)\s+(?:flash\s+)?knuckle\b", "charged medium knuckle"),
                (r"\b(?:m|medium|mp)\s+(?:charged|hold|held)\s+(?:flash\s+)?knuckle\b", "charged medium knuckle"),
                (r"\b(?:charged|hold|held)\s+(?:h|heavy|hp)\s+(?:flash\s+)?knuckle\b", "charged heavy knuckle"),
                (r"\b(?:h|heavy|hp)\s+(?:charged|hold|held)\s+(?:flash\s+)?knuckle\b", "charged heavy knuckle"),
                (r"\b(?:charged|hold|held)\s+(?:flash\s+)?knuckle\b", "charged knuckle"),
            ]
            for pattern, alias_token in luke_knuckle_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

        if query_requests_ca and "critical art" not in extra_inputs:
            extra_inputs.append("critical art")

        if "akuma" in mentioned_chars:
            if air_sa3_context and "sip of calamity" not in extra_inputs:
                extra_inputs.append("sip of calamity")

        if "lily" in mentioned_chars and query_requires_stocked:
            lily_stocked_aliases = [
                (r"\b(?:stocked|stock|windclad|wind\s+clad)\s+(?:condor\s+)?spire\b", "stocked spire"),
                (r"\b(?:stocked|stock|windclad|wind\s+clad)\s+(?:tomahawk|tomahawk\s+buster)\b", "stocked tomahawk"),
                (r"\b(?:stocked|stock|windclad|wind\s+clad|wind\s+stock)\s+(?:condor\s+)?wind\b", "stocked condor wind"),
            ]
            for pattern, alias_token in lily_stocked_aliases:
                if re.search(pattern, text_lower) and alias_token not in extra_inputs:
                    extra_inputs.append(alias_token)

        if "mai" in mentioned_chars and query_requires_stocked:
            mai_stocked_aliases = [
                (r"\b(?:od|ex)\s+(?:stocked|stock)\s+(?:fireball|kachousen)\b", "od stocked fireball"),
                (r"\b(?:stocked|stock)\s+(?:od|ex)\s+(?:fireball|kachousen)\b", "od stocked fireball"),
                (r"\b(?:od|ex)\s+(?:stocked|stock)\s+(?:dp|ryuuenjin)\b", "od stocked dp"),
                (r"\b(?:stocked|stock)\s+(?:od|ex)\s+(?:dp|ryuuenjin)\b", "od stocked dp"),
                (r"\b(?:od|ex)\s+(?:stocked|stock)\s+(?:twirl|ryuuenbu)\b", "od stocked twirl"),
                (r"\b(?:stocked|stock)\s+(?:od|ex)\s+(?:twirl|ryuuenbu)\b", "od stocked twirl"),
                (r"\b(?:od|ex)\s+(?:stocked|stock)\s+(?:cartwheel|shinobi\s+bachi)\b", "od stocked cartwheel"),
                (r"\b(?:stocked|stock)\s+(?:od|ex)\s+(?:cartwheel|shinobi\s+bachi)\b", "od stocked cartwheel"),
                (
                    r"\b(?:od|ex)\s+(?:stocked|stock)\s+(?:dive\s+kick|divekick|musasabi(?:\s+no\s+mai)?)\b",
                    "od stocked dive kick",
                ),
                (
                    r"\b(?:stocked|stock)\s+(?:od|ex)\s+(?:dive\s+kick|divekick|musasabi(?:\s+no\s+mai)?)\b",
                    "od stocked dive kick",
                ),
                (r"\b(?:stocked|stock)\s+(?:fireball|kachousen)\b", "stocked fireball"),
                (r"\b(?:stocked|stock)\s+(?:dp|ryuuenjin)\b", "stocked dp"),
                (r"\b(?:stocked|stock)\s+(?:twirl|ryuuenbu)\b", "stocked twirl"),
                (r"\b(?:stocked|stock)\s+(?:cartwheel|shinobi\s+bachi)\b", "stocked cartwheel"),
                (
                    r"\b(?:stocked|stock)\s+(?:dive\s+kick|divekick|musasabi(?:\s+no\s+mai)?)\b",
                    "stocked dive kick",
                ),
                (r"\b(?:stocked|stock)\s+(?:sa\s*1|super\s*art\s*1|super\s*1|level\s*1)\b", "stocked sa1"),
                (
                    r"\b(?:stocked|stock)\s+(?:air\s+)?(?:sa\s*2|super\s*art\s*2|super\s*2|level\s*2)\b",
                    "stocked air sa2",
                ),
                (
                    r"\b(?:air\s+)?(?:stocked|stock)\s+(?:sa\s*2|super\s*art\s*2|super\s*2|level\s*2)\b",
                    "stocked air sa2",
                ),
            ]
            for pattern, alias_token in mai_stocked_aliases:
                if re.search(pattern, text_lower) and alias_token not in extra_inputs:
                    extra_inputs.append(alias_token)

        if "juri" in mentioned_chars and query_requires_stocked:
            juri_stocked_aliases = [
                (r"\b(?:stocked|stock)\s+(?:fireball|saihasho|fuha\s+release)\b", "stocked fireball"),
                (r"\b(?:stocked|stock)\s+(?:axe\s+kick|ankensatsu)\b", "stocked axe kick"),
                (r"\b(?:stocked|stock)\s+(?:spinning\s+kicks?|go\s+ohsatsu)\b", "stocked spinning kicks"),
                (r"\b(?:stocked|stock)\s+(?:air\s+)?sa\s*1\b", "stocked sa1"),
                (r"\b(?:air\s+)?(?:stocked|stock)\s+sa\s*1\b", "stocked sa1"),
            ]
            for pattern, alias_token in juri_stocked_aliases:
                if re.search(pattern, text_lower) and alias_token not in extra_inputs:
                    extra_inputs.append(alias_token)

        def is_special_motion_num_cmd(num_cmd_raw):
            compact = re.sub(r"[^a-z0-9]", "", str(num_cmd_raw).lower())
            if not compact or ">" in str(num_cmd_raw):
                return False
            motion_prefixes = (
                "236", "214", "623", "421", "41236", "63214", "4268", "624", "46", "28",
                "214214", "236236", "360", "720", "22",
            )
            return compact.startswith(motion_prefixes)

        def get_special_canonical_base_name(row):
            raw_name = str(row.get("cmnName", "")).lower().strip()
            if not raw_name:
                raw_name = str(row.get("moveName", "")).lower().strip()
            if not raw_name:
                return ""
            base_name = re.sub(r"^(od|ex)\s+", "", raw_name)
            base_name = re.sub(
                r"^(lp|mp|hp|lk|mk|hk|pp|kk|light|medium|heavy|l|m|h)\s+",
                "",
                base_name,
            ).strip()
            return re.sub(r"\s*\(charged\)", "", base_name).strip()

        command_jump_notation_present = bool(
            re.search(
                r"\b(?:neutral\s+|n\s+)?(?:jump\s+|j\.?\s*)[1-9][0-9]*(?:lp|mp|hp|lk|mk|hk|p|k)\b",
                text_lower,
            )
        )

        if (
            not query_has_explicit_strength
            and mentioned_chars
            and not target_combo_query
            and not command_jump_notation_present
            and not query_requires_stocked
            and not query_requests_ca
        ):
            seen_special_prompts = set()
            for char in mentioned_chars:
                special_base_map = {}
                for row in FRAME_DATA.get(char, []):
                    if not is_special_motion_num_cmd(row.get("numCmd", "")):
                        continue
                    raw_name = str(row.get("cmnName", "")).lower().strip()
                    if not raw_name:
                        raw_name = str(row.get("moveName", "")).lower().strip()
                    if not raw_name:
                        continue
                    base_name = re.sub(r"^(od|ex)\s+", "", raw_name)
                    base_name = re.sub(
                        r"^(lp|mp|hp|lk|mk|hk|pp|kk|light|medium|heavy|l|m|h)\s+",
                        "",
                        base_name,
                    ).strip()
                    canonical_base = re.sub(r"\s*\(charged\)", "", base_name).strip()
                    if not canonical_base:
                        continue
                    special_base_map.setdefault(canonical_base, [])
                    if row not in special_base_map[canonical_base]:
                        special_base_map[canonical_base].append(row)

                for base_name, variants in special_base_map.items():
                    prompt_variants = variants

                    if char == "ryu" and base_name in {"super art level 1", "super art level 2"}:
                        if base_name == "super art level 1" and not query_requests_sa1:
                            continue
                        if base_name == "super art level 2" and not query_requests_sa2:
                            continue

                        denjin_variants = [row for row in variants if row_is_denjin_variant(row)]
                        non_denjin_variants = [row for row in variants if not row_is_denjin_variant(row)]
                        if query_requires_denjin and denjin_variants:
                            chosen_variant = denjin_variants[0]
                            if chosen_variant not in results:
                                results.append(chosen_variant)
                            continue
                        if not query_requires_denjin and non_denjin_variants:
                            chosen_variant = non_denjin_variants[0]
                            if chosen_variant not in results:
                                results.append(chosen_variant)
                            continue

                    if query_requires_denjin:
                        denjin_variants = [row for row in variants if row_is_denjin_variant(row)]
                        if denjin_variants:
                            prompt_variants = denjin_variants
                        else:
                            continue
                    if len(prompt_variants) < 2:
                        continue
                    base_tokens = re.findall(r"[a-z0-9]+", base_name)
                    base_in_query = tokens_in_text(base_tokens)
                    if not base_in_query and base_name == "fireball":
                        base_in_query = "hadoken" in text_tokens or "hadouken" in text_tokens
                    if not base_in_query and base_name == "upkicks":
                        base_in_query = "tensho" in text_tokens or "tenshokyaku" in text_tokens
                    if not base_in_query and base_name == "palm thrust":
                        base_in_query = "hashogeki" in text_tokens
                    if not base_in_query and base_name == "super art level 1":
                        base_in_query = bool(re.search(r"\bsa\s*1\b", text_lower))
                    if not base_in_query and base_name == "super art level 2":
                        base_in_query = bool(re.search(r"\bsa\s*2\b", text_lower))
                    if not base_in_query and base_name == "super art level 3":
                        base_in_query = bool(re.search(r"\bsa\s*3\b", text_lower))
                    if not base_in_query and base_name == "spd":
                        base_in_query = "command" in text_tokens and "grab" in text_tokens
                    if not base_in_query:
                        continue
                    if (
                        air_fireball_context
                        and base_name == "fireball"
                        and "air fireball" in special_base_map
                    ):
                        continue
                    if len(prompt_variants) == 2:
                        od_variants = [row for row in prompt_variants if row_is_od_variant(row)]
                        non_od_variants = [row for row in prompt_variants if not row_is_od_variant(row)]
                        if len(od_variants) == 1 and len(non_od_variants) == 1:
                            chosen_variant = od_variants[0] if query_wants_od_strength else non_od_variants[0]
                            if chosen_variant not in results:
                                results.append(chosen_variant)
                            continue
                    if char == "akuma" and base_name == "demon flip":
                        continue
                    if (
                        air_tatsu_context
                        and char in {"ryu", "ken", "akuma"}
                        and base_name in {"tatsu", "air tatsu"}
                    ):
                        continue
                    if (
                        ken_run_followup_context
                        and char == "ken"
                        and base_name in {"dp", "tatsu", "dragonlash"}
                    ):
                        continue
                    prompt_key = (char, base_name)
                    if prompt_key in seen_special_prompts:
                        continue
                    seen_special_prompts.add(prompt_key)
                    variant_lines = "\n".join(
                        f"- {row.get('moveName', '?')} ({row.get('numCmd', '?')})"
                        for row in prompt_variants
                    )
                    special_prompt_blocks.append(
                        f"**Special Strength Options ({char.capitalize()})**\n"
                        f"{base_name.title()} variants:\n{variant_lines}\n"
                        "Reply or make a new prompt with the exact strength+move."
                    )
        dp_strength_inputs = []
        dp_strength_prefix_matches = re.findall(
            r"\b(lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\s*(?:\+)?\s*(dp|srk|shoryu|shoryuken)\b",
            text_lower,
        )
        for strength_token, motion_token in dp_strength_prefix_matches:
            token = f"{strength_token} {motion_token}"
            if token not in dp_strength_inputs:
                dp_strength_inputs.append(token)
        dp_strength_suffix_matches = re.findall(
            r"\b(dp|srk|shoryu|shoryuken)\s*(?:\+)?\s*(lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b",
            text_lower,
        )
        for motion_token, strength_token in dp_strength_suffix_matches:
            token = f"{strength_token} {motion_token}"
            if token not in dp_strength_inputs:
                dp_strength_inputs.append(token)
        for token in dp_strength_inputs:
            if token not in extra_inputs:
                extra_inputs.append(token)

        dp_aliases = ["dp", "srk", "shoryu", "shoryuken", "623"]
        dp_present = False
        for token in dp_aliases:
            if re.search(rf"\b{re.escape(token)}\b", text_lower):
                if dp_strength_inputs and token in {"dp", "srk", "shoryu", "shoryuken"}:
                    dp_present = True
                    continue
                if token not in extra_inputs:
                    extra_inputs.append(token)
                dp_present = True
        if dp_present and re.search(r"\b(ex|od)\b", text_lower):
            extra_inputs.append("623pp")
            extra_inputs.append("623kk")
        if re.search(r"\b(ex|od)(dp|srk|shoryu|shoryuken)\b", text_lower):
            extra_inputs.append("623pp")
            extra_inputs.append("623kk")
        if ken_run_followup_context:
            extra_inputs = [
                token for token in extra_inputs
                if token not in {"dp", "srk", "shoryu", "shoryuken", "tatsu", "dragonlash"}
            ]
        if "sway" in text_lower:
            extra_inputs.append("sway")
        if "jus cool" in text_lower or "juscool" in text_lower:
            extra_inputs.append("jus cool")

        if "dee jay" in mentioned_chars:
            if (
                re.search(r"\bsway\s*(?:low)?\s*>\s*(?:lk|light)\b", text_lower)
                or re.search(r"\bsway\s+low\b", text_lower)
                or re.search(r"\bsway\s+lk\b", text_lower)
            ):
                deejay_sway_followup_alias = "sway low"
            elif (
                re.search(r"\bsway\s*(?:overhead)?\s*>\s*(?:mk|medium)\b", text_lower)
                or re.search(r"\bsway\s+overhead\b", text_lower)
                or re.search(r"\bsway\s+mk\b", text_lower)
            ):
                deejay_sway_followup_alias = "sway overhead"
            elif (
                re.search(r"\bsway\s*(?:launch|launcher)?\s*>\s*(?:hk|heavy)\b", text_lower)
                or re.search(r"\bsway\s+(?:launch|launcher)\b", text_lower)
                or re.search(r"\bsway\s+hk\b", text_lower)
            ):
                deejay_sway_followup_alias = "sway launch"
            elif (
                re.search(r"\bsway\s+feint\b", text_lower)
                or (
                    "sway" in text_lower
                    and re.search(r"\b6p\b", text_lower)
                    and re.search(r"\b4p\b", text_lower)
                )
            ):
                deejay_sway_followup_alias = "sway feint"

        if deejay_sway_followup_alias:
            if deejay_sway_followup_alias not in extra_inputs:
                extra_inputs.insert(0, deejay_sway_followup_alias)
            extra_inputs = [
                token
                for token in extra_inputs
                if token not in {"sway", "jus cool", "juscool"}
            ]
        has_od_denjin_fireball = bool(
            re.search(r"\b(ex|od)\s+denjin\s+(fireball|hadoken|hadouken)\b", text_lower)
        )
        if has_od_denjin_fireball:
            if "od denjin fireball" not in extra_inputs:
                extra_inputs.append("od denjin fireball")
        elif re.search(r"\bdenjin\s+(fireball|hadoken|hadouken)\b", text_lower):
            if "denjin fireball" not in extra_inputs:
                extra_inputs.append("denjin fireball")
        sa_alias_matches = re.findall(r"\bsa\s*([123])\b", text_lower)
        for sa_level in sa_alias_matches:
            sa_token = f"sa{sa_level}"
            if sa_token not in extra_inputs:
                extra_inputs.append(sa_token)
        # 46P charge patterns (back-forward+punch)
        charge_patterns = [
            (r"\b46p\b", "46p"),
            (r"\b46lp\b", "46lp"),
            (r"\b46mp\b", "46mp"),
            (r"\b46hp\b", "46hp"),
            (r"\b46pp\b", "46pp"),
            (r"\bb,\s*f\+?p\b", "46p"),
            (r"\bb,\s*f\+?lp\b", "46lp"),
            (r"\bb,\s*f\+?mp\b", "46mp"),
            (r"\bb,\s*f\+?hp\b", "46hp"),
            (r"\bb,\s*f\+?pp\b", "46pp"),
            (r"\bbf\+?p\b", "46p"),
            (r"\bbf\+?lp\b", "46lp"),
            (r"\bbf\+?mp\b", "46mp"),
            (r"\bbf\+?hp\b", "46hp"),
            (r"\bbf\+?pp\b", "46pp"),
            (r"\bback\s*forward\+?p\b", "46p"),
            (r"\bback\s*forward\+?lp\b", "46lp"),
            (r"\bback\s*forward\+?mp\b", "46mp"),
            (r"\bback\s*forward\+?hp\b", "46hp"),
            (r"\bback\s*forward\+?pp\b", "46pp"),
            # 28K charge patterns (down-up+kick)
            (r"\b28k\b", "28k"),
            (r"\b28lk\b", "28lk"),
            (r"\b28mk\b", "28mk"),
            (r"\b28hk\b", "28hk"),
            (r"\b28kk\b", "28kk"),
            (r"\bd,\s*u\+?k\b", "28k"),
            (r"\bd,\s*u\+?lk\b", "28lk"),
            (r"\bd,\s*u\+?mk\b", "28mk"),
            (r"\bd,\s*u\+?hk\b", "28hk"),
            (r"\bd,\s*u\+?kk\b", "28kk"),
            (r"\bdu\+?k\b", "28k"),
            (r"\bdu\+?lk\b", "28lk"),
            (r"\bdu\+?mk\b", "28mk"),
            (r"\bdu\+?hk\b", "28hk"),
            (r"\bdu\+?kk\b", "28kk"),
            (r"\bdown\s*up\+?k\b", "28k"),
            (r"\bdown\s*up\+?lk\b", "28lk"),
            (r"\bdown\s*up\+?mk\b", "28mk"),
            (r"\bdown\s*up\+?hk\b", "28hk"),
            (r"\bdown\s*up\+?kk\b", "28kk"),
        ]
        for pattern, token in charge_patterns:
            if re.search(pattern, text_lower) and token not in extra_inputs:
                extra_inputs.append(token)
        combo_text = text_lower.replace("->", ">")
        tc_selected_combos = set()
        tc_base_tokens = set(re.findall(r"\b[1-9][0-9]*[a-z]{1,3}\b", text_lower))
        tc_pair_candidates = set()
        for base_token, follow_token in re.findall(
            r"\b([1-9][0-9]*[a-z]{1,3})\s*(?:,|>|->)\s*([a-z]{1,3}|[1-9][0-9]*[a-z]{1,3})\b",
            combo_text,
        ):
            tc_pair_candidates.add(f"{base_token}>{follow_token}")
        for base_token, follow_token in re.findall(
            r"\b([1-9][0-9]*[a-z]{1,3})\s+([a-z]{1,3})\s+(?:target\s+combo|tc)\b",
            text_lower,
        ):
            tc_pair_candidates.add(f"{base_token}>{follow_token}")

        combo_matches = re.findall(
            r"\b[0-9a-zA-Z+]+(?:\s*>\s*[0-9a-zA-Z+]+)+\b",
            combo_text,
        )
        for combo in combo_matches:
            combo_token = re.sub(r"\s+", "", combo)
            tc_selected_combos.add(combo_token)
            if combo_token not in extra_inputs:
                extra_inputs.append(combo_token)

        if target_combo_query and mentioned_chars:
            compact_text = re.sub(r"\s+", "", combo_text)
            for char in mentioned_chars:
                normalized_char = normalize_char_name(char)
                compact_text_for_char = re.sub(
                    rf"\b{re.escape(normalized_char)}\b", "", compact_text
                )
                if compact_text_for_char == compact_text:
                    compact_text_for_char = compact_text
                tc_map = {}
                for row in FRAME_DATA.get(char, []):
                    num_cmd_raw = str(row.get("numCmd", ""))
                    num_cmd = num_cmd_raw.lower()
                    if ">" not in num_cmd:
                        continue
                    base_cmd = num_cmd.split(">", 1)[0].strip()
                    base_key = re.sub(r"\s+", "", base_cmd)
                    if not base_key:
                        continue
                    tc_map.setdefault(base_key, []).append(num_cmd_raw)
                for base_key, combos in tc_map.items():
                    if base_key not in compact_text_for_char:
                        continue
                    explicit_pair_matches = [
                        pair for pair in tc_pair_candidates if pair.startswith(f"{base_key}>")
                    ]
                    if explicit_pair_matches:
                        matched_any = False
                        for combo_raw in combos:
                            combo_key = re.sub(r"\s+", "", combo_raw.lower())
                            if ">" not in combo_key:
                                continue
                            combo_follow = combo_key.split(">", 1)[1]
                            for explicit_pair in explicit_pair_matches:
                                explicit_follow = explicit_pair.split(">", 1)[1]
                                if combo_follow == explicit_follow or combo_follow.startswith(explicit_follow):
                                    tc_selected_combos.add(combo_key)
                                    if combo_key not in extra_inputs:
                                        extra_inputs.append(combo_key)
                                    matched_any = True
                        if matched_any:
                            continue
                    if len(combos) == 1:
                        combo_token = re.sub(r"\s+", "", combos[0].lower())
                        tc_selected_combos.add(combo_token)
                        if combo_token not in extra_inputs:
                            extra_inputs.append(combo_token)
                        continue
                    tc_ambiguous_inputs.add(base_key)
                    combo_list = "\n".join(f"- {combo}" for combo in combos)
                    tc_prompt_blocks.append(
                        f"**Target Combo Options ({char.capitalize()})**\n"
                        f"{base_key.upper()} follow-ups:\n{combo_list}\n"
                        "Reply or Make a new prompt with the exact target combo "
                    )
        keyword_inputs = [
            # 46P moves
            "air slasher",
            "sonic boom",
            "sumo headbutt",
            "psycho crusher",
            "rolling attack",
            "blanka ball",
            "bison crusher",
            "crusher",
            "fireball",
            "boom",
            "headbutt",
            "clap",
            "claps",
            "neko damashi",
            "oicho",
            "oicho throw",
            "ball",
            # 28K moves
            "vertical rolling attack",
            "upball",
            "up ball",
            "somersault kick",
            "flash kick",
            "flashkick",
            "shadow rise",
            "command jump",
            "fly",
            "jackknife maximum",
            "upkicks",
            "upkick",
            "up kicks",
            "tensho",
            "tenshokyaku",
            "tensho kick",
            "tensho kicks",
            "dive kick",
            "divekick",
            "demon flip",
            "demon raid",
            "demon low slash",
            "demon guillotine",
            "demon blade kick",
            "demon swoop",
            "demon gou zanku",
            "demon gou rasen",
            "adamant flame",
            "flaming fist",
            "flame",
            "burn kick",
            "burnkick",
            "burn kicks",
            "burnkicks",
            "burning kick",
            "burning kicks",
            "air burn kick",
            "air burnkick",
            "air burning kick",
            "air burning kicks",
            "aerial burn kick",
            "aerial burnkick",
            "aerial burning kick",
            "teleport",
            "ashura",
            "ashura senku",
            "raging demon",
            "tenma",
            "gozanku",
            "air fireball",
            "aerial fireball",
            "air hadoken",
            "zanku",
            "air tatsu",
            "aerial tatsu",
            "air tatsumaki",
            "aerial tatsumaki",
            "air legs",
            "airlegs",
            "aerial legs",
            "air lightning legs",
            "sumo smash",
            "ass slam",
            "butt slam",
            "spinning bird kick",
            "sbk",
            # JP 22 specials
            "triglav",
            "amnesia",
            "ground spike",
            "spike",
            "pierce",
        ]
        # Strength prefixes for charge moves
        strength_prefixes = ["lp", "mp", "hp", "od", "ex", "light", "medium", "heavy", "l", "m", "h"]
        for token in keyword_inputs:
            matched_strength_for_token = False
            # Check for strength+keyword combos (e.g., "heavy fireball", "hp boom")
            for prefix in strength_prefixes:
                combo = f"{prefix} {token}"
                if combo in text_lower and combo not in extra_inputs:
                    if token == "ball" and "blanka" not in text_lower:
                        continue
                    extra_inputs.append(combo)
                    matched_strength_for_token = True
            # Check for bare keyword
            if (
                not matched_strength_for_token
                and re.search(rf"\b{re.escape(token)}\b", text_lower)
                and token not in extra_inputs
            ):
                if token == "ball" and "blanka" not in text_lower:
                    continue
                extra_inputs.append(token)
        if "akuma" in mentioned_chars:
            if re.search(r"\bback(?:ward)?\s+teleport\b", text_lower):
                extra_inputs = [token for token in extra_inputs if token != "teleport"]
                if "back teleport" not in extra_inputs:
                    extra_inputs.insert(0, "back teleport")
            elif re.search(r"\btele(?:port)?\s+back(?:ward)?\b", text_lower):
                extra_inputs = [token for token in extra_inputs if token != "teleport"]
                if "teleport back" not in extra_inputs:
                    extra_inputs.insert(0, "teleport back")
            elif re.search(r"\bforward\s+teleport\b", text_lower):
                extra_inputs = [token for token in extra_inputs if token != "teleport"]
                if "forward teleport" not in extra_inputs:
                    extra_inputs.insert(0, "forward teleport")
        ordered_inputs = []
        for inp in extra_inputs + potential_inputs:
            if inp and inp not in ordered_inputs:
                ordered_inputs.append(inp)
        potential_inputs = ordered_inputs

        if wants_comparison and (potential_inputs or extra_inputs) and len(mentioned_chars) >= 2:
            side_segments = [
                segment.strip()
                for segment in re.split(r"\b(?:vs|versus|and)\b", text_lower)
                if segment.strip()
            ]
            if len(side_segments) >= 2:
                assigned_chars = set()

                def segment_mentions_character(segment_text, char_key):
                    segment_tokens = re.findall(r"[a-z0-9]+", segment_text)
                    if not segment_tokens:
                        return False
                    char_tokens = re.findall(r"[a-z0-9]+", str(char_key).lower())
                    if char_tokens and tokens_in_haystack(segment_tokens, char_tokens):
                        return True
                    for alias, canonical in CHARACTER_ALIASES.items():
                        if normalize_char_name(canonical) != normalize_char_name(char_key):
                            continue
                        alias_tokens = re.findall(r"[a-z0-9]+", str(alias).lower())
                        if alias_tokens and tokens_in_haystack(segment_tokens, alias_tokens):
                            return True
                    return False

                for side_text in side_segments:
                    side_chars = [
                        char for char in mentioned_chars
                        if segment_mentions_character(side_text, char)
                    ]
                    if not side_chars:
                        continue

                    if len(side_chars) == 1:
                        target_char = side_chars[0]
                    else:
                        target_char = next(
                            (char for char in side_chars if char not in assigned_chars),
                            side_chars[0],
                        )

                    side_inputs = []
                    for inp in potential_inputs:
                        inp_norm = str(inp or "").strip().lower()
                        if not inp_norm:
                            continue
                        if re.search(rf"\b{re.escape(inp_norm)}\b", side_text):
                            if inp not in side_inputs:
                                side_inputs.append(inp)

                    if side_inputs:
                        comparison_char_inputs[target_char] = side_inputs
                        assigned_chars.add(target_char)

        explicit_move_attempt = bool(potential_inputs or extra_inputs)
        if mentioned_chars:
            stop_tokens = {
                "frame", "frames", "framedata", "data", "startup", "recovery", "active",
                "on", "hit", "block", "compare", "comparison", "versus", "vs", "which",
                "is", "faster", "better", "tc", "target", "combo", "combos", "how", "fast",
                "quick", "speed", "of", "the", "a", "an", "for", "with", "please", "show",
                "tell", "me", "about", "can", "i", "punish", "punishable", "stats",
                "send", "post", "drop", "give", "link",
                "gif", "gifs", "hitbox", "hitboxes",
            }
            char_tokens = set()
            for char in mentioned_chars:
                char_tokens.update(re.findall(r"[a-z0-9]+", str(char).lower()))
                normalized_char = normalize_char_name(char)
                if normalized_char:
                    char_tokens.add(normalized_char)
            residual_tokens = [
                tok for tok in text_tokens
                if tok not in stop_tokens and tok not in char_tokens
            ]
            if residual_tokens:
                explicit_move_attempt = True
                residual_candidate = " ".join(residual_tokens).strip()
                if residual_candidate and residual_candidate not in potential_inputs:
                    potential_inputs.append(residual_candidate)

        strength_prefix_re = re.compile(r"^(?:lp|mp|hp|lk|mk|hk|pp|kk|od|ex|light|medium|heavy|l|m|h)\s+")
        text_compact = re.sub(r"[^a-z0-9]", "", text_lower)

        def token_matches_move_name(name_token, query_token):
            if (name_token == "od" and query_token == "ex") or (name_token == "ex" and query_token == "od"):
                return True
            if name_token == query_token:
                return True
            if len(query_token) >= 3 and name_token.startswith(query_token):
                return True
            if len(name_token) >= 3 and query_token.startswith(name_token):
                return True
            return False

        motion_button_notation_present = bool(
            re.search(
                r"\b[1-9][0-9]*\s*(?:\+)?\s*(?:lp|mp|hp|lk|mk|hk|pp|kk|p|k)\b",
                text_lower,
            )
        )

        for char in mentioned_chars:
            char_data = FRAME_DATA[char]
            for row in char_data:
                for name_key in ["cmnName", "moveName"]:
                    raw_name = str(row.get(name_key, "")).lower().strip()
                    if not raw_name:
                        continue
                    candidate_names = [raw_name]
                    stripped_name = strength_prefix_re.sub("", raw_name).strip()
                    if (
                        stripped_name
                        and stripped_name != raw_name
                        and not query_has_explicit_strength
                    ):
                        candidate_names.append(stripped_name)
                    if char == "sagat":
                        tigerless_candidates = []
                        for name_variant in list(candidate_names):
                            tigerless_variant = re.sub(r"\btiger\b", "", name_variant)
                            tigerless_variant = re.sub(r"\s+", " ", tigerless_variant).strip()
                            if (
                                tigerless_variant
                                and tigerless_variant != name_variant
                                and tigerless_variant not in candidate_names
                            ):
                                tigerless_candidates.append(tigerless_variant)
                        candidate_names.extend(tigerless_candidates)
                    for candidate_name in candidate_names:
                        candidate_has_strength_prefix = bool(strength_prefix_re.match(candidate_name))
                        if query_has_explicit_strength and not candidate_has_strength_prefix:
                            continue
                        candidate_tokens = re.findall(r"[a-z0-9]+", candidate_name)
                        if not candidate_tokens:
                            continue
                        if len(candidate_tokens) < 2:
                            if (
                                char == "sagat"
                                and len(candidate_tokens) == 1
                                and len(candidate_tokens[0]) >= 4
                                and candidate_tokens[0] in text_tokens
                            ):
                                if candidate_name not in potential_inputs:
                                    potential_inputs.append(candidate_name)
                            if (
                                char == "ken"
                                and len(candidate_tokens) == 1
                                and candidate_tokens[0] == "run"
                                and "run" in text_tokens
                                and not re.search(
                                    r"\brun\s+(?:stop|overhead|step|dp|shoryu|shoryuken|tatsu|dragonlash|dragon\s+lash|lash)\b",
                                    text_lower,
                                )
                            ):
                                if candidate_name not in potential_inputs:
                                    potential_inputs.append(candidate_name)
                            continue
                        candidate_compact = re.sub(r"[^a-z0-9]", "", candidate_name)
                        if (
                            len(candidate_compact) >= 6
                            and candidate_compact in text_compact
                        ):
                            if candidate_name not in potential_inputs:
                                potential_inputs.append(candidate_name)
                            continue
                        if all(
                            any(token_matches_move_name(name_tok, query_tok) for query_tok in text_tokens)
                            for name_tok in candidate_tokens
                        ):
                            if candidate_name not in potential_inputs:
                                potential_inputs.append(candidate_name)

        # also valid simple inputs: "mp", "hk" if preceded by char?

        for char in mentioned_chars:
            char_data = FRAME_DATA[char]

            # Check against potential inputs found via regex
            char_lookup_inputs = potential_inputs
            if comparison_char_inputs.get(char):
                char_lookup_inputs = comparison_char_inputs[char]
            for inp in char_lookup_inputs:
                row = lookup_frame_data(char, inp)
                if row and row not in results:
                    results.append(row)

            # Also check strict "frame data [char] [move]" remainder if exists
            # (This handles the specific verified cases)

            # "brute force" check for short inputs if the regex missed them (like "mp")
            # only if the string looks like "ryu mp"
            def is_button_part_of_dp_motion(button):
                return bool(
                    re.search(
                        rf"\b{re.escape(char)}\s+{button}\s*(?:\+)?\s*(?:dp|srk|shoryu|shoryuken)\b",
                        text_lower,
                    )
                )

            if not special_grab_query and not motion_button_notation_present:
                if f"{char} mp" in text_lower and not is_button_part_of_dp_motion("mp"):
                    row = lookup_frame_data(char, "mp")
                    if row and row not in results:
                        results.append(row)
                if f"{char} mk" in text_lower and not is_button_part_of_dp_motion("mk"):
                    row = lookup_frame_data(char, "mk")
                    if row and row not in results:
                        results.append(row)
                if f"{char} hp" in text_lower and not is_button_part_of_dp_motion("hp"):
                    row = lookup_frame_data(char, "hp")
                    if row and row not in results:
                        results.append(row)
                if f"{char} hk" in text_lower and not is_button_part_of_dp_motion("hk"):
                    row = lookup_frame_data(char, "hk")
                    if row and row not in results:
                        results.append(row)
                if f"{char} lp" in text_lower and not is_button_part_of_dp_motion("lp"):
                    row = lookup_frame_data(char, "lp")
                    if row and row not in results:
                        results.append(row)
                if f"{char} lk" in text_lower and not is_button_part_of_dp_motion("lk"):
                    row = lookup_frame_data(char, "lk")
                    if row and row not in results:
                        results.append(row)

        # SPD/360 variations - for Zangief (Screw Piledriver) and Lily (Mexican Typhoon)
            if not (char == "zangief" and zangief_borscht_context):
                spd_patterns = [
                    ("l spd", "lp"), ("m spd", "mp"), ("h spd", "hp"),
                    ("light spd", "lp"), ("medium spd", "mp"), ("heavy spd", "hp"),
                    ("lspd", "lp"), ("mspd", "mp"), ("hspd", "hp"),
                    ("od spd", "od"), ("ex spd", "od"),
                    ("l command grab", "lp"), ("m command grab", "mp"), ("h command grab", "hp"),
                    ("light command grab", "lp"), ("medium command grab", "mp"), ("heavy command grab", "hp"),
                    ("od command grab", "od"), ("ex command grab", "od"),
                    ("360+lp", "lp"), ("360+mp", "mp"), ("360+hp", "hp"), ("360+pp", "od"),
                    ("360lp", "lp"), ("360mp", "mp"), ("360hp", "hp"), ("360pp", "od"),
                    ("command grab", ""), ("spd", ""), ("360", ""),
                ]
                for pattern, strength in spd_patterns:
                    if pattern in text_lower:
                        if not strength and query_has_explicit_strength:
                            continue
                        # Try both Screw Piledriver (Gief) and Mexican Typhoon (Lily)
                        if strength:
                            move_names = [
                                f"{strength} command grab",
                                f"{strength} screw piledriver",
                                f"{strength} mexican typhoon",
                            ]
                        else:
                            move_names = ["command grab", "screw piledriver", "mexican typhoon"]
                        for move_name in move_names:
                            row = lookup_frame_data(char, move_name)
                            if row and row not in results:
                                results.append(row)
                                break
                        break  # Only match one SPD variant

            if char == "zangief" and zangief_borscht_context:
                borscht_lookup = "od borscht dynamite" if (
                    re.search(r"\b(?:od|ex)\s+borscht\b", text_lower)
                    or re.search(r"\bj\.?\s*360\s*\+?\s*kk\b", text_lower)
                    or re.search(r"\bj\s+360\s*\+?\s*kk\b", text_lower)
                ) else "borscht dynamite"
                row = lookup_frame_data(char, borscht_lookup)
                if row and row not in results:
                    results.append(row)

            if char == "alex":
                alex_stance_patterns = [
                    ("stance hk hk", "stance hk hk"),
                    ("stance lp", "stance lp"), ("stance mp", "stance mp"), ("stance hp", "stance hp"),
                    ("stance lk", "stance lk"), ("stance mk", "stance mk"), ("stance hk", "stance hk"),
                    ("stance lplk", "stance lplk"), ("stance 5lplk", "stance 5lplk"),
                    ("stance 2lplk", "stance 2lplk"), ("stance 6p", "stance 6p"),
                    ("stance 6", "stance 6"), ("stance 4", "stance 4"),
                    ("stance jab", "stance jab"), ("stance shoulder", "stance shoulder"),
                    ("stance lariat", "stance lariat"), ("stance hop", "stance hop"),
                    ("stance stomp", "stance stomp"), ("stance throw", "stance throw"),
                    ("stance command grab", "stance command grab"), ("stance", "stance"),
                ]
                for pattern, alias_key in alex_stance_patterns:
                    if pattern in text_lower:
                        row = lookup_frame_data(char, alias_key)
                        if row and row not in results:
                            results.append(row)
                        break

            # Chun-Li serenity stream aliases are special-cased here because they
            # use generic "stance"/"ss" wording that would otherwise be too broad.
            if char == "chun-li":
                stance_patterns = [
                    ("stance lp", "stance lp"), ("stance mp", "stance mp"), ("stance hp", "stance hp"),
                    ("stance lk", "stance lk"), ("stance mk", "stance mk"), ("stance hk", "stance hk"),
                    ("ss lp", "ss lp"), ("ss mp", "ss mp"), ("ss hp", "ss hp"),
                    ("ss lk", "ss lk"), ("ss mk", "ss mk"), ("ss hk", "ss hk"),
                    ("serenity stream", "stance"), ("stance", "stance"), ("ss", "ss"),
                ]
                for pattern, alias_key in stance_patterns:
                    if pattern in text_lower:
                        row = lookup_frame_data(char, alias_key)
                        if row and row not in results:
                            results.append(row)
                        break  # Only match one stance variant

            # Lily Mexican Typhoon variations
            typhoon_patterns = [
                ("l typhoon", "l typhoon"), ("m typhoon", "m typhoon"), ("h typhoon", "h typhoon"),
                ("light typhoon", "light typhoon"), ("medium typhoon", "medium typhoon"), ("heavy typhoon", "heavy typhoon"),
                ("od typhoon", "od typhoon"), ("ex typhoon", "ex typhoon"),
                ("mexican typhoon", "mexican typhoon"), ("typhoon", "typhoon"),
            ]
            for pattern, alias_key in typhoon_patterns:
                if pattern in text_lower:
                    row = lookup_frame_data(char, alias_key)
                    if row and row not in results:
                        results.append(row)
                    break  # Only match one typhoon variant

        if special_grab_query and query_has_explicit_strength and not results and mentioned_chars:
            for char in mentioned_chars:
                grab_variants = []
                for row in FRAME_DATA.get(char, []):
                    cmn_name = str(row.get("cmnName", "")).lower()
                    if "command grab" in cmn_name or re.search(r"\bspd\b", cmn_name):
                        grab_variants.append(row)
                if len(grab_variants) >= 2:
                    variant_lines = "\n".join(
                        f"- {row.get('moveName', '?')} ({row.get('numCmd', '?')})"
                        for row in grab_variants
                    )
                    special_prompt_blocks.append(
                        f"**Special Strength Options ({char.capitalize()})**\n"
                        f"Command Grab variants:\n{variant_lines}\n"
                        "Reply or make a new prompt with the exact command or move name."
                    )

        if query_requires_denjin and results:
            denjin_results = [row for row in results if row_is_denjin_variant(row)]
            results = denjin_results

        if query_requires_charged and results:
            charged_results = [row for row in results if row_is_charged_variant(row)]
            if charged_results:
                results = charged_results
            else:
                upgraded_charged_results = []
                for row in results:
                    row_char_key = resolve_character_key(row.get("char_name", ""))
                    if not row_char_key:
                        continue

                    row_num_cmd_base = normalize_num_cmd_token(row.get("numCmd", ""))
                    if not row_num_cmd_base:
                        continue

                    charged_match = None
                    for candidate in FRAME_DATA.get(row_char_key, []):
                        if not row_is_charged_variant(candidate):
                            continue
                        candidate_base = normalize_num_cmd_token(candidate.get("numCmd", ""))
                        if candidate_base == row_num_cmd_base:
                            charged_match = candidate
                            break

                    if charged_match and charged_match not in upgraded_charged_results:
                        upgraded_charged_results.append(charged_match)

                if upgraded_charged_results:
                    results = upgraded_charged_results

        if query_has_explicit_strength and results:
            wants_od_strength = bool(re.search(r"\b(od|ex)\b", text_lower))
            wants_non_od_strength = bool(
                re.search(r"\b(lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b", text_lower)
            )
            if wants_od_strength:
                od_results = [row for row in results if row_is_od_variant(row)]
                if od_results:
                    results = od_results
            elif wants_non_od_strength:
                non_od_results = [row for row in results if not row_is_od_variant(row)]
                if non_od_results:
                    results = non_od_results

            exact_strength_results = [
                row for row in results
                if row_matches_explicit_strength(row, text_lower)
            ]
            if exact_strength_results:
                results = exact_strength_results

            exact_term_results = [
                row for row in results
                if row_matches_query_move_terms(row)
            ]
            if exact_term_results:
                results = exact_term_results

        if alex_stance_followup_context and results:
            filtered_results = []
            for row in results:
                row_char_key = normalize_char_name(row.get("char_name", ""))
                if row_char_key != "alex":
                    filtered_results.append(row)
                    continue
                row_num_cmd_norm = normalize_num_cmd_token(row.get("numCmd", ""))
                row_cmn_name = str(row.get("cmnName", "")).lower()
                if row_num_cmd_norm.startswith("2pp>") or "stance >" in row_cmn_name:
                    filtered_results.append(row)
            if filtered_results:
                results = filtered_results

        if air_tatsu_context and results:
            air_tatsu_chars = {"ryu", "ken", "akuma"}
            mentioned_air_tatsu_chars = set(mentioned_chars) & air_tatsu_chars
            if mentioned_air_tatsu_chars:
                filtered_results = []
                for row in results:
                    row_char_key = normalize_char_name(row.get("char_name", ""))
                    row_char_matches = any(
                        normalize_char_name(char) == row_char_key
                        for char in mentioned_air_tatsu_chars
                    )
                    if not row_char_matches:
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    num_cmd = str(row.get("numCmd", "")).lower()
                    if "air" in move_name or "air" in cmn_name or "(air)" in num_cmd:
                        filtered_results.append(row)
                if filtered_results:
                    results = filtered_results

        if air_fireball_context and results:
            mentioned_air_fireball_chars = set(mentioned_chars) & {"akuma"}
            if mentioned_air_fireball_chars:
                allow_demon_fireball = any(token in text_tokens for token in {"demon", "flip", "raid"})
                filtered_results = []
                for row in results:
                    row_char_key = normalize_char_name(row.get("char_name", ""))
                    row_char_matches = any(
                        normalize_char_name(char) == row_char_key
                        for char in mentioned_air_fireball_chars
                    )
                    if not row_char_matches:
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    num_cmd = str(row.get("numCmd", "")).lower()
                    is_air_fireball_row = (
                        "air fireball" in cmn_name
                        or "zanku" in move_name
                        or "zanku" in cmn_name
                        or "(air)" in num_cmd
                    )
                    if not is_air_fireball_row:
                        continue
                    if not allow_demon_fireball and ("demon" in move_name or "demon" in cmn_name):
                        continue
                    filtered_results.append(row)
                if filtered_results:
                    results = filtered_results
                else:
                    fallback_input = "od zanku hadoken" if query_wants_od_strength else "zanku hadoken"
                    fallback_row = lookup_frame_data("akuma", fallback_input)
                    if fallback_row:
                        results = [fallback_row]

        if air_sa1_context and results:
            mentioned_air_sa1_chars = set(mentioned_chars) & {"akuma"}
            if mentioned_air_sa1_chars:
                filtered_results = []
                for row in results:
                    row_char_key = normalize_char_name(row.get("char_name", ""))
                    row_char_matches = any(
                        normalize_char_name(char) == row_char_key
                        for char in mentioned_air_sa1_chars
                    )
                    if not row_char_matches:
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    num_cmd = str(row.get("numCmd", "")).lower()
                    is_air_sa1_row = (
                        "tenma" in move_name
                        or "gozanku" in move_name
                        or (
                            "super art level 1" in cmn_name
                            and ("air" in cmn_name or "(air)" in num_cmd)
                        )
                    )
                    if is_air_sa1_row:
                        filtered_results.append(row)
                if filtered_results:
                    results = filtered_results
                else:
                    fallback_row = lookup_frame_data("akuma", "tenma gozanku")
                    if fallback_row:
                        results = [fallback_row]

        if (query_requests_sa3 or air_sa3_context) and results:
            mentioned_sa3_chars = set(mentioned_chars) & {"akuma"}
            if mentioned_sa3_chars:
                filtered_results = []
                for row in results:
                    row_char_key = normalize_char_name(row.get("char_name", ""))
                    row_char_matches = any(
                        normalize_char_name(char) == row_char_key
                        for char in mentioned_sa3_chars
                    )
                    if not row_char_matches:
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    num_cmd = str(row.get("numCmd", "")).lower()
                    is_air_variant = "air" in move_name or "air" in cmn_name or "(air)" in num_cmd
                    is_ca_variant = row_is_ca_variant(row)
                    if not is_air_variant and not is_ca_variant:
                        filtered_results.append(row)
                if filtered_results:
                    results = filtered_results
                else:
                    fallback_row = lookup_frame_data("akuma", "sip of calamity")
                    if fallback_row:
                        results = [fallback_row]

        if query_requests_ca and results:
            ca_rows = [row for row in results if row_is_ca_variant(row)]
            if ca_rows:
                results = ca_rows

        if query_requests_air_context and results:
            air_rows = []
            for row in results:
                move_name = str(row.get("moveName", "")).lower()
                cmn_name = str(row.get("cmnName", "")).lower()
                num_cmd = str(row.get("numCmd", "")).lower()
                if "air" in move_name or "air" in cmn_name or "(air)" in num_cmd:
                    air_rows.append(row)
            if air_rows:
                results = air_rows

        if query_requires_stocked and results:
            stocked_rows = [row for row in results if row_is_stocked_variant(row)]
            if stocked_rows:
                results = stocked_rows

        if (
            "jamie" in mentioned_chars
            and results
            and re.search(
                r"\b(?:rekka|freeflow|palm|swagger|arrow\s+kick|upkicks?|drink(?:\s+activation)?|activation)\b",
                text_lower,
            )
        ):
            jamie_special_rows = [
                row
                for row in results
                if str(row.get("moveType", "")).strip().lower()
                in {"special", "movement-special", "super", "command-grab"}
            ]
            if jamie_special_rows:
                results = jamie_special_rows

        if akuma_followup_alias and results:
            alias_lower = akuma_followup_alias.lower()
            followup_keyword = None
            if "gou rasen" in alias_lower:
                followup_keyword = "gou rasen"
            elif "gou zanku" in alias_lower:
                followup_keyword = "gou zanku"
            elif "low" in alias_lower or "slide" in alias_lower:
                followup_keyword = "low slash"
            elif "chop" in alias_lower or "guillotine" in alias_lower:
                followup_keyword = "guillotine"
            elif "divekick" in alias_lower or "blade kick" in alias_lower:
                followup_keyword = "blade kick"
            elif any(token in alias_lower for token in ("swoop", "empty", "stop", "feint")):
                followup_keyword = "swoop"

            if followup_keyword:
                filtered_results = []
                for row in results:
                    row_char = normalize_char_name(row.get("char_name", ""))
                    if row_char != "akuma":
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    if (
                        followup_keyword == "blade kick"
                        and "demon" not in move_name
                        and "demon" not in cmn_name
                    ):
                        continue
                    if followup_keyword in move_name or followup_keyword in cmn_name:
                        filtered_results.append(row)
                if filtered_results:
                    results = filtered_results

        if ken_jinrai_followup_alias and results:
            alias_lower = ken_jinrai_followup_alias.lower()
            ken_followup_keywords = []
            if "low" in alias_lower or "lk" in alias_lower:
                ken_followup_keywords = ["jinrai > low", "kazekama", "> 6lk"]
            elif "overhead" in alias_lower or "mk" in alias_lower:
                ken_followup_keywords = ["jinrai > overhead", "gorai", "> 6mk"]
            elif any(token in alias_lower for token in ("heavy", "launcher", "hk")):
                ken_followup_keywords = ["jinrai > heavy", "senka", "> 6hk"]

            if ken_followup_keywords:
                filtered_results = []
                for row in results:
                    row_char = normalize_char_name(row.get("char_name", ""))
                    if row_char != "ken":
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    num_cmd = str(row.get("numCmd", "")).lower()
                    if any(
                        keyword in move_name or keyword in cmn_name or keyword in num_cmd
                        for keyword in ken_followup_keywords
                    ):
                        filtered_results.append(row)
                if filtered_results:
                    results = filtered_results

        if deejay_sway_followup_alias and results:
            alias_lower = deejay_sway_followup_alias.lower()
            deejay_char_key_norm = normalize_char_name("dee jay")
            deejay_followup_keywords = []
            if "low" in alias_lower:
                deejay_followup_keywords = ["funky slicer", "sway > low", "> lk"]
            elif "overhead" in alias_lower:
                deejay_followup_keywords = ["waning moon", "sway > overhead", "> mk"]
            elif any(token in alias_lower for token in ("launch", "launcher", "hk")):
                deejay_followup_keywords = ["maximum strike", "sway > launcher", "> hk"]
            elif any(token in alias_lower for token in ("feint", "dash", "backdash")):
                deejay_followup_keywords = [
                    "juggling sway",
                    "sway > dash > backdash",
                    "> 6p > 4p",
                ]

            if deejay_followup_keywords:
                filtered_results = []
                for row in results:
                    row_char = normalize_char_name(row.get("char_name", ""))
                    if row_char != deejay_char_key_norm:
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    num_cmd = str(row.get("numCmd", "")).lower()
                    if any(
                        keyword in move_name or keyword in cmn_name or keyword in num_cmd
                        for keyword in deejay_followup_keywords
                    ):
                        filtered_results.append(row)
                if filtered_results:
                    results = filtered_results

        if (
            not query_has_explicit_strength
            and results
            and not target_combo_query
            and not query_requires_stocked
            and not query_requests_ca
        ):
            existing_special_prompt_keys = set()

            def variant_is_air_move(row):
                move_name = str(row.get("moveName", "")).lower()
                cmn_name = str(row.get("cmnName", "")).lower()
                num_cmd = str(row.get("numCmd", "")).lower()
                return (
                    "(air" in num_cmd
                    or "air" in move_name
                    or "air" in cmn_name
                    or "aerial" in move_name
                    or "aerial" in cmn_name
                )

            for prompt_block in special_prompt_blocks:
                char_match = re.search(r"Special Strength Options \(([^)]+)\)", prompt_block)
                base_match = re.search(r"\n([^\n]+) variants:", prompt_block)
                if not char_match or not base_match:
                    continue
                prompt_char = normalize_char_name(char_match.group(1))
                prompt_base = str(base_match.group(1)).lower().strip()
                if prompt_char and prompt_base:
                    existing_special_prompt_keys.add((prompt_char, prompt_base))

            ambiguous_special_keys = set()
            for row in results:
                row_char_norm = normalize_char_name(row.get("char_name", ""))
                if not row_char_norm:
                    continue
                if mentioned_chars and row_char_norm not in {
                    normalize_char_name(char) for char in mentioned_chars
                }:
                    continue
                row_char_key = resolve_character_key(row.get("char_name", ""))
                if not row_char_key:
                    continue
                if not is_special_motion_num_cmd(row.get("numCmd", "")):
                    continue

                base_name = get_special_canonical_base_name(row)
                if not base_name:
                    continue

                if row_char_norm == "ryu" and base_name in {"super art level 1", "super art level 2"}:
                    continue

                key = (row_char_norm, base_name)
                if key in existing_special_prompt_keys or key in ambiguous_special_keys:
                    continue

                variants = []
                for candidate in FRAME_DATA.get(row_char_key, []):
                    if not is_special_motion_num_cmd(candidate.get("numCmd", "")):
                        continue
                    if get_special_canonical_base_name(candidate) != base_name:
                        continue
                    if query_requires_denjin and not row_is_denjin_variant(candidate):
                        continue
                    variants.append(candidate)

                if query_requests_air_context and not any(
                    variant_is_air_move(candidate) for candidate in variants
                ):
                    continue

                if len(variants) < 2:
                    continue

                if len(variants) == 2:
                    od_variants = [candidate for candidate in variants if row_is_od_variant(candidate)]
                    non_od_variants = [candidate for candidate in variants if not row_is_od_variant(candidate)]
                    if len(od_variants) == 1 and len(non_od_variants) == 1:
                        chosen_variant = od_variants[0] if query_wants_od_strength else non_od_variants[0]
                        if chosen_variant not in results:
                            results.append(chosen_variant)
                        continue

                variant_lines = "\n".join(
                    f"- {candidate.get('moveName', '?')} ({candidate.get('numCmd', '?')})"
                    for candidate in variants
                )
                special_prompt_blocks.append(
                    f"**Special Strength Options ({row_char_key.capitalize()})**\n"
                    f"{base_name.title()} variants:\n{variant_lines}\n"
                    "Reply or make a new prompt with the exact strength+move."
                )
                ambiguous_special_keys.add(key)

            if ambiguous_special_keys:
                filtered_results = []
                for row in results:
                    row_char = normalize_char_name(row.get("char_name", ""))
                    row_base = get_special_canonical_base_name(row)
                    row_key = (row_char, row_base)
                    if (
                        is_special_motion_num_cmd(row.get("numCmd", ""))
                        and row_key in ambiguous_special_keys
                    ):
                        continue
                    filtered_results.append(row)
                results = filtered_results

    if special_prompt_blocks and (
        (
            not query_has_explicit_strength
            and not query_requires_stocked
            and not query_requests_ca
        )
        or (special_grab_query and not results)
    ):
        results = []

    if (
        wants_comparison
        and len(mentioned_chars) >= 2
        and len(comparison_char_inputs) >= 2
        and not special_prompt_blocks
    ):
        scoped_comparison_rows = []
        for char in mentioned_chars:
            scoped_inputs = comparison_char_inputs.get(char, [])
            for scoped_input in scoped_inputs:
                scoped_row = lookup_frame_data(char, scoped_input)
                if scoped_row and scoped_row not in scoped_comparison_rows:
                    scoped_comparison_rows.append(scoped_row)
        if scoped_comparison_rows:
            results = scoped_comparison_rows

    if target_combo_query:
        if tc_prompt_blocks and not tc_selected_combos:
            results = []
        else:
            filtered_tc_results = []
            for row in results:
                num_cmd_compact = re.sub(r"\s+", "", str(row.get("numCmd", "")).lower())
                if ">" not in num_cmd_compact:
                    continue
                if tc_selected_combos and num_cmd_compact not in tc_selected_combos:
                    continue
                if tc_base_tokens and not any(
                    num_cmd_compact.startswith(f"{base}>") for base in tc_base_tokens
                ):
                    continue
                if row not in filtered_tc_results:
                    filtered_tc_results.append(row)
            if filtered_tc_results:
                results = filtered_tc_results
            elif tc_prompt_blocks:
                results = []

    # Format the results
    formatted_blocks = []
    
    # 3. Add Character Stats if relevant keywords found
    stats_keywords = ["stats", "health", "health", "drive", "reversal", "jump", "dash", "speed", "throw"]
    wants_stats = any(k in text_lower for k in stats_keywords)
    if startup_alias_query and re.search(r"\b[1-9][0-9]*[a-zA-Z]{1,3}\b", text_lower):
        wants_stats = False
    if wants_frame_data and explicit_move_attempt:
        wants_stats = False
    
    if wants_stats:
        for char in mentioned_chars:
            if char in FRAME_STATS:
                s = FRAME_STATS[char]
                # Format specific stats or all of them? 
                # Let's provide the key ones: Health, Best Reversal, Dashes, Jumps
                # The user asked for "best reversal" specifically.
                reversal_name = s.get('bestReversal', '?')
                
                stats_block = (
                    f"**{char.capitalize()} Stats**\n"
                    f"Health: {s.get('health', '?')}\n"
                    f"Best Reversal: {reversal_name}\n"
                    f"Forward Dash: {s.get('fDash', '?')}f // Back Dash: {s.get('bDash', '?')}f\n"
                    f"Jump: {s.get('nJump', '?')}f\n"
                )
                formatted_blocks.append(stats_block)
                
                # RECURSIVE LOOKUP: If we have a best reversal name, fetch its REAL frame data
                # so the LLM doesn't hallucinate it.
                if reversal_name and reversal_name != '?':
                     # Try to find this move in the moves list
                     rev_row = lookup_frame_data(char, str(reversal_name))
                     if rev_row and rev_row not in results:
                         results.append(rev_row)

    # 4. AUTO-INJECT KEY MOVES (Context Injection)
    # If we have a character but NO specific moves found (e.g. "Help me with Ryu"),
    # the LLM will try to give advice about buttons. We MUST provide the data for those likely buttons
    # to prevent hallucinations (like saying 5MK is special cancellable when it isn't).
    viper_air_burnkick_query = bool(
        "c.viper" in mentioned_chars
        and re.search(
            r"\b(?:air|aerial)\s+burn(?:ing)?\s*kicks?\b"
            r"|\b(?:air|aerial)\s+burnkicks?\b"
            r"|\bburn(?:ing)?\s*kicks?\s+(?:air|aerial)\b"
            r"|\bburnkicks?\s+(?:air|aerial)\b"
            r"|\bj\.?\s*236k\b"
            r"|\b236k\s*(?:\(air\)|air|aerial)\b",
            text_lower,
        )
    )
    if viper_air_burnkick_query and query_has_explicit_strength and results:
        preferred_air_input = "air burn kick"
        if re.search(r"\b(?:od|ex|236kk)\b", text_lower):
            preferred_air_input = "od air burn kick"
        elif re.search(r"\b(?:h|heavy|hk|236hk)\b", text_lower):
            preferred_air_input = "h air burn kick"
        elif re.search(r"\b(?:m|medium|mk|236mk)\b", text_lower):
            preferred_air_input = "m air burn kick"
        elif re.search(r"\b(?:l|light|lk|236lk)\b", text_lower):
            preferred_air_input = "l air burn kick"

        preferred_air_row = lookup_frame_data("c.viper", preferred_air_input)
        if preferred_air_row and preferred_air_row not in results:
            results.insert(0, preferred_air_row)

        filtered_results = []
        for row in results:
            move_name = str(row.get("moveName", "")).lower()
            cmn_name = str(row.get("cmnName", "")).lower()
            num_cmd = str(row.get("numCmd", "")).lower()
            burnkick_row = "burn" in move_name or "burn" in cmn_name
            if not burnkick_row:
                filtered_results.append(row)
                continue
            if (
                "(air" in num_cmd
                or "air" in move_name
                or "air" in cmn_name
                or "aerial" in move_name
                or "aerial" in cmn_name
            ):
                filtered_results.append(row)
        if filtered_results:
            results = filtered_results

    if (
        wants_frame_data
        and mentioned_chars
        and not results
        and not target_combo_query
        and not special_prompt_blocks
        and not explicit_move_attempt
    ):
        key_moves = ["5MP", "5MK", "2MK", "5HP", "2HP", "5HK", "2HK"]
        for char in mentioned_chars:
            for km in key_moves:
                k_row = lookup_frame_data(char, km)
                if k_row and k_row not in results:
                    results.append(k_row)

    if (
        wants_frame_data
        and mentioned_chars
        and explicit_move_attempt
        and not results
        and not tc_prompt_blocks
        and not special_prompt_blocks
    ):
        missing_scrolls_query = True

    has_results = bool(results)

    if not wants_frame_data and (
        wants_info or (mentioned_chars and not has_results and not wants_bnb and not wants_stats)
    ):
        for char in mentioned_chars:
            if char in CHARACTER_INFO:
                info_blocks.append(
                    f"**{char.capitalize()} Overview:**\n{CHARACTER_INFO[char]}"
                )

    for move_data in results:
        def clean(val):
            return str(val).replace('*', ',')

        startup = clean(move_data.get('startup', '-'))
        active = clean(move_data.get('active', '-'))
        recovery = clean(move_data.get('recovery', '-')).replace('(', ' (Whiff: ')
        cancel = clean(move_data.get('xx', '-'))
        damage = clean(move_data.get('dmg', '-'))
        guard = clean(move_data.get('atkLvl', '-'))
        atk_range = format_attack_range_for_table(move_data)
        on_hit = clean(move_data.get('onHit', '-'))
        on_block = clean(move_data.get('onBlock', '-'))
        extra_info = clean(move_data.get('extraInfo', '-')).replace('[', '').replace(']', '').replace('"', '')
        
        # New Stats (Drive/Super)
        ddoh = clean(move_data.get('DDoH', '-'))
        ddob = clean(move_data.get('DDoB', '-'))
        dgain = clean(move_data.get('DGain', '-'))
        ssoh = clean(move_data.get('SelfSoH', '-'))
        ssob = clean(move_data.get('SelfSoB', '-'))
        
        gauge_info = (
             f"Drive Dmg: Hit {ddoh} / Block {ddob} // Drive Gain: {dgain}\n"
             f"Super Gain: Hit {ssoh} / Block {ssob}\n"
        )
        
        # Hit Confirm Data (Always Included)
        hc_sp = clean(move_data.get('hcWinSpCa', '-')).strip() or '-'
        hc_tc = clean(move_data.get('hcWinTc', '-')).strip() or '-'
        hc_notes = clean(move_data.get('hcWinNotes', '-')).replace('[', '').replace(']', '').replace('"', '').strip() or '-'
        hc_info = (
            f"Hit Confirm (Sp/Su): {hc_sp} // Hit Confirm (TC): {hc_tc}\n"
            f"Hit Confirm Notes: {hc_notes}\n"
        )

        # Stun Data (Always Included)
        hstun = clean(move_data.get('hitstun', '-'))
        bstun = clean(move_data.get('blockstun', '-'))
        stun_info = f"Stun Frames: Hit {hstun} // Block {bstun}\n"

        block = (
            f"**{move_data['moveName']} ({move_data['numCmd']})**\n"
            f"Character: {move_data.get('char_name', 'Unknown')}\n"
            f"Startup: {startup} // Active: {active} // Recovery: {recovery}\n"
            f"Cancel: {cancel}\n"
            f"Damage: {damage}\n"
            f"Guard: {guard}\n"
            f"Range: {atk_range}\n"
            f"On Hit: {on_hit} // On Block: {on_block}\n"
            f"{gauge_info}"
            f"{stun_info}"
            f"{hc_info}"
            f"Notes: {extra_info}"
        )
        formatted_blocks.append(block)

    if tc_prompt_blocks:
        formatted_blocks.extend(tc_prompt_blocks)
    if special_prompt_blocks:
        formatted_blocks.extend(special_prompt_blocks)
    
    sections = []
    if formatted_blocks:
        sections.append("\n\n".join(formatted_blocks))
    if info_blocks:
        sections.append("\n\n".join(info_blocks))
    if bnb_context:
        sections.append(bnb_context.strip())

    output = "\n\n---\n".join(sections)

    # Check for punish calculation
    punish_verdict = check_punish(text_lower, results)
    if punish_verdict:
        if output:
            output = punish_verdict + "\n\n---\n\n" + output
        else:
            output = punish_verdict

    has_frame_blocks = bool(formatted_blocks)
    has_combo_blocks = bool(bnb_context)
    has_overview_blocks = bool(info_blocks)
    if has_frame_blocks:
        mode = "frame"
    elif has_combo_blocks:
        mode = "combo"
    elif has_overview_blocks:
        mode = "overview"
    else:
        mode = "none"

    return {
        "data": output,
        "mode": mode,
        "rows": results,
        "startup_alias_query": startup_alias_query,
        "hitconfirm_alias_query": hitconfirm_alias_query,
        "super_gain_alias_query": super_gain_alias_query,
        "range_alias_query": range_alias_query,
        "wants_comparison": bool(wants_comparison),
        "property_only_query": property_only_query,
        "target_combo_query": target_combo_query,
        "missing_scrolls_query": missing_scrolls_query,
        "gif_query": gif_query,
        "explicit_move_attempt": explicit_move_attempt,
    }


def lookup_frame_data(character, move_input, _seen_inputs=None):
    """Search for a move in character's frame data by numCmd, plnCmd, or moveName."""
    move_input = str(move_input)
    seen_key = move_input.strip().lower()
    if _seen_inputs is None:
        _seen_inputs = set()
    if seen_key in _seen_inputs:
        return None
    _seen_inputs.add(seen_key)
    char_key = character.lower()
    if char_key not in FRAME_DATA:
        return None
    
    data = FRAME_DATA[char_key]
    move_input = normalize_jump_normal_text(move_input.lower().strip())

    def normalize_strength_word_shorthand(text):
        prefix_map = {"l": "light", "m": "medium", "h": "heavy"}

        def replace_prefix(match):
            token = match.group(1)
            rest = match.group(2)
            return f"{prefix_map[token]} {rest}"

        def replace_suffix(match):
            rest = match.group(1)
            token = match.group(2)
            return f"{rest} {prefix_map[token]}"

        text = re.sub(r"^(l|m|h)\s+(.+)$", replace_prefix, text)
        text = re.sub(r"^(.+)\s+(l|m|h)$", replace_suffix, text)
        return text

    move_input = normalize_strength_word_shorthand(move_input)

    def normalize_boomer_normal_notation(text):
        pattern = re.compile(
            r"\b(st|cr)\s*\.?\s*(lp|mp|hp|lk|mk|hk|l\s*p|m\s*p|h\s*p|l\s*k|m\s*k|h\s*k)\b"
        )

        def repl(match):
            stance = match.group(1).lower()
            button = re.sub(r"\s+", "", match.group(2).lower())
            prefix = "5" if stance == "st" else "2"
            return f"{prefix}{button}"

        return pattern.sub(repl, text)

    move_input = normalize_boomer_normal_notation(move_input)
    move_input = re.sub(r"^(?:7|9)\s*(lp|mp|hp|lk|mk|hk)$", r"jump \1", move_input)

    original_move_input = move_input
    query_requests_air_context = bool(re.search(r"\b(air|aerial)\b", original_move_input))
    query_requests_charged = bool(re.search(r"\b(charged|hold|held)\b", original_move_input))
    query_requests_sa1 = bool(
        re.search(r"\b(?:sa\s*1|super\s*art\s*1|super\s*1|level\s*1)\b", original_move_input)
    )
    query_requests_sa3 = bool(
        re.search(r"\b(?:sa\s*3|super\s*art\s*3|super\s*3|level\s*3)\b", original_move_input)
    )
    query_requests_ca = bool(re.search(r"\b(?:ca|critical\s+art)\b", original_move_input))
    stock_hint_tokens = ("stock", "stocked", "enhanced", "windclad")

    def token_is_stock_hint(token):
        token_norm = str(token or "").lower().strip()
        if not token_norm:
            return False
        if token_norm in stock_hint_tokens:
            return True
        return any(
            difflib.SequenceMatcher(None, token_norm, hint_token).ratio() >= 0.82
            for hint_token in stock_hint_tokens
        )

    query_requests_stocked = bool(
        re.search(r"\b(stock|stocked|enhanced|windclad|wind\s+clad)\b", original_move_input)
    ) or any(token_is_stock_hint(token) for token in re.findall(r"[a-z0-9]+", original_move_input))
    neutral_tokens = []
    input_tokens = re.findall(r"[a-z0-9]+", original_move_input)
    if (
        ("neutral" in input_tokens or "n" in input_tokens or "nj" in input_tokens)
        and ("jump" in input_tokens or "j" in input_tokens or "nj" in input_tokens)
    ):
        neutral_query = original_move_input
        neutral_query = re.sub(r"\bnj\b", "n jump", neutral_query)
        neutral_query = re.sub(r"\bneutral\b", "n", neutral_query)
        neutral_query = re.sub(r"\bj\b", "jump", neutral_query)
        neutral_query = re.sub(r"[^a-z0-9]+", " ", neutral_query)
        neutral_query = re.sub(r"\s+", " ", neutral_query).strip()
        if neutral_query:
            neutral_tokens = neutral_query.split()

    move_input = re.sub(r"^ex\s+", "od ", move_input)
    move_input = re.sub(r"\bdivekick\b", "dive kick", move_input)
    if not re.match(
        r"^(jump|j)[\s\.]+(?:(?:214|236|623|421|22|46|28|41236|63214)|(?:[123]\s*(?:lp|mp|hp|lk|mk|hk|p|k)))",
        move_input,
    ):
        move_input = re.sub(r"^(jump|j)[\s\.]+", "8", move_input)
    move_input = re.sub(
        r"^([1-9][0-9]*)\s*(?:\+)?\s*(lp|mp|hp|lk|mk|hk|pp|kk|p|k)$",
        r"\1\2",
        move_input,
    )

    def get_motion_suffixes(motion_digits):
        suffixes = set()
        for row in data:
            num_cmd = re.sub(r"\s+", "", str(row.get("numCmd", "")).lower())
            if not num_cmd.startswith(motion_digits):
                continue
            for suffix in ("lp", "mp", "hp", "lk", "mk", "hk", "pp", "kk"):
                if num_cmd.startswith(f"{motion_digits}{suffix}"):
                    suffixes.add(suffix)
        return suffixes

    def resolve_623_strength_suffix(strength_token, available_suffixes):
        token = strength_token.lower()
        explicit_suffix_map = {
            "lp": "lp",
            "mp": "mp",
            "hp": "hp",
            "lk": "lk",
            "mk": "mk",
            "hk": "hk",
        }
        if token in explicit_suffix_map:
            return explicit_suffix_map[token]

        strength_letter_map = {
            "l": "l",
            "m": "m",
            "h": "h",
            "light": "l",
            "medium": "m",
            "heavy": "h",
        }
        strength_letter = strength_letter_map.get(token)
        if not strength_letter:
            return None

        preferred_suffixes = {
            "l": ["lp", "lk"],
            "m": ["mp", "mk"],
            "h": ["hp", "hk"],
        }
        for suffix in preferred_suffixes[strength_letter]:
            if suffix in available_suffixes:
                return suffix

        fallback_suffixes = {
            "l": "lp",
            "m": "mp",
            "h": "hp",
        }
        return fallback_suffixes[strength_letter]

    def normalize_motion_strength_aliases(raw_input):
        normalized = re.sub(r"\s+", " ", raw_input).strip()
        motion_alias_pattern = r"(dp|srk|shoryu|shoryuken)"
        strength_token_pattern = r"(lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)"
        available_623_suffixes = get_motion_suffixes("623")

        od_motion_match = re.fullmatch(
            rf"(?:od|ex)\s*(?:\+)?\s*{motion_alias_pattern}",
            normalized,
        )
        if od_motion_match:
            if "pp" in available_623_suffixes:
                return "623pp"
            if "kk" in available_623_suffixes:
                return "623kk"
            return "623pp"

        strength_motion_match = re.fullmatch(
            rf"{strength_token_pattern}\s*(?:\+)?\s*{motion_alias_pattern}",
            normalized,
        )
        if strength_motion_match:
            strength_token = strength_motion_match.group(1)
            resolved_suffix = resolve_623_strength_suffix(
                strength_token,
                available_623_suffixes,
            )
            if resolved_suffix:
                return f"623{resolved_suffix}"
            return normalized

        motion_strength_match = re.fullmatch(
            rf"{motion_alias_pattern}\s*(?:\+)?\s*{strength_token_pattern}",
            normalized,
        )
        if motion_strength_match:
            strength_token = motion_strength_match.group(2)
            resolved_suffix = resolve_623_strength_suffix(
                strength_token,
                available_623_suffixes,
            )
            if resolved_suffix:
                return f"623{resolved_suffix}"

        return normalized

    def resolve_strength_special_input(raw_input):
        normalized = re.sub(r"\s+", " ", raw_input).strip().lower()
        if ">" in normalized or "->" in normalized:
            return normalized
        strength_map = {
            "light": ["lp", "lk"],
            "l": ["lp", "lk"],
            "medium": ["mp", "mk"],
            "m": ["mp", "mk"],
            "heavy": ["hp", "hk"],
            "h": ["hp", "hk"],
        }

        match = re.fullmatch(r"(light|medium|heavy|l|m|h)\s+(.+)", normalized)
        if not match:
            match = re.fullmatch(r"(.+)\s+(light|medium|heavy|l|m|h)", normalized)
            if not match:
                return normalized
            remainder = match.group(1).strip()
            strength_token = match.group(2)
        else:
            strength_token = match.group(1)
            remainder = match.group(2).strip()

        candidate_prefixes = strength_map.get(strength_token, [])
        if not candidate_prefixes:
            return normalized

        for prefix in candidate_prefixes:
            candidate = f"{prefix} {remainder}"
            candidate_compact = re.sub(r"[^a-z0-9]", "", candidate)
            for row in data:
                num_cmd = str(row.get("numCmd", "")).lower()
                pln_cmd = str(row.get("plnCmd", "")).lower()
                cmn_name = str(row.get("cmnName", "")).lower()
                move_name = str(row.get("moveName", "")).lower()
                if (
                    candidate == num_cmd
                    or candidate == pln_cmd
                    or candidate == cmn_name
                    or candidate in cmn_name
                    or candidate in move_name
                ):
                    return candidate
                cmn_compact = re.sub(r"[^a-z0-9]", "", cmn_name)
                move_compact = re.sub(r"[^a-z0-9]", "", move_name)
                if candidate_compact and (
                    candidate_compact in cmn_compact
                    or candidate_compact in move_compact
                ):
                    return candidate

        return normalized

    pre_strength_alias_input = move_input
    move_input = normalize_motion_strength_aliases(move_input)
    move_input = resolve_strength_special_input(move_input)

    combo_input = None
    if ">" in move_input or "->" in move_input:
        combo_input = re.sub(r"\s+", "", move_input.replace("->", ">"))

    def normalize_move_name_tokens(text):
        normalized = re.sub(r"[^a-z0-9]+", " ", str(text).lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized.split() if normalized else []

    def neutral_tokens_match(query_tokens, move_name_tokens):
        if not query_tokens:
            return False
        move_name_set = set(move_name_tokens)
        for token in query_tokens:
            if token == "jump":
                if not any(t == "j" or t.startswith("jump") for t in move_name_tokens):
                    return False
                continue
            if token == "n":
                if "n" not in move_name_set and "neutral" not in move_name_set:
                    return False
                continue
            if token not in move_name_set:
                return False
        return True

    def jump_tokens_match(query_tokens, move_name_tokens):
        if "jump" not in query_tokens:
            return False
        for token in query_tokens:
            if token in ("neutral", "n"):
                continue
            if token == "jump":
                if not any(t == "j" or t.startswith("jump") for t in move_name_tokens):
                    return False
                continue
            if token not in move_name_tokens:
                return False
        return True

    if "jump" in input_tokens:
        neutral_candidate = None
        for row in data:
            move_name_tokens = normalize_move_name_tokens(row.get("moveName", ""))
            if not move_name_tokens:
                continue
            if neutral_tokens:
                if neutral_tokens_match(neutral_tokens, move_name_tokens):
                    return row
                continue
            if not jump_tokens_match(input_tokens, move_name_tokens):
                continue
            if "neutral" in move_name_tokens or "n" in move_name_tokens:
                if neutral_candidate is None:
                    neutral_candidate = row
                continue
            return row
        if neutral_candidate:
            return neutral_candidate

    def normalize_num_cmd_for_lookup(value):
        normalized = re.sub(r"[\[\]\(\)\{\}]", "", str(value or "").lower())
        normalized = re.sub(r"\s+", "", normalized)
        return re.sub(r"[^a-z0-9>]", "", normalized)

    def normalize_num_cmd_generic_for_lookup(value):
        normalized = str(value or "").lower()
        normalized = re.sub(r"\([^)]*\)", "", normalized)
        normalized = re.sub(r"\[[^\]]*\]", "", normalized)
        normalized = re.sub(r"\{[^}]*\}", "", normalized)
        normalized = re.sub(r"\s+", "", normalized)
        return re.sub(r"[^a-z0-9>]", "", normalized)
    
    char_aliases = CHARACTER_INPUT_ALIASES.get(char_key, {})
    alias_lookup_candidates = []
    for candidate in (pre_strength_alias_input, move_input):
        candidate = str(candidate or "").strip().lower()
        if candidate and candidate not in alias_lookup_candidates:
            alias_lookup_candidates.append(candidate)

    def resolve_input_alias_chain(raw_value):
        current = str(raw_value or "").strip().lower()
        seen_alias_values = set()
        while current and current not in seen_alias_values:
            seen_alias_values.add(current)
            next_value = None
            if current in char_aliases:
                next_value = str(char_aliases[current]).strip().lower()
            elif current in INPUT_ALIASES:
                next_value = str(INPUT_ALIASES[current]).strip().lower()
            if not next_value or next_value == current:
                break
            current = next_value
        return current

    for candidate in alias_lookup_candidates:
        resolved_candidate = resolve_input_alias_chain(candidate)
        if resolved_candidate != candidate or candidate in char_aliases or candidate in INPUT_ALIASES:
            move_input = resolved_candidate
            break

    def resolve_fuzzy_alias_target(raw_input):
        raw_compact = re.sub(r"[^a-z0-9]", "", str(raw_input or "").lower())
        if len(raw_compact) < 4:
            return None

        alias_compact_to_target = {}
        for alias_key, alias_target in char_aliases.items():
            alias_compact = re.sub(r"[^a-z0-9]", "", str(alias_key or "").lower())
            if len(alias_compact) < 4:
                continue
            if alias_compact not in alias_compact_to_target:
                alias_compact_to_target[alias_compact] = str(alias_target)

        for alias_key, alias_target in INPUT_ALIASES.items():
            alias_compact = re.sub(r"[^a-z0-9]", "", str(alias_key or "").lower())
            if len(alias_compact) < 4:
                continue
            if alias_compact not in alias_compact_to_target:
                alias_compact_to_target[alias_compact] = str(alias_target)

        if not alias_compact_to_target:
            return None

        close_matches = difflib.get_close_matches(
            raw_compact,
            list(alias_compact_to_target.keys()),
            n=1,
            cutoff=0.82,
        )
        if not close_matches:
            return None
        return alias_compact_to_target.get(close_matches[0])

    def row_is_ca_variant(row):
        move_name = str(row.get("moveName", "")).lower()
        cmn_name = str(row.get("cmnName", "")).lower()
        num_cmd = str(row.get("numCmd", "")).lower()
        return (
            "critical art" in move_name
            or "critical art" in cmn_name
            or bool(re.search(r"\(\s*ca\s*\)", num_cmd))
        )

    def row_is_charged_variant(row):
        move_name = str(row.get("moveName", "")).lower()
        cmn_name = str(row.get("cmnName", "")).lower()
        num_cmd = str(row.get("numCmd", "")).lower()
        return (
            "charged" in move_name
            or "charged" in cmn_name
            or "hold" in move_name
            or "hold" in cmn_name
            or "(charged" in num_cmd
            or "(hold" in num_cmd
        )

    def row_is_stocked_variant(row):
        move_name = str(row.get("moveName", "")).lower()
        cmn_name = str(row.get("cmnName", "")).lower()
        num_cmd = str(row.get("numCmd", "")).lower()
        combined = f"{move_name} {cmn_name} {num_cmd}"
        if re.search(r"\b0\s*stocks?\b", combined):
            return False

        has_stock_count = bool(re.search(r"\b[1-9]\d*\s*stocks?\b", combined))
        has_stock_tag = "(stock" in move_name or "(stock" in cmn_name or "(stock" in num_cmd
        has_enhanced_tag = (
            "enhanced" in move_name
            or "enhanced" in cmn_name
            or "(enhanced" in num_cmd
        )
        has_windclad_tag = "windclad" in move_name or "windclad" in cmn_name
        has_wind_stock_hold = "wind stock" in cmn_name and (
            "(" in cmn_name or "(hold" in num_cmd
        )
        return (
            has_stock_count
            or has_stock_tag
            or has_enhanced_tag
            or has_windclad_tag
            or has_wind_stock_hold
        )

    def genericize_lookup_button_suffix(num_cmd_token):
        token = str(num_cmd_token or "")
        token = re.sub(r"(lp|mp|hp)$", "p", token)
        token = re.sub(r"(lk|mk|hk)$", "k", token)
        token = re.sub(r"pp$", "p", token)
        token = re.sub(r"kk$", "k", token)
        return token

    def build_strengthless_lookup_variants(raw_input):
        variants = []
        normalized = str(raw_input or "").lower().strip()
        if not normalized:
            return variants

        collapsed_numcmd = re.sub(r"(\d+)(lp|mp|hp)\b", r"\1p", normalized)
        collapsed_numcmd = re.sub(r"(\d+)(lk|mk|hk)\b", r"\1k", collapsed_numcmd)
        collapsed_numcmd = re.sub(r"(\d+)(pp)\b", r"\1p", collapsed_numcmd)
        collapsed_numcmd = re.sub(r"(\d+)(kk)\b", r"\1k", collapsed_numcmd)
        collapsed_numcmd = re.sub(r"\s+", " ", collapsed_numcmd).strip()
        if collapsed_numcmd and collapsed_numcmd != normalized:
            variants.append(collapsed_numcmd)

        stripped_strength = re.sub(
            r"\b(?:lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b",
            " ",
            normalized,
        )
        stripped_strength = re.sub(r"\s+", " ", stripped_strength).strip()
        if stripped_strength and stripped_strength != normalized and stripped_strength not in variants:
            variants.append(stripped_strength)

        stripped_after_collapse = re.sub(
            r"\b(?:lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b",
            " ",
            collapsed_numcmd,
        )
        stripped_after_collapse = re.sub(r"\s+", " ", stripped_after_collapse).strip()
        if (
            stripped_after_collapse
            and stripped_after_collapse != normalized
            and stripped_after_collapse not in variants
        ):
            variants.append(stripped_after_collapse)

        return variants
    move_input_compact = re.sub(r"[^a-z0-9]", "", move_input)
    move_input_num_cmd = normalize_num_cmd_for_lookup(move_input)
    move_input_num_cmd_generic = normalize_num_cmd_generic_for_lookup(move_input)
    move_input_has_numcmd_qualifier = bool(
        re.search(r"\b(air|hold|held|bomb|charged)\b", move_input)
        or any(ch in move_input for ch in "()[]{}")
    )

    if char_key == "akuma":
        if move_input in {"air sa1", "aerial sa1", "sa1 air", "air super art 1"}:
            move_input = "tenma gozanku"
        if move_input in {"air sa3", "aerial sa3", "sa3 air", "air super art 3"}:
            move_input = "sip of calamity"

    move_input_tigerless = move_input
    move_input_tigerless_compact = move_input_compact
    if char_key == "sagat":
        move_input_tigerless = re.sub(r"\btiger\b", "", move_input)
        move_input_tigerless = re.sub(r"\s+", " ", move_input_tigerless).strip()
        move_input_tigerless_compact = re.sub(r"[^a-z0-9]", "", move_input_tigerless)

    if char_key == "akuma" and move_input_num_cmd_generic == "236236k":
        akuma_super_rows = []
        for row in data:
            row_token = normalize_num_cmd_generic_for_lookup(row.get("numCmd", ""))
            if row_token == "236236k":
                akuma_super_rows.append(row)
        if akuma_super_rows:
            ca_rows = [row for row in akuma_super_rows if row_is_ca_variant(row)]
            air_rows = [
                row
                for row in akuma_super_rows
                if "air" in str(row.get("moveName", "")).lower()
                or "air" in str(row.get("cmnName", "")).lower()
                or "(air)" in str(row.get("numCmd", "")).lower()
                or "tenma" in str(row.get("moveName", "")).lower()
            ]
            non_air_non_ca_rows = [
                row
                for row in akuma_super_rows
                if row not in air_rows and row not in ca_rows
            ]

            if query_requests_ca and ca_rows:
                return ca_rows[0]
            if query_requests_air_context or query_requests_sa1:
                if air_rows:
                    return air_rows[0]
            if query_requests_sa3 and non_air_non_ca_rows:
                return non_air_non_ca_rows[0]
            if non_air_non_ca_rows:
                return non_air_non_ca_rows[0]
    
    # search priority: numCmd -> plnCmd -> moveName
    for row in data:
        num_cmd = str(row.get('numCmd', '')).lower()
        num_cmd_normalized = normalize_num_cmd_for_lookup(num_cmd)
        num_cmd_generic = normalize_num_cmd_generic_for_lookup(num_cmd)
        if combo_input and ">" in num_cmd:
            if re.sub(r"\s+", "", num_cmd) == combo_input:
                return row
        # exact match numCmd (5MP)
        if num_cmd == move_input:
            return row
        # strict normalized numCmd match (preserves annotation words)
        if move_input_num_cmd and num_cmd_normalized == move_input_num_cmd:
            return row
        # generic normalized numCmd match (drops annotation words, for convenience)
        if (
            not move_input_has_numcmd_qualifier
            and move_input_num_cmd_generic
            and num_cmd_generic == move_input_num_cmd_generic
        ):
            return row
        # prefix match for motion inputs (e.g., 623 -> 623LP)
        if move_input.isdigit() and len(move_input) == 3:
            if move_input == "623":
                exception_terms = DP_PREFIX_EXCEPTIONS.get(char_key, [])
                if exception_terms:
                    move_name = str(row.get("moveName", "")).lower()
                    if any(term in move_name for term in exception_terms):
                        continue
            if num_cmd.startswith(move_input) or num_cmd_generic.startswith(move_input):
                return row
        # exact match plnCmd (MP)
        if str(row.get('plnCmd', '')).lower() == move_input:
            return row
        # exact/contains match cmnName
        cmn_name = str(row.get('cmnName', '')).lower()
        if cmn_name == move_input or (len(move_input_compact) >= 3 and cmn_name and move_input in cmn_name):
            return row
        # fuzzy match moveName ("Stand MP")
        move_name = str(row.get('moveName', '')).lower()
        cmn_name_tigerless = cmn_name
        move_name_tigerless = move_name
        if len(move_input_compact) >= 3 and move_input in move_name:
            return row
        if char_key == "sagat" and move_input_tigerless:
            cmn_name_tigerless = re.sub(r"\btiger\b", "", cmn_name)
            cmn_name_tigerless = re.sub(r"\s+", " ", cmn_name_tigerless).strip()
            move_name_tigerless = re.sub(r"\btiger\b", "", move_name)
            move_name_tigerless = re.sub(r"\s+", " ", move_name_tigerless).strip()
            if cmn_name_tigerless == move_input_tigerless or (
                len(move_input_tigerless_compact) >= 3
                and cmn_name_tigerless
                and move_input_tigerless in cmn_name_tigerless
            ):
                return row
            if (
                len(move_input_tigerless_compact) >= 3
                and move_input_tigerless in move_name_tigerless
            ):
                return row
        if len(move_input_compact) >= 6:
            cmn_compact = re.sub(r"[^a-z0-9]", "", cmn_name)
            move_name_compact = re.sub(r"[^a-z0-9]", "", move_name)
            if (
                (cmn_compact and move_input_compact in cmn_compact)
                or move_input_compact in move_name_compact
            ):
                return row
            if char_key == "sagat" and len(move_input_tigerless_compact) >= 6:
                cmn_tigerless_compact = re.sub(r"[^a-z0-9]", "", cmn_name_tigerless)
                move_tigerless_compact = re.sub(r"[^a-z0-9]", "", move_name_tigerless)
                if (
                    (cmn_tigerless_compact and move_input_tigerless_compact in cmn_tigerless_compact)
                    or move_input_tigerless_compact in move_tigerless_compact
                ):
                    return row

    if query_requests_charged:
        base_chargeless_input = re.sub(
            r"\b(?:charged|hold|held)\b",
            " ",
            move_input,
        )
        base_chargeless_input = re.sub(r"\s+", " ", base_chargeless_input).strip()
        if base_chargeless_input and base_chargeless_input != move_input:
            base_row = lookup_frame_data(character, base_chargeless_input, _seen_inputs=_seen_inputs)
            if base_row:
                base_token = normalize_num_cmd_token(base_row.get("numCmd", ""))
                base_suffix = extract_button_suffix(base_token)
                charged_candidates = []
                for row in data:
                    if not row_is_charged_variant(row):
                        continue
                    row_token = normalize_num_cmd_token(row.get("numCmd", ""))
                    if row_token != base_token:
                        continue
                    charged_candidates.append(row)
                if charged_candidates:
                    if base_suffix:
                        for row in charged_candidates:
                            row_suffix = extract_button_suffix(normalize_num_cmd_token(row.get("numCmd", "")))
                            if row_suffix == base_suffix:
                                return row
                    return charged_candidates[0]

                base_generic_token = genericize_lookup_button_suffix(base_token)
                generic_channel = ""
                if base_suffix in {"lp", "mp", "hp", "pp", "p"}:
                    generic_channel = "p"
                elif base_suffix in {"lk", "mk", "hk", "kk", "k"}:
                    generic_channel = "k"

                generic_charged_candidates = []
                for row in data:
                    if not row_is_charged_variant(row):
                        continue
                    row_token = normalize_num_cmd_token(row.get("numCmd", ""))
                    if genericize_lookup_button_suffix(row_token) != base_generic_token:
                        continue
                    generic_charged_candidates.append(row)
                if generic_charged_candidates:
                    if generic_channel:
                        for row in generic_charged_candidates:
                            row_suffix = extract_button_suffix(normalize_num_cmd_token(row.get("numCmd", "")))
                            if row_suffix == generic_channel:
                                return row
                    return generic_charged_candidates[0]

    for strengthless_input in build_strengthless_lookup_variants(move_input):
        strengthless_row = lookup_frame_data(character, strengthless_input, _seen_inputs=_seen_inputs)
        if strengthless_row is not None:
            return strengthless_row

    if query_requests_stocked:
        base_stockless_input = re.sub(
            r"\b(?:stocked|stock|enhanced|windclad|wind\s+clad)\b",
            " ",
            move_input,
        )
        base_stockless_input = re.sub(r"\s+", " ", base_stockless_input).strip()
        if base_stockless_input and base_stockless_input != move_input:
            base_row = lookup_frame_data(character, base_stockless_input, _seen_inputs=_seen_inputs)
            if base_row:
                base_token = normalize_num_cmd_token(base_row.get("numCmd", ""))
                base_suffix = extract_button_suffix(base_token)
                stocked_candidates = []
                for row in data:
                    if not row_is_stocked_variant(row):
                        continue
                    row_token = normalize_num_cmd_token(row.get("numCmd", ""))
                    if row_token != base_token:
                        continue
                    stocked_candidates.append(row)
                if stocked_candidates:
                    if base_suffix:
                        for row in stocked_candidates:
                            row_suffix = extract_button_suffix(normalize_num_cmd_token(row.get("numCmd", "")))
                            if row_suffix == base_suffix:
                                return row
                    return stocked_candidates[0]

    if len(move_input_compact) >= 4:
        fuzzy_candidates = []
        for row in data:
            move_name = str(row.get("moveName", "")).lower()
            cmn_name = str(row.get("cmnName", "")).lower()
            for candidate in (move_name, cmn_name):
                candidate_compact = re.sub(r"[^a-z0-9]", "", candidate)
                if len(candidate_compact) >= 4:
                    fuzzy_candidates.append((candidate_compact, row))

        if fuzzy_candidates:
            choices = [candidate for candidate, _ in fuzzy_candidates]
            close = difflib.get_close_matches(move_input_compact, choices, n=1, cutoff=0.86)
            if close:
                matched = close[0]
                for candidate, row in fuzzy_candidates:
                    if candidate == matched:
                        return row

    fuzzy_alias_target = resolve_fuzzy_alias_target(move_input)
    if fuzzy_alias_target and fuzzy_alias_target != move_input:
        fuzzy_alias_row = lookup_frame_data(character, fuzzy_alias_target, _seen_inputs=_seen_inputs)
        if fuzzy_alias_row is not None:
            return fuzzy_alias_row

    return None



def check_punish(text_lower, results):
    """Calculate if Move B can punish Move A based on frame advantage."""
    # Only trigger on punish-related queries
    punish_keywords = ['punish', 'punishable', 'can i punish', 'is it punishable']
    if not any(kw in text_lower for kw in punish_keywords):
        return None
    
    # If only one move is identified, provide basic safety guidance
    if len(results) < 2:
        move_a = results[0] if results else None
        if not move_a:
            return None
        try:
            on_block_raw = str(move_a.get("onBlock", "0"))
            on_block_clean = on_block_raw.replace("+", "").strip()
            if not on_block_clean.lstrip("-").isdigit():
                return (
                    f"Cannot calculate punish: {move_a['moveName']} has non-numeric block advantage "
                    f"({on_block_raw})."
                )
            on_block = int(on_block_clean)
        except Exception as e:
            return f"Punish calculation error: {e}"

        move_a_name = f"{move_a.get('char_name', 'Unknown')}'s {move_a['moveName']}"
        frame_advantage = max(-on_block, 0)
        if on_block >= -3:
            return (
                f"**PUNISH CALCULATION**\n"
                f"{move_a_name} is **{on_block}** on block.\n\n"
                f"NO: This is **safe on block**. Moves that are -3 or better cannot be "
                f"punished by normal attacks."
            )
        return (
            f"**PUNISH CALCULATION**\n"
            f"{move_a_name} is **{on_block}** on block.\n\n"
            f"This is punishable **if** your move's startup is **≤{frame_advantage}f** and you're in range."
        )
    
    # Assume first move = blocked move (Move A), second = punish attempt (Move B)
    move_a = results[0]
    move_b = results[1]
    
    try:
        # Extract on_block from Move A (e.g. "-8")
        on_block_raw = str(move_a.get('onBlock', '0'))
        # Handle edge cases like "KD", "+5", "-8"
        on_block_clean = on_block_raw.replace('+', '').strip()
        if on_block_clean.lstrip('-').isdigit():
            on_block = int(on_block_clean)
        else:
            # Non-numeric (e.g. "KD") - can't calculate
            return f"Cannot calculate punish: {move_a['moveName']} has non-numeric block advantage ({on_block_raw})."
        
        # Extract startup from Move B (e.g. "5")
        startup_raw = str(move_b.get('startup', '0'))
        # Handle multi-hit like "3+5" - use first number
        startup_clean = startup_raw.split('+')[0].split('~')[0].split('(')[0].strip()
        if startup_clean.isdigit():
            startup = int(startup_clean)
        else:
            return f"Cannot calculate punish: {move_b['moveName']} has non-numeric startup ({startup_raw})."
        
        move_a_name = f"{move_a.get('char_name', 'Unknown')}'s {move_a['moveName']}"
        move_b_name = f"{move_b.get('char_name', 'Unknown')}'s {move_b['moveName']}"
        
        # Punish logic: defender frame advantage = -on_block (when negative)
        # If startup <= frame advantage, punishable (range still matters).
        frame_advantage = max(-on_block, 0)
        is_punishable = on_block <= -4 and frame_advantage >= startup
        if is_punishable:
            return (
                f"**PUNISH CALCULATION**\n"
                f"{move_a_name} is **{on_block}** on block.\n"
                f"{move_b_name} has **{startup}f startup**.\n\n"
                f"YES: This is punishable numerically speaking, "
                f"but my scrolls do not contain data on pushback so I cannot comment on range."
            )
        else:
            return (
                f"**PUNISH CALCULATION**\n"
                f"{move_a_name} is **{on_block}** on block.\n"
                f"{move_b_name} has **{startup}f startup**.\n\n"
                f"NO: {move_a_name} cannot be punished by {move_b_name}.\n"
                f"{move_b_name} startup must be **≤{frame_advantage}f** to punish, and the character must be in range."
            )
    except Exception as e:
        return f"Punish calculation error: {e}"


        filtered_lines.append(stripped)

    cleaned = "\n".join(filtered_lines).strip()
    if cleaned:
        return cleaned

    sentence_candidates = re.split(r"(?<=[.!?])\s+", raw)
    for sentence in sentence_candidates:
        sentence = sentence.strip()
        if sentence:
            return sentence
    return "Noted. The relevant frame data is in the embeds above."
# message queue - initialized in on_ready to avoid event loop issues
message_queue = None
worker_task = None
background_task_handle = None
background_encouragement_task_handle = None
background_damn_gg_task_handle = None
background_streetfighterdle_task_handle = None
background_streetfighterdle_leaderboard_task_handle = None
reminder_task_handle = None
web_server_task = None
_TYPING_DISABLED = False
LAST_DAILY_VIDEO_ID = {}
SPECIAL_STRENGTH_PROMPT_MODE = {}
SPECIAL_STRENGTH_PROMPT_MODE_MAX = 300

reminder_manager = ReminderManager(
    client,
    truncate_message,
    build_reminder_ack_text,
    build_reminder_fire_text,
)
scheduler_manager = SchedulerManager(
    client=client,
    channel_id=CHANNEL_ID,
    daily_encouragement_messages=DAILY_ENCOURAGEMENT_MESSAGES,
    daily_damn_gg_text=DAILY_DAMN_GG_TEXT,
    daily_streetfighterdle_messages=DAILY_STREETFIGHTERDLE_MESSAGES,
    streetfighterdle_url=STREETFIGHTERDLE_URL,
    streetfighterdle_score_source_channel_id=STREETFIGHTERDLE_SCORE_SOURCE_CHANNEL_ID,
    build_streetfighterdle_reminder_text=build_streetfighterdle_reminder_text,
    collect_streetfighterdle_daily_scores=collect_streetfighterdle_daily_scores,
    save_streetfighterdle_score_snapshot=save_streetfighterdle_score_snapshot,
    build_streetfighterdle_leaderboard_text=build_streetfighterdle_leaderboard_text,
    send_generated_encouragement=send_generated_encouragement,
    strip_discord_mentions=strip_discord_mentions,
    memory_file=MEMORY_FILE,
    memory_max_entries=MEMORY_MAX_ENTRIES,
    memory_context_max_messages=MEMORY_CONTEXT_MAX_MESSAGES,
    encouragement_context_chance=ENCOURAGEMENT_CONTEXT_CHANCE,
    encouragement_context_source=ENCOURAGEMENT_CONTEXT_SOURCE,
)


def check_quiz_answer(quiz_state, text):
    return quiz_module.check_quiz_answer(quiz_state, text)


compact_move_token = gif_lookup_module.compact_move_token
normalize_num_cmd_token = gif_lookup_module.normalize_num_cmd_token
extract_button_suffix = gif_lookup_module.extract_button_suffix
parse_local_hitbox_gif_filename = gif_lookup_module.parse_local_hitbox_gif_filename
load_local_hitbox_gif_data = gif_lookup_module.load_local_hitbox_gif_data
get_existing_local_gif_asset_paths = gif_lookup_module.get_existing_local_gif_asset_paths
normalize_move_name_for_gif_text = gif_lookup_module.normalize_move_name_for_gif_text
move_name_match_tokens = gif_lookup_module.move_name_match_tokens
build_num_cmd_candidates_for_gif = gif_lookup_module.build_num_cmd_candidates_for_gif
lookup_hitbox_gif_link = gif_lookup_module.lookup_hitbox_gif_link
collect_hitbox_gif_links = gif_lookup_module.collect_hitbox_gif_links
find_characters_in_text = gif_lookup_module.find_characters_in_text
remove_first_token_sequence = gif_lookup_module.remove_first_token_sequence
extract_gif_move_query_text = gif_lookup_module.extract_gif_move_query_text
resolve_hitbox_gif_query_alias = gif_lookup_module.resolve_hitbox_gif_query_alias
lookup_hitbox_gif_links_from_query = gif_lookup_module.lookup_hitbox_gif_links_from_query
collect_hitbox_gif_links_from_text = gif_lookup_module.collect_hitbox_gif_links_from_text

get_attack_range_details = frame_output_module.get_attack_range_details
format_attack_range_for_table = frame_output_module.format_attack_range_for_table
format_frame_data = frame_output_module.format_frame_data
format_property_only_lines = frame_output_module.format_property_only_lines
format_startup_only_reply = frame_output_module.format_startup_only_reply
format_hitconfirm_only_reply = frame_output_module.format_hitconfirm_only_reply
format_super_gain_only_reply = frame_output_module.format_super_gain_only_reply
format_range_only_reply = frame_output_module.format_range_only_reply
truncate_embed_value = frame_output_module.truncate_embed_value
is_missing_embed_value = frame_output_module.is_missing_embed_value
clean_embed_value = frame_output_module.clean_embed_value
add_embed_field = frame_output_module.add_embed_field
format_hit_block_value = frame_output_module.format_hit_block_value
build_frame_embed = frame_output_module.build_frame_embed
iter_unique_frame_rows = frame_output_module.iter_unique_frame_rows
build_frame_embeds = frame_output_module.build_frame_embeds
sanitize_embed_followup_text = frame_output_module.sanitize_embed_followup_text


def configure_extracted_modules():
    gif_lookup_module.configure(
        CHARACTER_ALIASES=CHARACTER_ALIASES,
        FRAME_DATA=FRAME_DATA,
        HITBOX_GIF_DATA=HITBOX_GIF_DATA,
        LOCAL_HITBOX_GIF_ROOT=LOCAL_HITBOX_GIF_ROOT,
        LOCAL_HITBOX_GIF_EXTENSIONS=LOCAL_HITBOX_GIF_EXTENSIONS,
        normalize_char_name=normalize_char_name,
        resolve_character_key=resolve_character_key,
        iter_unique_frame_rows=frame_output_module.iter_unique_frame_rows,
        strip_discord_mentions=strip_discord_mentions,
        find_moves_in_text=find_moves_in_text,
        lookup_frame_data=lookup_frame_data,
    )
    frame_output_module.configure(
        is_missing_attack_range_value=is_missing_attack_range_value,
        truncate_message=truncate_message,
        send_deleted_message_failsafe=send_deleted_message_failsafe,
        get_frame_row_gif_links=gif_lookup_module.get_frame_row_gif_links,
        get_existing_local_gif_asset_paths=gif_lookup_module.get_existing_local_gif_asset_paths,
        is_deleted_message_reference_error=is_deleted_message_reference_error,
        RANGE_SCROLLS_MISSING_TEXT=RANGE_SCROLLS_MISSING_TEXT,
    )

def remember_special_strength_prompt_mode(message_id, mode):
    if not message_id or not mode:
        return
    SPECIAL_STRENGTH_PROMPT_MODE[int(message_id)] = str(mode)
    while len(SPECIAL_STRENGTH_PROMPT_MODE) > SPECIAL_STRENGTH_PROMPT_MODE_MAX:
        oldest_key = next(iter(SPECIAL_STRENGTH_PROMPT_MODE))
        SPECIAL_STRENGTH_PROMPT_MODE.pop(oldest_key, None)


def is_deleted_message_reference_error(error):
    if isinstance(error, discord.NotFound):
        return True
    if isinstance(error, discord.HTTPException):
        text = str(error).lower()
        if "message_reference" in text and "unknown message" in text:
            return True
    return False


def ensure_message_queue_started():
    global message_queue
    global worker_task
    if message_queue is None:
        message_queue = asyncio.Queue()
    if worker_task is None or worker_task.done():
        worker_task = asyncio.create_task(worker())
    return message_queue

async def worker():
    global _TYPING_DISABLED
    print("Worker started...")
    while True:
        # get msg from queue
        queue = message_queue
        if queue is None:
            queue = asyncio.Queue()
        ctx = await queue.get()
        if len(ctx) == 6:
            message, llm_messages, fallback_reply, reply_prefix, reply_embeds, reply_embed_rows = ctx
        elif len(ctx) == 5:
            message, llm_messages, fallback_reply, reply_prefix, reply_embeds = ctx
            reply_embed_rows = []
        elif len(ctx) == 4:
            message, llm_messages, fallback_reply, reply_prefix = ctx
            reply_embeds = []
            reply_embed_rows = []
        elif len(ctx) == 3:
            message, llm_messages, fallback_reply = ctx
            reply_prefix = None
            reply_embeds = []
            reply_embed_rows = []
        else:
            message, llm_messages = ctx
            fallback_reply = None
            reply_prefix = None
            reply_embeds = []
            reply_embed_rows = []

        embeds_sent = False
        try:
            memory_context = build_memory_context(MEMORY_FILE, max_entries=10, char_budget=1400)
            if memory_context:
                insert_at = 1 if llm_messages and llm_messages[0].get("role") == "system" else 0
                llm_messages = (
                    llm_messages[:insert_at]
                    + [
                        {"role": "user", "content": f"Long-term Discord memory:\n{memory_context}"},
                        {"role": "assistant", "content": "Understood. I will keep that memory in mind."},
                    ]
                    + llm_messages[insert_at:]
                )

            # extract user query and determine if search should be used
            user_query = ""
            for msg in llm_messages:
                if msg.get("role") == "user":
                    candidate_query = str(msg.get("content", "") or "")
                    if candidate_query.startswith("Long-term Discord memory:"):
                        continue
                    candidate_query = re.sub(r"^Prompting user:.*?(?:\n|$)", "", candidate_query, count=1, flags=re.IGNORECASE)
                    candidate_query = re.sub(r"^User message:\s*", "", candidate_query, count=1, flags=re.IGNORECASE)
                    candidate_query = candidate_query.strip()
                    user_query = candidate_query
                    break
            enable_search = should_use_search(user_query)
            if enable_search:
                print(f"Google Search enabled for query: {user_query[:50]}...")

            async def _do_reply_work():
                if reply_embeds:
                    try:
                        await send_frame_embeds_with_views(
                            message.channel,
                            reply_embed_rows,
                            embeds=reply_embeds,
                        )
                        nonlocal embeds_sent
                        embeds_sent = True
                        asyncio.create_task(
                            capture_message_exchange_memory(
                                MEMORY_FILE,
                                MEMORY_MAX_ENTRIES,
                                MEMORY_CONTEXT_MAX_MESSAGES,
                                MEMORY_CONTEXT_CHAR_BUDGET,
                                message,
                                strip_discord_mentions,
                                bot_user=client.user,
                                source_label="worker-embed",
                            )
                        )
                    except Exception as embed_error:
                        print(f"Embed send failed: {embed_error}", flush=True)
                    return

                reply_text = await get_llm_response(llm_messages, enable_search=enable_search)
                final_reply = f"{reply_prefix}\n\n{reply_text}" if reply_prefix else reply_text
                try:
                    await message.reply(final_reply)
                    asyncio.create_task(
                        capture_message_exchange_memory(
                            MEMORY_FILE,
                            MEMORY_MAX_ENTRIES,
                            MEMORY_CONTEXT_MAX_MESSAGES,
                            MEMORY_CONTEXT_CHAR_BUDGET,
                            message,
                            strip_discord_mentions,
                            bot_user=client.user,
                            source_label="worker-reply",
                        )
                    )
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Worker reply target deleted before send. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        raise

            if _TYPING_DISABLED:
                await _do_reply_work()
            else:
                try:
                    async with message.channel.typing():
                        await _do_reply_work()
                except Exception as typing_err:
                    print(f"Typing indicator failed, disabling for session: {typing_err}", flush=True)
                    _TYPING_DISABLED = True
                    await _do_reply_work()
        except Exception as e:
            print(f"Worker error: {e}")
            error_detail = str(e)
            try:
                if reply_embeds:
                    if not embeds_sent:
                        try:
                            await send_frame_embeds_with_views(
                                message.channel,
                                reply_embed_rows,
                                embeds=reply_embeds,
                            )
                        except Exception as embed_error:
                            print(f"Worker embed error send failed: {embed_error}", flush=True)
                else:
                    if fallback_reply:
                        error_reply = f"{fallback_reply}\n\ fuck you Error: {error_detail}"
                        if reply_prefix and fallback_reply != reply_prefix:
                            error_reply = f"{reply_prefix}\n\n{error_reply}"
                        await message.reply(error_reply)
                    else:
                        if reply_prefix:
                            await message.reply(f"{reply_prefix}\n\ fuck you error: {error_detail}")
                        else:
                            await message.reply(f" fuck you error: {error_detail}")
            except Exception as reply_error:
                if not reply_embeds and is_deleted_message_reference_error(reply_error):
                    print("Worker error reply target deleted. Triggering failsafe.", flush=True)
                    await send_deleted_message_failsafe(message.channel)
                    continue
                print(f"Worker fallback reply error: {reply_error}", flush=True)
        finally:
            queue.task_done()

@client.event
async def on_ready():
    global message_queue
    global worker_task
    global background_task_handle
    global background_encouragement_task_handle
    global background_damn_gg_task_handle
    global background_streetfighterdle_task_handle
    global background_streetfighterdle_leaderboard_task_handle
    global reminder_task_handle
    global web_server_task
    print(f'Logged in as {client.user}')
    for guild in client.guilds:
        try:
            tree.clear_commands(guild=guild)
            tree.copy_global_to(guild=guild)
            await tree.sync(guild=guild)
            print(f"[menu] Slash commands synced to guild: {guild.name} ({guild.id})", flush=True)
        except Exception as e:
            print(f"[menu] Guild sync error for {guild.name}: {e}", flush=True)
    try:
        tree.clear_commands(guild=None)
        await tree.sync()
        print("[menu] Global slash commands cleared; using guild-scoped commands only.", flush=True)
    except Exception as e:
        print(f"[menu] Global slash command clear error: {e}", flush=True)
    # create queue in the correct event loop
    ensure_message_queue_started()
    # Disabled by request: daily "Hello everyone / How are you today? / Has anyone improved?" batch.
    # Re-enable by uncommenting this block.
    # if background_task_handle is None or background_task_handle.done():
    #     background_task_handle = client.loop.create_task(scheduler_manager.background_task())
    # start encouragement task
    if background_encouragement_task_handle is None or background_encouragement_task_handle.done():
        background_encouragement_task_handle = client.loop.create_task(scheduler_manager.background_encouragement_task())
    # Disabled by request: scheduled "damn gg" message.
    # Re-enable by uncommenting this block.
    # if background_damn_gg_task_handle is None or background_damn_gg_task_handle.done():
    #     background_damn_gg_task_handle = client.loop.create_task(scheduler_manager.background_damn_gg_task())
    # start streetfighterdle reminder task
    if background_streetfighterdle_task_handle is None or background_streetfighterdle_task_handle.done():
        background_streetfighterdle_task_handle = client.loop.create_task(scheduler_manager.background_streetfighterdle_task())
    # start streetfighterdle leaderboard task
    if background_streetfighterdle_leaderboard_task_handle is None or background_streetfighterdle_leaderboard_task_handle.done():
        background_streetfighterdle_leaderboard_task_handle = client.loop.create_task(scheduler_manager.background_streetfighterdle_leaderboard_task())
    # start worker
    ensure_message_queue_started()
    # start web server
    if web_server_task is None or web_server_task.done():
        web_server_task = client.loop.create_task(scheduler_manager.start_web_server())
    # start reminder loop
    if reminder_task_handle is None or reminder_task_handle.done():
        reminder_task_handle = client.loop.create_task(reminder_manager.reminder_loop())
        print("Reminder loop task created.", flush=True)
    print(
        "[scheduler] Expected behavior active: daily 'do the thing' batch disabled; "
        "scheduled 'damn gg' disabled; "
        f"{DAILY_ENCOURAGEMENT_MESSAGES} scheduled LLM encouragements per day; "
        "1 Streetfighterdle leaderboard at 23:00 UTC and 1 reminder at 00:00 UTC per day.",
        flush=True,
    )
    ensure_memory_file_exists(MEMORY_FILE)
    print(f"[memory] loaded entries={len(load_memory_entries(MEMORY_FILE))}", flush=True)
    load_frame_data()
    ggst_module.load_frame_data()
    tuco_module.load_frame_data()
    bbcf_module.load_frame_data()
    cotw_module.load_frame_data()
    third_strike_module.load_frame_data()
    mk1_module.load_frame_data()
    configure_extracted_modules()
    quiz_module.configure(
        FRAME_DATA=FRAME_DATA,
        CHARACTER_ALIASES=CHARACTER_ALIASES,
        GAME_QUIZ_CONFIGS={
            "sf6": {
                "label": "Street Fighter 6",
                "data": FRAME_DATA,
                "aliases": CHARACTER_ALIASES,
                "resolve_character_key": resolve_character_key,
                "lookup_frame_data": lookup_frame_data,
                "find_moves_in_text": find_moves_in_text,
                "build_frame_embed": build_frame_embed,
                "get_notes_text": frame_output_module.get_notes_text,
                "game_terms": ("sf6", "street fighter 6"),
            },
            "ggst": {
                "label": "Guilty Gear Strive",
                "data": ggst_module.GGST_FRAME_DATA,
                "aliases": ggst_module.GGST_CHARACTER_ALIASES,
                "resolve_character_key": ggst_module.resolve_character_key,
                "find_moves_in_text": ggst_module.find_moves_in_text,
                "build_frame_embed": ggst_module.build_frame_embed,
                "get_notes_text": ggst_module.get_notes_text,
                "game_terms": ("ggst", "guilty gear strive"),
            },
            "tuco": {
                "label": "2XKO",
                "data": tuco_module.TUCO_FRAME_DATA,
                "aliases": tuco_module.TUCO_CHARACTER_ALIASES,
                "resolve_character_key": tuco_module.resolve_character_key,
                "find_moves_in_text": tuco_module.find_moves_in_text,
                "build_frame_embed": tuco_module.build_frame_embed,
                "get_notes_text": tuco_module.get_notes_text,
                "game_terms": ("2xko", "tuco"),
            },
            "bbcf": {
                "label": "BlazBlue Central Fiction",
                "data": bbcf_module.BBCF_FRAME_DATA,
                "aliases": bbcf_module.BBCF_CHARACTER_ALIASES,
                "resolve_character_key": bbcf_module.resolve_character_key,
                "find_moves_in_text": bbcf_module.find_moves_in_text,
                "build_frame_embed": bbcf_module.build_frame_embed,
                "get_notes_text": bbcf_module.get_notes_text,
                "game_terms": ("bbcf", "blazblue central fiction"),
            },
            "cotw": {
                "label": "City of the Wolves",
                "data": cotw_module.COTW_FRAME_DATA,
                "aliases": cotw_module.COTW_CHARACTER_ALIASES,
                "resolve_character_key": cotw_module.resolve_character_key,
                "find_moves_in_text": cotw_module.find_moves_in_text,
                "build_frame_embed": cotw_module.build_frame_embed,
                "get_notes_text": cotw_module.get_notes_text,
                "game_terms": ("cotw", "city of the wolves"),
            },
            "third_strike": {
                "label": "Third Strike",
                "data": third_strike_module.THIRD_STRIKE_FRAME_DATA,
                "aliases": third_strike_module.THIRD_STRIKE_CHARACTER_ALIASES,
                "resolve_character_key": third_strike_module.resolve_character_key,
                "find_moves_in_text": third_strike_module.find_moves_in_text,
                "build_frame_embed": third_strike_module.build_frame_embed,
                "get_notes_text": third_strike_module.get_notes_text,
                "game_terms": ("3s", "third strike"),
            },
            "mk1": {
                "label": "Mortal Kombat 1",
                "data": mk1_module.MK1_FRAME_DATA,
                "aliases": mk1_module.MK1_CHARACTER_ALIASES,
                "resolve_character_key": mk1_module.resolve_character_key,
                "find_moves_in_text": mk1_module.find_moves_in_text,
                "build_frame_embed": mk1_module.build_frame_embed,
                "get_notes_text": mk1_module.get_notes_text,
                "game_terms": ("mk1", "mortal kombat 1"),
            },
        },
        resolve_character_key=resolve_character_key,
        normalize_char_name=normalize_char_name,
        lookup_frame_data=lookup_frame_data,
        find_moves_in_text=find_moves_in_text,
        is_missing_attack_range_value=is_missing_attack_range_value,
        clean_embed_value=clean_embed_value,
        truncate_embed_value=truncate_embed_value,
        build_frame_embed=build_frame_embed,
        strip_discord_mentions=strip_discord_mentions,
    )
    quiz_module.load_quiz_leaderboard()
    print(
        f"[quiz] global leaderboard loaded entries={len(quiz_module.QUIZ_GLOBAL_LEADERBOARD)}",
        flush=True,
    )
    menu_system.configure(
        frame_data=FRAME_DATA,
        character_aliases=CHARACTER_ALIASES,
        ggst_frame_data=ggst_module.GGST_FRAME_DATA,
        ggst_character_aliases=ggst_module.GGST_CHARACTER_ALIASES,
        ggst_supplemental_frame_data=ggst_module.GGST_SUPPLEMENTAL_FRAME_DATA,
        ggst_state_frame_data=ggst_module.GGST_STATE_FRAME_DATA,
        tuco_frame_data=tuco_module.TUCO_FRAME_DATA,
        tuco_character_aliases=tuco_module.TUCO_CHARACTER_ALIASES,
        bbcf_frame_data=bbcf_module.BBCF_FRAME_DATA,
        bbcf_character_aliases=bbcf_module.BBCF_CHARACTER_ALIASES,
        cotw_frame_data=cotw_module.COTW_FRAME_DATA,
        cotw_character_aliases=cotw_module.COTW_CHARACTER_ALIASES,
        third_strike_frame_data=third_strike_module.THIRD_STRIKE_FRAME_DATA,
        third_strike_character_aliases=third_strike_module.THIRD_STRIKE_CHARACTER_ALIASES,
        mk1_frame_data=mk1_module.MK1_FRAME_DATA,
        mk1_character_aliases=mk1_module.MK1_CHARACTER_ALIASES,
        mk1_combo_data=mk1_module.MK1_COMBO_DATA,
        quiz_module_ref=quiz_module,
        build_sf6_frame_embed_fn=build_frame_embed,
        build_ggst_frame_embed_fn=ggst_module.build_frame_embed,
        build_tuco_frame_embed_fn=tuco_module.build_frame_embed,
        build_bbcf_frame_embed_fn=bbcf_module.build_frame_embed,
        build_cotw_frame_embed_fn=cotw_module.build_frame_embed,
        build_third_strike_frame_embed_fn=third_strike_module.build_frame_embed,
        send_frame_embeds_with_views_fn=send_frame_embeds_with_views,
    )
    print("[menu] Menu system configured.", flush=True)

@client.event
async def on_message(message):
    # ignore bot msgs
    if message.author == client.user:
        return

    content_raw = message.content or ""
    content_no_mentions = strip_discord_mentions(content_raw)
    content_lower = content_no_mentions.lower()

    # Disabled by request: manual trigger for the old daily "Hello everyone" batch.
    # Re-enable by uncommenting this block.
    # if client.user.mentioned_in(message) and "do the thing" in content_lower:
    #     print(f"[daily-message] Manual trigger received from user_id={message.author.id}", flush=True)
    #     await scheduler_manager.send_daily_messages(message.channel)
    #     return

    if client.user.mentioned_in(message) and content_lower.strip() == "menu":
        await menu_system.send_main_menu(message.channel, owner_id=message.author.id)
        return

    if client.user.mentioned_in(message) and re.fullmatch(r"\s*(?:.+\s+)?moves\s*", content_lower):
        sf6_char_key = resolve_character_from_aliases_in_text(
            content_lower,
            CHARACTER_ALIASES,
            FRAME_DATA.keys(),
        )
        ggst_char_key = resolve_character_from_aliases_in_text(
            content_lower,
            ggst_module.GGST_CHARACTER_ALIASES,
            ggst_module.GGST_FRAME_DATA.keys(),
        )
        tuco_char_key = resolve_character_from_aliases_in_text(
            content_lower,
            tuco_module.TUCO_CHARACTER_ALIASES,
            tuco_module.TUCO_FRAME_DATA.keys(),
        )
        bbcf_char_key = resolve_character_from_aliases_in_text(
            content_lower,
            bbcf_module.BBCF_CHARACTER_ALIASES,
            bbcf_module.BBCF_FRAME_DATA.keys(),
        )
        cotw_char_key = resolve_character_from_aliases_in_text(
            content_lower,
            cotw_module.COTW_CHARACTER_ALIASES,
            cotw_module.COTW_FRAME_DATA.keys(),
        )
        third_strike_char_key = resolve_character_from_aliases_in_text(
            content_lower,
            third_strike_module.THIRD_STRIKE_CHARACTER_ALIASES,
            third_strike_module.THIRD_STRIKE_FRAME_DATA.keys(),
        )
        explicit_ggst_moves_query = bool(re.search(r"\b(?:ggst|strive|guilty\s+gear|guilty)\b", content_lower))
        explicit_tuco_moves_query = bool(re.search(r"\b(?:2xko|tuco)\b", content_lower))
        explicit_bbcf_moves_query = bool(re.search(r"\b(?:bbcf|blazblue|central\s*fiction)\b", content_lower))
        explicit_cotw_moves_query = bool(re.search(r"\b(?:cotw|city\s+of\s+the\s+wolves|fatal\s+fury)\b", content_lower))
        explicit_third_strike_moves_query = bool(re.search(r"\b(?:3s|third\s*strike|street\s*fighter\s*(?:3|iii)|sf3|sfiii)\b", content_lower))
        if explicit_third_strike_moves_query and third_strike_char_key:
            await menu_system.send_character_moves_menu(message.channel, "third_strike", third_strike_char_key, owner_id=message.author.id)
            return
        if explicit_cotw_moves_query and cotw_char_key:
            await menu_system.send_character_moves_menu(message.channel, "cotw", cotw_char_key, owner_id=message.author.id)
            return
        if explicit_bbcf_moves_query and bbcf_char_key:
            await menu_system.send_character_moves_menu(message.channel, "bbcf", bbcf_char_key, owner_id=message.author.id)
            return
        if explicit_tuco_moves_query and tuco_char_key:
            await menu_system.send_character_moves_menu(message.channel, "tuco", tuco_char_key, owner_id=message.author.id)
            return
        if explicit_ggst_moves_query and ggst_char_key:
            await menu_system.send_character_moves_menu(message.channel, "ggst", ggst_char_key, owner_id=message.author.id)
            return
        if sf6_char_key:
            await menu_system.send_character_moves_menu(message.channel, "sf6", sf6_char_key, owner_id=message.author.id)
            return
        if ggst_char_key:
            await menu_system.send_character_moves_menu(message.channel, "ggst", ggst_char_key, owner_id=message.author.id)
            return
        if tuco_char_key:
            await menu_system.send_character_moves_menu(message.channel, "tuco", tuco_char_key, owner_id=message.author.id)
            return
        if bbcf_char_key:
            await menu_system.send_character_moves_menu(message.channel, "bbcf", bbcf_char_key, owner_id=message.author.id)
            return
        if cotw_char_key:
            await menu_system.send_character_moves_menu(message.channel, "cotw", cotw_char_key, owner_id=message.author.id)
            return
        if third_strike_char_key:
            await menu_system.send_character_moves_menu(message.channel, "third_strike", third_strike_char_key, owner_id=message.author.id)
            return

    if await reminder_manager.handle_message(message, content_no_mentions, content_lower):
        return

    quiz_result = await quiz_module.route_message(client, message, content_lower)
    if quiz_result is not False:
        return

    if message.reference:
        try:
            if message.reference.cached_message:
                ggst_replied_msg = message.reference.cached_message
            else:
                ggst_replied_msg = await message.channel.fetch_message(message.reference.message_id)

            ggst_replied_content = ggst_replied_msg.content or ""
            if (
                ggst_replied_msg.author == client.user
                and (
                    "Multiple GGST moves match" in ggst_replied_content
                    or "GGST Follow-up Options" in ggst_replied_content
                )
            ):
                ggst_char_match = re.search(r"Multiple GGST moves match ([^.]+)\. Please specify one:", ggst_replied_content)
                if not ggst_char_match:
                    ggst_char_match = re.search(r"GGST Follow-up Options \(([^)]+)\)", ggst_replied_content)
                ggst_char_hint = ggst_char_match.group(1).strip() if ggst_char_match else ""
                ggst_reply_query = (content_no_mentions or "").strip()

                if "GGST Follow-up Options" in ggst_replied_content:
                    reply_compact = re.sub(r"[^a-z0-9]", "", ggst_reply_query.lower())
                    followup_options = []
                    for raw_line in ggst_replied_content.splitlines():
                        line = raw_line.strip()
                        option_match = re.match(r"^[\-•·]\s*(.+?):\s*`([^`]+)`", line)
                        if option_match:
                            followup_options.append((option_match.group(1).strip(), option_match.group(2).strip()))
                    selected_followup_cmd = None
                    if reply_compact and followup_options:
                        suffix_matches = []
                        for option_name, option_cmd in followup_options:
                            option_name_compact = re.sub(r"[^a-z0-9]", "", option_name.lower())
                            option_cmd_compact = re.sub(r"[^a-z0-9]", "", option_cmd.lower())
                            command_parts = [
                                part for part in re.split(r"(?:>|~|during|after)", option_cmd.lower())
                                if part.strip()
                            ]
                            suffix_compacts = {
                                re.sub(r"[^a-z0-9]", "", part)
                                for part in command_parts[1:]
                                if re.sub(r"[^a-z0-9]", "", part)
                            }
                            if re.search(r"\b(?:during|after)\b", option_cmd.lower()) and command_parts:
                                first_part_compact = re.sub(r"[^a-z0-9]", "", command_parts[0])
                                if first_part_compact:
                                    suffix_compacts.add(first_part_compact)
                            if reply_compact in {option_name_compact, option_cmd_compact}:
                                selected_followup_cmd = option_cmd
                                break
                            if reply_compact in suffix_compacts:
                                suffix_matches.append(option_cmd)
                        if selected_followup_cmd is None and len(suffix_matches) == 1:
                            selected_followup_cmd = suffix_matches[0]
                    if selected_followup_cmd:
                        ggst_reply_query = selected_followup_cmd

                if ggst_char_hint and ggst_char_hint.lower() not in ggst_reply_query.lower():
                    ggst_reply_query = f"{ggst_char_hint} {ggst_reply_query}".strip()

                ggst_reply_mode = "frame"
                if ggst_replied_msg.reference and ggst_replied_msg.reference.message_id:
                    try:
                        if ggst_replied_msg.reference.cached_message:
                            ggst_prompt_source = ggst_replied_msg.reference.cached_message
                        else:
                            ggst_prompt_source = await message.channel.fetch_message(ggst_replied_msg.reference.message_id)
                        ggst_prompt_source_text = strip_discord_mentions(ggst_prompt_source.content or "").lower()
                        ggst_source_wants_hitbox = bool(re.search(r"\b(?:gif|gifs|hitbox|hitboxes)\b", ggst_prompt_source_text))
                        ggst_source_wants_frames = bool(re.search(r"\b(?:framedata|frame\s*data|frames?)\b", ggst_prompt_source_text))
                        if ggst_source_wants_hitbox and ggst_source_wants_frames:
                            ggst_reply_mode = "both"
                        elif ggst_source_wants_hitbox:
                            ggst_reply_mode = "gif"
                    except Exception:
                        pass

                if ggst_reply_mode == "gif":
                    ggst_reply_query = f"{ggst_reply_query} hitbox".strip()
                elif ggst_reply_mode == "both":
                    ggst_reply_query = f"{ggst_reply_query} hitbox framedata".strip()
                elif not re.search(r"\b(?:framedata|frame\s*data|frames?)\b", ggst_reply_query.lower()):
                    ggst_reply_query = f"{ggst_reply_query} framedata".strip()

                ggst_reply_payload = ggst_module.find_moves_in_text(ggst_reply_query.lower())
                ggst_reply_rows = ggst_reply_payload.get("rows", []) or []
                if ggst_reply_payload.get("needs_disambiguation"):
                    await message.reply(ggst_reply_payload.get("data", "Please specify which GGST move you mean."))
                elif ggst_reply_rows and ggst_reply_mode == "gif":
                    await ggst_module.send_hitbox_response(message, ggst_reply_rows)
                elif ggst_reply_rows and ggst_reply_mode == "both":
                    await ggst_module.send_frame_response(message, ggst_reply_rows)
                    await ggst_module.send_hitbox_response(message, ggst_reply_rows)
                elif ggst_reply_rows:
                    await ggst_module.send_frame_response(message, ggst_reply_rows)
                else:
                    await message.reply(ggst_replied_msg.content)
                return
        except discord.NotFound:
            pass
        except discord.Forbidden:
            pass
        except Exception as e:
            print(f"GGST reply logic error: {e}", flush=True)

    if message.reference:
        try:
            if message.reference.cached_message:
                third_strike_replied_msg = message.reference.cached_message
            else:
                third_strike_replied_msg = await message.channel.fetch_message(message.reference.message_id)

            third_strike_replied_content = third_strike_replied_msg.content or ""
            if (
                third_strike_replied_msg.author == client.user
                and "Multiple Third Strike moves match" in third_strike_replied_content
            ):
                third_strike_char_match = re.search(
                    r"Multiple Third Strike moves match ([^.]+)\. Please specify one:",
                    third_strike_replied_content,
                )
                third_strike_char_hint = third_strike_char_match.group(1).strip() if third_strike_char_match else ""
                reply_text = (content_no_mentions or "").strip()
                reply_compact = re.sub(r"[^a-z0-9]", "", reply_text.lower())
                options = []
                for raw_line in third_strike_replied_content.splitlines():
                    line = raw_line.strip()
                    option_match = re.match(r"^[\-•·]\s*(.+?):\s*`([^`]+)`(?:\s*\[([^\]]+)\])?", line)
                    if option_match:
                        options.append(
                            (
                                option_match.group(1).strip(),
                                option_match.group(2).strip(),
                                (option_match.group(3) or "").strip(),
                            )
                        )

                selected_option = None
                if reply_compact and options:
                    exact_matches = []
                    contains_matches = []
                    for option_name, option_cmd, option_version in options:
                        option_name_compact = re.sub(r"[^a-z0-9]", "", option_name.lower())
                        option_cmd_compact = re.sub(r"[^a-z0-9]", "", option_cmd.lower())
                        option_version_compact = re.sub(r"[^a-z0-9]", "", option_version.lower())
                        option_terms = {
                            option_name_compact,
                            option_cmd_compact,
                            option_version_compact,
                        }
                        option_terms.discard("")
                        if reply_compact in option_terms:
                            exact_matches.append((option_name, option_cmd, option_version))
                        elif any(reply_compact in term for term in option_terms):
                            contains_matches.append((option_name, option_cmd, option_version))
                    if len(exact_matches) == 1:
                        selected_option = exact_matches[0]
                    elif len(contains_matches) == 1:
                        selected_option = contains_matches[0]

                if selected_option and third_strike_char_hint:
                    _option_name, option_cmd, option_version = selected_option
                    version_text = f" {option_version}" if option_version else ""
                    source_wants_hitbox = False
                    source_wants_frames = True
                    prompt_source_text = ""
                    if third_strike_replied_msg.reference and third_strike_replied_msg.reference.message_id:
                        try:
                            if third_strike_replied_msg.reference.cached_message:
                                prompt_source = third_strike_replied_msg.reference.cached_message
                            else:
                                prompt_source = await message.channel.fetch_message(third_strike_replied_msg.reference.message_id)
                            prompt_source_text = strip_discord_mentions(prompt_source.content or "").lower()
                            source_wants_hitbox = bool(re.search(r"\b(?:gif|gifs|hitbox|hitboxes)\b", prompt_source_text))
                            source_wants_frames = bool(re.search(r"\b(?:framedata|frame\s*data|frames?|data)\b", prompt_source_text)) or not source_wants_hitbox
                        except Exception:
                            pass
                    third_strike_reply_query = f"3s {third_strike_char_hint} {option_cmd}{version_text}".strip()
                    if third_strike_module.query_requests_genei_jin(prompt_source_text):
                        third_strike_reply_query = f"{third_strike_reply_query} genei jin".strip()
                    if source_wants_hitbox:
                        third_strike_reply_query = f"{third_strike_reply_query} hitbox".strip()
                    if source_wants_frames:
                        third_strike_reply_query = f"{third_strike_reply_query} framedata".strip()
                    third_strike_reply_payload = third_strike_module.find_moves_in_text(third_strike_reply_query.lower())
                    third_strike_reply_rows = third_strike_reply_payload.get("rows", []) or []
                    if third_strike_reply_payload.get("needs_disambiguation"):
                        await message.reply(third_strike_reply_payload.get("data", "Please specify which Third Strike move you mean."))
                    elif third_strike_reply_rows and source_wants_hitbox and source_wants_frames:
                        await third_strike_module.send_frame_response(message, third_strike_reply_rows)
                        await third_strike_module.send_hitbox_response(message, third_strike_reply_rows)
                    elif third_strike_reply_rows and source_wants_hitbox:
                        await third_strike_module.send_hitbox_response(message, third_strike_reply_rows)
                    elif third_strike_reply_rows:
                        await third_strike_module.send_frame_response(message, third_strike_reply_rows)
                    else:
                        await message.reply(third_strike_replied_content)
                else:
                    await message.reply(third_strike_replied_content)
                return
        except discord.NotFound:
            pass
        except discord.Forbidden:
            pass
        except Exception as e:
            print(f"Third Strike reply logic error: {e}", flush=True)

    sf6_exact_character_query = text_mentions_character_from_aliases(
        content_lower,
        CHARACTER_ALIASES,
        FRAME_DATA.keys(),
    )
    ggst_exact_character_query = text_mentions_character_from_aliases(
        content_lower,
        ggst_module.GGST_CHARACTER_ALIASES,
        ggst_module.GGST_FRAME_DATA.keys(),
    )
    tuco_exact_character_query = text_mentions_character_from_aliases(
        content_lower,
        tuco_module.TUCO_CHARACTER_ALIASES,
        tuco_module.TUCO_FRAME_DATA.keys(),
    )
    bbcf_exact_character_query = text_mentions_character_from_aliases(
        content_lower,
        bbcf_module.BBCF_CHARACTER_ALIASES,
        bbcf_module.BBCF_FRAME_DATA.keys(),
    )
    cotw_exact_character_query = text_mentions_character_from_aliases(
        content_lower,
        cotw_module.COTW_CHARACTER_ALIASES,
        cotw_module.COTW_FRAME_DATA.keys(),
    )
    third_strike_exact_character_query = text_mentions_character_from_aliases(
        content_lower,
        third_strike_module.THIRD_STRIKE_CHARACTER_ALIASES,
        third_strike_module.THIRD_STRIKE_FRAME_DATA.keys(),
    )
    mk1_exact_character_query = text_mentions_character_from_aliases(
        content_lower,
        mk1_module.MK1_CHARACTER_ALIASES,
        mk1_module.MK1_FRAME_DATA.keys(),
    )
    fd_context_payload = find_moves_in_text(content_lower)

    ggst_payload = ggst_module.find_moves_in_text(content_lower)
    tuco_payload = tuco_module.find_moves_in_text(content_lower)
    bbcf_payload = bbcf_module.find_moves_in_text(content_lower)
    cotw_payload = cotw_module.find_moves_in_text(content_lower)
    third_strike_payload = third_strike_module.find_moves_in_text(content_lower)
    mk1_payload = mk1_module.find_moves_in_text(content_lower)
    ggst_rows = ggst_payload.get("rows", [])
    ggst_lookup_intent = bool(
        ggst_payload.get("frame_query")
        or ggst_payload.get("gif_query")
        or ggst_payload.get("game_query")
    )
    explicit_ggst_query = bool(ggst_payload.get("game_query"))
    ggst_route_allowed = bool(
        explicit_ggst_query
        or (ggst_exact_character_query and not sf6_exact_character_query)
    )
    if client.user.mentioned_in(message) and ggst_route_allowed and ggst_lookup_intent and not ggst_rows:
        rewritten_ggst_query = await rewrite_ggst_lookup_query_with_llm(
            content_no_mentions,
            strip_discord_mentions,
        )
        if rewritten_ggst_query:
            rewritten_ggst_payload = ggst_module.find_moves_in_text(rewritten_ggst_query.lower())
            rewritten_ggst_rows = rewritten_ggst_payload.get("rows", []) or []
            if rewritten_ggst_rows or rewritten_ggst_payload.get("needs_disambiguation"):
                ggst_payload = rewritten_ggst_payload
                ggst_rows = rewritten_ggst_rows
                ggst_lookup_intent = bool(
                    ggst_payload.get("frame_query")
                    or ggst_payload.get("gif_query")
                    or ggst_payload.get("game_query")
                )
                print(f"[ggst-parser-llm] rewritten query: {rewritten_ggst_query}", flush=True)

    if client.user.mentioned_in(message) and ggst_route_allowed and ggst_lookup_intent and ggst_rows:
        if ggst_payload.get("needs_disambiguation"):
            await message.reply(ggst_payload.get("data", "Please specify which GGST move you mean."))
        elif ggst_payload.get("gif_query") and ggst_payload.get("frame_query"):
            await ggst_module.send_frame_response(message, ggst_rows)
            await ggst_module.send_hitbox_response(message, ggst_rows)
        elif ggst_payload.get("gif_query"):
            await ggst_module.send_hitbox_response(message, ggst_rows)
        else:
            await ggst_module.send_frame_response(message, ggst_rows)
        return
    elif client.user.mentioned_in(message) and ggst_route_allowed and ggst_lookup_intent and ggst_payload.get("needs_disambiguation"):
        await message.reply(ggst_payload.get("data", "Please specify which GGST move you mean."))
        return

    tuco_rows = tuco_payload.get("rows", [])
    tuco_lookup_intent = bool(
        tuco_payload.get("frame_query")
        or tuco_payload.get("gif_query")
        or tuco_payload.get("game_query")
    )
    tuco_route_allowed = bool(
        tuco_payload.get("game_query")
        or (tuco_exact_character_query and not sf6_exact_character_query and not ggst_exact_character_query)
    )
    if client.user.mentioned_in(message) and tuco_route_allowed and tuco_lookup_intent and tuco_rows:
        if tuco_payload.get("needs_disambiguation"):
            await message.reply(tuco_payload.get("data", "Please specify which 2XKO move you mean."))
        elif tuco_payload.get("gif_query") and tuco_payload.get("frame_query"):
            await tuco_module.send_frame_response(message, tuco_rows)
            await tuco_module.send_hitbox_response(message, tuco_rows)
        elif tuco_payload.get("gif_query"):
            await tuco_module.send_hitbox_response(message, tuco_rows)
        else:
            await tuco_module.send_frame_response(message, tuco_rows)
        return
    elif client.user.mentioned_in(message) and tuco_route_allowed and tuco_lookup_intent and tuco_payload.get("needs_disambiguation"):
        await message.reply(tuco_payload.get("data", "Please specify which 2XKO move you mean."))
        return

    bbcf_rows = bbcf_payload.get("rows", [])
    bbcf_lookup_intent = bool(
        bbcf_payload.get("frame_query")
        or bbcf_payload.get("gif_query")
        or bbcf_payload.get("game_query")
        or bbcf_payload.get("notes_query")
    )
    bbcf_route_allowed = bool(
        bbcf_payload.get("game_query")
        or (
            bbcf_exact_character_query
            and bbcf_module.query_has_bbcf_notation(content_lower)
            and not third_strike_module.query_has_third_strike_notation(content_lower)
        )
        or (
            bbcf_exact_character_query
            and bbcf_rows
            and not sf6_exact_character_query
            and not ggst_exact_character_query
            and not tuco_exact_character_query
            and not third_strike_exact_character_query
        )
    )
    if client.user.mentioned_in(message) and bbcf_route_allowed and bbcf_lookup_intent and bbcf_rows:
        if bbcf_payload.get("needs_disambiguation"):
            await message.reply(bbcf_payload.get("data", "Please specify which BBCF move you mean."))
        elif bbcf_payload.get("gif_query") and bbcf_payload.get("frame_query"):
            await bbcf_module.send_frame_response(message, bbcf_rows)
            await bbcf_module.send_hitbox_response(message, bbcf_rows)
        elif bbcf_payload.get("gif_query"):
            await bbcf_module.send_hitbox_response(message, bbcf_rows)
        else:
            await bbcf_module.send_frame_response(message, bbcf_rows)
        return
    elif client.user.mentioned_in(message) and bbcf_route_allowed and bbcf_lookup_intent and bbcf_payload.get("needs_disambiguation"):
        await message.reply(bbcf_payload.get("data", "Please specify which BBCF move you mean."))
        return

    cotw_rows = cotw_payload.get("rows", [])
    cotw_lookup_intent = bool(
        cotw_payload.get("frame_query")
        or cotw_payload.get("gif_query")
        or cotw_payload.get("game_query")
        or cotw_payload.get("notes_query")
    )
    cotw_route_allowed = bool(
        cotw_payload.get("game_query")
        or (
            cotw_exact_character_query
            and cotw_module.query_has_cotw_notation(content_lower)
        )
        or (
            cotw_exact_character_query
            and cotw_rows
            and not sf6_exact_character_query
            and not ggst_exact_character_query
            and not tuco_exact_character_query
            and not bbcf_exact_character_query
        )
    )
    if client.user.mentioned_in(message) and cotw_route_allowed and cotw_lookup_intent and cotw_rows:
        if cotw_payload.get("needs_disambiguation"):
            await message.reply(cotw_payload.get("data", "Please specify which COTW move you mean."))
        else:
            await cotw_module.send_frame_response(message, cotw_rows)
        return
    elif client.user.mentioned_in(message) and cotw_route_allowed and cotw_lookup_intent and cotw_payload.get("needs_disambiguation"):
        await message.reply(cotw_payload.get("data", "Please specify which COTW move you mean."))
        return

    third_strike_rows = third_strike_payload.get("rows", [])
    third_strike_lookup_intent = bool(
        third_strike_payload.get("frame_query")
        or third_strike_payload.get("gif_query")
        or third_strike_payload.get("game_query")
        or third_strike_payload.get("notes_query")
        or third_strike_module.query_has_third_strike_notation(content_lower)
    )
    third_strike_route_allowed = bool(
        third_strike_payload.get("game_query")
        or (
            third_strike_exact_character_query
            and third_strike_module.query_has_third_strike_notation(content_lower)
            and not sf6_exact_character_query
        )
        or (
            third_strike_exact_character_query
            and third_strike_rows
            and not sf6_exact_character_query
            and not ggst_exact_character_query
            and not tuco_exact_character_query
            and not bbcf_exact_character_query
            and not cotw_exact_character_query
            and not mk1_exact_character_query
            and not bbcf_module.query_has_bbcf_notation(content_lower)
        )
    )
    if client.user.mentioned_in(message) and third_strike_route_allowed and third_strike_lookup_intent and third_strike_rows:
        if third_strike_payload.get("needs_disambiguation"):
            await message.reply(third_strike_payload.get("data", "Please specify which Third Strike move you mean."))
        elif third_strike_payload.get("gif_query") and third_strike_payload.get("frame_query"):
            await third_strike_module.send_frame_response(message, third_strike_rows)
            await third_strike_module.send_hitbox_response(message, third_strike_rows)
        elif third_strike_payload.get("gif_query"):
            await third_strike_module.send_hitbox_response(message, third_strike_rows)
        else:
            await third_strike_module.send_frame_response(message, third_strike_rows)
        return
    elif client.user.mentioned_in(message) and third_strike_route_allowed and third_strike_lookup_intent and third_strike_payload.get("needs_disambiguation"):
        await message.reply(third_strike_payload.get("data", "Please specify which Third Strike move you mean."))
        return
    elif client.user.mentioned_in(message) and third_strike_route_allowed and third_strike_lookup_intent and third_strike_payload.get("explicit_move_attempt"):
        char_label = third_strike_module.display_char_name(third_strike_payload.get("char_key"))
        await message.reply(f"I have Third Strike scrolls for {char_label}, but I couldn't find that move.")
        return

    mk1_rows = mk1_payload.get("rows", [])
    mk1_combo_rows = mk1_payload.get("combo_rows", []) or []
    mk1_lookup_intent = bool(
        mk1_payload.get("frame_query")
        or mk1_payload.get("gif_query")
        or mk1_payload.get("game_query")
        or mk1_payload.get("notes_query")
        or mk1_payload.get("combo_query")
        or mk1_module.query_has_mk1_notation(content_lower)
    )
    mk1_route_allowed = bool(
        mk1_payload.get("game_query")
        or (
            mk1_exact_character_query
            and mk1_module.query_has_mk1_notation(content_lower)
            and not sf6_exact_character_query
        )
        or (
            mk1_exact_character_query
            and (mk1_rows or mk1_combo_rows)
            and not sf6_exact_character_query
            and not ggst_exact_character_query
            and not tuco_exact_character_query
            and not bbcf_exact_character_query
            and not cotw_exact_character_query
            and not third_strike_exact_character_query
        )
    )
    if client.user.mentioned_in(message) and mk1_route_allowed and mk1_lookup_intent and mk1_combo_rows:
        await mk1_module.send_combo_response(message, mk1_combo_rows)
        return
    if client.user.mentioned_in(message) and mk1_route_allowed and mk1_lookup_intent and mk1_rows:
        if mk1_payload.get("needs_disambiguation"):
            await message.reply(mk1_payload.get("data", "Please specify which MK1 move you mean."))
        elif mk1_payload.get("gif_query") and mk1_payload.get("frame_query"):
            await mk1_module.send_frame_response(message, mk1_rows)
            await mk1_module.send_hitbox_response(message, mk1_rows)
        elif mk1_payload.get("gif_query"):
            await mk1_module.send_hitbox_response(message, mk1_rows)
        else:
            await mk1_module.send_frame_response(message, mk1_rows)
        return
    elif client.user.mentioned_in(message) and mk1_route_allowed and mk1_lookup_intent and mk1_payload.get("needs_disambiguation"):
        await message.reply(mk1_payload.get("data", "Please specify which MK1 move you mean."))
        return
    elif client.user.mentioned_in(message) and mk1_route_allowed and mk1_lookup_intent and mk1_payload.get("explicit_move_attempt"):
        char_label = mk1_module.display_char_name(mk1_payload.get("char_key"))
        await message.reply(f"I have MK1 scrolls for {char_label}, but I couldn't find that move.")
        return

    if (
        client.user.mentioned_in(message)
        and mk1_route_allowed
        and not mk1_lookup_intent
        and not message.reference
        and (mk1_rows or mk1_payload.get("needs_disambiguation"))
    ):
        if mk1_payload.get("needs_disambiguation"):
            await message.reply(mk1_payload.get("data", "Please specify which MK1 move you mean."))
        else:
            await mk1_module.send_frame_response(message, mk1_rows)
        return

    if (
        client.user.mentioned_in(message)
        and third_strike_route_allowed
        and not third_strike_lookup_intent
        and not message.reference
        and (third_strike_rows or third_strike_payload.get("needs_disambiguation"))
    ):
        if third_strike_payload.get("needs_disambiguation"):
            await message.reply(third_strike_payload.get("data", "Please specify which Third Strike move you mean."))
        else:
            await third_strike_module.send_frame_response(message, third_strike_rows)
        return

    if (
        client.user.mentioned_in(message)
        and tuco_route_allowed
        and not tuco_lookup_intent
        and not message.reference
        and (tuco_rows or tuco_payload.get("needs_disambiguation"))
    ):
        if tuco_payload.get("needs_disambiguation"):
            await message.reply(tuco_payload.get("data", "Please specify which 2XKO move you mean."))
        else:
            await tuco_module.send_frame_response(message, tuco_rows)
        return

    if (
        client.user.mentioned_in(message)
        and bbcf_route_allowed
        and not bbcf_lookup_intent
        and not message.reference
        and (bbcf_rows or bbcf_payload.get("needs_disambiguation"))
    ):
        if bbcf_payload.get("needs_disambiguation"):
            await message.reply(bbcf_payload.get("data", "Please specify which BBCF move you mean."))
        else:
            await bbcf_module.send_frame_response(message, bbcf_rows)
        return

    if (
        client.user.mentioned_in(message)
        and cotw_route_allowed
        and not cotw_lookup_intent
        and not message.reference
        and (cotw_rows or cotw_payload.get("needs_disambiguation"))
    ):
        if cotw_payload.get("needs_disambiguation"):
            await message.reply(cotw_payload.get("data", "Please specify which COTW move you mean."))
        else:
            await cotw_module.send_frame_response(message, cotw_rows)
        return

    if (
        client.user.mentioned_in(message)
        and ggst_route_allowed
        and not ggst_lookup_intent
        and not message.reference
        and (ggst_rows or ggst_payload.get("needs_disambiguation"))
    ):
        if ggst_payload.get("needs_disambiguation"):
            await message.reply(ggst_payload.get("data", "Please specify which GGST move you mean."))
        else:
            await ggst_module.send_frame_response(message, ggst_rows)
        return


    if "tarkus" in content_lower:
        await message.reply("My brother is African American. Our love language is slurs and assaulting each other.")
        return

    
    if "clanker" in content_lower:
        await message.reply("please can we not say slurs thanks <:sponge:1416270403923480696>")
        return


    if "verbatim" in content_lower:
        await message.reply("it's less how i think and more so the nature of existence. free will is an illusion. everything that happens in the universe has been metaphysically set in stone since the big bang. menaRD was always going to be the best. if i were destined for more, it would've happened already. <:sponge:1416270403923480696>")
        return


    if client.user.mentioned_in(message) and "link the mod" in content_lower:
        await message.reply("This message was sponsored by LL. Download the LL hitbox viewer mod now from the link below! 'I am Daigo Umehara and I endorse this message' - Daigo Umehara <https://github.com/LL5270/sf6mods>  <:sponge:1416270403923480696>")
        return

    # logic flags
    check_media = False
    replied_context = None  # store bub's original message if replying to bot
    special_strength_reply_mode = None
    is_reply_to_bot = False
    
    
    # check mentions
    if client.user.mentioned_in(message):
        check_media = True

    replied_context = None 
    is_coach_mode = "coach" in content_lower
    

    fd_context_data = fd_context_payload.get("data", "")
    fd_context_mode = fd_context_payload.get("mode", "none")
    fd_context_rows = fd_context_payload.get("rows", [])
    startup_alias_query = bool(fd_context_payload.get("startup_alias_query"))
    hitconfirm_alias_query = bool(fd_context_payload.get("hitconfirm_alias_query"))
    super_gain_alias_query = bool(fd_context_payload.get("super_gain_alias_query"))
    range_alias_query = bool(fd_context_payload.get("range_alias_query"))
    wants_comparison = bool(fd_context_payload.get("wants_comparison"))
    property_only_query = bool(fd_context_payload.get("property_only_query"))
    target_combo_query = bool(fd_context_payload.get("target_combo_query"))
    missing_scrolls_query = bool(fd_context_payload.get("missing_scrolls_query"))
    gif_query = bool(fd_context_payload.get("gif_query"))
    explicit_move_attempt = bool(fd_context_payload.get("explicit_move_attempt"))
    fallback_reply = fd_context_data if fd_context_data else None

    def row_matches_requested_strength(row, query_text):
        move_name = str(row.get("moveName", "")).lower().strip()
        cmn_name = str(row.get("cmnName", "")).lower().strip()
        num_cmd = str(row.get("numCmd", "")).lower().strip()
        num_cmd_compact = re.sub(r"[^a-z0-9]", "", num_cmd)

        if re.search(r"\b(?:od|ex)\b", query_text):
            return (
                move_name.startswith(("od ", "ex "))
                or cmn_name.startswith(("od ", "ex "))
                or num_cmd_compact.endswith(("pp", "kk"))
            )

        strength_groups = [
            ({"light", "l", "lp", "lk"}, {"lp", "lk"}),
            ({"medium", "m", "mp", "mk"}, {"mp", "mk"}),
            ({"heavy", "h", "hp", "hk"}, {"hp", "hk"}),
        ]
        requested_suffixes = set()
        for token_group, suffixes in strength_groups:
            if any(re.search(rf"\b{re.escape(token)}\b", query_text) for token in token_group):
                requested_suffixes.update(suffixes)
        if not requested_suffixes:
            return False

        if any(
            move_name.startswith(f"{suffix} ") or cmn_name.startswith(f"{suffix} ")
            for suffix in requested_suffixes
        ):
            return True
        return num_cmd_compact.endswith(tuple(requested_suffixes))

    def row_has_explicit_strength(row):
        move_name = str(row.get("moveName", "")).lower().strip()
        cmn_name = str(row.get("cmnName", "")).lower().strip()
        num_cmd_compact = re.sub(r"[^a-z0-9]", "", str(row.get("numCmd", "")).lower())
        return (
            move_name.startswith(("lp ", "mp ", "hp ", "lk ", "mk ", "hk ", "od ", "ex "))
            or cmn_name.startswith(("lp ", "mp ", "hp ", "lk ", "mk ", "hk ", "od ", "ex "))
            or num_cmd_compact.endswith(("lp", "mp", "hp", "lk", "mk", "hk", "pp", "kk"))
        )

    query_requests_explicit_strength = bool(
        re.search(r"\b(?:od|ex|lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b", content_lower)
    )
    payload_strength_mismatch = bool(
        query_requests_explicit_strength
        and fd_context_rows
        and any(row_has_explicit_strength(row) for row in fd_context_rows)
        and not any(row_matches_requested_strength(row, content_lower) for row in fd_context_rows)
    )

    should_try_llm_lookup_rewrite = bool(
        client.user.mentioned_in(message)
        and (fd_context_payload.get("gif_query") or re.search(r"\b(?:framedata|frame\s*data|frames?)\b", content_lower))
        and (not fd_context_rows or payload_strength_mismatch)
        and "Special Strength Options" not in str(fd_context_data)
        and "Target Combo Options" not in str(fd_context_data)
        and not startup_alias_query
        and not hitconfirm_alias_query
        and not super_gain_alias_query
        and not range_alias_query
    )
    if should_try_llm_lookup_rewrite:
        rewritten_lookup_query = await rewrite_sf_lookup_query_with_llm(
            content_no_mentions,
            strip_discord_mentions,
        )
        if rewritten_lookup_query:
            rewritten_payload = find_moves_in_text(rewritten_lookup_query.lower())
            rewritten_data = str(rewritten_payload.get("data", "") or "")
            rewritten_rows = rewritten_payload.get("rows", []) or []
            if (
                rewritten_rows
                or "Special Strength Options" in rewritten_data
                or "Target Combo Options" in rewritten_data
            ):
                content_no_mentions = rewritten_lookup_query
                content_lower = rewritten_lookup_query.lower()
                fd_context_payload = rewritten_payload
                fd_context_data = rewritten_payload.get("data", "")
                fd_context_mode = rewritten_payload.get("mode", "none")
                fd_context_rows = rewritten_rows
                startup_alias_query = bool(rewritten_payload.get("startup_alias_query"))
                hitconfirm_alias_query = bool(rewritten_payload.get("hitconfirm_alias_query"))
                super_gain_alias_query = bool(rewritten_payload.get("super_gain_alias_query"))
                range_alias_query = bool(rewritten_payload.get("range_alias_query"))
                wants_comparison = bool(rewritten_payload.get("wants_comparison"))
                property_only_query = bool(rewritten_payload.get("property_only_query"))
                target_combo_query = bool(rewritten_payload.get("target_combo_query"))
                missing_scrolls_query = bool(rewritten_payload.get("missing_scrolls_query"))
                gif_query = bool(rewritten_payload.get("gif_query"))
                explicit_move_attempt = bool(rewritten_payload.get("explicit_move_attempt"))
                fallback_reply = fd_context_data if fd_context_data else None
                print(f"[parser-llm] rewritten query: {rewritten_lookup_query}", flush=True)

    if gif_query and not client.user.mentioned_in(message):
        return

    explicit_frame_request = (
        "framedata" in content_lower
        or "frame data" in content_lower
        or re.search(r"\bframes?\b", content_lower)
        or re.search(r"\bhow\s+fast\b", content_lower)
        or re.search(r"\bhow\s+quick\b", content_lower)
        or re.search(r"\bspeed\s+of\b", content_lower)
        or (
            re.search(r"\bfast\b", content_lower)
            and re.search(r"\b[1-9][0-9]*[a-zA-Z]{1,3}\b", content_lower)
        )
    )
    force_verbatim_frame_reply = bool(
        fd_context_mode == "frame"
        and not property_only_query
        and fd_context_rows
    )
    frame_reply_embeds = (
        build_frame_embeds(fd_context_rows)
        if force_verbatim_frame_reply and fd_context_rows
        else []
    )
    frame_reply_rows = (
        iter_unique_frame_rows(fd_context_rows)
        if force_verbatim_frame_reply and fd_context_rows
        else []
    )
    if frame_reply_embeds:
        print(
            "Frame embed mode active: "
            f"count={len(frame_reply_embeds)} property_only={property_only_query}",
            flush=True,
        )
    

    
    should_handle_direct_frame = (
        client.user.mentioned_in(message)
        or ".framedata" in content_lower
    )
    combined_frame_gif_request = bool(
        gif_query
        and explicit_frame_request
        and fd_context_mode == "frame"
        and not property_only_query
        and not startup_alias_query
        and not hitconfirm_alias_query
        and not super_gain_alias_query
        and not range_alias_query
    )

    vague_move_query_without_output_intent = False
    implied_rows = []
    implied_data = ""
    if (
        client.user.mentioned_in(message)
        and not message.reference
        and not gif_query
        and not explicit_frame_request
        and not property_only_query
        and not target_combo_query
        and not startup_alias_query
        and not hitconfirm_alias_query
        and not super_gain_alias_query
        and not range_alias_query
        and not re.search(
            r"\b(punish|punishable|compare|comparison|versus|vs|stats?|health|reversal|combo|bnb|oki|playstyle|overview|coach)\b",
            content_lower,
        )
    ):
        implied_frame_payload = find_moves_in_text(f"{content_lower} framedata")
        implied_data = implied_frame_payload.get("data", "")
        implied_rows = implied_frame_payload.get("rows", [])
        implied_mode = implied_frame_payload.get("mode", "none")
        implied_explicit_move_attempt = bool(implied_frame_payload.get("explicit_move_attempt"))
        implied_has_special_prompt = "Special Strength Options" in implied_data
        vague_move_query_without_output_intent = bool(
            implied_explicit_move_attempt
            and (
                (implied_mode == "frame" and implied_rows)
                or implied_has_special_prompt
            )
        )

    if (
        not vague_move_query_without_output_intent
        and client.user.mentioned_in(message)
        and not message.reference
        and target_combo_query
        and explicit_move_attempt
        and fd_context_mode == "frame"
        and fd_context_rows
        and not gif_query
        and not explicit_frame_request
        and not property_only_query
        and not startup_alias_query
        and not hitconfirm_alias_query
        and not super_gain_alias_query
        and not range_alias_query
    ):
        vague_move_query_without_output_intent = True

    if should_handle_direct_frame:
        if vague_move_query_without_output_intent:
            default_rows = implied_rows or fd_context_rows
            default_data = implied_data or fd_context_data
            frame_sent = await send_frame_table_response(message, default_rows, default_data)
            if not frame_sent and default_data:
                await message.reply(default_data)
            return

        if combined_frame_gif_request and client.user.mentioned_in(message):
            if "Special Strength Options" in fd_context_data:
                try:
                    sent_prompt = await message.reply(fd_context_data)
                    remember_special_strength_prompt_mode(sent_prompt.id, "both")
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Special strength options both reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Special strength options both reply error: {reply_error}", flush=True)
                return

            if not explicit_move_attempt:
                await message.reply("Tell me the exact move too, like 'aki 5hp gif framedata'.")
                return

            if missing_scrolls_query:
                missing_msg = (
                    f"I don't have the scrolls for that move. "
                    f"<@{SCROLLS_MAINTAINER_USER_ID}> {SCROLLS_FIX_REQUEST_TEXT}"
                )
                try:
                    await message.reply(missing_msg)
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Missing-scrolls both reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Missing-scrolls both reply error: {reply_error}", flush=True)
                return

            if fd_context_rows:
                await send_frame_table_response(message, fd_context_rows, fd_context_data)

                gif_frame_rows = fd_context_rows
                if wants_comparison and fd_context_rows:
                    comparison_rows = []
                    seen_comparison_chars = set()
                    for row in fd_context_rows:
                        row_char = normalize_char_name(row.get("char_name", ""))
                        if not row_char or row_char in seen_comparison_chars:
                            continue
                        seen_comparison_chars.add(row_char)
                        comparison_rows.append(row)
                    if len(comparison_rows) >= 2:
                        gif_frame_rows = comparison_rows

                gif_limit = 3
                if wants_comparison and gif_frame_rows:
                    gif_limit = max(2, min(6, len(gif_frame_rows)))

                gif_links = collect_hitbox_gif_links_from_text(
                    content_no_mentions,
                    frame_rows=gif_frame_rows,
                    limit=gif_limit,
                )
                if gif_links:
                    await send_gif_links_response(
                        message,
                        gif_links,
                        wants_comparison=wants_comparison,
                    )
                    return

                missing_gif_msg = (
                    f"I have frame data for that move but no hitbox gif link yet. "
                    f"<@{SCROLLS_MAINTAINER_USER_ID}> {SCROLLS_FIX_REQUEST_TEXT}"
                )
                try:
                    await message.reply(missing_gif_msg)
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Missing-gif both reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Missing-gif both reply error: {reply_error}", flush=True)
                return

        if gif_query and client.user.mentioned_in(message):
            if "Special Strength Options" in fd_context_data:
                try:
                    sent_prompt = await message.reply(fd_context_data)
                    remember_special_strength_prompt_mode(sent_prompt.id, "gif")
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Special strength options gif reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Special strength options gif reply error: {reply_error}", flush=True)
                return

            if not explicit_move_attempt:
                await message.reply("Tell me the exact move too, like 'aki 5hp gif'.")
                return

            gif_frame_rows = fd_context_rows
            if wants_comparison and fd_context_rows:
                comparison_rows = []
                seen_comparison_chars = set()
                for row in fd_context_rows:
                    row_char = normalize_char_name(row.get("char_name", ""))
                    if not row_char or row_char in seen_comparison_chars:
                        continue
                    seen_comparison_chars.add(row_char)
                    comparison_rows.append(row)
                if len(comparison_rows) >= 2:
                    gif_frame_rows = comparison_rows

            gif_limit = 3
            if wants_comparison and gif_frame_rows:
                gif_limit = max(2, min(6, len(gif_frame_rows)))

            gif_links = collect_hitbox_gif_links_from_text(
                content_no_mentions,
                frame_rows=gif_frame_rows,
                limit=gif_limit,
            )
            if gif_links:
                await send_gif_links_response(
                    message,
                    gif_links,
                    wants_comparison=wants_comparison,
                )
                return

            if fd_context_rows:
                missing_gif_msg = (
                    f"I have frame data for that move but no hitbox gif link yet. "
                    f"<@{SCROLLS_MAINTAINER_USER_ID}> {SCROLLS_FIX_REQUEST_TEXT}"
                )
                try:
                    await message.reply(missing_gif_msg)
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Missing-gif reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Missing-gif reply error: {reply_error}", flush=True)
                return

        if missing_scrolls_query:
            missing_msg = (
                f"I don't have the scrolls for that move. "
                f"<@{SCROLLS_MAINTAINER_USER_ID}> {SCROLLS_FIX_REQUEST_TEXT}"
            )
            try:
                await message.reply(missing_msg)
            except Exception as reply_error:
                if is_deleted_message_reference_error(reply_error):
                    print("Missing-scrolls reply target deleted. Triggering failsafe.", flush=True)
                    await send_deleted_message_failsafe(message.channel)
                else:
                    print(f"Missing-scrolls reply error: {reply_error}", flush=True)
            return
        if "Target Combo Options" in fd_context_data:
            try:
                await message.reply(fd_context_data)
            except Exception as reply_error:
                if is_deleted_message_reference_error(reply_error):
                    print("Target combo options reply target deleted. Triggering failsafe.", flush=True)
                    await send_deleted_message_failsafe(message.channel)
                else:
                    print(f"Target combo options reply error: {reply_error}", flush=True)
            return
        if "Special Strength Options" in fd_context_data:
            try:
                sent_prompt = await message.reply(fd_context_data)
                remember_special_strength_prompt_mode(
                    sent_prompt.id,
                    "gif" if gif_query else "frame",
                )
            except Exception as reply_error:
                if is_deleted_message_reference_error(reply_error):
                    print("Special strength options reply target deleted. Triggering failsafe.", flush=True)
                    await send_deleted_message_failsafe(message.channel)
                else:
                    print(f"Special strength options reply error: {reply_error}", flush=True)
            return
        if target_combo_query and fd_context_mode == "frame" and fd_context_rows:
            await send_frame_table_response(message, fd_context_rows, fd_context_data)
            return
        if range_alias_query and fd_context_mode == "frame" and fd_context_rows:
            range_reply = format_range_only_reply(fd_context_rows)
            if range_reply:
                try:
                    await message.reply(range_reply)
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Direct range reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Direct range reply error: {reply_error}", flush=True)
                return
        if super_gain_alias_query and fd_context_mode == "frame" and fd_context_rows:
            super_gain_reply = format_super_gain_only_reply(fd_context_rows)
            if super_gain_reply:
                try:
                    await message.reply(super_gain_reply)
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Direct super gain reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Direct super gain reply error: {reply_error}", flush=True)
                return
        if hitconfirm_alias_query and fd_context_mode == "frame" and fd_context_rows:
            hitconfirm_reply = format_hitconfirm_only_reply(fd_context_rows)
            if hitconfirm_reply:
                try:
                    await message.reply(hitconfirm_reply)
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Direct hitconfirm reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Direct hitconfirm reply error: {reply_error}", flush=True)
                return
        if startup_alias_query and fd_context_mode == "frame" and fd_context_rows:
            startup_reply = format_startup_only_reply(fd_context_rows)
            if startup_reply:
                try:
                    await message.reply(startup_reply)
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Direct startup reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Direct startup reply error: {reply_error}", flush=True)
                return

        if (
            explicit_frame_request
            and fd_context_mode == "frame"
            and fd_context_rows
            and not property_only_query
            and not target_combo_query
            and not startup_alias_query
            and not hitconfirm_alias_query
            and not super_gain_alias_query
            and not range_alias_query
            and not gif_query
        ):
            frame_sent = await send_frame_table_response(message, fd_context_rows, fd_context_data)
            if not frame_sent and fd_context_data:
                try:
                    await message.reply(fd_context_data)
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Direct frame reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Direct frame reply error: {reply_error}", flush=True)
            return

        # If Coach Mode, pre-pend some advice instruction
        coach_instruction = ""
        if is_coach_mode:
            coach_instruction = (
                "MODE: COACH\n"
                "You are a Fighting Game Coach. Focus on improvement, frame advantage, and punishment.\n"
                "Guide the player towards better habits.\n"
            )
            
        if fd_context_data:
            if fd_context_mode == "frame":
                # Found relevant frame data! Inject it.
                if frame_reply_embeds:
                    replied_context = (
                        f"{coach_instruction}"
                        f"USER QUERY: {content_no_mentions}\n"
                        f"AVAILABLE DATA:\n{fd_context_data}\n"
                        f"{MOVE_DEFINITIONS}\n"
                        "INSTRUCTION: The full frame table is already shown above your reply.\n"
                        " - Write a short follow-up comment (1-2 sentences) underneath the table.\n"
                        " - Do NOT reprint or restate the full table.\n"
                        " - Do NOT output labels like Startup/Active/Recovery/Range/On Hit/On Block/Drive/Super/Hit Confirm/Notes.\n"
                        " - Do NOT include move lines like 'Move Name (numCmd)'.\n"
                        " - If the user asked for a comparison or takeaway, give a brief practical note using AVAILABLE DATA.\n"
                        " - If data is missing for what they asked, say you don't have the scrolls for that part.\n"
                        "CRITICAL: Do NOT invent frame data not present in AVAILABLE DATA."
                    )
                elif property_only_query:
                    replied_context = (
                        f"{coach_instruction}"
                        f"USER QUERY: {content_no_mentions}\n"
                        f"AVAILABLE DATA:\n{fd_context_data}\n"
                        f"{MOVE_DEFINITIONS}\n"
                        "INSTRUCTION: Answer with ONLY the specific value the user asked for in plain text.\n"
                        " - Do NOT output the full frame table for this request.\n"
                        " - If they ask startup/active/recovery/on hit/on block/cancel/damage/drive/super gain/stun/hit confirm/range, return those exact values only.\n"
                        " - Keep it concise (1-2 sentences max).\n"
                        "CRITICAL: Do NOT invent values not present in AVAILABLE DATA."
                    )
                else:
                    replied_context = (
                        f"{coach_instruction}"
                        f"USER QUERY: {content_no_mentions}\n"
                        f"AVAILABLE DATA:\n{fd_context_data}\n"
                        f"{MOVE_DEFINITIONS}\n"
                        "INSTRUCTION: Use the AVAILABLE DATA to answer the user's question.\n"
                        " - If the user asks for 'frame data', 'stats', or general info, output the full data block VERBATIM.\n"
                        " - If the user asks for a SPECIFIC property (e.g. 'what is the recovery?', 'is it plus?', 'damage?'), answer DIRECTLY with just that value in a sentence. Do NOT output the full chart unless asked.\n"
                        " - Examples:\n"
                        "   User: 'Startup of Ryu 5LP?' -> Bot: 'Ryu's Stand LP has 4 frames of startup.'\n"
                        "   User: 'Ryu 5LP frame data' -> Bot: [Outputs Full Chart]\n"
                        "Even if the user asks for a comparison (like 'who is faster?'), FIRST list the full stats for valid moves, THEN add a brief 1-sentence comparison.\n"
                        "If the user asks about stats (health, reversal, etc.), use the provided **Stats** block.\n"
                        "CRITICAL: If a move's frame data is not listed in AVAILABLE DATA above, DO NOT INVENT IT. Just say you don't have the scrolls for it.\n"
                        "CRITICAL: The 'Cancel' field corresponds to the 'xx' column in the data. \n"
                        " - If Cancel is 'sp', it means Special Cancellable.\n"
                        " - If Cancel is 'su', it means Super Cancellable.\n"
                        " - If Cancel is '-' or 'No', it is NOT cancellable. Do NOT suggest canceling it.\n"
                        "Format for Moves: \n"
                        "**Move Name**\n"
                        "Startup: X // Active: Y ...\n"
                        "(Repeat for all moves)\n\n"
                        "Comparison: [Your 1 sentence comparison]"
                    )
                should_respond = True
            elif fd_context_mode == "combo":
                replied_context = (
                    f"{coach_instruction}"
                    f"USER QUERY: {content_no_mentions}\n"
                    f"AVAILABLE DATA:\n{fd_context_data}\n"
                    "INSTRUCTION: Use ONLY the combo/oki data in AVAILABLE DATA.\n"
                    " - Do NOT invent frame data, move inputs, or stats that are not explicitly listed.\n"
                    " - If the question asks for frame data or a move not shown, say the scrolls do not include it."
                )
                should_respond = True
            elif fd_context_mode == "overview":
                replied_context = (
                    f"{coach_instruction}"
                    f"USER QUERY: {content_no_mentions}\n"
                    f"AVAILABLE DATA:\n{fd_context_data}\n"
                    "INSTRUCTION: Use ONLY the overview text in AVAILABLE DATA.\n"
                    " - Do NOT invent moves, inputs, frame data, or specific anti-air buttons unless they appear in the overview.\n"
                    " - Answer in prose, not a table.\n"
                    " - If the overview does not mention the requested detail, say the scrolls do not cover it."
                )
                should_respond = True
            else:
                replied_context = (
                    f"{coach_instruction}"
                    f"USER QUERY: {content_no_mentions}\n"
                    f"AVAILABLE DATA:\n{fd_context_data}\n"
                    "INSTRUCTION: Use ONLY the AVAILABLE DATA to answer the user's question."
                )
                should_respond = True
        elif is_coach_mode:
            # Coach mode but no specific frame data found? 
            # Still provide a coached response.
             replied_context = (
                f"{coach_instruction}"
                f"USER QUERY: {content_no_mentions}\n"
                f"{MOVE_DEFINITIONS}\n"
                "Answer as a helpful coach."
            )
             should_respond = True

    if replied_context is None and message.reference:
        try:
            if message.reference.cached_message:
                replied_msg = message.reference.cached_message
            else:
                replied_msg = await message.channel.fetch_message(message.reference.message_id)
            
            # replying to bot
            if replied_msg.author == client.user:
                check_media = True # check media on reply
                is_reply_to_bot = True
                if replied_msg.id == LAST_DAILY_VIDEO_ID.get(message.channel.id):
                    replied_context = "Has anyone improved?"
                elif "Target Combo Options" in replied_msg.content:
                    replied_context = replied_msg.content  # capture only TC prompt
                elif "Special Strength Options" in replied_msg.content:
                    replied_context = replied_msg.content
                    special_strength_reply_mode = SPECIAL_STRENGTH_PROMPT_MODE.get(replied_msg.id)
                    if (
                        not special_strength_reply_mode
                        and replied_msg.reference
                        and replied_msg.reference.message_id
                    ):
                        try:
                            if replied_msg.reference.cached_message:
                                prompt_source_msg = replied_msg.reference.cached_message
                            else:
                                prompt_source_msg = await message.channel.fetch_message(
                                    replied_msg.reference.message_id
                                )
                            prompt_source_text = strip_discord_mentions(
                                prompt_source_msg.content or ""
                            ).lower()
                            if has_explicit_gif_lookup_intent(prompt_source_text):
                                special_strength_reply_mode = "gif"
                        except Exception:
                            pass

        except discord.NotFound:
            pass
        except discord.Forbidden:
            pass
        except Exception as e:
            print(f"Reply logic error: {e}")

    if replied_context and "Target Combo Options" in replied_context:
        match = re.search(r"Target Combo Options \(([^)]+)\)", replied_context)
        char_hint = match.group(1).strip() if match else ""
        tc_query = (content_no_mentions or "").strip()
        tc_query_lower = tc_query.lower()
        if char_hint:
            normalized_hint = normalize_char_name(char_hint)
            if normalized_hint not in tc_query_lower:
                tc_query = f"{char_hint} {tc_query}".strip()
                tc_query_lower = tc_query.lower()
        if not re.search(r"\b(tc|target\s+combo|targetcombo)\b", tc_query_lower):
            tc_query = f"{tc_query} target combo".strip()
            tc_query_lower = tc_query.lower()
        if not (
            "framedata" in tc_query_lower
            or "frame data" in tc_query_lower
            or re.search(r"\bframes?\b", tc_query_lower)
        ):
            tc_query = f"{tc_query} framedata".strip()
        tc_payload = find_moves_in_text(tc_query.lower())
        tc_data = tc_payload.get("data", "")
        tc_rows = tc_payload.get("rows", [])
        if "Target Combo Options" in tc_data:
            await message.reply(tc_data)
            return
        if tc_payload.get("mode") == "frame" and tc_rows and tc_data:
            await send_frame_table_response(message, tc_rows, tc_data)
            return

    if replied_context and "Special Strength Options" in replied_context:
        char_match = re.search(r"Special Strength Options \(([^)]+)\)", replied_context)
        char_hint = char_match.group(1).strip() if char_match else ""
        base_match = re.search(r"\n([^\n]+) variants:", replied_context)
        base_hint = base_match.group(1).strip().lower() if base_match else ""

        option_matches = []

        def parse_special_option_line(option_line):
            line = str(option_line or "").strip()
            if not line:
                return None, None
            if "::" in line:
                left, right = line.split("::", 1)
                option_name = left.strip()
                option_cmd = right.strip()
                if option_name and option_cmd:
                    return option_name, option_cmd
                return None, None
            if not line.endswith(")"):
                return None, None

            depth = 0
            split_idx = None
            for idx in range(len(line) - 1, -1, -1):
                ch = line[idx]
                if ch == ")":
                    depth += 1
                elif ch == "(":
                    depth -= 1
                    if depth == 0:
                        split_idx = idx
                        break

            if split_idx is None:
                return None, None

            option_name = line[:split_idx].strip()
            option_cmd = line[split_idx + 1 : -1].strip()
            if option_name and option_cmd:
                return option_name, option_cmd
            return None, None

        for raw_line in replied_context.splitlines():
            line = raw_line.strip()
            if not line.startswith(("-", "•", "·")):
                continue
            option_line = re.sub(r"^[\s\-•·]+", "", line).strip()
            if not option_line:
                continue
            option_name, option_cmd = parse_special_option_line(option_line)
            if not option_name or not option_cmd:
                continue
            option_matches.append((option_name, option_cmd))

        def compact_token(value):
            return re.sub(r"[^a-z0-9]", "", str(value or "").lower())

        strength_aliases = {
            "l": {"lp", "lk", "light"},
            "light": {"lp", "lk", "light"},
            "m": {"mp", "mk", "medium"},
            "medium": {"mp", "mk", "medium"},
            "h": {"hp", "hk", "heavy"},
            "heavy": {"hp", "hk", "heavy"},
            "lp": {"lp", "light"},
            "mp": {"mp", "medium"},
            "hp": {"hp", "heavy"},
            "lk": {"lk", "light"},
            "mk": {"mk", "medium"},
            "hk": {"hk", "heavy"},
            "od": {"od", "ex", "pp", "kk"},
            "ex": {"od", "ex", "pp", "kk"},
        }

        special_query = (content_no_mentions or "").strip()
        raw_special_reply_lower = special_query.lower()
        special_query_lower = raw_special_reply_lower
        if special_strength_reply_mode == "both":
            special_request_mode = "both"
        elif special_strength_reply_mode == "gif" or gif_query:
            special_request_mode = "gif"
        else:
            special_request_mode = "frame"

        selected_option_name = None
        selected_option_cmd = None
        reply_compact = compact_token(raw_special_reply_lower)
        if option_matches and reply_compact:
            exact_option_matches = []
            for option_name, option_cmd in option_matches:
                option_name_lower = option_name.lower()
                option_name_fireball_alias = re.sub(r"hadou?ken", "fireball", option_name_lower)
                if (
                    reply_compact == compact_token(option_name)
                    or reply_compact == compact_token(option_name_fireball_alias)
                    or reply_compact == compact_token(option_cmd)
                ):
                    exact_option_matches.append((option_name, option_cmd))
            if len(exact_option_matches) == 1:
                selected_option_name, selected_option_cmd = exact_option_matches[0]
            elif not exact_option_matches and raw_special_reply_lower in strength_aliases:
                alias_tokens = strength_aliases[raw_special_reply_lower]
                for option_name, option_cmd in option_matches:
                    option_name_tokens = set(re.findall(r"[a-z0-9]+", option_name.lower()))
                    option_cmd_tokens = set(re.findall(r"[a-z0-9]+", option_cmd.lower()))
                    if alias_tokens & option_name_tokens or alias_tokens & option_cmd_tokens:
                        selected_option_name = option_name
                        selected_option_cmd = option_cmd
                        break

            if not selected_option_name and not selected_option_cmd:
                reply_tokens = set(re.findall(r"[a-z0-9]+", raw_special_reply_lower))
                scored_matches = []
                for option_name, option_cmd in option_matches:
                    option_name_tokens = set(re.findall(r"[a-z0-9]+", option_name.lower()))
                    overlap = len(reply_tokens & option_name_tokens)
                    if overlap > 0:
                        scored_matches.append((overlap, option_name, option_cmd))
                if scored_matches:
                    scored_matches.sort(key=lambda item: item[0], reverse=True)
                    top_score = scored_matches[0][0]
                    top_matches = [item for item in scored_matches if item[0] == top_score]
                    if len(top_matches) == 1:
                        _, selected_option_name, selected_option_cmd = top_matches[0]

        if selected_option_name or selected_option_cmd:
            selected_value = selected_option_cmd or selected_option_name
            if char_hint:
                resolved_char = resolve_character_key(char_hint) or normalize_char_name(char_hint)
                for direct_value in (selected_option_cmd, selected_option_name):
                    if not direct_value:
                        continue
                    direct_row = None
                    direct_value_norm = str(direct_value).lower().strip()
                    for candidate_row in FRAME_DATA.get(resolved_char, []):
                        candidate_num_cmd = str(candidate_row.get("numCmd", "")).lower().strip()
                        if candidate_num_cmd == direct_value_norm:
                            direct_row = candidate_row
                            break
                    if direct_row is None:
                        direct_row = lookup_frame_data(resolved_char, direct_value)
                    if direct_row:
                        if special_request_mode == "gif":
                            gif_links = []
                            direct_link = lookup_hitbox_gif_link(direct_row)
                            if direct_link:
                                gif_links.append(direct_link)
                            else:
                                gif_links = collect_hitbox_gif_links_from_text(
                                    f"{char_hint} {direct_value} gif",
                                    frame_rows=[direct_row],
                                    limit=1,
                                )
                            if gif_links:
                                await message.reply(gif_links[0])
                            else:
                                missing_gif_msg = (
                                    "I have frame data for that move but no hitbox gif link yet. "
                                    f"<@{SCROLLS_MAINTAINER_USER_ID}> {SCROLLS_FIX_REQUEST_TEXT}"
                                )
                                await message.reply(missing_gif_msg)
                        elif special_request_mode == "both":
                            await send_frame_table_response(message, [direct_row], format_frame_data(direct_row))
                            gif_links = []
                            direct_link = lookup_hitbox_gif_link(direct_row)
                            if direct_link:
                                gif_links.append(direct_link)
                            else:
                                gif_links = collect_hitbox_gif_links_from_text(
                                    f"{char_hint} {direct_value} gif",
                                    frame_rows=[direct_row],
                                    limit=1,
                                )
                            if gif_links:
                                await send_gif_links_response(message, gif_links)
                            else:
                                missing_gif_msg = (
                                    "I have frame data for that move but no hitbox gif link yet. "
                                    f"<@{SCROLLS_MAINTAINER_USER_ID}> {SCROLLS_FIX_REQUEST_TEXT}"
                                )
                                await message.reply(missing_gif_msg)
                        else:
                            await send_frame_table_response(message, [direct_row], format_frame_data(direct_row))
                        return
            special_query = f"{char_hint} {selected_value}".strip()
            special_query_lower = special_query.lower()

        if char_hint:
            normalized_hint = normalize_char_name(char_hint)
            if normalized_hint not in special_query_lower:
                special_query = f"{char_hint} {special_query}".strip()
                special_query_lower = special_query.lower()

        if base_hint and base_hint not in special_query_lower and not selected_option_cmd:
            if re.fullmatch(r"(lp|mp|hp|lk|mk|hk|od|ex|light|medium|heavy|l|m|h)", raw_special_reply_lower):
                special_query = f"{special_query} {base_hint}".strip()
            elif not re.search(r"\b(lp|mp|hp|lk|mk|hk|od|ex|light|medium|heavy|l|m|h)\b", special_query_lower):
                special_query = f"{special_query} {base_hint}".strip()
            special_query_lower = special_query.lower()

        if special_request_mode == "gif":
            if not re.search(r"\b(gif|gifs|hitbox|hitboxes)\b", special_query_lower):
                special_query = f"{special_query} gif".strip()
        elif special_request_mode == "both":
            if not re.search(r"\b(gif|gifs|hitbox|hitboxes)\b", special_query_lower):
                special_query = f"{special_query} gif framedata".strip()
        elif not (
            "framedata" in special_query_lower
            or "frame data" in special_query_lower
            or re.search(r"\bframes?\b", special_query_lower)
        ):
            special_query = f"{special_query} framedata".strip()

        special_payload = find_moves_in_text(special_query.lower())
        special_data = special_payload.get("data", "")
        special_rows = special_payload.get("rows", [])
        if "Special Strength Options" in special_data:
            sent_prompt = await message.reply(special_data)
            remember_special_strength_prompt_mode(
                sent_prompt.id,
                special_request_mode,
            )
            return
        if special_request_mode == "gif" and special_rows:
            gif_links = []
            if len(special_rows) == 1:
                direct_link = lookup_hitbox_gif_link(special_rows[0])
                if direct_link:
                    gif_links.append(direct_link)
            if not gif_links:
                gif_links = collect_hitbox_gif_links_from_text(
                    special_query,
                    frame_rows=special_rows,
                    limit=1,
                )
            if gif_links:
                await message.reply(gif_links[0])
                return
            missing_gif_msg = (
                "I have frame data for that move but no hitbox gif link yet. "
                f"<@{SCROLLS_MAINTAINER_USER_ID}> {SCROLLS_FIX_REQUEST_TEXT}"
            )
            await message.reply(missing_gif_msg)
            return
        if special_request_mode == "both" and special_rows:
            await send_frame_table_response(message, special_rows, special_data)
            gif_links = []
            if len(special_rows) == 1:
                direct_link = lookup_hitbox_gif_link(special_rows[0])
                if direct_link:
                    gif_links.append(direct_link)
            if not gif_links:
                gif_links = collect_hitbox_gif_links_from_text(
                    special_query,
                    frame_rows=special_rows,
                    limit=1,
                )
            if gif_links:
                await send_gif_links_response(message, gif_links)
                return
            missing_gif_msg = (
                "I have frame data for that move but no hitbox gif link yet. "
                f"<@{SCROLLS_MAINTAINER_USER_ID}> {SCROLLS_FIX_REQUEST_TEXT}"
            )
            await message.reply(missing_gif_msg)
            return
        if special_payload.get("mode") == "frame" and special_rows and special_data:
            await send_frame_table_response(message, special_rows, special_data)
            return
        await message.reply(replied_context)
        return



    # media check
    media_found = False
    if check_media:
        # check gif embeds
        has_gif = any("tenor.com" in str(e.url or "") or "giphy.com" in str(e.url or "") or (e.type == "gifv") for e in message.embeds)
        # check gif links
        if not has_gif:
            has_gif = "tenor.com" in content_lower or "giphy.com" in content_lower or ".gif" in content_lower
        
        # check images
        has_image = any(att.content_type and att.content_type.startswith("image/") for att in message.attachments)
        
        if has_gif or has_image:
            media_found = True

    # llm response (mentioned OR replying to bot)
    should_respond = client.user.mentioned_in(message) or is_reply_to_bot or replied_context is not None
    if should_respond:
        prompt = content_no_mentions
        media_parts = []
        media_notes = []
        attachments = await get_message_media_items(message, bot_user=client.user)
        if attachments:
            if GEMINI_ENABLED:
                media_parts, media_notes = await build_gemini_media_parts(attachments)
            elif MIMO_ENABLED:
                media_parts, media_notes = await build_mimo_media_parts(attachments)
            else:
                for attachment in attachments:
                    filename = attachment.get("filename") or "media"
                    url = attachment.get("url") or ""
                    media_notes.append(f"{filename}: {url}".strip(": "))
        media_context = get_media_context(attachments, media_parts, media_notes)
        has_prompt_or_media = bool(prompt) or bool(media_parts) or bool(media_notes)
        if has_prompt_or_media and not LLM_ENABLED:
            offline_reason = LLM_PROVIDER_ERROR or (
                "Enable one of USE_GEMINI_API, USE_OPENROUTER_API, or USE_MIMO_API and configure its API key."
            )
            await message.reply(
                f"Aiya! The oracle is offline. {offline_reason}"
            )
            return
        if has_prompt_or_media and LLM_ENABLED:
             try:
                # build msg list
                selected_figures_str = get_selected_figures_str(message.guild)
                
                # check if replying to improvement message
                is_improvement_reply = replied_context and "improved" in replied_context.lower()
                
                if is_improvement_reply:
                    active_prompt = IMPROVEMENT_PROMPT.format(
                        selected_figures_str=selected_figures_str
                    )
                else:
                    active_prompt = SYSTEM_PROMPT.format(selected_figures_str=selected_figures_str)

                history_char_budget = estimate_llm_context_history_char_budget(
                    active_prompt,
                    prompt,
                    replied_context,
                    media_context,
                    MOVE_DEFINITIONS,
                )
                context_history = await build_llm_context_history(
                    message,
                    strip_discord_mentions,
                    bot_user=client.user,
                    char_budget=history_char_budget,
                )
                context_str = "\n".join(context_history)
                 
                llm_messages = [
                    {"role": "system", "content": active_prompt}
                ]
                
                # add context msg
                if context_str:
                        llm_messages.append({"role": "user", "content": f"Here is the recent chat context:\n{context_str}"})
                        llm_messages.append({"role": "assistant", "content": "Understood. I have the context."})
                
                # if replying to bub's message, add that as explicit context
                user_parts = []
                user_content = prompt
                prompting_user_identity = build_prompting_user_identity(message)
                if media_context:
                    user_content = f"{user_content}\n\n{media_context}" if user_content else media_context
                if user_content:
                    user_content = f"{prompting_user_identity}\nUser message: {user_content}"
                else:
                    user_content = prompting_user_identity
                if replied_context:
                    llm_messages.append({"role": "assistant", "content": replied_context})
                    if prompt:
                        user_parts.append({"text": f"{prompting_user_identity}\n(Replying to your message above) {prompt}"})
                    else:
                        user_parts.append({"text": prompting_user_identity})
                else:
                    if prompt:
                        user_parts.append({"text": f"{prompting_user_identity}\nUser message: {prompt}"})
                    else:
                        user_parts.append({"text": prompting_user_identity})
                if media_parts:
                    user_parts.extend(media_parts)
                if media_notes:
                    user_parts.append({"text": f"Media notes: {'; '.join(media_notes)}"})
                if media_context:
                    user_parts.append({"text": media_context})
                if user_parts:
                    user_message = {
                        "role": "user",
                        "content": user_content,
                        "parts": user_parts,
                    }
                    llm_messages.append(user_message)
                
                # push to queue
                queue = ensure_message_queue_started()
                await queue.put((message, llm_messages, fallback_reply, None, frame_reply_embeds, frame_reply_rows))

             except Exception as e:
                await message.reply(f"Error generating response: {e}")

def main():
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found in .env")
    else:
        client.run(TOKEN)


if __name__ == "__main__":
    main()
