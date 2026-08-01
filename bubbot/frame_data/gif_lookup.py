"""Local SF6 hitbox GIF index and row/query GIF matching."""

import os
import re

from bubbot.utils.character_lookup import find_aliases_in_text
from bubbot.utils.text_utils import compact_key, remove_first_token_sequence as remove_first_token_sequence_shared
from bubbot.frame_data import gif_query_flow

CHARACTER_ALIASES = {}
FRAME_DATA = {}
HITBOX_GIF_DATA = {}
LOCAL_HITBOX_GIF_ROOT = ""
LOCAL_HITBOX_GIF_EXTENSIONS = set()
normalize_char_name = None
resolve_character_key = None
normalize_num_cmd_token = None
extract_button_suffix = None
iter_unique_frame_rows = None
strip_discord_mentions = None
find_moves_in_text = None
lookup_frame_data = None
get_sf6_move_image_url = None
lookup_hitbox_gif_links_from_query = gif_query_flow.lookup_hitbox_gif_links_from_query
collect_hitbox_gif_links_from_text = gif_query_flow.collect_hitbox_gif_links_from_text
get_frame_row_gif_links = gif_query_flow.get_frame_row_gif_links


# Runtime dependency injection


def configure(**deps):
    globals().update(deps)
    gif_query_flow.configure(
        **{
            name: value
            for name, value in globals().items()
            if not name.startswith("__") and name not in {"configure", "gif_query_flow"}
        }
    )


def compact_move_token(value):
    return compact_key(value)


def normalize_num_cmd_token(value):
    normalized = re.sub(r"\([^)]*\)", "", str(value or "").lower())
    normalized = re.sub(r"\s+", "", normalized)
    return re.sub(r"[^a-z0-9>]", "", normalized)


def extract_button_suffix(num_cmd_token):
    token = str(num_cmd_token or "")
    match = re.search(r"(lp|mp|hp|lk|mk|hk|pp|kk|p|k)$", token)
    return match.group(1) if match else ""


def is_local_gif_num_cmd_part(value):
    token = normalize_num_cmd_token(value)
    return bool(token and re.match(r"^j?\d", token))


# Local GIF filename parsing and index load


def parse_local_hitbox_gif_filename(filename):
    stem, ext = os.path.splitext(os.path.basename(str(filename or "")))
    if ext.lower() not in LOCAL_HITBOX_GIF_EXTENSIONS:
        return None

    parts = [part for part in stem.split("_") if part]
    if not parts:
        return None

    primary_num_cmd = parts[0]
    move_name_parts = parts[1:]
    num_cmd = primary_num_cmd

    if len(parts) > 1 and is_local_gif_num_cmd_part(parts[1]):
        num_cmd = f"{primary_num_cmd}>{parts[1]}"
        move_name_parts = parts[2:]

    move_name = " ".join(move_name_parts).replace("-", " ").strip()
    if not move_name:
        move_name = primary_num_cmd

    return {
        "moveName": move_name,
        "numCmd": num_cmd,
    }


def load_local_hitbox_gif_data(character_lookup):
    gif_data = {}
    if not os.path.isdir(LOCAL_HITBOX_GIF_ROOT):
        print(f"Local hitbox gif folder not found: {LOCAL_HITBOX_GIF_ROOT}")
        return gif_data

    for char_entry in sorted(os.scandir(LOCAL_HITBOX_GIF_ROOT), key=lambda entry: entry.name.lower()):
        if not char_entry.is_dir():
            continue

        char_key = character_lookup.get(normalize_char_name(char_entry.name))
        if not char_key:
            continue

        for file_entry in sorted(os.scandir(char_entry.path), key=lambda entry: entry.name.lower()):
            if not file_entry.is_file():
                continue

            parsed = parse_local_hitbox_gif_filename(file_entry.name)
            if not parsed:
                continue

            gif_data.setdefault(char_key, []).append(
                {
                    "moveName": parsed["moveName"],
                    "numCmd": parsed["numCmd"],
                    "moveLink": file_entry.path,
                    "sourceFile": file_entry.name,
                }
            )

    if not gif_data:
        print(f"No local hitbox gifs loaded from: {LOCAL_HITBOX_GIF_ROOT}")
    return gif_data


DISCORD_ATTACHMENT_LIMIT = 10


def get_existing_local_gif_asset_paths(gif_links, limit=DISCORD_ATTACHMENT_LIMIT):
    paths = []
    seen = set()
    for move_link in gif_links or []:
        path = str(move_link or "").strip()
        if not path:
            continue
        normalized_path = os.path.normpath(path)
        if not os.path.isfile(normalized_path):
            continue
        if normalized_path in seen:
            continue
        seen.add(normalized_path)
        paths.append(normalized_path)
        if limit is not None and len(paths) >= limit:
            break
    return paths


def normalize_move_name_for_gif_text(value):
    text = str(value or "").lower()
    text = text.replace("aerial", "air")
    text = re.sub(r"\bdivekick\b", "dive kick", text)
    text = re.sub(r"\b6\s*h\s*p\s*\+\s*h\s*k\b", "drive reversal", text)
    text = re.sub(r"\b6hphk\b", "drive reversal", text)
    text = re.sub(r"\b5\s*h\s*p\s*\+\s*h\s*k\b", "drive impact", text)
    text = re.sub(r"\b5hphk\b", "drive impact", text)
    text = re.sub(r"\bh\s*p\s*\+\s*h\s*k\b", "drive impact", text)
    text = re.sub(r"\bhphk\b", "drive impact", text)
    text = re.sub(r"\bdi\b", "drive impact", text)
    text = re.sub(r"\bdrev\b", "drive reversal", text)
    text = re.sub(r"\bdrive\s+rev\b", "drive reversal", text)
    text = re.sub(r"\bcr\.?\b", "crouching", text)
    text = re.sub(r"\bidling\b", "idle", text)
    text = re.sub(r"\bidle\b", "standing", text)
    text = re.sub(r"\bstand\b", "standing", text)
    text = re.sub(r"\bbackdash\b", "backward dash", text)
    text = re.sub(r"\bdash\s+back\b", "backward dash", text)
    text = re.sub(r"\bback\s+dash\b", "backward dash", text)
    text = re.sub(r"\bdash\s+forward\b", "forward dash", text)
    text = re.sub(r"\bfwd\b", "forward", text)
    text = re.sub(r"\bdr\b", "drive rush", text)
    text = text.replace("jumping", "jump")
    text = text.replace("standing", "stand")
    text = text.replace("crouching", "crouch")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    raw_tokens = [tok for tok in text.split() if tok]
    if not raw_tokens:
        return ""

    token_map = {
        "lp": "l",
        "lk": "l",
        "light": "l",
        "l": "l",
        "mp": "m",
        "mk": "m",
        "medium": "m",
        "m": "m",
        "hp": "h",
        "hk": "h",
        "heavy": "h",
        "h": "h",
        "ex": "od",
    }
    drop_tokens = {"punch", "kick", "button", "normal", "attack", "move"}
    stocked_variant_tokens = {"stock", "stocked", "boosted", "enhanced", "windclad"}
    has_stocked_variant = False
    normalized_tokens = []
    for token in raw_tokens:
        mapped = token_map.get(token, token)
        if mapped in drop_tokens:
            continue
        if mapped in stocked_variant_tokens:
            has_stocked_variant = True
            continue
        normalized_tokens.append(mapped)
    if has_stocked_variant:
        normalized_tokens.append("stocked")
    return " ".join(normalized_tokens).strip()


def move_name_match_tokens(move_name, num_cmd=""):
    token_set = set()
    name_norm = normalize_move_name_for_gif_text(move_name)
    if name_norm:
        token_set.update(name_norm.split())

    num_cmd_norm = normalize_num_cmd_token(num_cmd)
    suffix = extract_button_suffix(num_cmd_norm)
    strength_token_map = {
        "lp": "l",
        "lk": "l",
        "mp": "m",
        "mk": "m",
        "hp": "h",
        "hk": "h",
        "p": "p",
        "k": "k",
        "pp": "od",
        "kk": "od",
    }
    if suffix:
        token_set.add(suffix)
        mapped_strength = strength_token_map.get(suffix)
        if mapped_strength:
            token_set.add(mapped_strength)

    if num_cmd_norm.startswith(("7", "8", "9")) and ">" not in num_cmd_norm:
        token_set.add("jump")

    return token_set


def text_mentions_stocked_variant(value):
    text = str(value or "").lower()
    if re.search(r"\b0\s*stocks?\b", text):
        return False
    return bool(
        re.search(r"\b[1-9]\d*\s*stocks?\b", text)
        or re.search(r"\b(?:stock|stocked|boosted|enhanced|windclad)\b", text)
        or "wind stock" in text
    )


def row_mentions_stocked_variant(row):
    return any(
        text_mentions_stocked_variant(row.get(field, ""))
        for field in ("moveName", "cmnName", "numCmd", "sourceFile")
    )


def build_num_cmd_candidates_for_gif(row):
    row_num_cmd_raw = str(row.get("numCmd", "")).lower()
    row_num_cmd = normalize_num_cmd_token(row_num_cmd_raw)
    candidates = set()
    move_name_lower = str(row.get("moveName", "")).lower()
    cmn_name_lower = str(row.get("cmnName", "")).lower()
    if row_num_cmd:
        candidates.add(row_num_cmd)
        if ">" in row_num_cmd:
            parts = [part for part in row_num_cmd.split(">") if part]
            candidates.update(parts)
            if parts:
                candidates.add(parts[-1])
                if len(parts) == 2 and parts[0] in {"7", "8", "9"}:
                    candidates.add(f"{parts[0]}{parts[-1]}")
    row_suffix = extract_button_suffix(row_num_cmd)

    if row_suffix and "jump" in move_name_lower and ">" not in row_num_cmd:
        for prefix in ("7", "8", "9"):
            candidates.add(f"{prefix}{row_suffix}")

    if row_suffix and row_num_cmd.startswith("4268"):
        candidates.add(f"9{row_suffix}")
        if row_num_cmd.startswith("42684268"):
            candidates.add(f"99{row_suffix}")

    if row_suffix and "air" in cmn_name_lower and row_num_cmd.startswith("4268"):
        candidates.add(f"9{row_suffix}")

    if row_suffix and "(air" in row_num_cmd_raw:
        if re.match(
            r"^\s*(?:2|1\s*or\s*2\s*or\s*3)\s*(?:lp|mp|hp|lk|mk|hk)\b",
            row_num_cmd_raw,
        ):
            candidates.add(f"92{row_suffix}")

    if row_num_cmd.startswith("46") and "(air" in row_num_cmd_raw and "rolling attack" in move_name_lower:
        candidates.add(f"9{row_num_cmd}")

    if row_suffix in {"p", "k"} and ">" not in row_num_cmd:
        prefix = row_num_cmd[:-1]
        if prefix:
            if row_suffix == "p":
                candidates.update({f"{prefix}lp", f"{prefix}mp", f"{prefix}hp"})
            else:
                candidates.update({f"{prefix}lk", f"{prefix}mk", f"{prefix}hk"})

    return candidates


def should_use_sf6_move_image_for_gif(row):
    char_key = resolve_character_key(str(row.get("char_name", "")).strip())
    row_num_cmd = normalize_num_cmd_token(row.get("numCmd", ""))
    row_move_name_norm = normalize_move_name_for_gif_text(row.get("moveName", ""))

    row_num_cmd_raw = str(row.get("numCmd", "")).lower()
    return bool(
        (char_key == "rashid" and row_num_cmd == "8hk" and row_move_name_norm == "jump h")
        or (
            char_key == "akuma"
            and row_num_cmd == "5lp>5lp>6lk>5hp"
            and row_move_name_norm == "shun goku satsu"
        )
        or (
            str(row.get("moveType", "")).lower() == "throw"
            and (
                "(air" in row_num_cmd_raw
                or "air" in row_move_name_norm
            )
        )
    )


def get_sf6_move_image_gif_fallback(row):
    if not should_use_sf6_move_image_for_gif(row):
        return ""
    if not callable(get_sf6_move_image_url):
        return ""
    return str(get_sf6_move_image_url(row) or "").strip()


# Match a frame row to a local GIF link


def lookup_hitbox_gif_link(row):
    row_char = str(row.get("char_name", "")).strip()
    char_key = resolve_character_key(row_char)
    if not char_key:
        return None

    gif_rows = HITBOX_GIF_DATA.get(char_key, [])
    if not gif_rows:
        return None

    if should_use_sf6_move_image_for_gif(row):
        return None

    row_num_cmd_raw = str(row.get("numCmd", "")).lower()
    row_num_cmd = normalize_num_cmd_token(row_num_cmd_raw)
    row_suffix = extract_button_suffix(row_num_cmd)
    row_move_name_norm = normalize_move_name_for_gif_text(row.get("moveName", ""))
    row_cmn_name_norm = normalize_move_name_for_gif_text(row.get("cmnName", ""))
    row_tokens = set()
    row_tokens.update(move_name_match_tokens(row.get("moveName", ""), row.get("numCmd", "")))
    row_tokens.update(move_name_match_tokens(row.get("cmnName", ""), row.get("numCmd", "")))
    num_cmd_candidates = build_num_cmd_candidates_for_gif(row)
    row_is_jump = "jump" in row_tokens
    row_is_air = bool(
        "(air" in row_num_cmd_raw
        or "air" in row_move_name_norm
        or "air" in row_cmn_name_norm
    )
    row_is_denjin = bool(
        "denjin" in row_move_name_norm
        or "denjin" in row_cmn_name_norm
        or "charged" in row_move_name_norm
        or "charged" in row_cmn_name_norm
        or "hold" in row_move_name_norm
        or "hold" in row_cmn_name_norm
        or "(charged" in row_num_cmd_raw
        or "(hold" in row_num_cmd_raw
    )
    row_is_stocked = row_mentions_stocked_variant(row)

    if char_key == "akuma" and "gou hadoken" in row_move_name_norm and re.search(r"\blvl\s*[23]\b", row_move_name_norm):
        level_match = re.search(r"\blvl\s*([23])\b", row_move_name_norm)
        preferred_level = f"lv{level_match.group(1)}" if level_match else ""
        for gif_row in gif_rows:
            move_link = str(gif_row.get("moveLink", "")).strip()
            if not move_link:
                continue
            gif_name_norm = normalize_move_name_for_gif_text(gif_row.get("moveName", ""))
            if "gou hadoken" in gif_name_norm and preferred_level in gif_name_norm and "zanku" not in gif_name_norm:
                return move_link

    if (
        char_key == "akuma"
        and (
            "zanku hadoken" in row_move_name_norm
            or "air fireball" in row_cmn_name_norm
        )
        and "demon" not in row_move_name_norm
        and "demon" not in row_cmn_name_norm
    ):
        row_is_od = (
            str(row.get("moveName", "")).lower().strip().startswith(("od ", "ex "))
            or row_num_cmd.endswith("pp")
        )
        preferred_names = ["od zanku hadoken"] if row_is_od else ["l zanku hadoken", "zanku hadoken"]

        for preferred_name in preferred_names:
            for gif_row in gif_rows:
                move_link = str(gif_row.get("moveLink", "")).strip()
                if not move_link:
                    continue
                gif_name_norm = normalize_move_name_for_gif_text(gif_row.get("moveName", ""))
                if preferred_name in gif_name_norm and "demon" not in gif_name_norm:
                    return move_link

        for gif_row in gif_rows:
            move_link = str(gif_row.get("moveLink", "")).strip()
            if not move_link:
                continue
            gif_name_norm = normalize_move_name_for_gif_text(gif_row.get("moveName", ""))
            if "zanku hadoken" in gif_name_norm and "demon" not in gif_name_norm:
                return move_link

    gif_candidates = []
    for gif_row in gif_rows:
        move_link = str(gif_row.get("moveLink", "")).strip()
        if not move_link:
            continue

        gif_num_cmd_raw = str(gif_row.get("numCmd", "")).lower()
        gif_num_cmd = normalize_num_cmd_token(gif_num_cmd_raw)
        gif_name_norm = normalize_move_name_for_gif_text(gif_row.get("moveName", ""))
        gif_tokens = move_name_match_tokens(gif_row.get("moveName", ""), gif_row.get("numCmd", ""))

        gif_candidates.append(
            {
                "link": move_link,
                "num_cmd": gif_num_cmd,
                "suffix": extract_button_suffix(gif_num_cmd),
                "name_norm": gif_name_norm,
                "tokens": gif_tokens,
                "is_jump": "jump" in gif_tokens,
                "is_air": bool("(air" in gif_num_cmd_raw or "air" in gif_name_norm),
                "is_denjin": bool(
                    "denjin" in gif_name_norm
                    or "charged" in gif_name_norm
                    or "hold" in gif_name_norm
                    or "(charged" in gif_num_cmd_raw
                    or "(hold" in gif_num_cmd_raw
                ),
                "is_stocked": row_mentions_stocked_variant(gif_row),
            }
        )

    if not gif_candidates:
        return None

    def apply_row_context_filters(items):
        filtered = list(items)

        denjin_matches = [item for item in filtered if item["is_denjin"] == row_is_denjin]
        if denjin_matches:
            filtered = denjin_matches

        air_matches = [item for item in filtered if item["is_air"] == row_is_air]
        if air_matches:
            filtered = air_matches

        jump_matches = [item for item in filtered if item["is_jump"] == row_is_jump]
        if jump_matches:
            filtered = jump_matches

        stocked_matches = [item for item in filtered if item["is_stocked"] == row_is_stocked]
        if stocked_matches:
            filtered = stocked_matches
        elif filtered:
            return []

        return filtered

    def pick_first_link(items):
        if not items:
            return None
        filtered = apply_row_context_filters(items)
        if row_suffix in {"p", "k"}:
            specific_suffixes = {
                item["suffix"]
                for item in filtered
                if item["suffix"] and item["suffix"] not in {"p", "k"}
            }
            if len(specific_suffixes) > 1:
                return None
        if row_suffix:
            suffix_matches = [item for item in filtered if item["suffix"] == row_suffix]
            if suffix_matches:
                filtered = suffix_matches
        return filtered[0]["link"] if filtered else None

    row_names = []
    if row_move_name_norm:
        row_names.append(row_move_name_norm)
    if row_cmn_name_norm and row_cmn_name_norm not in row_names:
        row_names.append(row_cmn_name_norm)

    preferred_air_command_candidates = [
        item
        for item in gif_candidates
        if item["num_cmd"] and item["num_cmd"] in num_cmd_candidates and item["num_cmd"].startswith("92")
    ]
    link = pick_first_link(preferred_air_command_candidates)
    if link:
        return link

    exact_num_cmd_matches = [
        item for item in gif_candidates
        if row_num_cmd and item["num_cmd"] == row_num_cmd
    ]
    exact_num_cmd_has_air_split = (
        any(item["is_air"] for item in exact_num_cmd_matches)
        and any(not item["is_air"] for item in exact_num_cmd_matches)
    )
    num_cmd_candidate_matches = [
        item for item in gif_candidates
        if item["num_cmd"] and item["num_cmd"] in num_cmd_candidates
    ]
    if (
        row_is_jump
        and "neutral" not in row_move_name_norm
        and re.search(r"\b7\s*or\s*9", row_num_cmd_raw)
    ):
        forward_jump_matches = [
            item for item in num_cmd_candidate_matches if item["num_cmd"].startswith("9")
        ]
        link = pick_first_link(forward_jump_matches)
        if link:
            return link
    if exact_num_cmd_has_air_split:
        link = pick_first_link(exact_num_cmd_matches)
        if link:
            return link
    if row_is_air and exact_num_cmd_matches and not any(item["is_air"] for item in exact_num_cmd_matches):
        num_cmd_candidate_name_matches = [
            item for item in num_cmd_candidate_matches
            if any(
                name and (
                    item["name_norm"] == name
                    or name in item["name_norm"]
                    or item["name_norm"] in name
                )
                for name in row_names
            )
        ]
        link = pick_first_link(num_cmd_candidate_name_matches)
        if link:
            return link
        air_candidate_matches = [item for item in num_cmd_candidate_matches if item["is_air"]]
        link = pick_first_link(air_candidate_matches)
        if link:
            return link
    exact_num_cmd_name_matches = [
        item for item in exact_num_cmd_matches
        if any(
            name and (
                item["name_norm"] == name
                or name in item["name_norm"]
                or item["name_norm"] in name
            )
            for name in row_names
        )
    ]
    link = pick_first_link(exact_num_cmd_name_matches)
    if link:
        return link
    link = pick_first_link(exact_num_cmd_matches)
    if link:
        return link

    num_cmd_candidate_name_matches = [
        item for item in num_cmd_candidate_matches
        if any(
            name and (
                item["name_norm"] == name
                or name in item["name_norm"]
                or item["name_norm"] in name
            )
            for name in row_names
        )
    ]
    link = pick_first_link(num_cmd_candidate_name_matches)
    if link:
        return link
    link = pick_first_link(num_cmd_candidate_matches)
    if link:
        return link

    exact_name_matches = [
        item for item in gif_candidates
        if any(name and item["name_norm"] == name for name in row_names)
    ]
    link = pick_first_link(exact_name_matches)
    if link:
        return link

    contains_name_matches = [
        item for item in gif_candidates
        if any(
            name
            and (
                name in item["name_norm"]
                or item["name_norm"] in name
            )
            for name in row_names
        )
    ]
    link = pick_first_link(contains_name_matches)
    if link:
        return link

    token_overlap_matches = [
        item for item in gif_candidates
        if row_tokens and (row_tokens & item["tokens"])
    ]
    link = pick_first_link(token_overlap_matches)
    if link:
        return link

    return None


def collect_hitbox_gif_links(rows, limit=DISCORD_ATTACHMENT_LIMIT):
    links = []
    seen = set()
    for row in rows:
        for move_link in get_frame_row_gif_links(row, limit=limit):
            if not move_link or move_link in seen:
                continue
            seen.add(move_link)
            links.append(move_link)
            if len(links) >= limit:
                break
        if len(links) >= limit:
            break
    return links


# Natural-language GIF query resolution


def find_characters_in_text(text):
    text_lower = strip_discord_mentions(text).lower()
    return find_aliases_in_text(text_lower, CHARACTER_ALIASES, FRAME_DATA.keys())


def remove_first_token_sequence(tokens, sequence):
    return remove_first_token_sequence_shared(tokens, sequence)


def extract_gif_move_query_text(text, char_key):
    tokens = re.findall(r"[a-z0-9]+", strip_discord_mentions(text).lower())

    alias_forms = {char_key}
    for alias, canonical in CHARACTER_ALIASES.items():
        if canonical == char_key:
            alias_forms.add(alias)

    alias_sequences = sorted(
        [tuple(re.findall(r"[a-z0-9]+", form.lower())) for form in alias_forms],
        key=len,
        reverse=True,
    )
    alias_sequences = [seq for seq in alias_sequences if seq]

    for sequence in alias_sequences:
        tokens, _ = remove_first_token_sequence(tokens, list(sequence))

    filler_tokens = {
        "send", "show", "post", "drop", "give", "get", "share", "link",
        "gif", "gifs", "hitbox", "hitboxes", "the", "a", "an", "me",
        "please", "can", "you", "for", "of", "to", "with", "and",
        "korean", "bub",
        "framedata", "frame", "frames", "data",
    }
    filtered_tokens = [tok for tok in tokens if tok not in filler_tokens]
    return " ".join(filtered_tokens).strip()


def resolve_hitbox_gif_query_alias(char_key, move_query):
    query_raw = str(move_query or "").strip().lower()
    if not query_raw:
        return query_raw

    query_raw = re.sub(r"\bdivekick\b", "dive kick", query_raw)
    if char_key != "jamie":
        if char_key == "cammy":
            cammy_gif_aliases = {
                "airthrow": "leg scissors choke",
                "air throw": "leg scissors choke",
                "air grab": "leg scissors choke",
                "aerial throw": "leg scissors choke",
                "reverse edge": "236k>2k",
                "od reverse edge": "236kk>2k",
                "silent step": "236k>p",
                "od silent step": "236kk>p",
                "cannon strike": "236k>k",
                "od cannon strike": "236kk>k",
                "fatal leg twister": "236k>lplk",
                "od fatal leg twister": "236kk>lplk",
                "hooligan combination reverse edge": "236k>2k",
                "od hooligan combination reverse edge": "236kk>2k",
                "hooligan combination silent step": "236k>p",
                "od hooligan combination silent step": "236kk>p",
                "hooligan combination cannon strike": "236k>k",
                "od hooligan combination cannon strike": "236kk>k",
                "hooligan combination fatal leg twister": "236k>lplk",
                "od hooligan combination fatal leg twister": "236kk>lplk",
                "hooligan combination > reverse edge": "236k>2k",
                "od hooligan combination > reverse edge": "236kk>2k",
                "hooligan combination > silent step": "236k>p",
                "od hooligan combination > silent step": "236kk>p",
                "hooligan combination > cannon strike": "236k>k",
                "od hooligan combination > cannon strike": "236kk>k",
                "hooligan combination > fatal leg twister": "236k>lplk",
                "od hooligan combination > fatal leg twister": "236kk>lplk",
            }
            return cammy_gif_aliases.get(query_raw, query_raw)
        if char_key == "dhalsim":
            dhalsim_gif_aliases = {
                "fireball": "yoga fire",
                "yoga fire": "yoga fire",
                "l yoga fire": "236llp",
                "m yoga fire": "236lmp",
                "h yoga fire": "236lhp",
                "light yoga fire": "236llp",
                "medium yoga fire": "236lmp",
                "heavy yoga fire": "236lhp",
                "light fireball": "236llp",
                "medium fireball": "236lmp",
                "heavy fireball": "236lhp",
                "236lp": "236llp",
                "236mp": "236lmp",
                "236hp": "236lhp",
                "od yoga fire": "236lpmp",
                "ex yoga fire": "236lpmp",
                "236pp": "236lpmp",
                "arch": "yoga arch",
                "yoga arch": "yoga arch",
                "l arch": "236lk",
                "m arch": "236mk",
                "h arch": "236hk",
                "light arch": "236lk",
                "medium arch": "236mk",
                "heavy arch": "236hk",
                "l yoga arch": "236lk",
                "m yoga arch": "236mk",
                "h yoga arch": "236hk",
                "light yoga arch": "236lk",
                "medium yoga arch": "236mk",
                "heavy yoga arch": "236hk",
                "236lk": "236lk",
                "236mk": "236mk",
                "236hk": "236hk",
                "comet": "yoga comet",
                "commet": "yoga comet",
                "yoga comet": "yoga comet",
                "yoga commet": "yoga comet",
                "air comet": "yoga comet",
                "air commet": "yoga comet",
                "air yoga comet": "yoga comet",
                "air yoga commet": "yoga comet",
                "l yoga comet": "963214lp",
                "m yoga comet": "963214mp",
                "h yoga comet": "963214hp",
                "l yoga commet": "963214lp",
                "m yoga commet": "963214mp",
                "h yoga commet": "963214hp",
                "light yoga comet": "963214lp",
                "medium yoga comet": "963214mp",
                "heavy yoga comet": "963214hp",
                "light yoga commet": "963214lp",
                "medium yoga commet": "963214mp",
                "heavy yoga commet": "963214hp",
            }
            return dhalsim_gif_aliases.get(query_raw, query_raw)
        if char_key == "alex":
            alex_gif_aliases = {
                "stance jab": "palm jab",
                "stance lp": "palm jab",
                "2pp lp": "palm jab",
                "2pp 5lp": "palm jab",
                "stance shoulder": "shoulder launcher",
                "stance mp": "shoulder launcher",
                "2pp mp": "shoulder launcher",
                "2pp 5mp": "shoulder launcher",
                "stance lariat": "heavy lariat",
                "stance hp": "heavy lariat",
                "2pp hp": "heavy lariat",
                "2pp 5hp": "heavy lariat",
                "stance hop": "tactical hop",
                "stance lk": "tactical hop",
                "2pp lk": "tactical hop",
                "2pp 5lk": "tactical hop",
                "stance stomp": "air stampede",
                "stance mk": "air stampede",
                "2pp mk": "air stampede",
                "2pp 5mk": "air stampede",
                "stance hk": "sweep combination",
                "stance hk hk": "sweep combination",
                "sweep combination 1": "sweep combination",
                "sweep combination 2": "sweep combination",
                "2pp hk": "sweep combination",
                "2pp 5hk": "sweep combination",
                "stance throw": "hyper takedown",
                "stance lplk": "hyper takedown",
                "stance 5lplk": "hyper takedown",
                "2pp lplk": "hyper takedown",
                "2pp 5lplk": "hyper takedown",
                "stance command grab": "dangerous armbar",
                "stance 2lplk": "dangerous armbar",
                "2pp 2lplk": "dangerous armbar",
                "stance 6p": "slashing elbow",
                "2pp 6p": "slashing elbow",
                "stance 6": "low rush",
                "2pp 6": "low rush",
                "stance 4": "low retreat",
                "2pp 4": "low retreat",
                "hold hp": "stand hp (hold)",
                "held hp": "stand hp (hold)",
                "charged hp": "stand hp (hold)",
                "hold hk": "stand hk (hold)",
                "held hk": "stand hk (hold)",
                "charged hk": "stand hk (hold)",
            }
            return alex_gif_aliases.get(query_raw, query_raw)
        if char_key == "rashid":
            rashid_gif_aliases = {
                "whirlwind shot (lvl 2)": "whirlwind shot",
                "whirlwind shot (lvl 3)": "whirlwind shot",
                "whirlwind shot lvl 2": "whirlwind shot",
                "whirlwind shot lvl 3": "whirlwind shot",
                "level 2 whirlwind shot": "whirlwind shot",
                "level 3 whirlwind shot": "whirlwind shot",
                "lvl 2 whirlwind shot": "whirlwind shot",
                "lvl 3 whirlwind shot": "whirlwind shot",
            }
            return rashid_gif_aliases.get(query_raw, query_raw)
        return query_raw

    jamie_gif_aliases = {
        "breakdance": "bakkai",
        "break dance": "bakkai",
        "l breakdance": "l bakkai",
        "l break dance": "l bakkai",
        "m breakdance": "m bakkai",
        "m break dance": "m bakkai",
        "h breakdance": "h bakkai",
        "h break dance": "h bakkai",
        "od breakdance": "od bakkai",
        "od break dance": "od bakkai",
        "ex breakdance": "od bakkai",
        "ex break dance": "od bakkai",
        "236k": "bakkai",
        "236lk": "l bakkai",
        "236mk": "m bakkai",
        "236hk": "h bakkai",
        "236kk": "od bakkai",
        "dive kick": "luminous dive kick",
        "l dive kick": "l luminous dive kick",
        "m dive kick": "m luminous dive kick",
        "h dive kick": "h luminous dive kick",
        "od dive kick": "od luminous dive kick",
        "ex dive kick": "od luminous dive kick",
        "luminous dive kick": "luminous dive kick",
        "l luminous dive kick": "l luminous dive kick",
        "m luminous dive kick": "m luminous dive kick",
        "h luminous dive kick": "h luminous dive kick",
        "od luminous dive kick": "od luminous dive kick",
        "ex luminous dive kick": "od luminous dive kick",
        "214k": "luminous dive kick",
        "214lk": "l luminous dive kick",
        "214mk": "m luminous dive kick",
        "214hk": "h luminous dive kick",
        "214kk": "od luminous dive kick",
        "j214k": "luminous dive kick",
        "j.214k": "luminous dive kick",
        "j 214k": "luminous dive kick",
        "j214lk": "l luminous dive kick",
        "j.214lk": "l luminous dive kick",
        "j 214lk": "l luminous dive kick",
        "j214mk": "m luminous dive kick",
        "j.214mk": "m luminous dive kick",
        "j 214mk": "m luminous dive kick",
        "j214hk": "h luminous dive kick",
        "j.214hk": "h luminous dive kick",
        "j 214hk": "h luminous dive kick",
        "j214kk": "od luminous dive kick",
        "j.214kk": "od luminous dive kick",
        "j 214kk": "od luminous dive kick",
        "swagger hermit punch": "freeflow strikes (2) (drink 4)",
        "hermit punch": "freeflow strikes (2) (drink 4)",
        "lp swagger hermit punch": "freeflow strikes (2) (drink 4)",
        "mp swagger hermit punch": "freeflow strikes (2) (drink 4)",
        "hp swagger hermit punch": "freeflow strikes (2) (drink 4)",
        "lp hermit punch": "freeflow strikes (2) (drink 4)",
        "mp hermit punch": "freeflow strikes (2) (drink 4)",
        "hp hermit punch": "freeflow strikes (2) (drink 4)",
        "palm followup": "freeflow strikes (2) (drink 4)",
        "palm follow-up": "freeflow strikes (2) (drink 4)",
        "palm follow up": "freeflow strikes (2) (drink 4)",
        "od swagger hermit punch": "od drink level 4 freeflow strikes (2)",
        "ex swagger hermit punch": "od drink level 4 freeflow strikes (2)",
        "od hermit punch": "od drink level 4 freeflow strikes (2)",
        "ex hermit punch": "od drink level 4 freeflow strikes (2)",
    }
    return jamie_gif_aliases.get(query_raw, query_raw)


