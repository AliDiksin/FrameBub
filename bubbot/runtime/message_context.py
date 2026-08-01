"""Shared message context, mention, reply, and response-ID helpers."""

import re
from collections import deque

import discord

client = None
menu_system = None
build_failed_prompt_report_view = None
attach_failed_prompt_report_button = None
FAILED_PROMPT_REASONS = set()
INTERACTION_MENU = "menu"
INTERACTION_PROMPT = "prompt"
build_log_record = None
log_message_and_reply = None
notify_owner = None
log_record = None
build_glossary_definition_embed = None
build_glossary_link_view = None
normalize_glossary_term = None
RANGE_MISSING_PLACEHOLDERS = set()
strip_discord_mentions = None

_FRAME_DATA_RESPONSE_IDS = deque(maxlen=500)
_FRAME_RESULT_COMPONENT_LABELS = {
    "back to menu",
    "compare",
    "hide image",
    "hide notes",
    "return to menu",
    "show all images",
    "show full framedata",
    "show gif",
    "show hitbox",
    "show image",
    "show notes",
}
_NUMBERED_DISAMBIGUATION_PROMPT_RE = re.compile(
    r"(?:Special Strength Options|Target Combo Options|Multiple (?:SFV|GGST|2XKO|BBCF|COTW|Third Strike|MK1) moves match)"
)
MENTION_PATTERN = re.compile(r"<@!?\d+>|<@&\d+>|<#\d+>")


def configure(**deps):
    globals().update(deps)


def strip_discord_mentions(content):
    if not content:
        return ""
    stripped = MENTION_PATTERN.sub(" ", content)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped
async def _fetch_referenced_message(message):
    if not message.reference or not message.reference.message_id:
        return None
    if message.reference.cached_message:
        return message.reference.cached_message
    return await message.channel.fetch_message(message.reference.message_id)
_FRAME_DATA_RESPONSE_IDS = deque(maxlen=500)


# Reply helpers: log failed prompts, attach Report Issue, stamp frame-data ids for reports
async def _reply_and_log_response(message, response_text, reason, **kwargs):
    view = kwargs.pop("view", None)
    if reason in FAILED_PROMPT_REASONS:
        if view is None:
            view = build_failed_prompt_report_view(
                message,
                bub_response_text=response_text,
                failure_reason=reason,
            )
        else:
            attach_failed_prompt_report_button(
                view,
                message,
                bub_response_text=response_text,
                failure_reason=reason,
            )
    sent = await message.reply(response_text, view=view, **kwargs)
    for child in getattr(view, "children", []) or []:
        report_context = getattr(child, "report_context", None)
        if isinstance(report_context, dict):
            report_context["reply_message_id"] = getattr(sent, "id", None)
            report_context["reply_jump_url"] = str(getattr(sent, "jump_url", "") or "")
            report_context["client"] = client
    try:
        log_message_and_reply(
            message,
            sent,
            interaction_type=INTERACTION_PROMPT,
            reason=reason,
            response_text=response_text,
        )
        if reason in FAILED_PROMPT_REASONS:
            record = build_log_record(
                interaction_type=INTERACTION_PROMPT,
                reason=reason,
                prompt=str(getattr(message, "content", "") or ""),
                response_text=response_text,
                failure_reason=reason,
                source_message=message,
                reply_message=sent,
            )
            await notify_owner(client, record)
    except Exception as log_error:
        print(f"Response log error: {log_error}", flush=True)
    return sent


def _message_prompt_text(message):
    parts = [str(getattr(message, "content", "") or "")]
    for embed in getattr(message, "embeds", []) or []:
        parts.append(str(getattr(embed, "title", "") or ""))
        parts.append(str(getattr(embed, "description", "") or ""))
    return "\n".join(part for part in parts if part).strip()


def _text_is_numbered_disambiguation_prompt(text):
    return bool(_NUMBERED_DISAMBIGUATION_PROMPT_RE.search(str(text or "")))


def _message_is_numbered_disambiguation_prompt(message):
    return _text_is_numbered_disambiguation_prompt(_message_prompt_text(message))


def _record_frame_data_ids(ids, *, response_text=None):
    if response_text and _text_is_numbered_disambiguation_prompt(response_text):
        return
    for mid in (ids or []):
        if mid:
            _FRAME_DATA_RESPONSE_IDS.append(mid)


_FRAME_RESULT_COMPONENT_LABELS = {
    "back to menu",
    "compare",
    "hide image",
    "hide notes",
    "return to menu",
    "show all images",
    "show full framedata",
    "show gif",
    "show hitbox",
    "show image",
    "show notes",
}


def _message_component_labels(message):
    labels = set()
    for component in getattr(message, "components", []) or []:
        children = getattr(component, "children", None) or []
        for child in children:
            label = str(getattr(child, "label", "") or "").strip().lower()
            if label:
                labels.add(label)
    return labels


def _is_frame_data_embed(embed):
    field_names = {
        str(getattr(field, "name", "") or "").strip().lower()
        for field in getattr(embed, "fields", []) or []
    }
    if {"startup", "active", "recovery"}.issubset(field_names):
        return True
    if "input" in field_names and "startup" in field_names and {"on hit", "on block"} & field_names:
        return True
    title = str(getattr(embed, "title", "") or "").strip().lower()
    if title.startswith(("ggst - ", "ggacr - ", "2xko - ", "bbcf - ", "cotw - ", "third strike - ", "mk1 - ")):
        return bool(field_names & {"startup", "input", "on hit", "on block"})
    return False


def _is_quiz_embed(embed):
    title = str(getattr(embed, "title", "") or "").strip().lower()
    return "frame data quiz" in title


def _message_looks_like_quiz_output(message):
    return any(_is_quiz_embed(embed) for embed in getattr(message, "embeds", []) or [])


def _message_looks_like_frame_data_output(message):
    if any(_is_frame_data_embed(embed) for embed in getattr(message, "embeds", []) or []):
        return True

    labels = _message_component_labels(message)
    if labels and labels <= _FRAME_RESULT_COMPONENT_LABELS:
        return True
    if {"compare", "show full framedata"}.issubset(labels):
        return True

    if getattr(message, "attachments", None):
        return True

    content = str(getattr(message, "content", "") or "").strip().lower()
    if not content:
        return False
    if "wiki.supercombo.gg/images" in content:
        return True
    if "dustloop.com" in content or "dreamcancel.com" in content:
        return True
    if re.fullmatch(r"(?:https?://\S+\s*)+", content) and re.search(r"\.(?:png|webp|gif|jpg|jpeg)(?:\?|\b)", content):
        return True
    if re.search(r"\b\w[\w .'-]*'s .+ \(.+\) .+ is .+\.\s*$", content):
        return True
    return False


_NUMBERED_DISAMBIGUATION_PROMPT_RE = re.compile(
    r"(?:Special Strength Options|Target Combo Options|Multiple (?:SFV|GGST|2XKO|BBCF|COTW|Third Strike|MK1) moves match)"
)


async def _is_reply_to_suppressed_bub_message(message):
    if not message.reference:
        return False
    replied_id = message.reference.message_id
    try:
        replied_message = await _fetch_referenced_message(message)
    except (discord.NotFound, discord.Forbidden):
        return False
    except Exception as error:
        print(f"Frame data reply guard fetch error: {error}", flush=True)
        return False
    if not replied_message or getattr(replied_message, "author", None) != client.user:
        return False

    if _message_is_numbered_disambiguation_prompt(replied_message):
        return False

    if replied_id in _FRAME_DATA_RESPONSE_IDS:
        return True

    if _message_looks_like_quiz_output(replied_message):
        return False

    if getattr(replied_message, "embeds", None):
        return True

    if _message_looks_like_frame_data_output(replied_message):
        _FRAME_DATA_RESPONSE_IDS.append(replied_id)
        return True
    return False


async def _is_reply_to_frame_data(message):
    return await _is_reply_to_suppressed_bub_message(message)


def is_missing_attack_range_value(raw_value):
    text = str(raw_value or "").strip()
    if not text:
        return True
    normalized = re.sub(r"\s+", "", text).lower()
    return normalized in RANGE_MISSING_PLACEHOLDERS

MENTION_PATTERN = re.compile(r"<@!?\d+>|<@&\d+>|<#\d+>")


def strip_url_like_text(text):
    cleaned = str(text or "")
    cleaned = re.sub(r"https?://\S+", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bwww\.\S+\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\S+\.gif(?:\?\S*)?\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\S+\.gifv(?:\?\S*)?\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def message_directly_mentions_bot(message):
    bot_user = getattr(client, "user", None)
    bot_id = getattr(bot_user, "id", None)
    if bot_id is None:
        return False
    if any(getattr(user, "id", None) == bot_id for user in getattr(message, "mentions", []) or []):
        return True
    return bot_id in (getattr(message, "raw_mentions", []) or [])


def is_plain_bot_mention_only(message):
    """True when the message is only a direct @Bub ping (works for replies too)."""
    if not message_directly_mentions_bot(message):
        return False
    content_no_mentions = strip_discord_mentions(getattr(message, "content", "") or "")
    return not content_no_mentions.strip()


async def _send_main_menu_for_plain_mention(message):
    await menu_system.send_main_menu(message.channel, owner_id=message.author.id)
    try:
        log_record(
            build_log_record(
                interaction_type=INTERACTION_MENU,
                reason="empty_mention_menu",
                prompt=str(getattr(message, "content", "") or ""),
                response_text="Opened main menu embed.",
                response_kind="embed",
                source_message=message,
            )
        )
    except Exception as log_error:
        print(f"Response log error: {log_error}", flush=True)


def has_explicit_gif_lookup_intent(text):
    cleaned = strip_url_like_text(strip_discord_mentions(text).lower())
    return bool(
        re.search(r"\bgif(?:s)?\b", cleaned)
        or re.search(r"\bhit\s*box(?:es)?\b", cleaned)
        or re.search(r"\bhitbox(?:es)?\b", cleaned)
    )


def extract_glossary_lookup_term(text):
    cleaned = strip_discord_mentions(text).strip()
    patterns = (
        r"^(?:(?:fg|fighting\s+game)\s+)?glossary(?:\s+(.+))?$",
        r"^fgg(?:\s+(.+))?$",
        r"^(?:define|definition)(?:\s+(.+))?$",
    )
    for pattern in patterns:
        match = re.match(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            return normalize_glossary_term(match.group(1) or "")
    return None


async def maybe_handle_glossary_lookup(message, content_no_mentions, *, addressed):
    if not addressed:
        return False
    term = extract_glossary_lookup_term(content_no_mentions)
    if term is None:
        return False
    sent = await message.reply(embed=build_glossary_definition_embed(term), view=build_glossary_link_view(term))
    try:
        log_message_and_reply(
            message,
            sent,
            interaction_type=INTERACTION_PROMPT,
            reason="fg_glossary_lookup",
            response_text=f"Opened FG glossary lookup for: {term or 'home'}",
        )
    except Exception as log_error:
        print(f"Response log error: {log_error}", flush=True)
    return True
