"""Numbered frame-data and game-specific follow-up selection."""

import re

import discord

client = None
_fetch_referenced_message = None
strip_discord_mentions = lambda text: str(text or "")
third_strike_module = None
_requested_property_key = None
_format_requested_property_reply = None
_game_key_for_frame_module = None
_send_property_value_reply = None
sf6_prompt_replies = None
FRAME_DATA = {}
send_missing_hitbox_gif_reply = None
normalize_char_name = resolve_character_key = lookup_frame_data = None
lookup_hitbox_gif_link = collect_hitbox_gif_links_from_text = None
send_frame_table_response = send_gif_links_response = None
format_frame_data = find_moves_in_text = None
_reply_and_log_response = None
_message_prompt_text = lambda message: str(getattr(message, "content", "") or "")
has_explicit_gif_lookup_intent = lambda text: False
_record_frame_data_ids = lambda ids, **kwargs: None

sfv_module = ggst_module = ggacr_module = tuco_module = bbcf_module = None
cotw_module = third_strike_module = mk1_module = None


def configure(**deps):
    globals().update(deps)
    for candidate in globals().get("DISAMBIGUATION_GAME_CONFIGS", []):
        prefix = candidate.get("prefix")
        module_name = f"{prefix}_module"
        if prefix == "2xko":
            module_name = "tuco_module"
        elif prefix == "3s":
            module_name = "third_strike_module"
        module = globals().get(module_name)
        if module is not None:
            candidate["module"] = module
 
 
DISAMBIGUATION_GAME_CONFIGS = [
    {
        "label": "SFV",
        "prefix": "sfv",
        "module": sfv_module,
        "prompt_re": re.compile(r"Multiple SFV moves match (.+?)\. (?:Please specify one|Reply with the option number):"),
    },
    {
        "label": "GGST",
        "prefix": "ggst",
        "module": ggst_module,
        "prompt_re": re.compile(
            r"(?:Multiple GGST moves match (?P<char>[^.]+)\. (?:Please specify one|Reply with the option number):"
            r"|GGST Follow-up Options \((?P<followup>[^)]+)\))"
        ),
    },
    {
        "label": "GGACR",
        "prefix": "ggacr",
        "module": ggacr_module,
        "prompt_re": re.compile(r"Multiple GGACR moves match (.+?)\. (?:Please specify one|Reply with the option number):"),
    },
    {
        "label": "2XKO",
        "prefix": "2xko",
        "module": tuco_module,
        "prompt_re": re.compile(r"Multiple 2XKO moves match (.+?)\. (?:Please specify one|Reply with the option number):"),
    },
    {
        "label": "BBCF",
        "prefix": "bbcf",
        "module": bbcf_module,
        "prompt_re": re.compile(r"Multiple BBCF moves match (.+?)\. (?:Please specify one|Reply with the option number):"),
    },
    {
        "label": "COTW",
        "prefix": "cotw",
        "module": cotw_module,
        "prompt_re": re.compile(r"Multiple COTW moves match (.+?)\. (?:Please specify one|Reply with the option number):"),
    },
    {
        "label": "Third Strike",
        "prefix": "3s",
        "module": third_strike_module,
        "prompt_re": re.compile(r"Multiple Third Strike moves match (.+?)\. (?:Please specify one|Reply with the option number):"),
    },
    {
        "label": "MK1",
        "prefix": "mk1",
        "module": mk1_module,
        "prompt_re": re.compile(r"Multiple MK1 moves match (.+?)\. (?:Please specify one|Reply with the option number):"),
    },
]


# Numbered disambiguation reply parsing (GGST/SFV/etc follow-up prompts)
def _compact_disambiguation_text(text):
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def _parse_disambiguation_options(prompt_text):
    options = []
    for raw_line in str(prompt_text or "").splitlines():
        line = raw_line.strip()
        option_match = re.match(r"^(?:(\d+)\s*[\.)]\s*|[\-•·]\s*)(.+?):\s*`([^`]+)`(?:\s*\[([^\]]+)\])?", line)
        if option_match:
            options.append(
                {
                    "number": int(option_match.group(1)) if option_match.group(1) else len(options) + 1,
                    "name": option_match.group(2).strip(),
                    "cmd": option_match.group(3).strip(),
                    "version": (option_match.group(4) or "").strip(),
                }
            )
    return options


def _disambiguation_reply_number(reply_text):
    text = str(reply_text or "").strip().lower()
    if not text:
        return None

    ordinal_words = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "eighth": 8,
        "ninth": 9,
        "tenth": 10,
        "eleventh": 11,
        "twelfth": 12,
    }
    digit_match = re.fullmatch(r"(?:#|number\s+|option\s+|pick\s+|choice\s+)?(\d+)(?:st|nd|rd|th)?(?:\s+one)?", text)
    if digit_match:
        return int(digit_match.group(1))
    word_match = re.fullmatch(
        r"(?:the\s+)?(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth)(?:\s+one)?",
        text,
    )
    if word_match:
        return ordinal_words.get(word_match.group(1))
    return None


def _select_disambiguation_option(reply_text, options):
    reply_compact = _compact_disambiguation_text(reply_text)
    if not reply_compact or not options:
        return None

    selected_number = _disambiguation_reply_number(reply_text)
    if selected_number is not None:
        number_matches = [option for option in options if option.get("number") == selected_number]
        if len(number_matches) == 1:
            return number_matches[0]

    exact_matches = []
    contains_matches = []
    for option in options:
        terms = {
            _compact_disambiguation_text(option.get("name")),
            _compact_disambiguation_text(option.get("cmd")),
            _compact_disambiguation_text(option.get("version")),
        }
        terms.discard("")
        if reply_compact in terms:
            exact_matches.append(option)
        elif any(reply_compact in term for term in terms):
            contains_matches.append(option)

    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(contains_matches) == 1:
        return contains_matches[0]
    return None
def _select_ggst_followup_option(reply_text, options):
    selected = _select_disambiguation_option(reply_text, options)
    if selected:
        return selected

    reply_compact = _compact_disambiguation_text(reply_text)
    suffix_matches = []
    for option in options or []:
        command = str(option.get("cmd") or "").lower()
        command_parts = [
            part.strip()
            for part in re.split(r"(?:>|~|during|after)", command)
            if part.strip()
        ]
        suffix_compacts = {
            _compact_disambiguation_text(part)
            for part in command_parts[1:]
            if _compact_disambiguation_text(part)
        }
        if re.search(r"\b(?:during|after)\b", command) and command_parts:
            first_part_compact = _compact_disambiguation_text(command_parts[0])
            if first_part_compact:
                suffix_compacts.add(first_part_compact)
        if reply_compact in suffix_compacts:
            suffix_matches.append(option)
    return suffix_matches[0] if len(suffix_matches) == 1 else None


def _row_matches_disambiguation_option(row, option):
    row_name = _compact_disambiguation_text(row.get("moveName"))
    row_char_name = _compact_disambiguation_text(row.get("char_name"))
    row_cmd = _compact_disambiguation_text(row.get("numCmd"))
    row_version = _compact_disambiguation_text(row.get("version"))
    row_state_label = _compact_disambiguation_text(row.get("state_label"))
    option_name = _compact_disambiguation_text(option.get("name"))
    option_cmd = _compact_disambiguation_text(option.get("cmd"))
    option_version = _compact_disambiguation_text(option.get("version"))
    if option_name and row_name != option_name and option_name != f"{row_char_name}{row_name}":
        return False
    if option_cmd and row_cmd != option_cmd:
        return False
    if option_version and option_version not in {row_version, row_state_label}:
        return False
    return True


def _find_selected_disambiguation_row(rows, option):
    if not option:
        return None
    option_number = option.get("number")
    if isinstance(option_number, int) and 1 <= option_number <= len(rows or []):
        return list(rows or [])[option_number - 1]
    matches = [row for row in rows or [] if _row_matches_disambiguation_option(row, option)]
    return matches[0] if len(matches) == 1 else None




def _reply_output_mode_from_source_text(source_text):
    source_lower = strip_discord_mentions(source_text or "").lower()
    wants_hitbox = bool(re.search(r"\b(?:gif|gifs|hitbox|hitboxes|image|images|picture|pictures)\b", source_lower))
    wants_frames = bool(re.search(r"\b(?:framedata|frame\s*data|frames?|data|notes?)\b", source_lower)) or not wants_hitbox
    if wants_hitbox and wants_frames:
        return "both"
    if wants_hitbox:
        return "gif"
    return "frame"
async def _handle_cross_game_disambiguation_reply(message, content_no_mentions):
    if not message.reference:
        return False
    try:
        replied_msg = await _fetch_referenced_message(message)
    except (discord.NotFound, discord.Forbidden):
        return False
    if not replied_msg or replied_msg.author != client.user:
        return False

    replied_content = replied_msg.content or ""
    config = None
    char_hint = ""
    for candidate in DISAMBIGUATION_GAME_CONFIGS:
        prompt_match = candidate["prompt_re"].search(replied_content)
        if prompt_match:
            config = candidate
            char_hint = (
                prompt_match.groupdict().get("char")
                or prompt_match.groupdict().get("followup")
                or (prompt_match.group(1) if prompt_match.groups() else "")
                or ""
            ).strip()
            break
    if not config or config.get("module") is None:
        return False

    options = _parse_disambiguation_options(replied_content)
    if config["label"] == "GGST" and "GGST Follow-up Options" in replied_content:
        selected_option = _select_ggst_followup_option(content_no_mentions, options)
    else:
        selected_option = _select_disambiguation_option(content_no_mentions, options)
    if not selected_option:
        await message.reply(replied_content)
        return True

    source_text = ""
    if replied_msg.reference and replied_msg.reference.message_id:
        try:
            prompt_source = await _fetch_referenced_message(replied_msg)
            source_text = prompt_source.content if prompt_source else ""
        except (discord.NotFound, discord.Forbidden):
            source_text = ""

    output_mode = _reply_output_mode_from_source_text(source_text)
    module = config["module"]
    source_payload = module.find_moves_in_text(strip_discord_mentions(source_text).lower()) if source_text else {}
    selected_row = _find_selected_disambiguation_row(source_payload.get("rows", []) or [], selected_option)
    if selected_row:
        rows = [selected_row]
        payload = {"rows": rows}
    else:
        option_name = selected_option.get("cmd") or selected_option.get("name") or ""
        version_text = f" {selected_option.get('version')}" if selected_option.get("version") else ""
        reply_query = f"{config['prefix']} {char_hint} {option_name}{version_text}".strip()
        if config["label"] == "Third Strike" and third_strike_module.query_requests_genei_jin(source_text):
            reply_query = f"{reply_query} genei jin".strip()
        if output_mode == "gif":
            reply_query = f"{reply_query} hitbox".strip()
        elif output_mode == "both":
            reply_query = f"{reply_query} hitbox framedata".strip()
        else:
            reply_query = f"{reply_query} framedata".strip()
        payload = module.find_moves_in_text(reply_query.lower())
        rows = payload.get("rows", []) or []

    if payload.get("needs_disambiguation"):
        await message.reply(payload.get("data", f"Please specify which {config['label']} move you mean."))
    elif rows and output_mode == "gif":
        _record_frame_data_ids(await module.send_hitbox_response(message, rows))
    elif rows and output_mode == "both":
        _record_frame_data_ids(await module.send_frame_response(message, rows))
        _record_frame_data_ids(await module.send_hitbox_response(message, rows))
    elif rows and _format_requested_property_reply(rows, _requested_property_key(source_text), game=_game_key_for_frame_module(module)):
        await _send_property_value_reply(message, rows, _requested_property_key(source_text), game=_game_key_for_frame_module(module))
    elif rows:
        _record_frame_data_ids(await module.send_frame_response(message, rows))
    else:
        await message.reply(replied_content)
    return True
def _sf6_prompt_reply_deps():
    return {
        "FRAME_DATA": FRAME_DATA,
        "send_missing_hitbox_gif_reply": send_missing_hitbox_gif_reply,
        "normalize_char_name": normalize_char_name,
        "resolve_character_key": resolve_character_key,
        "lookup_frame_data": lookup_frame_data,
        "lookup_hitbox_gif_link": lookup_hitbox_gif_link,
        "collect_hitbox_gif_links_from_text": collect_hitbox_gif_links_from_text,
        "send_frame_table_response": send_frame_table_response,
        "send_gif_links_response": send_gif_links_response,
        "format_frame_data": format_frame_data,
        "find_moves_in_text": find_moves_in_text,
        "reply_and_log_response": _reply_and_log_response,
    }


async def _resolve_special_strength_reply_mode(replied_msg):
    mode = sf6_prompt_replies.get_special_strength_prompt_mode(replied_msg.id)
    if mode:
        return mode
    if not replied_msg.reference or not replied_msg.reference.message_id:
        return None
    try:
        prompt_source = await _fetch_referenced_message(replied_msg)
    except (discord.NotFound, discord.Forbidden):
        return None
    if not prompt_source:
        return None
    prompt_source_text = strip_discord_mentions(prompt_source.content or "").lower()
    if has_explicit_gif_lookup_intent(prompt_source_text):
        return "gif"
    return None


async def _handle_sf6_prompt_disambiguation_reply(message, content_no_mentions, *, gif_query=False):
    if not message.reference:
        return False
    try:
        replied_msg = await _fetch_referenced_message(message)
    except (discord.NotFound, discord.Forbidden):
        return False
    if not replied_msg or replied_msg.author != client.user:
        return False

    replied_content = _message_prompt_text(replied_msg)
    if not (
        "Special Strength Options" in replied_content
        or "Target Combo Options" in replied_content
    ):
        return False

    special_strength_reply_mode = None
    if "Special Strength Options" in replied_content:
        special_strength_reply_mode = await _resolve_special_strength_reply_mode(replied_msg)

    return await sf6_prompt_replies.handle_sf6_prompt_reply(
        _sf6_prompt_reply_deps(),
        message,
        replied_content,
        content_no_mentions,
        gif_query=gif_query,
        special_strength_reply_mode=special_strength_reply_mode,
    )


