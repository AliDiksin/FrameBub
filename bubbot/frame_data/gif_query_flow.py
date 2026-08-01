"""Query-driven GIF resolution and frame-row GIF flow."""

DISCORD_ATTACHMENT_LIMIT = 10


def configure(**deps):
    globals().update(deps)
def lookup_hitbox_gif_links_from_query(char_key, move_query, limit=DISCORD_ATTACHMENT_LIMIT):
    gif_rows = HITBOX_GIF_DATA.get(char_key, [])
    if not gif_rows:
        return []

    query_raw = resolve_hitbox_gif_query_alias(char_key, move_query)
    if not query_raw:
        return []

    query_num_cmd = normalize_num_cmd_token(query_raw)
    query_name_norm = normalize_move_name_for_gif_text(query_raw)
    query_tokens = set(query_name_norm.split())
    query_tokens.update(move_name_match_tokens(query_raw, query_num_cmd))
    if query_num_cmd:
        query_tokens.add(query_num_cmd)

    gif_candidates = []
    for gif_row in gif_rows:
        move_link = str(gif_row.get("moveLink", "")).strip()
        if not move_link:
            continue

        gif_num_cmd_raw = str(gif_row.get("numCmd", "")).lower()
        gif_num_cmd = normalize_num_cmd_token(gif_num_cmd_raw)
        gif_name_norm = normalize_move_name_for_gif_text(gif_row.get("moveName", ""))
        gif_tokens = move_name_match_tokens(gif_row.get("moveName", ""), gif_row.get("numCmd", ""))
        if gif_num_cmd:
            gif_tokens.add(gif_num_cmd)

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
        return []

    query_suffix = extract_button_suffix(query_num_cmd)
    query_wants_air = bool({"air", "aerial"} & query_tokens)
    query_wants_jump = "jump" in query_tokens
    query_wants_denjin = bool({"denjin", "charged", "hold", "held"} & query_tokens)
    query_wants_stocked = any(text_mentions_stocked_variant(token) for token in query_tokens)

    def apply_query_context_filters(items):
        filtered = list(items)

        token_context_filters = [
            "dash",
            "forward",
            "backward",
            "drive",
            "rush",
            "impact",
            "reversal",
            "stand",
            "crouch",
        ]
        for token in token_context_filters:
            if token in query_tokens:
                token_matches = [item for item in filtered if token in item["tokens"]]
                if token_matches:
                    filtered = token_matches

        if query_wants_air:
            air_matches = [item for item in filtered if item["is_air"]]
            if air_matches:
                filtered = air_matches

        if query_wants_jump:
            jump_matches = [item for item in filtered if item["is_jump"]]
            if jump_matches:
                filtered = jump_matches

        if query_wants_denjin:
            denjin_matches = [item for item in filtered if item["is_denjin"]]
            if denjin_matches:
                filtered = denjin_matches

        stocked_matches = [item for item in filtered if item["is_stocked"] == query_wants_stocked]
        if stocked_matches:
            filtered = stocked_matches
        elif filtered:
            return []

        if query_suffix:
            suffix_matches = [item for item in filtered if item["suffix"] == query_suffix]
            if suffix_matches:
                filtered = suffix_matches

        return filtered

    def unique_links(items):
        resolved_links = []
        seen = set()
        for item in items:
            move_link = item["link"]
            if move_link in seen:
                continue
            seen.add(move_link)
            resolved_links.append(move_link)
            if len(resolved_links) >= limit:
                break
        return resolved_links

    if query_num_cmd:
        exact_num_cmd = [
            item for item in gif_candidates
            if item["num_cmd"] and item["num_cmd"] == query_num_cmd
        ]
        if exact_num_cmd:
            links = unique_links(apply_query_context_filters(exact_num_cmd))
            if links:
                return links

        partial_num_cmd = [
            item for item in gif_candidates
            if item["num_cmd"] and (
                query_num_cmd in item["num_cmd"]
                or item["num_cmd"] in query_num_cmd
            )
        ]
        if partial_num_cmd:
            links = unique_links(apply_query_context_filters(partial_num_cmd))
            if links:
                return links

    exact_name_matches = [
        item for item in gif_candidates
        if query_name_norm and item["name_norm"] == query_name_norm
    ]
    if exact_name_matches:
        links = unique_links(apply_query_context_filters(exact_name_matches))
        if links:
            return links

    contains_name_matches = [
        item for item in gif_candidates
        if query_name_norm and (
            query_name_norm in item["name_norm"]
            or item["name_norm"] in query_name_norm
        )
    ]
    if contains_name_matches:
        links = unique_links(apply_query_context_filters(contains_name_matches))
        if links:
            return links

    token_overlap_matches = [
        item for item in gif_candidates
        if query_tokens and (query_tokens & item["tokens"])
    ]
    if token_overlap_matches:
        links = unique_links(apply_query_context_filters(token_overlap_matches))
        if links:
            return links

    return []


def collect_hitbox_gif_links_from_text(text, frame_rows=None, limit=DISCORD_ATTACHMENT_LIMIT, prefer_frame_rows=False):
    links = []
    seen = set()
    has_frame_rows = bool(frame_rows)

    text_lower = strip_discord_mentions(text).lower()
    normalized_query = normalize_move_name_for_gif_text(text_lower)
    normalized_tokens = set(normalized_query.split())
    normalized_num_cmd = normalize_num_cmd_token(text_lower)
    query_has_strength_preference = bool(
        normalized_tokens & {"l", "m", "h", "od"}
        or normalized_num_cmd.endswith(("lp", "mp", "hp", "lk", "mk", "hk", "pp", "kk"))
    )

    query_prefers_text_match = bool(
        normalized_tokens & {
            "drive", "impact", "rush", "reversal",
            "dash", "forward", "backward",
            "air", "aerial",
            "stand", "standing", "crouch", "crouching", "idle",
        }
        or "hphk" in normalized_num_cmd
    )

    char_candidates = []
    for row in frame_rows or []:
        row_char = str(row.get("char_name", "")).strip()
        char_key = resolve_character_key(row_char)
        if char_key and char_key not in char_candidates:
            char_candidates.append(char_key)

    for char_key in find_characters_in_text(text):
        if char_key not in char_candidates:
            char_candidates.append(char_key)

    def frame_rows_require_query_first(rows):
        unique_rows = iter_unique_frame_rows(rows or [])
        if len(unique_rows) != 1:
            return False
        row = unique_rows[0]
        row_char = resolve_character_key(str(row.get("char_name", "")).strip())
        move_name_norm = normalize_move_name_for_gif_text(row.get("moveName", ""))
        if row_char == "dhalsim":
            return move_name_norm in {"yoga fire", "yoga arch", "yoga comet air"}
        if row_char == "alex":
            row_num_cmd_norm = normalize_num_cmd_token(row.get("numCmd", ""))
            return row_num_cmd_norm.startswith("2pp>")
        return False

    def add_frame_row_links():
        for row in frame_rows or []:
            row_links = get_frame_row_gif_links(row, limit=limit)
            for move_link in row_links:
                if not move_link or move_link in seen:
                    continue
                seen.add(move_link)
                links.append(move_link)
                if len(links) >= limit:
                    return True
        return False

    def add_query_links():
        for char_key in char_candidates:
            move_query = extract_gif_move_query_text(text, char_key)
            if not move_query:
                continue

            raw_move_query = move_query
            move_query = resolve_hitbox_gif_query_alias(char_key, move_query)

            # Keep gif-mode behavior aligned with framedata parsing. If the
            # normalized query would trigger a special-strength prompt instead
            # of resolving to a concrete row, do not guess a gif from fuzzy
            # token overlap unless the gif alias map already resolved the
            # request to a concrete gif query.
            prompt_probe = find_moves_in_text(f"{char_key} {raw_move_query} framedata")
            prompt_probe_data = str(prompt_probe.get("data", "") or "")
            if (
                move_query == raw_move_query
                and (
                    "Special Strength Options" in prompt_probe_data
                    or "Target Combo Options" in prompt_probe_data
                )
                and not prompt_probe.get("rows")
            ):
                continue

            query_links = lookup_hitbox_gif_links_from_query(char_key, move_query, limit=limit)
            for move_link in query_links:
                if move_link in seen:
                    continue
                seen.add(move_link)
                links.append(move_link)
                if len(links) >= limit:
                    return True

            if query_links:
                continue

            resolved_row = lookup_frame_data(char_key, move_query)
            if resolved_row:
                move_link = lookup_hitbox_gif_link(resolved_row)
                if move_link and move_link not in seen:
                    seen.add(move_link)
                    links.append(move_link)
                    if len(links) >= limit:
                        return True
        return False

    if has_frame_rows:
        if prefer_frame_rows:
            add_frame_row_links()
            if links:
                return links
            add_query_links()
            return links

        if len(frame_rows or []) > 1:
            add_query_links()
            if links:
                return links
            add_frame_row_links()
            return links

        if frame_rows_require_query_first(frame_rows):
            add_query_links()
            if links:
                return links

        add_frame_row_links()
        if links:
            return links
        add_query_links()
        return links

    if query_prefers_text_match:
        if add_query_links():
            return links
        add_frame_row_links()
        return links

    if add_frame_row_links():
        return links
    return links


def get_frame_row_gif_links(row, limit=DISCORD_ATTACHMENT_LIMIT):
    if not isinstance(row, dict):
        return []

    links = []

    row_char = str(row.get("char_name", "")).strip()
    char_key = resolve_character_key(row_char)
    if not char_key:
        return []

    row_move_name_norm = normalize_move_name_for_gif_text(row.get("moveName", ""))
    generic_dhalsim_family_queries = {
        "yoga fire": "yoga fire",
        "yoga arch": "yoga arch",
        "yoga comet air": "yoga comet",
    }
    if char_key == "dhalsim":
        for family_name, query_name in generic_dhalsim_family_queries.items():
            if row_move_name_norm == family_name:
                return lookup_hitbox_gif_links_from_query(char_key, query_name, limit=limit)

    row_num_cmd_norm = normalize_num_cmd_token(row.get("numCmd", ""))

    image_fallback = get_sf6_move_image_gif_fallback(row)
    if image_fallback:
        return [image_fallback]

    if char_key == "alex" and row_num_cmd_norm.startswith("2pp>"):
        alex_query_links = lookup_hitbox_gif_links_from_query(
            char_key,
            row_move_name_norm,
            limit=limit,
        )
        if alex_query_links:
            return alex_query_links

    prefer_query_resolution = bool(
        (char_key == "cammy" and row_num_cmd_norm.startswith(("236p>", "236pp>")))
        or (char_key == "rashid" and "(lvl" in str(row.get("moveName", "")).lower())
    )

    candidate_queries = []

    def add_query_variant(raw_value):
        query = str(raw_value or "").strip()
        if not query:
            return
        stripped_drink_query = re.sub(r"\s*\(drink[^)]*\)", "", query, flags=re.IGNORECASE).strip()
        stripped_drink_query = re.sub(r"\s+", " ", stripped_drink_query).strip()
        if stripped_drink_query and stripped_drink_query not in candidate_queries:
            candidate_queries.append(stripped_drink_query)
        if stripped_drink_query == query and query not in candidate_queries:
            candidate_queries.append(query)

    for value in (row.get("moveName", ""), row.get("cmnName", ""), row.get("numCmd", "")):
        add_query_variant(value)

    direct_link = lookup_hitbox_gif_link(row)
    if direct_link and not prefer_query_resolution:
        return [direct_link]
    first_query_links = []
    for query in candidate_queries:
        query_links = lookup_hitbox_gif_links_from_query(char_key, query, limit=limit)
        query_links_deduped = []
        local_seen = set()
        for move_link in query_links:
            if move_link in local_seen:
                continue
            local_seen.add(move_link)
            query_links_deduped.append(move_link)
            if len(query_links_deduped) >= limit:
                break
        if not query_links_deduped:
            continue
        first_query_links = query_links_deduped
        if not direct_link or direct_link not in query_links_deduped:
            return query_links_deduped[:limit]
        return [direct_link]

    if direct_link:
        return [direct_link]

    for move_link in first_query_links:
        if move_link in links:
            continue
        links.append(move_link)
        if len(links) >= limit:
            return links

    return links
