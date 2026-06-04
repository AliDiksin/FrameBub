"""Report button + modal for failed Bub prompts (missing data, invalid query, etc.)."""

from __future__ import annotations

import discord

from bubbot.utils.response_log import (
    INTERACTION_REPORT,
    build_log_record,
    log_and_notify_owner,
)


class FailedPromptReportModal(discord.ui.Modal, title="Report an issue"):
    report_details = discord.ui.TextInput(
        label="What went wrong?",
        style=discord.TextStyle.paragraph,
        placeholder="Example: I asked for mai ex fan and Bub said the scrolls are missing.",
        required=True,
        max_length=1500,
    )

    def __init__(self, report_context: dict):
        super().__init__()
        self.report_context = dict(report_context or {})

    async def on_submit(self, interaction: discord.Interaction):
        report_text = str(self.report_details.value or "").strip()
        if not report_text:
            await interaction.response.send_message("Please describe the issue before submitting.", ephemeral=True)
            return
        ctx = self.report_context
        record = build_log_record(
            interaction_type=INTERACTION_REPORT,
            reason="user_report",
            prompt=str(ctx.get("prompt", "") or ""),
            response_text=str(ctx.get("bub_response_text", "") or ""),
            response_kind="text",
            user_report=report_text,
            failure_reason=str(ctx.get("failure_reason", "") or ""),
            extra={
                "guild_id": ctx.get("guild_id"),
                "guild_name": ctx.get("guild_name", ""),
                "channel_id": ctx.get("channel_id"),
                "channel_name": ctx.get("channel_name", ""),
                "user_id": getattr(interaction.user, "id", None),
                "user_name": str(
                    getattr(interaction.user, "display_name", "")
                    or getattr(interaction.user, "name", "")
                    or ""
                ),
                "source_message_id": ctx.get("source_message_id"),
                "reply_message_id": ctx.get("reply_message_id"),
                "source_jump_url": ctx.get("source_jump_url", ""),
                "reply_jump_url": str(getattr(interaction.message, "jump_url", "") or ""),
            },
        )
        client = ctx.get("client")
        if client is None:
            from bubbot.runtime import message_router

            client = message_router.client
        await log_and_notify_owner(client, record)
        await interaction.response.send_message(
            "Thanks — your report was logged and sent to the maintainer.",
            ephemeral=True,
        )


class FailedPromptReportButton(discord.ui.Button):
    def __init__(self, report_context: dict):
        super().__init__(
            label="Report Issue",
            style=discord.ButtonStyle.secondary,
            custom_id="bub_failed_prompt_report",
        )
        self.report_context = dict(report_context or {})

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(FailedPromptReportModal(self.report_context))


def build_report_context_from_message(source_message, *, bub_response_text: str, failure_reason: str) -> dict:
    author = getattr(source_message, "author", None)
    guild = getattr(source_message, "guild", None)
    channel = getattr(source_message, "channel", None)
    return {
        "prompt": str(getattr(source_message, "content", "") or ""),
        "bub_response_text": bub_response_text,
        "failure_reason": failure_reason,
        "guild_id": getattr(guild, "id", None),
        "guild_name": str(getattr(guild, "name", "") or ""),
        "channel_id": getattr(channel, "id", None),
        "channel_name": str(getattr(channel, "name", "") or ""),
        "source_message_id": getattr(source_message, "id", None),
        "source_jump_url": str(getattr(source_message, "jump_url", "") or ""),
        "source_user_id": getattr(author, "id", None),
        "source_user_name": str(getattr(author, "display_name", "") or getattr(author, "name", "") or ""),
    }


def attach_failed_prompt_report_button(view, source_message, *, bub_response_text: str, failure_reason: str):
    if view is None:
        return None
    for child in getattr(view, "children", []) or []:
        if getattr(child, "custom_id", None) == "bub_failed_prompt_report":
            return view
    context = build_report_context_from_message(
        source_message,
        bub_response_text=bub_response_text,
        failure_reason=failure_reason,
    )
    view.add_item(FailedPromptReportButton(context))
    return view


def build_failed_prompt_report_view(source_message, *, bub_response_text: str, failure_reason: str):
    view = discord.ui.View(timeout=None)
    attach_failed_prompt_report_button(
        view,
        source_message,
        bub_response_text=bub_response_text,
        failure_reason=failure_reason,
    )
    return view
