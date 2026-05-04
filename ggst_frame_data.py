import difflib
import os
import re

import discord
import pandas as pd


GGST_FRAME_DATA_FILE = "GGST Frame Data.ods"
GGST_FRAME_DATA_FILE_CANDIDATES = [
    GGST_FRAME_DATA_FILE,
    "ggst-framedata.ods",
    "GGST - Dustloop Frame Data.ods",
]
GGST_FRAME_DATA = {}
GGST_STATE_FRAME_DATA = {}
GGST_SUPPLEMENTAL_FRAME_DATA = {}
GGST_HITBOX_DATA = {}

GGST_CHARACTER_ALIASES = {
    "aba": "aba",
    "a.b.a": "aba",
    "a.b.a.": "aba",
    "anji": "anji",
    "anji mito": "anji",
    "asuka": "asuka",
    "asuka r": "asuka",
    "asuka r#": "asuka",
    "axl": "axl",
    "axl low": "axl",
    "baiken": "baiken",
    "bedman": "bedman",
    "bedman?": "bedman",
    "bridget": "bridget",
    "chipp": "chipp",
    "dizzy": "dizzy",
    "elphelt": "elphelt",
    "faust": "faust",
    "gio": "giovanna",
    "giovanna": "giovanna",
    "goldlewis": "goldlewis",
    "goldlewis dickinson": "goldlewis",
    "chaos": "h. chaos",
    "happy chaos": "h. chaos",
    "h chaos": "h. chaos",
    "h. chaos": "h. chaos",
    "ino": "i-no",
    "i-no": "i-no",
    "i no": "i-no",
    "jacko": "jack-o",
    "jack-o": "jack-o",
    "jack o": "jack-o",
    "jam": "jam",
    "johnny": "johnny",
    "ky": "ky",
    "ky kiske": "ky",
    "leo": "leo",
    "leo whitefang": "leo",
    "lucy": "lucy",
    "may": "may",
    "millia": "millia",
    "millia rage": "millia",
    "nago": "nagoriyuki",
    "nagoriyuki": "nagoriyuki",
    "pot": "potemkin",
    "potemkin": "potemkin",
    "ram": "ramlethal",
    "ramlethal": "ramlethal",
    "ramlethal valentine": "ramlethal",
    "sin": "sin",
    "sin kiske": "sin",
    "slayer": "slayer",
    "sol": "sol",
    "sol badguy": "sol",
    "test": "testament",
    "testament": "testament",
    "unika": "unika",
    "venom": "venom",
    "zato": "zato-1",
    "zato1": "zato-1",
    "zato-1": "zato-1",
    "zato 1": "zato-1",
}

GGST_MOVE_ALIASES = {
    "p": "5P",
    "k": "5K",
    "s": "f.S",
    "slash": "f.S",
    "fs": "f.S",
    "f s": "f.S",
    "f.s": "f.S",
    "far s": "f.S",
    "far slash": "f.S",
    "cs": "c.S",
    "c s": "c.S",
    "c.s": "c.S",
    "close s": "c.S",
    "close slash": "c.S",
    "h": "5H",
    "hs": "5H",
    "heavy": "5H",
    "heavy slash": "5H",
    "d": "5D",
    "dust": "5D",
    "2p": "2P",
    "2k": "2K",
    "2s": "2S",
    "2h": "2H",
    "2hs": "2H",
    "2d": "2D",
    "6p": "6P",
    "6k": "6K",
    "6s": "6S",
    "6h": "6H",
    "6hs": "6H",
    "jp": "j.P",
    "j p": "j.P",
    "j.p": "j.P",
    "jk": "j.K",
    "j k": "j.K",
    "j.k": "j.K",
    "js": "j.S",
    "j s": "j.S",
    "j.s": "j.S",
    "jh": "j.H",
    "j h": "j.H",
    "j.h": "j.H",
    "jhs": "j.H",
    "jd": "j.D",
    "j d": "j.D",
    "j.d": "j.D",
    "air throw": "4D or 6D (air)",
    "throw": "4D or 6D",
}

GGST_CHARACTER_MOVE_ALIASES = {
    "sol": {
        "svv": "623S",
        "hvv": "623H",
    },
    "h. chaos": {
        "h": "H",
    },
}

GGST_LOOKUP_WORDS = {
    "ggst",
    "guilty",
    "gear",
    "strive",
    "framedata",
    "frame",
    "frames",
    "data",
    "gif",
    "gifs",
    "hitbox",
    "hitboxes",
    "blood",
    "level",
    "levels",
    "bl",
    "br",
    "followup",
    "followups",
    "follow",
    "up",
    "item",
    "items",
    "spell",
    "spells",
    "install",
    "di",
}

NAGORIYUKI_BLOOD_STATE_SHEETS = {
    "NagoriyukiL2": ("blood_l2", "Blood Lv2"),
    "NagoriyukiL3": ("blood_l3", "Blood Lv3"),
    "NagoriyukiBR": ("blood_rage", "Blood Rage"),
}
GOLDLEWIS_SECURITY_STATE_SHEETS = {
    "GoldlewisL2": ("security_l2", "Security Lv2"),
    "GoldlewisL3": ("security_l3", "Security Lv3"),
}
GGST_CHARACTER_STATE_SHEETS = {
    "bedman": {
        "BedmanInstall": ("install", "Error 6E"),
    },
    "ky": {
        "KyDragon Install": ("dragon_install", "Dragon Install"),
    },
}
GGST_CHARACTER_SUPPLEMENTAL_SHEETS = {
    "asuka": {
        "AsukaSpells": "Spells",
    },
    "faust": {
        "FaustItems": "Items",
    },
}


def normalize_key(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def canonical_char_key(value):
    return str(value or "").strip().lower()


def display_char_name(char_key):
    for key in GGST_FRAME_DATA:
        if key == char_key:
            rows = GGST_FRAME_DATA.get(key) or []
            if rows:
                return str(rows[0].get("char_name") or key).strip()
    return str(char_key or "Unknown").title()


def resolve_character_key(text):
    raw = str(text or "").strip().lower()
    if not raw:
        return None
    if raw in GGST_FRAME_DATA:
        return raw
    if raw in GGST_CHARACTER_ALIASES:
        return GGST_CHARACTER_ALIASES[raw]
    normalized = normalize_key(raw)
    for alias, char_key in GGST_CHARACTER_ALIASES.items():
        if normalize_key(alias) == normalized:
            return char_key
    for char_key in GGST_FRAME_DATA:
        if normalize_key(char_key) == normalized:
            return char_key
    return None


def resolve_frame_data_file(filename=None):
    if filename:
        return filename if os.path.exists(filename) else None
    for candidate in GGST_FRAME_DATA_FILE_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return None


def load_frame_data(filename=None):
    global GGST_FRAME_DATA, GGST_STATE_FRAME_DATA, GGST_SUPPLEMENTAL_FRAME_DATA
    GGST_FRAME_DATA = {}
    GGST_STATE_FRAME_DATA = {}
    GGST_SUPPLEMENTAL_FRAME_DATA = {}
    filename = resolve_frame_data_file(filename)
    if not filename:
        print(f"[ggst] frame data file not found. Tried: {', '.join(GGST_FRAME_DATA_FILE_CANDIDATES)}", flush=True)
        return False

    xls = pd.ExcelFile(filename, engine="odf")
    loaded = 0
    for sheet_name in xls.sheet_names:
        if not sheet_name.endswith("Normal"):
            continue
        if sheet_name in {"IdealSheetNormal", "TemplateNormal"}:
            continue
        char_label = sheet_name[: -len("Normal")]
        char_key = canonical_char_key(char_label)
        df = pd.read_excel(xls, sheet_name=sheet_name).fillna("")
        rows = df.to_dict("records")
        clean_rows = []
        for row in rows:
            if not str(row.get("moveName", "")).strip() and not str(row.get("numCmd", "")).strip():
                continue
            row["char_key"] = char_key
            row["char_name"] = char_label
            clean_rows.append(row)
        if clean_rows:
            GGST_FRAME_DATA[char_key] = clean_rows
            GGST_CHARACTER_ALIASES.setdefault(char_key, char_key)
            GGST_CHARACTER_ALIASES.setdefault(char_label.lower(), char_key)
            loaded += 1

    for sheet_name, (state_key, state_label) in NAGORIYUKI_BLOOD_STATE_SHEETS.items():
        if sheet_name not in xls.sheet_names:
            continue
        df = pd.read_excel(xls, sheet_name=sheet_name).fillna("")
        state_rows = []
        for row in df.to_dict("records"):
            if not str(row.get("moveName", "")).strip() and not str(row.get("numCmd", "")).strip():
                continue
            row["char_key"] = "nagoriyuki"
            row["char_name"] = f"Nagoriyuki ({state_label})"
            row["state_key"] = state_key
            row["state_label"] = state_label
            state_rows.append(row)
        if state_rows:
            GGST_STATE_FRAME_DATA.setdefault("nagoriyuki", {})[state_key] = state_rows

    for sheet_name, (state_key, state_label) in GOLDLEWIS_SECURITY_STATE_SHEETS.items():
        if sheet_name not in xls.sheet_names:
            continue
        df = pd.read_excel(xls, sheet_name=sheet_name).fillna("")
        state_rows = []
        for row in df.to_dict("records"):
            if not str(row.get("moveName", "")).strip() and not str(row.get("numCmd", "")).strip():
                continue
            row["char_key"] = "goldlewis"
            row["char_name"] = f"Goldlewis ({state_label})"
            row["state_key"] = state_key
            row["state_label"] = state_label
            state_rows.append(row)
        if state_rows:
            GGST_STATE_FRAME_DATA.setdefault("goldlewis", {})[state_key] = state_rows

    for char_key, sheets in GGST_CHARACTER_STATE_SHEETS.items():
        for sheet_name, (state_key, state_label) in sheets.items():
            if sheet_name not in xls.sheet_names:
                continue
            df = pd.read_excel(xls, sheet_name=sheet_name).fillna("")
            state_rows = []
            base_name = display_char_name(char_key)
            for row in df.to_dict("records"):
                if not str(row.get("moveName", "")).strip() and not str(row.get("numCmd", "")).strip():
                    continue
                row["char_key"] = char_key
                row["char_name"] = f"{base_name} ({state_label})"
                row["state_key"] = state_key
                row["state_label"] = state_label
                state_rows.append(row)
            if state_rows:
                GGST_STATE_FRAME_DATA.setdefault(char_key, {})[state_key] = state_rows

    for char_key, sheets in GGST_CHARACTER_SUPPLEMENTAL_SHEETS.items():
        for sheet_name, sheet_label in sheets.items():
            if sheet_name not in xls.sheet_names:
                continue
            df = pd.read_excel(xls, sheet_name=sheet_name).fillna("")
            supplemental_rows = []
            base_name = display_char_name(char_key)
            for row in df.to_dict("records"):
                if not str(row.get("moveName", "")).strip() and not str(row.get("numCmd", "")).strip():
                    continue
                row["char_key"] = char_key
                row["char_name"] = f"{base_name} ({sheet_label})"
                row["state_key"] = normalize_key(sheet_label)
                row["state_label"] = sheet_label
                supplemental_rows.append(row)
            if supplemental_rows:
                GGST_SUPPLEMENTAL_FRAME_DATA.setdefault(char_key, []).extend(supplemental_rows)
    print(f"[ggst] Total characters loaded: {loaded}", flush=True)
    return bool(GGST_FRAME_DATA)


def normalize_move_query(query):
    text = str(query or "").lower().strip()
    text = re.sub(r"\b(?:ggst|guilty\s+gear|guilty|gear|strive)\b", " ", text)
    text = re.sub(r"\b(?:framedata|frame\s*data|frames?|data|gif|gifs|hitbox(?:es)?)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    compact = normalize_key(text)
    if text in GGST_MOVE_ALIASES:
        return GGST_MOVE_ALIASES[text]
    if compact in GGST_MOVE_ALIASES:
        return GGST_MOVE_ALIASES[compact]
    return text


def extract_nagoriyuki_blood_state(query):
    text = str(query or "").lower()
    state_key = None

    if re.search(r"\b(?:blood\s*rage|br)\b", text):
        state_key = "blood_rage"
    elif re.search(r"\b(?:blood\s*(?:level|lvl|lv)?\s*3|bl\s*3|l\s*3|lv\s*3|lvl\s*3|level\s*3)\b", text):
        state_key = "blood_l3"
    elif re.search(r"\b(?:blood\s*(?:level|lvl|lv)?\s*2|bl\s*2|l\s*2|lv\s*2|lvl\s*2|level\s*2)\b", text):
        state_key = "blood_l2"
    elif re.search(r"\b(?:blood\s*level|blood|bl)\b", text):
        state_key = "blood_l2"

    cleaned = text
    cleaned = re.sub(r"\b(?:blood\s*rage|br)\b", " ", cleaned)
    cleaned = re.sub(r"\b(?:blood\s*(?:level|lvl|lv)?\s*[23]|bl\s*[23]|l\s*[23]|lv\s*[23]|lvl\s*[23]|level\s*[23])\b", " ", cleaned)
    cleaned = re.sub(r"\b(?:blood\s*level|blood|bl)\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return state_key, cleaned


def extract_goldlewis_security_state(query):
    text = str(query or "").lower()
    state_key = None

    if re.search(r"\b(?:security\s*(?:level|lvl|lv)?\s*3|sec\s*3|sl\s*3|l\s*3|lv\s*3|lvl\s*3|level\s*3)\b", text):
        state_key = "security_l3"
    elif re.search(r"\b(?:security\s*(?:level|lvl|lv)?\s*2|sec\s*2|sl\s*2|l\s*2|lv\s*2|lvl\s*2|level\s*2)\b", text):
        state_key = "security_l2"

    cleaned = text
    cleaned = re.sub(r"\b(?:security\s*(?:level|lvl|lv)?\s*[23]|sec\s*[23]|sl\s*[23]|l\s*[23]|lv\s*[23]|lvl\s*[23]|level\s*[23])\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return state_key, cleaned


def extract_ky_dragon_install_state(query):
    text = str(query or "").lower()
    state_key = "dragon_install" if re.search(r"\b(?:dragon\s*install|di)\b", text) else None
    cleaned = re.sub(r"\b(?:dragon\s*install|di)\b", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return state_key, cleaned


def extract_bedman_install_state(query):
    text = str(query or "").lower()
    state_key = "install" if re.search(r"\b(?:install|error\s*6e|malfunction)\b", text) else None
    cleaned = re.sub(r"\b(?:install|error\s*6e|malfunction)\b", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return state_key, cleaned


def query_prefers_supplemental_rows(char_key, query):
    text = str(query or "").lower()
    if char_key == "asuka" and re.search(r"\b(?:spell|spells|test\s*case|mana|bookmark)\b", text):
        return True
    if char_key == "faust" and re.search(r"\b(?:item|items|bomb|banana|donut|afro|hammer|weight|horn|trumpet|meteor|mini\s*faust)\b", text):
        return True
    return False


def is_followup_row(row):
    if str(row.get("followUp", "")).strip().lower() in {"true", "1", "yes"}:
        return True
    if str(row.get("char_key", "")).strip().lower() == "h. chaos":
        move_name = str(row.get("moveName", "")).strip().lower()
        num_cmd = str(row.get("numCmd", "")).strip().lower()
        return (
            move_name in {"at the ready (fire)", "at the ready (cancel)", "steady aim (fire)", "steady aim (cancel)"}
            or "during steady aim" in num_cmd
        )
    return False


def is_universal_followup_row(row):
    move_name = str(row.get("moveName", "")).strip().lower()
    return move_name in {"counter blitz", "finishing blow"}


def strip_followup_terms(query):
    text = str(query or "").lower()
    text = re.sub(r"\b(?:follow\s*ups?|followups?|follow\s*up)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_move_token(value):
    text = str(value or "").lower().strip()
    text = text.replace(" ", "")
    text = text.replace("jump", "j")
    text = text.replace("air", "j")
    text = text.replace("hs", "h")
    text = text.replace(".", "")
    return re.sub(r"[^a-z0-9>~+/-]", "", text)


def expand_or_command_alternatives(value):
    text = str(value or "").strip()
    has_or = re.search(r"\bor\b", text, re.IGNORECASE)
    has_slash = "/" in text and not re.search(r"\d+/\d+", text)
    if not has_or and not has_slash:
        return []
    if has_or:
        parts = re.split(r"\bor\b", text, flags=re.IGNORECASE)
    else:
        parts = text.split("/")
    first_segment = parts[0].strip() if parts else ""
    alternatives = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        alternatives.append(part)
        if re.fullmatch(r"[PKSHDpkshd]", part) and re.search(r"\d+[PKSHDpkshd]$", first_segment):
            numeric_prefix = re.sub(r"[PKSHDpkshd]+$", "", first_segment)
            alternatives.append(f"{numeric_prefix}{part}")
    deduped = []
    seen = set()
    for alternative in alternatives:
        key = normalize_move_token(alternative)
        if key and key not in seen:
            deduped.append(alternative)
            seen.add(key)
    return deduped


def row_matches_move(row, move_query):
    raw_query = str(move_query or "").lower().strip()
    raw_query_norm = normalize_move_token(raw_query)
    query = normalize_move_query(move_query)
    query_norm = normalize_move_token(query)
    if not query_norm:
        return False
    values = [
        row.get("numCmd", ""),
        row.get("cmnName", ""),
        row.get("plnCmd", ""),
        row.get("moveName", ""),
        row.get("dustloopKey", ""),
    ]
    for value in values:
        value_text = str(value or "").lower().strip()
        if query.lower() == value_text:
            return True
        if query_norm == normalize_move_token(value_text):
            return True
        for alternative in expand_or_command_alternatives(value_text):
            alternative_norm = normalize_move_token(alternative)
            if query_norm == alternative_norm or raw_query_norm == alternative_norm:
                return True
    query_words = set(re.findall(r"[a-z0-9]+", query.lower())) - GGST_LOOKUP_WORDS
    descriptive_query_words = {
        word for word in query_words
        if len(word) >= 3 and not any(char.isdigit() for char in word)
    }
    numeric_variant_words = {word for word in query_words if word.isdigit()}
    if query_words and (descriptive_query_words or numeric_variant_words):
        move_words = set()
        for value in values:
            move_words.update(re.findall(r"[a-z0-9]+", str(value or "").lower()))
        if query_words.issubset(move_words):
            return True
        if not descriptive_query_words or query_words != descriptive_query_words:
            return False
        if all(
            any(difflib.SequenceMatcher(None, query_word, move_word).ratio() >= 0.74 for move_word in move_words)
            for query_word in descriptive_query_words
        ):
            return True
    return False


def find_fuzzy_character_in_text(text):
    words = re.findall(r"[a-z0-9]+", str(text or "").lower())
    if not words:
        return None
    best = None
    alias_items = sorted(GGST_CHARACTER_ALIASES.items(), key=lambda item: len(item[0]), reverse=True)
    for alias, char_key in alias_items:
        alias_words = re.findall(r"[a-z0-9]+", alias.lower())
        if not alias_words:
            continue
        span_size = len(alias_words)
        for index in range(0, len(words) - span_size + 1):
            candidate = " ".join(words[index:index + span_size])
            score = difflib.SequenceMatcher(None, normalize_key(candidate), normalize_key(alias)).ratio()
            if score < 0.84:
                continue
            if best is None or score > best[0]:
                best = (score, char_key, candidate)
    if best:
        return best[1], best[2]
    return None


def lookup_frame_data(character, move_input, state_key=None):
    char_key = resolve_character_key(character)
    if not char_key:
        return None
    query = GGST_CHARACTER_MOVE_ALIASES.get(char_key, {}).get(str(move_input or "").lower().strip())
    if not query:
        query = normalize_move_query(move_input)
    if char_key == "nagoriyuki" and state_key:
        rows = GGST_STATE_FRAME_DATA.get(char_key, {}).get(state_key, [])
        for row in rows:
            if row_matches_move(row, query):
                return row

    rows = GGST_FRAME_DATA.get(char_key, [])
    for row in rows:
        if row_matches_move(row, query):
            return row
    return None


def find_matching_rows(character, move_input, state_key=None):
    char_key = resolve_character_key(character)
    if not char_key:
        return []
    query = GGST_CHARACTER_MOVE_ALIASES.get(char_key, {}).get(str(move_input or "").lower().strip())
    if not query:
        query = normalize_move_query(move_input)
    if state_key:
        state_matches = []
        seen = set()
        for row in GGST_STATE_FRAME_DATA.get(char_key, {}).get(state_key, []):
            key = (row.get("char_name"), row.get("moveName"), row.get("numCmd"), row.get("state_key"))
            if key in seen:
                continue
            if row_matches_move(row, query):
                state_matches.append(row)
                seen.add(key)
        if state_matches:
            return state_matches

    supplemental_first = query_prefers_supplemental_rows(char_key, move_input)
    if supplemental_first:
        supplemental_matches = []
        seen_supplemental = set()
        for row in GGST_SUPPLEMENTAL_FRAME_DATA.get(char_key, []):
            key = (row.get("char_name"), row.get("moveName"), row.get("numCmd"), row.get("state_key"))
            if key in seen_supplemental:
                continue
            if row_matches_move(row, query):
                supplemental_matches.append(row)
                seen_supplemental.add(key)
        if supplemental_matches:
            return supplemental_matches

    rows_to_search = []
    rows_to_search.extend(GGST_FRAME_DATA.get(char_key, []))
    if not supplemental_first:
        rows_to_search.extend(GGST_SUPPLEMENTAL_FRAME_DATA.get(char_key, []))

    matches = []
    seen = set()
    for row in rows_to_search:
        key = (row.get("char_name"), row.get("moveName"), row.get("numCmd"), row.get("state_key"))
        if key in seen:
            continue
        if row_matches_move(row, query):
            matches.append(row)
            seen.add(key)
    return matches


def find_followup_rows(character, move_input):
    char_key = resolve_character_key(character)
    if not char_key:
        return []
    stripped_query = strip_followup_terms(move_input)
    query = GGST_CHARACTER_MOVE_ALIASES.get(char_key, {}).get(stripped_query)
    if not query:
        query = normalize_move_query(stripped_query)
    rows_to_search = [
        row for row in GGST_FRAME_DATA.get(char_key, [])
        if is_followup_row(row) and not is_universal_followup_row(row)
    ]
    if not query:
        return rows_to_search

    query_compact = normalize_key(query)
    if char_key == "h. chaos":
        at_ready_keys = {"236s", "236h", "attheready", "gun"}
        steady_aim_keys = {"214s", "steadyaim"}
        if query_compact in at_ready_keys:
            return [
                row for row in rows_to_search
                if str(row.get("moveName", "")).strip().lower().startswith("at the ready (")
            ]
        if query_compact in steady_aim_keys:
            return [
                row for row in rows_to_search
                if (
                    str(row.get("moveName", "")).strip().lower().startswith("steady aim (")
                    or "during steady aim" in str(row.get("numCmd", "")).strip().lower()
                )
            ]

    matches = []
    seen = set()
    for row in rows_to_search:
        key = (row.get("char_name"), row.get("moveName"), row.get("numCmd"), row.get("state_key"))
        if key in seen:
            continue
        row_cmd_compact = normalize_key(row.get("numCmd", ""))
        if row_cmd_compact.startswith(query_compact) or row_matches_move(row, query):
            matches.append(row)
            seen.add(key)
    return matches


def build_disambiguation_prompt(char_key, rows):
    char_name = display_char_name(char_key)
    lines = [f"Multiple GGST moves match {char_name}. Please specify one:"]
    for row in rows[:12]:
        state_label = clean_value(row.get("state_label"))
        state_text = f" [{state_label}]" if state_label else ""
        move_name = clean_value(row.get("moveName"), "Unknown")
        num_cmd = clean_value(row.get("numCmd"), "?")
        lines.append(f"- {move_name}{state_text}: `{num_cmd}`")
    return "\n".join(lines)


def build_followup_prompt(char_key, rows):
    char_name = display_char_name(char_key)
    lines = [f"**GGST Follow-up Options ({char_name})**"]
    lines.append("Follow-ups:")
    for row in rows[:12]:
        move_name = clean_value(row.get("moveName"), "Unknown")
        num_cmd = clean_value(row.get("numCmd"), "?")
        lines.append(f"- {move_name}: `{num_cmd}`")
    lines.append("Reply or make a new prompt with the exact follow-up.")
    return "\n".join(lines)


def find_characters_in_text(text):
    lowered = str(text or "").lower()
    matches = []
    aliases = sorted(GGST_CHARACTER_ALIASES.items(), key=lambda item: len(item[0]), reverse=True)
    for alias, char_key in aliases:
        pattern = rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])"
        match = re.search(pattern, lowered)
        if match:
            matches.append((char_key, match.start(), match.end(), alias))
    deduped = []
    seen = set()
    for item in sorted(matches, key=lambda x: x[1]):
        if item[0] in seen:
            continue
        seen.add(item[0])
        deduped.append(item)
    return deduped


def find_moves_in_text(text):
    lowered = str(text or "").lower()
    gif_query = bool(re.search(r"\b(?:gif|gifs|hitbox|hitboxes)\b", lowered))
    frame_query = bool(re.search(r"\b(?:framedata|frame\s*data|frames?|data)\b", lowered))
    game_query = bool(re.search(r"\b(?:ggst|guilty\s+gear|guilty|strive)\b", lowered))
    char_matches = find_characters_in_text(lowered)
    if not char_matches:
        fuzzy_char = find_fuzzy_character_in_text(lowered)
        if fuzzy_char:
            char_key, matched_text = fuzzy_char
            start = lowered.find(matched_text)
            end = start + len(matched_text) if start >= 0 else start
            char_matches = [(char_key, start, end, matched_text)]
    rows = []
    char_found = bool(char_matches)
    matched_char_key = char_matches[0][0] if char_matches else None
    for char_key, start, end, _alias in char_matches:
        if start >= 0 and end >= 0:
            move_text = (lowered[:start] + " " + lowered[end:]).strip()
        else:
            move_text = lowered
        state_key = None
        if char_key == "nagoriyuki":
            state_key, move_text = extract_nagoriyuki_blood_state(move_text)
        elif char_key == "goldlewis":
            state_key, move_text = extract_goldlewis_security_state(move_text)
        elif char_key == "ky":
            state_key, move_text = extract_ky_dragon_install_state(move_text)
        elif char_key == "bedman":
            state_key, move_text = extract_bedman_install_state(move_text)
        char_alias_text = re.sub(r"\b(?:framedata|frame\s*data|frames?|data|gif|gifs|hitbox(?:es)?)\b", " ", move_text)
        char_alias_text = re.sub(r"\s+", " ", char_alias_text).strip()
        char_move_alias = GGST_CHARACTER_MOVE_ALIASES.get(char_key, {}).get(char_alias_text)
        if char_move_alias:
            move_text = char_move_alias
        else:
            move_text = normalize_move_query(move_text)
            char_move_alias = GGST_CHARACTER_MOVE_ALIASES.get(char_key, {}).get(move_text)
            if char_move_alias:
                move_text = char_move_alias
        if not move_text:
            continue
        if re.search(r"\b(?:follow\s*ups?|followups?|follow\s*up)\b", move_text):
            followup_matches = find_followup_rows(char_key, move_text)
            if len(followup_matches) > 1:
                return {
                    "mode": "options",
                    "rows": followup_matches,
                    "data": build_followup_prompt(char_key, followup_matches),
                    "gif_query": gif_query,
                    "frame_query": frame_query,
                    "game_query": game_query,
                    "needs_disambiguation": True,
                    "followup_options": True,
                    "char_found": char_found,
                    "char_key": char_key,
                }
            if followup_matches:
                rows.append(followup_matches[0])
                break
        matches = find_matching_rows(char_key, move_text, state_key=state_key)
        if len(matches) > 1:
            return {
                "mode": "options",
                "rows": matches,
                "data": build_disambiguation_prompt(char_key, matches),
                "gif_query": gif_query,
                "frame_query": frame_query,
                "game_query": game_query,
                "needs_disambiguation": True,
            }
        if matches:
            rows.append(matches[0])
            break
    data = "\n\n".join(format_frame_data(row) for row in rows)
    return {
        "mode": "gif" if gif_query else "frame" if rows else "none",
        "rows": rows,
        "data": data,
        "gif_query": gif_query,
        "frame_query": frame_query,
        "game_query": game_query,
        "char_found": char_found,
        "char_key": matched_char_key,
        "explicit_move_attempt": bool(char_found and (frame_query or gif_query or game_query)),
        "missing_scrolls_query": bool(char_found and not rows and (frame_query or gif_query or game_query)),
    }


def clean_value(value, default=""):
    text = str(value if value is not None else "").replace("*", ",").strip()
    if text.lower() in {"", "nan", "none", "null", "-", "--"}:
        return default
    return text


def truncate_value(value, limit):
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def add_embed_field(embed, name, value, inline=True):
    value = clean_value(value)
    if not value:
        return
    embed.add_field(
        name=truncate_value(name, 256),
        value=truncate_value(value, 1024),
        inline=inline,
    )


def format_jsonish_list(value):
    text = clean_value(value)
    if not text:
        return ""
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text.strip("[]")
        parts = [part.strip().strip('"\'') for part in text.split(",")]
        return ", ".join(part for part in parts if part)
    return text


def format_frame_data(row):
    return (
        f"Move: {clean_value(row.get('moveName'))} ({clean_value(row.get('numCmd'))})\n"
        f"Startup: {clean_value(row.get('startup'), '-')}f | Active: {clean_value(row.get('active'), '-')}f | Recovery: {clean_value(row.get('recovery'), '-')}f\n"
        f"On Hit: {clean_value(row.get('onHit'), '-')} | On Block: {clean_value(row.get('onBlock'), '-')}\n"
        f"Damage: {clean_value(row.get('dmg'), '-')} | Guard: {clean_value(row.get('guardLevel'), '-')} | Attack Level: {clean_value(row.get('atkLvl'), '-')}\n"
        f"RISC Gain: {clean_value(row.get('riscGain'), '-')} | Proration: {clean_value(row.get('prorate'), '-')} | Knockdown Adv: {clean_value(row.get('kda'), '-')}\n"
        f"Notes: {format_jsonish_list(row.get('extraInfo'))}"
    )


def build_frame_embed(row):
    char_name = clean_value(row.get("char_name"), "Unknown")
    move_name = clean_value(row.get("moveName"), "Unknown")
    num_cmd = clean_value(row.get("numCmd"), "?")
    embed = discord.Embed(
        title=truncate_value(f"GGST - {char_name}", 256),
        description=truncate_value(f"{move_name} ({num_cmd})", 4096),
        colour=0x7A2BFF,
    )
    add_embed_field(embed, "Startup", row.get("startup"), inline=True)
    add_embed_field(embed, "Active", row.get("active"), inline=True)
    add_embed_field(embed, "Recovery", row.get("recovery"), inline=True)
    add_embed_field(embed, "Total", row.get("total"), inline=True)
    add_embed_field(embed, "On Hit", row.get("onHit"), inline=True)
    add_embed_field(embed, "On Block", row.get("onBlock"), inline=True)
    add_embed_field(embed, "Damage", row.get("dmg"), inline=True)
    add_embed_field(embed, "RISC Gain", row.get("riscGain"), inline=True)
    add_embed_field(embed, "Proration", row.get("prorate"), inline=True)
    add_embed_field(embed, "Knockdown Adv", row.get("kda"), inline=True)
    add_embed_field(embed, "Counter Hit Adv", row.get("chAdv"), inline=True)
    add_embed_field(embed, "Guard", row.get("guardLevel"), inline=True)
    add_embed_field(embed, "Attack Level", row.get("atkLvl"), inline=True)
    add_embed_field(embed, "Cancel", format_jsonish_list(row.get("xx")), inline=True)
    add_embed_field(embed, "Gatling", format_jsonish_list(row.get("gatling")), inline=False)
    add_embed_field(embed, "Move Type", row.get("moveType"), inline=True)
    add_embed_field(embed, "Notes", format_jsonish_list(row.get("extraInfo")), inline=False)
    return embed


def get_hitbox_links(row, limit=4):
    # Placeholder for future GGST hitbox image assets.
    # Expected future key shape: GGST_HITBOX_DATA[char_key][normalized_num_cmd] -> [paths_or_urls]
    char_key = str(row.get("char_key", "")).strip().lower()
    num_cmd_key = normalize_move_token(row.get("numCmd", ""))
    char_links = GGST_HITBOX_DATA.get(char_key, {})
    links = char_links.get(num_cmd_key, []) if isinstance(char_links, dict) else []
    return list(links or [])[:limit]


class GGSTHitboxButton(discord.ui.Button):
    def __init__(self, row):
        self.frame_row = row
        self.hitbox_links = get_hitbox_links(row)
        super().__init__(label="Show Hitbox", style=discord.ButtonStyle.primary, disabled=not self.hitbox_links)

    async def callback(self, interaction: discord.Interaction):
        if not self.hitbox_links:
            await interaction.response.send_message(
                "GGST hitbox images are not wired yet. The placeholder button is ready for future assets.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message("\n".join(self.hitbox_links[:4]))


class ReturnToMenuButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Return to Menu", style=discord.ButtonStyle.secondary, custom_id="ggst_frame_return_menu", row=1)

    async def callback(self, interaction: discord.Interaction):
        import menu_system
        await interaction.response.send_message(
            embed=menu_system._main_menu_embed(),
            view=menu_system.MainMenuView(interaction.user.id),
        )


class GGSTFrameDataView(discord.ui.View):
    def __init__(self, row, include_menu_button=True):
        super().__init__(timeout=3600)
        self.add_item(GGSTHitboxButton(row))
        if include_menu_button:
            self.add_item(ReturnToMenuButton())


async def send_frame_response(message, rows):
    if not rows:
        return False
    for row in rows[:4]:
        await message.channel.send(embed=build_frame_embed(row), view=GGSTFrameDataView(row))
    return True


async def send_hitbox_response(message, rows):
    if not rows:
        return False
    links = []
    for row in rows[:4]:
        links.extend(get_hitbox_links(row))
    if not links:
        await message.reply("GGST hitbox images are not added yet, but the frame-data lookup is wired.")
        return True
    await message.reply("\n".join(links[:4]))
    return True
