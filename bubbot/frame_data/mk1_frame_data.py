import difflib
import datetime
import json
import os
import re

import discord

from bubbot.data.mk1_aliases import MK1_CHARACTER_ALIASES, MK1_LOOKUP_WORDS, MK1_MOVE_ALIASES
from bubbot.utils.character_lookup import find_alias_positions_in_text, resolve_alias_key
from bubbot.utils.comparison_utils import find_comparison_rows, is_comparison_query
from bubbot.utils.discord_formatting import (
    add_embed_field as shared_add_embed_field,
    add_long_embed_field as shared_add_long_embed_field,
    clean_value as shared_clean_value,
    truncate_value as shared_truncate_value,
)
from bubbot.utils.row_utils import unique_rows
from bubbot.utils.text_utils import compact_key, correct_alias_typos, query_suffix_candidates, strip_noise_words


def _response_log_file_path():
    path_text = str(os.getenv("BUB_RESPONSE_LOG_FILE", "bub_response_log.jsonl") or "").strip()
    if not path_text:
        path_text = "bub_response_log.jsonl"
    if os.path.isabs(path_text):
        return path_text
    return os.path.join(os.getcwd(), path_text)


def _log_missing_scrolls_response(message, response_text):
    now = datetime.datetime.now(datetime.timezone.utc)
    guild = getattr(message, "guild", None)
    channel = getattr(message, "channel", None)
    author = getattr(message, "author", None)
    payload = {
        "timestamp_utc": now.isoformat(),
        "date_utc": now.date().isoformat(),
        "time_utc": now.time().replace(microsecond=0).isoformat(),
        "reason": "missing_scrolls",
        "server_id": getattr(guild, "id", None),
        "server_name": getattr(guild, "name", None),
        "channel_id": getattr(channel, "id", None),
        "channel_name": getattr(channel, "name", None),
        "user_id": getattr(author, "id", None),
        "user_name": getattr(author, "display_name", None) or getattr(author, "name", None),
        "prompt": str(getattr(message, "content", "") or ""),
        "response": str(response_text or ""),
    }
    try:
        with open(_response_log_file_path(), "a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception as error:
        print(f"[response-log] write error: {error}", flush=True)


MK1_MOVE_LIST_FILE = os.path.join("mk1", "move_list.json")
MK1_KAMEO_MOVE_LIST_FILE = os.path.join("mk1", "move_list_kameo.json")
MK1_COMBOS_FILE = os.path.join("mk1", "combos.json")
MK1_FRAME_DATA = {}
MK1_COMBO_DATA = {}


def normalize_key(value):
    return compact_key(value)


def normalize_move_token(value):
    text = str(value or "").lower().strip()
    replacements = {
        "forward": "f",
        "backward": "b",
        "back": "b",
        "down": "d",
        "up": "u",
        "enhanced": "ex",
        "meter burn": "ex",
        "meterburn": "ex",
        "fatal blow": "ss ex",
        "fb": "ss ex",
        "kameo": "kameo",
    }
    for old, new in replacements.items():
        text = re.sub(rf"\b{re.escape(old)}\b", new, text)
    text = text.replace("+", "")
    text = text.replace(",", "")
    text = text.replace("/", "")
    text = text.replace("-", "")
    text = text.replace(" ", "")
    return re.sub(r"[^a-z0-9]", "", text)


def _extract_export_rows(filename):
    if not os.path.exists(filename):
        print(f"[mk1] data file not found: {filename}", flush=True)
        return []
    with open(filename, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    for item in payload:
        if isinstance(item, dict) and isinstance(item.get("data"), list):
            return item["data"]
    return []


def _mk1_row(raw_row, source="character"):
    name_field = "kameo_name" if source == "kameo" else "char_name"
    display_name = str(raw_row.get(name_field) or "").strip()
    if not display_name:
        return None
    char_key = normalize_key(display_name)
    if source == "kameo":
        char_key = f"kameo_{char_key}"
    row = {
        "char_key": char_key,
        "char_name": display_name,
        "game_source": source,
        "moveName": str(raw_row.get("move_name") or "").strip(),
        "numCmd": str(raw_row.get("command") or "").strip(),
        "moveType": str(raw_row.get("subcategory") or raw_row.get("category") or "").strip(),
        "category": str(raw_row.get("category") or "").strip(),
        "parent_command": str(raw_row.get("parent_command") or "").strip(),
        "startup": str(raw_row.get("startup") or "").strip(),
        "active": str(raw_row.get("active") or "").strip(),
        "recovery": str(raw_row.get("recovery") or "").strip(),
        "onHit": str(raw_row.get("hit_advantage") or "").strip(),
        "onBlock": str(raw_row.get("block_advantage") or "").strip(),
        "flawlessBlock": str(raw_row.get("fblock_advantage") or "").strip(),
        "dmg": str(raw_row.get("hit_damage") or "").strip(),
        "blockDamage": str(raw_row.get("block_damage") or "").strip(),
        "guardLevel": str(raw_row.get("block_type") or "").strip(),
        "xx": str(raw_row.get("cancel") or "").strip(),
        "properties": str(raw_row.get("properties") or "").strip(),
        "extraInfo": str(raw_row.get("notes") or "").strip(),
    }
    return row if row["moveName"] or row["numCmd"] else None


def _register_character_aliases(char_key, display_name, source="character"):
    normalized_name = str(display_name or "").lower().strip()
    compact_name = normalize_key(display_name)
    for alias in {normalized_name, compact_name, normalized_name.replace("-", " ")}:
        if alias:
            MK1_CHARACTER_ALIASES.setdefault(alias, char_key)
    if source == "kameo":
        for alias in {f"kameo {normalized_name}", f"{normalized_name} kameo", f"assist {normalized_name}", f"{normalized_name} assist"}:
            MK1_CHARACTER_ALIASES.setdefault(alias, char_key)


def _mk1_combo_row(raw_row):
    char_name = str(raw_row.get("char_name") or "").strip()
    if not char_name:
        return None
    return {
        "char_key": normalize_key(char_name),
        "char_name": char_name,
        "kameo_name": str(raw_row.get("kameo_name") or "").strip(),
        "category": str(raw_row.get("category") or "").strip(),
        "subcategory": str(raw_row.get("subcategory") or "").strip(),
        "combo": str(raw_row.get("combo") or "").strip(),
        "damage": str(raw_row.get("damage") or "").strip(),
        "difficulty": str(raw_row.get("difficulty") or "").strip(),
        "meter": str(raw_row.get("meter") or "").strip(),
        "kameo_meter": str(raw_row.get("kameo_meter") or "").strip(),
        "tags": str(raw_row.get("tags") or "").strip(),
        "url": str(raw_row.get("url") or "").strip(),
        "notes": str(raw_row.get("notes") or "").strip(),
    }


def load_frame_data(move_file=None, kameo_file=None, combo_file=None):
    global MK1_FRAME_DATA, MK1_COMBO_DATA
    MK1_FRAME_DATA = {}
    MK1_COMBO_DATA = {}
    move_file = move_file or MK1_MOVE_LIST_FILE
    kameo_file = kameo_file or MK1_KAMEO_MOVE_LIST_FILE
    combo_file = combo_file or MK1_COMBOS_FILE

    for raw_row in _extract_export_rows(move_file):
        row = _mk1_row(raw_row, source="character")
        if not row:
            continue
        MK1_FRAME_DATA.setdefault(row["char_key"], []).append(row)
        _register_character_aliases(row["char_key"], row["char_name"], source="character")

    for raw_row in _extract_export_rows(kameo_file):
        row = _mk1_row(raw_row, source="kameo")
        if not row:
            continue
        MK1_FRAME_DATA.setdefault(row["char_key"], []).append(row)
        _register_character_aliases(row["char_key"], row["char_name"], source="kameo")

    for raw_row in _extract_export_rows(combo_file):
        row = _mk1_combo_row(raw_row)
        if not row:
            continue
        MK1_COMBO_DATA.setdefault(row["char_key"], []).append(row)
        _register_character_aliases(row["char_key"], row["char_name"], source="character")

    print(
        f"[mk1] Total fighters loaded: {sum(1 for key in MK1_FRAME_DATA if not key.startswith('kameo_'))}; "
        f"kameos loaded: {sum(1 for key in MK1_FRAME_DATA if key.startswith('kameo_'))}; "
        f"combo characters loaded: {len(MK1_COMBO_DATA)}",
        flush=True,
    )
    return bool(MK1_FRAME_DATA)


def resolve_character_key(text):
    lowered = str(text or "").lower()
    if re.search(r"\b(?:kameo|assist)\b", lowered):
        for key in MK1_FRAME_DATA.keys():
            if not str(key).startswith("kameo_"):
                continue
            display = display_char_name(key).lower()
            if display and re.search(rf"\b{re.escape(display)}\b", lowered):
                return key
    return resolve_alias_key(text, MK1_CHARACTER_ALIASES, MK1_FRAME_DATA.keys(), normalize_fn=normalize_key)


def display_char_name(char_key):
    rows = MK1_FRAME_DATA.get(char_key) or []
    if rows:
        label = str(rows[0].get("char_name") or char_key).strip()
        return f"Kameo {label}" if str(char_key).startswith("kameo_") else label
    return str(char_key or "Unknown").replace("_", " ").title()


def find_characters_in_text(text):
    lowered = str(text or "").lower()
    matches = find_alias_positions_in_text(lowered, MK1_CHARACTER_ALIASES, MK1_FRAME_DATA.keys())
    if re.search(r"\b(?:kameo|assist)\b", lowered):
        kameo_matches = [match for match in matches if str(match[0]).startswith("kameo_")]
        if kameo_matches:
            return kameo_matches
    return [match for match in matches if match[0] != "mk1"]


def query_has_mk1_notation(text):
    lowered = str(text or "").lower()
    return bool(
        re.search(r"\b(?:[bfdu]\s*\+?\s*)?[1-4](?:\s*,\s*(?:[bfdu]\s*\+?\s*)?[1-4])*\b|\b(?:db|df|bf|bb|ff|du|dd|uf|ub)\s*\+?\s*[1-4]\b|\bkameo\b", lowered)
        or re.search(r"\b(?:fatal\s+blow|fb)\b", lowered)
    )


def normalize_move_query(query):
    text = str(query or "").lower().strip()
    text = re.sub(r"\b(?:mk1|mortal\s+kombat\s+1|mortal\s+kombat\s+one|mortal\s+kombat)\b", " ", text)
    text = re.sub(r"\b(?:framedata|frame\s*data|frames?|data|gif|gifs|hitbox(?:es)?|images?|notes?|start\s*up|startup|active|recovery|total|on\s+hit|on\s+block|flawless\s+block|block\s+damage|rev\s+damage|guard\s+damage|damage|dmg|guard|attack\s+level|atk\s*lvl|atk\s*level|cancel(?:l?able)?|gatling|invuln(?:erability)?|invul|attribute|range|length|hit\s*-?\s*confirm|hitconfirm|confirm\s+window|confirm\s+timing|confirmable|super\s*gain|super\s*meter\s*gain|meter\s*gain|super\s*build|sa\s*gain|drive\s+gain|drive\s+chip|drive\s+dmg|drive\s+damage|hitstun|blockstun|stun|risc\s*gain|risc|proration|prorate|knockdown\s+adv(?:antage)?|kda|counter\s*hit\s+adv(?:antage)?|ch\s*adv)\b", " ", text)
    text = re.sub(r"\b(?:combo|combos|bnb|bnbs|route|routes)\b", " ", text)
    text = strip_noise_words(text)
    normalized_words = re.sub(r"[^a-z0-9+,-]+", " ", text).strip()
    compact = normalize_move_token(normalized_words)
    if normalized_words in MK1_MOVE_ALIASES:
        return MK1_MOVE_ALIASES[normalized_words]
    if compact in MK1_MOVE_ALIASES:
        return MK1_MOVE_ALIASES[compact]
    corrected_words = correct_alias_typos(normalized_words, MK1_MOVE_ALIASES)
    if corrected_words != normalized_words:
        corrected_compact = normalize_move_token(corrected_words)
        if corrected_words in MK1_MOVE_ALIASES:
            return MK1_MOVE_ALIASES[corrected_words]
        if corrected_compact in MK1_MOVE_ALIASES:
            return MK1_MOVE_ALIASES[corrected_compact]
        return corrected_words
    return normalized_words


def row_match_keys(row):
    keys = set()
    for value in (row.get("numCmd"), row.get("moveName")):
        if str(value or "").strip():
            keys.add(normalize_move_token(value))
    return {key for key in keys if key}


def find_matching_rows(char_key, move_text):
    raw_move_text = str(move_text or "").lower()
    query_requests_enhanced = bool(re.search(r"\b(?:ex|enhanced|meter\s*burn|meterburn)\b", raw_move_text))
    query = normalize_move_query(move_text)
    query_key = normalize_move_token(query)
    if not query_key:
        return []
    rows = MK1_FRAME_DATA.get(char_key, []) or []

    def row_is_enhanced(row):
        return bool(
            re.search(r"\b(?:enhanced|ex)\b", str(row.get("moveName") or "").lower())
            or "ex" in normalize_move_token(row.get("numCmd"))
        )

    def enhanced_rows_for_base(base_rows, base_query_key):
        base_command_keys = {normalize_move_token(row.get("numCmd")) for row in base_rows if row.get("numCmd")}
        base_name_keys = {normalize_move_token(row.get("moveName")) for row in base_rows if row.get("moveName")}
        base_command_keys.discard("")
        base_name_keys.discard("")
        enhanced_matches = []
        for row in rows:
            if not row_is_enhanced(row):
                continue
            row_cmd_key = normalize_move_token(row.get("numCmd"))
            row_name_key = normalize_move_token(row.get("moveName"))
            parent_keys = {
                normalize_move_token(part)
                for part in re.split(r"[,/]+", str(row.get("parent_command") or ""))
                if str(part or "").strip()
            }
            parent_keys.discard("")
            if parent_keys & base_command_keys:
                enhanced_matches.append(row)
                continue
            if base_query_key and base_query_key in {row_cmd_key, row_name_key}:
                enhanced_matches.append(row)
                continue
            if base_query_key and row_name_key.endswith(base_query_key):
                enhanced_matches.append(row)
                continue
            if base_command_keys and any(row_cmd_key.startswith(f"{cmd}ex") for cmd in base_command_keys):
                enhanced_matches.append(row)
                continue
            if base_name_keys and any(row_name_key.endswith(name_key) for name_key in base_name_keys):
                enhanced_matches.append(row)
        return unique_rows(enhanced_matches)

    def prefer_enhanced(matches, base_query_key):
        if not query_requests_enhanced or not matches:
            return unique_rows(matches)
        enhanced_matches = [row for row in matches if row_is_enhanced(row)]
        if enhanced_matches:
            return unique_rows(enhanced_matches)
        derived = enhanced_rows_for_base(matches, base_query_key)
        return derived or unique_rows(matches)

    base_query = re.sub(r"\b(?:ex|enhanced|meter\s*burn|meterburn)\b", " ", query, flags=re.IGNORECASE)
    base_query = re.sub(r"\s+", " ", base_query).strip()
    base_query_key = normalize_move_token(base_query)

    exact = [row for row in rows if query_key in row_match_keys(row)]
    if exact:
        return prefer_enhanced(exact, base_query_key or query_key)

    if query_requests_enhanced and base_query_key and base_query_key != query_key:
        base_exact = [row for row in rows if base_query_key in row_match_keys(row)]
        if base_exact:
            return prefer_enhanced(base_exact, base_query_key)

    name_matches = []
    normalized_query_words = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
    normalized_base_query_words = re.sub(r"[^a-z0-9]+", " ", base_query.lower()).strip()
    for row in rows:
        move_name = re.sub(r"[^a-z0-9]+", " ", str(row.get("moveName", "")).lower()).strip()
        num_cmd = re.sub(r"[^a-z0-9]+", " ", str(row.get("numCmd", "")).lower()).strip()
        if normalized_query_words and (normalized_query_words in move_name or normalized_query_words in num_cmd):
            name_matches.append(row)
    if name_matches:
        return prefer_enhanced(name_matches, base_query_key or query_key)

    if query_requests_enhanced and normalized_base_query_words and normalized_base_query_words != normalized_query_words:
        base_name_matches = []
        for row in rows:
            move_name = re.sub(r"[^a-z0-9]+", " ", str(row.get("moveName", "")).lower()).strip()
            num_cmd = re.sub(r"[^a-z0-9]+", " ", str(row.get("numCmd", "")).lower()).strip()
            if normalized_base_query_words in move_name or normalized_base_query_words in num_cmd:
                base_name_matches.append(row)
        if base_name_matches:
            return prefer_enhanced(base_name_matches, base_query_key)

    candidates = []
    for row in rows:
        for value in (row.get("moveName"), row.get("numCmd")):
            key = normalize_move_token(value)
            if key:
                candidates.append((key, row))
    close_keys = difflib.get_close_matches(query_key, [key for key, _row in candidates], n=4, cutoff=0.84)
    fuzzy_matches = [row for key, row in candidates if key in close_keys]
    if fuzzy_matches:
        return prefer_enhanced(fuzzy_matches, base_query_key or query_key)
    return []


def build_disambiguation_prompt(char_key, rows):
    lines = [f"Multiple MK1 moves match {display_char_name(char_key)}. Reply with the option number:"]
    for index, row in enumerate(rows[:12], start=1):
        move_name = clean_value(row.get("moveName"), "Unknown")
        num_cmd = clean_value(row.get("numCmd"), "?")
        lines.append(f"{index}. {move_name}: `{num_cmd}`")
    return "\n".join(lines)


def _combo_query_terms(text):
    lowered = str(text or "").lower()
    return {
        "corner": bool(re.search(r"\bcorner\b", lowered)),
        "midscreen": bool(re.search(r"\bmid\s*screen|\bmidscreen\b", lowered)),
        "easy": bool(re.search(r"\beasy\b", lowered)),
        "medium": bool(re.search(r"\bmedium\b", lowered)),
        "hard": bool(re.search(r"\bhard\b", lowered)),
        "meterless": bool(re.search(r"\bmeterless|no\s+meter\b", lowered)),
    }


def find_combo_rows_in_text(text, limit=8):
    lowered = str(text or "").lower()
    if not re.search(r"\b(?:combo|combos|bnb|bnbs|route|routes)\b", lowered):
        return []
    char_matches = find_alias_positions_in_text(lowered, MK1_CHARACTER_ALIASES, MK1_COMBO_DATA.keys())
    char_key = None
    for candidate, _start, _end, _alias in char_matches:
        if not str(candidate).startswith("kameo_"):
            char_key = candidate
            break
    if not char_key:
        return []
    rows = list(MK1_COMBO_DATA.get(char_key, []) or [])
    terms = _combo_query_terms(lowered)
    kameo_filter = None
    for row in rows:
        kameo_name = str(row.get("kameo_name") or "").strip().lower()
        if kameo_name and re.search(rf"\b{re.escape(kameo_name)}\b", lowered):
            kameo_filter = kameo_name
            break
    if kameo_filter:
        rows = [row for row in rows if str(row.get("kameo_name") or "").strip().lower() == kameo_filter]
    if terms["corner"]:
        rows = [row for row in rows if "corner" in str(row.get("category") or "").lower()]
    if terms["midscreen"]:
        rows = [row for row in rows if "mid" in str(row.get("category") or "").lower()]
    for difficulty in ("easy", "medium", "hard"):
        if terms[difficulty]:
            rows = [row for row in rows if str(row.get("difficulty") or "").lower() == difficulty]
            break
    if terms["meterless"]:
        rows = [row for row in rows if str(row.get("meter") or "").strip() in {"", "0"}]
    return rows[:limit]


def find_moves_in_text(text):
    lowered = str(text or "").lower()
    combo_query = bool(re.search(r"\b(?:combo|combos|bnb|bnbs|route|routes)\b", lowered))
    gif_query = bool(re.search(r"\b(?:gif|gifs|hitbox|hitboxes|image|images)\b", lowered))
    frame_query = bool(re.search(r"\b(?:framedata|frame\s*data|frames?|data)\b", lowered))
    notes_query = bool(re.search(r"\bnotes?\b", lowered))
    game_query = bool(re.search(r"\b(?:mk1|mortal\s+kombat\s+1|mortal\s+kombat\s+one|mortal\s+kombat)\b", lowered))
    if combo_query:
        combo_rows = find_combo_rows_in_text(lowered)
        return {
            "mode": "combo" if combo_rows else "none",
            "rows": [],
            "combo_rows": combo_rows,
            "data": format_combo_rows(combo_rows),
            "combo_query": True,
            "frame_query": frame_query,
            "gif_query": gif_query,
            "notes_query": notes_query,
            "game_query": game_query,
            "char_found": bool(combo_rows),
            "explicit_move_attempt": bool(game_query),
        }
    char_matches = find_characters_in_text(lowered)
    rows = []
    matched_char_key = char_matches[0][0] if char_matches else None
    comparison_result = find_comparison_rows(
        lowered,
        char_matches,
        find_characters_in_text=find_characters_in_text,
        find_rows_for_char=find_matching_rows,
    )
    if comparison_result and comparison_result.get("needs_disambiguation"):
        char_key = comparison_result["char_key"]
        matches = comparison_result["rows"]
        return {
            "mode": "options",
            "rows": matches,
            "data": build_disambiguation_prompt(char_key, matches),
            "gif_query": gif_query,
            "frame_query": frame_query,
            "notes_query": notes_query,
            "game_query": game_query,
            "needs_disambiguation": True,
            "char_found": True,
            "char_key": char_key,
            "wants_comparison": True,
        }
    if comparison_result:
        rows = comparison_result["rows"]
        return {
            "mode": "gif" if gif_query else "frame",
            "rows": rows,
            "data": "\n\n".join(format_frame_data(row) for row in rows),
            "gif_query": gif_query,
            "frame_query": frame_query,
            "notes_query": notes_query,
            "game_query": game_query,
            "char_found": True,
            "char_key": comparison_result.get("char_key") or matched_char_key,
            "wants_comparison": True,
            "explicit_move_attempt": True,
            "missing_scrolls_query": False,
        }
    for char_key, start, end, _alias in char_matches:
        move_text = (lowered[:start] + " " + lowered[end:]).strip() if start >= 0 and end >= 0 else lowered
        matches = []
        for move_candidate in query_suffix_candidates(move_text):
            normalized_candidate = normalize_move_query(move_candidate)
            if not normalized_candidate:
                continue
            matches = find_matching_rows(char_key, normalized_candidate)
            if matches:
                break
        if len(matches) > 1:
            return {
                "mode": "options",
                "rows": matches,
                "data": build_disambiguation_prompt(char_key, matches),
                "gif_query": gif_query,
                "frame_query": frame_query,
                "notes_query": notes_query,
                "game_query": game_query,
                "needs_disambiguation": True,
                "char_found": True,
                "char_key": char_key,
            }
        if matches:
            rows.append(matches[0])
            break
    return {
        "mode": "gif" if gif_query else "frame" if rows else "none",
        "rows": rows,
        "data": "\n\n".join(format_frame_data(row) for row in rows),
        "gif_query": gif_query,
        "frame_query": frame_query,
        "notes_query": notes_query,
        "game_query": game_query,
        "char_found": bool(char_matches),
        "char_key": matched_char_key,
        "wants_comparison": is_comparison_query(lowered, char_matches),
        "explicit_move_attempt": bool(char_matches and (frame_query or gif_query or notes_query or game_query or query_has_mk1_notation(lowered))),
        "missing_scrolls_query": bool(char_matches and not rows and (frame_query or gif_query or notes_query or game_query)),
    }


def clean_value(value, default=""):
    return shared_clean_value(value, default)


def truncate_value(value, limit):
    return shared_truncate_value(value, limit)


def add_embed_field(embed, name, value, inline=True):
    shared_add_embed_field(embed, name, clean_value(value), inline=inline)


def add_long_embed_field(embed, name, value, inline=False):
    shared_add_long_embed_field(embed, name, clean_value(value), inline=inline)


def get_notes_text(row):
    notes = clean_value(row.get("extraInfo"))
    properties = clean_value(row.get("properties"))
    parts = [part for part in (properties, notes) if part]
    return "\n".join(parts)


def format_frame_data(row, include_notes=False):
    text = (
        f"Move: {clean_value(row.get('moveName'))} ({clean_value(row.get('numCmd'))})\n"
        f"Startup: {clean_value(row.get('startup'), '-')}f | Active: {clean_value(row.get('active'), '-')}f | Recovery: {clean_value(row.get('recovery'), '-')}f\n"
        f"On Hit: {clean_value(row.get('onHit'), '-')} | On Block: {clean_value(row.get('onBlock'), '-')} | Flawless Block: {clean_value(row.get('flawlessBlock'), '-')}\n"
        f"Damage: {clean_value(row.get('dmg'), '-')} | Guard: {clean_value(row.get('guardLevel'), '-')} | Cancel: {clean_value(row.get('xx'), '-')}"
    )
    notes = get_notes_text(row)
    if include_notes and notes:
        text += f"\nNotes: {notes}"
    return text


def build_frame_embed(row, show_notes=False):
    char_name = display_char_name(row.get("char_key"))
    move_name = clean_value(row.get("moveName"), "Unknown")
    num_cmd = clean_value(row.get("numCmd"), "?")
    embed = discord.Embed(
        title=truncate_value(f"MK1 - {char_name}", 256),
        description=truncate_value(f"{move_name} ({num_cmd})", 4096),
        colour=0x7E1616,
    )
    add_embed_field(embed, "Startup", row.get("startup"), inline=True)
    add_embed_field(embed, "Active", row.get("active"), inline=True)
    add_embed_field(embed, "Recovery", row.get("recovery"), inline=True)
    add_embed_field(embed, "On Hit", row.get("onHit"), inline=True)
    add_embed_field(embed, "On Block", row.get("onBlock"), inline=True)
    add_embed_field(embed, "Flawless Block", row.get("flawlessBlock"), inline=True)
    add_embed_field(embed, "Damage", row.get("dmg"), inline=True)
    add_embed_field(embed, "Block Damage", row.get("blockDamage"), inline=True)
    add_embed_field(embed, "Guard", row.get("guardLevel"), inline=True)
    add_embed_field(embed, "Cancel", row.get("xx"), inline=True)
    if show_notes:
        add_long_embed_field(embed, "Notes", get_notes_text(row), inline=False)
    category = clean_value(row.get("category"))
    move_type = clean_value(row.get("moveType"))
    if category or move_type:
        embed.set_footer(text=truncate_value(" / ".join(part for part in (category, move_type) if part), 2048))
    return embed


def format_combo_rows(rows):
    if not rows:
        return ""
    blocks = []
    for row in rows[:8]:
        heading = f"{row.get('category') or 'Combo'}"
        if row.get("subcategory"):
            heading += f" - {row.get('subcategory')}"
        if row.get("kameo_name"):
            heading += f" with {row.get('kameo_name')}"
        details = [
            f"Combo: {row.get('combo')}",
            f"Damage: {clean_value(row.get('damage'), '-')} | Difficulty: {clean_value(row.get('difficulty'), '-')} | Meter: {clean_value(row.get('meter'), '0')} | Kameo: {clean_value(row.get('kameo_meter'), '0')}",
        ]
        if row.get("tags"):
            details.append(f"Tags: {row.get('tags')}")
        if row.get("notes"):
            details.append(f"Notes: {row.get('notes')}")
        if row.get("url"):
            details.append(f"URL: {row.get('url')}")
        blocks.append(f"**{heading}**\n" + "\n".join(details))
    return "\n\n".join(blocks)


def build_combo_embed(char_key, rows):
    embed = discord.Embed(
        title=truncate_value(f"MK1 Combos - {display_char_name(char_key)}", 256),
        colour=0x7E1616,
    )
    if not rows:
        embed.description = "No combos found for that filter."
        return embed
    for row in rows[:8]:
        title = f"{row.get('category') or 'Combo'}"
        if row.get("subcategory"):
            title += f" - {row.get('subcategory')}"
        if row.get("kameo_name"):
            title += f" with {row.get('kameo_name')}"
        value = (
            f"`{row.get('combo')}`\n"
            f"Damage: **{clean_value(row.get('damage'), '-')}** | Difficulty: **{clean_value(row.get('difficulty'), '-')}** | "
            f"Meter: **{clean_value(row.get('meter'), '0')}** | Kameo: **{clean_value(row.get('kameo_meter'), '0')}**"
        )
        extras = []
        if row.get("tags"):
            extras.append(f"Tags: {row.get('tags')}")
        if row.get("notes"):
            extras.append(f"Notes: {row.get('notes')}")
        if row.get("url"):
            extras.append(str(row.get("url")))
        if extras:
            value += "\n" + "\n".join(extras)
        add_long_embed_field(embed, truncate_value(title, 256), value, inline=False)
    return embed


class MK1NotesButton(discord.ui.Button):
    def __init__(self, row):
        self.frame_row = row
        super().__init__(label="Show Notes", style=discord.ButtonStyle.primary, disabled=not get_notes_text(row), row=0)

    async def callback(self, interaction: discord.Interaction):
        if not hasattr(self.view, "build_embed"):
            await interaction.response.defer()
            return
        self.view.show_notes = not self.view.show_notes
        self.label = "Hide Notes" if self.view.show_notes else "Show Notes"
        self.style = discord.ButtonStyle.danger if self.view.show_notes else discord.ButtonStyle.primary
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)


class ReturnToMenuButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Return to Menu", style=discord.ButtonStyle.primary, custom_id="mk1_frame_return_menu", row=0)

    async def callback(self, interaction: discord.Interaction):
        from bubbot.features import menu_system
        await interaction.response.send_message(embed=menu_system._main_menu_embed(), view=menu_system.MainMenuView(interaction.user.id))


class MK1FrameDataView(discord.ui.View):
    def __init__(self, row, include_menu_button=True, owner_id=None, char_key=None):
        super().__init__(timeout=3600)
        self.row = row
        self.show_notes = False
        self.notes_button = MK1NotesButton(row)
        self.add_item(self.notes_button)
        from bubbot.features import menu_system
        menu_system.attach_compare_button(self, "mk1", row, owner_id=owner_id, char_key=char_key)
        if include_menu_button:
            self.add_item(ReturnToMenuButton())

    def build_embed(self):
        return build_frame_embed(self.row, show_notes=self.show_notes)


async def send_frame_response(message, rows):
    if not rows:
        return []
    sent_ids = []
    for row in rows:
        view = MK1FrameDataView(row, owner_id=getattr(message.author, "id", None))
        sent = await message.channel.send(embed=view.build_embed(), view=view)
        sent_ids.append(sent.id)
    return sent_ids


async def send_hitbox_response(message, rows):
    if not rows:
        return []
    response_text = "I have MK1 frame data for that move, but no MK1 hitbox image links are in the scrolls yet."
    _log_missing_scrolls_response(message, response_text)
    sent = await message.reply(response_text)
    return [sent.id]


async def send_combo_response(message, rows):
    if not rows:
        return []
    char_key = rows[0].get("char_key")
    sent = await message.channel.send(embed=build_combo_embed(char_key, rows))
    return [sent.id]
