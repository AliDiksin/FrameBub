"""Main Discord message router. Owns on_message flow: quiz, menus, combos, per-game
frame/gif routing, SF6 prompt replies, buenavista LLM hook, and invalid-query fallback.
Also holds SF6 compat wrappers (load_frame_data, find_moves_in_text) for import bot regressions."""

import discord
import asyncio
import random
import datetime
import difflib
import json
import os
import re
from dotenv import load_dotenv

load_dotenv()

from bubbot.data.aliases import (
    CHARACTER_ALIASES,
    CHARACTER_INPUT_ALIASES,
    DP_PREFIX_EXCEPTIONS,
    INPUT_ALIASES,
)
from bubbot.features.reminders import ReminderManager
import bubbot.features.quiz as quiz_module
import bubbot.frame_data.gif_lookup as gif_lookup_module
import bubbot.frame_data.frame_output as frame_output_module
import bubbot.frame_data.sf6_loader as sf6_loader
import bubbot.frame_data.sf6_lookup as sf6_lookup
import bubbot.frame_data.sf6_parser as sf6_parser
import bubbot.frame_data.sf6_prompt_replies as sf6_prompt_replies
sf6_module = sf6_parser
import bubbot.frame_data.ggst_frame_data as ggst_module
import bubbot.frame_data.sfv_frame_data as sfv_module
import bubbot.frame_data.tuco_frame_data as tuco_module
import bubbot.frame_data.bbcf_frame_data as bbcf_module
import bubbot.frame_data.ggacr_frame_data as ggacr_module
import bubbot.frame_data.cotw_frame_data as cotw_module
import bubbot.frame_data.third_strike_frame_data as third_strike_module
import bubbot.frame_data.mk1_frame_data as mk1_module
import bubbot.frame_data.combo_data as combo_data_module
import bubbot.features.menu_system as menu_system
from bubbot.features.fg_glossary import build_glossary_definition_embed, build_glossary_link_view, normalize_glossary_term
from bubbot.frame_data.frame_output import (
    send_character_stats_response,
    send_frame_embeds_with_views,
    send_frame_table_response,
    send_gif_links_response,
    send_missing_hitbox_gif_reply,
)
from bubbot.frame_data.gif_lookup import get_frame_row_gif_links
from bubbot.runtime.config import (
    BASE_DIR,
    LOCAL_HITBOX_GIF_EXTENSIONS,
    LOCAL_HITBOX_GIF_ROOT,
    RANGE_MISSING_PLACEHOLDERS,
    MISSING_SCROLLS_TEXT,
    PUBLIC_INVALID_QUERY_TEXT,
    RANGE_SCROLLS_MISSING_TEXT,
    TOKEN,
)
from bubbot.features.failed_prompt_report import (
    attach_failed_prompt_report_button,
    build_failed_prompt_report_view,
)
from bubbot.utils.character_lookup import find_aliases_in_text, resolve_alias_key, text_mentions_alias
from bubbot.utils.response_log import (
    FAILED_PROMPT_REASONS,
    INTERACTION_MENU,
    INTERACTION_PROMPT,
    build_log_record,
    log_message_and_reply,
    notify_owner,
    log_record,
)
from bubbot.utils.text_utils import compact_key, contains_token_sequence, word_tokens
from bubbot.runtime.buenavista_extension import buenavista_extension
from collections import deque
from bubbot.runtime.slash_commands import register_slash_commands
from bubbot.runtime.startup import handle_ready
from bubbot.runtime import message_context
from bubbot.runtime import disambiguation
from bubbot.features import property_results
from bubbot.runtime import frame_routing
from bubbot.runtime import sf6_message_flow












buenavista_extension.log_status()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(
    client,
    allowed_contexts=discord.app_commands.AppCommandContext(
        guild=True,
        dm_channel=True,
        private_channel=True,
    ),
    allowed_installs=discord.app_commands.AppInstallationType(guild=True, user=True),
)
message_context.configure(
    client=client,
    menu_system=menu_system,
    build_failed_prompt_report_view=build_failed_prompt_report_view,
    attach_failed_prompt_report_button=attach_failed_prompt_report_button,
    FAILED_PROMPT_REASONS=FAILED_PROMPT_REASONS,
    INTERACTION_MENU=INTERACTION_MENU,
    INTERACTION_PROMPT=INTERACTION_PROMPT,
    build_log_record=build_log_record,
    log_message_and_reply=log_message_and_reply,
    notify_owner=notify_owner,
    log_record=log_record,
    build_glossary_definition_embed=build_glossary_definition_embed,
    build_glossary_link_view=build_glossary_link_view,
    normalize_glossary_term=normalize_glossary_term,
    RANGE_MISSING_PLACEHOLDERS=RANGE_MISSING_PLACEHOLDERS,
)


def truncate_message(text, limit=1800):
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."







_BOSCH_BREAKDANCE_VIDEO_URL = (
    "https://cdn.discordapp.com/attachments/1345474577316319265/"
    "1520875333803577386/breakdance.mp4"
)


_reply_and_log_response = message_context._reply_and_log_response
_message_prompt_text = message_context._message_prompt_text
_record_frame_data_ids = message_context._record_frame_data_ids
_FRAME_DATA_RESPONSE_IDS = message_context._FRAME_DATA_RESPONSE_IDS
_is_reply_to_suppressed_bub_message = message_context._is_reply_to_suppressed_bub_message
_is_reply_to_frame_data = message_context._is_reply_to_frame_data
is_missing_attack_range_value = message_context.is_missing_attack_range_value
strip_url_like_text = message_context.strip_url_like_text
message_directly_mentions_bot = message_context.message_directly_mentions_bot
is_plain_bot_mention_only = message_context.is_plain_bot_mention_only
_send_main_menu_for_plain_mention = message_context._send_main_menu_for_plain_mention
has_explicit_gif_lookup_intent = message_context.has_explicit_gif_lookup_intent
extract_glossary_lookup_term = message_context.extract_glossary_lookup_term
maybe_handle_glossary_lookup = message_context.maybe_handle_glossary_lookup
strip_discord_mentions = message_context.strip_discord_mentions
_message_is_numbered_disambiguation_prompt = message_context._message_is_numbered_disambiguation_prompt
_text_is_numbered_disambiguation_prompt = message_context._text_is_numbered_disambiguation_prompt
DISAMBIGUATION_GAME_CONFIGS = disambiguation.DISAMBIGUATION_GAME_CONFIGS
_compact_disambiguation_text = disambiguation._compact_disambiguation_text
_parse_disambiguation_options = disambiguation._parse_disambiguation_options
_disambiguation_reply_number = disambiguation._disambiguation_reply_number
_select_disambiguation_option = disambiguation._select_disambiguation_option
_row_matches_disambiguation_option = disambiguation._row_matches_disambiguation_option
_find_selected_disambiguation_row = disambiguation._find_selected_disambiguation_row
_fetch_referenced_message = message_context._fetch_referenced_message
_reply_output_mode_from_source_text = disambiguation._reply_output_mode_from_source_text
_handle_cross_game_disambiguation_reply = disambiguation._handle_cross_game_disambiguation_reply
_sf6_prompt_reply_deps = disambiguation._sf6_prompt_reply_deps
_resolve_special_strength_reply_mode = disambiguation._resolve_special_strength_reply_mode
_handle_sf6_prompt_disambiguation_reply = disambiguation._handle_sf6_prompt_disambiguation_reply
PROPERTY_VALUE_ALIASES = property_results.PROPERTY_VALUE_ALIASES
_PROPERTY_REQUEST_PRIORITY = property_results._PROPERTY_REQUEST_PRIORITY
_requested_property_key = property_results._requested_property_key
_format_requested_property_reply = property_results._format_requested_property_reply
_game_key_for_frame_module = property_results._game_key_for_frame_module
_property_reply_view = property_results._property_reply_view
_send_property_value_reply = property_results._send_property_value_reply
PropertyValueView = property_results.PropertyValueView
PropertyCompareButton = property_results.PropertyCompareButton
PropertyFullFrameDataButton = property_results.PropertyFullFrameDataButton
PropertyCompareSelectView = property_results.PropertyCompareSelectView
PropertyCompareSelect = property_results.PropertyCompareSelect
_try_route_combo_query = frame_routing._try_route_combo_query
_send_cross_game_lookup_response = property_results._send_cross_game_lookup_response


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
        strength = match.group(2)
        button = match.group(3)
        short = f"{strength_map[strength]}{button_map[button]}"
        return f"{'8' if match.group(1) else 'jump'}{short if match.group(1) else f' {short}'}"

    text = re.sub(
        r"\b(?:(neutral|n)\s+)?jump\s+(light|medium|heavy)\s+(punch|kick)\b",
        replace_named_jump,
        text,
    )
    text = re.sub(r"\b(?:neutral|n)\s+j\s*\.?\s*([lmh][pk])\b", r"8\1", text)
    text = re.sub(r"\bn\.?j\s*([lmh][pk])\b", r"8\1", text)
    text = re.sub(r"\bnj\s*([lmh][pk])\b", r"8\1", text)
    text = re.sub(r"\b(?:neutral|n)\s+jump\s+([lmh][pk])\b", r"8\1", text)
    text = re.sub(r"\bjump\s+([lmh][pk])\b", r"jump \1", text)
    text = re.sub(r"\bj\s*\.?\s*([lmh][pk])\b", r"jump \1", text)
    text = re.sub(r"\bn\.?j\s*\.?\s*([1-9][0-9]*[a-z]{1,3})\b", r"neutral j\1", text)
    text = re.sub(r"\bnj\s*([1-9][0-9]*[a-z]{1,3})\b", r"neutral j\1", text)
    text = re.sub(r"\bj\s*\.?\s*([1-9][0-9]*[a-z]{1,3})\b", r"j\1", text)
    return text










FRAME_DATA = {}
FRAME_STATS = {}
HITBOX_GIF_DATA = {}
RANGE_DATA = {}

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


# SF6 loader/parser compat surface (root bot.py and regressions import these names)
def load_frame_data():
    """Compatibility wrapper for SF6 ODS loading."""
    sf6_loader.load_frame_data(
        {
            "FRAME_DATA": FRAME_DATA,
            "FRAME_STATS": FRAME_STATS,
            "HITBOX_GIF_DATA": HITBOX_GIF_DATA,
            "RANGE_DATA": RANGE_DATA,
            "CHARACTER_ALIASES": CHARACTER_ALIASES,
            "normalize_char_name": normalize_char_name,
            "resolve_character_key": resolve_character_key,
            "lookup_frame_data": lookup_frame_data,
            "find_moves_in_text": find_moves_in_text,
            "is_missing_attack_range_value": is_missing_attack_range_value,
            "strip_discord_mentions": strip_discord_mentions,
            "build_num_cmd_candidates_for_gif": build_num_cmd_candidates_for_gif,
            "configure_extracted_modules": configure_extracted_modules,
            "load_local_hitbox_gif_data": load_local_hitbox_gif_data,
            "quiz_module": quiz_module,
            "frame_output_module": frame_output_module,
        }
    )

def find_moves_in_text(text):
    return sf6_parser.find_moves_in_text(
        {
            "CHARACTER_ALIASES": CHARACTER_ALIASES,
            "FRAME_DATA": FRAME_DATA,
            "FRAME_STATS": FRAME_STATS,
            "strip_discord_mentions": strip_discord_mentions,
            "normalize_jump_normal_text": normalize_jump_normal_text,
            "word_tokens": word_tokens,
            "contains_token_sequence": contains_token_sequence,
            "has_explicit_gif_lookup_intent": has_explicit_gif_lookup_intent,
            "lookup_frame_data": lookup_frame_data,
            "normalize_char_name": normalize_char_name,
            "resolve_character_key": resolve_character_key,
            "normalize_num_cmd_token": normalize_num_cmd_token,
            "check_punish": check_punish,
        },
        text,
    )

def lookup_frame_data(character, move_input, _seen_inputs=None):
    return sf6_lookup.lookup_frame_data(
        {
            "FRAME_DATA": FRAME_DATA,
            "INPUT_ALIASES": INPUT_ALIASES,
            "CHARACTER_INPUT_ALIASES": CHARACTER_INPUT_ALIASES,
            "DP_PREFIX_EXCEPTIONS": DP_PREFIX_EXCEPTIONS,
            "normalize_jump_normal_text": normalize_jump_normal_text,
            "compact_key": compact_key,
            "compact_move_token": compact_move_token,
            "extract_button_suffix": extract_button_suffix,
            "normalize_num_cmd_token": normalize_num_cmd_token,
        },
        character,
        move_input,
        _seen_inputs=_seen_inputs,
    )

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

reminder_task_handle = None
_TYPING_DISABLED = False
_DATA_LOADED = False
reminder_manager = ReminderManager(
    client,
    truncate_message,
    buenavista_extension.build_reminder_ack_text,
    buenavista_extension.build_reminder_fire_text,
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
    combo_data_module.configure(
        resolve_sf6_character_key=resolve_character_key,
        resolve_mk1_character_key=mk1_module.resolve_character_key,
        sf6_character_aliases=CHARACTER_ALIASES,
        mk1_character_aliases=mk1_module.MK1_CHARACTER_ALIASES,
    )
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
        get_sf6_move_image_url=frame_output_module.get_sf6_move_image_url,
    )
    frame_output_module.configure(
        is_missing_attack_range_value=is_missing_attack_range_value,
        truncate_message=truncate_message,
        send_deleted_message_failsafe=send_deleted_message_failsafe,
        get_frame_row_gif_links=gif_lookup_module.get_frame_row_gif_links,
        get_existing_local_gif_asset_paths=gif_lookup_module.get_existing_local_gif_asset_paths,
        is_deleted_message_reference_error=is_deleted_message_reference_error,
        RANGE_SCROLLS_MISSING_TEXT=RANGE_SCROLLS_MISSING_TEXT,
        FRAME_STATS=FRAME_STATS,
        normalize_char_name=normalize_char_name,
    )
    property_results.configure(
        _FRAME_MODULES={
            sf6_module: "sf6",
            sfv_module: "sfv",
            ggst_module: "ggst",
            tuco_module: "2xko",
            bbcf_module: "bbcf",
            ggacr_module: "ggacr",
            cotw_module: "cotw",
            third_strike_module: "3s",
            mk1_module: "mk1",
        },
        _record_frame_data_ids=_record_frame_data_ids,
        iter_unique_frame_rows=frame_output_module.iter_unique_frame_rows,
        format_range_only_reply=frame_output_module.format_range_only_reply,
        truncate_message=truncate_message,
    )
    disambiguation.configure(
        client=client,
        _fetch_referenced_message=_fetch_referenced_message,
        strip_discord_mentions=strip_discord_mentions,
        third_strike_module=third_strike_module,
        _requested_property_key=_requested_property_key,
        _format_requested_property_reply=_format_requested_property_reply,
        _game_key_for_frame_module=_game_key_for_frame_module,
        _send_property_value_reply=_send_property_value_reply,
        sf6_prompt_replies=sf6_prompt_replies,
        FRAME_DATA=FRAME_DATA,
        send_missing_hitbox_gif_reply=send_missing_hitbox_gif_reply,
        normalize_char_name=normalize_char_name,
        resolve_character_key=resolve_character_key,
        lookup_frame_data=lookup_frame_data,
        lookup_hitbox_gif_link=gif_lookup_module.lookup_hitbox_gif_link,
        collect_hitbox_gif_links_from_text=gif_lookup_module.collect_hitbox_gif_links_from_text,
        send_frame_table_response=send_frame_table_response,
        send_gif_links_response=send_gif_links_response,
        find_moves_in_text=find_moves_in_text,
        _reply_and_log_response=_reply_and_log_response,
        _message_prompt_text=_message_prompt_text,
        has_explicit_gif_lookup_intent=has_explicit_gif_lookup_intent,
        _record_frame_data_ids=_record_frame_data_ids,
        sfv_module=sfv_module,
        ggst_module=ggst_module,
        ggacr_module=ggacr_module,
        tuco_module=tuco_module,
        bbcf_module=bbcf_module,
        cotw_module=cotw_module,
        mk1_module=mk1_module,
    )
    frame_routing.configure(
        client=client,
        buenavista_extension=buenavista_extension,
        combo_data_module=combo_data_module,
        sf6_module=sf6_module,
        sfv_module=sfv_module,
        ggst_module=ggst_module,
        tuco_module=tuco_module,
        bbcf_module=bbcf_module,
        ggacr_module=ggacr_module,
        cotw_module=cotw_module,
        third_strike_module=third_strike_module,
        mk1_module=mk1_module,
        CHARACTER_ALIASES=CHARACTER_ALIASES,
        FRAME_DATA=FRAME_DATA,
        resolve_character_from_aliases_in_text=resolve_character_from_aliases_in_text,
        text_mentions_character_from_aliases=text_mentions_character_from_aliases,
        find_moves_in_text=find_moves_in_text,
        _fetch_referenced_message=_fetch_referenced_message,
        _requested_property_key=_requested_property_key,
        _send_cross_game_lookup_response=_send_cross_game_lookup_response,
        _reply_and_log_response=_reply_and_log_response,
        strip_discord_mentions=strip_discord_mentions,
        _record_frame_data_ids=_record_frame_data_ids,
    )
    sf6_message_flow.configure(
        client=client,
        buenavista_extension=buenavista_extension,
        sf6_prompt_replies=sf6_prompt_replies,
        gif_lookup_module=gif_lookup_module,
        find_moves_in_text=find_moves_in_text,
        strip_discord_mentions=strip_discord_mentions,
        build_frame_embeds=build_frame_embeds,
        iter_unique_frame_rows=iter_unique_frame_rows,
        send_character_stats_response=send_character_stats_response,
        send_frame_table_response=send_frame_table_response,
        send_gif_links_response=send_gif_links_response,
        send_missing_hitbox_gif_reply=send_missing_hitbox_gif_reply,
        send_frame_embeds_with_views=send_frame_embeds_with_views,
        collect_hitbox_gif_links_from_text=collect_hitbox_gif_links_from_text,
        _record_frame_data_ids=_record_frame_data_ids,
        _reply_and_log_response=_reply_and_log_response,
        _requested_property_key=_requested_property_key,
        _format_requested_property_reply=_format_requested_property_reply,
        _send_property_value_reply=_send_property_value_reply,
        _resolve_special_strength_reply_mode=_resolve_special_strength_reply_mode,
        _sf6_prompt_reply_deps=_sf6_prompt_reply_deps,
        format_range_only_reply=format_range_only_reply,
        format_super_gain_only_reply=format_super_gain_only_reply,
        format_hitconfirm_only_reply=format_hitconfirm_only_reply,
        format_startup_only_reply=format_startup_only_reply,
        is_deleted_message_reference_error=is_deleted_message_reference_error,
        send_deleted_message_failsafe=send_deleted_message_failsafe,
        MISSING_SCROLLS_TEXT=MISSING_SCROLLS_TEXT,
        PUBLIC_INVALID_QUERY_TEXT=PUBLIC_INVALID_QUERY_TEXT,
    )


# NL combo routing before SF6 frame parser (SF6 Combos.ods + mk1/combos.json)


def is_deleted_message_reference_error(error):
    if isinstance(error, discord.NotFound):
        return True
    if isinstance(error, discord.HTTPException):
        text = str(error).lower()
        if "message_reference" in text and "unknown message" in text:
            return True
    return False


async def send_deleted_message_failsafe(channel):
    try:
        await channel.send("That reply target disappeared, so I cannot attach the response there.")
    except Exception:
        pass


@client.event
async def on_ready():
    global reminder_task_handle
    global _DATA_LOADED
    reminder_task_handle = await handle_ready(
        {
            "client": client,
            "tree": tree,
            "reminder_manager": reminder_manager,
            "reminder_task_handle": reminder_task_handle,
            "buenavista_extension": buenavista_extension,
            "load_frame_data": load_frame_data,
            "configure_extracted_modules": configure_extracted_modules,
            "quiz_module": quiz_module,
            "menu_system": menu_system,
            "frame_output_module": frame_output_module,
            "ggst_module": ggst_module,
            "sfv_module": sfv_module,
            "tuco_module": tuco_module,
            "bbcf_module": bbcf_module,
            "ggacr_module": ggacr_module,
            "cotw_module": cotw_module,
            "third_strike_module": third_strike_module,
            "mk1_module": mk1_module,
            "combo_data_module": combo_data_module,
            "FRAME_DATA": FRAME_DATA,
            "FRAME_STATS": FRAME_STATS,
            "CHARACTER_ALIASES": CHARACTER_ALIASES,
            "resolve_character_key": resolve_character_key,
            "normalize_char_name": normalize_char_name,
            "lookup_frame_data": lookup_frame_data,
            "find_moves_in_text": find_moves_in_text,
            "is_missing_attack_range_value": is_missing_attack_range_value,
            "clean_embed_value": clean_embed_value,
            "truncate_embed_value": truncate_embed_value,
            "build_frame_embed": build_frame_embed,
            "strip_discord_mentions": strip_discord_mentions,
            "send_frame_embeds_with_views": send_frame_embeds_with_views,
        }
    )
    _DATA_LOADED = True
    print("[startup] All game data loaded; message handling is now active.", flush=True)


@client.event
async def on_interaction(interaction):
    """Acknowledge stale Bub components after a restart instead of timing out."""
    if getattr(interaction, "type", None) != discord.InteractionType.component:
        return
    message = getattr(interaction, "message", None)
    if message is None or getattr(getattr(message, "author", None), "id", None) != getattr(client.user, "id", None):
        return
    await asyncio.sleep(1.0)
    if interaction.response.is_done():
        return
    try:
        await interaction.response.send_message(
            "This menu was created before Bub restarted. Please open `/bub` again.",
            ephemeral=True,
        )
    except Exception as error:
        print(f"[menu] stale component response failed: {error}", flush=True)

@client.event
async def on_message(message):
    try:
        await _handle_message(message)
    except Exception as e:
        print(f"[on_message] unhandled error: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()


async def _handle_message(message):
    # ignore bot msgs
    if message.author == client.user:
        return

    if not _DATA_LOADED:
        return

    content_raw = message.content or ""
    content_no_mentions = strip_discord_mentions(content_raw)
    content_lower = content_no_mentions.lower()

    # Plain @bub or @bub sf6 opens menu without other text
    if is_plain_bot_mention_only(message):
        await _send_main_menu_for_plain_mention(message)
        return

    directly_mentions_bot = message_directly_mentions_bot(message)

    game_only = menu_system.parse_game_only_mention(content_no_mentions)
    if directly_mentions_bot and game_only:
        await menu_system.send_game_menu(message.channel, game_only, owner_id=message.author.id)
        try:
            log_record(
                build_log_record(
                    interaction_type=INTERACTION_MENU,
                    reason="game_mention_menu",
                    prompt=str(getattr(message, "content", "") or ""),
                    response_text=f"Opened {menu_system._game_label(game_only)} menu embed.",
                    response_kind="embed",
                    source_message=message,
                )
            )
        except Exception as log_error:
            print(f"Response log error: {log_error}", flush=True)
        return

    if await buenavista_extension.maybe_handle_pin_tierlist(
        message=message,
        content_no_mentions=content_no_mentions,
    ):
        return

    # Quiz beats frame lookup while a session is active (must be @bub or reply to quiz msg)
    quiz_result = await quiz_module.route_message(client, message, content_lower)
    if quiz_result is not False:
        return

    if "bosch breakdance" in content_lower:
        await message.reply(_BOSCH_BREAKDANCE_VIDEO_URL)
        return

    if await _handle_cross_game_disambiguation_reply(message, content_no_mentions):
        return

    if await _handle_sf6_prompt_disambiguation_reply(
        message,
        content_no_mentions,
        gif_query=has_explicit_gif_lookup_intent(content_lower),
    ):
        return


    if await buenavista_extension.maybe_handle_streetfighterdle_message(
        client=client,
        message=message,
        content_lower=content_lower,
    ):
        return

    if await maybe_handle_glossary_lookup(message, content_no_mentions, addressed=directly_mentions_bot):
        return

    await buenavista_extension.maybe_ack_streetfighterdle_score(message)

    if await _is_reply_to_suppressed_bub_message(message):
        return

    # @bub menu and @bub {char} moves shortcuts
    if directly_mentions_bot and content_lower.strip() == "menu":
        await menu_system.send_main_menu(message.channel, owner_id=message.author.id)
        return

    if directly_mentions_bot and re.fullmatch(r"\s*(?:.+\s+)?moves\s*", content_lower):
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
        sfv_char_key = resolve_character_from_aliases_in_text(
            content_lower,
            sfv_module.SFV_CHARACTER_ALIASES,
            sfv_module.SFV_FRAME_DATA.keys(),
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
        ggacr_char_key = resolve_character_from_aliases_in_text(
            content_lower,
            ggacr_module.GGACR_CHARACTER_ALIASES,
            ggacr_module.GGACR_FRAME_DATA.keys(),
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
        explicit_ggacr_moves_query = ggacr_module.query_has_explicit_ggacr_tag(content_lower)
        explicit_ggst_moves_query = bool(
            re.search(r"\b(?:ggst|strive|guilty\s+gear|guilty)\b", content_lower)
            and not explicit_ggacr_moves_query
        )
        explicit_sfv_moves_query = bool(re.search(r"\b(?:sfv|sf5|street\s*fighter\s*(?:v|5))\b", content_lower))
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
        if explicit_ggacr_moves_query and ggacr_char_key:
            await menu_system.send_character_moves_menu(message.channel, "ggacr", ggacr_char_key, owner_id=message.author.id)
            return
        if explicit_tuco_moves_query and tuco_char_key:
            await menu_system.send_character_moves_menu(message.channel, "tuco", tuco_char_key, owner_id=message.author.id)
            return
        if explicit_ggst_moves_query and ggst_char_key:
            await menu_system.send_character_moves_menu(message.channel, "ggst", ggst_char_key, owner_id=message.author.id)
            return
        if explicit_sfv_moves_query and sfv_char_key:
            await menu_system.send_character_moves_menu(message.channel, "sfv", sfv_char_key, owner_id=message.author.id)
            return
        if sf6_char_key:
            await menu_system.send_character_moves_menu(message.channel, "sf6", sf6_char_key, owner_id=message.author.id)
            return
        if ggacr_char_key and ggacr_module.is_exclusive_character(ggacr_char_key):
            await menu_system.send_character_moves_menu(message.channel, "ggacr", ggacr_char_key, owner_id=message.author.id)
            return
        if ggst_char_key:
            await menu_system.send_character_moves_menu(message.channel, "ggst", ggst_char_key, owner_id=message.author.id)
            return
        if sfv_char_key:
            await menu_system.send_character_moves_menu(message.channel, "sfv", sfv_char_key, owner_id=message.author.id)
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

    # User reminders (public) then BV catchphrase keyword replies
    if await reminder_manager.handle_message(message, content_no_mentions, content_lower):
        return

    if await buenavista_extension.maybe_handle_private_message(
        client=client,
        message=message,
        content_no_mentions=content_no_mentions,
        content_lower=content_lower,
    ):
        return

    if await _is_reply_to_frame_data(message):
        return

    cross_route_result = await frame_routing.route_cross_game(
        message,
        content_lower=content_lower,
        content_no_mentions=content_no_mentions,
        directly_mentions_bot=directly_mentions_bot,
    )
    if cross_route_result is None:
        return
    (
        fd_context_payload,
        frame_command_is_addressed,
        allow_implied_frame_routing,
    ) = cross_route_result
    await sf6_message_flow.handle_sf6_message(
        message,
        content_lower=content_lower,
        content_no_mentions=content_no_mentions,
        fd_context_payload=fd_context_payload,
        frame_command_is_addressed=frame_command_is_addressed,
        allow_implied_frame_routing=allow_implied_frame_routing,
        directly_mentions_bot=directly_mentions_bot,
    )






register_slash_commands(
    tree,
    {
        "frame_data": FRAME_DATA,
        "frame_stats": FRAME_STATS,
        "resolve_character_key": resolve_character_key,
        "find_moves_in_text": find_moves_in_text,
        "frame_output_module": frame_output_module,
        "ggst_module": ggst_module,
        "sfv_module": sfv_module,
        "tuco_module": tuco_module,
        "bbcf_module": bbcf_module,
        "ggacr_module": ggacr_module,
        "cotw_module": cotw_module,
        "third_strike_module": third_strike_module,
        "mk1_module": mk1_module,
        "combo_data_module": combo_data_module,
        "menu_system": menu_system,
        "buenavista_extension": buenavista_extension,
    },
)


def main():
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found in .env")
    else:
        client.run(TOKEN)


if __name__ == "__main__":
    main()
