import discord
import asyncio
import random
import datetime
import difflib
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
import bubbot.frame_data.ggst_frame_data as ggst_module
import bubbot.frame_data.tuco_frame_data as tuco_module
import bubbot.frame_data.bbcf_frame_data as bbcf_module
import bubbot.frame_data.cotw_frame_data as cotw_module
import bubbot.frame_data.third_strike_frame_data as third_strike_module
import bubbot.frame_data.mk1_frame_data as mk1_module
import bubbot.features.menu_system as menu_system
from bubbot.frame_data.frame_output import send_frame_embeds_with_views, send_frame_table_response, send_gif_links_response
from bubbot.frame_data.gif_lookup import get_frame_row_gif_links
from bubbot.runtime.config import (
    BASE_DIR,
    LOCAL_HITBOX_GIF_EXTENSIONS,
    LOCAL_HITBOX_GIF_ROOT,
    RANGE_MISSING_PLACEHOLDERS,
    RANGE_SCROLLS_MISSING_TEXT,
    SCROLLS_FIX_REQUEST_TEXT,
    SCROLLS_MAINTAINER_USER_ID,
    TOKEN,
)
from bubbot.utils.character_lookup import find_aliases_in_text, resolve_alias_key, text_mentions_alias
from bubbot.utils.text_utils import compact_key, contains_token_sequence, word_tokens
from bubbot.runtime.buenavista_extension import buenavista_extension
from bubbot.runtime.slash_commands import register_slash_commands
from bubbot.runtime.startup import handle_ready


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

buenavista_extension.log_status()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)


def truncate_message(text, limit=1800):
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."







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


def load_frame_data():
    """Compatibility wrapper for SF6 ODS loading."""
    sf6_loader.load_frame_data(
        {
            "FRAME_DATA": FRAME_DATA,
            "FRAME_STATS": FRAME_STATS,
            "BNB_DATA": BNB_DATA,
            "OKI_DATA": OKI_DATA,
            "CHARACTER_INFO": CHARACTER_INFO,
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
            "BNB_DATA": BNB_DATA,
            "OKI_DATA": OKI_DATA,
            "CHARACTER_INFO": CHARACTER_INFO,
            "strip_discord_mentions": strip_discord_mentions,
            "normalize_jump_normal_text": normalize_jump_normal_text,
            "word_tokens": word_tokens,
            "contains_token_sequence": contains_token_sequence,
            "has_explicit_gif_lookup_intent": has_explicit_gif_lookup_intent,
            "lookup_frame_data": lookup_frame_data,
            "normalize_char_name": normalize_char_name,
            "resolve_character_key": resolve_character_key,
            "is_missing_attack_range_value": is_missing_attack_range_value,
            "get_attack_range_details": get_attack_range_details,
            "format_attack_range_for_table": format_attack_range_for_table,
            "format_frame_data": format_frame_data,
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
            "tuco_module": tuco_module,
            "bbcf_module": bbcf_module,
            "cotw_module": cotw_module,
            "third_strike_module": third_strike_module,
            "mk1_module": mk1_module,
            "FRAME_DATA": FRAME_DATA,
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

    # Disabled by request: manual trigger for the old daily "Hello everyone" batch.
    # Re-enable by uncommenting this block.
    # if client.user.mentioned_in(message) and "do the thing" in content_lower:
    #     print(f"[daily-message] Manual trigger received from user_id={message.author.id}", flush=True)
    #     await buenavista_extension.send_daily_messages(message.channel)
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

    if await buenavista_extension.maybe_handle_private_message(
        client=client,
        message=message,
        content_no_mentions=content_no_mentions,
        content_lower=content_lower,
    ):
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
        rewritten_ggst_query = await buenavista_extension.rewrite_ggst_lookup_query(
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
                print(f"[ggst-parser-private] rewritten query: {rewritten_ggst_query}", flush=True)

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


    # logic flags
    check_media = False
    replied_context = None  # store bub's original message if replying to bot
    special_strength_reply_mode = None
    is_reply_to_bot = False
    
    
    # check mentions
    if client.user.mentioned_in(message):
        check_media = True

    replied_context = None 
    

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

    should_try_private_lookup_rewrite = bool(
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
    if should_try_private_lookup_rewrite:
        rewritten_lookup_query = await buenavista_extension.rewrite_sf_lookup_query(
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
                print(f"[parser-private] rewritten query: {rewritten_lookup_query}", flush=True)

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
                    sf6_prompt_replies.remember_special_strength_prompt_mode(sent_prompt.id, "both")
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
                    prefer_frame_rows=wants_comparison,
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
                    sf6_prompt_replies.remember_special_strength_prompt_mode(sent_prompt.id, "gif")
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
                prefer_frame_rows=wants_comparison,
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
                sf6_prompt_replies.remember_special_strength_prompt_mode(
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

        if fd_context_data or "coach" in content_lower:
            handled = await buenavista_extension.maybe_handle_frame_context(
                client=client,
                message=message,
                content_no_mentions=content_no_mentions,
                content_lower=content_lower,
                fd_context_payload=fd_context_payload,
                fd_context_data=fd_context_data,
                fd_context_mode=fd_context_mode,
                fd_context_rows=fd_context_rows,
                property_only_query=property_only_query,
                frame_reply_embeds=frame_reply_embeds,
                frame_reply_rows=frame_reply_rows,
                fallback_reply=fallback_reply,
                strip_discord_mentions=strip_discord_mentions,
                is_deleted_message_reference_error=is_deleted_message_reference_error,
                send_frame_embeds_with_views=send_frame_embeds_with_views,
            )
            if handled:
                return

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
                if "Target Combo Options" in replied_msg.content:
                    replied_context = replied_msg.content  # capture only TC prompt
                elif "Special Strength Options" in replied_msg.content:
                    replied_context = replied_msg.content
                    special_strength_reply_mode = sf6_prompt_replies.get_special_strength_prompt_mode(replied_msg.id)
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

    if await sf6_prompt_replies.handle_sf6_prompt_reply(
        {
            "FRAME_DATA": FRAME_DATA,
            "SCROLLS_MAINTAINER_USER_ID": SCROLLS_MAINTAINER_USER_ID,
            "SCROLLS_FIX_REQUEST_TEXT": SCROLLS_FIX_REQUEST_TEXT,
            "normalize_char_name": normalize_char_name,
            "resolve_character_key": resolve_character_key,
            "lookup_frame_data": lookup_frame_data,
            "lookup_hitbox_gif_link": lookup_hitbox_gif_link,
            "collect_hitbox_gif_links_from_text": collect_hitbox_gif_links_from_text,
            "send_frame_table_response": send_frame_table_response,
            "send_gif_links_response": send_gif_links_response,
            "format_frame_data": format_frame_data,
            "find_moves_in_text": find_moves_in_text,
        },
        message,
        replied_context,
        content_no_mentions,
        gif_query=gif_query,
        special_strength_reply_mode=special_strength_reply_mode,
    ):
        return



    should_respond = client.user.mentioned_in(message) or is_reply_to_bot or replied_context is not None
    if should_respond:
        handled = await buenavista_extension.maybe_handle_chat(
            client=client,
            message=message,
            content_no_mentions=content_no_mentions,
            content_lower=content_lower,
            replied_context=replied_context,
            fallback_reply=fallback_reply,
            frame_reply_embeds=frame_reply_embeds,
            frame_reply_rows=frame_reply_rows,
            strip_discord_mentions=strip_discord_mentions,
            is_deleted_message_reference_error=is_deleted_message_reference_error,
            send_frame_embeds_with_views=send_frame_embeds_with_views,
        )
        if handled:
            return


register_slash_commands(
    tree,
    {
        "frame_data": FRAME_DATA,
        "resolve_character_key": resolve_character_key,
        "find_moves_in_text": find_moves_in_text,
        "build_frame_embed": build_frame_embed,
        "frame_output_module": frame_output_module,
        "ggst_module": ggst_module,
        "tuco_module": tuco_module,
        "bbcf_module": bbcf_module,
        "cotw_module": cotw_module,
        "third_strike_module": third_strike_module,
        "mk1_module": mk1_module,
        "menu_system": menu_system,
    },
)


def main():
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found in .env")
    else:
        client.run(TOKEN)


if __name__ == "__main__":
    main()
