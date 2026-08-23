"""Property-only frame-data replies and comparison controls."""
# Property replies reuse row selection but intentionally avoid rendering full frame-data embeds.

import re

import discord

import bubbot.features.menu_system as menu_system

_FRAME_MODULES = {}
_record_frame_data_ids = lambda ids, **kwargs: None
iter_unique_frame_rows = None
format_range_only_reply = None
truncate_message = lambda text, limit=1800: text if len(text) <= limit else text[: limit - 3] + "..."


def configure(**deps):
    globals().update(deps)
PROPERTY_VALUE_ALIASES = [
    ("startup", "Startup", ("startup",), r"\b(?:start\s*up|startup|how\s+fast|how\s+quick|speed\s+of)\b"),
    ("active", "Active", ("active",), r"\bactive(?:\s+frames?)?\b"),
    ("recovery", "Recovery", ("recovery",), r"\brecovery\b"),
    ("total", "Total", ("total",), r"\btotal(?:\s+frames?)?\b"),
    ("on_hit", "On Hit", ("onHit", "onODR"), r"\bon\s+hit\b"),
    ("on_block", "On Block", ("onBlock",), r"\bon\s+block\b|\bplus\s+on\s+block\b|\bminus\s+on\s+block\b"),
    ("flawless_block", "Flawless Block", ("flawlessBlock",), r"\bflawless\s+block\b"),
    ("damage", "Damage", ("dmg", "damage"), r"\b(?:damage|dmg)\b"),
    ("block_damage", "Block Damage", ("blockDamage",), r"\bblock\s+damage\b"),
    ("rev_damage", "REV Damage", ("revDamage",), r"\brev\s+damage\b"),
    ("guard_damage", "Guard Damage", ("guardDamage",), r"\bguard\s+damage\b"),
    ("guard", "Guard", ("guardLevel", "guard", "atkLvl"), r"\bguard\b"),
    ("attack_level", "Attack Level", ("atkLvl", "level"), r"\b(?:attack\s+level|atk\s*lvl|atk\s*level)\b"),
    ("cancel", "Cancel", ("cancel", "xx"), r"\bcancel(?:l?able)?\b"),
    ("gatling", "Gatling", ("gatling",), r"\bgatling\b"),
    ("invuln", "Invuln", ("invuln", "invul"), r"\binvuln(?:erability)?\b|\binvul\b"),
    ("attribute", "Attribute", ("attribute",), r"\battribute\b"),
    ("range", "Range", ("atkRange", "range"), r"\b(?:range|length)\b"),
    ("hitconfirm", "Hit Confirm Window", ("hcWinSpCa", "hcWinTc", "hcWinNotes"), r"\bhit\s*-?\s*confirm\b|\bhitconfirm\b|\bhc\b|\bconfirm\s+(?:window|timing)\b|\bconfirmable\b"),
    ("super_gain", "Super Gain", ("SelfSoH", "SelfSoB"), r"\bsuper\s*gain\b|\bsuper\s*meter\s*gain\b|\bsuper\s*build\b|\bsa\s*gain\b"),
    ("meter_gain", "Meter Gain", ("meterGain",), r"\bmeter\s*gain\b"),
    ("chip_damage", "Chip Damage", ("chp",), r"\bchip\s+damage\b"),
    ("drive_damage", "Drive Damage", ("DDoH", "DDoB"), r"\bdrive\s+(?:chip|dmg|damage)\b"),
    ("stun", "Stun", ("hitstun", "blockstun", "stun"), r"\bhitstun\b|\bblockstun\b|\bstun\b"),
    ("risc_gain", "RISC Gain", ("riscGain",), r"\brisc\s*gain\b|\brisc\b"),
    ("proration", "Proration", ("prorate",), r"\bproration\b|\bprorate\b"),
    ("knockdown_adv", "Knockdown Adv", ("kda",), r"\bknockdown\s+adv(?:antage)?\b|\bkda\b"),
    ("punish_counter", "Punish Counter", (), r"\bpunish\s*counter\b|\bpc\b"),
    ("counter_hit_adv", "Counter Hit", (), r"\bcounter\s*hit\s+adv(?:antage)?\b|\bch\s*adv\b"),
    ("counter_hit", "Counter Hit", (), r"\bcounter\s*hit\b|\bch\b"),
    ("frame_advantage", "Frame Advantage", (), r"\bframe\s+adv(?:antage)?\b"),
]

_PROPERTY_REQUEST_PRIORITY = (
    "punish_counter",
    "counter_hit_adv",
    "counter_hit",
    "frame_advantage",
)


def _requested_property_key(text):
    lowered = str(text or "").lower()
    if re.search(r"\b(?:all|full)\s+(?:frame\s*)?data\b|\btable\b", lowered):
        return None
    for key in _PROPERTY_REQUEST_PRIORITY:
        config = next((item for item in PROPERTY_VALUE_ALIASES if item[0] == key), None)
        if config and re.search(config[3], lowered):
            return key
    matches = [
        key for key, _label, _fields, pattern in PROPERTY_VALUE_ALIASES
        if key not in _PROPERTY_REQUEST_PRIORITY and re.search(pattern, lowered)
    ]
    if "damage" in matches and any(
        key in matches for key in ("block_damage", "guard_damage", "rev_damage", "chip_damage", "drive_damage")
    ):
        matches = [key for key in matches if key != "damage"]
    if "guard" in matches and "guard_damage" in matches:
        matches = [key for key in matches if key != "guard"]
    if "meter_gain" in matches and "super_gain" in matches:
        matches = [key for key in matches if key != "meter_gain"]
    return matches[0] if len(matches) == 1 else None


def _format_requested_property_reply(rows, property_key, *, game="sf6"):
    if not rows or not property_key:
        return None
    config = next((item for item in PROPERTY_VALUE_ALIASES if item[0] == property_key), None)
    if not config:
        return None
    _key, label, fields, _pattern = config
    lines = []
    for row in rows:
        if property_key == "range" and row.get("atkRange") is not None:
            range_reply = format_range_only_reply([row])
            if range_reply:
                lines.append(range_reply)
                continue
        if property_key == "hitconfirm":
            hc_sp = str(row.get("hcWinSpCa") or "-").replace("*", ",").strip() or "-"
            hc_tc = str(row.get("hcWinTc") or "-").replace("*", ",").strip() or "-"
            hc_notes = str(row.get("hcWinNotes") or "-").replace("[", "").replace("]", "").replace('"', "").strip() or "-"
            value = f"Sp/Su: {hc_sp}, TC: {hc_tc}. Notes: {hc_notes}"
        elif game == "sf6" and property_key in {"frame_advantage", "counter_hit", "punish_counter", "counter_hit_adv"}:
            from bubbot.utils.sf6_advantage_utils import format_sf6_frame_advantage_value

            value = format_sf6_frame_advantage_value(row, mode=property_key)
        elif game != "sf6" and property_key == "frame_advantage":
            on_hit = str(row.get("onHit") or row.get("on_hit") or "-").replace("*", ",").strip() or "-"
            on_block = str(row.get("onBlock") or row.get("on_block") or "-").replace("*", ",").strip() or "-"
            value = f"On Hit: {on_hit}, On Block: {on_block}"
        elif property_key in {"super_gain", "drive_damage", "stun"} or (
            property_key == "meter_gain" and (row.get("SelfSoH") is not None or row.get("SelfSoB") is not None) and row.get("meterGain") is None
        ):
            hit_value = str(row.get(fields[0]) or "-").replace("*", ",").strip() or "-"
            block_value = str(row.get(fields[1]) or "-").replace("*", ",").strip() or "-"
            value = f"Hit: {hit_value}, Block: {block_value}"
        else:
            value = ""
            for field in fields:
                value = str(row.get(field) or "").strip()
                if value:
                    break
            if not value:
                value = "-"
        value = discord.utils.escape_markdown(value)
        char_name = str(row.get("char_name") or row.get("char_key") or "Unknown").strip()
        move_name = str(row.get("moveName") or row.get("name") or row.get("numCmd") or "Unknown").strip()
        num_cmd = str(row.get("numCmd") or row.get("input") or "?").strip()
        suffix = "f" if property_key in {"startup", "active", "recovery", "total"} and any(ch.isdigit() for ch in value) and not value.endswith("f") else ""
        lines.append(f"{char_name}'s {move_name} ({num_cmd}) {label.lower()} is {value}{suffix}.")
    return truncate_message("\n".join(lines))


def _game_key_for_frame_module(module):
    return _FRAME_MODULES.get(module, "sf6")


def _property_reply_view(game, rows, property_key, owner_id, content):
    unique_rows = iter_unique_frame_rows(rows or [])
    if not unique_rows or not property_key or owner_id is None:
        return None
    char_key = menu_system._row_character_key(game, unique_rows[0])
    if not char_key:
        return None
    return PropertyValueView(game, char_key, unique_rows, property_key, owner_id, content)


async def _send_property_value_reply(message, rows, property_key, content=None, game="sf6"):
    property_reply = content or _format_requested_property_reply(rows, property_key, game=game)
    if not property_reply:
        return None
    view = _property_reply_view(game, rows, property_key, getattr(message.author, "id", None), property_reply)
    sent = await message.reply(property_reply, view=view)
    _record_frame_data_ids([sent.id])
    return sent


class PropertyValueView(discord.ui.View):
    def __init__(self, game, char_key, rows, property_key, owner_id, content):
        super().__init__(timeout=300)
        self.game = game
        self.char_key = char_key
        self.rows = iter_unique_frame_rows(rows or [])
        self.row = self.rows[0] if self.rows else None
        self.property_key = property_key
        self.owner_id = owner_id
        self.content = content
        self.add_item(PropertyCompareButton())
        self.add_item(PropertyFullFrameDataButton())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the person who opened this result can control it.", ephemeral=True)
            return False
        return True


class PropertyCompareButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Compare", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        parent = self.view
        moves = menu_system._move_list(parent.game, parent.char_key)
        if not moves:
            await interaction.response.send_message("No moves found for this character.", ephemeral=True)
            return
        display = menu_system._character_display_name(parent.game, parent.char_key)
        await interaction.response.edit_message(
            content=f"Choose another move to compare {parent.property_key.replace('_', ' ')} with.",
            embed=menu_system._move_select_embed(display, page=0, total_pages=max(1, (len(moves) + 24) // 25), compare_row=parent.row),
            view=PropertyCompareSelectView(parent, moves, page=0),
            attachments=[],
        )


class PropertyFullFrameDataButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Show Full Framedata", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        parent = self.view
        await interaction.response.defer()
        for row in parent.rows:
            row_char_key = menu_system._row_character_key(parent.game, row, parent.char_key)
            sent = await menu_system._send_frame_result_message(
                interaction.channel,
                parent.game,
                row_char_key or parent.char_key,
                row,
                parent.owner_id,
            )
            if sent:
                _record_frame_data_ids([sent.id])


class PropertyCompareSelectView(discord.ui.View):
    def __init__(self, parent_view, moves, page=0):
        super().__init__(timeout=300)
        self.parent_view = parent_view
        self.moves = moves
        self.page = page
        select = PropertyCompareSelect()
        self.add_item(select)
        select._refresh_options()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.parent_view.owner_id:
            await interaction.response.send_message("Only the person who opened this result can control it.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, row=4)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        page_count = max(1, (len(self.moves) + 24) // 25)
        new_page = self.page - 1 if self.page > 0 else page_count - 1
        await self._edit_page(interaction, new_page)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, row=4)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        page_count = max(1, (len(self.moves) + 24) // 25)
        new_page = self.page + 1 if self.page < page_count - 1 else 0
        await self._edit_page(interaction, new_page)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, row=4)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        parent = self.parent_view
        await interaction.response.edit_message(content=parent.content, embed=None, view=parent, attachments=[])

    async def _edit_page(self, interaction, new_page):
        parent = self.parent_view
        display = menu_system._character_display_name(parent.game, parent.char_key)
        page_count = max(1, (len(self.moves) + 24) // 25)
        await interaction.response.edit_message(
            content=f"Choose another move to compare {parent.property_key.replace('_', ' ')} with.",
            embed=menu_system._move_select_embed(display, page=new_page, total_pages=page_count, compare_row=parent.row),
            view=PropertyCompareSelectView(parent, self.moves, page=new_page),
            attachments=[],
        )


class PropertyCompareSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Select a move", options=[discord.SelectOption(label="Loading...", value="0")])

    def _refresh_options(self):
        parent_view = self.view
        start = parent_view.page * 25
        page_moves = parent_view.moves[start : start + 25]
        self.options = [
            discord.SelectOption(label=(label[:100] if len(label) > 100 else label), value=str(start + index))
            for index, (_row, label) in enumerate(page_moves)
        ] or [discord.SelectOption(label="No moves", value="none")]

    async def callback(self, interaction: discord.Interaction):
        self._refresh_options()
        if self.values[0] == "none":
            await interaction.response.send_message("No moves found for this character.", ephemeral=True)
            return
        idx = int(self.values[0])
        parent = self.view.parent_view
        row, _label = self.view.moves[idx]
        next_rows = iter_unique_frame_rows(parent.rows + [row])
        property_reply = _format_requested_property_reply(next_rows, parent.property_key, game=parent.game)
        if not property_reply:
            await interaction.response.send_message("I could not format that value for the selected move.", ephemeral=True)
            return
        next_char_key = menu_system._row_character_key(parent.game, row, parent.char_key) or parent.char_key
        await interaction.response.edit_message(
            content=property_reply,
            embed=None,
            view=PropertyValueView(parent.game, next_char_key, next_rows, parent.property_key, parent.owner_id, property_reply),
            attachments=[],
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        self._refresh_options()
        return True


async def _send_cross_game_lookup_response(message, module, rows, payload, query_text):
    if payload.get("gif_query") and payload.get("frame_query"):
        _record_frame_data_ids(await module.send_frame_response(message, rows))
        _record_frame_data_ids(await module.send_hitbox_response(message, rows))
        return True
    if payload.get("gif_query"):
        _record_frame_data_ids(await module.send_hitbox_response(message, rows))
        return True
    property_key = _requested_property_key(query_text)
    if _format_requested_property_reply(rows, property_key, game=_game_key_for_frame_module(module)):
        await _send_property_value_reply(message, rows, property_key, game=_game_key_for_frame_module(module))
        return True
    _record_frame_data_ids(await module.send_frame_response(message, rows))
    return True
