"""SF6 Target Combo and Special Strength disambiguation reply parsing."""

import re


SPECIAL_STRENGTH_PROMPT_MODE = {}
SPECIAL_STRENGTH_PROMPT_MODE_MAX = 300


def remember_special_strength_prompt_mode(message_id, mode):
    if not message_id or not mode:
        return
    SPECIAL_STRENGTH_PROMPT_MODE[int(message_id)] = str(mode)
    while len(SPECIAL_STRENGTH_PROMPT_MODE) > SPECIAL_STRENGTH_PROMPT_MODE_MAX:
        oldest_key = next(iter(SPECIAL_STRENGTH_PROMPT_MODE))
        SPECIAL_STRENGTH_PROMPT_MODE.pop(oldest_key, None)


def get_special_strength_prompt_mode(message_id):
    if not message_id:
        return None
    return SPECIAL_STRENGTH_PROMPT_MODE.get(int(message_id))


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


def compact_token(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def reply_option_number(reply_text):
    text = str(reply_text or "").strip().lower()
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


async def handle_target_combo_reply(deps, message, replied_context, content_no_mentions):
    if not replied_context or "Target Combo Options" not in replied_context:
        return False

    normalize_char_name = deps["normalize_char_name"]
    find_moves_in_text = deps["find_moves_in_text"]
    send_frame_table_response = deps["send_frame_table_response"]

    match = re.search(r"Target Combo Options \(([^)]+)\)", replied_context)
    char_hint = match.group(1).strip() if match else ""
    tc_query = (content_no_mentions or "").strip()
    selected_number = reply_option_number(tc_query)
    if selected_number is not None:
        options = []
        for raw_line in replied_context.splitlines():
            line = raw_line.strip()
            option_match = re.match(r"^(\d+)\s*[\.)]\s*(.+)$", line)
            if option_match:
                options.append((int(option_match.group(1)), option_match.group(2).strip()))
        number_matches = [option_text for option_number, option_text in options if option_number == selected_number]
        if len(number_matches) == 1:
            tc_query = number_matches[0]
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
        return True
    if tc_payload.get("mode") == "frame" and tc_rows and tc_data:
        await send_frame_table_response(message, tc_rows, tc_data)
        return True
    return False


async def handle_special_strength_reply(
    deps,
    message,
    replied_context,
    content_no_mentions,
    gif_query=False,
    special_strength_reply_mode=None,
):
    if not replied_context or "Special Strength Options" not in replied_context:
        return False

    FRAME_DATA = deps["FRAME_DATA"]
    send_missing_hitbox_gif_reply = deps["send_missing_hitbox_gif_reply"]
    normalize_char_name = deps["normalize_char_name"]
    resolve_character_key = deps["resolve_character_key"]
    lookup_frame_data = deps["lookup_frame_data"]
    lookup_hitbox_gif_link = deps["lookup_hitbox_gif_link"]
    collect_hitbox_gif_links_from_text = deps["collect_hitbox_gif_links_from_text"]
    send_frame_table_response = deps["send_frame_table_response"]
    send_gif_links_response = deps["send_gif_links_response"]
    format_frame_data = deps["format_frame_data"]
    find_moves_in_text = deps["find_moves_in_text"]
    reply_and_log_response = deps.get("reply_and_log_response")

    async def send_missing_scrolls_reply(text):
        if reply_and_log_response:
            return await reply_and_log_response(message, text, "missing_scrolls")
        return await message.reply(text)

    async def send_missing_gif_reply(rows, *, include_framedata_button=True):
        return await send_missing_hitbox_gif_reply(
            message,
            rows,
            include_framedata_button=include_framedata_button,
            reply_and_log_response=reply_and_log_response,
        )

    char_match = re.search(r"Special Strength Options \(([^)]+)\)", replied_context)
    char_hint = char_match.group(1).strip() if char_match else ""
    base_match = re.search(r"\n([^\n]+) variants:", replied_context)
    base_hint = base_match.group(1).strip().lower() if base_match else ""

    option_matches = []
    for raw_line in replied_context.splitlines():
        line = raw_line.strip()
        if not re.match(r"^(?:\d+\s*[\.)]|[\-•·])", line):
            continue
        option_line = re.sub(r"^(?:\d+\s*[\.)]\s*|[\s\-•·]+)", "", line).strip()
        if not option_line:
            continue
        option_name, option_cmd = parse_special_option_line(option_line)
        if not option_name or not option_cmd:
            continue
        option_matches.append((option_name, option_cmd))

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
        selected_number = reply_option_number(raw_special_reply_lower)
        if selected_number is not None and 1 <= selected_number <= len(option_matches):
            selected_option_name, selected_option_cmd = option_matches[selected_number - 1]

        exact_option_matches = []
        for option_name, option_cmd in option_matches:
            if selected_option_name or selected_option_cmd:
                break
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
                            await send_missing_gif_reply([direct_row])
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
                            await send_missing_gif_reply([direct_row], include_framedata_button=False)
                    else:
                        await send_frame_table_response(message, [direct_row], format_frame_data(direct_row))
                    return True
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
        remember_special_strength_prompt_mode(sent_prompt.id, special_request_mode)
        return True
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
            return True
        await send_missing_gif_reply(special_rows)
        return True
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
            return True
        await send_missing_gif_reply(special_rows, include_framedata_button=False)
        return True
    if special_payload.get("mode") == "frame" and special_rows and special_data:
        await send_frame_table_response(message, special_rows, special_data)
        return True
    await message.reply(replied_context)
    return True


async def handle_sf6_prompt_reply(deps, message, replied_context, content_no_mentions, gif_query=False, special_strength_reply_mode=None):
    if await handle_target_combo_reply(deps, message, replied_context, content_no_mentions):
        return True
    if await handle_special_strength_reply(
        deps,
        message,
        replied_context,
        content_no_mentions,
        gif_query=gif_query,
        special_strength_reply_mode=special_strength_reply_mode,
    ):
        return True
    return False
