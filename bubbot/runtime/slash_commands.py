import re

import discord

from bubbot.utils.choice_utils import autocomplete_values, character_choices, move_choices
from bubbot.frame_data.sf6_character_stats import (
    build_character_stats_embed,
    build_slash_stats_query,
    sf6_stat_slash_autocomplete_values,
)
from bubbot.utils.slash_frame_flow import send_slash_frame_result, send_slash_stats_result


def register_slash_commands(tree, deps):
    """Register public slash commands and autocomplete handlers."""

    frame_data = deps["frame_data"]
    frame_stats = deps["frame_stats"]
    resolve_character_key = deps["resolve_character_key"]
    find_moves_in_text = deps["find_moves_in_text"]
    build_frame_embed = deps["build_frame_embed"]
    frame_output_module = deps["frame_output_module"]
    ggst_module = deps["ggst_module"]
    sfv_module = deps["sfv_module"]
    tuco_module = deps["tuco_module"]
    bbcf_module = deps["bbcf_module"]
    cotw_module = deps["cotw_module"]
    third_strike_module = deps["third_strike_module"]
    mk1_module = deps["mk1_module"]
    menu_system = deps["menu_system"]

    def slash_choices(values):
        return [discord.app_commands.Choice(name=str(value)[:100], value=str(value)[:100]) for value in values[:25]]

    def move_choice_label(row):
        move_name = str(row.get("moveName", "")).strip()
        num_cmd = str(row.get("numCmd", "")).strip()
        move_type = str(row.get("moveType", "")).strip().lower()
        label = f"{move_name} ({num_cmd})" if move_name and num_cmd else move_name or num_cmd
        if move_type and move_type not in {"normal", ""}:
            label = f"{label} [{move_type}]"
        return label

    def sf6_character_choice_values():
        return sorted(display for _char_key, display in character_choices({key: rows for key, rows in frame_data.items() if rows}))

    def ggst_character_choice_values():
        return sorted(display for _char_key, display in character_choices({key: rows for key, rows in ggst_module.GGST_FRAME_DATA.items() if rows}))


    def sfv_character_choice_values():
        return sorted(
            display
            for _char_key, display in character_choices(
                {key: rows for key, rows in sfv_module.SFV_FRAME_DATA.items() if rows},
                display_fn=lambda char_key, _rows: sfv_module.display_char_name(char_key),
            )
        )

    def tuco_character_choice_values():
        return sorted(display for _char_key, display in character_choices({key: rows for key, rows in tuco_module.TUCO_FRAME_DATA.items() if rows}))

    def bbcf_character_choice_values():
        return sorted(display for _char_key, display in character_choices({key: rows for key, rows in bbcf_module.BBCF_FRAME_DATA.items() if rows}))

    def cotw_character_choice_values():
        return sorted(display for _char_key, display in character_choices({key: rows for key, rows in cotw_module.COTW_FRAME_DATA.items() if rows}))

    def third_strike_character_choice_values():
        return sorted(display for _char_key, display in character_choices({key: rows for key, rows in third_strike_module.THIRD_STRIKE_FRAME_DATA.items() if rows}))

    def mk1_character_choice_values():
        return sorted(
            display
            for _char_key, display in character_choices(
                {key: rows for key, rows in mk1_module.MK1_FRAME_DATA.items() if rows},
                display_fn=lambda char_key, _rows: mk1_module.display_char_name(char_key),
            )
        )

    def sf6_move_choice_values(char_name):
        char_key = resolve_character_key(char_name)
        if not char_key:
            return []
        return [
            label
            for _row, label in move_choices(
                frame_data.get(char_key, []),
                label_fn=move_choice_label,
                key_fields=("moveName", "numCmd", "moveType"),
            )
            if label
        ]

    def sf6_char_state_choice_values(char_name):
        char_key = resolve_character_key(char_name)
        state_map = {
            "ryu": ["denjin"],
            "jamie": ["drink 1", "drink 2", "drink 3", "drink 4"],
            "lily": ["stocked"],
            "mai": ["stocked"],
            "juri": ["stocked"],
        }
        return state_map.get(char_key, [])

    def ggst_move_choice_values(char_name):
        char_key = ggst_module.resolve_character_key(char_name)
        if not char_key:
            return []
        rows = []
        rows.extend(ggst_module.GGST_FRAME_DATA.get(char_key, []))
        rows.extend(ggst_module.GGST_SUPPLEMENTAL_FRAME_DATA.get(char_key, []))
        for state_rows in ggst_module.GGST_STATE_FRAME_DATA.get(char_key, {}).values():
            rows.extend(state_rows)
        values = []
        seen = set()
        for _row, label in move_choices(rows, label_fn=move_choice_label, key_fields=("moveName", "numCmd", "moveType")):
            if label and label not in seen:
                seen.add(label)
                values.append(label)
        return values


    def sfv_move_choice_values(char_name):
        char_key = sfv_module.resolve_character_key(char_name)
        if not char_key:
            return []
        rows = list(sfv_module.SFV_FRAME_DATA.get(char_key, []) or [])
        for state_rows in (sfv_module.SFV_TRIGGER_FRAME_DATA.get(char_key, {}) or {}).values():
            rows.extend(state_rows)
        return [label for _row, label in move_choices(rows, label_fn=move_choice_label, key_fields=("moveName", "numCmd", "state_label")) if label]

    def tuco_move_choice_values(char_name):
        char_key = tuco_module.resolve_character_key(char_name)
        if not char_key:
            return []
        return [label for _row, label in move_choices(tuco_module.TUCO_FRAME_DATA.get(char_key, []), label_fn=move_choice_label, key_fields=("moveName", "numCmd")) if label]

    def bbcf_move_choice_values(char_name):
        char_key = bbcf_module.resolve_character_key(char_name)
        if not char_key:
            return []
        return [label for _row, label in move_choices(bbcf_module.BBCF_FRAME_DATA.get(char_key, []), label_fn=move_choice_label, key_fields=("moveName", "numCmd", "moveType")) if label]

    def cotw_move_choice_values(char_name):
        char_key = cotw_module.resolve_character_key(char_name)
        if not char_key:
            return []
        return [label for _row, label in move_choices(cotw_module.COTW_FRAME_DATA.get(char_key, []), label_fn=move_choice_label, key_fields=("moveName", "numCmd", "moveType")) if label]

    def third_strike_move_choice_values(char_name):
        char_key = third_strike_module.resolve_character_key(char_name)
        if not char_key:
            return []
        return [label for _row, label in move_choices(third_strike_module.THIRD_STRIKE_FRAME_DATA.get(char_key, []), label_fn=move_choice_label, key_fields=("moveName", "numCmd", "version", "moveType")) if label]

    def mk1_move_choice_values(char_name):
        char_key = mk1_module.resolve_character_key(char_name)
        if not char_key:
            return []
        return [label for _row, label in move_choices(mk1_module.MK1_FRAME_DATA.get(char_key, []), label_fn=move_choice_label, key_fields=("moveName", "numCmd", "moveType")) if label]

    def mk1_combo_character_choice_values():
        return sorted(display for _char_key, display in character_choices({key: rows for key, rows in mk1_module.MK1_COMBO_DATA.items() if rows}))

    def ggst_char_state_choice_values(char_name):
        char_key = ggst_module.resolve_character_key(char_name)
        if not char_key:
            return []
        values = []
        seen = set()
        for row_map in ggst_module.GGST_STATE_FRAME_DATA.get(char_key, {}).values():
            for row in row_map:
                for value in (str(row.get("state_label", "")).strip(), str(row.get("state_key", "")).strip()):
                    if value and value not in seen:
                        seen.add(value)
                        values.append(value)
        for row in ggst_module.GGST_SUPPLEMENTAL_FRAME_DATA.get(char_key, []):
            for value in (str(row.get("state_label", "")).strip(), str(row.get("state_key", "")).strip()):
                if value and value not in seen:
                    seen.add(value)
                    values.append(value)
        return values


    def sfv_char_state_choice_values(char_name):
        char_key = sfv_module.resolve_character_key(char_name)
        if not char_key:
            return []
        states = sfv_module.SFV_TRIGGER_FRAME_DATA.get(char_key, {}) or {}
        labels = []
        if "trigger1" in states:
            labels.append("vt1")
        if "trigger2" in states:
            labels.append("vt2")
        return labels

    def strip_autocomplete_label(value):
        text = str(value or "").strip()
        text = re.sub(r"\s+\[[^\]]+\]$", "", text).strip()
        match = re.match(r"^(.+)\s+\(([^()]*)\)$", text)
        if match:
            return match.group(2).strip() or match.group(1).strip()
        return text

    def selected_choice_row(move_name, choices):
        selected = str(move_name or "").strip()
        if not selected:
            return None
        selected_lower = selected.lower()
        selected_short = selected[:100].lower()
        for row, label in choices or []:
            label_text = str(label or "").strip()
            if not label_text:
                continue
            if selected_lower in {label_text.lower(), label_text[:100].lower()}:
                return row
            if selected_short == label_text[:100].lower():
                return row
        return None

    def sf6_selected_row(char_name, move_name):
        char_key = resolve_character_key(char_name)
        if not char_key:
            return None, None
        choices = move_choices(
            frame_data.get(char_key, []),
            label_fn=move_choice_label,
            key_fields=("moveName", "numCmd", "moveType"),
        )
        return selected_choice_row(move_name, choices), char_key

    async def send_sf6_slash_stats(interaction, char_name, stat=None):
        char_key = resolve_character_key(char_name)
        stats_row = (frame_stats or {}).get(char_key or "")
        query = build_slash_stats_query(char_name, stat)
        payload = find_moves_in_text(query)
        if not payload.get("stats_query"):
            await interaction.response.send_message(
                f"{char_name} with `{stat or 'stats'}` is not a valid character/stat combination for SF6."
            )
            return
        stat_keys = payload.get("stats_keys")
        if stat_keys is not None:
            stat_keys = tuple(stat_keys)
        await send_slash_stats_result(
            interaction,
            char_name=char_name,
            char_key=char_key,
            stats_row=stats_row,
            build_stats_embed_fn=build_character_stats_embed,
            stat_keys=stat_keys,
            game_label="SF6",
            query=query,
        )

    async def send_sf6_slash_frame(interaction, char_name, move_name, char_state=None):
        if char_state and char_state not in sf6_char_state_choice_values(char_name):
            await interaction.response.send_message(f"{char_name} does not use the `{char_state}` state for SF6 lookups.")
            return
        selected_row, selected_char_key = sf6_selected_row(char_name, move_name)
        query = f"{char_name} {char_state or ''} {strip_autocomplete_label(move_name)} framedata".strip().lower()
        await send_slash_frame_result(
            interaction,
            char_name=char_name,
            move_name=move_name,
            query=query,
            parse_fn=find_moves_in_text,
            embed_fn=build_frame_embed,
            game="sf6",
            game_label="SF6",
            selected_row=selected_row,
            selected_char_key=selected_char_key,
            prompt_predicate=lambda payload: "Special Strength Options" in str(payload.get("data", "") or "") or "Target Combo Options" in str(payload.get("data", "") or ""),
        )

    async def send_ggst_slash_frame(interaction, char_name, move_name, char_state=None):
        query = f"ggst {char_name} {char_state or ''} {strip_autocomplete_label(move_name)} framedata".strip().lower()
        await send_slash_frame_result(interaction, char_name=char_name, move_name=move_name, query=query, parse_fn=ggst_module.find_moves_in_text, embed_fn=ggst_module.build_frame_embed, game="ggst", game_label="GGST", disambiguation_predicate=lambda payload: payload.get("needs_disambiguation"))


    async def send_sfv_slash_frame(interaction, char_name, move_name, char_state=None):
        if not char_state:
            if re.search(r"\[\s*v-?trigger\s*1\s*\]", str(move_name or ""), re.IGNORECASE):
                char_state = "vt1"
            elif re.search(r"\[\s*v-?trigger\s*2\s*\]", str(move_name or ""), re.IGNORECASE):
                char_state = "vt2"
        query = f"sfv {char_name} {char_state or ''} {strip_autocomplete_label(move_name)} framedata".strip().lower()
        await send_slash_frame_result(interaction, char_name=char_name, move_name=move_name, query=query, parse_fn=sfv_module.find_moves_in_text, embed_fn=sfv_module.build_frame_embed, game="sfv", game_label="SFV", disambiguation_predicate=lambda payload: payload.get("needs_disambiguation"))


    async def send_tuco_slash_frame(interaction, char_name, move_name):
        query = f"2xko {char_name} {strip_autocomplete_label(move_name)} framedata".strip().lower()
        await send_slash_frame_result(interaction, char_name=char_name, move_name=move_name, query=query, parse_fn=tuco_module.find_moves_in_text, embed_fn=tuco_module.build_frame_embed, game="tuco", game_label="2XKO", disambiguation_predicate=lambda payload: payload.get("needs_disambiguation"))

    async def send_bbcf_slash_frame(interaction, char_name, move_name):
        query = f"bbcf {char_name} {strip_autocomplete_label(move_name)} framedata".strip().lower()
        await send_slash_frame_result(interaction, char_name=char_name, move_name=move_name, query=query, parse_fn=bbcf_module.find_moves_in_text, embed_fn=bbcf_module.build_frame_embed, game="bbcf", game_label="BBCF", disambiguation_predicate=lambda payload: payload.get("needs_disambiguation"))

    async def send_cotw_slash_frame(interaction, char_name, move_name):
        query = f"cotw {char_name} {strip_autocomplete_label(move_name)} framedata".strip().lower()
        await send_slash_frame_result(
            interaction,
            char_name=char_name,
            move_name=move_name,
            query=query,
            parse_fn=cotw_module.find_moves_in_text,
            embed_fn=cotw_module.build_frame_embed,
            game="cotw",
            game_label="COTW",
            disambiguation_predicate=lambda payload: payload.get("needs_disambiguation"),
        )

    async def send_third_strike_slash_frame(interaction, char_name, move_name):
        query = f"3s {char_name} {strip_autocomplete_label(move_name)} framedata".strip().lower()
        await send_slash_frame_result(interaction, char_name=char_name, move_name=move_name, query=query, parse_fn=third_strike_module.find_moves_in_text, embed_fn=third_strike_module.build_frame_embed, game="third_strike", game_label="Third Strike", disambiguation_predicate=lambda payload: payload.get("needs_disambiguation"))

    async def send_mk1_slash_frame(interaction, char_name, move_name):
        query = f"mk1 {char_name} {strip_autocomplete_label(move_name)} framedata".strip().lower()
        await send_slash_frame_result(interaction, char_name=char_name, move_name=move_name, query=query, parse_fn=mk1_module.find_moves_in_text, embed_fn=mk1_module.build_frame_embed, game="mk1", game_label="MK1", disambiguation_predicate=lambda payload: payload.get("needs_disambiguation"))

    async def send_mk1_slash_combos(interaction, char_name, difficulty=None, position=None):
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
        await interaction.response.send_message(embed=menu_system._main_menu_embed(), view=menu_system.MainMenuView(interaction.user.id))

    @tree.command(name="readme", description="Show a quick guide to Bub's features")
    async def readme_slash_command(interaction: discord.Interaction):
        await interaction.response.send_message(embed=menu_system.build_readme_embed())

    @tree.command(name="ggst")
    @discord.app_commands.describe(char_name="The characters name", move_name="The move name", char_state="Optional char specific states like Installs.")
    async def ggst(interaction: discord.Interaction, char_name: str, move_name: str, char_state: str = None):
        return await send_ggst_slash_frame(interaction, char_name, move_name, char_state)

    @tree.command(name="sfv")
    @discord.app_commands.describe(char_name="The character name", move_name="The move name or input", char_state="Optional V-Trigger state: vt1 or vt2")
    async def sfv(interaction: discord.Interaction, char_name: str, move_name: str, char_state: str = None):
        return await send_sfv_slash_frame(interaction, char_name, move_name, char_state)

    @tree.command(name="2xko")
    @discord.app_commands.describe(char_name="The champion name", move_name="The move name or input")
    async def tuco(interaction: discord.Interaction, char_name: str, move_name: str):
        return await send_tuco_slash_frame(interaction, char_name, move_name)

    @tree.command(name="bbcf")
    @discord.app_commands.describe(char_name="The character name", move_name="The move name or input")
    async def bbcf(interaction: discord.Interaction, char_name: str, move_name: str):
        return await send_bbcf_slash_frame(interaction, char_name, move_name)

    @tree.command(name="cotw")
    @discord.app_commands.describe(char_name="The character name", move_name="The move name or input")
    async def cotw(interaction: discord.Interaction, char_name: str, move_name: str):
        return await send_cotw_slash_frame(interaction, char_name, move_name)

    @tree.command(name="third-strike")
    @discord.app_commands.describe(char_name="The character name", move_name="The move name or input")
    async def third_strike(interaction: discord.Interaction, char_name: str, move_name: str):
        return await send_third_strike_slash_frame(interaction, char_name, move_name)

    @tree.command(name="mk1")
    @discord.app_commands.describe(char_name="The character or kameo name", move_name="The move name or input")
    async def mk1(interaction: discord.Interaction, char_name: str, move_name: str):
        return await send_mk1_slash_frame(interaction, char_name, move_name)

    @tree.command(name="mk1-combos")
    @discord.app_commands.describe(char_name="The character name", difficulty="Optional difficulty filter: easy, medium, or hard", position="Optional position filter: midscreen or corner")
    async def mk1_combos(interaction: discord.Interaction, char_name: str, difficulty: str = None, position: str = None):
        return await send_mk1_slash_combos(interaction, char_name, difficulty, position)

    @tree.command(name="sf6")
    @discord.app_commands.describe(char_name="The characters name", move_name="The move name", char_state="Optional char specific states like Installs.")
    async def sf6(interaction: discord.Interaction, char_name: str, move_name: str, char_state: str = None):
        return await send_sf6_slash_frame(interaction, char_name, move_name, char_state)

    @tree.command(name="sf6-stats", description="Show SF6 character stats (dash, jump, health, throw, drive rush, etc.)")
    @discord.app_commands.describe(
        char_name="The character name",
        stat="Optional stat filter (e.g. All stats, 66 — Forward dash, Health, Drive rush (dr))",
    )
    async def sf6_stats(interaction: discord.Interaction, char_name: str, stat: str = None):
        return await send_sf6_slash_stats(interaction, char_name, stat)

    @sf6_stats.autocomplete("char_name")
    async def sf6_stats_char_autocomplete(interaction: discord.Interaction, current: str):
        return slash_choices(autocomplete_values(current, sf6_character_choice_values()))

    @sf6_stats.autocomplete("stat")
    async def sf6_stats_stat_autocomplete(interaction: discord.Interaction, current: str):
        return slash_choices(autocomplete_values(current, sf6_stat_slash_autocomplete_values()))

    @sf6.autocomplete("char_state")
    async def sf6_char_state_autocomplete(interaction: discord.Interaction, current: str):
        if not interaction.namespace.char_name:
            return slash_choices([])
        return slash_choices(autocomplete_values(current, sf6_char_state_choice_values(interaction.namespace.char_name)))

    @sf6.autocomplete("char_name")
    async def sf6_char_autocomplete(interaction: discord.Interaction, current: str):
        return slash_choices(autocomplete_values(current, sf6_character_choice_values()))

    @sf6.autocomplete("move_name")
    async def sf6_move_autocomplete(interaction: discord.Interaction, current: str):
        if not interaction.namespace.char_name:
            return slash_choices([])
        return slash_choices(autocomplete_values(current, sf6_move_choice_values(interaction.namespace.char_name)))

    @ggst.autocomplete("char_name")
    async def ggst_char_autocomplete(interaction: discord.Interaction, current: str):
        return slash_choices(autocomplete_values(current, ggst_character_choice_values()))

    @ggst.autocomplete("char_state")
    async def ggst_char_state_autocomplete(interaction: discord.Interaction, current: str):
        if not interaction.namespace.char_name:
            return slash_choices([])
        return slash_choices(autocomplete_values(current, ggst_char_state_choice_values(interaction.namespace.char_name)))

    @ggst.autocomplete("move_name")
    async def ggst_move_autocomplete(interaction: discord.Interaction, current: str):
        if not interaction.namespace.char_name:
            return slash_choices([])
        return slash_choices(autocomplete_values(current, ggst_move_choice_values(interaction.namespace.char_name)))

    @sfv.autocomplete("char_name")
    async def sfv_char_autocomplete(interaction: discord.Interaction, current: str):
        return slash_choices(autocomplete_values(current, sfv_character_choice_values()))

    @sfv.autocomplete("char_state")
    async def sfv_char_state_autocomplete(interaction: discord.Interaction, current: str):
        if not interaction.namespace.char_name:
            return slash_choices([])
        return slash_choices(autocomplete_values(current, sfv_char_state_choice_values(interaction.namespace.char_name)))

    @sfv.autocomplete("move_name")
    async def sfv_move_autocomplete(interaction: discord.Interaction, current: str):
        if not interaction.namespace.char_name:
            return slash_choices([])
        return slash_choices(autocomplete_values(current, sfv_move_choice_values(interaction.namespace.char_name)))

    @tuco.autocomplete("char_name")
    async def tuco_char_autocomplete(interaction: discord.Interaction, current: str):
        return slash_choices(autocomplete_values(current, tuco_character_choice_values()))

    @tuco.autocomplete("move_name")
    async def tuco_move_autocomplete(interaction: discord.Interaction, current: str):
        if not interaction.namespace.char_name:
            return slash_choices([])
        return slash_choices(autocomplete_values(current, tuco_move_choice_values(interaction.namespace.char_name)))

    @bbcf.autocomplete("char_name")
    async def bbcf_char_autocomplete(interaction: discord.Interaction, current: str):
        return slash_choices(autocomplete_values(current, bbcf_character_choice_values()))

    @bbcf.autocomplete("move_name")
    async def bbcf_move_autocomplete(interaction: discord.Interaction, current: str):
        if not interaction.namespace.char_name:
            return slash_choices([])
        return slash_choices(autocomplete_values(current, bbcf_move_choice_values(interaction.namespace.char_name)))

    @cotw.autocomplete("char_name")
    async def cotw_char_autocomplete(interaction: discord.Interaction, current: str):
        return slash_choices(autocomplete_values(current, cotw_character_choice_values()))

    @cotw.autocomplete("move_name")
    async def cotw_move_autocomplete(interaction: discord.Interaction, current: str):
        if not interaction.namespace.char_name:
            return slash_choices([])
        return slash_choices(autocomplete_values(current, cotw_move_choice_values(interaction.namespace.char_name)))

    @third_strike.autocomplete("char_name")
    async def third_strike_char_autocomplete(interaction: discord.Interaction, current: str):
        return slash_choices(autocomplete_values(current, third_strike_character_choice_values()))

    @third_strike.autocomplete("move_name")
    async def third_strike_move_autocomplete(interaction: discord.Interaction, current: str):
        if not interaction.namespace.char_name:
            return slash_choices([])
        return slash_choices(autocomplete_values(current, third_strike_move_choice_values(interaction.namespace.char_name)))

    @mk1.autocomplete("char_name")
    async def mk1_char_autocomplete(interaction: discord.Interaction, current: str):
        return slash_choices(autocomplete_values(current, mk1_character_choice_values()))

    @mk1.autocomplete("move_name")
    async def mk1_move_autocomplete(interaction: discord.Interaction, current: str):
        if not interaction.namespace.char_name:
            return slash_choices([])
        return slash_choices(autocomplete_values(current, mk1_move_choice_values(interaction.namespace.char_name)))

    @mk1_combos.autocomplete("char_name")
    async def mk1_combo_char_autocomplete(interaction: discord.Interaction, current: str):
        return slash_choices(autocomplete_values(current, mk1_combo_character_choice_values()))

    @mk1_combos.autocomplete("difficulty")
    async def mk1_combo_difficulty_autocomplete(interaction: discord.Interaction, current: str):
        return slash_choices(autocomplete_values(current, ["easy", "medium", "hard"]))

    @mk1_combos.autocomplete("position")
    async def mk1_combo_position_autocomplete(interaction: discord.Interaction, current: str):
        return slash_choices(autocomplete_values(current, ["midscreen", "corner"]))
