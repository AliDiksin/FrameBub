"""Shared Discord controls for frame-result media."""
# These controls are shared by frame-result views; game parsers only supply media links.

import discord


class ShowAllImagesButton(discord.ui.Button):
    def __init__(self, links):
        self.media_links = [str(link).strip() for link in (links or []) if str(link or "").strip()]
        super().__init__(
            label="Show All Images",
            style=discord.ButtonStyle.success,
            disabled=len(self.media_links) <= 1,
        )

    async def callback(self, interaction: discord.Interaction):
        if len(self.media_links) <= 1:
            await interaction.response.defer()
            return
        await interaction.response.send_message("\n".join(self.media_links))


def preferred_frame_image_url(game, row):
    game_key = str(game or "").strip().lower()
    if game_key == "ggst":
        from bubbot.frame_data.ggst_frame_data import get_hitbox_links
    elif game_key == "bbcf":
        from bubbot.frame_data.bbcf_frame_data import get_hitbox_links
    elif game_key == "ggacr":
        from bubbot.frame_data.ggacr_frame_data import get_hitbox_links
    elif game_key == "third_strike":
        from bubbot.frame_data.third_strike_frame_data import get_hitbox_links
    else:
        return ""
    links = get_hitbox_links(row)
    return links[0] if links else ""
