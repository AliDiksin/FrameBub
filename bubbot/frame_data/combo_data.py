"""Cross-game SF6 and MK1 combo load, NL filter, embeds, menu/slash views."""

import json
import os
import re
from pathlib import Path

import discord
import pandas as pd

from bubbot.utils.character_lookup import find_alias_positions_in_text, resolve_alias_key
from bubbot.utils.choice_utils import character_choices
from bubbot.utils.discord_formatting import add_embed_field, clean_value, truncate_value
from bubbot.utils.text_utils import compact_key, strip_noise_words
from bubbot.frame_data import combo_presentation

SF6_COMBOS_FILE = "SF6 Combos.ods"
MK1_COMBOS_FILE = os.path.join("mk1", "combos.json")
COMBO_GAMES = frozenset({"sf6", "mk1"})
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

COMBO_DATA = {}

GAME_CONFIG = {
    "sf6": {
        "label": "Street Fighter 6",
        "colour": 0x3998C6,
        "game_terms": ("sf6", "street fighter 6"),
    },
    "mk1": {
        "label": "Mortal Kombat 1",
        "colour": 0x7E1616,
        "game_terms": ("mk1", "mortal kombat 1", "mortal kombat one", "mortal kombat"),
        "kameo_aware": True,
    },
}

COMBO_COLUMNS = [
    "char_key",
    "char_name",
    "source_url",
    "group",
    "position",
    "title",
    "recipe",
    "damage",
    "difficulty",
    "drive",
    "meter",
    "kameo",
    "kameo_meter",
    "tags",
    "video",
    "notes",
]

DISCORD_EMBED_CHAR_BUDGET = 5800
DISCORD_EMBED_MAX_FIELDS = 25

_resolve_sf6_character_key = None
_resolve_mk1_character_key = None
_mk1_character_aliases = None
_sf6_character_aliases = None
_row_subheader = combo_presentation._row_subheader
_combo_field_name = combo_presentation._combo_field_name
_combo_field_value = combo_presentation._combo_field_value
_embed_size = combo_presentation._embed_size
_clone_embed = combo_presentation._clone_embed
build_combo_pages = combo_presentation.build_combo_pages
ComboListView = combo_presentation.ComboListView
ComboListPreviousButton = combo_presentation.ComboListPreviousButton
ComboListNextButton = combo_presentation.ComboListNextButton
ComboListBackButton = combo_presentation.ComboListBackButton
send_combo_section_menu = combo_presentation.send_combo_section_menu
send_combo_entry = combo_presentation.send_combo_entry
send_combo_response = combo_presentation.send_combo_response
build_combo_embed = combo_presentation.build_combo_embed


# Game config and ODS/JSON load


def configure(
    *,
    resolve_sf6_character_key,
    resolve_mk1_character_key,
    sf6_character_aliases,
    mk1_character_aliases,
):
    global _resolve_sf6_character_key, _resolve_mk1_character_key
    global _sf6_character_aliases, _mk1_character_aliases
    _resolve_sf6_character_key = resolve_sf6_character_key
    _resolve_mk1_character_key = resolve_mk1_character_key
    _sf6_character_aliases = sf6_character_aliases or {}
    _mk1_character_aliases = mk1_character_aliases or {}
    combo_presentation.configure(
        **{
            name: value
            for name, value in globals().items()
            if not name.startswith("__") and name not in {"configure", "combo_presentation"}
        }
    )


def _game_config(game):
    return GAME_CONFIG.get(str(game or "").strip().lower()) or {}


def game_label(game):
    return _game_config(game).get("label") or str(game).upper()


def game_colour(game):
    return int(_game_config(game).get("colour") or 0xAAAAAA)


def _resolve_data_path(filename):
    path = Path(str(filename or ""))
    if path.is_absolute():
        return str(path)
    return str(_PROJECT_ROOT / path)


def combo_row_count(game):
    data = COMBO_DATA.get(str(game or "").strip().lower()) or {}
    return sum(len(rows) for rows in data.values())


def has_combos(game):
    game_key = str(game or "").strip().lower()
    if game_key not in COMBO_GAMES:
        return False
    return combo_row_count(game_key) > 0


def ensure_combo_data_loaded(game=None):
    """Load combo workbooks if missing; safe to call from menu buttons after startup."""
    game_key = str(game or "").strip().lower() if game else ""
    if game_key and combo_row_count(game_key) > 0:
        return True
    if not game_key and combo_row_count("sf6") > 0 and combo_row_count("mk1") > 0:
        return True
    return load_combo_data()


def _aliases_for_game(game):
    if game == "sf6":
        return _sf6_character_aliases or {}
    if game == "mk1":
        return _mk1_character_aliases or {}
    return {}


def _resolve_character_key(game, text):
    if game == "sf6" and _resolve_sf6_character_key:
        return _resolve_sf6_character_key(text)
    if game == "mk1" and _resolve_mk1_character_key:
        return _resolve_mk1_character_key(text)
    aliases = _aliases_for_game(game)
    keys = list((COMBO_DATA.get(game) or {}).keys())
    return resolve_alias_key(text, aliases, keys, normalize_fn=compact_key)


def _extract_export_rows(filename):
    if not os.path.exists(filename):
        print(f"[combo] data file not found: {filename}", flush=True)
        return []
    with open(filename, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    for item in payload:
        if isinstance(item, dict) and isinstance(item.get("data"), list):
            return item["data"]
    return []


def _normalize_row(game, raw_row):
    if game == "mk1":
        char_name = str(raw_row.get("char_name") or "").strip()
        if not char_name:
            return None
        char_key = compact_key(char_name)
        return {
            "char_key": char_key,
            "char_name": char_name,
            "source_url": str(raw_row.get("url") or "").strip(),
            "group": str(raw_row.get("subcategory") or "").strip(),
            "position": str(raw_row.get("category") or "").strip(),
            "title": "",
            "recipe": str(raw_row.get("combo") or "").strip(),
            "damage": str(raw_row.get("damage") or "").strip(),
            "difficulty": str(raw_row.get("difficulty") or "").strip(),
            "drive": "",
            "meter": str(raw_row.get("meter") or "").strip(),
            "kameo": str(raw_row.get("kameo_name") or "").strip(),
            "kameo_meter": str(raw_row.get("kameo_meter") or "").strip(),
            "tags": str(raw_row.get("tags") or "").strip(),
            "video": str(raw_row.get("url") or "").strip(),
            "notes": str(raw_row.get("notes") or "").strip(),
        }
    row = {column: str(raw_row.get(column, "") or "").strip() for column in COMBO_COLUMNS}
    if not row.get("recipe"):
        return None
    if not row.get("char_key") and row.get("char_name"):
        row["char_key"] = compact_key(row["char_name"])
    return row


def load_combo_data(
    *,
    sf6_file=None,
    mk1_file=None,
):
    global COMBO_DATA
    COMBO_DATA = {"sf6": {}, "mk1": {}}
    sf6_file = _resolve_data_path(sf6_file or SF6_COMBOS_FILE)
    mk1_file = _resolve_data_path(mk1_file or MK1_COMBOS_FILE)

    if os.path.exists(sf6_file):
        try:
            workbook = pd.ExcelFile(sf6_file)
            for sheet_name in workbook.sheet_names:
                df = pd.read_excel(workbook, sheet_name=sheet_name)
                df = df.fillna("")
                for _, raw in df.iterrows():
                    row = _normalize_row("sf6", raw.to_dict())
                    if not row:
                        continue
                    resolved = _resolve_sf6_character_key(row.get("char_name") or sheet_name) if _resolve_sf6_character_key else None
                    if resolved:
                        row["char_key"] = resolved
                    elif not row.get("char_key"):
                        row["char_key"] = compact_key(sheet_name.replace("Normal", ""))
                    COMBO_DATA["sf6"].setdefault(row["char_key"], []).append(row)
        except Exception as error:
            print(f"[combo] SF6 load error: {error}", flush=True)
    else:
        print(f"[combo] SF6 combos workbook missing: {sf6_file}", flush=True)

    for raw_row in _extract_export_rows(mk1_file):
        row = _normalize_row("mk1", raw_row)
        if not row:
            continue
        if _resolve_mk1_character_key:
            resolved = _resolve_mk1_character_key(row["char_name"])
            if resolved and not str(resolved).startswith("kameo_"):
                row["char_key"] = resolved
        COMBO_DATA["mk1"].setdefault(row["char_key"], []).append(row)

    sf6_count = sum(len(rows) for rows in COMBO_DATA["sf6"].values())
    mk1_count = sum(len(rows) for rows in COMBO_DATA["mk1"].values())
    print(
        f"[combo] loaded sf6 characters={len(COMBO_DATA['sf6'])} combos={sf6_count}; "
        f"mk1 characters={len(COMBO_DATA['mk1'])} combos={mk1_count}",
        flush=True,
    )
    return bool(sf6_count or mk1_count)


# Menu section/subsection navigation


def combo_character_list(game):
    data = COMBO_DATA.get(game) or {}
    filtered = {key: rows for key, rows in data.items() if rows and not str(key).startswith("kameo_")}

    if game == "mk1":
        from bubbot.frame_data.mk1_frame_data import display_char_name

        return character_choices(
            filtered,
            display_fn=lambda char_key, _rows: display_char_name(char_key),
        )
    return character_choices(
        filtered,
        display_fn=lambda char_key, _rows: str(char_key).replace(".", " ").replace("_", " ").title(),
    )


def display_char_name(game, char_key):
    rows = (COMBO_DATA.get(game) or {}).get(char_key) or []
    if rows and rows[0].get("char_name"):
        return str(rows[0]["char_name"]).strip()
    if game == "mk1":
        from bubbot.frame_data.mk1_frame_data import display_char_name as mk1_display

        return mk1_display(char_key)
    return str(char_key or "Unknown").replace("_", " ").title()


def combo_groups(game, char_key):
    rows = list((COMBO_DATA.get(game) or {}).get(char_key) or [])
    ordered = []
    seen = set()
    for row in rows:
        label = str(row.get("group") or "").strip() or "General"
        if label in seen:
            continue
        seen.add(label)
        count = sum(1 for item in rows if (str(item.get("group") or "").strip() or "General") == label)
        ordered.append((label, count))
    return ordered


GROUP_SEPARATOR = " — "
COMBO_SECTION_SUBSECTION_THRESHOLD = 10
POSITION_SUBSECTION_ORDER = (
    "Anywhere",
    "Midscreen",
    "Corner",
    "Near Corner",
    "Point Blank",
    "Corner Wallsplat",
    "Punish Counter",
    "Back To Corner",
    "Not In The Corner",
    "Not Corner",
    "Corner Only",
    "Midscreen/Corner",
)


def _split_group(group):
    """Split a stored group label into (section, subsection)."""
    text = str(group or "").strip() or "General"
    if GROUP_SEPARATOR in text:
        section, subsection = text.split(GROUP_SEPARATOR, 1)
        return (section.strip() or "General"), subsection.strip()
    return text, ""


def combo_sections(game, char_key):
    """Return ordered (section_label, count) pairs for the page's top-level headings."""
    rows = list((COMBO_DATA.get(game) or {}).get(char_key) or [])
    ordered = []
    seen = set()
    for row in rows:
        section, _subsection = _split_group(row.get("group"))
        if section in seen:
            continue
        seen.add(section)
        count = sum(1 for item in rows if _split_group(item.get("group"))[0] == section)
        ordered.append((section, count))
    return ordered


def rows_for_section(game, char_key, section):
    rows = list((COMBO_DATA.get(game) or {}).get(char_key) or [])
    return [row for row in rows if _split_group(row.get("group"))[0] == section]


def _row_partition_label(row):
    """Menu button label within a section. Wiki h3/tabber trail plus row position when present."""
    _section, subsection = _split_group(row.get("group"))
    parts = [part.strip() for part in subsection.split(GROUP_SEPARATOR) if part.strip()] if subsection else []
    position = str(row.get("position") or "").strip()
    if position and (not parts or parts[-1].lower() != position.lower()):
        parts.append(position)
    if parts:
        return GROUP_SEPARATOR.join(parts)
    return "General"


def _subsection_label(row):
    return _row_partition_label(row)


def _subsection_sort_key(label):
    parts = [part.strip() for part in str(label or "").split(GROUP_SEPARATOR) if part.strip()]
    if len(parts) >= 2:
        prefix = GROUP_SEPARATOR.join(parts[:-1])
        position = parts[-1]
        pos_rank = (
            POSITION_SUBSECTION_ORDER.index(position)
            if position in POSITION_SUBSECTION_ORDER
            else len(POSITION_SUBSECTION_ORDER)
        )
        return (0, prefix.lower(), pos_rank, position.lower())
    if label in POSITION_SUBSECTION_ORDER:
        return (1, "", POSITION_SUBSECTION_ORDER.index(label), "")
    return (1, "", len(POSITION_SUBSECTION_ORDER), str(label or "").lower())


def combo_subsections(game, char_key, section):
    """Return ordered (subsection_label, count) pairs within a top-level section."""
    rows = rows_for_section(game, char_key, section)
    counts: dict[str, int] = {}
    order: list[str] = []
    for row in rows:
        label = _row_partition_label(row)
        if label not in counts:
            order.append(label)
            counts[label] = 0
        counts[label] += 1
    ordered = [(label, counts[label]) for label in order]
    # Preserve wiki/tabber order for compound labels (e.g. Windless before Windclad).
    if all(GROUP_SEPARATOR in label for label in order):
        return ordered
    return sorted(ordered, key=lambda item: _subsection_sort_key(item[0]))


def section_needs_subsection_menu(game, char_key, section):
    """True when a section has more than one navigable subsection (any character)."""
    return len(combo_subsections(game, char_key, section)) > 1


def rows_for_subsection(game, char_key, section, subsection):
    rows = rows_for_section(game, char_key, section)
    return [row for row in rows if _row_partition_label(row) == subsection]


def combo_entry_nav(game, char_key, *, group=None, rows=None):
    """Choose section menu vs a filtered combo list for NL/slash entry."""
    rows = list(rows or [])
    group_label = str(group or "").strip()
    if not group_label:
        return "section_menu", {}
    if not rows:
        return "empty", {}
    section_names = {label for label, _count in combo_sections(game, char_key)}
    if group_label in section_names:
        return "section_list", {"section": group_label, "rows": rows_for_section(game, char_key, group_label)}
    return "group_list", {"group": group_label, "rows": rows}


def _combo_compact(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _query_has_combo_intent(text):
    return bool(re.search(r"\b(?:combo|combos|bnb|bnbs|route|routes)\b", str(text or "").lower()))


def _query_has_game_tag(text, game):
    lowered = str(text or "").lower()
    for term in _game_config(game).get("game_terms") or ():
        if re.search(rf"\b{re.escape(term)}\b", lowered):
            return True
    return False


def _combo_query_terms(text):
    lowered = str(text or "").lower()
    return {
        "corner": bool(re.search(r"\bcorner\b", lowered)),
        "midscreen": bool(re.search(r"\bmid\s*screen|\bmidscreen\b", lowered)),
        "anywhere": bool(re.search(r"\banywhere\b", lowered)),
        "easy": bool(re.search(r"\b(?:very\s+)?easy\b", lowered)),
        "medium": bool(re.search(r"\bmedium\b", lowered)),
        "hard": bool(re.search(r"\b(?:very\s+)?hard\b", lowered)),
        "meterless": bool(re.search(r"\bmeterless|no\s+meter\b", lowered)),
        "starter": bool(re.search(r"\bstarter\b", lowered)),
        "punish": bool(re.search(r"\bpunish(?:\s+counter)?\b", lowered)),
        "stun": bool(re.search(r"\bstun\b", lowered)),
        "drive_impact": bool(re.search(r"\bdrive\s+impact\b", lowered)),
    }


def _difficulty_matches(row_difficulty, terms):
    row_value = str(row_difficulty or "").strip().lower()
    if not row_value:
        return not any(terms.get(key) for key in ("easy", "medium", "hard"))
    if terms.get("easy") and "easy" in row_value:
        return True
    if terms.get("medium") and "medium" in row_value:
        return True
    if terms.get("hard") and "hard" in row_value:
        return True
    return not any(terms.get(key) for key in ("easy", "medium", "hard"))


def _position_matches(row_position, terms):
    position = str(row_position or "").strip().lower()
    if terms.get("corner") and "corner" in position:
        return True
    if terms.get("midscreen") and "mid" in position:
        return True
    if terms.get("anywhere") and ("anywhere" in position or not position):
        return True
    if not terms.get("corner") and not terms.get("midscreen") and not terms.get("anywhere"):
        return True
    return False


def _extract_group_filter(text, char_key, game):
    lowered = str(text or "").lower()
    if not char_key:
        return None, lowered
    groups = [label for label, _count in combo_groups(game, char_key)]
    if not groups:
        return None, lowered

    alias_text = lowered
    strip_aliases = dict(_aliases_for_game(game) or {})
    for key in (COMBO_DATA.get(game) or {}):
        strip_aliases.setdefault(str(key), key)
    for alias, resolved in sorted(strip_aliases.items(), key=lambda item: len(item[0]), reverse=True):
        if resolved == char_key and alias in alias_text:
            alias_text = re.sub(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", " ", alias_text)

    alias_text = re.sub(r"\b(?:combo|combos|bnb|bnbs|route|routes)\b", " ", alias_text)
    for term in _game_config(game).get("game_terms") or ():
        alias_text = re.sub(rf"\b{re.escape(term)}\b", " ", alias_text)
    alias_text = strip_noise_words(alias_text)
    alias_text = re.sub(
        r"\b(?:corner|mid\s*screen|midscreen|anywhere|easy|medium|hard|very|starter|punish|counter|stun|drive\s+impact|meterless|no\s+meter)\b",
        " ",
        alias_text,
    )
    alias_text = re.sub(r"\s+", " ", alias_text).strip()
    if not alias_text:
        return None, lowered

    query_compact = _combo_compact(alias_text)
    if not query_compact:
        return None, lowered

    best_group = None
    best_score = -1
    for group_label in groups:
        group_compact = _combo_compact(group_label)
        if not group_compact:
            continue
        score = 0
        if query_compact == group_compact:
            score = 100
        elif group_compact.startswith(query_compact) or query_compact.startswith(group_compact):
            score = 80
        elif query_compact in group_compact or group_compact in query_compact:
            score = 60
        if score > best_score:
            best_score = score
            best_group = group_label

    if best_score < 60:
        return None, lowered
    return best_group, lowered


def find_characters_in_text(game, text):
    keys = list((COMBO_DATA.get(game) or {}).keys())
    # Combo keys are the scraped canonical names (e.g. "ken", "ryu"). The shared
    # alias matcher only scans the alias map, so make each canonical key matchable
    # on its own even when no nickname alias exists for it.
    aliases = dict(_aliases_for_game(game) or {})
    for key in keys:
        aliases.setdefault(str(key), key)
    matches = find_alias_positions_in_text(str(text or "").lower(), aliases, keys)
    if game == "mk1":
        return [match for match in matches if not str(match[0]).startswith("kameo_")]
    return matches


# Natural-language combo query


def find_combo_rows_in_text(game, text):
    lowered = str(text or "").lower()
    combo_query = _query_has_combo_intent(lowered)
    if not combo_query:
        return {
            "combo_query": False,
            "rows": [],
            "char_key": None,
            "char_found": False,
            "group": None,
            "game_query": _query_has_game_tag(lowered, game),
        }

    char_matches = find_characters_in_text(game, lowered)
    char_key = None
    for candidate, _start, _end, _alias in char_matches:
        char_key = candidate
        break

    if not char_key:
        return {
            "combo_query": True,
            "rows": [],
            "char_key": None,
            "char_found": False,
            "group": None,
            "game_query": _query_has_game_tag(lowered, game),
        }

    rows = list((COMBO_DATA.get(game) or {}).get(char_key) or [])
    terms = _combo_query_terms(lowered)
    group_filter, _ = _extract_group_filter(lowered, char_key, game)

    if game == "mk1" and _game_config(game).get("kameo_aware"):
        kameo_filter = None
        for row in rows:
            kameo_name = str(row.get("kameo") or "").strip().lower()
            if kameo_name and re.search(rf"\b{re.escape(kameo_name)}\b", lowered):
                kameo_filter = kameo_name
                break
        if kameo_filter:
            rows = [row for row in rows if str(row.get("kameo") or "").strip().lower() == kameo_filter]

    if group_filter:
        rows = [row for row in rows if (str(row.get("group") or "").strip() or "General") == group_filter]
    elif terms.get("starter") or terms.get("punish") or terms.get("stun") or terms.get("drive_impact"):
        keyword_rows = []
        for row in rows:
            haystack = " ".join(
                part
                for part in (
                    str(row.get("group") or ""),
                    str(row.get("position") or ""),
                    str(row.get("title") or ""),
                    str(row.get("notes") or ""),
                )
                if part
            ).lower()
            if terms.get("starter") and "starter" in haystack:
                keyword_rows.append(row)
            elif terms.get("punish") and "punish" in haystack:
                keyword_rows.append(row)
            elif terms.get("stun") and "stun" in haystack:
                keyword_rows.append(row)
            elif terms.get("drive_impact") and "drive impact" in haystack:
                keyword_rows.append(row)
        if keyword_rows:
            rows = keyword_rows

    if terms.get("corner") or terms.get("midscreen") or terms.get("anywhere"):
        rows = [row for row in rows if _position_matches(row.get("position"), terms)]

    if any(terms.get(key) for key in ("easy", "medium", "hard")):
        rows = [row for row in rows if _difficulty_matches(row.get("difficulty"), terms)]

    if terms.get("meterless"):
        rows = [row for row in rows if str(row.get("meter") or "").strip() in {"", "0"}]

    query_compact = _combo_compact(
        re.sub(
            r"\b(?:combo|combos|bnb|bnbs|route|routes|corner|mid\s*screen|midscreen|anywhere|easy|medium|hard|meterless|starter|punish|stun|drive\s+impact)\b",
            " ",
            lowered,
        )
    )
    if query_compact and not group_filter:
        prefix_rows = [
            row
            for row in rows
            if _combo_compact(row.get("recipe")).startswith(query_compact)
            or _combo_compact(row.get("group")).startswith(query_compact)
        ]
        if prefix_rows:
            rows = prefix_rows

    return {
        "combo_query": True,
        "rows": rows,
        "char_key": char_key,
        "char_found": True,
        "group": group_filter,
        "game_query": _query_has_game_tag(lowered, game),
    }


SUBHEADER_DIVIDER = "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"


# Paginated combo embeds and Discord views


