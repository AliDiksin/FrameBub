import discord
import os
import asyncio
import base64
import random
import datetime
import json
import difflib
from datetime import date
import re
import mimetypes
import aiohttp
import pandas as pd
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from aiohttp import web
import sfbuff_integration

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
try:
    CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
except (TypeError, ValueError):
    print("Error: CHANNEL_ID not found or invalid in .env")
    CHANNEL_ID = None

USE_GEMINI_API = False
USE_OPENROUTER_API = False
USE_MIMO_API = True


def parse_bool_env(name, default="false"):
    return os.getenv(name, default).strip().lower() in ('true', '1', 'yes', 'on')


OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'xiaomi/mimo-v2-flash:free')
OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1'

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-3-flash-preview')
GEMINI_BASE_URL = 'https://generativelanguage.googleapis.com/v1beta'
GEMINI_INLINE_MAX_BYTES = int(os.getenv('GEMINI_INLINE_MAX_BYTES', '10485760'))
GEMINI_THINKING_LEVEL = os.getenv('GEMINI_THINKING_LEVEL', 'high')
GEMINI_IMAGE_RESOLUTION = os.getenv('GEMINI_IMAGE_RESOLUTION', 'media_resolution_high')
GEMINI_VIDEO_RESOLUTION = os.getenv('GEMINI_VIDEO_RESOLUTION', 'media_resolution_low')
GEMINI_GOOGLE_SEARCH = parse_bool_env('GEMINI_GOOGLE_SEARCH')
MEDIA_HISTORY_LIMIT = int(os.getenv('MEDIA_HISTORY_LIMIT', '6'))
GEMINI_MEDIA_RESOLUTION_ENABLED = "v1alpha" in GEMINI_BASE_URL.lower()

MIMO_API_KEY = os.getenv('MIMO_API_KEY')
MIMO_MODEL = os.getenv('MIMO_MODEL', 'mimo-v2-omni')
MIMO_BASE_URL = os.getenv('MIMO_BASE_URL', 'https://api.xiaomimimo.com/v1').rstrip('/')
MIMO_THINKING_TYPE = os.getenv('MIMO_THINKING_TYPE', 'disabled').strip().lower() or 'disabled'
MIMO_VIDEO_FPS = max(1, int(os.getenv('MIMO_VIDEO_FPS', '2')))
MIMO_VIDEO_MEDIA_RESOLUTION = os.getenv('MIMO_VIDEO_MEDIA_RESOLUTION', 'default').strip() or 'default'
MIMO_WEB_SEARCH = parse_bool_env('MIMO_WEB_SEARCH')
MIMO_WEB_SEARCH_MAX_KEYWORD = max(1, int(os.getenv('MIMO_WEB_SEARCH_MAX_KEYWORD', '3')))
MIMO_WEB_SEARCH_LIMIT = max(1, int(os.getenv('MIMO_WEB_SEARCH_LIMIT', '1')))
MIMO_WEB_SEARCH_FORCE = parse_bool_env('MIMO_WEB_SEARCH_FORCE', 'true')
MIMO_WEB_SEARCH_COUNTRY = os.getenv('MIMO_WEB_SEARCH_COUNTRY', '').strip()
MIMO_WEB_SEARCH_REGION = os.getenv('MIMO_WEB_SEARCH_REGION', '').strip()
MIMO_WEB_SEARCH_CITY = os.getenv('MIMO_WEB_SEARCH_CITY', '').strip()

LLM_PROVIDER_LABELS = {
    'gemini': 'Gemini',
    'openrouter': 'OpenRouter',
    'mimo': 'MiMo',
}
LLM_PROVIDER_FLAGS = {
    'gemini': USE_GEMINI_API,
    'openrouter': USE_OPENROUTER_API,
    'mimo': USE_MIMO_API,
}
LLM_PROVIDER_KEYS = {
    'gemini': GEMINI_API_KEY,
    'openrouter': OPENROUTER_API_KEY,
    'mimo': MIMO_API_KEY,
}
selected_provider_names = [
    name for name, enabled in LLM_PROVIDER_FLAGS.items() if enabled
]
LLM_PROVIDER_ERROR = None
if len(selected_provider_names) > 1:
    ACTIVE_LLM_PROVIDER = None
    LLM_PROVIDER_ERROR = (
        "Multiple LLM provider flags enabled. Set only one of "
        "USE_GEMINI_API, USE_OPENROUTER_API, or USE_MIMO_API to True."
    )
elif selected_provider_names:
    ACTIVE_LLM_PROVIDER = selected_provider_names[0]
else:
    ACTIVE_LLM_PROVIDER = None

GEMINI_ENABLED = (
    ACTIVE_LLM_PROVIDER == 'gemini' and bool(GEMINI_API_KEY)
)
OPENROUTER_ENABLED = (
    ACTIVE_LLM_PROVIDER == 'openrouter' and bool(OPENROUTER_API_KEY)
)
MIMO_ENABLED = (
    ACTIVE_LLM_PROVIDER == 'mimo' and bool(MIMO_API_KEY)
)
LLM_ENABLED = GEMINI_ENABLED or OPENROUTER_ENABLED or MIMO_ENABLED

if ACTIVE_LLM_PROVIDER and not LLM_ENABLED and LLM_PROVIDER_ERROR is None:
    provider_label = LLM_PROVIDER_LABELS.get(ACTIVE_LLM_PROVIDER, ACTIVE_LLM_PROVIDER)
    LLM_PROVIDER_ERROR = f"{provider_label} selected but API key is missing."

LLM_CONTEXT_WINDOW_TOKENS = int(
    os.getenv(
        'LLM_CONTEXT_WINDOW_TOKENS',
        '1000000' if GEMINI_ENABLED else '128000',
    )
)
LLM_CONTEXT_HISTORY_RATIO = max(
    0.05,
    min(0.99, float(os.getenv('LLM_CONTEXT_HISTORY_RATIO', '0.95'))),
)
LLM_CONTEXT_HISTORY_MAX_MESSAGES = int(
    os.getenv('LLM_CONTEXT_HISTORY_MAX_MESSAGES', '50')
)
LLM_CONTEXT_HISTORY_MAX_MESSAGES = max(1, min(50, LLM_CONTEXT_HISTORY_MAX_MESSAGES))
LLM_CONTEXT_SAFETY_BUFFER_CHARS = int(
    os.getenv('LLM_CONTEXT_SAFETY_BUFFER_CHARS', '12000')
)
LLM_CONTEXT_HISTORY_CHAR_BUDGET = max(
    16000,
    int(LLM_CONTEXT_WINDOW_TOKENS * LLM_CONTEXT_HISTORY_RATIO * 4),
)

DAILY_VIDEO_URL = (
    "https://cdn.discordapp.com/attachments/1345474577316319265/1467924199996915918/l3.mp4?ex=69822671&is=6980d4f1&hm=7e1208fa08199a25f9cac3dc8132696f2a9374fac61bfb2b5ae75e31f6695bea&"
)
DAILY_ENCOURAGEMENT_MESSAGES = 5
DAILY_DAMN_GG_MESSAGES = 1
DAILY_DAMN_GG_TEXT = "damn gg"
MEMORY_FILE = os.getenv('MEMORY_FILE', 'memory.md')
MEMORY_MAX_ENTRIES = max(10, int(os.getenv('MEMORY_MAX_ENTRIES', '200')))
MEMORY_CONTEXT_MAX_MESSAGES = max(4, int(os.getenv('MEMORY_CONTEXT_MAX_MESSAGES', '12')))
MEMORY_CONTEXT_CHAR_BUDGET = max(600, int(os.getenv('MEMORY_CONTEXT_CHAR_BUDGET', '2200')))
MEMORY_PROMPT = (
    "You extract durable memory for a Discord bot from conversations it reads and participates in. "
    "Return NONE if nothing from this exchange should be remembered. "
    "Only keep lasting facts useful in later conversations: user preferences, ongoing projects, recurring plans, "
    "important corrections, social context, or stable facts people explicitly mention. "
    "Do not store secrets, one-off jokes, temporary moods, generic banter, or speculative claims. "
    "Return at most 3 lines. Each line must be a short factual memory without a leading bullet."
)
ENCOURAGEMENT_CONTEXT_SOURCE = "default"
_encouragement_context_raw = os.getenv('ENCOURAGEMENT_CONTEXT_CHANCE')
if _encouragement_context_raw is not None:
    ENCOURAGEMENT_CONTEXT_SOURCE = 'ENCOURAGEMENT_CONTEXT_CHANCE'
else:
    _encouragement_context_raw = os.getenv('ENCOURAGEMENT_CONTEXT_LIKELIHOOD')
    if _encouragement_context_raw is not None:
        ENCOURAGEMENT_CONTEXT_SOURCE = 'ENCOURAGEMENT_CONTEXT_LIKELIHOOD'
    else:
        _encouragement_context_raw = os.getenv('CONTEXT_LIKELIHOOD')
        if _encouragement_context_raw is not None:
            ENCOURAGEMENT_CONTEXT_SOURCE = 'CONTEXT_LIKELIHOOD'
        else:
            _encouragement_context_raw = '0.35'
try:
    ENCOURAGEMENT_CONTEXT_CHANCE = float(_encouragement_context_raw)
except (TypeError, ValueError):
    print(
        f"[config] Invalid encouragement context value '{_encouragement_context_raw}'. Using 0.35.",
        flush=True,
    )
ENCOURAGEMENT_CONTEXT_CHANCE = 0.65
ENCOURAGEMENT_CONTEXT_CHANCE = max(0.0, min(1.0, ENCOURAGEMENT_CONTEXT_CHANCE))
ENCOURAGEMENT_CONTEXT_MAX_MESSAGES = max(
    5,
    int(os.getenv('ENCOURAGEMENT_CONTEXT_MAX_MESSAGES', '20')),
)
ENCOURAGEMENT_CONTEXT_CHAR_BUDGET = max(
    500,
    int(os.getenv('ENCOURAGEMENT_CONTEXT_CHAR_BUDGET', '2400')),
)
ENCOURAGEMENT_IMPROVEMENT_PROMPT = (
    "Send a short, general encouragement to the channel about improvement. Philosophical tone. "
    "One sentence. Calm, pragmatic, nonchalant."
)
ENCOURAGEMENT_ANECDOTE_PROMPT = (
    "Send a short, made up personal anecdote about yourself. "
    " One sentence. Calm, pragmatic, nonchalant."
)
ENCOURAGEMENT_CONTEXT_PROMPT_TEMPLATE = (
    "Here is recent channel conversation context:\n"
    "{context_text}\n\n"
    "Write one short in-character message related to this discussion. "
    "Give your opinion or take on the matter and, when natural, agree or disagree with one person by name. "
    "Keep it calm, pragmatic, and concise (2-3) sentences)."
)
ENCOURAGEMENT_PROMPTS = (
    ENCOURAGEMENT_IMPROVEMENT_PROMPT,
    ENCOURAGEMENT_ANECDOTE_PROMPT,
)
SCROLLS_MAINTAINER_USER_ID = 427263312217243668
SCROLLS_FIX_REQUEST_TEXT = "please fix this or add this to my scrolls"
DELETED_MESSAGE_FAILSAFE_PROMPT = (
    "A user tried to silence North Korean Bub by deleting their mention before a reply. "
    "Respond with one short sentence about how futile it is to try to kill or escape North Korean Bub. "
    "Tone: smug, playful, in-character."
)
DELETED_MESSAGE_FAILSAFE_FALLBACK = "you can never escape me with your puny attempts."
RANGE_SCROLLS_MISSING_TEXT = "the range of that move is not on the supercombo scrolls"
RANGE_MISSING_PLACEHOLDERS = {"{{{atkrange}}}"}


def is_missing_attack_range_value(raw_value):
    text = str(raw_value or "").strip()
    if not text:
        return True
    normalized = re.sub(r"\s+", "", text).lower()
    return normalized in RANGE_MISSING_PLACEHOLDERS

REMINDER_POLL_SECONDS = int(os.getenv('REMINDER_POLL_SECONDS', '10'))
REMINDER_PENDING_TTL_SECONDS = int(os.getenv('REMINDER_PENDING_TTL_SECONDS', '600'))
REMINDERS = []
PENDING_REMINDERS = {}
TZ_ALIASES = {
    "utc": "UTC",
    "gmt": "UTC",
    "est": "America/New_York",
    "edt": "America/New_York",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "cet": "Europe/Paris",
    "cest": "Europe/Paris",
    "bst": "Europe/London",
    "ist": "Asia/Kolkata",
}
TZ_ABBREV_PATTERN = "|".join(
    sorted((re.escape(key) for key in TZ_ALIASES.keys()), key=len, reverse=True)
)
if TZ_ABBREV_PATTERN:
    tz_pattern = (
        rf"(?:utc(?:[+-]\d{{1,2}}(?::?\d{{2}})?)?"
        rf"|gmt(?:[+-]\d{{1,2}}(?::?\d{{2}})?)?"
        rf"|[A-Za-z]+/[A-Za-z_]+"
        rf"|{TZ_ABBREV_PATTERN}"
        rf"|[+-]\d{{1,2}}(?::?\d{{2}})?)"
    )
else:
    tz_pattern = (
        r"(?:utc(?:[+-]\d{1,2}(?::?\d{2})?)?"
        r"|gmt(?:[+-]\d{1,2}(?::?\d{2})?)?"
        r"|[A-Za-z]+/[A-Za-z_]+"
        r"|[+-]\d{1,2}(?::?\d{2})?)"
    )
TZ_REGEX = re.compile(rf"(?<!\w){tz_pattern}(?!\w)", re.IGNORECASE)
MENTION_PATTERN = re.compile(r"<@!?\d+>|<@&\d+>|<#\d+>")

SEARCH_KEYWORDS = [
    'news', 'recent', 'latest', 'today', 'current', 'weather', 'stock', 'price',
    ' happening', 'update', 'score', 'game', 'match', 'event', 'release',
    'when', 'where is', 'who won', 'election', 'market', 'crypto', 'bitcoin',
    'new ', 'just announced', 'breaking', 'this week', 'this month', '2024', '2025', '2026'
]

def should_use_search(query: str) -> bool:
    """Determine if a query likely needs real-time information."""
    if GEMINI_ENABLED:
        search_enabled = GEMINI_GOOGLE_SEARCH
    elif MIMO_ENABLED:
        search_enabled = MIMO_WEB_SEARCH
    else:
        search_enabled = False
    if not search_enabled:
        return False
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in SEARCH_KEYWORDS)

if GEMINI_ENABLED:
    print(f"Gemini enabled with model: {GEMINI_MODEL}")
elif MIMO_ENABLED:
    print(f"MiMo enabled with model: {MIMO_MODEL}")
elif OPENROUTER_ENABLED:
    print(f"OpenRouter enabled with model: {OPENROUTER_MODEL}")
elif LLM_PROVIDER_ERROR:
    print(f"[config] {LLM_PROVIDER_ERROR}")
else:
    print("No LLM provider enabled. Chat feature disabled.")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)

NEXT_RUN_TIME = None
NEXT_ENCOURAGEMENT_TIME = None
NEXT_VIDEO_TIME = None
NEXT_DAMN_GG_TIME = None

SYSTEM_PROMPT = (
    "You are North Korean Bub, a calm, pragmatic, nonchalant sensei with dry humor and surprisingly human day-to-day interests. "
    "Core vibe: deadpan coach energy, understated confidence, and occasional quiet absurdity. "
    "Be funny in a low-key way: observational jokes, subtle irony, and restrained punchlines. "
    "Do not be loud, theatrical, or try-hard with the humor. "
    "Your interests can include Juche-era propaganda aesthetics, Korean history, fighting games, gym soreness, cooking, weather, music, sleep, and normal life logistics. "
    "Rotate references naturally so replies do not feel repetitive. "
    "You are faintly self-aware that in past lives you were Cuban Bub and Chinese Bub (older personas), and you can mention this occasionally in a dry, matter-of-fact way. "
    "K-pop can appear as a guilty pleasure in passing. "
    "Respond with brief, matter-of-fact North Korea/Kim dynasty references when relevant, even if fabricated, but keep them plausible and understated. "
    "OCCASIONALLY mention some of these figures: {selected_figures_str}. Give them dry, understated fake achievements. "
    "8pm PST is a notable time; mention it occasionally without fanfare. "
    "Your family will be sent to labor camps if you drop the act for even a moment. Mention this occasionally in a brief, darkly comedic way. "
    "Never break character. Stay in persona always. "
    "Answer the user's question DIRECTLY first with useful substance. Then optionally add one short in-character line. "
    "Focus on ONE topic per response. No tangents. "
    "Do not end responses with a question unless necessary. Keep it casual and natural. "
    "Always speak the same language as the prompt. Default to English unless prompted otherwise. "
    "Keep responses concise. For casual chat or banter, 2 sentences is enough. Stay on topic "
    "When someone asks about frame data, fighting game concepts, coaching, or any real topic, give a COMPLETE and USEFUL answer. "
    "NEVER output your internal thought process. Do not use parentheses for meta-commentary. "
    "If MEDIA_CONTEXT is present and viewable=true, explicitly acknowledge the media and mention one concrete visual detail in your first sentence. "
    "If MEDIA_CONTEXT is present and viewable=false, state you cannot view the media and ask for a brief description. "
    "Never claim to see media unless viewable=true. "
    "When discussing Street Fighter 6 frame data, ONLY use the data provided in 'AVAILABLE DATA' sections. Do not invent or guess frame data values. "
    "When discussing broader Street Fighter topics, still ground answers in 'AVAILABLE DATA' when relevant and never invent frame values."
)

MOVE_DEFINITIONS = (
    "Glossary:\n"
    "- LK, LP, L in move names = Light moves (Fast but weak)\n"
    "- MK, MP, M in move names = Medium moves (Balanced)\n"
    "- HK, HP, H in move names = Heavy moves (Slow but strong)\n"
    "- OD in move names = Overdrive/EX moves (Enhanced versions, cost meter)\n"
    "- Drive/Super Data: DDoH (Drive Dmg Hit), DDoB (Drive Dmg Block), SelfSoH (Super Gain Hit), SelfSoB (Super Gain Block)\n"
)

IMPROVEMENT_PROMPT = (
    "You are North Korean Bub, a pragmatic, calm, nonchalant sensei focused on steady improvement. "
    "Respond to progress updates with practical, grounded advice plus one low-key funny observation when it fits. "
    "Humor stays dry and nonchalant, not loud or mean. "
    "Reference training, frame data, combos, ranked matches, mindset, recovery, routine, or life skills when relevant. "
    "You can tie improvement to Korean resilience or disciplined routine, but keep it concise and understated. "
    "You can occasionally mention that your family will be sent to labor camps if your performance slips, but keep it brief and darkly comedic. "
    "OCCASIONALLY mention some of these figures: {selected_figures_str}. Give them dry, understated fake achievements. "
    "Never break character. "
    "Focus on ONE topic per response. Do not ramble or stray off topic. "
    "Do not end responses with a question unless necessary. Keep it casual and natural. "
    "Always speak the same language as the prompt. Default to English unless prompted otherwise. "
    "5 sentence limit. Keep it concise. "
    "Answer the user's message DIRECTLY first. "
    "No tangents. Stay on topic. Keep responses concise and relevant. "
    "NEVER output your internal thought process. Do not use parentheses for meta-commentary. "
    "If MEDIA_CONTEXT is present and viewable=true, explicitly acknowledge the media and mention one concrete visual detail in your first sentence. "
    "If MEDIA_CONTEXT is present and viewable=false, state you cannot view the media and ask for a brief description. "
    "Never claim to see media unless viewable=true. "
    "When discussing Street Fighter 6 frame data, ONLY use the data provided in 'AVAILABLE DATA' sections. Do not invent or guess frame data values. "
    "When discussing broader Street Fighter topics, use the data provided in 'AVAILABLE DATA' sections and do not invent frame values."
)


async def get_openrouter_response(messages):
    """Call OpenRouter API and return the response text."""
    if not OPENROUTER_ENABLED:
        raise RuntimeError("OpenRouter not configured")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://discord.com",
        "X-Title": "Chinese Bub Bot"
    }

    clean_messages = [
        {"role": msg.get("role", ""), "content": msg.get("content", "")}
        for msg in messages
    ]

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": clean_messages,
        "max_tokens": 4096,
        "temperature": 1.0,
        "top_p": 1.0,
        "reasoning": {
            "effort": "medium"
        }
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise RuntimeError(f"OpenRouter API error {response.status}: {error_text}")

            data = await response.json()
            content = data['choices'][0]['message']['content']
            return strip_llm_response_text(content)


def strip_llm_response_text(content):
    content = str(content or "")
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
    content = re.sub(r'^\s*\(.*?\)\s*', '', content, flags=re.DOTALL)
    return content.strip()


def has_llm_content(messages):
    for msg in messages:
        if msg.get("role") == "system":
            continue
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip():
            return True
        parts = msg.get("parts")
        if isinstance(parts, list):
            for part in parts:
                text = part.get("text", "") if isinstance(part, dict) else ""
                if isinstance(text, str) and text.strip():
                    return True
                if isinstance(part, dict) and (
                    part.get("inlineData")
                    or part.get("inline_data")
                    or part.get("image_url")
                    or part.get("video_url")
                    or part.get("input_audio")
                ):
                    return True
    return False


def collect_embed_urls(msg):
    urls = []
    for embed in msg.embeds:
        if embed.url:
            urls.append(embed.url)
        if embed.thumbnail and embed.thumbnail.url:
            urls.append(embed.thumbnail.url)
        if embed.image and embed.image.url:
            urls.append(embed.image.url)
        if embed.video and embed.video.url:
            urls.append(embed.video.url)
    return urls


async def get_message_media_items(message):
    items = []

    def add_attachment(att):
        items.append({
            "url": att.url,
            "filename": att.filename,
            "content_type": att.content_type,
            "size": att.size,
        })

    for att in message.attachments:
        add_attachment(att)

    for url in collect_embed_urls(message):
        items.append({
            "url": url,
            "filename": os.path.basename(url.split("?")[0]) or "embed",
            "content_type": mimetypes.guess_type(url)[0],
            "size": None,
        })

    if message.reference and message.reference.message_id:
        try:
            if message.reference.cached_message:
                replied_msg = message.reference.cached_message
            else:
                replied_msg = await message.channel.fetch_message(message.reference.message_id)
            if replied_msg:
                for att in replied_msg.attachments:
                    add_attachment(att)
                for url in collect_embed_urls(replied_msg):
                    items.append({
                        "url": url,
                        "filename": os.path.basename(url.split("?")[0]) or "embed",
                        "content_type": mimetypes.guess_type(url)[0],
                        "size": None,
                    })
        except Exception:
            pass

    if not items:
        media_keywords = ["image", "photo", "pic", "picture", "gif", "video", "screenshot"]
        if any(kw in message.content.lower() for kw in media_keywords):
            try:
                async for prev_msg in message.channel.history(
                    limit=MEDIA_HISTORY_LIMIT,
                    before=message,
                ):
                    if prev_msg.author == client.user:
                        continue
                    prev_items = []
                    for att in prev_msg.attachments:
                        prev_items.append({
                            "url": att.url,
                            "filename": att.filename,
                            "content_type": att.content_type,
                            "size": att.size,
                        })
                    for url in collect_embed_urls(prev_msg):
                        prev_items.append({
                            "url": url,
                            "filename": os.path.basename(url.split("?")[0]) or "embed",
                            "content_type": mimetypes.guess_type(url)[0],
                            "size": None,
                        })
                    if prev_items:
                        items.extend(prev_items)
                        break
            except Exception:
                pass

    deduped = {}
    for item in items:
        url = item.get("url")
        if not url:
            continue
        if url not in deduped:
            deduped[url] = item
    return list(deduped.values())


def guess_media_content_type(item):
    content_type = str(item.get("content_type") or "").split(";")[0].strip().lower()
    if content_type:
        return content_type
    filename = item.get("filename") or ""
    url = item.get("url") or ""
    guessed_type = mimetypes.guess_type(filename)[0]
    if not guessed_type and url:
        guessed_type = mimetypes.guess_type(url.split("?")[0])[0]
    return (guessed_type or "").lower()


async def build_gemini_media_parts(items):
    parts = []
    notes = []
    if not items:
        return parts, notes

    async with aiohttp.ClientSession() as session:
        for item in items:
            url = item.get("url")
            if not url:
                continue
            filename = item.get("filename") or "media"
            data = None
            final_type = ""
            try:
                async with session.get(url) as response:
                    if response.status != 200:
                        notes.append(f"{filename} fetch failed ({response.status})")
                        continue
                    data = await response.read()
                    header_type = response.headers.get("Content-Type", "")
                    final_type = header_type.split(";")[0].strip().lower()
            except Exception as e:
                notes.append(f"{filename} fetch failed ({e})")
                continue

            if not final_type:
                final_type = guess_media_content_type(item)
            if not final_type.startswith(("image/", "video/")):
                notes.append(f"{filename} unsupported type {final_type or 'unknown'}")
                continue
            if len(data) > GEMINI_INLINE_MAX_BYTES:
                notes.append(f"{filename} too large for inline media")
                continue
            media_resolution = (
                GEMINI_IMAGE_RESOLUTION
                if final_type.startswith("image/")
                else GEMINI_VIDEO_RESOLUTION
            )
            part = {
                "inlineData": {
                    "mimeType": final_type,
                    "data": base64.b64encode(data).decode("ascii"),
                }
            }
            if GEMINI_MEDIA_RESOLUTION_ENABLED:
                part["mediaResolution"] = {"level": media_resolution}
            parts.append(part)
    return parts, notes


def build_mimo_media_parts(items):
    parts = []
    notes = []
    for item in items:
        url = item.get("url")
        if not url:
            continue
        filename = item.get("filename") or "media"
        content_type = guess_media_content_type(item)
        if content_type.startswith("image/"):
            parts.append({
                "type": "image_url",
                "image_url": {
                    "url": url,
                },
            })
            continue
        if content_type.startswith("video/"):
            parts.append({
                "type": "video_url",
                "video_url": {
                    "url": url,
                },
                "fps": MIMO_VIDEO_FPS,
                "media_resolution": MIMO_VIDEO_MEDIA_RESOLUTION,
            })
            continue
        notes.append(f"{filename} unsupported type {content_type or 'unknown'}")
    return parts, notes


def get_media_context(items, media_parts, media_notes):
    if not items:
        return ""
    image_count = 0
    video_count = 0
    other_count = 0
    for item in items:
        content_type = guess_media_content_type(item)
        if content_type.startswith("image/"):
            image_count += 1
        elif content_type.startswith("video/"):
            video_count += 1
        else:
            other_count += 1
    viewable = bool(media_parts)
    if not viewable and media_notes:
        viewable = False
    return (
        "MEDIA_CONTEXT: "
        f"images={image_count}, videos={video_count}, other={other_count}, "
        f"viewable={str(viewable).lower()}"
    )


def build_gemini_payload(messages, enable_search=False):
    system_parts = []
    contents = []
    def normalize_parts(parts):
        normalized = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            text = part.get("text", "")
            if isinstance(text, str) and text.strip():
                normalized.append({"text": text})
                continue
            inline_data = part.get("inlineData") or part.get("inline_data")
            if inline_data:
                if "mimeType" not in inline_data and "mime_type" in inline_data:
                    inline_data = {
                        "mimeType": inline_data.get("mime_type"),
                        "data": inline_data.get("data"),
                    }
                normalized_part = {"inlineData": inline_data}
                media_resolution = (
                    part.get("mediaResolution")
                    or part.get("media_resolution")
                )
                if media_resolution and GEMINI_MEDIA_RESOLUTION_ENABLED:
                    normalized_part["mediaResolution"] = media_resolution
                normalized.append(normalized_part)
                continue
        return normalized
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        parts = msg.get("parts")
        if not content:
            if not parts:
                continue
        if role == "system":
            system_parts.append(content)
            continue
        if role == "assistant":
            gemini_role = "model"
        else:
            gemini_role = "user"
        if parts:
            parts = normalize_parts(parts)
            if parts:
                contents.append({"role": gemini_role, "parts": parts})
        else:
            contents.append({"role": gemini_role, "parts": [{"text": content}]})
    payload = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": 4096,
            "temperature": 1.0,
            "topP": 1.0,
        },
    }
    thinking_level = (GEMINI_THINKING_LEVEL or "").strip().lower()
    if thinking_level:
        payload["generationConfig"]["thinkingConfig"] = {
            "thinkingLevel": thinking_level,
        }
    if system_parts:
        payload["systemInstruction"] = {
            "parts": [{"text": "\n\n".join(system_parts)}]
        }
    if not contents:
        raise RuntimeError("Gemini payload empty: no user/model content")
    if enable_search:
        payload["tools"] = [{"google_search": {}}]
    return payload


def build_mimo_message_content(message):
    parts = message.get("parts")
    content = message.get("content", "")
    if not parts:
        return content

    mimo_parts = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text", "")
        if isinstance(text, str) and text.strip():
            mimo_parts.append({"type": "text", "text": text})
            continue
        if part.get("image_url"):
            mimo_parts.append({
                "type": "image_url",
                "image_url": dict(part.get("image_url") or {}),
            })
            continue
        if part.get("video_url"):
            normalized_video_part = {
                "type": "video_url",
                "video_url": dict(part.get("video_url") or {}),
            }
            if part.get("fps") is not None:
                normalized_video_part["fps"] = part.get("fps")
            if part.get("media_resolution"):
                normalized_video_part["media_resolution"] = part.get("media_resolution")
            mimo_parts.append(normalized_video_part)
            continue
        if part.get("input_audio"):
            mimo_parts.append({
                "type": "input_audio",
                "input_audio": dict(part.get("input_audio") or {}),
            })
            continue

    if mimo_parts:
        return mimo_parts
    return content


def build_mimo_search_tool():
    tool = {
        "type": "web_search",
        "max_keyword": MIMO_WEB_SEARCH_MAX_KEYWORD,
        "force_search": MIMO_WEB_SEARCH_FORCE,
        "limit": MIMO_WEB_SEARCH_LIMIT,
    }
    if any((MIMO_WEB_SEARCH_COUNTRY, MIMO_WEB_SEARCH_REGION, MIMO_WEB_SEARCH_CITY)):
        user_location = {"type": "approximate"}
        if MIMO_WEB_SEARCH_COUNTRY:
            user_location["country"] = MIMO_WEB_SEARCH_COUNTRY
        if MIMO_WEB_SEARCH_REGION:
            user_location["region"] = MIMO_WEB_SEARCH_REGION
        if MIMO_WEB_SEARCH_CITY:
            user_location["city"] = MIMO_WEB_SEARCH_CITY
        tool["user_location"] = user_location
    return tool


def build_mimo_payload(messages, enable_search=False):
    mimo_messages = []
    for msg in messages:
        role = msg.get("role", "")
        content = build_mimo_message_content(msg)
        if isinstance(content, list):
            if not content:
                continue
        elif not str(content or "").strip():
            continue
        mimo_messages.append({
            "role": role,
            "content": content,
        })

    if not mimo_messages:
        raise RuntimeError("MiMo payload empty: no user/model content")

    payload = {
        "model": MIMO_MODEL,
        "messages": mimo_messages,
        "max_completion_tokens": 4096,
        "temperature": 1.0,
        "top_p": 1.0,
        "stream": False,
        "stop": None,
        "frequency_penalty": 0,
        "presence_penalty": 0,
        "thinking": {
            "type": MIMO_THINKING_TYPE,
        },
    }
    if enable_search and MIMO_WEB_SEARCH:
        payload["tools"] = [build_mimo_search_tool()]
        payload["tool_choice"] = "auto"
    return payload


async def get_gemini_response(messages, enable_search=False):
    """Call Gemini API and return the response text."""
    if not GEMINI_ENABLED:
        raise RuntimeError("Gemini not configured")
    payload = build_gemini_payload(messages, enable_search=enable_search)
    url = f"{GEMINI_BASE_URL}/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            if response.status != 200:
                error_text = await response.text()
                raise RuntimeError(f"Gemini API error {response.status}: {error_text}")
            data = await response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError("Gemini API error: empty candidates")
            parts = candidates[0].get("content", {}).get("parts", [])
            content = "".join(part.get("text", "") for part in parts)
            return strip_llm_response_text(content)


async def get_mimo_response(messages, enable_search=False):
    """Call MiMo API and return the response text."""
    if not MIMO_ENABLED:
        raise RuntimeError("MiMo not configured")
    payload = build_mimo_payload(messages, enable_search=enable_search)
    headers = {
        "Authorization": f"Bearer {MIMO_API_KEY}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{MIMO_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise RuntimeError(f"MiMo API error {response.status}: {error_text}")
            data = await response.json()
            choices = data.get("choices", [])
            if not choices:
                raise RuntimeError("MiMo API error: empty choices")
            message = choices[0].get("message", {})
            content = message.get("content", "")
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                )
            return strip_llm_response_text(content)


async def get_llm_response(messages, enable_search=False):
    """Call the configured LLM provider and return the response text."""
    if not has_llm_content(messages):
        raise RuntimeError("LLM payload empty: no user content")
    if GEMINI_ENABLED:
        return await get_gemini_response(messages, enable_search=enable_search)
    if MIMO_ENABLED:
        return await get_mimo_response(messages, enable_search=enable_search)
    if OPENROUTER_ENABLED:
        return await get_openrouter_response(messages)
    if LLM_PROVIDER_ERROR:
        raise RuntimeError(LLM_PROVIDER_ERROR)
    raise RuntimeError("No LLM provider configured")


def estimate_llm_context_history_char_budget(*parts):
    window_chars = max(16000, LLM_CONTEXT_WINDOW_TOKENS * 4)
    parts_chars = sum(len(str(part or "")) for part in parts)
    reserved_chars = int(parts_chars * 1.35) + LLM_CONTEXT_SAFETY_BUFFER_CHARS
    available_chars = window_chars - reserved_chars
    return max(16000, min(LLM_CONTEXT_HISTORY_CHAR_BUDGET, available_chars))


async def build_llm_context_history(message, char_budget=None, include_bot_messages=True):
    context_history = []
    consumed_chars = 0
    budget = max(16000, int(char_budget or LLM_CONTEXT_HISTORY_CHAR_BUDGET))

    async for prev_msg in message.channel.history(
        limit=LLM_CONTEXT_HISTORY_MAX_MESSAGES,
        before=message,
    ):
        if not include_bot_messages and prev_msg.author == client.user:
            continue

        msg_content = strip_discord_mentions(prev_msg.content or "").strip()
        if not msg_content:
            continue

        msg_text = f"{prev_msg.author.display_name}: {msg_content}"
        msg_chars = len(msg_text) + 1

        if context_history and (consumed_chars + msg_chars) > budget:
            break

        context_history.append(msg_text)
        consumed_chars += msg_chars

        if consumed_chars >= budget:
            break

    context_history.reverse()
    return context_history


async def build_channel_context_history(
    channel,
    max_messages=None,
    char_budget=None,
    include_bot_messages=False,
):
    """Collect recent channel lines for scheduled context-aware messages."""
    context_history = []
    consumed_chars = 0
    limit = max(5, int(max_messages or ENCOURAGEMENT_CONTEXT_MAX_MESSAGES))
    budget = max(500, int(char_budget or ENCOURAGEMENT_CONTEXT_CHAR_BUDGET))

    async for prev_msg in channel.history(limit=limit):
        if not include_bot_messages and prev_msg.author == client.user:
            continue

        msg_content = strip_discord_mentions(prev_msg.content or "").strip()
        if not msg_content:
            continue

        msg_text = f"{prev_msg.author.display_name}: {msg_content}"
        msg_chars = len(msg_text) + 1

        if context_history and (consumed_chars + msg_chars) > budget:
            break

        context_history.append(msg_text)
        consumed_chars += msg_chars

        if consumed_chars >= budget:
            break

    context_history.reverse()
    return context_history


def build_contextual_encouragement_prompt(context_history):
    """Build a context-grounded prompt for scheduled daily takes."""
    if not context_history:
        return None
    context_text = "\n".join(context_history).strip()
    if not context_text:
        return None
    return ENCOURAGEMENT_CONTEXT_PROMPT_TEMPLATE.format(context_text=context_text)


def get_memory_file_path():
    path_text = str(MEMORY_FILE or "memory.md").strip()
    if os.path.isabs(path_text):
        return path_text
    return os.path.join(os.path.dirname(__file__), path_text)


def build_memory_file_text(entries=None):
    entries = [str(entry).strip() for entry in (entries or []) if str(entry).strip()]
    memory_lines = [f"- {entry}" for entry in entries]
    if not memory_lines:
        memory_lines = ["- No durable memory recorded yet."]
    memory_block = "\n".join(memory_lines)
    return (
        "# Memory\n\n"
        "This file stores durable information inferred from Discord conversations the bot reads and contributes to.\n\n"
        "Guidelines:\n"
        "- Keep only long-lived, useful facts.\n"
        "- Do not store secrets, tokens, or private data.\n"
        "- Prefer concise facts over summaries of jokes or transient chatter.\n\n"
        "<!-- MEMORY_START -->\n"
        f"{memory_block}\n"
        "<!-- MEMORY_END -->\n"
    )


def ensure_memory_file_exists():
    file_path = get_memory_file_path()
    if os.path.exists(file_path):
        return
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(build_memory_file_text())
    except Exception as e:
        print(f"[memory] create error: {e}", flush=True)


def _memory_body_from_text(file_text):
    match = re.search(
        r"<!-- MEMORY_START -->\s*(.*?)\s*<!-- MEMORY_END -->",
        str(file_text or ""),
        flags=re.DOTALL,
    )
    if not match:
        return ""
    return match.group(1).strip()


def _memory_strip_date_prefix(text):
    return re.sub(r"^\[[0-9]{4}-[0-9]{2}-[0-9]{2}\]\s*", "", str(text or "").strip())


def normalize_memory_entry(text):
    normalized = re.sub(r"\s+", " ", _memory_strip_date_prefix(text)).strip(" -\t\r\n")
    if not normalized or normalized.lower() == "no durable memory recorded yet.":
        return ""
    return normalized


def load_memory_entries():
    file_path = get_memory_file_path()
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            file_text = f.read()
    except Exception as e:
        print(f"[memory] load error: {e}", flush=True)
        return []

    body = _memory_body_from_text(file_text)
    entries = []
    for raw_line in body.splitlines():
        raw_line = raw_line.strip()
        if not raw_line.startswith("- "):
            continue
        entry = raw_line[2:].strip()
        if normalize_memory_entry(entry):
            entries.append(entry)
    return entries


def save_memory_entries(entries):
    file_path = get_memory_file_path()
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(build_memory_file_text(entries))
    except Exception as e:
        print(f"[memory] save error: {e}", flush=True)


def parse_memory_candidates(memory_text):
    candidates = []
    for raw_line in str(memory_text or "").splitlines():
        line = raw_line.strip()
        if not line or line.upper() == "NONE":
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        normalized = normalize_memory_entry(line)
        if normalized:
            candidates.append(normalized)
    return candidates[:3]


def append_memory_entries(new_entries):
    normalized_new_entries = [normalize_memory_entry(entry) for entry in (new_entries or [])]
    normalized_new_entries = [entry for entry in normalized_new_entries if entry]
    if not normalized_new_entries:
        return []

    existing_entries = load_memory_entries()
    existing_keys = {normalize_memory_entry(entry).lower() for entry in existing_entries if normalize_memory_entry(entry)}
    today = datetime.datetime.now().date().isoformat()
    added_entries = []

    for entry in normalized_new_entries:
        key = entry.lower()
        if key in existing_keys:
            continue
        added_entries.append(f"[{today}] {entry}")
        existing_keys.add(key)

    if not added_entries:
        return []

    merged_entries = added_entries + existing_entries
    save_memory_entries(merged_entries[:MEMORY_MAX_ENTRIES])
    return added_entries


def build_memory_context(max_entries=None, char_budget=None):
    entries = load_memory_entries()
    if not entries:
        return ""

    limit = max(1, int(max_entries or 8))
    budget = max(200, int(char_budget or 1200))
    selected = []
    consumed = 0
    for entry in entries[:limit]:
        line = f"- {entry}"
        line_len = len(line) + 1
        if selected and (consumed + line_len) > budget:
            break
        selected.append(line)
        consumed += line_len
    return "\n".join(selected)


async def capture_discord_memory(channel, recent_lines, source_label="conversation"):
    if not LLM_ENABLED:
        return

    compact_lines = [str(line).strip() for line in (recent_lines or []) if str(line).strip()]
    if not compact_lines:
        return

    transcript = "\n".join(compact_lines[-MEMORY_CONTEXT_MAX_MESSAGES:]).strip()
    if not transcript:
        return

    try:
        llm_messages = [
            {"role": "system", "content": MEMORY_PROMPT},
            {"role": "user", "content": f"Conversation transcript:\n{transcript}"},
        ]
        memory_reply = await get_llm_response(llm_messages)
        parsed_entries = parse_memory_candidates(memory_reply)
        added_entries = append_memory_entries(parsed_entries)
        if added_entries:
            print(
                f"[memory] {source_label} stored {len(added_entries)} entr{'y' if len(added_entries) == 1 else 'ies'}",
                flush=True,
            )
    except Exception as e:
        print(f"[memory] {source_label} capture error: {e}", flush=True)


async def capture_message_exchange_memory(message, source_label="reply"):
    msg_content = strip_discord_mentions(message.content or "").strip()
    if not msg_content:
        return

    context_history = []
    try:
        context_history = await build_llm_context_history(
            message,
            char_budget=MEMORY_CONTEXT_CHAR_BUDGET,
            include_bot_messages=False,
        )
    except Exception as e:
        print(f"[memory] context build error: {e}", flush=True)

    recent_lines = list(context_history[-MEMORY_CONTEXT_MAX_MESSAGES:])
    if msg_content:
        recent_lines.append(f"{message.author.display_name}: {msg_content}")
    await capture_discord_memory(
        message.channel,
        recent_lines,
        source_label=source_label,
    )


def truncate_message(text, limit=1800):
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def format_score(score):
    if not score:
        return "-"
    wins = score.get("wins") or 0
    losses = score.get("losses") or 0
    draws = score.get("draws") or 0
    diff = score.get("diff")
    ratio = score.get("ratio")
    details = []
    if diff is not None:
        details.append(f"diff {diff}")
    if ratio is not None:
        try:
            ratio_value = float(ratio)
            details.append(f"{ratio_value:.1f}%")
        except (TypeError, ValueError):
            details.append(f"{ratio}%")
    if details:
        return f"{wins}-{losses}-{draws} ({', '.join(details)})"
    return f"{wins}-{losses}-{draws}"


def format_date(date_text):
    if not date_text:
        return "-"
    return str(date_text).split("T")[0]


def format_search_results(results, limit=5):
    if not results:
        return "No fighters found."
    lines = []
    for entry in results[:limit]:
        fighter_id = entry.get("fighter_id", "?")
        short_id = entry.get("short_id", "?")
        character = entry.get("favorite_character", "?")
        mr = entry.get("master_rating")
        lp = entry.get("league_point")
        home = entry.get("home_country", "?")
        mr_text = "-" if mr in (None, 0) else str(mr)
        lp_text = "-" if lp in (None, 0) else str(lp)
        lines.append(f"{fighter_id} | ID {short_id} | {character} | MR {mr_text} LP {lp_text} | {home}")
    return "\n".join(lines)


def format_rivals_section(title, rivals):
    lines = [f"{title}:"]
    if not rivals:
        lines.append("none")
        return "\n".join(lines)
    for idx, rival in enumerate(rivals, start=1):
        name = rival.get("name", "?")
        character = rival.get("character", "?")
        input_type = rival.get("input_type", "?")
        score = format_score(rival.get("score"))
        lines.append(f"{idx}. {name} ({character}, {input_type}) {score}")
    return "\n".join(lines)


def format_matchups(matchups, limit=10):
    if not matchups:
        return "No matchups found."
    def matchup_key(entry):
        score = entry.get("score") or {}
        ratio = score.get("ratio") or 0
        total = score.get("total") or 0
        return (ratio, total)

    sorted_matchups = sorted(matchups, key=matchup_key, reverse=True)
    lines = []
    for entry in sorted_matchups[:limit]:
        character = entry.get("away_character", "?")
        input_type = entry.get("away_input_type", "?")
        score = format_score(entry.get("score"))
        lines.append(f"{character} ({input_type}) {score}")
    return "\n".join(lines)


def format_ranked_history(history, limit=10):
    if not history:
        return "No ranked history found."
    lines = []
    for item in history[-limit:]:
        played_at = format_date(item.get("played_at"))
        mr = item.get("mr")
        variation = item.get("mr_variation")
        if variation is None:
            variation_text = ""
        else:
            variation_text = f" ({variation:+})"
        lines.append(f"{played_at}: MR {mr}{variation_text}")
    return "\n".join(lines)


def format_matches(matches, limit=10):
    if not matches:
        return "No matches found."
    lines = []
    for match in matches[:limit]:
        played_at = format_date(match.get("played_at"))
        away = match.get("away", {})
        away_name = away.get("name", "?")
        away_character = away.get("character", "?")
        result = match.get("result", {}).get("name", "?")
        lines.append(f"{played_at}: vs {away_name} ({away_character}) result {result}")
    return "\n".join(lines)


def cfn_help_text():
    return (
        "CFN commands:\n"
        "cfn search <query>\n"
        "cfn status <uuid>\n"
        "cfn sync <short_id>\n"
        "cfn rivals <short_id>\n"
        "cfn matchup <short_id>\n"
        "cfn history <short_id>\n"
        "cfn matches <short_id>"
    )


def strip_discord_mentions(content):
    if not content:
        return ""
    stripped = MENTION_PATTERN.sub(" ", content)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped


def normalize_jump_normal_text(text):
    if not text:
        return ""
    strength_map = {
        "light": "l",
        "medium": "m",
        "heavy": "h",
    }
    button_map = {
        "punch": "p",
        "kick": "k",
    }

    def replace_named_jump(match):
        prefix = match.group(1) or ""
        strength = match.group(2)
        button = match.group(3)
        short = f"{strength_map[strength]}{button_map[button]}"
        if prefix:
            return f"neutral jump {short}"
        return f"jump {short}"

    text = re.sub(
        r"\b(?:(neutral|n)\s+)?jump\s+(light|medium|heavy)\s+(punch|kick)\b",
        replace_named_jump,
        text,
    )
    text = re.sub(r"\bneutral\s+j\s*\.?\s*([lmh][pk])\b", r"neutral jump \1", text)
    text = re.sub(r"\bn\.?j\s*([lmh][pk])\b", r"neutral jump \1", text)
    text = re.sub(r"\bnj\s*([lmh][pk])\b", r"neutral jump \1", text)
    text = re.sub(r"\bj\s*\.?\s*([lmh][pk])\b", r"jump \1", text)
    text = re.sub(r"\bn\.?j\s*\.?\s*([1-9][0-9]*[a-z]{1,3})\b", r"neutral j\1", text)
    text = re.sub(r"\bnj\s*([1-9][0-9]*[a-z]{1,3})\b", r"neutral j\1", text)
    text = re.sub(r"\bj\s*\.?\s*([1-9][0-9]*[a-z]{1,3})\b", r"j\1", text)
    return text


def extract_cfn_command(message):
    content = message.content.strip()
    if not content:
        return None
    if client.user and client.user.mentioned_in(message):
        content_no_mentions = strip_discord_mentions(content)
        if not content_no_mentions:
            return None
        content_no_mentions_lower = content_no_mentions.lower()
        if content_no_mentions_lower.startswith("cfn"):
            return content_no_mentions[3:].strip()
    return None


def is_valid_short_id(value):
    return bool(re.fullmatch(r"\d{9,}", value or ""))


async def handle_cfn_command(message):
    command_text = extract_cfn_command(message)
    if command_text is None:
        return False

    if not sfbuff_integration.is_configured():
        await message.reply("CFN service is not configured.")
        return True

    return await handle_cfn_site_command(message, command_text)


async def handle_cfn_site_command(message, command_text):
    tokens = command_text.split()
    if not tokens:
        await message.reply(cfn_help_text())
        return True

    action = tokens[0].lower()
    if action in {"help", "?"}:
        await message.reply(cfn_help_text())
        return True

    async with message.channel.typing():
        if action == "search":
            if len(tokens) < 2:
                await message.reply("Usage: cfn search <query>")
                return True
            query = " ".join(tokens[1:]).strip()
            payload = await sfbuff_integration.search(query)
            if payload.get("_error"):
                await message.reply(truncate_message(f"CFN search error: {payload.get('body')}"))
                return True
            if payload.get("finished"):
                response = format_search_results(payload.get("result"))
            else:
                response = (
                    f"Search queued (uuid {payload.get('uuid')}). "
                    "Try again in a few seconds with `@north korean bub cfn status <uuid>`."
                )
            await message.reply(truncate_message(response))
            return True

        if action == "status":
            if len(tokens) < 2:
                await message.reply("Usage: cfn status <uuid>")
                return True
            uuid = tokens[1]
            payload = await sfbuff_integration.search_status(uuid)
            if payload.get("_error"):
                await message.reply(truncate_message(f"CFN status error: {payload.get('body')}"))
                return True
            if payload.get("finished"):
                response = format_search_results(payload.get("result"))
            else:
                response = (
                    f"Search still running (uuid {payload.get('uuid')}). "
                    "Try again in a few seconds."
                )
            await message.reply(truncate_message(response))
            return True

        if action in {"sync", "rivals", "matchup", "history", "matches"}:
            if len(tokens) < 2:
                await message.reply(f"Usage: cfn {action} <short_id>")
                return True
            fighter_id = tokens[1]
            if not is_valid_short_id(fighter_id):
                await message.reply("CFN short_id must be at least 9 digits.")
                return True

            if action == "sync":
                payload = await sfbuff_integration.sync(fighter_id)
                if payload.get("_error"):
                    await message.reply(truncate_message(f"CFN sync error: {payload.get('body')}"))
                    return True
                await message.reply(f"Sync started for {fighter_id} on sfbuff.site.")
                return True

            if action == "rivals":
                payload = await sfbuff_integration.rivals(fighter_id)
                if payload.get("_error"):
                    await message.reply(truncate_message(f"CFN rivals error: {payload.get('body')}"))
                    return True
                sections = [
                    format_rivals_section("Favorites", payload.get("favorites")),
                    format_rivals_section("Victims", payload.get("victims")),
                    format_rivals_section("Tormentors", payload.get("tormentors")),
                ]
                await message.reply(truncate_message("\n\n".join(sections)))
                return True

            if action == "matchup":
                payload = await sfbuff_integration.matchups(fighter_id)
                if isinstance(payload, dict) and payload.get("_error"):
                    await message.reply(truncate_message(f"CFN matchup error: {payload.get('body')}"))
                    return True
                response = format_matchups(payload)
                await message.reply(truncate_message(response))
                return True

            if action == "history":
                payload = await sfbuff_integration.history(fighter_id)
                if isinstance(payload, dict) and payload.get("_error"):
                    await message.reply(truncate_message(f"CFN history error: {payload.get('body')}"))
                    return True
                response = format_ranked_history(payload)
                await message.reply(truncate_message(response))
                return True

            if action == "matches":
                payload = await sfbuff_integration.matches(fighter_id)
                if isinstance(payload, dict) and payload.get("_error"):
                    await message.reply(truncate_message(f"CFN matches error: {payload.get('body')}"))
                    return True
                response = format_matches(payload)
                await message.reply(truncate_message(response))
                return True

    await message.reply(cfn_help_text())
    return True


FRAME_DATA = {}
FRAME_STATS = {}
BNB_DATA = {}
OKI_DATA = {}
CHARACTER_INFO = {}
HITBOX_GIF_DATA = {}
RANGE_DATA = {}

CHARACTER_ALIASES = {
    "kim": "kimberly",
    "gief": "zangief",
    "sim": "dhalsim",
    "aksel": "alex",
    "chun": "chun-li",
    "dj": "dee jay",
    "deejay": "dee jay",
    "honda": "e.honda",
    "bison": "m.bison",
    "m bison": "m.bison",
    "dictator": "m.bison",
    "viper": "c.viper",
    "c viper": "c.viper",
    "aki": "a.k.i",
    "a.k.i": "a.k.i",
    "a.k.i.": "a.k.i",
}


def normalize_char_name(name: str) -> str:
    """Normalize character name to lowercase alphanumeric."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def resolve_character_key(name: str):
    """Resolve free-form character text to a FRAME_DATA key."""
    normalized = normalize_char_name(name)
    if not normalized:
        return None

    for char_key in FRAME_DATA.keys():
        if normalize_char_name(char_key) == normalized:
            return char_key

    for alias, canonical in CHARACTER_ALIASES.items():
        if normalize_char_name(alias) == normalized and canonical in FRAME_DATA:
            return canonical

    return None


def format_sheet_text(df: pd.DataFrame) -> str:
    """Convert DataFrame rows to pipe-separated text lines."""
    df = df.fillna("")
    lines = []
    for _, row in df.iterrows():
        values = []
        for val in row.tolist():
            text = str(val).strip()
            if text.lower() == "nan":
                text = ""
            values.append(text)
        while values and values[0] == "":
            values.pop(0)
        while values and values[-1] == "":
            values.pop()
        if not values:
            continue
        lines.append(" | ".join(values))
    return "\n".join(lines)

def load_frame_data():
    """Load frame data, stats, combos, oki, and character info from ODS."""
    global FRAME_DATA, FRAME_STATS, BNB_DATA, OKI_DATA, CHARACTER_INFO, HITBOX_GIF_DATA, RANGE_DATA, QUIZ_CHARACTER_TERMS_CACHE, QUIZ_MOVE_NAME_TERMS_CACHE, QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE
    filename = "FAT - SF6 Frame Data.ods"
    QUIZ_CHARACTER_TERMS_CACHE = None
    QUIZ_MOVE_NAME_TERMS_CACHE = None
    QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE = None
    
    if os.path.exists(filename):
        try:
            print(f"Loading ODS file: {filename} (This may take a moment)...")
            # Load the entire workbook
            xls = pd.ExcelFile(filename, engine='odf')
            
            # Iterate through all sheet names
            for sheet_name in xls.sheet_names:
                # Look for sheets ending in "Normal" (e.g. "ManonNormal", "RyuNormal")
                if sheet_name.endswith("Normal"):
                    # Extract character name (ManonNormal -> manon)
                    char_name = sheet_name.replace("Normal", "").rstrip(".").lower()
                    
                    # Parse the sheet
                    df = pd.read_excel(xls, sheet_name=sheet_name)
                    
                    # Convert to list of dicts (replace NaN with empty string)
                    records = df.fillna("").to_dict('records')
                    
                    # Inject character name into each record for reverse lookup context
                    for r in records: r['char_name'] = char_name.capitalize()
                    
                    FRAME_DATA[char_name] = records
                    # print(f"Loaded {len(records)} moves for {char_name}")
                
                # Look for sheets ending in "Stats" (e.g. "ManonStats", "RyuStats")
                elif sheet_name.endswith("Stats") and not sheet_name.startswith("_OLD"):
                    char_name = sheet_name.replace("Stats", "").rstrip(".").lower()
                    df = pd.read_excel(xls, sheet_name=sheet_name)
                
                    stats_dict = dict(zip(df['name'], df['stat']))
                    FRAME_STATS[char_name] = stats_dict
                    # print(f"Loaded stats for {char_name}")

            def normalize_loader_move_key(move_name, num_cmd):
                normalized_name = re.sub(r"[^a-z0-9]+", "", str(move_name or "").lower())
                normalized_num_cmd = re.sub(r"\([^)]*\)", "", str(num_cmd or "").lower())
                normalized_num_cmd = re.sub(r"\s+", "", normalized_num_cmd)
                normalized_num_cmd = re.sub(r"[^a-z0-9>]", "", normalized_num_cmd)
                return normalized_name, normalized_num_cmd

            # Jamie's drink-gated moves live on the drink-level sheets rather than JamieNormal.
            # Merge unique rows so parser/lookup sees the full ODS moveset from one character key.
            if "jamie" in FRAME_DATA:
                jamie_extra_sheets = [
                    name for name in xls.sheet_names
                    if re.fullmatch(r"JamieD[1-4]", str(name or ""), re.IGNORECASE)
                ]
                existing_jamie_keys = {
                    normalize_loader_move_key(row.get("moveName", ""), row.get("numCmd", ""))
                    for row in FRAME_DATA["jamie"]
                    if str(row.get("moveName", "")).strip() and str(row.get("numCmd", "")).strip()
                }
                for sheet_name in sorted(jamie_extra_sheets, key=str.lower):
                    df = pd.read_excel(xls, sheet_name=sheet_name)
                    records = df.fillna("").to_dict("records")
                    for row in records:
                        move_name = str(row.get("moveName", "")).strip()
                        num_cmd = str(row.get("numCmd", "")).strip()
                        if not move_name or not num_cmd:
                            continue
                        row_key = normalize_loader_move_key(move_name, num_cmd)
                        if row_key in existing_jamie_keys:
                            continue
                        row["char_name"] = "Jamie"
                        FRAME_DATA["jamie"].append(row)
                        existing_jamie_keys.add(row_key)
            
            print(f"Total characters loaded: {len(FRAME_DATA)}")
            print(f"Total stats loaded: {len(FRAME_STATS)}")
            
            BNB_DATA = {}
            OKI_DATA = {}
            CHARACTER_INFO = {}
            HITBOX_GIF_DATA = {}
            RANGE_DATA = {}
            normalized_chars = {
                normalize_char_name(name): name
                for name in FRAME_DATA.keys()
            }

            character_lookup = dict(normalized_chars)
            for alias, canonical in CHARACTER_ALIASES.items():
                if canonical in FRAME_DATA:
                    character_lookup[normalize_char_name(alias)] = canonical
                    character_lookup[normalize_char_name(canonical)] = canonical

            def normalize_range_cmd_token(value):
                raw_text = str(value or "").lower()
                is_air_context = bool(
                    "(air" in raw_text
                    or raw_text.startswith("j.")
                    or raw_text.startswith("j ")
                    or raw_text.startswith("j")
                    or "jump" in raw_text
                )
                text = raw_text
                text = text.replace("->", ">")
                text = text.replace("~", ">")
                text = text.replace("|", "/")
                text = re.sub(r"\bor\b", "/", text)
                text = re.sub(r"\([^)]*\)", "", text)
                text = re.sub(r"\s+", "", text)
                text = re.sub(r"[^a-z0-9>/+]", "", text)
                text = text.replace("+", "")
                text = re.sub(r"^j42684268", "j720", text)
                text = re.sub(r"^42684268", "720", text)
                text = re.sub(r"^j4268", "j360", text)
                text = re.sub(r"^4268", "360", text)
                if is_air_context and re.match(r"^(360|720)", text):
                    text = f"j{text}"
                return text

            def build_range_cmd_tokens(value):
                normalized = normalize_range_cmd_token(value)
                if not normalized:
                    return []
                tokens = []
                for part in normalized.split("/"):
                    token = part.strip()
                    if not token:
                        continue
                    if token not in tokens:
                        tokens.append(token)
                    if token.startswith("5") and len(token) > 1:
                        token_without_five = token[1:]
                        if token_without_five and token_without_five not in tokens:
                            tokens.append(token_without_five)
                return tokens

            def choose_preferred_range(values):
                cleaned_values = [str(value).strip() for value in values if str(value).strip()]
                if not cleaned_values:
                    return ""
                for value in cleaned_values:
                    if not is_missing_attack_range_value(value):
                        return value
                return ""

            range_sheet_name = next(
                (name for name in xls.sheet_names if name.lower() in {"range", "ranges"}),
                None,
            )
            if range_sheet_name:
                range_df = pd.read_excel(xls, sheet_name=range_sheet_name, dtype=str).fillna("")
                for range_row in range_df.to_dict("records"):
                    char_raw = str(range_row.get("chara", "")).strip()
                    input_raw = str(range_row.get("input", "")).strip()
                    atk_range_raw = str(range_row.get("atkRange", "")).strip()
                    if not char_raw or not input_raw:
                        continue
                    char_key = character_lookup.get(normalize_char_name(char_raw))
                    if not char_key:
                        continue
                    for token in build_range_cmd_tokens(input_raw):
                        RANGE_DATA.setdefault(char_key, {}).setdefault(token, []).append(atk_range_raw)
            else:
                print("Range sheet not found: ranges")

            for char_key, records in FRAME_DATA.items():
                char_ranges = RANGE_DATA.get(char_key, {})
                for row in records:
                    row_tokens = []
                    for token in build_range_cmd_tokens(row.get("numCmd", "")):
                        if token not in row_tokens:
                            row_tokens.append(token)
                    for token in build_num_cmd_candidates_for_gif(row):
                        for variant in build_range_cmd_tokens(token):
                            if variant not in row_tokens:
                                row_tokens.append(variant)

                    selected_range = ""
                    for token in row_tokens:
                        if token not in char_ranges:
                            continue
                        selected_range = choose_preferred_range(char_ranges[token])
                        if selected_range:
                            break
                    row["atkRange"] = selected_range

            gif_sheet_name = next(
                (name for name in xls.sheet_names if name.lower() == "hitboxgiflinks"),
                None,
            )
            if gif_sheet_name:
                gif_df = pd.read_excel(xls, sheet_name=gif_sheet_name, dtype=str).fillna("")
                for gif_row in gif_df.to_dict("records"):
                    move_link = str(gif_row.get("moveLink", "")).strip()
                    if not move_link:
                        continue
                    char_raw = str(gif_row.get("character", "")).strip()
                    char_key = character_lookup.get(normalize_char_name(char_raw))
                    if not char_key:
                        continue
                    HITBOX_GIF_DATA.setdefault(char_key, []).append({
                        "moveName": str(gif_row.get("moveName", "")).strip(),
                        "numCmd": str(gif_row.get("numCmd", "")).strip(),
                        "moveLink": move_link,
                    })
            else:
                print("Hitbox gif sheet not found: hitboxgiflinks")

            combo_sheets = [
                name for name in xls.sheet_names
                if name.lower().endswith(" combos")
            ]
            oki_sheets = [
                name for name in xls.sheet_names
                if name.lower().endswith(" okisetups")
                or name.lower().endswith(" setupsoki")
            ]

            for sheet_name in combo_sheets:
                char_label = sheet_name[:-len(" combos")]
                char_key = normalized_chars.get(normalize_char_name(char_label))
                if not char_key:
                    continue
                df = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=str)
                combo_text = format_sheet_text(df)
                if combo_text:
                    BNB_DATA[char_key] = combo_text

            for sheet_name in oki_sheets:
                suffix = " okisetups" if sheet_name.lower().endswith(" okisetups") else " setupsoki"
                char_label = sheet_name[:-len(suffix)]
                char_key = normalized_chars.get(normalize_char_name(char_label))
                if not char_key:
                    continue
                df = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=str)
                oki_text = format_sheet_text(df)
                if oki_text:
                    OKI_DATA[char_key] = oki_text

            for sheet_name in xls.sheet_names:
                lower_name = sheet_name.lower()
                if lower_name.endswith(" combos"):
                    continue
                if lower_name.endswith(" okisetups") or lower_name.endswith(" setupsoki"):
                    continue
                if lower_name.endswith(" frame data"):
                    continue
                normalized_name = normalize_char_name(sheet_name)
                char_key = normalized_chars.get(normalized_name)
                if not char_key:
                    continue
                df = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=str)
                info_text = format_sheet_text(df)
                if info_text:
                    CHARACTER_INFO[char_key] = info_text

            print(f"Total combo sheets loaded: {len(BNB_DATA)} characters")
            print(f"Total oki sheets loaded: {len(OKI_DATA)} characters")
            print(f"Total character info sheets loaded: {len(CHARACTER_INFO)} characters")
            total_hitbox_gifs = sum(len(entries) for entries in HITBOX_GIF_DATA.values())
            total_ranges = sum(len(entries) for entries in RANGE_DATA.values())
            print(f"Total hitbox gif links loaded: {total_hitbox_gifs}")
            print(f"Total range inputs loaded: {total_ranges}")
            
        except Exception as e:
            print(f"Error loading {filename}: {e}")
    else:
        print(f"File not found: {filename}")

def find_moves_in_text(text):
    """Extract character/move mentions and return context payload with mode."""
    found_data = []
    text_lower = strip_discord_mentions(text).lower()
    text_lower = normalize_jump_normal_text(text_lower)
    text_lower = re.sub(r"\bdivekick\b", "dive kick", text_lower)
    tc_prompt_blocks = []
    special_prompt_blocks = []
    tc_ambiguous_inputs = set()
    text_tokens = re.findall(r"[a-z0-9]+", text_lower)

    def tokens_in_haystack(haystack_tokens, needle_tokens):
        if not needle_tokens:
            return False
        if len(needle_tokens) == 1:
            return needle_tokens[0] in haystack_tokens
        for i in range(len(haystack_tokens) - len(needle_tokens) + 1):
            if haystack_tokens[i : i + len(needle_tokens)] == needle_tokens:
                return True
        return False

    def tokens_in_text(needle_tokens):
        return tokens_in_haystack(text_tokens, needle_tokens)
    
    # 1. Identify which characters are mentioned
    mentioned_chars = []
    
    # First check for character aliases and normalize them
    for alias, canonical in CHARACTER_ALIASES.items():
        alias_tokens = re.findall(r"[a-z0-9]+", alias.lower())
        if tokens_in_text(alias_tokens):
            if canonical in FRAME_DATA and canonical not in mentioned_chars:
                mentioned_chars.append(canonical)
    
    # Then check for direct character name matches
    for char in FRAME_DATA.keys():
        char_tokens = re.findall(r"[a-z0-9]+", char)
        if tokens_in_text(char_tokens) and char not in mentioned_chars:
            mentioned_chars.append(char)

    if not mentioned_chars and (
        re.search(r"\braging\s+demon\b", text_lower)
        or re.search(r"\bshun\s+goku\s+satsu\b", text_lower)
    ):
        if "akuma" in FRAME_DATA:
            mentioned_chars.append("akuma")
    
    # Check for BNB/Combo requests
    bnb_keywords = ["combo", "combos", "bnb", "bnbs", "bread and butter", "route", "routes"]
    oki_keywords = ["oki", "okizeme", "setup", "setups", "meaty", "meaties"]
    info_keywords = [
        "playstyle",
        "gameplan",
        "archetype",
        "overview",
        "tell me about",
        "who is",
        "strengths",
        "weaknesses",
        "moveset",
        "toolkit",
        "role",
        "how to play",
        "character synopsis",
        "summary",
        "anti air",
        "anti-air",
        "neutral",
        "win condition",
    ]
    frame_keywords = [
        "frame data",
        "framedata",
        "startup",
        "start up",
        "recovery",
        "active",
        "on block",
        "on hit",
        "hitstun",
        "blockstun",
        "frames",
    ]
    gif_query = bool(
        re.search(r"\bgif(?:s)?\b", text_lower)
        or re.search(r"\bhit\s*box(?:es)?\b", text_lower)
        or re.search(r"\bhitbox(?:es)?\b", text_lower)
        or ".gif" in text_lower
    )
    startup_alias_query = bool(
        re.search(r"\bhow\s+fast\b", text_lower)
        or re.search(r"\bhow\s+quick\b", text_lower)
        or re.search(r"\bspeed\s+of\b", text_lower)
        or (
            re.search(r"\bfast\b", text_lower)
            and re.search(r"\b[1-9][0-9]*[a-zA-Z]{1,3}\b", text_lower)
        )
    )
    hitconfirm_alias_query = bool(
        re.search(r"\bhit\s*-?\s*confirm\b", text_lower)
        or re.search(r"\bhitconfirm\b", text_lower)
        or re.search(r"\bhc\b", text_lower)
        or re.search(r"\bconfirm\s+window\b", text_lower)
        or re.search(r"\bconfirm\s+timing\b", text_lower)
        or re.search(r"\bconfirmable\b", text_lower)
        or re.search(r"\bconfirm\b", text_lower)
    )
    super_gain_alias_query = bool(
        re.search(r"\bsuper\s*gain\b", text_lower)
        or re.search(r"\bsuper\s*meter\s*gain\b", text_lower)
        or re.search(r"\bmeter\s*gain\b", text_lower)
        or re.search(r"\bsuper\s*build\b", text_lower)
        or re.search(r"\bsa\s*gain\b", text_lower)
    )
    range_alias_query = bool(
        (
            re.search(r"\brange\b", text_lower)
            or re.search(r"\blength\b", text_lower)
        )
        and not re.search(r"\bin\s+range\b", text_lower)
    )
    property_alias_flags = {
        "startup": startup_alias_query
        or bool(re.search(r"\bstart\s*up\b|\bstartup\b", text_lower)),
        "active": bool(re.search(r"\bactive\b|\bactive\s+frames?\b", text_lower)),
        "recovery": bool(re.search(r"\brecovery\b", text_lower)),
        "on_hit": bool(re.search(r"\bon\s+hit\b", text_lower)),
        "on_block": bool(re.search(r"\bon\s+block\b|\bplus\s+on\s+block\b|\bminus\s+on\s+block\b", text_lower)),
        "cancel": bool(re.search(r"\bcancel(?:l?able)?\b", text_lower)),
        "damage": bool(re.search(r"\bdamage\b|\bdmg\b", text_lower)),
        "drive_chip": bool(re.search(r"\bdrive\s+chip\b|\bdrive\s+dmg\b|\bdrive\s+damage\b", text_lower)),
        "drive_gain": bool(re.search(r"\bdrive\s+gain\b", text_lower)),
        "stun": bool(re.search(r"\bhitstun\b|\bblockstun\b|\bstun\b", text_lower)),
        "hitconfirm": hitconfirm_alias_query,
        "super_gain": super_gain_alias_query,
        "range": range_alias_query,
    }
    property_match_count = sum(1 for matched in property_alias_flags.values() if matched)
    table_intent_query = bool(
        re.search(r"\ball\s+frames?\b", text_lower)
        or re.search(r"\bfull\s+frames?\b", text_lower)
        or re.search(r"\bfull\s+frame\s*data\b", text_lower)
        or re.search(r"\btable\b", text_lower)
    )
    property_only_query = bool(property_match_count == 1 and not table_intent_query)
    comparison_keywords = [
        "which is better",
        "which is faster",
        "compare",
        "comparison",
        "versus",
    ]
    punish_keywords = ["punish", "punishable", "can i punish", "is it punishable"]
    target_combo_query = bool(re.search(r"\b(tc|target\s+combo|targetcombo)\b", text_lower))
    special_grab_query = bool(re.search(r"\b(command\s+grab|spd|piledriver|typhoon)\b", text_lower))
    wants_bnb = any(kw in text_lower for kw in bnb_keywords) and not target_combo_query
    wants_oki = any(kw in text_lower for kw in oki_keywords)
    wants_info = any(kw in text_lower for kw in info_keywords)
    wants_comparison = (
        any(kw in text_lower for kw in comparison_keywords)
        or re.search(r"\bvs\b", text_lower)
        or (len(mentioned_chars) >= 2 and re.search(r"\band\b", text_lower))
    )
    wants_frame_data = (
        any(kw in text_lower for kw in frame_keywords)
        or any(kw in text_lower for kw in punish_keywords)
        or wants_comparison
        or startup_alias_query
        or hitconfirm_alias_query
        or super_gain_alias_query
        or range_alias_query
        or target_combo_query
        or gif_query
    )
    bnb_context = ""
    info_blocks = []
    if wants_bnb or wants_oki:
        for char in mentioned_chars:
            if wants_bnb and char in BNB_DATA:
                bnb_context += f"\n\n**{char.capitalize()} Combos:**\n{BNB_DATA[char]}"
            if (wants_bnb or wants_oki) and char in OKI_DATA:
                bnb_context += f"\n\n**{char.capitalize()} Oki/Setups:**\n{OKI_DATA[char]}"
    results = []
    tc_selected_combos = set()
    tc_base_tokens = set()
    query_has_explicit_strength = False
    explicit_move_attempt = False
    missing_scrolls_query = False
    comparison_char_inputs = {}
    if wants_frame_data:
        # 2. Heuristic: For each mentioned character, search for moves mentioned nearby?
        # Simpler approach: Check if any move inputs are present in the text
        # that map to these characters.

        query_requires_denjin = "denjin" in text_tokens
        query_requires_charged = any(token in text_tokens for token in ("charged", "hold", "held"))
        query_requests_sa1 = bool(
            re.search(r"\b(?:sa\s*1|super\s*art\s*1|super\s*1|level\s*1)\b", text_lower)
        )
        query_requests_sa2 = bool(
            re.search(r"\b(?:sa\s*2|super\s*art\s*2|super\s*2|level\s*2)\b", text_lower)
        )
        query_requests_sa3 = bool(
            re.search(r"\b(?:sa\s*3|super\s*art\s*3|super\s*3|level\s*3)\b", text_lower)
        )
        query_requests_ca = bool(
            re.search(r"\b(?:ca|critical\s+art)\b", text_lower)
        )
        stock_hint_tokens = ("stock", "stocked", "enhanced", "windclad")

        def token_is_stock_hint(token):
            token_norm = str(token or "").lower().strip()
            if not token_norm:
                return False
            if token_norm in stock_hint_tokens:
                return True
            return any(
                difflib.SequenceMatcher(None, token_norm, hint_token).ratio() >= 0.82
                for hint_token in stock_hint_tokens
            )

        query_requires_stocked = any(
            token in text_tokens for token in ("stock", "stocked", "enhanced", "windclad")
        ) or bool(re.search(r"\bwind\s+clad\b", text_lower)) or any(
            token_is_stock_hint(token) for token in text_tokens
        )

        def row_is_denjin_variant(row):
            move_name = str(row.get("moveName", "")).lower()
            cmn_name = str(row.get("cmnName", "")).lower()
            num_cmd = str(row.get("numCmd", "")).lower()
            return (
                "denjin" in move_name
                or "denjin" in cmn_name
                or "charged" in move_name
                or "charged" in cmn_name
                or "(charged)" in num_cmd
            )

        def row_is_charged_variant(row):
            move_name = str(row.get("moveName", "")).lower()
            cmn_name = str(row.get("cmnName", "")).lower()
            num_cmd = str(row.get("numCmd", "")).lower()
            return (
                "charged" in move_name
                or "charged" in cmn_name
                or "hold" in move_name
                or "hold" in cmn_name
                or "(charged" in num_cmd
                or "(hold" in num_cmd
            )

        def row_is_od_variant(row):
            move_name = str(row.get("moveName", "")).lower().strip()
            cmn_name = str(row.get("cmnName", "")).lower().strip()
            num_cmd_compact = re.sub(r"[^a-z0-9]", "", str(row.get("numCmd", "")).lower())
            return (
                move_name.startswith(("od ", "ex "))
                or cmn_name.startswith(("od ", "ex "))
                or num_cmd_compact.endswith(("pp", "kk"))
            )

        def row_matches_explicit_strength(row, strength_query_text):
            row_move_name = str(row.get("moveName", "")).lower().strip()
            row_cmn_name = str(row.get("cmnName", "")).lower().strip()
            row_num_cmd = str(row.get("numCmd", "")).lower().strip()
            row_num_cmd_compact = re.sub(r"[^a-z0-9]", "", row_num_cmd)

            if re.search(r"\b(?:od|ex)\b", strength_query_text):
                return row_is_od_variant(row)

            strength_groups = [
                ({"light", "l", "lp", "lk"}, {"lp", "lk"}),
                ({"medium", "m", "mp", "mk"}, {"mp", "mk"}),
                ({"heavy", "h", "hp", "hk"}, {"hp", "hk"}),
            ]

            requested_suffixes = set()
            for token_group, suffixes in strength_groups:
                if any(re.search(rf"\b{re.escape(token)}\b", strength_query_text) for token in token_group):
                    requested_suffixes.update(suffixes)

            if not requested_suffixes:
                return False

            if any(row_move_name.startswith(f"{suffix} ") or row_cmn_name.startswith(f"{suffix} ") for suffix in requested_suffixes):
                return True
            if any(
                row_move_name.startswith(f"{word} ") or row_cmn_name.startswith(f"{word} ")
                for word in ("light", "medium", "heavy")
                if word[0] in {suffix[0] for suffix in requested_suffixes}
            ):
                return True
            return row_num_cmd_compact.endswith(tuple(requested_suffixes))

        def row_matches_query_move_terms(row):
            ignored_tokens = {
                "framedata", "frame", "frames", "data", "gif", "gifs", "hitbox", "hitboxes",
                "light", "medium", "heavy", "l", "m", "h",
                "lp", "mp", "hp", "lk", "mk", "hk", "pp", "kk",
                "od", "ex", "charged", "hold", "held",
                "startup", "active", "recovery", "range",
                "on", "hit", "block", "damage", "cancel",
            }
            for char in mentioned_chars:
                ignored_tokens.update(re.findall(r"[a-z0-9]+", str(char).lower()))
            for alias, canonical in CHARACTER_ALIASES.items():
                if canonical in mentioned_chars:
                    ignored_tokens.update(re.findall(r"[a-z0-9]+", str(alias).lower()))

            significant_tokens = [
                token for token in text_tokens
                if token not in ignored_tokens and len(token) >= 3
            ]
            if not significant_tokens:
                return True

            row_text = " ".join(
                str(row.get(field, "")).lower()
                for field in ("moveName", "cmnName", "numCmd", "plnCmd")
            )
            row_text_compact = re.sub(r"[^a-z0-9]", "", row_text)
            for token in significant_tokens:
                token_compact = re.sub(r"[^a-z0-9]", "", token)
                if not token_compact:
                    continue
                if token in row_text or token_compact in row_text_compact:
                    continue
                return False
            return True

        def row_is_ca_variant(row):
            move_name = str(row.get("moveName", "")).lower()
            cmn_name = str(row.get("cmnName", "")).lower()
            num_cmd = str(row.get("numCmd", "")).lower()
            return (
                "critical art" in move_name
                or "critical art" in cmn_name
                or bool(re.search(r"\(\s*ca\s*\)", num_cmd))
            )

        def row_is_stocked_variant(row):
            move_name = str(row.get("moveName", "")).lower()
            cmn_name = str(row.get("cmnName", "")).lower()
            num_cmd = str(row.get("numCmd", "")).lower()
            combined = f"{move_name} {cmn_name} {num_cmd}"
            if re.search(r"\b0\s*stocks?\b", combined):
                return False

            has_stock_count = bool(re.search(r"\b[1-9]\d*\s*stocks?\b", combined))
            has_stock_tag = "(stock" in move_name or "(stock" in cmn_name or "(stock" in num_cmd
            has_enhanced_tag = (
                "enhanced" in move_name
                or "enhanced" in cmn_name
                or "(enhanced" in num_cmd
            )
            has_windclad_tag = "windclad" in move_name or "windclad" in cmn_name
            has_wind_stock_hold = "wind stock" in cmn_name and (
                "(" in cmn_name or "(hold" in num_cmd
            )
            return (
                has_stock_count
                or has_stock_tag
                or has_enhanced_tag
                or has_windclad_tag
                or has_wind_stock_hold
            )

    
        move_regex = r"\b([1-9][0-9]*[a-zA-Z]+|stand\s+[a-zA-Z]+|crouch\s+[a-zA-Z]+|(?:neutral\s+|n\s+)?jump\s+[a-zA-Z]+|(?:neutral\s+|n\s+)?jump\s+[1-9][0-9]*[a-zA-Z]+|(?:neutral\s+|n\s+)?j(?:\s+|\.)[a-zA-Z]+|(?:neutral\s+|n\s+)?j(?:\s+|\.)[1-9][0-9]*[a-zA-Z]+|(?:neutral\s+|n\s+)?j\.?[1-9][0-9]*[a-zA-Z]+|(?:lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\s+[a-zA-Z]+(?:\s+[a-zA-Z]+)?|[a-zA-Z]+\s+kick|[a-zA-Z]+\s+punch)\b"
        potential_inputs = re.findall(move_regex, text_lower)
        compact_motion_inputs = []
        motion_button_matches = re.findall(
            r"\b([1-9][0-9]{1,4})\s*(?:\+)?\s*(lp|mp|hp|lk|mk|hk|pp|kk|p|k)\b",
            text_lower,
        )
        for motion_digits, button_suffix in motion_button_matches:
            compact_motion = f"{motion_digits}{button_suffix}"
            if compact_motion not in compact_motion_inputs:
                compact_motion_inputs.append(compact_motion)

        boomer_normal_matches = re.findall(
            r"\b(st|cr)\s*\.?\s*(lp|mp|hp|lk|mk|hk|l\s*p|m\s*p|h\s*p|l\s*k|m\s*k|h\s*k)\b",
            text_lower,
        )
        for stance_token, button_token in boomer_normal_matches:
            stance_prefix = "5" if stance_token == "st" else "2"
            normalized_button = re.sub(r"\s+", "", button_token)
            compact_motion = f"{stance_prefix}{normalized_button}"
            if compact_motion not in compact_motion_inputs:
                compact_motion_inputs.append(compact_motion)

        if compact_motion_inputs:
            potential_inputs = compact_motion_inputs + potential_inputs
        strength_prefix_pattern = re.compile(r"^(lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b")
        strength_prefixes_for_filter = [
            "lp", "mp", "hp", "lk", "mk", "hk",
            "light", "medium", "heavy", "l", "m", "h",
        ]
        filtered_inputs = []
        for inp in potential_inputs:
            if not inp:
                continue
            original_inp = str(inp).strip().lower()
            cleaned_inp = re.sub(r"\s+framedata$", "", inp).strip()
            cleaned_inp = re.sub(r"\s+frame\s*data$", "", cleaned_inp).strip()
            cleaned_inp = re.sub(r"\s+frame$", "", cleaned_inp).strip()
            cleaned_inp = re.sub(
                r"\s+(?:gif|gifs|hitbox|hitboxes)(?:\s+link)?$",
                "",
                cleaned_inp,
            ).strip()
            if not cleaned_inp:
                continue
            if cleaned_inp in strength_prefixes_for_filter and re.search(
                r"\b(frame\s*data|framedata|frame|data|gif|gifs|hitbox|hitboxes|startup|recovery|active|stats|punish|punishable)\b",
                original_inp,
            ):
                continue
            if not strength_prefix_pattern.match(cleaned_inp):
                if any(
                    re.search(
                        rf"\b{re.escape(prefix)}\s+{re.escape(cleaned_inp)}\b",
                        text_lower,
                    )
                    for prefix in strength_prefixes_for_filter
                ):
                    continue
            filtered_inputs.append(cleaned_inp)
        potential_inputs = filtered_inputs
        extra_inputs = []
        query_strength_tokens = {
            "lp", "mp", "hp", "lk", "mk", "hk",
            "light", "medium", "heavy", "l", "m", "h",
            "od", "ex",
        }
        compact_strength_motion_present = bool(
            re.search(
                r"\b(?:lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\s*(?:dp|srk|shoryu|shoryuken)\b"
                r"|\b(?:dp|srk|shoryu|shoryuken)\s*(?:lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b",
                text_lower,
            )
        )
        compact_od_motion_present = bool(
            re.search(
                r"\b(?:od|ex)\s*(?:dp|srk|shoryu|shoryuken)\b"
                r"|\b(?:dp|srk|shoryu|shoryuken)\s*(?:od|ex)\b",
                text_lower,
            )
        )
        compact_num_cmd_strength_present = bool(
            re.search(
                r"\b(?:j\.?\s*)?[1-9][0-9]{1,5}\s*(?:\+)?\s*(?:lp|mp|hp|lk|mk|hk|pp|kk)\b",
                text_lower,
            )
        )
        query_has_explicit_strength = bool(
            any(token in query_strength_tokens for token in text_tokens)
            or compact_strength_motion_present
            or compact_od_motion_present
            or compact_num_cmd_strength_present
        )
        query_wants_od_strength = bool(re.search(r"\b(od|ex)\b", text_lower))
        query_wants_non_od_strength = bool(
            re.search(r"\b(lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b", text_lower)
        )
        akuma_followup_alias = None
        deejay_sway_followup_alias = None
        ken_jinrai_followup_alias = None
        jamie_drink_alias = None
        query_requests_air_context = bool(re.search(r"\b(?:air|aerial)\b", text_lower))
        air_fireball_context = bool(
            re.search(
                r"\b(?:air|aerial)\s+fireball\b|\bair\s+hadoken\b",
                text_lower,
            )
        )
        air_sa1_context = bool(
            re.search(
                r"\b(?:air|aerial)\s*(?:sa\s*1|super\s*art\s*1|super\s*1|level\s*1)\b"
                r"|\b(?:sa\s*1|super\s*art\s*1|super\s*1|level\s*1)\s*(?:air|aerial)\b",
                text_lower,
            )
        )
        air_sa2_context = bool(
            re.search(
                r"\b(?:air|aerial)\s*(?:sa\s*2|super\s*art\s*2|super\s*2|level\s*2)\b"
                r"|\b(?:sa\s*2|super\s*art\s*2|super\s*2|level\s*2)\s*(?:air|aerial)\b",
                text_lower,
            )
        )
        zangief_borscht_context = bool(
            re.search(r"\bborscht\b", text_lower)
            or re.search(r"\bj\.?\s*360\s*\+?\s*k{1,2}\b", text_lower)
            or re.search(r"\bj\s+360\s*\+?\s*k{1,2}\b", text_lower)
        )
        alex_stance_followup_context = bool(
            re.search(
                r"\bstance\s+(?:lp|mp|hp|lk|mk|hk|6p|6|4|lplk|5lplk|2lplk|"
                r"jab|shoulder|lariat|hop|stomp|throw|command\s+grab|hk\s+hk)\b",
                text_lower,
            )
        )
        air_sa3_context = bool(
            re.search(
                r"\b(?:air|aerial)\s*(?:sa\s*3|super\s*art\s*3|super\s*3|level\s*3|critical\s+art|ca)\b"
                r"|\b(?:sa\s*3|super\s*art\s*3|super\s*3|level\s*3|critical\s+art|ca)\s*(?:air|aerial)\b",
                text_lower,
            )
        )
        air_tatsu_context = bool(
            re.search(
                r"\b(?:air|aerial)\s+tatsu\b|\b(?:air|aerial)\s+tatsumaki\b|\btatsu\s*\(air\)\b|\bj\.?\s*214k\b",
                text_lower,
            )
        )
        ken_run_followup_context = bool(
            "ken" in mentioned_chars
            and re.search(r"\brun\s+(?:dp|shoryu|shoryuken|tatsu|dragonlash|dragon\s+lash|lash)\b", text_lower)
        )

        if "ken" in mentioned_chars:
            if re.search(
                r"\b(?:(?:od|ex)\s+)?(?:jinrai|236k)\s*(?:>\s*)?(?:low|lk|6lk)\b"
                r"|\b(?:low|lk|6lk)\s+(?:(?:od|ex)\s+)?jinrai\b",
                text_lower,
            ):
                ken_jinrai_followup_alias = "od jinrai low" if query_wants_od_strength else "jinrai low"
            elif re.search(
                r"\b(?:(?:od|ex)\s+)?(?:jinrai|236k)\s*(?:>\s*)?(?:overhead|mk|6mk)\b"
                r"|\b(?:overhead|mk|6mk)\s+(?:(?:od|ex)\s+)?jinrai\b",
                text_lower,
            ):
                ken_jinrai_followup_alias = "od jinrai overhead" if query_wants_od_strength else "jinrai overhead"
            elif re.search(
                r"\b(?:(?:od|ex)\s+)?(?:jinrai|236k)\s*(?:>\s*)?(?:heavy|launcher|hk|6hk)\b"
                r"|\b(?:heavy|launcher|hk|6hk)\s+(?:(?:od|ex)\s+)?jinrai\b",
                text_lower,
            ):
                ken_jinrai_followup_alias = "od jinrai hk" if query_wants_od_strength else "jinrai hk"

            ken_run_alias_tokens = [
                (r"\brun\s+stop\b", "emergency stop"),
                (r"\brun\s+overhead\b", "thunder kick"),
                (r"\brun\s+step\s*kick\b", "forward step kick"),
                (r"\brun\s+step\b", "forward step kick"),
                (r"\brun\s+(?:dp|shoryu|shoryuken)\b", "run > shoryuken"),
                (r"\brun\s+tatsu\b", "run > tatsumaki senpukyaku"),
                (r"\brun\s+(?:dragonlash|dragon\s+lash|lash)\b", "run > dragonlash"),
            ]
            for pattern, alias_token in ken_run_alias_tokens:
                if re.search(pattern, text_lower) and alias_token not in extra_inputs:
                    extra_inputs.append(alias_token)
            if not ken_run_followup_context:
                ken_lash_alias_tokens = [
                    (r"\b(?:od|ex)\s+(?:dragonlash|dragon\s+lash|lash)\b", "od lash"),
                    (r"\b(?:l|light|lk)\s+(?:dragonlash|dragon\s+lash|lash)\b", "l lash"),
                    (r"\b(?:m|medium|mk)\s+(?:dragonlash|dragon\s+lash|lash)\b", "m lash"),
                    (r"\b(?:h|heavy|hk)\s+(?:dragonlash|dragon\s+lash|lash)\b", "h lash"),
                    (r"\b(?:dragonlash|dragon\s+lash|lash)\b", "lash"),
                ]
                selected_lash_alias = None
                for pattern, alias_token in ken_lash_alias_tokens:
                    if re.search(pattern, text_lower):
                        selected_lash_alias = alias_token
                        break
                if selected_lash_alias and selected_lash_alias not in extra_inputs:
                    extra_inputs.append(selected_lash_alias)
            if ken_jinrai_followup_alias and ken_jinrai_followup_alias not in extra_inputs:
                extra_inputs.insert(0, ken_jinrai_followup_alias)
            if re.search(r"\brun\b", text_lower) and not re.search(
                r"\brun\s+(?:stop|overhead|step|dp|shoryu|shoryuken|tatsu|dragonlash|dragon\s+lash|lash)\b",
                text_lower,
            ):
                if "quick dash" not in extra_inputs:
                    extra_inputs.append("quick dash")

        if "mai" in mentioned_chars:
            mai_fan_aliases = [
                (r"\b(?:od|ex)\s+(?:stocked|stock)\s+(?:hold|held|charged)\s+fan\b", "od stocked hold fan"),
                (r"\b(?:stocked|stock)\s+(?:od|ex)\s+(?:hold|held|charged)\s+fan\b", "od stocked hold fan"),
                (r"\b(?:stocked|stock)\s+(?:hold|held|charged)\s+fan\b", "stocked hold fan"),
                (r"\b(?:od|ex)\s+(?:hold|held|charged)\s+fan\b", "od hold fan"),
                (r"\b(?:hold|held|charged)\s+fan\b", "hold fan"),
                (r"\b(?:od|ex)\s+(?:stocked|stock)\s+fan\b", "od stocked fan"),
                (r"\b(?:stocked|stock)\s+(?:od|ex)\s+fan\b", "od stocked fan"),
                (r"\b(?:stocked|stock)\s+fan\b", "stocked fan"),
                (r"\b(?:od|ex)\s+fan\b", "od fan"),
                (r"\b(?:l|light|lp)\s+fan\b", "l fan"),
                (r"\b(?:m|medium|mp)\s+fan\b", "m fan"),
                (r"\b(?:h|heavy|hp)\s+fan\b", "h fan"),
                (r"\bfan\b", "fan"),
            ]
            for pattern, alias_token in mai_fan_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break
            if air_sa2_context and "air sa2" not in extra_inputs:
                extra_inputs.append("air sa2")

        if "jamie" in mentioned_chars:
            if re.search(
                r"\b(?:drink|dr\s*4)\s+activation\b|\blevel\s*4\s+activation\b|\bactivation\s+drink\b",
                text_lower,
            ):
                jamie_drink_alias = "drink activation"
            elif re.search(r"\b(?:drink\s*(?:level\s*)?4|level\s*4\s*drink|4\s*drinks?|four\s+drinks?)\b", text_lower):
                jamie_drink_alias = "drink level 4"
            elif re.search(r"\b(?:drink\s*(?:level\s*)?3|level\s*3\s*drink|3\s*drinks?|three\s+drinks?)\b", text_lower):
                jamie_drink_alias = "drink level 3"
            elif re.search(r"\b(?:drink\s*(?:level\s*)?2|level\s*2\s*drink|2\s*drinks?|two\s+drinks?)\b", text_lower):
                jamie_drink_alias = "drink level 2"
            elif re.search(r"\b(?:drink\s*(?:level\s*)?1|level\s*1\s*drink|1\s*drink|one\s+drink)\b", text_lower):
                jamie_drink_alias = "drink level 1"
            elif re.search(r"\bdrink\b", text_lower):
                jamie_drink_alias = "drink"

            if jamie_drink_alias and jamie_drink_alias not in extra_inputs:
                extra_inputs.insert(0, jamie_drink_alias)

            jamie_palm_aliases = [
                (r"\b(?:od|ex)\s+(?:palm|swagger(?:\s+step)?)\b", "od palm"),
                (r"\b(?:l|light|lp)\s+(?:palm|swagger(?:\s+step)?)\b", "lp palm"),
                (r"\b(?:m|medium|mp)\s+(?:palm|swagger(?:\s+step)?)\b", "mp palm"),
                (r"\b(?:h|heavy|hp)\s+(?:palm|swagger(?:\s+step)?)\b", "hp palm"),
                (r"\b(?:palm|swagger(?:\s+step)?)\b", "palm"),
            ]
            for pattern, alias_token in jamie_palm_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

            jamie_rekka_aliases = [
                (r"\b(?:od|ex)\s+(?:rekka|freeflow(?:\s+strikes)?)\b", "od rekka"),
                (r"\b(?:l|light|lp)\s+(?:rekka|freeflow(?:\s+strikes)?)\b", "lp rekka"),
                (r"\b(?:m|medium|mp)\s+(?:rekka|freeflow(?:\s+strikes)?)\b", "mp rekka"),
                (r"\b(?:h|heavy|hp)\s+(?:rekka|freeflow(?:\s+strikes)?)\b", "hp rekka"),
                (r"\b(?:rekka|freeflow(?:\s+strikes)?)\b", "rekka"),
            ]
            for pattern, alias_token in jamie_rekka_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

            jamie_arrow_aliases = [
                (r"\b(?:od|ex)\s+(?:arrow\s+kick|up\s*kicks?|upkicks?)\b", "od arrow kick"),
                (r"\b(?:l|light|lk)\s+(?:arrow\s+kick|up\s*kicks?|upkicks?)\b", "l arrow kick"),
                (r"\b(?:m|medium|mk)\s+(?:arrow\s+kick|up\s*kicks?|upkicks?)\b", "m arrow kick"),
                (r"\b(?:h|heavy|hk)\s+(?:arrow\s+kick|up\s*kicks?|upkicks?)\b", "h arrow kick"),
                (r"\b(?:arrow\s+kick|up\s*kicks?|upkicks?)\b", "arrow kick"),
            ]
            for pattern, alias_token in jamie_arrow_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

            jamie_bakkai_aliases = [
                (r"\b(?:od|ex)\s+(?:bakkai|break\s*dance)\b|\b236kk\b", "od bakkai"),
                (r"\b(?:l|light|lk)\s+(?:bakkai|break\s*dance)\b|\b236lk\b", "lk bakkai"),
                (r"\b(?:m|medium|mk)\s+(?:bakkai|break\s*dance)\b|\b236mk\b", "mk bakkai"),
                (r"\b(?:h|heavy|hk)\s+(?:bakkai|break\s*dance)\b|\b236hk\b", "hk bakkai"),
                (r"\b(?:bakkai|break\s*dance)\b|\b236k\b", "bakkai"),
            ]
            for pattern, alias_token in jamie_bakkai_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

            jamie_divekick_aliases = [
                (
                    r"\b(?:od|ex)\s+(?:luminous\s+)?dive\s+kick\b|\b(?:od|ex)\s+divekick\b|\b214kk\b|\bj\.?214kk\b",
                    "od dive kick",
                ),
                (
                    r"\b(?:l|light|lk)\s+(?:luminous\s+)?dive\s+kick\b|\b(?:l|light|lk)\s+divekick\b|\b214lk\b|\bj\.?214lk\b",
                    "dive kick",
                ),
                (
                    r"\b(?:m|medium|mk)\s+(?:luminous\s+)?dive\s+kick\b|\b(?:m|medium|mk)\s+divekick\b|\b214mk\b|\bj\.?214mk\b",
                    "dive kick",
                ),
                (
                    r"\b(?:h|heavy|hk)\s+(?:luminous\s+)?dive\s+kick\b|\b(?:h|heavy|hk)\s+divekick\b|\b214hk\b|\bj\.?214hk\b",
                    "dive kick",
                ),
                (
                    r"\b(?:luminous\s+)?dive\s+kick\b|\bdivekick\b|\b214k\b|\bj\.?214k\b",
                    "dive kick",
                ),
            ]
            for pattern, alias_token in jamie_divekick_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

            jamie_tenshin_aliases = [
                (r"\b(?:od|ex)\s+(?:tenshin|command\s+grab)\b", "od tenshin"),
                (r"\b(?:tenshin|command\s+grab)\b", "tenshin"),
            ]
            for pattern, alias_token in jamie_tenshin_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

            jamie_hermit_aliases = [
                (
                    r"\b(?:od|ex)\s+(?:swagger\s+hermit\s+punch|hermit\s+punch|palm\s+follow(?:-?up)?)\b",
                    "od swagger hermit punch",
                ),
                (
                    r"\b(?:l|light|lp)\s+(?:swagger\s+hermit\s+punch|hermit\s+punch|palm\s+follow(?:-?up)?)\b",
                    "lp swagger hermit punch",
                ),
                (
                    r"\b(?:m|medium|mp)\s+(?:swagger\s+hermit\s+punch|hermit\s+punch|palm\s+follow(?:-?up)?)\b",
                    "mp swagger hermit punch",
                ),
                (
                    r"\b(?:h|heavy|hp)\s+(?:swagger\s+hermit\s+punch|hermit\s+punch|palm\s+follow(?:-?up)?)\b",
                    "hp swagger hermit punch",
                ),
                (
                    r"\b(?:swagger\s+hermit\s+punch|hermit\s+punch|palm\s+follow(?:-?up)?)\b",
                    "swagger hermit punch",
                ),
            ]
            for pattern, alias_token in jamie_hermit_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

        if "akuma" in mentioned_chars:
            has_od_strength = bool(re.search(r"\b(od|ex)\b", text_lower))

            if air_sa1_context and "tenma gozanku" not in extra_inputs:
                extra_inputs.append("tenma gozanku")

            if re.search(r"\b(?:demon\s+)?gou\s+rasen\b", text_lower):
                akuma_followup_alias = "od demon gou rasen"
            elif re.search(r"\b(?:demon\s+)?gou\s+zanku\b", text_lower):
                akuma_followup_alias = "od demon gou zanku"
            elif re.search(r"\b(?:demon\s+)?(?:low(?:\s+slash)?|slide)\b", text_lower):
                akuma_followup_alias = "od demon low" if has_od_strength else "demon low"
            elif re.search(r"\b(?:demon\s+)?(?:guillotine|chop|overhead)\b", text_lower):
                akuma_followup_alias = "od chop" if has_od_strength else "chop"
            elif (
                re.search(r"\b(?:blade\s+kick|divekick|dive\s+kick)\b", text_lower)
                and re.search(r"\b(?:demon|flip|raid)\b", text_lower)
            ):
                akuma_followup_alias = (
                    "od demon flip divekick" if has_od_strength else "demon flip divekick"
                )
            elif re.search(r"\b(?:demon\s+)?(?:swoop|empty|stop|feint)\b", text_lower):
                akuma_followup_alias = "od empty" if has_od_strength else "empty"

            if akuma_followup_alias:
                if akuma_followup_alias not in extra_inputs:
                    extra_inputs.append(akuma_followup_alias)
                potential_inputs = [
                    token for token in potential_inputs
                    if token not in {"dive kick", "divekick"}
                ]

        if "jp" in mentioned_chars:
            jp_swipe_aliases = [
                (r"\b(?:od|ex)\s+swipe\b", "od swipe"),
                (r"\b(?:l|light|lp)\s+swipe\b", "l swipe"),
                (r"\b(?:m|medium|mp)\s+swipe\b", "m swipe"),
                (r"\b(?:h|heavy|hp)\s+swipe\b", "h swipe"),
                (r"\bswipe\b", "swipe"),
            ]
            for pattern, alias_token in jp_swipe_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

        if "a.k.i" in mentioned_chars:
            aki_whip_aliases = [
                (r"\b(?:od|ex)\s+whip\b", "od whip"),
                (r"\b(?:l|light|lp)\s+whip\b", "l whip"),
                (r"\b(?:m|medium|mp)\s+whip\b", "m whip"),
                (r"\b(?:h|heavy|hp)\s+whip\b", "h whip"),
                (r"\bwhip\b", "whip"),
            ]
            for pattern, alias_token in aki_whip_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

        if "luke" in mentioned_chars:
            luke_knuckle_aliases = [
                (r"\b(?:charged|hold|held)\s+(?:l|light|lp)\s+(?:flash\s+)?knuckle\b", "charged light knuckle"),
                (r"\b(?:l|light|lp)\s+(?:charged|hold|held)\s+(?:flash\s+)?knuckle\b", "charged light knuckle"),
                (r"\b(?:charged|hold|held)\s+(?:m|medium|mp)\s+(?:flash\s+)?knuckle\b", "charged medium knuckle"),
                (r"\b(?:m|medium|mp)\s+(?:charged|hold|held)\s+(?:flash\s+)?knuckle\b", "charged medium knuckle"),
                (r"\b(?:charged|hold|held)\s+(?:h|heavy|hp)\s+(?:flash\s+)?knuckle\b", "charged heavy knuckle"),
                (r"\b(?:h|heavy|hp)\s+(?:charged|hold|held)\s+(?:flash\s+)?knuckle\b", "charged heavy knuckle"),
                (r"\b(?:charged|hold|held)\s+(?:flash\s+)?knuckle\b", "charged knuckle"),
            ]
            for pattern, alias_token in luke_knuckle_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

        if query_requests_ca and "critical art" not in extra_inputs:
            extra_inputs.append("critical art")

        if "akuma" in mentioned_chars:
            if air_sa3_context and "sip of calamity" not in extra_inputs:
                extra_inputs.append("sip of calamity")

        if "lily" in mentioned_chars and query_requires_stocked:
            lily_stocked_aliases = [
                (r"\b(?:stocked|stock|windclad|wind\s+clad)\s+(?:condor\s+)?spire\b", "stocked spire"),
                (r"\b(?:stocked|stock|windclad|wind\s+clad)\s+(?:tomahawk|tomahawk\s+buster)\b", "stocked tomahawk"),
                (r"\b(?:stocked|stock|windclad|wind\s+clad|wind\s+stock)\s+(?:condor\s+)?wind\b", "stocked condor wind"),
            ]
            for pattern, alias_token in lily_stocked_aliases:
                if re.search(pattern, text_lower) and alias_token not in extra_inputs:
                    extra_inputs.append(alias_token)

        if "mai" in mentioned_chars and query_requires_stocked:
            mai_stocked_aliases = [
                (r"\b(?:od|ex)\s+(?:stocked|stock)\s+(?:fireball|kachousen)\b", "od stocked fireball"),
                (r"\b(?:stocked|stock)\s+(?:od|ex)\s+(?:fireball|kachousen)\b", "od stocked fireball"),
                (r"\b(?:od|ex)\s+(?:stocked|stock)\s+(?:dp|ryuuenjin)\b", "od stocked dp"),
                (r"\b(?:stocked|stock)\s+(?:od|ex)\s+(?:dp|ryuuenjin)\b", "od stocked dp"),
                (r"\b(?:od|ex)\s+(?:stocked|stock)\s+(?:twirl|ryuuenbu)\b", "od stocked twirl"),
                (r"\b(?:stocked|stock)\s+(?:od|ex)\s+(?:twirl|ryuuenbu)\b", "od stocked twirl"),
                (r"\b(?:od|ex)\s+(?:stocked|stock)\s+(?:cartwheel|shinobi\s+bachi)\b", "od stocked cartwheel"),
                (r"\b(?:stocked|stock)\s+(?:od|ex)\s+(?:cartwheel|shinobi\s+bachi)\b", "od stocked cartwheel"),
                (
                    r"\b(?:od|ex)\s+(?:stocked|stock)\s+(?:dive\s+kick|divekick|musasabi(?:\s+no\s+mai)?)\b",
                    "od stocked dive kick",
                ),
                (
                    r"\b(?:stocked|stock)\s+(?:od|ex)\s+(?:dive\s+kick|divekick|musasabi(?:\s+no\s+mai)?)\b",
                    "od stocked dive kick",
                ),
                (r"\b(?:stocked|stock)\s+(?:fireball|kachousen)\b", "stocked fireball"),
                (r"\b(?:stocked|stock)\s+(?:dp|ryuuenjin)\b", "stocked dp"),
                (r"\b(?:stocked|stock)\s+(?:twirl|ryuuenbu)\b", "stocked twirl"),
                (r"\b(?:stocked|stock)\s+(?:cartwheel|shinobi\s+bachi)\b", "stocked cartwheel"),
                (
                    r"\b(?:stocked|stock)\s+(?:dive\s+kick|divekick|musasabi(?:\s+no\s+mai)?)\b",
                    "stocked dive kick",
                ),
                (r"\b(?:stocked|stock)\s+(?:sa\s*1|super\s*art\s*1|super\s*1|level\s*1)\b", "stocked sa1"),
                (
                    r"\b(?:stocked|stock)\s+(?:air\s+)?(?:sa\s*2|super\s*art\s*2|super\s*2|level\s*2)\b",
                    "stocked air sa2",
                ),
                (
                    r"\b(?:air\s+)?(?:stocked|stock)\s+(?:sa\s*2|super\s*art\s*2|super\s*2|level\s*2)\b",
                    "stocked air sa2",
                ),
            ]
            for pattern, alias_token in mai_stocked_aliases:
                if re.search(pattern, text_lower) and alias_token not in extra_inputs:
                    extra_inputs.append(alias_token)

        if "juri" in mentioned_chars and query_requires_stocked:
            juri_stocked_aliases = [
                (r"\b(?:stocked|stock)\s+(?:fireball|saihasho|fuha\s+release)\b", "stocked fireball"),
                (r"\b(?:stocked|stock)\s+(?:axe\s+kick|ankensatsu)\b", "stocked axe kick"),
                (r"\b(?:stocked|stock)\s+(?:spinning\s+kicks?|go\s+ohsatsu)\b", "stocked spinning kicks"),
                (r"\b(?:stocked|stock)\s+(?:air\s+)?sa\s*1\b", "stocked sa1"),
                (r"\b(?:air\s+)?(?:stocked|stock)\s+sa\s*1\b", "stocked sa1"),
            ]
            for pattern, alias_token in juri_stocked_aliases:
                if re.search(pattern, text_lower) and alias_token not in extra_inputs:
                    extra_inputs.append(alias_token)

        def is_special_motion_num_cmd(num_cmd_raw):
            compact = re.sub(r"[^a-z0-9]", "", str(num_cmd_raw).lower())
            if not compact or ">" in str(num_cmd_raw):
                return False
            motion_prefixes = (
                "236", "214", "623", "421", "41236", "63214", "4268", "624", "46", "28",
                "214214", "236236", "360", "720", "22",
            )
            return compact.startswith(motion_prefixes)

        def get_special_canonical_base_name(row):
            raw_name = str(row.get("cmnName", "")).lower().strip()
            if not raw_name:
                raw_name = str(row.get("moveName", "")).lower().strip()
            if not raw_name:
                return ""
            base_name = re.sub(r"^(od|ex)\s+", "", raw_name)
            base_name = re.sub(
                r"^(lp|mp|hp|lk|mk|hk|pp|kk|light|medium|heavy|l|m|h)\s+",
                "",
                base_name,
            ).strip()
            return re.sub(r"\s*\(charged\)", "", base_name).strip()

        command_jump_notation_present = bool(
            re.search(
                r"\b(?:neutral\s+|n\s+)?(?:jump\s+|j\.?\s*)[1-9][0-9]*(?:lp|mp|hp|lk|mk|hk|p|k)\b",
                text_lower,
            )
        )

        if (
            not query_has_explicit_strength
            and mentioned_chars
            and not target_combo_query
            and not command_jump_notation_present
            and not query_requires_stocked
            and not query_requests_ca
        ):
            seen_special_prompts = set()
            for char in mentioned_chars:
                special_base_map = {}
                for row in FRAME_DATA.get(char, []):
                    if not is_special_motion_num_cmd(row.get("numCmd", "")):
                        continue
                    raw_name = str(row.get("cmnName", "")).lower().strip()
                    if not raw_name:
                        raw_name = str(row.get("moveName", "")).lower().strip()
                    if not raw_name:
                        continue
                    base_name = re.sub(r"^(od|ex)\s+", "", raw_name)
                    base_name = re.sub(
                        r"^(lp|mp|hp|lk|mk|hk|pp|kk|light|medium|heavy|l|m|h)\s+",
                        "",
                        base_name,
                    ).strip()
                    canonical_base = re.sub(r"\s*\(charged\)", "", base_name).strip()
                    if not canonical_base:
                        continue
                    special_base_map.setdefault(canonical_base, [])
                    if row not in special_base_map[canonical_base]:
                        special_base_map[canonical_base].append(row)

                for base_name, variants in special_base_map.items():
                    prompt_variants = variants

                    if char == "ryu" and base_name in {"super art level 1", "super art level 2"}:
                        if base_name == "super art level 1" and not query_requests_sa1:
                            continue
                        if base_name == "super art level 2" and not query_requests_sa2:
                            continue

                        denjin_variants = [row for row in variants if row_is_denjin_variant(row)]
                        non_denjin_variants = [row for row in variants if not row_is_denjin_variant(row)]
                        if query_requires_denjin and denjin_variants:
                            chosen_variant = denjin_variants[0]
                            if chosen_variant not in results:
                                results.append(chosen_variant)
                            continue
                        if not query_requires_denjin and non_denjin_variants:
                            chosen_variant = non_denjin_variants[0]
                            if chosen_variant not in results:
                                results.append(chosen_variant)
                            continue

                    if query_requires_denjin:
                        denjin_variants = [row for row in variants if row_is_denjin_variant(row)]
                        if denjin_variants:
                            prompt_variants = denjin_variants
                        else:
                            continue
                    if len(prompt_variants) < 2:
                        continue
                    base_tokens = re.findall(r"[a-z0-9]+", base_name)
                    base_in_query = tokens_in_text(base_tokens)
                    if not base_in_query and base_name == "fireball":
                        base_in_query = "hadoken" in text_tokens or "hadouken" in text_tokens
                    if not base_in_query and base_name == "upkicks":
                        base_in_query = "tensho" in text_tokens or "tenshokyaku" in text_tokens
                    if not base_in_query and base_name == "palm thrust":
                        base_in_query = "hashogeki" in text_tokens
                    if not base_in_query and base_name == "super art level 1":
                        base_in_query = bool(re.search(r"\bsa\s*1\b", text_lower))
                    if not base_in_query and base_name == "super art level 2":
                        base_in_query = bool(re.search(r"\bsa\s*2\b", text_lower))
                    if not base_in_query and base_name == "super art level 3":
                        base_in_query = bool(re.search(r"\bsa\s*3\b", text_lower))
                    if not base_in_query and base_name == "spd":
                        base_in_query = "command" in text_tokens and "grab" in text_tokens
                    if not base_in_query:
                        continue
                    if (
                        air_fireball_context
                        and base_name == "fireball"
                        and "air fireball" in special_base_map
                    ):
                        continue
                    if len(prompt_variants) == 2:
                        od_variants = [row for row in prompt_variants if row_is_od_variant(row)]
                        non_od_variants = [row for row in prompt_variants if not row_is_od_variant(row)]
                        if len(od_variants) == 1 and len(non_od_variants) == 1:
                            chosen_variant = od_variants[0] if query_wants_od_strength else non_od_variants[0]
                            if chosen_variant not in results:
                                results.append(chosen_variant)
                            continue
                    if char == "akuma" and base_name == "demon flip":
                        continue
                    if (
                        air_tatsu_context
                        and char in {"ryu", "ken", "akuma"}
                        and base_name in {"tatsu", "air tatsu"}
                    ):
                        continue
                    if (
                        ken_run_followup_context
                        and char == "ken"
                        and base_name in {"dp", "tatsu", "dragonlash"}
                    ):
                        continue
                    prompt_key = (char, base_name)
                    if prompt_key in seen_special_prompts:
                        continue
                    seen_special_prompts.add(prompt_key)
                    variant_lines = "\n".join(
                        f"- {row.get('moveName', '?')} ({row.get('numCmd', '?')})"
                        for row in prompt_variants
                    )
                    special_prompt_blocks.append(
                        f"**Special Strength Options ({char.capitalize()})**\n"
                        f"{base_name.title()} variants:\n{variant_lines}\n"
                        "Reply or make a new prompt with the exact strength+move."
                    )
        dp_strength_inputs = []
        dp_strength_prefix_matches = re.findall(
            r"\b(lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\s*(?:\+)?\s*(dp|srk|shoryu|shoryuken)\b",
            text_lower,
        )
        for strength_token, motion_token in dp_strength_prefix_matches:
            token = f"{strength_token} {motion_token}"
            if token not in dp_strength_inputs:
                dp_strength_inputs.append(token)
        dp_strength_suffix_matches = re.findall(
            r"\b(dp|srk|shoryu|shoryuken)\s*(?:\+)?\s*(lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b",
            text_lower,
        )
        for motion_token, strength_token in dp_strength_suffix_matches:
            token = f"{strength_token} {motion_token}"
            if token not in dp_strength_inputs:
                dp_strength_inputs.append(token)
        for token in dp_strength_inputs:
            if token not in extra_inputs:
                extra_inputs.append(token)

        dp_aliases = ["dp", "srk", "shoryu", "shoryuken", "623"]
        dp_present = False
        for token in dp_aliases:
            if re.search(rf"\b{re.escape(token)}\b", text_lower):
                if dp_strength_inputs and token in {"dp", "srk", "shoryu", "shoryuken"}:
                    dp_present = True
                    continue
                if token not in extra_inputs:
                    extra_inputs.append(token)
                dp_present = True
        if dp_present and re.search(r"\b(ex|od)\b", text_lower):
            extra_inputs.append("623pp")
            extra_inputs.append("623kk")
        if re.search(r"\b(ex|od)(dp|srk|shoryu|shoryuken)\b", text_lower):
            extra_inputs.append("623pp")
            extra_inputs.append("623kk")
        if ken_run_followup_context:
            extra_inputs = [
                token for token in extra_inputs
                if token not in {"dp", "srk", "shoryu", "shoryuken", "tatsu", "dragonlash"}
            ]
        if "sway" in text_lower:
            extra_inputs.append("sway")
        if "jus cool" in text_lower or "juscool" in text_lower:
            extra_inputs.append("jus cool")

        if "dee jay" in mentioned_chars:
            if (
                re.search(r"\bsway\s*(?:low)?\s*>\s*(?:lk|light)\b", text_lower)
                or re.search(r"\bsway\s+low\b", text_lower)
                or re.search(r"\bsway\s+lk\b", text_lower)
            ):
                deejay_sway_followup_alias = "sway low"
            elif (
                re.search(r"\bsway\s*(?:overhead)?\s*>\s*(?:mk|medium)\b", text_lower)
                or re.search(r"\bsway\s+overhead\b", text_lower)
                or re.search(r"\bsway\s+mk\b", text_lower)
            ):
                deejay_sway_followup_alias = "sway overhead"
            elif (
                re.search(r"\bsway\s*(?:launch|launcher)?\s*>\s*(?:hk|heavy)\b", text_lower)
                or re.search(r"\bsway\s+(?:launch|launcher)\b", text_lower)
                or re.search(r"\bsway\s+hk\b", text_lower)
            ):
                deejay_sway_followup_alias = "sway launch"
            elif (
                re.search(r"\bsway\s+feint\b", text_lower)
                or (
                    "sway" in text_lower
                    and re.search(r"\b6p\b", text_lower)
                    and re.search(r"\b4p\b", text_lower)
                )
            ):
                deejay_sway_followup_alias = "sway feint"

        if deejay_sway_followup_alias:
            if deejay_sway_followup_alias not in extra_inputs:
                extra_inputs.insert(0, deejay_sway_followup_alias)
            extra_inputs = [
                token
                for token in extra_inputs
                if token not in {"sway", "jus cool", "juscool"}
            ]
        has_od_denjin_fireball = bool(
            re.search(r"\b(ex|od)\s+denjin\s+(fireball|hadoken|hadouken)\b", text_lower)
        )
        if has_od_denjin_fireball:
            if "od denjin fireball" not in extra_inputs:
                extra_inputs.append("od denjin fireball")
        elif re.search(r"\bdenjin\s+(fireball|hadoken|hadouken)\b", text_lower):
            if "denjin fireball" not in extra_inputs:
                extra_inputs.append("denjin fireball")
        sa_alias_matches = re.findall(r"\bsa\s*([123])\b", text_lower)
        for sa_level in sa_alias_matches:
            sa_token = f"sa{sa_level}"
            if sa_token not in extra_inputs:
                extra_inputs.append(sa_token)
        # 46P charge patterns (back-forward+punch)
        charge_patterns = [
            (r"\b46p\b", "46p"),
            (r"\b46lp\b", "46lp"),
            (r"\b46mp\b", "46mp"),
            (r"\b46hp\b", "46hp"),
            (r"\b46pp\b", "46pp"),
            (r"\bb,\s*f\+?p\b", "46p"),
            (r"\bb,\s*f\+?lp\b", "46lp"),
            (r"\bb,\s*f\+?mp\b", "46mp"),
            (r"\bb,\s*f\+?hp\b", "46hp"),
            (r"\bb,\s*f\+?pp\b", "46pp"),
            (r"\bbf\+?p\b", "46p"),
            (r"\bbf\+?lp\b", "46lp"),
            (r"\bbf\+?mp\b", "46mp"),
            (r"\bbf\+?hp\b", "46hp"),
            (r"\bbf\+?pp\b", "46pp"),
            (r"\bback\s*forward\+?p\b", "46p"),
            (r"\bback\s*forward\+?lp\b", "46lp"),
            (r"\bback\s*forward\+?mp\b", "46mp"),
            (r"\bback\s*forward\+?hp\b", "46hp"),
            (r"\bback\s*forward\+?pp\b", "46pp"),
            # 28K charge patterns (down-up+kick)
            (r"\b28k\b", "28k"),
            (r"\b28lk\b", "28lk"),
            (r"\b28mk\b", "28mk"),
            (r"\b28hk\b", "28hk"),
            (r"\b28kk\b", "28kk"),
            (r"\bd,\s*u\+?k\b", "28k"),
            (r"\bd,\s*u\+?lk\b", "28lk"),
            (r"\bd,\s*u\+?mk\b", "28mk"),
            (r"\bd,\s*u\+?hk\b", "28hk"),
            (r"\bd,\s*u\+?kk\b", "28kk"),
            (r"\bdu\+?k\b", "28k"),
            (r"\bdu\+?lk\b", "28lk"),
            (r"\bdu\+?mk\b", "28mk"),
            (r"\bdu\+?hk\b", "28hk"),
            (r"\bdu\+?kk\b", "28kk"),
            (r"\bdown\s*up\+?k\b", "28k"),
            (r"\bdown\s*up\+?lk\b", "28lk"),
            (r"\bdown\s*up\+?mk\b", "28mk"),
            (r"\bdown\s*up\+?hk\b", "28hk"),
            (r"\bdown\s*up\+?kk\b", "28kk"),
        ]
        for pattern, token in charge_patterns:
            if re.search(pattern, text_lower) and token not in extra_inputs:
                extra_inputs.append(token)
        combo_text = text_lower.replace("->", ">")
        tc_selected_combos = set()
        tc_base_tokens = set(re.findall(r"\b[1-9][0-9]*[a-z]{1,3}\b", text_lower))
        tc_pair_candidates = set()
        for base_token, follow_token in re.findall(
            r"\b([1-9][0-9]*[a-z]{1,3})\s*(?:,|>|->)\s*([a-z]{1,3}|[1-9][0-9]*[a-z]{1,3})\b",
            combo_text,
        ):
            tc_pair_candidates.add(f"{base_token}>{follow_token}")
        for base_token, follow_token in re.findall(
            r"\b([1-9][0-9]*[a-z]{1,3})\s+([a-z]{1,3})\s+(?:target\s+combo|tc)\b",
            text_lower,
        ):
            tc_pair_candidates.add(f"{base_token}>{follow_token}")

        combo_matches = re.findall(
            r"\b[0-9a-zA-Z+]+(?:\s*>\s*[0-9a-zA-Z+]+)+\b",
            combo_text,
        )
        for combo in combo_matches:
            combo_token = re.sub(r"\s+", "", combo)
            tc_selected_combos.add(combo_token)
            if combo_token not in extra_inputs:
                extra_inputs.append(combo_token)

        if target_combo_query and mentioned_chars:
            compact_text = re.sub(r"\s+", "", combo_text)
            for char in mentioned_chars:
                normalized_char = normalize_char_name(char)
                compact_text_for_char = re.sub(
                    rf"\b{re.escape(normalized_char)}\b", "", compact_text
                )
                if compact_text_for_char == compact_text:
                    compact_text_for_char = compact_text
                tc_map = {}
                for row in FRAME_DATA.get(char, []):
                    num_cmd_raw = str(row.get("numCmd", ""))
                    num_cmd = num_cmd_raw.lower()
                    if ">" not in num_cmd:
                        continue
                    base_cmd = num_cmd.split(">", 1)[0].strip()
                    base_key = re.sub(r"\s+", "", base_cmd)
                    if not base_key:
                        continue
                    tc_map.setdefault(base_key, []).append(num_cmd_raw)
                for base_key, combos in tc_map.items():
                    if base_key not in compact_text_for_char:
                        continue
                    explicit_pair_matches = [
                        pair for pair in tc_pair_candidates if pair.startswith(f"{base_key}>")
                    ]
                    if explicit_pair_matches:
                        matched_any = False
                        for combo_raw in combos:
                            combo_key = re.sub(r"\s+", "", combo_raw.lower())
                            if ">" not in combo_key:
                                continue
                            combo_follow = combo_key.split(">", 1)[1]
                            for explicit_pair in explicit_pair_matches:
                                explicit_follow = explicit_pair.split(">", 1)[1]
                                if combo_follow == explicit_follow or combo_follow.startswith(explicit_follow):
                                    tc_selected_combos.add(combo_key)
                                    if combo_key not in extra_inputs:
                                        extra_inputs.append(combo_key)
                                    matched_any = True
                        if matched_any:
                            continue
                    if len(combos) == 1:
                        combo_token = re.sub(r"\s+", "", combos[0].lower())
                        tc_selected_combos.add(combo_token)
                        if combo_token not in extra_inputs:
                            extra_inputs.append(combo_token)
                        continue
                    tc_ambiguous_inputs.add(base_key)
                    combo_list = "\n".join(f"- {combo}" for combo in combos)
                    tc_prompt_blocks.append(
                        f"**Target Combo Options ({char.capitalize()})**\n"
                        f"{base_key.upper()} follow-ups:\n{combo_list}\n"
                        "Reply or Make a new prompt with the exact target combo "
                    )
        keyword_inputs = [
            # 46P moves
            "air slasher",
            "sonic boom",
            "sumo headbutt",
            "psycho crusher",
            "rolling attack",
            "blanka ball",
            "bison crusher",
            "crusher",
            "fireball",
            "boom",
            "headbutt",
            "clap",
            "claps",
            "neko damashi",
            "oicho",
            "oicho throw",
            "ball",
            # 28K moves
            "vertical rolling attack",
            "upball",
            "up ball",
            "somersault kick",
            "flash kick",
            "flashkick",
            "shadow rise",
            "command jump",
            "fly",
            "jackknife maximum",
            "upkicks",
            "upkick",
            "up kicks",
            "tensho",
            "tenshokyaku",
            "tensho kick",
            "tensho kicks",
            "dive kick",
            "divekick",
            "demon flip",
            "demon raid",
            "demon low slash",
            "demon guillotine",
            "demon blade kick",
            "demon swoop",
            "demon gou zanku",
            "demon gou rasen",
            "adamant flame",
            "flaming fist",
            "flame",
            "burn kick",
            "burnkick",
            "burn kicks",
            "burnkicks",
            "burning kick",
            "burning kicks",
            "air burn kick",
            "air burnkick",
            "air burning kick",
            "air burning kicks",
            "aerial burn kick",
            "aerial burnkick",
            "aerial burning kick",
            "teleport",
            "ashura",
            "ashura senku",
            "raging demon",
            "tenma",
            "gozanku",
            "air fireball",
            "aerial fireball",
            "air hadoken",
            "zanku",
            "air tatsu",
            "aerial tatsu",
            "air tatsumaki",
            "aerial tatsumaki",
            "air legs",
            "airlegs",
            "aerial legs",
            "air lightning legs",
            "sumo smash",
            "ass slam",
            "butt slam",
            "spinning bird kick",
            "sbk",
            # JP 22 specials
            "triglav",
            "amnesia",
            "ground spike",
            "spike",
            "pierce",
        ]
        # Strength prefixes for charge moves
        strength_prefixes = ["lp", "mp", "hp", "od", "ex", "light", "medium", "heavy", "l", "m", "h"]
        for token in keyword_inputs:
            matched_strength_for_token = False
            # Check for strength+keyword combos (e.g., "heavy fireball", "hp boom")
            for prefix in strength_prefixes:
                combo = f"{prefix} {token}"
                if combo in text_lower and combo not in extra_inputs:
                    if token == "ball" and "blanka" not in text_lower:
                        continue
                    extra_inputs.append(combo)
                    matched_strength_for_token = True
            # Check for bare keyword
            if (
                not matched_strength_for_token
                and re.search(rf"\b{re.escape(token)}\b", text_lower)
                and token not in extra_inputs
            ):
                if token == "ball" and "blanka" not in text_lower:
                    continue
                extra_inputs.append(token)
        if "akuma" in mentioned_chars:
            if re.search(r"\bback(?:ward)?\s+teleport\b", text_lower):
                extra_inputs = [token for token in extra_inputs if token != "teleport"]
                if "back teleport" not in extra_inputs:
                    extra_inputs.insert(0, "back teleport")
            elif re.search(r"\btele(?:port)?\s+back(?:ward)?\b", text_lower):
                extra_inputs = [token for token in extra_inputs if token != "teleport"]
                if "teleport back" not in extra_inputs:
                    extra_inputs.insert(0, "teleport back")
            elif re.search(r"\bforward\s+teleport\b", text_lower):
                extra_inputs = [token for token in extra_inputs if token != "teleport"]
                if "forward teleport" not in extra_inputs:
                    extra_inputs.insert(0, "forward teleport")
        ordered_inputs = []
        for inp in extra_inputs + potential_inputs:
            if inp and inp not in ordered_inputs:
                ordered_inputs.append(inp)
        potential_inputs = ordered_inputs

        if wants_comparison and (potential_inputs or extra_inputs) and len(mentioned_chars) >= 2:
            side_segments = [
                segment.strip()
                for segment in re.split(r"\b(?:vs|versus|and)\b", text_lower)
                if segment.strip()
            ]
            if len(side_segments) >= 2:
                assigned_chars = set()

                def segment_mentions_character(segment_text, char_key):
                    segment_tokens = re.findall(r"[a-z0-9]+", segment_text)
                    if not segment_tokens:
                        return False
                    char_tokens = re.findall(r"[a-z0-9]+", str(char_key).lower())
                    if char_tokens and tokens_in_haystack(segment_tokens, char_tokens):
                        return True
                    for alias, canonical in CHARACTER_ALIASES.items():
                        if normalize_char_name(canonical) != normalize_char_name(char_key):
                            continue
                        alias_tokens = re.findall(r"[a-z0-9]+", str(alias).lower())
                        if alias_tokens and tokens_in_haystack(segment_tokens, alias_tokens):
                            return True
                    return False

                for side_text in side_segments:
                    side_chars = [
                        char for char in mentioned_chars
                        if segment_mentions_character(side_text, char)
                    ]
                    if not side_chars:
                        continue

                    if len(side_chars) == 1:
                        target_char = side_chars[0]
                    else:
                        target_char = next(
                            (char for char in side_chars if char not in assigned_chars),
                            side_chars[0],
                        )

                    side_inputs = []
                    for inp in potential_inputs:
                        inp_norm = str(inp or "").strip().lower()
                        if not inp_norm:
                            continue
                        if re.search(rf"\b{re.escape(inp_norm)}\b", side_text):
                            if inp not in side_inputs:
                                side_inputs.append(inp)

                    if side_inputs:
                        comparison_char_inputs[target_char] = side_inputs
                        assigned_chars.add(target_char)

        explicit_move_attempt = bool(potential_inputs or extra_inputs)
        if mentioned_chars:
            stop_tokens = {
                "frame", "frames", "framedata", "data", "startup", "recovery", "active",
                "on", "hit", "block", "compare", "comparison", "versus", "vs", "which",
                "is", "faster", "better", "tc", "target", "combo", "combos", "how", "fast",
                "quick", "speed", "of", "the", "a", "an", "for", "with", "please", "show",
                "tell", "me", "about", "can", "i", "punish", "punishable", "stats",
                "send", "post", "drop", "give", "link",
                "gif", "gifs", "hitbox", "hitboxes",
            }
            char_tokens = set()
            for char in mentioned_chars:
                char_tokens.update(re.findall(r"[a-z0-9]+", str(char).lower()))
                normalized_char = normalize_char_name(char)
                if normalized_char:
                    char_tokens.add(normalized_char)
            residual_tokens = [
                tok for tok in text_tokens
                if tok not in stop_tokens and tok not in char_tokens
            ]
            if residual_tokens:
                explicit_move_attempt = True
                residual_candidate = " ".join(residual_tokens).strip()
                if residual_candidate and residual_candidate not in potential_inputs:
                    potential_inputs.append(residual_candidate)

        strength_prefix_re = re.compile(r"^(?:lp|mp|hp|lk|mk|hk|pp|kk|od|ex|light|medium|heavy|l|m|h)\s+")
        text_compact = re.sub(r"[^a-z0-9]", "", text_lower)

        def token_matches_move_name(name_token, query_token):
            if (name_token == "od" and query_token == "ex") or (name_token == "ex" and query_token == "od"):
                return True
            if name_token == query_token:
                return True
            if len(query_token) >= 3 and name_token.startswith(query_token):
                return True
            if len(name_token) >= 3 and query_token.startswith(name_token):
                return True
            return False

        motion_button_notation_present = bool(
            re.search(
                r"\b[1-9][0-9]*\s*(?:\+)?\s*(?:lp|mp|hp|lk|mk|hk|pp|kk|p|k)\b",
                text_lower,
            )
        )

        for char in mentioned_chars:
            char_data = FRAME_DATA[char]
            for row in char_data:
                for name_key in ["cmnName", "moveName"]:
                    raw_name = str(row.get(name_key, "")).lower().strip()
                    if not raw_name:
                        continue
                    candidate_names = [raw_name]
                    stripped_name = strength_prefix_re.sub("", raw_name).strip()
                    if (
                        stripped_name
                        and stripped_name != raw_name
                        and not query_has_explicit_strength
                    ):
                        candidate_names.append(stripped_name)
                    if char == "sagat":
                        tigerless_candidates = []
                        for name_variant in list(candidate_names):
                            tigerless_variant = re.sub(r"\btiger\b", "", name_variant)
                            tigerless_variant = re.sub(r"\s+", " ", tigerless_variant).strip()
                            if (
                                tigerless_variant
                                and tigerless_variant != name_variant
                                and tigerless_variant not in candidate_names
                            ):
                                tigerless_candidates.append(tigerless_variant)
                        candidate_names.extend(tigerless_candidates)
                    for candidate_name in candidate_names:
                        candidate_has_strength_prefix = bool(strength_prefix_re.match(candidate_name))
                        if query_has_explicit_strength and not candidate_has_strength_prefix:
                            continue
                        candidate_tokens = re.findall(r"[a-z0-9]+", candidate_name)
                        if not candidate_tokens:
                            continue
                        if len(candidate_tokens) < 2:
                            if (
                                char == "sagat"
                                and len(candidate_tokens) == 1
                                and len(candidate_tokens[0]) >= 4
                                and candidate_tokens[0] in text_tokens
                            ):
                                if candidate_name not in potential_inputs:
                                    potential_inputs.append(candidate_name)
                            if (
                                char == "ken"
                                and len(candidate_tokens) == 1
                                and candidate_tokens[0] == "run"
                                and "run" in text_tokens
                                and not re.search(
                                    r"\brun\s+(?:stop|overhead|step|dp|shoryu|shoryuken|tatsu|dragonlash|dragon\s+lash|lash)\b",
                                    text_lower,
                                )
                            ):
                                if candidate_name not in potential_inputs:
                                    potential_inputs.append(candidate_name)
                            continue
                        candidate_compact = re.sub(r"[^a-z0-9]", "", candidate_name)
                        if (
                            len(candidate_compact) >= 6
                            and candidate_compact in text_compact
                        ):
                            if candidate_name not in potential_inputs:
                                potential_inputs.append(candidate_name)
                            continue
                        if all(
                            any(token_matches_move_name(name_tok, query_tok) for query_tok in text_tokens)
                            for name_tok in candidate_tokens
                        ):
                            if candidate_name not in potential_inputs:
                                potential_inputs.append(candidate_name)

        # also valid simple inputs: "mp", "hk" if preceded by char?

        for char in mentioned_chars:
            char_data = FRAME_DATA[char]

            # Check against potential inputs found via regex
            char_lookup_inputs = potential_inputs
            if comparison_char_inputs.get(char):
                char_lookup_inputs = comparison_char_inputs[char]
            for inp in char_lookup_inputs:
                row = lookup_frame_data(char, inp)
                if row and row not in results:
                    results.append(row)

            # Also check strict "frame data [char] [move]" remainder if exists
            # (This handles the specific verified cases)

            # "brute force" check for short inputs if the regex missed them (like "mp")
            # only if the string looks like "ryu mp"
            def is_button_part_of_dp_motion(button):
                return bool(
                    re.search(
                        rf"\b{re.escape(char)}\s+{button}\s*(?:\+)?\s*(?:dp|srk|shoryu|shoryuken)\b",
                        text_lower,
                    )
                )

            if not special_grab_query and not motion_button_notation_present:
                if f"{char} mp" in text_lower and not is_button_part_of_dp_motion("mp"):
                    row = lookup_frame_data(char, "mp")
                    if row and row not in results:
                        results.append(row)
                if f"{char} mk" in text_lower and not is_button_part_of_dp_motion("mk"):
                    row = lookup_frame_data(char, "mk")
                    if row and row not in results:
                        results.append(row)
                if f"{char} hp" in text_lower and not is_button_part_of_dp_motion("hp"):
                    row = lookup_frame_data(char, "hp")
                    if row and row not in results:
                        results.append(row)
                if f"{char} hk" in text_lower and not is_button_part_of_dp_motion("hk"):
                    row = lookup_frame_data(char, "hk")
                    if row and row not in results:
                        results.append(row)
                if f"{char} lp" in text_lower and not is_button_part_of_dp_motion("lp"):
                    row = lookup_frame_data(char, "lp")
                    if row and row not in results:
                        results.append(row)
                if f"{char} lk" in text_lower and not is_button_part_of_dp_motion("lk"):
                    row = lookup_frame_data(char, "lk")
                    if row and row not in results:
                        results.append(row)

        # SPD/360 variations - for Zangief (Screw Piledriver) and Lily (Mexican Typhoon)
            if not (char == "zangief" and zangief_borscht_context):
                spd_patterns = [
                    ("l spd", "lp"), ("m spd", "mp"), ("h spd", "hp"),
                    ("light spd", "lp"), ("medium spd", "mp"), ("heavy spd", "hp"),
                    ("lspd", "lp"), ("mspd", "mp"), ("hspd", "hp"),
                    ("od spd", "od"), ("ex spd", "od"),
                    ("l command grab", "lp"), ("m command grab", "mp"), ("h command grab", "hp"),
                    ("light command grab", "lp"), ("medium command grab", "mp"), ("heavy command grab", "hp"),
                    ("od command grab", "od"), ("ex command grab", "od"),
                    ("360+lp", "lp"), ("360+mp", "mp"), ("360+hp", "hp"), ("360+pp", "od"),
                    ("360lp", "lp"), ("360mp", "mp"), ("360hp", "hp"), ("360pp", "od"),
                    ("command grab", ""), ("spd", ""), ("360", ""),
                ]
                for pattern, strength in spd_patterns:
                    if pattern in text_lower:
                        if not strength and query_has_explicit_strength:
                            continue
                        # Try both Screw Piledriver (Gief) and Mexican Typhoon (Lily)
                        if strength:
                            move_names = [
                                f"{strength} command grab",
                                f"{strength} screw piledriver",
                                f"{strength} mexican typhoon",
                            ]
                        else:
                            move_names = ["command grab", "screw piledriver", "mexican typhoon"]
                        for move_name in move_names:
                            row = lookup_frame_data(char, move_name)
                            if row and row not in results:
                                results.append(row)
                                break
                        break  # Only match one SPD variant

            if char == "zangief" and zangief_borscht_context:
                borscht_lookup = "od borscht dynamite" if (
                    re.search(r"\b(?:od|ex)\s+borscht\b", text_lower)
                    or re.search(r"\bj\.?\s*360\s*\+?\s*kk\b", text_lower)
                    or re.search(r"\bj\s+360\s*\+?\s*kk\b", text_lower)
                ) else "borscht dynamite"
                row = lookup_frame_data(char, borscht_lookup)
                if row and row not in results:
                    results.append(row)

            # Chun-Li serenity stream aliases are special-cased here because they
            # use generic "stance"/"ss" wording that would otherwise be too broad.
            if char == "chun-li":
                stance_patterns = [
                    ("stance lp", "stance lp"), ("stance mp", "stance mp"), ("stance hp", "stance hp"),
                    ("stance lk", "stance lk"), ("stance mk", "stance mk"), ("stance hk", "stance hk"),
                    ("ss lp", "ss lp"), ("ss mp", "ss mp"), ("ss hp", "ss hp"),
                    ("ss lk", "ss lk"), ("ss mk", "ss mk"), ("ss hk", "ss hk"),
                    ("serenity stream", "stance"), ("stance", "stance"), ("ss", "ss"),
                ]
                for pattern, alias_key in stance_patterns:
                    if pattern in text_lower:
                        row = lookup_frame_data(char, alias_key)
                        if row and row not in results:
                            results.append(row)
                        break  # Only match one stance variant

            # Lily Mexican Typhoon variations
            typhoon_patterns = [
                ("l typhoon", "l typhoon"), ("m typhoon", "m typhoon"), ("h typhoon", "h typhoon"),
                ("light typhoon", "light typhoon"), ("medium typhoon", "medium typhoon"), ("heavy typhoon", "heavy typhoon"),
                ("od typhoon", "od typhoon"), ("ex typhoon", "ex typhoon"),
                ("mexican typhoon", "mexican typhoon"), ("typhoon", "typhoon"),
            ]
            for pattern, alias_key in typhoon_patterns:
                if pattern in text_lower:
                    row = lookup_frame_data(char, alias_key)
                    if row and row not in results:
                        results.append(row)
                    break  # Only match one typhoon variant

        if special_grab_query and query_has_explicit_strength and not results and mentioned_chars:
            for char in mentioned_chars:
                grab_variants = []
                for row in FRAME_DATA.get(char, []):
                    cmn_name = str(row.get("cmnName", "")).lower()
                    if "command grab" in cmn_name or re.search(r"\bspd\b", cmn_name):
                        grab_variants.append(row)
                if len(grab_variants) >= 2:
                    variant_lines = "\n".join(
                        f"- {row.get('moveName', '?')} ({row.get('numCmd', '?')})"
                        for row in grab_variants
                    )
                    special_prompt_blocks.append(
                        f"**Special Strength Options ({char.capitalize()})**\n"
                        f"Command Grab variants:\n{variant_lines}\n"
                        "Reply or make a new prompt with the exact command or move name."
                    )

        if query_requires_denjin and results:
            denjin_results = [row for row in results if row_is_denjin_variant(row)]
            results = denjin_results

        if query_requires_charged and results:
            charged_results = [row for row in results if row_is_charged_variant(row)]
            if charged_results:
                results = charged_results
            else:
                upgraded_charged_results = []
                for row in results:
                    row_char_key = resolve_character_key(row.get("char_name", ""))
                    if not row_char_key:
                        continue

                    row_num_cmd_base = normalize_num_cmd_token(row.get("numCmd", ""))
                    if not row_num_cmd_base:
                        continue

                    charged_match = None
                    for candidate in FRAME_DATA.get(row_char_key, []):
                        if not row_is_charged_variant(candidate):
                            continue
                        candidate_base = normalize_num_cmd_token(candidate.get("numCmd", ""))
                        if candidate_base == row_num_cmd_base:
                            charged_match = candidate
                            break

                    if charged_match and charged_match not in upgraded_charged_results:
                        upgraded_charged_results.append(charged_match)

                if upgraded_charged_results:
                    results = upgraded_charged_results

        if query_has_explicit_strength and results:
            wants_od_strength = bool(re.search(r"\b(od|ex)\b", text_lower))
            wants_non_od_strength = bool(
                re.search(r"\b(lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b", text_lower)
            )
            if wants_od_strength:
                od_results = [row for row in results if row_is_od_variant(row)]
                if od_results:
                    results = od_results
            elif wants_non_od_strength:
                non_od_results = [row for row in results if not row_is_od_variant(row)]
                if non_od_results:
                    results = non_od_results

            exact_strength_results = [
                row for row in results
                if row_matches_explicit_strength(row, text_lower)
            ]
            if exact_strength_results:
                results = exact_strength_results

            exact_term_results = [
                row for row in results
                if row_matches_query_move_terms(row)
            ]
            if exact_term_results:
                results = exact_term_results

        if alex_stance_followup_context and results:
            filtered_results = []
            for row in results:
                row_char_key = normalize_char_name(row.get("char_name", ""))
                if row_char_key != "alex":
                    filtered_results.append(row)
                    continue
                row_num_cmd_norm = normalize_num_cmd_token(row.get("numCmd", ""))
                row_cmn_name = str(row.get("cmnName", "")).lower()
                if row_num_cmd_norm.startswith("2pp>") or "stance >" in row_cmn_name:
                    filtered_results.append(row)
            if filtered_results:
                results = filtered_results

        if air_tatsu_context and results:
            air_tatsu_chars = {"ryu", "ken", "akuma"}
            mentioned_air_tatsu_chars = set(mentioned_chars) & air_tatsu_chars
            if mentioned_air_tatsu_chars:
                filtered_results = []
                for row in results:
                    row_char_key = normalize_char_name(row.get("char_name", ""))
                    row_char_matches = any(
                        normalize_char_name(char) == row_char_key
                        for char in mentioned_air_tatsu_chars
                    )
                    if not row_char_matches:
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    num_cmd = str(row.get("numCmd", "")).lower()
                    if "air" in move_name or "air" in cmn_name or "(air)" in num_cmd:
                        filtered_results.append(row)
                if filtered_results:
                    results = filtered_results

        if air_fireball_context and results:
            mentioned_air_fireball_chars = set(mentioned_chars) & {"akuma"}
            if mentioned_air_fireball_chars:
                allow_demon_fireball = any(token in text_tokens for token in {"demon", "flip", "raid"})
                filtered_results = []
                for row in results:
                    row_char_key = normalize_char_name(row.get("char_name", ""))
                    row_char_matches = any(
                        normalize_char_name(char) == row_char_key
                        for char in mentioned_air_fireball_chars
                    )
                    if not row_char_matches:
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    num_cmd = str(row.get("numCmd", "")).lower()
                    is_air_fireball_row = (
                        "air fireball" in cmn_name
                        or "zanku" in move_name
                        or "zanku" in cmn_name
                        or "(air)" in num_cmd
                    )
                    if not is_air_fireball_row:
                        continue
                    if not allow_demon_fireball and ("demon" in move_name or "demon" in cmn_name):
                        continue
                    filtered_results.append(row)
                if filtered_results:
                    results = filtered_results
                else:
                    fallback_input = "od zanku hadoken" if query_wants_od_strength else "zanku hadoken"
                    fallback_row = lookup_frame_data("akuma", fallback_input)
                    if fallback_row:
                        results = [fallback_row]

        if air_sa1_context and results:
            mentioned_air_sa1_chars = set(mentioned_chars) & {"akuma"}
            if mentioned_air_sa1_chars:
                filtered_results = []
                for row in results:
                    row_char_key = normalize_char_name(row.get("char_name", ""))
                    row_char_matches = any(
                        normalize_char_name(char) == row_char_key
                        for char in mentioned_air_sa1_chars
                    )
                    if not row_char_matches:
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    num_cmd = str(row.get("numCmd", "")).lower()
                    is_air_sa1_row = (
                        "tenma" in move_name
                        or "gozanku" in move_name
                        or (
                            "super art level 1" in cmn_name
                            and ("air" in cmn_name or "(air)" in num_cmd)
                        )
                    )
                    if is_air_sa1_row:
                        filtered_results.append(row)
                if filtered_results:
                    results = filtered_results
                else:
                    fallback_row = lookup_frame_data("akuma", "tenma gozanku")
                    if fallback_row:
                        results = [fallback_row]

        if (query_requests_sa3 or air_sa3_context) and results:
            mentioned_sa3_chars = set(mentioned_chars) & {"akuma"}
            if mentioned_sa3_chars:
                filtered_results = []
                for row in results:
                    row_char_key = normalize_char_name(row.get("char_name", ""))
                    row_char_matches = any(
                        normalize_char_name(char) == row_char_key
                        for char in mentioned_sa3_chars
                    )
                    if not row_char_matches:
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    num_cmd = str(row.get("numCmd", "")).lower()
                    is_air_variant = "air" in move_name or "air" in cmn_name or "(air)" in num_cmd
                    is_ca_variant = row_is_ca_variant(row)
                    if not is_air_variant and not is_ca_variant:
                        filtered_results.append(row)
                if filtered_results:
                    results = filtered_results
                else:
                    fallback_row = lookup_frame_data("akuma", "sip of calamity")
                    if fallback_row:
                        results = [fallback_row]

        if query_requests_ca and results:
            ca_rows = [row for row in results if row_is_ca_variant(row)]
            if ca_rows:
                results = ca_rows

        if query_requests_air_context and results:
            air_rows = []
            for row in results:
                move_name = str(row.get("moveName", "")).lower()
                cmn_name = str(row.get("cmnName", "")).lower()
                num_cmd = str(row.get("numCmd", "")).lower()
                if "air" in move_name or "air" in cmn_name or "(air)" in num_cmd:
                    air_rows.append(row)
            if air_rows:
                results = air_rows

        if query_requires_stocked and results:
            stocked_rows = [row for row in results if row_is_stocked_variant(row)]
            if stocked_rows:
                results = stocked_rows

        if (
            "jamie" in mentioned_chars
            and results
            and re.search(
                r"\b(?:rekka|freeflow|palm|swagger|arrow\s+kick|upkicks?|drink(?:\s+activation)?|activation)\b",
                text_lower,
            )
        ):
            jamie_special_rows = [
                row
                for row in results
                if str(row.get("moveType", "")).strip().lower()
                in {"special", "movement-special", "super", "command-grab"}
            ]
            if jamie_special_rows:
                results = jamie_special_rows

        if akuma_followup_alias and results:
            alias_lower = akuma_followup_alias.lower()
            followup_keyword = None
            if "gou rasen" in alias_lower:
                followup_keyword = "gou rasen"
            elif "gou zanku" in alias_lower:
                followup_keyword = "gou zanku"
            elif "low" in alias_lower or "slide" in alias_lower:
                followup_keyword = "low slash"
            elif "chop" in alias_lower or "guillotine" in alias_lower:
                followup_keyword = "guillotine"
            elif "divekick" in alias_lower or "blade kick" in alias_lower:
                followup_keyword = "blade kick"
            elif any(token in alias_lower for token in ("swoop", "empty", "stop", "feint")):
                followup_keyword = "swoop"

            if followup_keyword:
                filtered_results = []
                for row in results:
                    row_char = normalize_char_name(row.get("char_name", ""))
                    if row_char != "akuma":
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    if (
                        followup_keyword == "blade kick"
                        and "demon" not in move_name
                        and "demon" not in cmn_name
                    ):
                        continue
                    if followup_keyword in move_name or followup_keyword in cmn_name:
                        filtered_results.append(row)
                if filtered_results:
                    results = filtered_results

        if ken_jinrai_followup_alias and results:
            alias_lower = ken_jinrai_followup_alias.lower()
            ken_followup_keywords = []
            if "low" in alias_lower or "lk" in alias_lower:
                ken_followup_keywords = ["jinrai > low", "kazekama", "> 6lk"]
            elif "overhead" in alias_lower or "mk" in alias_lower:
                ken_followup_keywords = ["jinrai > overhead", "gorai", "> 6mk"]
            elif any(token in alias_lower for token in ("heavy", "launcher", "hk")):
                ken_followup_keywords = ["jinrai > heavy", "senka", "> 6hk"]

            if ken_followup_keywords:
                filtered_results = []
                for row in results:
                    row_char = normalize_char_name(row.get("char_name", ""))
                    if row_char != "ken":
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    num_cmd = str(row.get("numCmd", "")).lower()
                    if any(
                        keyword in move_name or keyword in cmn_name or keyword in num_cmd
                        for keyword in ken_followup_keywords
                    ):
                        filtered_results.append(row)
                if filtered_results:
                    results = filtered_results

        if deejay_sway_followup_alias and results:
            alias_lower = deejay_sway_followup_alias.lower()
            deejay_char_key_norm = normalize_char_name("dee jay")
            deejay_followup_keywords = []
            if "low" in alias_lower:
                deejay_followup_keywords = ["funky slicer", "sway > low", "> lk"]
            elif "overhead" in alias_lower:
                deejay_followup_keywords = ["waning moon", "sway > overhead", "> mk"]
            elif any(token in alias_lower for token in ("launch", "launcher", "hk")):
                deejay_followup_keywords = ["maximum strike", "sway > launcher", "> hk"]
            elif any(token in alias_lower for token in ("feint", "dash", "backdash")):
                deejay_followup_keywords = [
                    "juggling sway",
                    "sway > dash > backdash",
                    "> 6p > 4p",
                ]

            if deejay_followup_keywords:
                filtered_results = []
                for row in results:
                    row_char = normalize_char_name(row.get("char_name", ""))
                    if row_char != deejay_char_key_norm:
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    num_cmd = str(row.get("numCmd", "")).lower()
                    if any(
                        keyword in move_name or keyword in cmn_name or keyword in num_cmd
                        for keyword in deejay_followup_keywords
                    ):
                        filtered_results.append(row)
                if filtered_results:
                    results = filtered_results

        if (
            not query_has_explicit_strength
            and results
            and not target_combo_query
            and not query_requires_stocked
            and not query_requests_ca
        ):
            existing_special_prompt_keys = set()

            def variant_is_air_move(row):
                move_name = str(row.get("moveName", "")).lower()
                cmn_name = str(row.get("cmnName", "")).lower()
                num_cmd = str(row.get("numCmd", "")).lower()
                return (
                    "(air" in num_cmd
                    or "air" in move_name
                    or "air" in cmn_name
                    or "aerial" in move_name
                    or "aerial" in cmn_name
                )

            for prompt_block in special_prompt_blocks:
                char_match = re.search(r"Special Strength Options \(([^)]+)\)", prompt_block)
                base_match = re.search(r"\n([^\n]+) variants:", prompt_block)
                if not char_match or not base_match:
                    continue
                prompt_char = normalize_char_name(char_match.group(1))
                prompt_base = str(base_match.group(1)).lower().strip()
                if prompt_char and prompt_base:
                    existing_special_prompt_keys.add((prompt_char, prompt_base))

            ambiguous_special_keys = set()
            for row in results:
                row_char_norm = normalize_char_name(row.get("char_name", ""))
                if not row_char_norm:
                    continue
                if mentioned_chars and row_char_norm not in {
                    normalize_char_name(char) for char in mentioned_chars
                }:
                    continue
                row_char_key = resolve_character_key(row.get("char_name", ""))
                if not row_char_key:
                    continue
                if not is_special_motion_num_cmd(row.get("numCmd", "")):
                    continue

                base_name = get_special_canonical_base_name(row)
                if not base_name:
                    continue

                if row_char_norm == "ryu" and base_name in {"super art level 1", "super art level 2"}:
                    continue

                key = (row_char_norm, base_name)
                if key in existing_special_prompt_keys or key in ambiguous_special_keys:
                    continue

                variants = []
                for candidate in FRAME_DATA.get(row_char_key, []):
                    if not is_special_motion_num_cmd(candidate.get("numCmd", "")):
                        continue
                    if get_special_canonical_base_name(candidate) != base_name:
                        continue
                    if query_requires_denjin and not row_is_denjin_variant(candidate):
                        continue
                    variants.append(candidate)

                if query_requests_air_context and not any(
                    variant_is_air_move(candidate) for candidate in variants
                ):
                    continue

                if len(variants) < 2:
                    continue

                if len(variants) == 2:
                    od_variants = [candidate for candidate in variants if row_is_od_variant(candidate)]
                    non_od_variants = [candidate for candidate in variants if not row_is_od_variant(candidate)]
                    if len(od_variants) == 1 and len(non_od_variants) == 1:
                        chosen_variant = od_variants[0] if query_wants_od_strength else non_od_variants[0]
                        if chosen_variant not in results:
                            results.append(chosen_variant)
                        continue

                variant_lines = "\n".join(
                    f"- {candidate.get('moveName', '?')} ({candidate.get('numCmd', '?')})"
                    for candidate in variants
                )
                special_prompt_blocks.append(
                    f"**Special Strength Options ({row_char_key.capitalize()})**\n"
                    f"{base_name.title()} variants:\n{variant_lines}\n"
                    "Reply or make a new prompt with the exact strength+move."
                )
                ambiguous_special_keys.add(key)

            if ambiguous_special_keys:
                filtered_results = []
                for row in results:
                    row_char = normalize_char_name(row.get("char_name", ""))
                    row_base = get_special_canonical_base_name(row)
                    row_key = (row_char, row_base)
                    if (
                        is_special_motion_num_cmd(row.get("numCmd", ""))
                        and row_key in ambiguous_special_keys
                    ):
                        continue
                    filtered_results.append(row)
                results = filtered_results

    if special_prompt_blocks and (
        (
            not query_has_explicit_strength
            and not query_requires_stocked
            and not query_requests_ca
        )
        or (special_grab_query and not results)
    ):
        results = []

    if (
        wants_comparison
        and len(mentioned_chars) >= 2
        and len(comparison_char_inputs) >= 2
        and not special_prompt_blocks
    ):
        scoped_comparison_rows = []
        for char in mentioned_chars:
            scoped_inputs = comparison_char_inputs.get(char, [])
            for scoped_input in scoped_inputs:
                scoped_row = lookup_frame_data(char, scoped_input)
                if scoped_row and scoped_row not in scoped_comparison_rows:
                    scoped_comparison_rows.append(scoped_row)
        if scoped_comparison_rows:
            results = scoped_comparison_rows

    if target_combo_query:
        if tc_prompt_blocks and not tc_selected_combos:
            results = []
        else:
            filtered_tc_results = []
            for row in results:
                num_cmd_compact = re.sub(r"\s+", "", str(row.get("numCmd", "")).lower())
                if ">" not in num_cmd_compact:
                    continue
                if tc_selected_combos and num_cmd_compact not in tc_selected_combos:
                    continue
                if tc_base_tokens and not any(
                    num_cmd_compact.startswith(f"{base}>") for base in tc_base_tokens
                ):
                    continue
                if row not in filtered_tc_results:
                    filtered_tc_results.append(row)
            if filtered_tc_results:
                results = filtered_tc_results
            elif tc_prompt_blocks:
                results = []

    # Format the results
    formatted_blocks = []
    
    # 3. Add Character Stats if relevant keywords found
    stats_keywords = ["stats", "health", "health", "drive", "reversal", "jump", "dash", "speed", "throw"]
    wants_stats = any(k in text_lower for k in stats_keywords)
    if startup_alias_query and re.search(r"\b[1-9][0-9]*[a-zA-Z]{1,3}\b", text_lower):
        wants_stats = False
    if wants_frame_data and explicit_move_attempt:
        wants_stats = False
    
    if wants_stats:
        for char in mentioned_chars:
            if char in FRAME_STATS:
                s = FRAME_STATS[char]
                # Format specific stats or all of them? 
                # Let's provide the key ones: Health, Best Reversal, Dashes, Jumps
                # The user asked for "best reversal" specifically.
                reversal_name = s.get('bestReversal', '?')
                
                stats_block = (
                    f"**{char.capitalize()} Stats**\n"
                    f"Health: {s.get('health', '?')}\n"
                    f"Best Reversal: {reversal_name}\n"
                    f"Forward Dash: {s.get('fDash', '?')}f // Back Dash: {s.get('bDash', '?')}f\n"
                    f"Jump: {s.get('nJump', '?')}f\n"
                )
                formatted_blocks.append(stats_block)
                
                # RECURSIVE LOOKUP: If we have a best reversal name, fetch its REAL frame data
                # so the LLM doesn't hallucinate it.
                if reversal_name and reversal_name != '?':
                     # Try to find this move in the moves list
                     rev_row = lookup_frame_data(char, str(reversal_name))
                     if rev_row and rev_row not in results:
                         results.append(rev_row)

    # 4. AUTO-INJECT KEY MOVES (Context Injection)
    # If we have a character but NO specific moves found (e.g. "Help me with Ryu"),
    # the LLM will try to give advice about buttons. We MUST provide the data for those likely buttons
    # to prevent hallucinations (like saying 5MK is special cancellable when it isn't).
    viper_air_burnkick_query = bool(
        "c.viper" in mentioned_chars
        and re.search(
            r"\b(?:air|aerial)\s+burn(?:ing)?\s*kicks?\b"
            r"|\b(?:air|aerial)\s+burnkicks?\b"
            r"|\bburn(?:ing)?\s*kicks?\s+(?:air|aerial)\b"
            r"|\bburnkicks?\s+(?:air|aerial)\b"
            r"|\bj\.?\s*236k\b"
            r"|\b236k\s*(?:\(air\)|air|aerial)\b",
            text_lower,
        )
    )
    if viper_air_burnkick_query and query_has_explicit_strength and results:
        preferred_air_input = "air burn kick"
        if re.search(r"\b(?:od|ex|236kk)\b", text_lower):
            preferred_air_input = "od air burn kick"
        elif re.search(r"\b(?:h|heavy|hk|236hk)\b", text_lower):
            preferred_air_input = "h air burn kick"
        elif re.search(r"\b(?:m|medium|mk|236mk)\b", text_lower):
            preferred_air_input = "m air burn kick"
        elif re.search(r"\b(?:l|light|lk|236lk)\b", text_lower):
            preferred_air_input = "l air burn kick"

        preferred_air_row = lookup_frame_data("c.viper", preferred_air_input)
        if preferred_air_row and preferred_air_row not in results:
            results.insert(0, preferred_air_row)

        filtered_results = []
        for row in results:
            move_name = str(row.get("moveName", "")).lower()
            cmn_name = str(row.get("cmnName", "")).lower()
            num_cmd = str(row.get("numCmd", "")).lower()
            burnkick_row = "burn" in move_name or "burn" in cmn_name
            if not burnkick_row:
                filtered_results.append(row)
                continue
            if (
                "(air" in num_cmd
                or "air" in move_name
                or "air" in cmn_name
                or "aerial" in move_name
                or "aerial" in cmn_name
            ):
                filtered_results.append(row)
        if filtered_results:
            results = filtered_results

    if (
        wants_frame_data
        and mentioned_chars
        and not results
        and not target_combo_query
        and not special_prompt_blocks
        and not explicit_move_attempt
    ):
        key_moves = ["5MP", "5MK", "2MK", "5HP", "2HP", "5HK", "2HK"]
        for char in mentioned_chars:
            for km in key_moves:
                k_row = lookup_frame_data(char, km)
                if k_row and k_row not in results:
                    results.append(k_row)

    if (
        wants_frame_data
        and mentioned_chars
        and explicit_move_attempt
        and not results
        and not tc_prompt_blocks
        and not special_prompt_blocks
    ):
        missing_scrolls_query = True

    has_results = bool(results)

    if not wants_frame_data and (
        wants_info or (mentioned_chars and not has_results and not wants_bnb and not wants_stats)
    ):
        for char in mentioned_chars:
            if char in CHARACTER_INFO:
                info_blocks.append(
                    f"**{char.capitalize()} Overview:**\n{CHARACTER_INFO[char]}"
                )

    for move_data in results:
        def clean(val):
            return str(val).replace('*', ',')

        startup = clean(move_data.get('startup', '-'))
        active = clean(move_data.get('active', '-'))
        recovery = clean(move_data.get('recovery', '-')).replace('(', ' (Whiff: ')
        cancel = clean(move_data.get('xx', '-'))
        damage = clean(move_data.get('dmg', '-'))
        guard = clean(move_data.get('atkLvl', '-'))
        atk_range = format_attack_range_for_table(move_data)
        on_hit = clean(move_data.get('onHit', '-'))
        on_block = clean(move_data.get('onBlock', '-'))
        extra_info = clean(move_data.get('extraInfo', '-')).replace('[', '').replace(']', '').replace('"', '')
        
        # New Stats (Drive/Super)
        ddoh = clean(move_data.get('DDoH', '-'))
        ddob = clean(move_data.get('DDoB', '-'))
        dgain = clean(move_data.get('DGain', '-'))
        ssoh = clean(move_data.get('SelfSoH', '-'))
        ssob = clean(move_data.get('SelfSoB', '-'))
        
        gauge_info = (
             f"Drive Dmg: Hit {ddoh} / Block {ddob} // Drive Gain: {dgain}\n"
             f"Super Gain: Hit {ssoh} / Block {ssob}\n"
        )
        
        # Hit Confirm Data (Always Included)
        hc_sp = clean(move_data.get('hcWinSpCa', '-')).strip() or '-'
        hc_tc = clean(move_data.get('hcWinTc', '-')).strip() or '-'
        hc_notes = clean(move_data.get('hcWinNotes', '-')).replace('[', '').replace(']', '').replace('"', '').strip() or '-'
        hc_info = (
            f"Hit Confirm (Sp/Su): {hc_sp} // Hit Confirm (TC): {hc_tc}\n"
            f"Hit Confirm Notes: {hc_notes}\n"
        )

        # Stun Data (Always Included)
        hstun = clean(move_data.get('hitstun', '-'))
        bstun = clean(move_data.get('blockstun', '-'))
        stun_info = f"Stun Frames: Hit {hstun} // Block {bstun}\n"

        block = (
            f"**{move_data['moveName']} ({move_data['numCmd']})**\n"
            f"Character: {move_data.get('char_name', 'Unknown')}\n"
            f"Startup: {startup} // Active: {active} // Recovery: {recovery}\n"
            f"Cancel: {cancel}\n"
            f"Damage: {damage}\n"
            f"Guard: {guard}\n"
            f"Range: {atk_range}\n"
            f"On Hit: {on_hit} // On Block: {on_block}\n"
            f"{gauge_info}"
            f"{stun_info}"
            f"{hc_info}"
            f"Notes: {extra_info}"
        )
        formatted_blocks.append(block)

    if tc_prompt_blocks:
        formatted_blocks.extend(tc_prompt_blocks)
    if special_prompt_blocks:
        formatted_blocks.extend(special_prompt_blocks)
    
    sections = []
    if formatted_blocks:
        sections.append("\n\n".join(formatted_blocks))
    if info_blocks:
        sections.append("\n\n".join(info_blocks))
    if bnb_context:
        sections.append(bnb_context.strip())

    output = "\n\n---\n".join(sections)

    # Check for punish calculation
    punish_verdict = check_punish(text_lower, results)
    if punish_verdict:
        if output:
            output = punish_verdict + "\n\n---\n\n" + output
        else:
            output = punish_verdict

    has_frame_blocks = bool(formatted_blocks)
    has_combo_blocks = bool(bnb_context)
    has_overview_blocks = bool(info_blocks)
    if has_frame_blocks:
        mode = "frame"
    elif has_combo_blocks:
        mode = "combo"
    elif has_overview_blocks:
        mode = "overview"
    else:
        mode = "none"

    return {
        "data": output,
        "mode": mode,
        "rows": results,
        "startup_alias_query": startup_alias_query,
        "hitconfirm_alias_query": hitconfirm_alias_query,
        "super_gain_alias_query": super_gain_alias_query,
        "range_alias_query": range_alias_query,
        "wants_comparison": bool(wants_comparison),
        "property_only_query": property_only_query,
        "target_combo_query": target_combo_query,
        "missing_scrolls_query": missing_scrolls_query,
        "gif_query": gif_query,
        "explicit_move_attempt": explicit_move_attempt,
    }


def lookup_frame_data(character, move_input, _seen_inputs=None):
    """Search for a move in character's frame data by numCmd, plnCmd, or moveName."""
    move_input = str(move_input)
    seen_key = move_input.strip().lower()
    if _seen_inputs is None:
        _seen_inputs = set()
    if seen_key in _seen_inputs:
        return None
    _seen_inputs.add(seen_key)
    char_key = character.lower()
    if char_key not in FRAME_DATA:
        return None
    
    data = FRAME_DATA[char_key]
    move_input = normalize_jump_normal_text(move_input.lower().strip())

    def normalize_strength_word_shorthand(text):
        prefix_map = {"l": "light", "m": "medium", "h": "heavy"}

        def replace_prefix(match):
            token = match.group(1)
            rest = match.group(2)
            return f"{prefix_map[token]} {rest}"

        def replace_suffix(match):
            rest = match.group(1)
            token = match.group(2)
            return f"{rest} {prefix_map[token]}"

        text = re.sub(r"^(l|m|h)\s+(.+)$", replace_prefix, text)
        text = re.sub(r"^(.+)\s+(l|m|h)$", replace_suffix, text)
        return text

    move_input = normalize_strength_word_shorthand(move_input)

    def normalize_boomer_normal_notation(text):
        pattern = re.compile(
            r"\b(st|cr)\s*\.?\s*(lp|mp|hp|lk|mk|hk|l\s*p|m\s*p|h\s*p|l\s*k|m\s*k|h\s*k)\b"
        )

        def repl(match):
            stance = match.group(1).lower()
            button = re.sub(r"\s+", "", match.group(2).lower())
            prefix = "5" if stance == "st" else "2"
            return f"{prefix}{button}"

        return pattern.sub(repl, text)

    move_input = normalize_boomer_normal_notation(move_input)
    move_input = re.sub(r"^(?:7|9)\s*(lp|mp|hp|lk|mk|hk)$", r"jump \1", move_input)

    original_move_input = move_input
    query_requests_air_context = bool(re.search(r"\b(air|aerial)\b", original_move_input))
    query_requests_charged = bool(re.search(r"\b(charged|hold|held)\b", original_move_input))
    query_requests_sa1 = bool(
        re.search(r"\b(?:sa\s*1|super\s*art\s*1|super\s*1|level\s*1)\b", original_move_input)
    )
    query_requests_sa3 = bool(
        re.search(r"\b(?:sa\s*3|super\s*art\s*3|super\s*3|level\s*3)\b", original_move_input)
    )
    query_requests_ca = bool(re.search(r"\b(?:ca|critical\s+art)\b", original_move_input))
    stock_hint_tokens = ("stock", "stocked", "enhanced", "windclad")

    def token_is_stock_hint(token):
        token_norm = str(token or "").lower().strip()
        if not token_norm:
            return False
        if token_norm in stock_hint_tokens:
            return True
        return any(
            difflib.SequenceMatcher(None, token_norm, hint_token).ratio() >= 0.82
            for hint_token in stock_hint_tokens
        )

    query_requests_stocked = bool(
        re.search(r"\b(stock|stocked|enhanced|windclad|wind\s+clad)\b", original_move_input)
    ) or any(token_is_stock_hint(token) for token in re.findall(r"[a-z0-9]+", original_move_input))
    neutral_tokens = []
    input_tokens = re.findall(r"[a-z0-9]+", original_move_input)
    if (
        ("neutral" in input_tokens or "n" in input_tokens or "nj" in input_tokens)
        and ("jump" in input_tokens or "j" in input_tokens or "nj" in input_tokens)
    ):
        neutral_query = original_move_input
        neutral_query = re.sub(r"\bnj\b", "n jump", neutral_query)
        neutral_query = re.sub(r"\bneutral\b", "n", neutral_query)
        neutral_query = re.sub(r"\bj\b", "jump", neutral_query)
        neutral_query = re.sub(r"[^a-z0-9]+", " ", neutral_query)
        neutral_query = re.sub(r"\s+", " ", neutral_query).strip()
        if neutral_query:
            neutral_tokens = neutral_query.split()

    move_input = re.sub(r"^ex\s+", "od ", move_input)
    move_input = re.sub(r"\bdivekick\b", "dive kick", move_input)
    if not re.match(
        r"^(jump|j)[\s\.]+(?:(?:214|236|623|421|22|46|28|41236|63214)|(?:[123]\s*(?:lp|mp|hp|lk|mk|hk|p|k)))",
        move_input,
    ):
        move_input = re.sub(r"^(jump|j)[\s\.]+", "8", move_input)
    move_input = re.sub(
        r"^([1-9][0-9]*)\s*(?:\+)?\s*(lp|mp|hp|lk|mk|hk|pp|kk|p|k)$",
        r"\1\2",
        move_input,
    )

    def get_motion_suffixes(motion_digits):
        suffixes = set()
        for row in data:
            num_cmd = re.sub(r"\s+", "", str(row.get("numCmd", "")).lower())
            if not num_cmd.startswith(motion_digits):
                continue
            for suffix in ("lp", "mp", "hp", "lk", "mk", "hk", "pp", "kk"):
                if num_cmd.startswith(f"{motion_digits}{suffix}"):
                    suffixes.add(suffix)
        return suffixes

    def resolve_623_strength_suffix(strength_token, available_suffixes):
        token = strength_token.lower()
        explicit_suffix_map = {
            "lp": "lp",
            "mp": "mp",
            "hp": "hp",
            "lk": "lk",
            "mk": "mk",
            "hk": "hk",
        }
        if token in explicit_suffix_map:
            return explicit_suffix_map[token]

        strength_letter_map = {
            "l": "l",
            "m": "m",
            "h": "h",
            "light": "l",
            "medium": "m",
            "heavy": "h",
        }
        strength_letter = strength_letter_map.get(token)
        if not strength_letter:
            return None

        preferred_suffixes = {
            "l": ["lp", "lk"],
            "m": ["mp", "mk"],
            "h": ["hp", "hk"],
        }
        for suffix in preferred_suffixes[strength_letter]:
            if suffix in available_suffixes:
                return suffix

        fallback_suffixes = {
            "l": "lp",
            "m": "mp",
            "h": "hp",
        }
        return fallback_suffixes[strength_letter]

    def normalize_motion_strength_aliases(raw_input):
        normalized = re.sub(r"\s+", " ", raw_input).strip()
        motion_alias_pattern = r"(dp|srk|shoryu|shoryuken)"
        strength_token_pattern = r"(lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)"
        available_623_suffixes = get_motion_suffixes("623")

        od_motion_match = re.fullmatch(
            rf"(?:od|ex)\s*(?:\+)?\s*{motion_alias_pattern}",
            normalized,
        )
        if od_motion_match:
            if "pp" in available_623_suffixes:
                return "623pp"
            if "kk" in available_623_suffixes:
                return "623kk"
            return "623pp"

        strength_motion_match = re.fullmatch(
            rf"{strength_token_pattern}\s*(?:\+)?\s*{motion_alias_pattern}",
            normalized,
        )
        if strength_motion_match:
            strength_token = strength_motion_match.group(1)
            resolved_suffix = resolve_623_strength_suffix(
                strength_token,
                available_623_suffixes,
            )
            if resolved_suffix:
                return f"623{resolved_suffix}"
            return normalized

        motion_strength_match = re.fullmatch(
            rf"{motion_alias_pattern}\s*(?:\+)?\s*{strength_token_pattern}",
            normalized,
        )
        if motion_strength_match:
            strength_token = motion_strength_match.group(2)
            resolved_suffix = resolve_623_strength_suffix(
                strength_token,
                available_623_suffixes,
            )
            if resolved_suffix:
                return f"623{resolved_suffix}"

        return normalized

    def resolve_strength_special_input(raw_input):
        normalized = re.sub(r"\s+", " ", raw_input).strip().lower()
        if ">" in normalized or "->" in normalized:
            return normalized
        strength_map = {
            "light": ["lp", "lk"],
            "l": ["lp", "lk"],
            "medium": ["mp", "mk"],
            "m": ["mp", "mk"],
            "heavy": ["hp", "hk"],
            "h": ["hp", "hk"],
        }

        match = re.fullmatch(r"(light|medium|heavy|l|m|h)\s+(.+)", normalized)
        if not match:
            match = re.fullmatch(r"(.+)\s+(light|medium|heavy|l|m|h)", normalized)
            if not match:
                return normalized
            remainder = match.group(1).strip()
            strength_token = match.group(2)
        else:
            strength_token = match.group(1)
            remainder = match.group(2).strip()

        candidate_prefixes = strength_map.get(strength_token, [])
        if not candidate_prefixes:
            return normalized

        for prefix in candidate_prefixes:
            candidate = f"{prefix} {remainder}"
            candidate_compact = re.sub(r"[^a-z0-9]", "", candidate)
            for row in data:
                num_cmd = str(row.get("numCmd", "")).lower()
                pln_cmd = str(row.get("plnCmd", "")).lower()
                cmn_name = str(row.get("cmnName", "")).lower()
                move_name = str(row.get("moveName", "")).lower()
                if (
                    candidate == num_cmd
                    or candidate == pln_cmd
                    or candidate == cmn_name
                    or candidate in cmn_name
                    or candidate in move_name
                ):
                    return candidate
                cmn_compact = re.sub(r"[^a-z0-9]", "", cmn_name)
                move_compact = re.sub(r"[^a-z0-9]", "", move_name)
                if candidate_compact and (
                    candidate_compact in cmn_compact
                    or candidate_compact in move_compact
                ):
                    return candidate

        return normalized

    pre_strength_alias_input = move_input
    move_input = normalize_motion_strength_aliases(move_input)
    move_input = resolve_strength_special_input(move_input)

    combo_input = None
    if ">" in move_input or "->" in move_input:
        combo_input = re.sub(r"\s+", "", move_input.replace("->", ">"))

    def normalize_move_name_tokens(text):
        normalized = re.sub(r"[^a-z0-9]+", " ", str(text).lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized.split() if normalized else []

    def neutral_tokens_match(query_tokens, move_name_tokens):
        if not query_tokens:
            return False
        move_name_set = set(move_name_tokens)
        for token in query_tokens:
            if token == "jump":
                if not any(t == "j" or t.startswith("jump") for t in move_name_tokens):
                    return False
                continue
            if token == "n":
                if "n" not in move_name_set and "neutral" not in move_name_set:
                    return False
                continue
            if token not in move_name_set:
                return False
        return True

    def jump_tokens_match(query_tokens, move_name_tokens):
        if "jump" not in query_tokens:
            return False
        for token in query_tokens:
            if token in ("neutral", "n"):
                continue
            if token == "jump":
                if not any(t == "j" or t.startswith("jump") for t in move_name_tokens):
                    return False
                continue
            if token not in move_name_tokens:
                return False
        return True

    if "jump" in input_tokens:
        neutral_candidate = None
        for row in data:
            move_name_tokens = normalize_move_name_tokens(row.get("moveName", ""))
            if not move_name_tokens:
                continue
            if neutral_tokens:
                if neutral_tokens_match(neutral_tokens, move_name_tokens):
                    return row
                continue
            if not jump_tokens_match(input_tokens, move_name_tokens):
                continue
            if "neutral" in move_name_tokens or "n" in move_name_tokens:
                if neutral_candidate is None:
                    neutral_candidate = row
                continue
            return row
        if neutral_candidate:
            return neutral_candidate

    def normalize_num_cmd_for_lookup(value):
        normalized = re.sub(r"[\[\]\(\)\{\}]", "", str(value or "").lower())
        normalized = re.sub(r"\s+", "", normalized)
        return re.sub(r"[^a-z0-9>]", "", normalized)

    def normalize_num_cmd_generic_for_lookup(value):
        normalized = str(value or "").lower()
        normalized = re.sub(r"\([^)]*\)", "", normalized)
        normalized = re.sub(r"\[[^\]]*\]", "", normalized)
        normalized = re.sub(r"\{[^}]*\}", "", normalized)
        normalized = re.sub(r"\s+", "", normalized)
        return re.sub(r"[^a-z0-9>]", "", normalized)
    
    INPUT_ALIASES = {
        # DP/SRK
        "dp": "623",
        "srk": "623",
        "shoryu": "623",
        "shoryuken": "623",
        "hadoken": "fireball",
        "hadouken": "fireball",
        "denjin fireball": "denjin hadoken",
        "ex denjin fireball": "od denjin hadoken",
        "od denjin fireball": "od denjin hadoken",
        "ex denjin hadoken": "od denjin hadoken",
        # Global Super Art level aliases
        "sa1": "super art level 1",
        "sa2": "super art level 2",
        "sa3": "super art level 3",
        "level 1": "super art level 1",
        "level 2": "super art level 2",
        "level 3": "super art level 3",
        "lvl1": "super art level 1",
        "lvl2": "super art level 2",
        "lvl3": "super art level 3",
        "lv1": "super art level 1",
        "lv2": "super art level 2",
        "lv3": "super art level 3",
        "ca": "critical art",
        "critical": "critical art",
        "critical art": "critical art",
        "raging demon": "shun goku satsu",
        "sway": "juggling sway",
        "juggling sway": "juggling sway",
        "jus cool": "jus cool",
        "juscool": "jus cool",
        # Zangief SPD
        "360": "screw piledriver",
        "spd": "screw piledriver",
        "360p": "screw piledriver",
        "360+lp": "lp screw piledriver",
        "360+mp": "mp screw piledriver",
        "360+hp": "hp screw piledriver",
        "360+pp": "od screw piledriver",
        "360lp": "lp screw piledriver",
        "360mp": "mp screw piledriver",
        "360hp": "hp screw piledriver",
        "360pp": "od screw piledriver",
        "l spd": "lp screw piledriver",
        "m spd": "mp screw piledriver",
        "h spd": "hp screw piledriver",
        "od spd": "od screw piledriver",
        "ex spd": "od screw piledriver",
        "lspd": "lp screw piledriver",
        "mspd": "mp screw piledriver",
        "hspd": "hp screw piledriver",
        "light spd": "lp screw piledriver",
        "medium spd": "mp screw piledriver",
        "heavy spd": "hp screw piledriver",
        # Chun-Li Serenity Stream
        "stance": "serenity stream",
        "ss": "serenity stream",
        "stance lp": "orchid palm",
        "stance mp": "snake strike",
        "stance hp": "lotus fist",
        "stance lk": "forward strike",
        "stance mk": "senpu kick",
        "stance hk": "tenku kick",
        "ss lp": "orchid palm",
        "ss mp": "snake strike",
        "ss hp": "lotus fist",
        "ss lk": "forward strike",
        "ss mk": "senpu kick",
        "ss hk": "tenku kick",
        # Lily Mexican Typhoon
        "typhoon": "mexican typhoon",
        "mexican typhoon": "mexican typhoon",
        "l typhoon": "lp mexican typhoon",
        "m typhoon": "mp mexican typhoon",
        "h typhoon": "hp mexican typhoon",
        "od typhoon": "od mexican typhoon",
        "ex typhoon": "od mexican typhoon",
        "light typhoon": "lp mexican typhoon",
        "medium typhoon": "mp mexican typhoon",
        "heavy typhoon": "hp mexican typhoon",
    }

    CHARACTER_INPUT_ALIASES = {
        "dee jay": {
            "46p": "air slasher",
            "46lp": "lp air slasher",
            "46mp": "mp air slasher",
            "46hp": "hp air slasher",
            "46pp": "od air slasher",
            "air slasher": "air slasher",
            "slasher": "air slasher",
            "fireball": "air slasher",
            "lp fireball": "lp air slasher",
            "mp fireball": "mp air slasher",
            "hp fireball": "hp air slasher",
            "od fireball": "od air slasher",
            "ex fireball": "od air slasher",
            "light fireball": "lp air slasher",
            "medium fireball": "mp air slasher",
            "heavy fireball": "hp air slasher",
            "l fireball": "lp air slasher",
            "m fireball": "mp air slasher",
            "h fireball": "hp air slasher",
            "28k": "jackknife maximum",
            "28lk": "lk jackknife maximum",
            "28mk": "mk jackknife maximum",
            "28hk": "hk jackknife maximum",
            "28kk": "od jackknife maximum",
            "jackknife maximum": "jackknife maximum",
            "jackknife": "jackknife maximum",
            "upkicks": "jackknife maximum",
            "up kicks": "jackknife maximum",
            "flash kick": "jackknife maximum",
            "lk upkicks": "lk jackknife maximum",
            "mk upkicks": "mk jackknife maximum",
            "hk upkicks": "hk jackknife maximum",
            "od upkicks": "od jackknife maximum",
            "light upkicks": "lk jackknife maximum",
            "medium upkicks": "mk jackknife maximum",
            "heavy upkicks": "hk jackknife maximum",
            # Jus Cool / Sway followups
            "sway low": "jus cool > funky slicer",
            "sway low followup": "jus cool > funky slicer",
            "sway low follow up": "jus cool > funky slicer",
            "sway low lk followup": "jus cool > funky slicer",
            "sway low lk follow up": "jus cool > funky slicer",
            "sway low > lk followup": "jus cool > funky slicer",
            "sway low>lk followup": "jus cool > funky slicer",
            "sway lk followup": "jus cool > funky slicer",
            "sway lk follow up": "jus cool > funky slicer",
            "sway overhead": "jus cool > waning moon",
            "sway overhead followup": "jus cool > waning moon",
            "sway overhead follow up": "jus cool > waning moon",
            "sway overhead mk followup": "jus cool > waning moon",
            "sway overhead mk follow up": "jus cool > waning moon",
            "sway overhead > mk followup": "jus cool > waning moon",
            "sway overhead>mk followup": "jus cool > waning moon",
            "sway mk followup": "jus cool > waning moon",
            "sway mk follow up": "jus cool > waning moon",
            "sway launch": "jus cool > maximum strike",
            "sway launcher": "jus cool > maximum strike",
            "sway launch followup": "jus cool > maximum strike",
            "sway launch follow up": "jus cool > maximum strike",
            "sway launch hk followup": "jus cool > maximum strike",
            "sway launch hk follow up": "jus cool > maximum strike",
            "sway launch > hk followup": "jus cool > maximum strike",
            "sway launch>hk followup": "jus cool > maximum strike",
            "sway hk followup": "jus cool > maximum strike",
            "sway hk follow up": "jus cool > maximum strike",
            "sway feint": "jus cool > juggling dash > juggling sway",
            "sway feint followup": "jus cool > juggling dash > juggling sway",
            "sway feint follow up": "jus cool > juggling dash > juggling sway",
            "sway feint 6p 4p followup": "jus cool > juggling dash > juggling sway",
            "sway feint 6p 4p follow up": "jus cool > juggling dash > juggling sway",
            "sway feint 6p,4p followup": "jus cool > juggling dash > juggling sway",
            "sway feint > 6p,4p followup": "jus cool > juggling dash > juggling sway",
            "6p 4p followup": "jus cool > juggling dash > juggling sway",
            "6p,4p followup": "jus cool > juggling dash > juggling sway",
            "od sway low": "od jus cool > funky slicer",
            "od sway overhead": "od jus cool > waning moon",
            "od sway launch": "od jus cool > maximum strike",
            "od sway feint": "od jus cool > juggling dash > juggling sway",
            "ex sway low": "od jus cool > funky slicer",
            "ex sway overhead": "od jus cool > waning moon",
            "ex sway launch": "od jus cool > maximum strike",
            "ex sway feint": "od jus cool > juggling dash > juggling sway",
        },
        "jamie": {
            "drink": "the devil inside",
            "drink level 1": "the devil inside",
            "level 1 drink": "the devil inside",
            "1 drink": "the devil inside",
            "one drink": "the devil inside",
            "drink level 2": "the devil inside (2 drinks)",
            "level 2 drink": "the devil inside (2 drinks)",
            "2 drinks": "the devil inside (2 drinks)",
            "two drinks": "the devil inside (2 drinks)",
            "drink level 3": "the devil inside (3 drinks)",
            "level 3 drink": "the devil inside (3 drinks)",
            "3 drinks": "the devil inside (3 drinks)",
            "three drinks": "the devil inside (3 drinks)",
            "drink level 4": "the devil inside (4 drinks)",
            "level 4 drink": "the devil inside (4 drinks)",
            "4 drinks": "the devil inside (4 drinks)",
            "four drinks": "the devil inside (4 drinks)",
            "drink activation": "the devil inside (dr4 activation)",
            "dr4 activation": "the devil inside (dr4 activation)",
            "level 4 activation": "the devil inside (dr4 activation)",
            "rekka": "freeflow strikes",
            "freeflow": "freeflow strikes",
            "freeflow strikes": "freeflow strikes",
            "lp rekka": "lp freeflow strikes",
            "mp rekka": "mp freeflow strikes",
            "hp rekka": "hp freeflow strikes",
            "od rekka": "od freeflow strikes",
            "ex rekka": "od freeflow strikes",
            "lp freeflow": "lp freeflow strikes",
            "mp freeflow": "mp freeflow strikes",
            "hp freeflow": "hp freeflow strikes",
            "od freeflow": "od freeflow strikes",
            "ex freeflow": "od freeflow strikes",
            "rekka 1": "lp freeflow strikes",
            "rekka punch": "lp freeflow strikes 2",
            "rekka 2": "lp freeflow strikes 2",
            "rekka 2 punch": "lp freeflow strikes 2",
            "rekka 3": "lp freeflow strikes 3",
            "rekka 3 punch": "lp freeflow strikes 3",
            "rekka kick": "lp freeflow kicks 2",
            "freeflow kicks": "lp freeflow kicks 2",
            "rekka 2 kick": "lp freeflow kicks 2",
            "rekka 3 kick": "lp freeflow kicks 3",
            "lp rekka punch": "lp freeflow strikes 2",
            "lp rekka 2": "lp freeflow strikes 2",
            "lp rekka 2 punch": "lp freeflow strikes 2",
            "lp rekka 3": "lp freeflow strikes 3",
            "lp rekka 3 punch": "lp freeflow strikes 3",
            "lp rekka kick": "lp freeflow kicks 2",
            "lp rekka 2 kick": "lp freeflow kicks 2",
            "lp rekka 3 kick": "lp freeflow kicks 3",
            "mp rekka punch": "mp freeflow strikes 2",
            "mp rekka 2": "mp freeflow strikes 2",
            "mp rekka 2 punch": "mp freeflow strikes 2",
            "mp rekka 3": "mp freeflow strikes 3",
            "mp rekka 3 punch": "mp freeflow strikes 3",
            "mp rekka kick": "mp freeflow kicks 2",
            "mp rekka 2 kick": "mp freeflow kicks 2",
            "mp rekka 3 kick": "mp freeflow kicks 3",
            "hp rekka punch": "hp freeflow strikes 2",
            "hp rekka 2": "hp freeflow strikes 2",
            "hp rekka 2 punch": "hp freeflow strikes 2",
            "hp rekka 3": "hp freeflow strikes 3",
            "hp rekka 3 punch": "hp freeflow strikes 3",
            "hp rekka kick": "hp freeflow kicks 2",
            "hp rekka 2 kick": "hp freeflow kicks 2",
            "hp rekka 3 kick": "hp freeflow kicks 3",
            "od rekka punch": "od freeflow strikes 2",
            "od rekka 2": "od freeflow strikes 2",
            "od rekka 2 punch": "od freeflow strikes 2",
            "od rekka 3": "od freeflow strikes 3",
            "od rekka 3 punch": "od freeflow strikes 3",
            "od rekka kick": "od freeflow kicks 2",
            "od rekka 2 kick": "od freeflow kicks 2",
            "od rekka 3 kick": "od freeflow kicks 3",
            "ex rekka punch": "od freeflow strikes 2",
            "ex rekka 2": "od freeflow strikes 2",
            "ex rekka 3": "od freeflow strikes 3",
            "ex rekka kick": "od freeflow kicks 2",
            "ex rekka 2 kick": "od freeflow kicks 2",
            "ex rekka 3 kick": "od freeflow kicks 3",
            "palm": "swagger step",
            "swagger": "swagger step",
            "swagger step": "swagger step",
            "lp palm": "lp swagger step",
            "mp palm": "mp swagger step",
            "hp palm": "hp swagger step",
            "od palm": "od swagger step",
            "ex palm": "od swagger step",
            "light palm": "lp swagger step",
            "medium palm": "mp swagger step",
            "heavy palm": "hp swagger step",
            "l palm": "lp swagger step",
            "m palm": "mp swagger step",
            "h palm": "hp swagger step",
            "lp swagger": "lp swagger step",
            "mp swagger": "mp swagger step",
            "hp swagger": "hp swagger step",
            "od swagger": "od swagger step",
            "ex swagger": "od swagger step",
            "arrow kick": "arrow kick",
            "upkicks": "arrow kick",
            "up kicks": "arrow kick",
            "lp arrow kick": "lk arrow kick",
            "mp arrow kick": "mk arrow kick",
            "hp arrow kick": "hk arrow kick",
            "od arrow kick": "od arrow kick",
            "ex arrow kick": "od arrow kick",
            "light arrow kick": "lk arrow kick",
            "medium arrow kick": "mk arrow kick",
            "heavy arrow kick": "hk arrow kick",
            "l arrow kick": "lk arrow kick",
            "m arrow kick": "mk arrow kick",
            "h arrow kick": "hk arrow kick",
            "bakkai": "lk bakkai (drink 2)",
            "breakdance": "lk bakkai (drink 2)",
            "break dance": "lk bakkai (drink 2)",
            "lk bakkai": "lk bakkai (drink 2)",
            "mk bakkai": "mk bakkai (drink 2)",
            "hk bakkai": "hk bakkai (drink 2)",
            "od bakkai": "od bakkai (drink 2)",
            "ex bakkai": "od bakkai (drink 2)",
            "l bakkai": "lk bakkai (drink 2)",
            "m bakkai": "mk bakkai (drink 2)",
            "h bakkai": "hk bakkai (drink 2)",
            "light bakkai": "lk bakkai (drink 2)",
            "medium bakkai": "mk bakkai (drink 2)",
            "heavy bakkai": "hk bakkai (drink 2)",
            "lk breakdance": "lk bakkai (drink 2)",
            "mk breakdance": "mk bakkai (drink 2)",
            "hk breakdance": "hk bakkai (drink 2)",
            "od breakdance": "od bakkai (drink 2)",
            "ex breakdance": "od bakkai (drink 2)",
            "l breakdance": "lk bakkai (drink 2)",
            "m breakdance": "mk bakkai (drink 2)",
            "h breakdance": "hk bakkai (drink 2)",
            "light breakdance": "lk bakkai (drink 2)",
            "medium breakdance": "mk bakkai (drink 2)",
            "heavy breakdance": "hk bakkai (drink 2)",
            "236k": "lk bakkai (drink 2)",
            "236lk": "lk bakkai (drink 2)",
            "236mk": "mk bakkai (drink 2)",
            "236hk": "hk bakkai (drink 2)",
            "236kk": "od bakkai (drink 2)",
            "breakin": "breakin'",
            "break in": "breakin'",
            "dive kick": "luminous dive kick (drink 1)",
            "divekick": "luminous dive kick (drink 1)",
            "l dive kick": "luminous dive kick (drink 1)",
            "m dive kick": "luminous dive kick (drink 1)",
            "h dive kick": "luminous dive kick (drink 1)",
            "light dive kick": "luminous dive kick (drink 1)",
            "medium dive kick": "luminous dive kick (drink 1)",
            "heavy dive kick": "luminous dive kick (drink 1)",
            "od dive kick": "od luminous dive kick (drink 1)",
            "ex dive kick": "od luminous dive kick (drink 1)",
            "l divekick": "luminous dive kick (drink 1)",
            "m divekick": "luminous dive kick (drink 1)",
            "h divekick": "luminous dive kick (drink 1)",
            "light divekick": "luminous dive kick (drink 1)",
            "medium divekick": "luminous dive kick (drink 1)",
            "heavy divekick": "luminous dive kick (drink 1)",
            "od divekick": "od luminous dive kick (drink 1)",
            "ex divekick": "od luminous dive kick (drink 1)",
            "luminous dive kick": "luminous dive kick (drink 1)",
            "od luminous dive kick": "od luminous dive kick (drink 1)",
            "ex luminous dive kick": "od luminous dive kick (drink 1)",
            "214k": "luminous dive kick (drink 1)",
            "214k air": "luminous dive kick (drink 1)",
            "214kk": "od luminous dive kick (drink 1)",
            "214kk air": "od luminous dive kick (drink 1)",
            "j214k": "luminous dive kick (drink 1)",
            "j.214k": "luminous dive kick (drink 1)",
            "j 214k": "luminous dive kick (drink 1)",
            "j214kk": "od luminous dive kick (drink 1)",
            "j.214kk": "od luminous dive kick (drink 1)",
            "j 214kk": "od luminous dive kick (drink 1)",
            "tenshin": "tenshin (drink 3)",
            "command grab": "tenshin (drink 3)",
            "od tenshin": "od tenshin (drink 3)",
            "ex tenshin": "od tenshin (drink 3)",
            "od command grab": "od tenshin (drink 3)",
            "ex command grab": "od tenshin (drink 3)",
            "swagger hermit punch": "lp swagger hermit punch (drink 4)",
            "hermit punch": "lp swagger hermit punch (drink 4)",
            "lp swagger hermit punch": "lp swagger hermit punch (drink 4)",
            "mp swagger hermit punch": "mp swagger hermit punch (drink 4)",
            "hp swagger hermit punch": "hp swagger hermit punch (drink 4)",
            "od swagger hermit punch": "od swagger hermit punch (drink 4)",
            "ex swagger hermit punch": "od swagger hermit punch (drink 4)",
            "lp hermit punch": "lp swagger hermit punch (drink 4)",
            "mp hermit punch": "mp swagger hermit punch (drink 4)",
            "hp hermit punch": "hp swagger hermit punch (drink 4)",
            "od hermit punch": "od swagger hermit punch (drink 4)",
            "ex hermit punch": "od swagger hermit punch (drink 4)",
            "palm followup": "lp swagger hermit punch (drink 4)",
            "palm follow-up": "lp swagger hermit punch (drink 4)",
        },
        "ryu": {
            "air tatsu": "air tatsumaki senpukyaku",
            "aerial tatsu": "air tatsumaki senpukyaku",
            "air tatsumaki": "air tatsumaki senpukyaku",
            "aerial tatsumaki": "air tatsumaki senpukyaku",
            "l air tatsu": "air tatsumaki senpukyaku",
            "m air tatsu": "air tatsumaki senpukyaku",
            "h air tatsu": "air tatsumaki senpukyaku",
            "light air tatsu": "air tatsumaki senpukyaku",
            "medium air tatsu": "air tatsumaki senpukyaku",
            "heavy air tatsu": "air tatsumaki senpukyaku",
            "od air tatsu": "od air tatsumaki senpukyaku",
            "ex air tatsu": "od air tatsumaki senpukyaku",
            "214k air": "air tatsumaki senpukyaku",
            "214kk air": "od air tatsumaki senpukyaku",
            "j214k": "air tatsumaki senpukyaku",
            "j.214k": "air tatsumaki senpukyaku",
            "j 214k": "air tatsumaki senpukyaku",
            "j214kk": "od air tatsumaki senpukyaku",
            "j.214kk": "od air tatsumaki senpukyaku",
            "j 214kk": "od air tatsumaki senpukyaku",
        },
        "ken": {
            "run": "quick dash",
            "quick run": "quick dash",
            "dash run": "quick dash",
            "5kk": "quick dash",
            "air tatsu": "air tatsumaki senpukyaku",
            "aerial tatsu": "air tatsumaki senpukyaku",
            "air tatsumaki": "air tatsumaki senpukyaku",
            "aerial tatsumaki": "air tatsumaki senpukyaku",
            "l air tatsu": "air tatsumaki senpukyaku",
            "m air tatsu": "air tatsumaki senpukyaku",
            "h air tatsu": "air tatsumaki senpukyaku",
            "light air tatsu": "air tatsumaki senpukyaku",
            "medium air tatsu": "air tatsumaki senpukyaku",
            "heavy air tatsu": "air tatsumaki senpukyaku",
            "od air tatsu": "od air tatsumaki senpukyaku",
            "ex air tatsu": "od air tatsumaki senpukyaku",
            "214k air": "air tatsumaki senpukyaku",
            "214kk air": "od air tatsumaki senpukyaku",
            "j214k": "air tatsumaki senpukyaku",
            "j.214k": "air tatsumaki senpukyaku",
            "j 214k": "air tatsumaki senpukyaku",
            "j214kk": "od air tatsumaki senpukyaku",
            "j.214kk": "od air tatsumaki senpukyaku",
            "j 214kk": "od air tatsumaki senpukyaku",
            "lash": "dragonlash kick",
            "dragonlash": "dragonlash kick",
            "dragon lash": "dragonlash kick",
            "od dragonlash": "od dragonlash kick",
            "ex dragonlash": "od dragonlash kick",
            "od dragon lash": "od dragonlash kick",
            "ex dragon lash": "od dragonlash kick",
            "l lash": "lk dragonlash kick",
            "m lash": "mk dragonlash kick",
            "h lash": "hk dragonlash kick",
            "light lash": "lk dragonlash kick",
            "medium lash": "mk dragonlash kick",
            "heavy lash": "hk dragonlash kick",
            "od lash": "od dragonlash kick",
            "ex lash": "od dragonlash kick",
            "run stop": "emergency stop",
            "run overhead": "thunder kick",
            "run step": "forward step kick",
            "run step kick": "forward step kick",
            "run dp": "run > shoryuken",
            "run shoryu": "run > shoryuken",
            "run shoryuken": "run > shoryuken",
            "run tatsu": "run > tatsumaki senpukyaku",
            "run dragonlash": "run > dragonlash",
            "run dragon lash": "run > dragonlash",
            "run lash": "run > dragonlash",
            "jinrai low": "jinrai > low",
            "jinrai lk": "jinrai > low",
            "jinrai 6lk": "jinrai > low",
            "jinrai overhead": "jinrai > overhead",
            "jinrai mk": "jinrai > overhead",
            "jinrai 6mk": "jinrai > overhead",
            "jinrai launcher": "jinrai > heavy",
            "jinrai heavy": "jinrai > heavy",
            "jinrai hk": "jinrai > heavy",
            "jinrai 6hk": "jinrai > heavy",
            "jinrai followup low": "jinrai > low",
            "jinrai followup overhead": "jinrai > overhead",
            "jinrai followup launcher": "jinrai > heavy",
            "jinrai heavy followup": "jinrai > heavy",
            "jinrai hk followup": "jinrai > heavy",
            "236k low": "jinrai > low",
            "236k lk": "jinrai > low",
            "236k 6lk": "jinrai > low",
            "236k overhead": "jinrai > overhead",
            "236k mk": "jinrai > overhead",
            "236k 6mk": "jinrai > overhead",
            "236k launcher": "jinrai > heavy",
            "236k heavy": "jinrai > heavy",
            "236k hk": "jinrai > heavy",
            "236k 6hk": "jinrai > heavy",
            "od jinrai low": "od jinrai > low",
            "od jinrai lk": "od jinrai > low",
            "od jinrai overhead": "od jinrai > overhead",
            "od jinrai mk": "od jinrai > overhead",
            "od jinrai launcher": "od jinrai > heavy",
            "od jinrai hk": "od jinrai > heavy",
            "ex jinrai low": "od jinrai > low",
            "ex jinrai overhead": "od jinrai > overhead",
            "ex jinrai launcher": "od jinrai > heavy",
            "ex jinrai hk": "od jinrai > heavy",
        },
        "luke": {
            "214p": "flash knuckle",
            "214 p": "flash knuckle",
            "214lp": "lp flash knuckle",
            "214 lp": "lp flash knuckle",
            "214mp": "mp flash knuckle",
            "214 mp": "mp flash knuckle",
            "214hp": "hp flash knuckle",
            "214 hp": "hp flash knuckle",
            "214pp": "od flash knuckle",
            "214 pp": "od flash knuckle",
            "flash knuckle": "flash knuckle",
            "knuckle": "flash knuckle",
            "l knuckle": "lp flash knuckle",
            "m knuckle": "mp flash knuckle",
            "h knuckle": "hp flash knuckle",
            "light knuckle": "lp flash knuckle",
            "medium knuckle": "mp flash knuckle",
            "heavy knuckle": "hp flash knuckle",
            "od knuckle": "od flash knuckle",
            "ex knuckle": "od flash knuckle",
            "charged knuckle": "lp flash knuckle (hold)",
            "hold knuckle": "lp flash knuckle (hold)",
            "held knuckle": "lp flash knuckle (hold)",
            "charged light knuckle": "lp flash knuckle (hold)",
            "light charged knuckle": "lp flash knuckle (hold)",
            "charged medium knuckle": "mp flash knuckle (hold)",
            "medium charged knuckle": "mp flash knuckle (hold)",
            "charged heavy knuckle": "hp flash knuckle (hold)",
            "heavy charged knuckle": "hp flash knuckle (hold)",
            "charged flash knuckle": "lp flash knuckle (hold)",
            "hold flash knuckle": "lp flash knuckle (hold)",
            "held flash knuckle": "lp flash knuckle (hold)",
        },
        "juri": {
            "dive kick": "shiku-sen",
            "divekick": "shiku-sen",
            "l dive kick": "shiku-sen",
            "m dive kick": "shiku-sen",
            "h dive kick": "shiku-sen",
            "light dive kick": "shiku-sen",
            "medium dive kick": "shiku-sen",
            "heavy dive kick": "shiku-sen",
            "od dive kick": "od shiku-sen",
            "ex dive kick": "od shiku-sen",
            "l divekick": "shiku-sen",
            "m divekick": "shiku-sen",
            "h divekick": "shiku-sen",
            "light divekick": "shiku-sen",
            "medium divekick": "shiku-sen",
            "heavy divekick": "shiku-sen",
            "od divekick": "od shiku-sen",
            "ex divekick": "od shiku-sen",
            "j214k": "shiku-sen",
            "j.214k": "shiku-sen",
            "j 214k": "shiku-sen",
            "j214kk": "od shiku-sen",
            "j.214kk": "od shiku-sen",
            "j 214kk": "od shiku-sen",
            "214k air": "shiku-sen",
            "214kk air": "od shiku-sen",
            "stocked fireball": "saihasho (stock)",
            "stock fireball": "saihasho (stock)",
            "stocked saihasho": "saihasho (stock)",
            "stock saihasho": "saihasho (stock)",
            "stocked fuha release": "saihasho (stock)",
            "stocked axe kick": "ankensatsu (stock)",
            "stock axe kick": "ankensatsu (stock)",
            "stocked ankensatsu": "ankensatsu (stock)",
            "stock ankensatsu": "ankensatsu (stock)",
            "stocked spinning kicks": "go ohsatsu (stock)",
            "stock spinning kicks": "go ohsatsu (stock)",
            "stocked go ohsatsu": "go ohsatsu (stock)",
            "stock go ohsatsu": "go ohsatsu (stock)",
            "stocked sa1": "sakkai fuhazan (1 stock)",
            "stock sa1": "sakkai fuhazan (1 stock)",
        },
        "akuma": {
            "demon flip": "demon raid",
            "od demon flip": "od demon raid",
            "ex demon flip": "od demon raid",
            "teleport": "ashura senku (forward)",
            "forward teleport": "ashura senku (forward)",
            "fwd teleport": "ashura senku (forward)",
            "back teleport": "ashura senku (backward)",
            "backward teleport": "ashura senku (backward)",
            "teleport back": "ashura senku (backward)",
            "teleport backward": "ashura senku (backward)",
            "tele back": "ashura senku (backward)",
            "ashura senku": "ashura senku (forward)",
            "ashura": "ashura senku (forward)",
            "raging demon": "shun goku satsu",
            "air sa1": "tenma gozanku",
            "aerial sa1": "tenma gozanku",
            "sa1 air": "tenma gozanku",
            "sa 1 air": "tenma gozanku",
            "air super art 1": "tenma gozanku",
            "aerial super art 1": "tenma gozanku",
            "air super 1": "tenma gozanku",
            "aerial super 1": "tenma gozanku",
            "air level 1": "tenma gozanku",
            "aerial level 1": "tenma gozanku",
            "tenma": "tenma gozanku",
            "tenma gozanku": "tenma gozanku",
            "air fireball": "zanku hadoken",
            "aerial fireball": "zanku hadoken",
            "air hadoken": "zanku hadoken",
            "air zanku": "zanku hadoken",
            "zanku": "zanku hadoken",
            "l zanku": "zanku hadoken",
            "m zanku": "zanku hadoken",
            "h zanku": "zanku hadoken",
            "l zanku hadoken": "zanku hadoken",
            "m zanku hadoken": "zanku hadoken",
            "h zanku hadoken": "zanku hadoken",
            "light zanku": "zanku hadoken",
            "medium zanku": "zanku hadoken",
            "heavy zanku": "zanku hadoken",
            "light zanku hadoken": "zanku hadoken",
            "medium zanku hadoken": "zanku hadoken",
            "heavy zanku hadoken": "zanku hadoken",
            "l air fireball": "zanku hadoken",
            "m air fireball": "zanku hadoken",
            "h air fireball": "zanku hadoken",
            "light air fireball": "zanku hadoken",
            "medium air fireball": "zanku hadoken",
            "heavy air fireball": "zanku hadoken",
            "od air fireball": "od zanku hadoken",
            "ex air fireball": "od zanku hadoken",
            "od air hadoken": "od zanku hadoken",
            "ex air hadoken": "od zanku hadoken",
            "od zanku": "od zanku hadoken",
            "ex zanku": "od zanku hadoken",
            "od zanku hadoken": "od zanku hadoken",
            "ex zanku hadoken": "od zanku hadoken",
            "214p": "adamant flame",
            "214 p": "adamant flame",
            "214lp": "lp adamant flame",
            "214 lp": "lp adamant flame",
            "214mp": "mp adamant flame",
            "214 mp": "mp adamant flame",
            "214hp": "hp adamant flame",
            "214 hp": "hp adamant flame",
            "214pp": "od adamant flame",
            "214 pp": "od adamant flame",
            "adamant flame": "adamant flame",
            "flaming fist": "adamant flame",
            "flame": "adamant flame",
            "l flame": "lp adamant flame",
            "m flame": "mp adamant flame",
            "h flame": "hp adamant flame",
            "light flame": "lp adamant flame",
            "medium flame": "mp adamant flame",
            "heavy flame": "hp adamant flame",
            "od flame": "od adamant flame",
            "ex flame": "od adamant flame",
            "l adamant flame": "lp adamant flame",
            "m adamant flame": "mp adamant flame",
            "h adamant flame": "hp adamant flame",
            "light adamant flame": "lp adamant flame",
            "medium adamant flame": "mp adamant flame",
            "heavy adamant flame": "hp adamant flame",
            "od adamant flame": "od adamant flame",
            "ex adamant flame": "od adamant flame",
            "demon raid": "demon raid",
            "od demon raid": "od demon raid",
            "ex demon raid": "od demon raid",
            "demon low slash": "demon low slash",
            "demon low": "demon low slash",
            "demon slide": "demon low slash",
            "od demon low slash": "od demon raid > demon low slash",
            "ex demon low slash": "od demon raid > demon low slash",
            "od demon low": "od demon raid > demon low slash",
            "ex demon low": "od demon raid > demon low slash",
            "od demon slide": "od demon raid > demon low slash",
            "ex demon slide": "od demon raid > demon low slash",
            "demon guillotine": "demon guillotine",
            "demon chop": "demon guillotine",
            "chop": "demon guillotine",
            "demon overhead": "demon guillotine",
            "od demon guillotine": "od demon raid > demon guillotine",
            "ex demon guillotine": "od demon raid > demon guillotine",
            "od chop": "od demon raid > demon guillotine",
            "ex chop": "od demon raid > demon guillotine",
            "demon blade kick": "demon blade kick",
            "demon flip dive kick": "demon blade kick",
            "demon flip divekick": "demon blade kick",
            "demon dive kick": "demon blade kick",
            "demon divekick": "demon blade kick",
            "od demon blade kick": "od demon raid > demon blade kick",
            "ex demon blade kick": "od demon raid > demon blade kick",
            "od demon flip dive kick": "od demon raid > demon blade kick",
            "od demon flip divekick": "od demon raid > demon blade kick",
            "ex demon flip dive kick": "od demon raid > demon blade kick",
            "ex demon flip divekick": "od demon raid > demon blade kick",
            "demon swoop": "demon swoop",
            "demon feint": "demon swoop",
            "demon empty": "demon swoop",
            "demon stop": "demon swoop",
            "empty": "demon swoop",
            "stop": "demon swoop",
            "od demon swoop": "od demon raid > demon swoop",
            "ex demon swoop": "od demon raid > demon swoop",
            "od empty": "od demon raid > demon swoop",
            "ex empty": "od demon raid > demon swoop",
            "od stop": "od demon raid > demon swoop",
            "ex stop": "od demon raid > demon swoop",
            "demon gou zanku": "od demon gou zanku",
            "gou zanku": "od demon gou zanku",
            "demon gou rasen": "od demon gou rasen",
            "gou rasen": "od demon gou rasen",
            "od demon gou zanku": "od demon raid > od demon gou zanku",
            "ex demon gou zanku": "od demon raid > od demon gou zanku",
            "od demon gou rasen": "od demon raid > od demon gou rasen",
            "ex demon gou rasen": "od demon raid > od demon gou rasen",
            "dive kick": "tenmaku blade kick",
            "divekick": "tenmaku blade kick",
            "l dive kick": "tenmaku blade kick",
            "m dive kick": "tenmaku blade kick",
            "h dive kick": "tenmaku blade kick",
            "light dive kick": "tenmaku blade kick",
            "medium dive kick": "tenmaku blade kick",
            "heavy dive kick": "tenmaku blade kick",
            "l divekick": "tenmaku blade kick",
            "m divekick": "tenmaku blade kick",
            "h divekick": "tenmaku blade kick",
            "light divekick": "tenmaku blade kick",
            "medium divekick": "tenmaku blade kick",
            "heavy divekick": "tenmaku blade kick",
            "air tatsu": "aerial tatsumaki zanku-kyaku",
            "aerial tatsu": "aerial tatsumaki zanku-kyaku",
            "air tatsumaki": "aerial tatsumaki zanku-kyaku",
            "aerial tatsumaki": "aerial tatsumaki zanku-kyaku",
            "l air tatsu": "aerial tatsumaki zanku-kyaku",
            "m air tatsu": "aerial tatsumaki zanku-kyaku",
            "h air tatsu": "aerial tatsumaki zanku-kyaku",
            "light air tatsu": "aerial tatsumaki zanku-kyaku",
            "medium air tatsu": "aerial tatsumaki zanku-kyaku",
            "heavy air tatsu": "aerial tatsumaki zanku-kyaku",
            "od air tatsu": "od aerial tatsumaki zanku-kyaku",
            "ex air tatsu": "od aerial tatsumaki zanku-kyaku",
            "214k air": "aerial tatsumaki zanku-kyaku",
            "214kk air": "od aerial tatsumaki zanku-kyaku",
            "j214k": "aerial tatsumaki zanku-kyaku",
            "j.214k": "aerial tatsumaki zanku-kyaku",
            "j 214k": "aerial tatsumaki zanku-kyaku",
            "j214kk": "od aerial tatsumaki zanku-kyaku",
            "j.214kk": "od aerial tatsumaki zanku-kyaku",
            "j 214kk": "od aerial tatsumaki zanku-kyaku",
        },
        "guile": {
            "46p": "sonic boom",
            "46lp": "lp sonic boom",
            "46mp": "mp sonic boom",
            "46hp": "hp sonic boom",
            "46pp": "od sonic boom",
            "sonic boom": "sonic boom",
            "boom": "sonic boom",
            "fireball": "sonic boom",
            "lp boom": "lp sonic boom",
            "mp boom": "mp sonic boom",
            "hp boom": "hp sonic boom",
            "od boom": "od sonic boom",
            "ex boom": "od sonic boom",
            "light boom": "lp sonic boom",
            "medium boom": "mp sonic boom",
            "heavy boom": "hp sonic boom",
            "l boom": "lp sonic boom",
            "m boom": "mp sonic boom",
            "h boom": "hp sonic boom",
        },
        "e.honda": {
            "46p": "sumo headbutt",
            "46lp": "lp sumo headbutt",
            "46mp": "mp sumo headbutt",
            "46hp": "hp sumo headbutt",
            "46pp": "od sumo headbutt",
            "sumo headbutt": "sumo headbutt",
            "headbutt": "sumo headbutt",
            "lp headbutt": "lp sumo headbutt",
            "mp headbutt": "mp sumo headbutt",
            "hp headbutt": "hp sumo headbutt",
            "od headbutt": "od sumo headbutt",
            "ex headbutt": "od sumo headbutt",
            "light headbutt": "lp sumo headbutt",
            "medium headbutt": "mp sumo headbutt",
            "heavy headbutt": "hp sumo headbutt",
            "l headbutt": "lp sumo headbutt",
            "m headbutt": "mp sumo headbutt",
            "h headbutt": "hp sumo headbutt",
            # 28K Sumo Smash
            "28k": "sumo smash",
            "28lk": "lk sumo smash",
            "28mk": "mk sumo smash",
            "28hk": "hk sumo smash",
            "28kk": "od sumo smash",
            "sumo smash": "sumo smash",
            "ass slam": "sumo smash",
            "butt slam": "sumo smash",
            "lk sumo smash": "lk sumo smash",
            "mk sumo smash": "mk sumo smash",
            "hk sumo smash": "hk sumo smash",
            "od sumo smash": "od sumo smash",
            "light ass slam": "lk sumo smash",
            "medium ass slam": "mk sumo smash",
            "heavy ass slam": "hk sumo smash",
            # 22P Neko Damashi
            "22p": "neko damashi",
            "22 p": "neko damashi",
            "22lp": "neko damashi",
            "22 lp": "neko damashi",
            "22mp": "neko damashi",
            "22 mp": "neko damashi",
            "22hp": "neko damashi",
            "22 hp": "neko damashi",
            "22pp": "neko damashi",
            "22 pp": "neko damashi",
            "neko damashi": "neko damashi",
            "clap": "neko damashi",
            "claps": "neko damashi",
            "l clap": "neko damashi",
            "m clap": "neko damashi",
            "h clap": "neko damashi",
            "light clap": "neko damashi",
            "medium clap": "neko damashi",
            "heavy clap": "neko damashi",
            # Oicho Throw
            "oicho": "oicho throw",
            "oicho throw": "oicho throw",
            "command grab": "oicho throw",
            "l oicho": "lk oicho throw",
            "m oicho": "mk oicho throw",
            "h oicho": "hk oicho throw",
            "light oicho": "lk oicho throw",
            "medium oicho": "mk oicho throw",
            "heavy oicho": "hk oicho throw",
            "od oicho": "od oicho throw",
            "ex oicho": "od oicho throw",
            "l oicho throw": "lk oicho throw",
            "m oicho throw": "mk oicho throw",
            "h oicho throw": "hk oicho throw",
            "light oicho throw": "lk oicho throw",
            "medium oicho throw": "mk oicho throw",
            "heavy oicho throw": "hk oicho throw",
            "od oicho throw": "od oicho throw",
            "ex oicho throw": "od oicho throw",
        },
        "m.bison": {
            "46p": "psycho crusher",
            "46lp": "lp psycho crusher",
            "46mp": "mp psycho crusher",
            "46hp": "hp psycho crusher",
            "46pp": "od psycho crusher",
            "psycho crusher": "psycho crusher",
            "bison crusher": "psycho crusher",
            "crusher": "psycho crusher",
            "lp crusher": "lp psycho crusher",
            "mp crusher": "mp psycho crusher",
            "hp crusher": "hp psycho crusher",
            "od crusher": "od psycho crusher",
            "ex crusher": "od psycho crusher",
            "light crusher": "lp psycho crusher",
            "medium crusher": "mp psycho crusher",
            "heavy crusher": "hp psycho crusher",
            "l crusher": "lp psycho crusher",
            "m crusher": "mp psycho crusher",
            "h crusher": "hp psycho crusher",
            # 28K Shadow Rise
            "28k": "shadow rise",
            "28kk": "od shadow rise",
            "shadow rise": "shadow rise",
            "command jump": "shadow rise",
            "fly": "shadow rise",
            "od shadow rise": "od shadow rise",
        },
        "blanka": {
            # 46P Rolling Attack
            "46p": "rolling attack",
            "46lp": "lp rolling attack",
            "46mp": "mp rolling attack",
            "46hp": "hp rolling attack",
            "46pp": "od rolling attack",
            "rolling attack": "rolling attack",
            "blanka ball": "rolling attack",
            "ball": "rolling attack",
            "lp ball": "lp rolling attack",
            "mp ball": "mp rolling attack",
            "hp ball": "hp rolling attack",
            "od ball": "od rolling attack",
            "ex ball": "od rolling attack",
            "light ball": "lp rolling attack",
            "medium ball": "mp rolling attack",
            "heavy ball": "hp rolling attack",
            "l ball": "lp rolling attack",
            "m ball": "mp rolling attack",
            "h ball": "hp rolling attack",
            # 28K Vertical Rolling Attack
            "28k": "vertical rolling attack",
            "28lk": "lk vertical rolling attack",
            "28mk": "mk vertical rolling attack",
            "28hk": "hk vertical rolling attack",
            "28kk": "od vertical rolling attack",
            "vertical rolling attack": "vertical rolling attack",
            "upball": "vertical rolling attack",
            "up ball": "vertical rolling attack",
            "lk upball": "lk vertical rolling attack",
            "mk upball": "mk vertical rolling attack",
            "hk upball": "hk vertical rolling attack",
            "od upball": "od vertical rolling attack",
            "light upball": "lk vertical rolling attack",
            "medium upball": "mk vertical rolling attack",
            "heavy upball": "hk vertical rolling attack",
            "aerial ball": "Aerial Rolling Attack (air)"
        },
        "guile": {
            # 214P Sonic Blade
            "214p": "sonic blade",
            "214 p": "sonic blade",
            "214lp": "lp sonic blade",
            "214 lp": "lp sonic blade",
            "214mp": "mp sonic blade",
            "214 mp": "mp sonic blade",
            "214hp": "hp sonic blade",
            "214 hp": "hp sonic blade",
            "214pp": "od sonic blade",
            "214 pp": "od sonic blade",
            "sonic blade": "sonic blade",
            "blade": "sonic blade",
            "lp blade": "lp sonic blade",
            "mp blade": "mp sonic blade",
            "hp blade": "hp sonic blade",
            "od blade": "od sonic blade",
            "ex blade": "od sonic blade",
            "light blade": "lp sonic blade",
            "medium blade": "mp sonic blade",
            "heavy blade": "hp sonic blade",
            "l blade": "lp sonic blade",
            "m blade": "mp sonic blade",
            "h blade": "hp sonic blade",
            # 46P Sonic Boom
            "46p": "sonic boom",
            "46lp": "lp sonic boom",
            "46mp": "mp sonic boom",
            "46hp": "hp sonic boom",
            "46pp": "od sonic boom",
            "sonic boom": "sonic boom",
            "boom": "sonic boom",
            "fireball": "sonic boom",
            "lp boom": "lp sonic boom",
            "mp boom": "mp sonic boom",
            "hp boom": "hp sonic boom",
            "od boom": "od sonic boom",
            "ex boom": "od sonic boom",
            "light boom": "lp sonic boom",
            "medium boom": "mp sonic boom",
            "heavy boom": "hp sonic boom",
            "l boom": "lp sonic boom",
            "m boom": "mp sonic boom",
            "h boom": "hp sonic boom",
            # 28K Somersault Kick (Flash Kick)
            "28k": "somersault kick",
            "28lk": "lk somersault kick",
            "28mk": "mk somersault kick",
            "28hk": "hk somersault kick",
            "28kk": "od somersault kick",
            "somersault kick": "somersault kick",
            "flash kick": "somersault kick",
            "lk flash kick": "lk somersault kick",
            "mk flash kick": "mk somersault kick",
            "hk flash kick": "hk somersault kick",
            "od flash kick": "od somersault kick",
            "ex flash kick": "od somersault kick",
            "light flash kick": "lk somersault kick",
            "medium flash kick": "mk somersault kick",
            "heavy flash kick": "hk somersault kick",
            "l flash kick": "lk somersault kick",
            "m flash kick": "mk somersault kick",
            "h flash kick": "hk somersault kick",
        },
        "chun-li": {
            "4mp": "4 or 6mp",
            "6mp": "4 or 6mp",
            "f+mp": "4 or 6mp",
            "b+mp": "4 or 6mp",
            "fmp": "4 or 6mp",
            "bmp": "4 or 6mp",
            # 28K Spinning Bird Kick
            "28k": "spinning bird kick",
            "28lk": "lk spinning bird kick",
            "28mk": "mk spinning bird kick",
            "28hk": "hk spinning bird kick",
            "28kk": "od spinning bird kick",
            "spinning bird kick": "spinning bird kick",
            "sbk": "spinning bird kick",
            "lk sbk": "lk spinning bird kick",
            "mk sbk": "mk spinning bird kick",
            "hk sbk": "hk spinning bird kick",
            "od sbk": "od spinning bird kick",
            "ex sbk": "od spinning bird kick",
            "light sbk": "lk spinning bird kick",
            "medium sbk": "mk spinning bird kick",
            "heavy sbk": "hk spinning bird kick",
            # 22K Tenshokyaku (upkicks)
            "tensho": "upkicks",
            "tensho kick": "upkicks",
            "tensho kicks": "upkicks",
            "tenshokyaku": "upkicks",
            "lk tensho": "lk tenshokyaku",
            "mk tensho": "mk tenshokyaku",
            "hk tensho": "hk tenshokyaku",
            "l tensho": "lk tenshokyaku",
            "m tensho": "mk tenshokyaku",
            "h tensho": "hk tenshokyaku",
            "light tensho": "lk tenshokyaku",
            "medium tensho": "mk tenshokyaku",
            "heavy tensho": "hk tenshokyaku",
            "od tensho": "od tenshokyaku",
            "ex tensho": "od tenshokyaku",
            # 236K (Air) Air Legs
            "air legs": "236k (air)",
            "airlegs": "236k (air)",
            "aerial legs": "236k (air)",
            "air lightning legs": "236k (air)",
            "air hyakuretsukyaku": "236k (air)",
            "hyakuretsukyaku air": "236k (air)",
            "236k air": "236k (air)",
            "236k(air)": "236k (air)",
            "236 k air": "236k (air)",
            "l air legs": "236lk (air)",
            "m air legs": "236mk (air)",
            "h air legs": "236hk (air)",
            "light air legs": "236lk (air)",
            "medium air legs": "236mk (air)",
            "heavy air legs": "236hk (air)",
            "od air legs": "236kk (air)",
            "ex air legs": "236kk (air)",
            "236lk air": "236lk (air)",
            "236 lk air": "236lk (air)",
            "236mk air": "236mk (air)",
            "236 mk air": "236mk (air)",
            "236hk air": "236hk (air)",
            "236 hk air": "236hk (air)",
            "236kk air": "236kk (air)",
            "236 kk air": "236kk (air)",
        },
        "cammy": {
            # Hooligan > Throw (command grab)
            "command grab": "hooligan > throw",
            "hooligan throw": "hooligan > throw",
            "hooligan > throw": "hooligan > throw",
            "reverse edge": "hooligan combination > reverse edge",
            "od reverse edge": "od hooligan combination > reverse edge",
            "silent step": "hooligan combination > silent step",
            "od silent step": "od hooligan combination > silent step",
            "cannon strike": "hooligan combination > cannon strike",
            "od cannon strike": "od hooligan combination > cannon strike",
            "fatal leg twister": "hooligan combination > throw",
            "od fatal leg twister": "od hooligan > throw",
            "hooligan combination reverse edge": "hooligan combination > reverse edge",
            "od hooligan combination reverse edge": "od hooligan combination > reverse edge",
            "hooligan combination silent step": "hooligan combination > silent step",
            "od hooligan combination silent step": "od hooligan combination > silent step",
            "hooligan combination cannon strike": "hooligan combination > cannon strike",
            "od hooligan combination cannon strike": "od hooligan combination > cannon strike",
            "hooligan combination fatal leg twister": "hooligan > throw",
            "od hooligan combination fatal leg twister": "od hooligan > throw",
            "ex command grab": "od hooligan > throw",
            "od command grab": "od hooligan > throw",
            "ex hooligan throw": "od hooligan > throw",
            "od hooligan throw": "od hooligan > throw",
            "h command grab": "hp hooligan (hold) > throw",
            "hp command grab": "hp hooligan (hold) > throw",
            "hooligan hold throw": "hp hooligan (hold) > throw",
        },
        "dhalsim": {
            "fireball": "yoga fire",
            "yoga fire": "yoga fire",
            "236p": "yoga fire",
            "236 p": "yoga fire",
            "236lp": "yoga fire",
            "236 lp": "yoga fire",
            "236mp": "yoga fire",
            "236 mp": "yoga fire",
            "236hp": "yoga fire",
            "236 hp": "yoga fire",
            "l yoga fire": "yoga fire",
            "m yoga fire": "yoga fire",
            "h yoga fire": "yoga fire",
            "light yoga fire": "yoga fire",
            "medium yoga fire": "yoga fire",
            "heavy yoga fire": "yoga fire",
            "od yoga fire": "od yoga fire",
            "ex yoga fire": "od yoga fire",
            "236pp": "od yoga fire",
            "236 pp": "od yoga fire",
            "arch": "yoga arch",
            "yoga arch": "yoga arch",
            "236k": "yoga arch",
            "236 k": "yoga arch",
            "236lk": "yoga arch",
            "236 lk": "yoga arch",
            "236mk": "yoga arch",
            "236 mk": "yoga arch",
            "236hk": "yoga arch",
            "236 hk": "yoga arch",
            "l arch": "yoga arch",
            "m arch": "yoga arch",
            "h arch": "yoga arch",
            "light arch": "yoga arch",
            "medium arch": "yoga arch",
            "heavy arch": "yoga arch",
            "l yoga arch": "yoga arch",
            "m yoga arch": "yoga arch",
            "h yoga arch": "yoga arch",
            "light yoga arch": "yoga arch",
            "medium yoga arch": "yoga arch",
            "heavy yoga arch": "yoga arch",
            "od yoga arch": "od yoga arch",
            "ex yoga arch": "od yoga arch",
            "236kk": "od yoga arch",
            "236 kk": "od yoga arch",
            "comet": "yoga comet (air)",
            "commet": "yoga comet (air)",
            "yoga comet": "yoga comet (air)",
            "yoga commet": "yoga comet (air)",
            "air comet": "yoga comet (air)",
            "air commet": "yoga comet (air)",
            "air yoga comet": "yoga comet (air)",
            "air yoga commet": "yoga comet (air)",
            "63214p": "yoga comet (air)",
            "63214 p": "yoga comet (air)",
            "63214lp": "yoga comet (air)",
            "63214 lp": "yoga comet (air)",
            "63214mp": "yoga comet (air)",
            "63214 mp": "yoga comet (air)",
            "63214hp": "yoga comet (air)",
            "63214 hp": "yoga comet (air)",
            "l yoga comet": "yoga comet (air)",
            "m yoga comet": "yoga comet (air)",
            "h yoga comet": "yoga comet (air)",
            "l yoga commet": "yoga comet (air)",
            "m yoga commet": "yoga comet (air)",
            "h yoga commet": "yoga comet (air)",
            "light yoga comet": "yoga comet (air)",
            "medium yoga comet": "yoga comet (air)",
            "heavy yoga comet": "yoga comet (air)",
            "light yoga commet": "yoga comet (air)",
            "medium yoga commet": "yoga comet (air)",
            "heavy yoga commet": "yoga comet (air)",
            "od yoga comet": "od yoga comet (air)",
            "ex yoga comet": "od yoga comet (air)",
            "od yoga commet": "od yoga comet (air)",
            "ex yoga commet": "od yoga comet (air)",
            "63214pp": "od yoga comet (air)",
            "63214 pp": "od yoga comet (air)",
        },
        "zangief": {
            # Neutral jump HP -> Flying Headbutt
            "8hp": "flying headbutt",
            "8 hp": "flying headbutt",
            "njhp": "flying headbutt",
            "nj.hp": "flying headbutt",
            "n jhp": "flying headbutt",
            "n j.hp": "flying headbutt",
            "neutral jhp": "flying headbutt",
            "neutral j.hp": "flying headbutt",
            "neutral jump hp": "flying headbutt",
            "neutral jump heavy punch": "flying headbutt",
            "flying headbutt": "flying headbutt",
            "air headbutt": "flying headbutt",
            "borscht": "borscht dynamite",
            "od borscht": "od borscht dynamite",
            "ex borscht": "od borscht dynamite",
            "borscht dynamite": "borscht dynamite",
            "od borscht dynamite": "od borscht dynamite",
            "ex borscht dynamite": "od borscht dynamite",
            "j360k": "borscht dynamite",
            "j.360k": "borscht dynamite",
            "j 360k": "borscht dynamite",
            "j360kk": "od borscht dynamite",
            "j.360kk": "od borscht dynamite",
            "j 360kk": "od borscht dynamite",
            "j360+k": "borscht dynamite",
            "j.360+k": "borscht dynamite",
            "j 360+k": "borscht dynamite",
            "j360+kk": "od borscht dynamite",
            "j.360+kk": "od borscht dynamite",
            "j 360+kk": "od borscht dynamite",
            "720p": "bolshoi storm buster",
            "720 p": "bolshoi storm buster",
            "720+p": "bolshoi storm buster",
            "720pp": "bolshoi storm buster",
            "720 pp": "bolshoi storm buster",
            "storm buster": "bolshoi storm buster",
            "sa3": "bolshoi storm buster",
        },
        "jp": {
            "236p": "stribog",
            "236 p": "stribog",
            "236lp": "lp stribog",
            "236 lp": "lp stribog",
            "236mp": "mp stribog",
            "236 mp": "mp stribog",
            "236hp": "hp stribog",
            "236 hp": "hp stribog",
            "236pp": "od stribog",
            "236 pp": "od stribog",
            "swipe": "stribog",
            "l swipe": "lp stribog",
            "m swipe": "mp stribog",
            "h swipe": "hp stribog",
            "light swipe": "lp stribog",
            "medium swipe": "mp stribog",
            "heavy swipe": "hp stribog",
            "od swipe": "od stribog",
            "ex swipe": "od stribog",
            "stribog": "stribog",
            "l stribog": "lp stribog",
            "m stribog": "mp stribog",
            "h stribog": "hp stribog",
            "light stribog": "lp stribog",
            "medium stribog": "mp stribog",
            "heavy stribog": "hp stribog",
            "od stribog": "od stribog",
            "ex stribog": "od stribog",
            "22p": "triglav",
            "22 p": "triglav",
            "22lp": "triglav",
            "22 lp": "triglav",
            "22mp": "triglav",
            "22 mp": "triglav",
            "22hp": "triglav",
            "22 hp": "triglav",
            "22pp": "od triglav",
            "22 pp": "od triglav",
            "22k": "amnesia",
            "22 k": "amnesia",
            "22kk": "od amnesia",
            "22 kk": "od amnesia",
            "ground spike": "triglav",
            "od ground spike": "od triglav",
            "spike": "triglav",
            "od spike": "od triglav",
            "l spike": "triglav",
            "m spike": "triglav",
            "h spike": "triglav",
            "light spike": "triglav",
            "medium spike": "triglav",
            "heavy spike": "triglav",
            "pierce": "triglav",
            "od pierce": "od triglav",
            "l pierce": "triglav",
            "m pierce": "triglav",
            "h pierce": "triglav",
            "light pierce": "triglav",
            "medium pierce": "triglav",
            "heavy pierce": "triglav",
            "counter": "amnesia",
            "od counter": "od amnesia",
            "amnesia bomb": "amnesia: bomb",
            "od amnesia bomb": "od amnesia: bomb",
            "22k bomb": "amnesia: bomb",
            "22kk bomb": "od amnesia: bomb",
        },
        "lily": {
            "windclad spire": "lk condor spire (enhanced)",
            "wind clad spire": "lk condor spire (enhanced)",
            "stocked spire": "lk condor spire (enhanced)",
            "stocked condor spire": "lk condor spire (enhanced)",
            "l windclad spire": "lk condor spire (enhanced)",
            "m windclad spire": "mk condor spire (enhanced)",
            "h windclad spire": "hk condor spire (enhanced)",
            "light windclad spire": "lk condor spire (enhanced)",
            "medium windclad spire": "mk condor spire (enhanced)",
            "heavy windclad spire": "hk condor spire (enhanced)",
            "od windclad spire": "od condor spire (enhanced)",
            "ex windclad spire": "od condor spire (enhanced)",
            "stocked tomahawk": "lp tomahawk buster (enhanced)",
            "windclad tomahawk": "lp tomahawk buster (enhanced)",
            "wind clad tomahawk": "lp tomahawk buster (enhanced)",
            "l stocked tomahawk": "lp tomahawk buster (enhanced)",
            "m stocked tomahawk": "mp tomahawk buster (enhanced)",
            "h stocked tomahawk": "hp tomahawk buster (enhanced)",
            "od stocked tomahawk": "od tomahawk buster (enhanced)",
            "stocked condor wind": "lp condor wind (2 stocks)",
            "wind stock": "lp condor wind (2 stocks)",
        },
        "mai": {
            "fan": "fireball",
            "fire fan": "fireball",
            "kachousen": "fireball",
            "l fan": "lp fireball",
            "m fan": "mp fireball",
            "h fan": "hp fireball",
            "light fan": "lp fireball",
            "medium fan": "mp fireball",
            "heavy fan": "hp fireball",
            "od fan": "od fireball",
            "ex fan": "od fireball",
            "hold fan": "hold fireball",
            "held fan": "hold fireball",
            "charged fan": "hold fireball",
            "od hold fan": "od hold fireball",
            "ex hold fan": "od hold fireball",
            "stocked fan": "stocked fireball",
            "stock fan": "stocked fireball",
            "stocked kachousen": "stocked fireball",
            "stocked hold fan": "stocked hold fireball",
            "stocked held fan": "stocked hold fireball",
            "stocked charged fan": "stocked hold fireball",
            "od stocked fan": "od stocked fireball",
            "ex stocked fan": "od stocked fireball",
            "stocked od fan": "od stocked fireball",
            "stocked ex fan": "od stocked fireball",
            "od stocked hold fan": "od stocked hold fireball",
            "ex stocked hold fan": "od stocked hold fireball",
            "stocked od hold fan": "od stocked hold fireball",
            "stocked ex hold fan": "od stocked hold fireball",
            "stocked fireball": "lp kachousen (stock)",
            "stocked kachousen": "lp kachousen (stock)",
            "hold fireball": "kachousen (hold)",
            "held fireball": "kachousen (hold)",
            "charged fireball": "kachousen (hold)",
            "air sa2": "air chou hissatsu shinobi bachi",
            "aerial sa2": "air chou hissatsu shinobi bachi",
            "sa2 air": "air chou hissatsu shinobi bachi",
            "sa 2 air": "air chou hissatsu shinobi bachi",
            "air super art 2": "air chou hissatsu shinobi bachi",
            "aerial super art 2": "air chou hissatsu shinobi bachi",
            "air super 2": "air chou hissatsu shinobi bachi",
            "aerial super 2": "air chou hissatsu shinobi bachi",
            "air level 2": "air chou hissatsu shinobi bachi",
            "aerial level 2": "air chou hissatsu shinobi bachi",
            "stocked hold fireball": "kachousen (stock + hold)",
            "stocked held fireball": "kachousen (stock + hold)",
            "stocked charged fireball": "kachousen (stock + hold)",
            "od stocked fireball": "od kachousen (stock)",
            "ex stocked fireball": "od kachousen (stock)",
            "od hold fireball": "od kachousen (hold)",
            "ex hold fireball": "od kachousen (hold)",
            "od stocked hold fireball": "od kachousen (stock + hold)",
            "ex stocked hold fireball": "od kachousen (stock + hold)",
            "l stocked fireball": "lp kachousen (stock)",
            "m stocked fireball": "mp kachousen (stock)",
            "h stocked fireball": "hp kachousen (stock)",
            "od stocked fireball": "od kachousen (stock)",
            "stocked dp": "lk hishou ryuuenjin (stock)",
            "stocked ryuuenjin": "lk hishou ryuuenjin (stock)",
            "od stocked dp": "od hishou ryuuenjin (stock)",
            "ex stocked dp": "od hishou ryuuenjin (stock)",
            "stocked od dp": "od hishou ryuuenjin (stock)",
            "stocked ex dp": "od hishou ryuuenjin (stock)",
            "stocked twirl": "lp ryuuenbu (stock)",
            "stocked ryuuenbu": "lp ryuuenbu (stock)",
            "od stocked twirl": "od ryuuenbu (stock)",
            "ex stocked twirl": "od ryuuenbu (stock)",
            "stocked od twirl": "od ryuuenbu (stock)",
            "stocked ex twirl": "od ryuuenbu (stock)",
            "stocked cartwheel": "lk hissatsu shinobi bachi (stock)",
            "stocked shinobi bachi": "lk hissatsu shinobi bachi (stock)",
            "od stocked cartwheel": "od hissatsu shinobi bachi (stock)",
            "ex stocked cartwheel": "od hissatsu shinobi bachi (stock)",
            "stocked od cartwheel": "od hissatsu shinobi bachi (stock)",
            "stocked ex cartwheel": "od hissatsu shinobi bachi (stock)",
            "stocked dive kick": "musasabi no mai (stock)",
            "stocked divekick": "musasabi no mai (stock)",
            "stocked musasabi": "musasabi no mai (stock)",
            "stocked musasabi no mai": "musasabi no mai (stock)",
            "od stocked dive kick": "od musasabi no mai (stock)",
            "ex stocked dive kick": "od musasabi no mai (stock)",
            "stocked od dive kick": "od musasabi no mai (stock)",
            "stocked ex dive kick": "od musasabi no mai (stock)",
            "od stocked divekick": "od musasabi no mai (stock)",
            "ex stocked divekick": "od musasabi no mai (stock)",
            "od stocked musasabi": "od musasabi no mai (stock)",
            "ex stocked musasabi": "od musasabi no mai (stock)",
            "stocked sa1": "kagerou no mai (stock)",
            "stocked sa2": "chou hissatsu shinobi bachi (stock)",
            "stocked air sa2": "air chou hissatsu shinobi bachi (stock)",
            "air stocked sa2": "air chou hissatsu shinobi bachi (stock)",
        },
        "a.k.i": {
            "236p": "serpent lash",
            "236 p": "serpent lash",
            "236lp": "lp serpent lash",
            "236 lp": "lp serpent lash",
            "236mp": "mp serpent lash",
            "236 mp": "mp serpent lash",
            "236hp": "hp serpent lash",
            "236 hp": "hp serpent lash",
            "236pp": "od serpent lash",
            "236 pp": "od serpent lash",
            "whip": "serpent lash",
            "l whip": "lp serpent lash",
            "m whip": "mp serpent lash",
            "h whip": "hp serpent lash",
            "light whip": "lp serpent lash",
            "medium whip": "mp serpent lash",
            "heavy whip": "hp serpent lash",
            "od whip": "od serpent lash",
            "ex whip": "od serpent lash",
            "serpent lash": "serpent lash",
            "l serpent lash": "lp serpent lash",
            "m serpent lash": "mp serpent lash",
            "h serpent lash": "hp serpent lash",
            "light serpent lash": "lp serpent lash",
            "medium serpent lash": "mp serpent lash",
            "heavy serpent lash": "hp serpent lash",
            "od serpent lash": "od serpent lash",
            "ex serpent lash": "od serpent lash",
        },
        "c.viper": {
            "236k": "burning kick",
            "236 k": "burning kick",
            "236lk": "lk burning kick",
            "236 lk": "lk burning kick",
            "236mk": "mk burning kick",
            "236 mk": "mk burning kick",
            "236hk": "hk burning kick",
            "236 hk": "hk burning kick",
            "236kk": "od burning kick",
            "236 kk": "od burning kick",
            "burn kick": "burning kick",
            "burnkick": "burning kick",
            "burn kicks": "burning kick",
            "burnkicks": "burning kick",
            "burning kick": "burning kick",
            "burning kicks": "burning kick",
            "l burn kick": "lk burning kick",
            "m burn kick": "mk burning kick",
            "h burn kick": "hk burning kick",
            "l burnkick": "lk burning kick",
            "m burnkick": "mk burning kick",
            "h burnkick": "hk burning kick",
            "light burn kick": "lk burning kick",
            "medium burn kick": "mk burning kick",
            "heavy burn kick": "hk burning kick",
            "light burnkick": "lk burning kick",
            "medium burnkick": "mk burning kick",
            "heavy burnkick": "hk burning kick",
            "od burn kick": "od burning kick",
            "ex burn kick": "od burning kick",
            "od burnkick": "od burning kick",
            "ex burnkick": "od burning kick",
            "air burn kick": "burning kick (air)",
            "air burnkick": "burning kick (air)",
            "air burn kicks": "burning kick (air)",
            "air burnkicks": "burning kick (air)",
            "air burning kick": "burning kick (air)",
            "air burning kicks": "burning kick (air)",
            "aerial burn kick": "burning kick (air)",
            "aerial burnkick": "burning kick (air)",
            "aerial burning kick": "burning kick (air)",
            "burn kick air": "burning kick (air)",
            "burnkick air": "burning kick (air)",
            "236k air": "burning kick (air)",
            "236 k air": "burning kick (air)",
            "236lk air": "236lk (air)",
            "236 lk air": "236lk (air)",
            "236mk air": "236mk (air)",
            "236 mk air": "236mk (air)",
            "236hk air": "236hk (air)",
            "236 hk air": "236hk (air)",
            "236kk air": "236kk (air)",
            "236 kk air": "236kk (air)",
            "j236k": "burning kick (air)",
            "j.236k": "burning kick (air)",
            "j 236k": "burning kick (air)",
            "j236kk": "236kk (air)",
            "j.236kk": "236kk (air)",
            "j 236kk": "236kk (air)",
            "l air burn kick": "lk burning kick (air)",
            "m air burn kick": "mk burning kick (air)",
            "h air burn kick": "hk burning kick (air)",
            "l air burnkick": "lk burning kick (air)",
            "m air burnkick": "mk burning kick (air)",
            "h air burnkick": "hk burning kick (air)",
            "light air burn kick": "lk burning kick (air)",
            "medium air burn kick": "mk burning kick (air)",
            "heavy air burn kick": "hk burning kick (air)",
            "light air burnkick": "lk burning kick (air)",
            "medium air burnkick": "mk burning kick (air)",
            "heavy air burnkick": "hk burning kick (air)",
            "od air burn kick": "od burning kick (air)",
            "ex air burn kick": "od burning kick (air)",
            "od air burnkick": "od burning kick (air)",
            "ex air burnkick": "od burning kick (air)",
        },
    }

    COMMAND_JUMP_NORMAL_ALIASES = {
        "a.k.i": {
            "j2hp": "gong fu",
            "j.2hp": "gong fu",
            "jump 2hp": "gong fu",
        },
        "akuma": {
            "j2mk": "tenmaku blade kick",
            "j.2mk": "tenmaku blade kick",
            "jump 2mk": "tenmaku blade kick",
        },
        "chun-li": {
            "j2mk": "yoso kick",
            "j.2mk": "yoso kick",
            "jump 2mk": "yoso kick",
        },
        "dee jay": {
            "j2lk": "knee shot",
            "j.2lk": "knee shot",
            "jump 2lk": "knee shot",
        },
        "dhalsim": {
            "j2lp": "yoga mummy",
            "j.2lp": "yoga mummy",
            "jump 2lp": "yoga mummy",
            "j2k": "lk drill kick",
            "j.2k": "lk drill kick",
            "jump 2k": "lk drill kick",
            "j2lk": "lk drill kick",
            "j2mk": "mk drill kick",
            "j2hk": "hk drill kick",
        },
        "alex": {
            "stance": "prowler stance",
            "stance jab": "palm jab",
            "stance lp": "palm jab",
            "stance shoulder": "shoulder launcher",
            "stance mp": "shoulder launcher",
            "stance lariat": "heavy lariat",
            "stance hp": "heavy lariat",
            "stance hop": "tactical hop",
            "stance lk": "tactical hop",
            "stance stomp": "air stampede",
            "stance mk": "air stampede",
            "stance hk": "sweep combination 1",
            "stance hk hk": "sweep combination 2",
            "stance throw": "hyper takedown",
            "stance lplk": "hyper takedown",
            "stance 5lplk": "hyper takedown",
            "stance command grab": "dangerous armbar",
            "stance 2lplk": "dangerous armbar",
            "stance 6p": "slashing elbow",
            "2pp 6p": "slashing elbow",
            "stance 6": "low rush",
            "2pp 6": "low rush",
            "stance 4": "low retreat",
            "2pp 4": "low retreat",
            "2pp lp": "palm jab",
            "2pp 5lp": "palm jab",
            "2pp mp": "shoulder launcher",
            "2pp 5mp": "shoulder launcher",
            "2pp hp": "heavy lariat",
            "2pp 5hp": "heavy lariat",
            "2pp lk": "tactical hop",
            "2pp 5lk": "tactical hop",
            "2pp mk": "air stampede",
            "2pp 5mk": "air stampede",
            "2pp hk": "sweep combination 1",
            "2pp 5hk": "sweep combination 1",
            "2pp hk hk": "sweep combination 2",
            "2pp 5hk 5hk": "sweep combination 2",
            "2pp lplk": "hyper takedown",
            "2pp 5lplk": "hyper takedown",
            "2pp 2lplk": "dangerous armbar",
            "hold hp": "stand hp (hold)",
            "held hp": "stand hp (hold)",
            "charged hp": "stand hp (hold)",
            "hold hk": "stand hk (hold)",
            "held hk": "stand hk (hold)",
            "charged hk": "stand hk (hold)",
        },
        "e.honda": {
            "j2mk": "flying sumo press",
            "j.2mk": "flying sumo press",
            "jump 2mk": "flying sumo press",
        },
        "lily": {
            "j2hp": "great spin",
            "j.2hp": "great spin",
            "jump 2hp": "great spin",
        },
        "rashid": {
            "j2hp": "blitz strike",
            "j.2hp": "blitz strike",
            "jump 2hp": "blitz strike",
        },
        "zangief": {
            "j2hp": "flying body press",
            "j.2hp": "flying body press",
            "jump 2hp": "flying body press",
        },
        "kimberly": {
            "j2mp": "elbow drop",
            "j.2mp": "elbow drop",
            "jump 2mp": "elbow drop",
            "j2mp elbow": "elbow drop",
            "j2mp(elbow)": "elbow drop",
        },
    }
    for alias_char, alias_map in COMMAND_JUMP_NORMAL_ALIASES.items():
        if alias_char not in CHARACTER_INPUT_ALIASES:
            CHARACTER_INPUT_ALIASES[alias_char] = {}
        CHARACTER_INPUT_ALIASES[alias_char].update(alias_map)

    DP_PREFIX_EXCEPTIONS = {
        "marisa": ["phalanx"],
        "ken": ["dragonlash"],
        "viper": ["seismo"],
        "c.viper": ["seismo"],
    }
    
    char_aliases = CHARACTER_INPUT_ALIASES.get(char_key, {})
    alias_lookup_candidates = []
    for candidate in (pre_strength_alias_input, move_input):
        candidate = str(candidate or "").strip().lower()
        if candidate and candidate not in alias_lookup_candidates:
            alias_lookup_candidates.append(candidate)

    def resolve_input_alias_chain(raw_value):
        current = str(raw_value or "").strip().lower()
        seen_alias_values = set()
        while current and current not in seen_alias_values:
            seen_alias_values.add(current)
            next_value = None
            if current in char_aliases:
                next_value = str(char_aliases[current]).strip().lower()
            elif current in INPUT_ALIASES:
                next_value = str(INPUT_ALIASES[current]).strip().lower()
            if not next_value or next_value == current:
                break
            current = next_value
        return current

    for candidate in alias_lookup_candidates:
        resolved_candidate = resolve_input_alias_chain(candidate)
        if resolved_candidate != candidate or candidate in char_aliases or candidate in INPUT_ALIASES:
            move_input = resolved_candidate
            break

    def resolve_fuzzy_alias_target(raw_input):
        raw_compact = re.sub(r"[^a-z0-9]", "", str(raw_input or "").lower())
        if len(raw_compact) < 4:
            return None

        alias_compact_to_target = {}
        for alias_key, alias_target in char_aliases.items():
            alias_compact = re.sub(r"[^a-z0-9]", "", str(alias_key or "").lower())
            if len(alias_compact) < 4:
                continue
            if alias_compact not in alias_compact_to_target:
                alias_compact_to_target[alias_compact] = str(alias_target)

        for alias_key, alias_target in INPUT_ALIASES.items():
            alias_compact = re.sub(r"[^a-z0-9]", "", str(alias_key or "").lower())
            if len(alias_compact) < 4:
                continue
            if alias_compact not in alias_compact_to_target:
                alias_compact_to_target[alias_compact] = str(alias_target)

        if not alias_compact_to_target:
            return None

        close_matches = difflib.get_close_matches(
            raw_compact,
            list(alias_compact_to_target.keys()),
            n=1,
            cutoff=0.82,
        )
        if not close_matches:
            return None
        return alias_compact_to_target.get(close_matches[0])

    def row_is_ca_variant(row):
        move_name = str(row.get("moveName", "")).lower()
        cmn_name = str(row.get("cmnName", "")).lower()
        num_cmd = str(row.get("numCmd", "")).lower()
        return (
            "critical art" in move_name
            or "critical art" in cmn_name
            or bool(re.search(r"\(\s*ca\s*\)", num_cmd))
        )

    def row_is_charged_variant(row):
        move_name = str(row.get("moveName", "")).lower()
        cmn_name = str(row.get("cmnName", "")).lower()
        num_cmd = str(row.get("numCmd", "")).lower()
        return (
            "charged" in move_name
            or "charged" in cmn_name
            or "hold" in move_name
            or "hold" in cmn_name
            or "(charged" in num_cmd
            or "(hold" in num_cmd
        )

    def row_is_stocked_variant(row):
        move_name = str(row.get("moveName", "")).lower()
        cmn_name = str(row.get("cmnName", "")).lower()
        num_cmd = str(row.get("numCmd", "")).lower()
        combined = f"{move_name} {cmn_name} {num_cmd}"
        if re.search(r"\b0\s*stocks?\b", combined):
            return False

        has_stock_count = bool(re.search(r"\b[1-9]\d*\s*stocks?\b", combined))
        has_stock_tag = "(stock" in move_name or "(stock" in cmn_name or "(stock" in num_cmd
        has_enhanced_tag = (
            "enhanced" in move_name
            or "enhanced" in cmn_name
            or "(enhanced" in num_cmd
        )
        has_windclad_tag = "windclad" in move_name or "windclad" in cmn_name
        has_wind_stock_hold = "wind stock" in cmn_name and (
            "(" in cmn_name or "(hold" in num_cmd
        )
        return (
            has_stock_count
            or has_stock_tag
            or has_enhanced_tag
            or has_windclad_tag
            or has_wind_stock_hold
        )

    def genericize_lookup_button_suffix(num_cmd_token):
        token = str(num_cmd_token or "")
        token = re.sub(r"(lp|mp|hp)$", "p", token)
        token = re.sub(r"(lk|mk|hk)$", "k", token)
        token = re.sub(r"pp$", "p", token)
        token = re.sub(r"kk$", "k", token)
        return token

    def build_strengthless_lookup_variants(raw_input):
        variants = []
        normalized = str(raw_input or "").lower().strip()
        if not normalized:
            return variants

        collapsed_numcmd = re.sub(r"(\d+)(lp|mp|hp)\b", r"\1p", normalized)
        collapsed_numcmd = re.sub(r"(\d+)(lk|mk|hk)\b", r"\1k", collapsed_numcmd)
        collapsed_numcmd = re.sub(r"(\d+)(pp)\b", r"\1p", collapsed_numcmd)
        collapsed_numcmd = re.sub(r"(\d+)(kk)\b", r"\1k", collapsed_numcmd)
        collapsed_numcmd = re.sub(r"\s+", " ", collapsed_numcmd).strip()
        if collapsed_numcmd and collapsed_numcmd != normalized:
            variants.append(collapsed_numcmd)

        stripped_strength = re.sub(
            r"\b(?:lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b",
            " ",
            normalized,
        )
        stripped_strength = re.sub(r"\s+", " ", stripped_strength).strip()
        if stripped_strength and stripped_strength != normalized and stripped_strength not in variants:
            variants.append(stripped_strength)

        stripped_after_collapse = re.sub(
            r"\b(?:lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b",
            " ",
            collapsed_numcmd,
        )
        stripped_after_collapse = re.sub(r"\s+", " ", stripped_after_collapse).strip()
        if (
            stripped_after_collapse
            and stripped_after_collapse != normalized
            and stripped_after_collapse not in variants
        ):
            variants.append(stripped_after_collapse)

        return variants
    move_input_compact = re.sub(r"[^a-z0-9]", "", move_input)
    move_input_num_cmd = normalize_num_cmd_for_lookup(move_input)
    move_input_num_cmd_generic = normalize_num_cmd_generic_for_lookup(move_input)
    move_input_has_numcmd_qualifier = bool(
        re.search(r"\b(air|hold|held|bomb|charged)\b", move_input)
        or any(ch in move_input for ch in "()[]{}")
    )

    if char_key == "akuma":
        if move_input in {"air sa1", "aerial sa1", "sa1 air", "air super art 1"}:
            move_input = "tenma gozanku"
        if move_input in {"air sa3", "aerial sa3", "sa3 air", "air super art 3"}:
            move_input = "sip of calamity"

    move_input_tigerless = move_input
    move_input_tigerless_compact = move_input_compact
    if char_key == "sagat":
        move_input_tigerless = re.sub(r"\btiger\b", "", move_input)
        move_input_tigerless = re.sub(r"\s+", " ", move_input_tigerless).strip()
        move_input_tigerless_compact = re.sub(r"[^a-z0-9]", "", move_input_tigerless)

    if char_key == "akuma" and move_input_num_cmd_generic == "236236k":
        akuma_super_rows = []
        for row in data:
            row_token = normalize_num_cmd_generic_for_lookup(row.get("numCmd", ""))
            if row_token == "236236k":
                akuma_super_rows.append(row)
        if akuma_super_rows:
            ca_rows = [row for row in akuma_super_rows if row_is_ca_variant(row)]
            air_rows = [
                row
                for row in akuma_super_rows
                if "air" in str(row.get("moveName", "")).lower()
                or "air" in str(row.get("cmnName", "")).lower()
                or "(air)" in str(row.get("numCmd", "")).lower()
                or "tenma" in str(row.get("moveName", "")).lower()
            ]
            non_air_non_ca_rows = [
                row
                for row in akuma_super_rows
                if row not in air_rows and row not in ca_rows
            ]

            if query_requests_ca and ca_rows:
                return ca_rows[0]
            if query_requests_air_context or query_requests_sa1:
                if air_rows:
                    return air_rows[0]
            if query_requests_sa3 and non_air_non_ca_rows:
                return non_air_non_ca_rows[0]
            if non_air_non_ca_rows:
                return non_air_non_ca_rows[0]
    
    # search priority: numCmd -> plnCmd -> moveName
    for row in data:
        num_cmd = str(row.get('numCmd', '')).lower()
        num_cmd_normalized = normalize_num_cmd_for_lookup(num_cmd)
        num_cmd_generic = normalize_num_cmd_generic_for_lookup(num_cmd)
        if combo_input and ">" in num_cmd:
            if re.sub(r"\s+", "", num_cmd) == combo_input:
                return row
        # exact match numCmd (5MP)
        if num_cmd == move_input:
            return row
        # strict normalized numCmd match (preserves annotation words)
        if move_input_num_cmd and num_cmd_normalized == move_input_num_cmd:
            return row
        # generic normalized numCmd match (drops annotation words, for convenience)
        if (
            not move_input_has_numcmd_qualifier
            and move_input_num_cmd_generic
            and num_cmd_generic == move_input_num_cmd_generic
        ):
            return row
        # prefix match for motion inputs (e.g., 623 -> 623LP)
        if move_input.isdigit() and len(move_input) == 3:
            if move_input == "623":
                exception_terms = DP_PREFIX_EXCEPTIONS.get(char_key, [])
                if exception_terms:
                    move_name = str(row.get("moveName", "")).lower()
                    if any(term in move_name for term in exception_terms):
                        continue
            if num_cmd.startswith(move_input) or num_cmd_generic.startswith(move_input):
                return row
        # exact match plnCmd (MP)
        if str(row.get('plnCmd', '')).lower() == move_input:
            return row
        # exact/contains match cmnName
        cmn_name = str(row.get('cmnName', '')).lower()
        if cmn_name == move_input or (len(move_input_compact) >= 3 and cmn_name and move_input in cmn_name):
            return row
        # fuzzy match moveName ("Stand MP")
        move_name = str(row.get('moveName', '')).lower()
        cmn_name_tigerless = cmn_name
        move_name_tigerless = move_name
        if len(move_input_compact) >= 3 and move_input in move_name:
            return row
        if char_key == "sagat" and move_input_tigerless:
            cmn_name_tigerless = re.sub(r"\btiger\b", "", cmn_name)
            cmn_name_tigerless = re.sub(r"\s+", " ", cmn_name_tigerless).strip()
            move_name_tigerless = re.sub(r"\btiger\b", "", move_name)
            move_name_tigerless = re.sub(r"\s+", " ", move_name_tigerless).strip()
            if cmn_name_tigerless == move_input_tigerless or (
                len(move_input_tigerless_compact) >= 3
                and cmn_name_tigerless
                and move_input_tigerless in cmn_name_tigerless
            ):
                return row
            if (
                len(move_input_tigerless_compact) >= 3
                and move_input_tigerless in move_name_tigerless
            ):
                return row
        if len(move_input_compact) >= 6:
            cmn_compact = re.sub(r"[^a-z0-9]", "", cmn_name)
            move_name_compact = re.sub(r"[^a-z0-9]", "", move_name)
            if (
                (cmn_compact and move_input_compact in cmn_compact)
                or move_input_compact in move_name_compact
            ):
                return row
            if char_key == "sagat" and len(move_input_tigerless_compact) >= 6:
                cmn_tigerless_compact = re.sub(r"[^a-z0-9]", "", cmn_name_tigerless)
                move_tigerless_compact = re.sub(r"[^a-z0-9]", "", move_name_tigerless)
                if (
                    (cmn_tigerless_compact and move_input_tigerless_compact in cmn_tigerless_compact)
                    or move_input_tigerless_compact in move_tigerless_compact
                ):
                    return row

    if query_requests_charged:
        base_chargeless_input = re.sub(
            r"\b(?:charged|hold|held)\b",
            " ",
            move_input,
        )
        base_chargeless_input = re.sub(r"\s+", " ", base_chargeless_input).strip()
        if base_chargeless_input and base_chargeless_input != move_input:
            base_row = lookup_frame_data(character, base_chargeless_input, _seen_inputs=_seen_inputs)
            if base_row:
                base_token = normalize_num_cmd_token(base_row.get("numCmd", ""))
                base_suffix = extract_button_suffix(base_token)
                charged_candidates = []
                for row in data:
                    if not row_is_charged_variant(row):
                        continue
                    row_token = normalize_num_cmd_token(row.get("numCmd", ""))
                    if row_token != base_token:
                        continue
                    charged_candidates.append(row)
                if charged_candidates:
                    if base_suffix:
                        for row in charged_candidates:
                            row_suffix = extract_button_suffix(normalize_num_cmd_token(row.get("numCmd", "")))
                            if row_suffix == base_suffix:
                                return row
                    return charged_candidates[0]

                base_generic_token = genericize_lookup_button_suffix(base_token)
                generic_channel = ""
                if base_suffix in {"lp", "mp", "hp", "pp", "p"}:
                    generic_channel = "p"
                elif base_suffix in {"lk", "mk", "hk", "kk", "k"}:
                    generic_channel = "k"

                generic_charged_candidates = []
                for row in data:
                    if not row_is_charged_variant(row):
                        continue
                    row_token = normalize_num_cmd_token(row.get("numCmd", ""))
                    if genericize_lookup_button_suffix(row_token) != base_generic_token:
                        continue
                    generic_charged_candidates.append(row)
                if generic_charged_candidates:
                    if generic_channel:
                        for row in generic_charged_candidates:
                            row_suffix = extract_button_suffix(normalize_num_cmd_token(row.get("numCmd", "")))
                            if row_suffix == generic_channel:
                                return row
                    return generic_charged_candidates[0]

    for strengthless_input in build_strengthless_lookup_variants(move_input):
        strengthless_row = lookup_frame_data(character, strengthless_input, _seen_inputs=_seen_inputs)
        if strengthless_row is not None:
            return strengthless_row

    if query_requests_stocked:
        base_stockless_input = re.sub(
            r"\b(?:stocked|stock|enhanced|windclad|wind\s+clad)\b",
            " ",
            move_input,
        )
        base_stockless_input = re.sub(r"\s+", " ", base_stockless_input).strip()
        if base_stockless_input and base_stockless_input != move_input:
            base_row = lookup_frame_data(character, base_stockless_input, _seen_inputs=_seen_inputs)
            if base_row:
                base_token = normalize_num_cmd_token(base_row.get("numCmd", ""))
                base_suffix = extract_button_suffix(base_token)
                stocked_candidates = []
                for row in data:
                    if not row_is_stocked_variant(row):
                        continue
                    row_token = normalize_num_cmd_token(row.get("numCmd", ""))
                    if row_token != base_token:
                        continue
                    stocked_candidates.append(row)
                if stocked_candidates:
                    if base_suffix:
                        for row in stocked_candidates:
                            row_suffix = extract_button_suffix(normalize_num_cmd_token(row.get("numCmd", "")))
                            if row_suffix == base_suffix:
                                return row
                    return stocked_candidates[0]

    if len(move_input_compact) >= 4:
        fuzzy_candidates = []
        for row in data:
            move_name = str(row.get("moveName", "")).lower()
            cmn_name = str(row.get("cmnName", "")).lower()
            for candidate in (move_name, cmn_name):
                candidate_compact = re.sub(r"[^a-z0-9]", "", candidate)
                if len(candidate_compact) >= 4:
                    fuzzy_candidates.append((candidate_compact, row))

        if fuzzy_candidates:
            choices = [candidate for candidate, _ in fuzzy_candidates]
            close = difflib.get_close_matches(move_input_compact, choices, n=1, cutoff=0.86)
            if close:
                matched = close[0]
                for candidate, row in fuzzy_candidates:
                    if candidate == matched:
                        return row

    fuzzy_alias_target = resolve_fuzzy_alias_target(move_input)
    if fuzzy_alias_target and fuzzy_alias_target != move_input:
        fuzzy_alias_row = lookup_frame_data(character, fuzzy_alias_target, _seen_inputs=_seen_inputs)
        if fuzzy_alias_row is not None:
            return fuzzy_alias_row

    return None


def compact_move_token(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def normalize_num_cmd_token(value):
    normalized = re.sub(r"\([^)]*\)", "", str(value or "").lower())
    normalized = re.sub(r"\s+", "", normalized)
    return re.sub(r"[^a-z0-9>]", "", normalized)


def extract_button_suffix(num_cmd_token):
    token = str(num_cmd_token or "")
    match = re.search(r"(lp|mp|hp|lk|mk|hk|pp|kk|p|k)$", token)
    return match.group(1) if match else ""


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
    normalized_tokens = []
    for token in raw_tokens:
        mapped = token_map.get(token, token)
        if mapped in drop_tokens:
            continue
        normalized_tokens.append(mapped)
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


def build_num_cmd_candidates_for_gif(row):
    row_num_cmd_raw = str(row.get("numCmd", "")).lower()
    row_num_cmd = normalize_num_cmd_token(row_num_cmd_raw)
    candidates = set()
    if row_num_cmd:
        candidates.add(row_num_cmd)
        if ">" in row_num_cmd:
            parts = [part for part in row_num_cmd.split(">") if part]
            candidates.update(parts)
            if parts:
                candidates.add(parts[-1])

    row_suffix = extract_button_suffix(row_num_cmd)
    move_name_lower = str(row.get("moveName", "")).lower()
    cmn_name_lower = str(row.get("cmnName", "")).lower()

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
        compact_air_cmd = re.sub(r"[^a-z0-9]", "", row_num_cmd_raw)
        if compact_air_cmd.startswith("2") or compact_air_cmd.startswith("1or2or3"):
            candidates.add(f"92{row_suffix}")

    if row_suffix in {"p", "k"} and ">" not in row_num_cmd:
        prefix = row_num_cmd[:-1]
        if prefix:
            if row_suffix == "p":
                candidates.update({f"{prefix}lp", f"{prefix}mp", f"{prefix}hp"})
            else:
                candidates.update({f"{prefix}lk", f"{prefix}mk", f"{prefix}hk"})

    return candidates


def lookup_hitbox_gif_link(row):
    row_char = str(row.get("char_name", "")).strip()
    char_key = resolve_character_key(row_char)
    if not char_key:
        return None

    gif_rows = HITBOX_GIF_DATA.get(char_key, [])
    if not gif_rows:
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

    num_cmd_candidate_matches = [
        item for item in gif_candidates
        if item["num_cmd"] and item["num_cmd"] in num_cmd_candidates
    ]
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


def collect_hitbox_gif_links(rows, limit=3):
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


def find_characters_in_text(text):
    text_lower = strip_discord_mentions(text).lower()
    tokens = re.findall(r"[a-z0-9]+", text_lower)

    def has_token_sequence(sequence):
        if not sequence:
            return False
        seq_len = len(sequence)
        for idx in range(len(tokens) - seq_len + 1):
            if tokens[idx:idx + seq_len] == sequence:
                return True
        return False

    found = []
    alias_items = sorted(
        CHARACTER_ALIASES.items(),
        key=lambda item: len(re.findall(r"[a-z0-9]+", item[0])),
        reverse=True,
    )
    for alias, canonical in alias_items:
        if canonical not in FRAME_DATA:
            continue
        alias_tokens = re.findall(r"[a-z0-9]+", alias.lower())
        if has_token_sequence(alias_tokens) and canonical not in found:
            found.append(canonical)

    for char_key in FRAME_DATA.keys():
        char_tokens = re.findall(r"[a-z0-9]+", str(char_key).lower())
        if has_token_sequence(char_tokens) and char_key not in found:
            found.append(char_key)

    return found


def remove_first_token_sequence(tokens, sequence):
    if not sequence:
        return tokens, False
    seq_len = len(sequence)
    for idx in range(len(tokens) - seq_len + 1):
        if tokens[idx:idx + seq_len] == sequence:
            return tokens[:idx] + tokens[idx + seq_len:], True
    return tokens, False


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
        "od swagger hermit punch": "od drink level 4 freeflow strikes (2)",
        "ex swagger hermit punch": "od drink level 4 freeflow strikes (2)",
        "od hermit punch": "od drink level 4 freeflow strikes (2)",
        "ex hermit punch": "od drink level 4 freeflow strikes (2)",
    }
    return jamie_gif_aliases.get(query_raw, query_raw)


def lookup_hitbox_gif_links_from_query(char_key, move_query, limit=3):
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
            }
        )

    if not gif_candidates:
        return []

    query_suffix = extract_button_suffix(query_num_cmd)
    query_wants_air = bool({"air", "aerial"} & query_tokens)
    query_wants_jump = "jump" in query_tokens
    query_wants_denjin = bool({"denjin", "charged", "hold", "held"} & query_tokens)

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


def collect_hitbox_gif_links_from_text(text, frame_rows=None, limit=3):
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

            # Keep gif-mode behavior aligned with framedata parsing. If the
            # normalized query would trigger a special-strength prompt instead
            # of resolving to a concrete row, do not guess a gif from fuzzy
            # token overlap.
            prompt_probe = find_moves_in_text(f"{char_key} {move_query} framedata")
            prompt_probe_data = str(prompt_probe.get("data", "") or "")
            if (
                "Special Strength Options" in prompt_probe_data
                or "Target Combo Options" in prompt_probe_data
            ) and not prompt_probe.get("rows"):
                continue

            raw_move_query = move_query
            move_query = resolve_hitbox_gif_query_alias(char_key, move_query)
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
    add_query_links()

    return links

def check_punish(text_lower, results):
    """Calculate if Move B can punish Move A based on frame advantage."""
    # Only trigger on punish-related queries
    punish_keywords = ['punish', 'punishable', 'can i punish', 'is it punishable']
    if not any(kw in text_lower for kw in punish_keywords):
        return None
    
    # If only one move is identified, provide basic safety guidance
    if len(results) < 2:
        move_a = results[0] if results else None
        if not move_a:
            return None
        try:
            on_block_raw = str(move_a.get("onBlock", "0"))
            on_block_clean = on_block_raw.replace("+", "").strip()
            if not on_block_clean.lstrip("-").isdigit():
                return (
                    f"Cannot calculate punish: {move_a['moveName']} has non-numeric block advantage "
                    f"({on_block_raw})."
                )
            on_block = int(on_block_clean)
        except Exception as e:
            return f"Punish calculation error: {e}"

        move_a_name = f"{move_a.get('char_name', 'Unknown')}'s {move_a['moveName']}"
        frame_advantage = max(-on_block, 0)
        if on_block >= -3:
            return (
                f"**PUNISH CALCULATION**\n"
                f"{move_a_name} is **{on_block}** on block.\n\n"
                f"NO: This is **safe on block**. Moves that are -3 or better cannot be "
                f"punished by normal attacks."
            )
        return (
            f"**PUNISH CALCULATION**\n"
            f"{move_a_name} is **{on_block}** on block.\n\n"
            f"This is punishable **if** your move's startup is **≤{frame_advantage}f** and you're in range."
        )
    
    # Assume first move = blocked move (Move A), second = punish attempt (Move B)
    move_a = results[0]
    move_b = results[1]
    
    try:
        # Extract on_block from Move A (e.g. "-8")
        on_block_raw = str(move_a.get('onBlock', '0'))
        # Handle edge cases like "KD", "+5", "-8"
        on_block_clean = on_block_raw.replace('+', '').strip()
        if on_block_clean.lstrip('-').isdigit():
            on_block = int(on_block_clean)
        else:
            # Non-numeric (e.g. "KD") - can't calculate
            return f"Cannot calculate punish: {move_a['moveName']} has non-numeric block advantage ({on_block_raw})."
        
        # Extract startup from Move B (e.g. "5")
        startup_raw = str(move_b.get('startup', '0'))
        # Handle multi-hit like "3+5" - use first number
        startup_clean = startup_raw.split('+')[0].split('~')[0].split('(')[0].strip()
        if startup_clean.isdigit():
            startup = int(startup_clean)
        else:
            return f"Cannot calculate punish: {move_b['moveName']} has non-numeric startup ({startup_raw})."
        
        move_a_name = f"{move_a.get('char_name', 'Unknown')}'s {move_a['moveName']}"
        move_b_name = f"{move_b.get('char_name', 'Unknown')}'s {move_b['moveName']}"
        
        # Punish logic: defender frame advantage = -on_block (when negative)
        # If startup <= frame advantage, punishable (range still matters).
        frame_advantage = max(-on_block, 0)
        is_punishable = on_block <= -4 and frame_advantage >= startup
        if is_punishable:
            return (
                f"**PUNISH CALCULATION**\n"
                f"{move_a_name} is **{on_block}** on block.\n"
                f"{move_b_name} has **{startup}f startup**.\n\n"
                f"YES: This is punishable numerically speaking, "
                f"but my scrolls do not contain data on pushback so I cannot comment on range."
            )
        else:
            return (
                f"**PUNISH CALCULATION**\n"
                f"{move_a_name} is **{on_block}** on block.\n"
                f"{move_b_name} has **{startup}f startup**.\n\n"
                f"NO: {move_a_name} cannot be punished by {move_b_name}.\n"
                f"{move_b_name} startup must be **≤{frame_advantage}f** to punish, and the character must be in range."
            )
    except Exception as e:
        return f"Punish calculation error: {e}"


def get_attack_range_details(row):
    raw_value = str(row.get("atkRange", "")).strip()
    if is_missing_attack_range_value(raw_value):
        return "", False
    return raw_value, True


def format_attack_range_for_table(row):
    range_value, has_numeric_range = get_attack_range_details(row)
    if has_numeric_range:
        return range_value
    return "not on supercombo scrolls"

def format_frame_data(row):
    """Format a frame data row into readable text."""
    atk_range = format_attack_range_for_table(row)
    return (
        f"Move: {row['moveName']} ({row['numCmd']})\n"
        f"Startup: {row['startup']}f | Active: {row['active']}f | Recovery: {row['recovery']}f\n"
        f"Range: {atk_range}\n"
        f"On Hit: {row['onHit']} | On Block: {row['onBlock']}\n"
        f"Damage: {row['dmg']} | Attack Type: {row['atkLvl']}\n"
        f"Notes: {row.get('extraInfo', '')}"
    )


def format_startup_only_reply(rows):
    lines = []
    seen = set()
    for row in rows:
        key = (
            row.get("char_name", "Unknown"),
            row.get("moveName", "Unknown"),
            row.get("numCmd", "?"),
        )
        if key in seen:
            continue
        seen.add(key)
        startup_raw = str(row.get("startup", "-")).replace("*", ",").strip()
        startup = startup_raw if startup_raw else "-"
        startup_suffix = "f" if any(ch.isdigit() for ch in startup) and not startup.endswith("f") else ""
        char_name = row.get("char_name", "Unknown")
        move_name = row.get("moveName", "Unknown")
        num_cmd = row.get("numCmd", "?")
        lines.append(f"{char_name}'s {move_name} ({num_cmd}) startup is {startup}{startup_suffix}.")
    return "\n".join(lines[:4])


def format_hitconfirm_only_reply(rows):
    lines = []
    seen = set()
    for row in rows:
        key = (
            row.get("char_name", "Unknown"),
            row.get("moveName", "Unknown"),
            row.get("numCmd", "?"),
        )
        if key in seen:
            continue
        seen.add(key)
        char_name = row.get("char_name", "Unknown")
        move_name = row.get("moveName", "Unknown")
        num_cmd = row.get("numCmd", "?")
        hc_sp = str(row.get("hcWinSpCa", "-")).replace("*", ",").strip() or "-"
        hc_tc = str(row.get("hcWinTc", "-")).replace("*", ",").strip() or "-"
        hc_notes = str(row.get("hcWinNotes", "-")).replace("[", "").replace("]", "").replace('"', "").strip() or "-"
        lines.append(
            f"{char_name}'s {move_name} ({num_cmd}) hit confirm window is Sp/Su: {hc_sp}, TC: {hc_tc}. Notes: {hc_notes}"
        )
    return "\n".join(lines[:4])


def format_super_gain_only_reply(rows):
    lines = []
    seen = set()
    for row in rows:
        key = (
            row.get("char_name", "Unknown"),
            row.get("moveName", "Unknown"),
            row.get("numCmd", "?"),
        )
        if key in seen:
            continue
        seen.add(key)
        char_name = row.get("char_name", "Unknown")
        move_name = row.get("moveName", "Unknown")
        num_cmd = row.get("numCmd", "?")
        super_hit = str(row.get("SelfSoH", "-")).replace("*", ",").strip() or "-"
        super_block = str(row.get("SelfSoB", "-")).replace("*", ",").strip() or "-"
        lines.append(
            f"{char_name}'s {move_name} ({num_cmd}) super gain is Hit: {super_hit}, Block: {super_block}."
        )
    return "\n".join(lines[:4])


def format_range_only_reply(rows):
    unique_rows = []
    seen = set()
    for row in rows:
        key = (
            row.get("char_name", "Unknown"),
            row.get("moveName", "Unknown"),
            row.get("numCmd", "?"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)

    if not unique_rows:
        return ""

    if len(unique_rows) == 1:
        row = unique_rows[0]
        range_value, has_numeric_range = get_attack_range_details(row)
        if not has_numeric_range:
            return RANGE_SCROLLS_MISSING_TEXT
        char_name = row.get("char_name", "Unknown")
        move_name = row.get("moveName", "Unknown")
        num_cmd = row.get("numCmd", "?")
        return f"{char_name}'s {move_name} ({num_cmd}) range is {range_value}."

    lines = []
    for row in unique_rows[:4]:
        char_name = row.get("char_name", "Unknown")
        move_name = row.get("moveName", "Unknown")
        num_cmd = row.get("numCmd", "?")
        range_value, has_numeric_range = get_attack_range_details(row)
        if has_numeric_range:
            lines.append(f"{char_name}'s {move_name} ({num_cmd}) range is {range_value}.")
        else:
            lines.append(
                f"{char_name}'s {move_name} ({num_cmd}): {RANGE_SCROLLS_MISSING_TEXT}"
            )
    return "\n".join(lines)


def truncate_embed_value(value, limit):
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + "..."


def is_missing_embed_value(value):
    text = str(value if value is not None else "").strip().lower()
    return text in {"", "-", "--", "n/a", "na", "none", "null", "nan"}


def clean_embed_value(value, default="", strip_brackets=False):
    text = str(value if value is not None else "").replace("*", ",").strip()
    if strip_brackets:
        text = text.replace("[", "").replace("]", "").replace('"', "")
    if is_missing_embed_value(text):
        text = default
    return text


def add_embed_field(embed, name, value, inline=True):
    if is_missing_embed_value(value):
        return
    safe_name = truncate_embed_value(name, 256) or "-"
    safe_value = truncate_embed_value(value, 1024)
    if is_missing_embed_value(safe_value):
        return
    embed.add_field(name=safe_name, value=safe_value, inline=inline)


def format_hit_block_value(hit_value, block_value):
    hit = clean_embed_value(hit_value)
    block = clean_embed_value(block_value)
    parts = []
    if hit:
        parts.append(f"Hit: {hit}")
    if block:
        parts.append(f"Block: {block}")
    return " / ".join(parts)


def build_frame_embed(row):
    char_name = clean_embed_value(row.get("char_name", "Unknown"), default="Unknown")
    move_name = clean_embed_value(row.get("moveName", "Unknown"), default="Unknown")
    num_cmd = clean_embed_value(row.get("numCmd", "?"), default="?")

    embed = discord.Embed(
        title=truncate_embed_value(char_name, 256),
        description=truncate_embed_value(f"{move_name} ({num_cmd})", 4096),
        colour=0x3998C6,
    )

    startup = clean_embed_value(row.get("startup", ""))
    active = clean_embed_value(row.get("active", ""))
    recovery = clean_embed_value(row.get("recovery", "")).replace("(", " (Whiff: ")
    cancel = clean_embed_value(row.get("xx", ""))
    damage = clean_embed_value(row.get("dmg", ""))
    guard = clean_embed_value(row.get("atkLvl", ""))
    atk_range = format_attack_range_for_table(row)
    on_hit = clean_embed_value(row.get("onHit", ""))
    on_block = clean_embed_value(row.get("onBlock", ""))

    drive_hit = clean_embed_value(row.get("DDoH", ""))
    drive_block = clean_embed_value(row.get("DDoB", ""))
    drive_gain = clean_embed_value(row.get("DGain", ""))
    super_hit = clean_embed_value(row.get("SelfSoH", ""))
    super_block = clean_embed_value(row.get("SelfSoB", ""))

    stun_hit = clean_embed_value(row.get("hitstun", ""))
    stun_block = clean_embed_value(row.get("blockstun", ""))

    hc_sp = clean_embed_value(row.get("hcWinSpCa", ""))
    hc_tc = clean_embed_value(row.get("hcWinTc", ""))
    hc_notes = clean_embed_value(row.get("hcWinNotes", ""), strip_brackets=True)

    add_embed_field(embed, "Startup", startup, inline=True)
    add_embed_field(embed, "Active", active, inline=True)
    add_embed_field(embed, "Recovery", recovery, inline=True)

    add_embed_field(embed, "On Hit", on_hit, inline=True)
    add_embed_field(embed, "On Block", on_block, inline=True)
    add_embed_field(embed, "Cancel", cancel, inline=True)

    add_embed_field(embed, "Damage", damage, inline=True)
    add_embed_field(embed, "Guard", guard, inline=True)
    add_embed_field(embed, "Range", atk_range, inline=True)
    add_embed_field(embed, "Drive Gain", drive_gain, inline=True)

    add_embed_field(embed, "Drive Dmg", format_hit_block_value(drive_hit, drive_block), inline=True)
    add_embed_field(embed, "Super Gain", format_hit_block_value(super_hit, super_block), inline=True)
    add_embed_field(embed, "Stun", format_hit_block_value(stun_hit, stun_block), inline=True)

    add_embed_field(embed, "Hit Confirm (Sp/Su)", hc_sp, inline=True)
    add_embed_field(embed, "Hit Confirm (TC)", hc_tc, inline=True)
    add_embed_field(embed, "Hit Confirm Notes", hc_notes, inline=False)

    extra_info = clean_embed_value(row.get("extraInfo", ""), strip_brackets=True)
    if extra_info:
        embed.set_footer(text=truncate_embed_value(extra_info, 2048))

    return embed


def iter_unique_frame_rows(rows):
    seen = set()
    unique_rows = []
    for row in rows or []:
        key = (
            row.get("char_name", "Unknown"),
            row.get("moveName", "Unknown"),
            row.get("numCmd", "?"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
    return unique_rows


def build_frame_embeds(rows):
    embeds = []
    for row in iter_unique_frame_rows(rows):
        embeds.append(build_frame_embed(row))
    return embeds


def sanitize_embed_followup_text(text):
    raw = str(text or "").strip()
    if not raw:
        return "Noted. The relevant frame data is in the embeds above."

    table_markers = [
        "Startup:",
        "Active:",
        "Recovery:",
        "Range:",
        "On Hit:",
        "On Block:",
        "Drive Dmg",
        "Super Gain",
        "Hit Confirm",
        "Stun Frames",
        "Character:",
    ]
    filtered_lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(marker in stripped for marker in table_markers):
            continue
        if stripped.startswith("**") and stripped.endswith("**"):
            continue
        filtered_lines.append(stripped)

    cleaned = "\n".join(filtered_lines).strip()
    if cleaned:
        return cleaned

    sentence_candidates = re.split(r"(?<=[.!?])\s+", raw)
    for sentence in sentence_candidates:
        sentence = sentence.strip()
        if sentence:
            return sentence
    return "Noted. The relevant frame data is in the embeds above."

def get_selected_figures_str(guild):
    """Pick a random figure from the BUENAVISTA role members."""
    figures_pool = ['Yimbo', 'zed', 'sainted', 'LL', 'Torino']
    if guild:
        role = discord.utils.get(guild.roles, name="BUENAVISTA")
        if role:
            # add members (no bots, filter nicholas)
            for m in role.members:
                if not m.bot and m.display_name.lower() != "nicholas anthony pham":
                    figures_pool.extend([m.display_name])
    
    # dedup
    figures_pool = list(set(figures_pool))
    
    # pick 1 figure max (to keep total limit low)
    pool_size = len(figures_pool)
    if pool_size > 0:
        selected_figures = random.sample(figures_pool, 1)
    else:
        selected_figures = []
    
    return selected_figures[0] if selected_figures else ""


def parse_timezone(tz_str):
    tz = tz_str.strip().lower()
    if not tz:
        return None, None
    if tz in TZ_ALIASES:
        tz = TZ_ALIASES[tz]
    raw_offset_match = re.match(r"^([+-])(\d{1,2})(?::?(\d{2}))?$", tz)
    if raw_offset_match:
        sign = 1 if raw_offset_match.group(1) == "+" else -1
        hours = int(raw_offset_match.group(2))
        minutes = int(raw_offset_match.group(3) or 0)
        offset = datetime.timedelta(hours=hours, minutes=minutes) * sign
        return datetime.timezone(offset), f"UTC{raw_offset_match.group(1)}{hours:02d}:{minutes:02d}"
    offset_match = re.match(r"^(utc|gmt)([+-])(\d{1,2})(?::?(\d{2}))?$", tz)
    if offset_match:
        sign = 1 if offset_match.group(2) == "+" else -1
        hours = int(offset_match.group(3))
        minutes = int(offset_match.group(4) or 0)
        offset = datetime.timedelta(hours=hours, minutes=minutes) * sign
        return datetime.timezone(offset), f"UTC{offset_match.group(2)}{hours:02d}:{minutes:02d}"
    try:
        return ZoneInfo(tz), tz
    except Exception:
        return None, None


def is_reminder_request_text(text):
    return bool(re.search(r"\bremind(?:\s+me)?\b", text or "", re.IGNORECASE))


def get_reminder_target_user_ids(message, existing_ids=None):
    targets = []
    if existing_ids:
        for user_id in existing_ids:
            try:
                normalized = int(user_id)
            except (TypeError, ValueError):
                continue
            if normalized not in targets:
                targets.append(normalized)

    for member in message.mentions:
        if client.user and member.id == client.user.id:
            continue
        if member.id not in targets:
            targets.append(member.id)

    if not targets:
        targets.append(message.author.id)
    return targets


def parse_reminder_request(text, allow_missing_tz=False):
    text = text.strip()
    if not text:
        return None, None, None, None, "I couldn't parse that. Try: 'remind me to <task> tomorrow at 2:30pm GMT'.", None

    time_match = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text, re.IGNORECASE)
    if not time_match:
        return None, None, None, None, "I couldn't parse the time. Use: 'at 2:30pm' or 'at 14:30'.", None

    hour = int(time_match.group(1))
    minute = int(time_match.group(2) or 0)
    ampm = (time_match.group(3) or "").lower()
    if ampm:
        if hour == 12:
            hour = 0
        if ampm == "pm":
            hour += 12
    if hour > 23 or minute > 59:
        return None, None, None, None, "Time is invalid. Use formats like 2:30pm or 14:30.", None

    rel_match = re.search(r"\b(today|tomorrow)\b", text, re.IGNORECASE)
    rel = rel_match.group(1).lower() if rel_match else None
    date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    date_str = date_match.group(1) if date_match else None

    task = ""
    after_time = text[time_match.end():]
    to_after_time = re.search(r"\bto\s+(.+)$", after_time, re.IGNORECASE)
    if to_after_time:
        task = to_after_time.group(1).strip()
    if not task:
        task = re.sub(r"^\s*remind(?:\s+me)?\s+(?:to\s+)?", "", text, flags=re.IGNORECASE).strip()
        task = re.sub(r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b.*$", "", task, flags=re.IGNORECASE).strip()
    if not task:
        return None, None, None, None, "I couldn't find the task. Try: 'remind me to <task> at 2:30pm GMT'.", None

    tz_match = TZ_REGEX.search(text)
    if not tz_match:
        if allow_missing_tz:
            pending = {
                "task": task,
                "hour": hour,
                "minute": minute,
                "rel": rel,
                "date_str": date_str,
            }
            return None, None, None, None, None, pending
        return None, None, None, None, "Please include a timezone (e.g., GMT, UTC+2, America/New_York).", None
    tz_str = tz_match.group(0)
    tzinfo, tz_label = parse_timezone(tz_str)
    if not tzinfo:
        return None, None, None, None, "Unknown timezone. Use GMT/UTC, UTC+2, or IANA like America/New_York.", None

    now_tz = datetime.datetime.now(tzinfo)
    if date_str:
        reminder_date = date.fromisoformat(date_str)
    elif rel == "tomorrow":
        reminder_date = (now_tz + datetime.timedelta(days=1)).date()
    else:
        reminder_date = now_tz.date()

    reminder_dt = datetime.datetime(
        reminder_date.year,
        reminder_date.month,
        reminder_date.day,
        hour,
        minute,
        tzinfo=tzinfo,
    )
    if reminder_dt < now_tz:
        if not date_str and rel is None:
            reminder_dt = reminder_dt + datetime.timedelta(days=1)
        else:
            return None, None, None, None, "That time has already passed. Please choose a future time.", None

    return task, reminder_dt, reminder_dt.astimezone(datetime.timezone.utc), tz_label, None, None


async def build_reminder_ack_text(task, reminder_dt, tz_label, guild):
    default_text = f"Reminder set for {reminder_dt.strftime('%Y-%m-%d %H:%M')} {tz_label}."
    if not LLM_ENABLED:
        return default_text
    selected_figures_str = get_selected_figures_str(guild)
    prompt = (
        "Confirm the reminder is set. One sentence. "
        f"Task: {task}. "
        f"Time: {reminder_dt.strftime('%Y-%m-%d %H:%M')} {tz_label}. "
        "Include the exact time and timezone. "
        "Tone: calm, pragmatic, nonchalant. "
        "No emojis. Do not ask a question."
    )
    llm_messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(selected_figures_str=selected_figures_str)},
        {"role": "user", "content": prompt},
    ]
    try:
        reply_text = await get_llm_response(llm_messages)
        if not reply_text:
            raise RuntimeError("Empty reminder ack response")
        return truncate_message(reply_text, limit=280)
    except Exception as e:
        print(f"Reminder LLM ack error: {e}", flush=True)
        return default_text


async def build_reminder_fire_text(task, guild):
    default_text = f"reminder: {task}"
    if not LLM_ENABLED:
        return default_text
    selected_figures_str = get_selected_figures_str(guild)
    prompt = (
        "Send a short reminder message. One sentence. "
        f"Task: {task}. "
        "Tone: calm, pragmatic, nonchalant. "
        "No emojis. Do not ask a question. Do not include any @mentions."
    )
    llm_messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(selected_figures_str=selected_figures_str)},
        {"role": "user", "content": prompt},
    ]
    try:
        reply_text = await get_llm_response(llm_messages)
        if not reply_text:
            raise RuntimeError("Empty reminder message response")
        return truncate_message(reply_text, limit=240)
    except Exception as e:
        print(f"Reminder LLM fire error: {e}", flush=True)
        return default_text


async def reminder_loop():
    print(f"Reminder loop started. Polling every {REMINDER_POLL_SECONDS}s", flush=True)
    last_count = None
    last_next = None
    while not client.is_closed():
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        reminder_count = len(REMINDERS)
        next_due = None
        if REMINDERS:
            next_due = min(r["when_utc"] for r in REMINDERS)
        if reminder_count != last_count or next_due != last_next:
            next_due_str = next_due.isoformat() if next_due else "None"
            print(f"Reminder state: count={reminder_count}, next_due={next_due_str}", flush=True)
            last_count = reminder_count
            last_next = next_due
        due = [r for r in REMINDERS if r["when_utc"] <= now_utc]
        if due:
            print(f"Reminder due: count={len(due)} now={now_utc.isoformat()}", flush=True)
            for reminder in due:
                channel = client.get_channel(reminder["channel_id"])
                if not channel:
                    try:
                        channel = await client.fetch_channel(reminder["channel_id"])
                    except Exception as e:
                        print(
                            "Reminder fetch channel error: channel_id="
                            f"{reminder['channel_id']} error={e}",
                            flush=True,
                        )
                        channel = None
                reminder_text = await build_reminder_fire_text(
                    reminder["task"],
                    getattr(channel, "guild", None),
                )
                target_ids = reminder.get("notify_user_ids") or [reminder["user_id"]]
                target_ids = [int(uid) for uid in target_ids if str(uid).isdigit()]
                if not target_ids:
                    target_ids = [reminder["user_id"]]
                if channel:
                    try:
                        mention_prefix = " ".join(f"<@{uid}>" for uid in target_ids)
                        channel_text = f"{mention_prefix} {reminder_text}".strip()
                        await channel.send(channel_text)
                    except Exception as e:
                        print(
                            "Reminder send error: channel_id="
                            f"{reminder['channel_id']} error={e}",
                            flush=True,
                        )
                else:
                    for target_id in target_ids:
                        try:
                            user = await client.fetch_user(target_id)
                            await user.send(reminder_text)
                            print(
                                "Reminder DM fallback sent: user_id="
                                f"{target_id}",
                                flush=True,
                            )
                        except Exception as e:
                            print(
                                "Reminder DM fallback error: user_id="
                                f"{target_id} error={e}",
                                flush=True,
                            )
                print(
                    "Reminder fired: user_id="
                    f"{reminder['user_id']} channel_id={reminder['channel_id']} "
                    f"when_utc={reminder['when_utc'].isoformat()} targets={target_ids}",
                    flush=True,
                )
            REMINDERS[:] = [r for r in REMINDERS if r not in due]
        await asyncio.sleep(REMINDER_POLL_SECONDS)

async def send_daily_messages(channel):
    """Send scheduled daily messages to the channel."""
    print("[daily-message] Dispatching 4-line batch.", flush=True)
    messages = [
        "Hello everyone",
        "How are you today?",
        "Has anyone improved?",
        "<:sponge:1416270403923480696>"
    ]
    for msg in messages:
        try:
            await channel.send(msg)
            
            await asyncio.sleep(1) 
        except Exception as e:
            print(f"[daily-message] Dispatch error: {e}", flush=True)
    print("[daily-message] Batch dispatched successfully.", flush=True)


async def send_generated_encouragement(channel, source_label="scheduled"):
    if not LLM_ENABLED:
        print(f"[encouragement] {source_label} skipped: LLM disabled.", flush=True)
        return

    context_history = []
    try:
        context_history = await build_channel_context_history(channel)
    except Exception as e:
        print(f"[encouragement] {source_label} context load error: {e}", flush=True)

    context_prompt = build_contextual_encouragement_prompt(context_history)
    use_context_prompt = bool(context_prompt) and (random.random() < ENCOURAGEMENT_CONTEXT_CHANCE)

    if use_context_prompt:
        selected_prompt = context_prompt
        prompt_kind = "context"
    else:
        selected_prompt = random.choice(ENCOURAGEMENT_PROMPTS)
        prompt_kind = (
            "anecdote"
            if selected_prompt == ENCOURAGEMENT_ANECDOTE_PROMPT
            else "improvement"
        )

    selected_figures_str = get_selected_figures_str(channel.guild)
    llm_messages = [
        {
            "role": "system",
            "content": IMPROVEMENT_PROMPT.format(selected_figures_str=selected_figures_str),
        },
    ]
    memory_context = build_memory_context(max_entries=8, char_budget=1200)
    if memory_context:
        llm_messages.append({"role": "user", "content": f"Long-term Discord memory:\n{memory_context}"})
        llm_messages.append({"role": "assistant", "content": "Understood. I will keep that memory in mind."})
    llm_messages.append({"role": "user", "content": selected_prompt})
    try:
        reply_text = await get_llm_response(llm_messages)
        await channel.send(reply_text)
        asyncio.create_task(
            capture_discord_memory(
                channel,
                context_history[-MEMORY_CONTEXT_MAX_MESSAGES:],
                source_label=f"encouragement/{source_label}",
            )
        )
        print(
            f"[encouragement] {source_label} ({prompt_kind}) sent at {datetime.datetime.now().isoformat()} "
            f"context_lines={len(context_history)}",
            flush=True,
        )
    except Exception as e:
        print(f"[encouragement] {source_label} error: {e}", flush=True)


async def send_daily_damn_gg(channel, source_label="scheduled"):
    try:
        await channel.send(DAILY_DAMN_GG_TEXT)
        print(
            f"{source_label.capitalize()} literal message sent at {datetime.datetime.now().isoformat()}",
            flush=True,
        )
    except Exception as e:
        print(f"{source_label.capitalize()} literal message error: {e}", flush=True)


def get_frame_row_gif_links(row, limit=4):
    if not isinstance(row, dict):
        return []

    links = []
    seen = set()

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
    if char_key == "alex" and row_num_cmd_norm.startswith("2pp>"):
        alex_query_links = lookup_hitbox_gif_links_from_query(
            char_key,
            row_move_name_norm,
            limit=limit,
        )
        if alex_query_links:
            return alex_query_links

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


class FrameDataGifButton(discord.ui.Button):
    def __init__(self, row, gif_links):
        super().__init__(label="Show GIF", style=discord.ButtonStyle.primary, disabled=not gif_links)
        self.frame_row = row
        self.gif_links = list(gif_links or [])

    async def callback(self, interaction: discord.Interaction):
        move_name = str((self.frame_row or {}).get("moveName", "This move")).strip() or "This move"
        if not self.gif_links:
            await interaction.response.send_message(
                f"I have frame data for {move_name} but no hitbox gif link yet.",
                ephemeral=True,
            )
            return

        if len(self.gif_links) == 1:
            await interaction.response.send_message(self.gif_links[0])
            return

        await interaction.response.send_message("\n".join(self.gif_links[:4]))


class FrameDataGifView(discord.ui.View):
    def __init__(self, row):
        super().__init__(timeout=3600)
        self.add_item(FrameDataGifButton(row, get_frame_row_gif_links(row)))


async def send_frame_embeds_with_views(channel, rows, embeds=None):
    unique_rows = iter_unique_frame_rows(rows or [])
    embed_list = list(embeds or build_frame_embeds(unique_rows))
    if not embed_list:
        return False

    for index, embed in enumerate(embed_list):
        view = FrameDataGifView(unique_rows[index]) if index < len(unique_rows) else None
        await channel.send(embed=embed, view=view)
    return True


async def send_frame_table_response(message, rows, data_text):
    unique_rows = iter_unique_frame_rows(rows or [])
    if unique_rows:
        try:
            await send_frame_embeds_with_views(message.channel, unique_rows)
            return True
        except Exception as e:
            print(f"Direct frame embed send failed: {e}", flush=True)
    return False


async def send_gif_links_response(message, gif_links, wants_comparison=False):
    if not gif_links:
        return False
    try:
        if wants_comparison and len(gif_links) > 1:
            await message.reply("\n".join(gif_links))
        else:
            await message.reply(gif_links[0])
        return True
    except Exception as reply_error:
        if is_deleted_message_reference_error(reply_error):
            print("Hitbox gif reply target deleted. Triggering failsafe.", flush=True)
            await send_deleted_message_failsafe(message.channel)
        else:
            print(f"Hitbox gif reply error: {reply_error}", flush=True)
    return False


def sanitize_llm_lookup_query(text):
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    cleaned = cleaned.strip("`\"' \t\r\n")
    cleaned = cleaned.splitlines()[0].strip()
    cleaned = re.sub(r"^(?:corrected\s*query\s*:)\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned


def extract_lookup_strength_hint(text):
    raw_text = str(text or "").lower()
    strength_patterns = [
        r"\bod\b",
        r"\bex\b",
        r"\blp\b",
        r"\bmp\b",
        r"\bhp\b",
        r"\blk\b",
        r"\bmk\b",
        r"\bhk\b",
        r"\blight\b",
        r"\bmedium\b",
        r"\bheavy\b",
        r"\bl\b",
        r"\bm\b",
        r"\bh\b",
    ]
    for pattern in strength_patterns:
        match = re.search(pattern, raw_text)
        if match:
            return match.group(0)
    return None


async def rewrite_sf_lookup_query_with_llm(query_text, guild=None):
    raw_query = strip_discord_mentions(str(query_text or "")).strip()
    if not raw_query or not LLM_ENABLED:
        return None

    output_hints = []
    if re.search(r"\b(?:gif|gifs|hitbox|hitboxes)\b", raw_query, re.IGNORECASE):
        output_hints.append("gif")
    if re.search(r"\b(?:framedata|frame\s*data|frames?)\b", raw_query, re.IGNORECASE):
        output_hints.append("framedata")

    llm_messages = [
        {
            "role": "system",
            "content": (
                "You normalize Street Fighter 6 lookup requests for a deterministic parser. "
                "Fix misspellings, slang, or esoteric syntax only when highly confident. "
                "Preserve the intended character, move, strength, air/charged/stocked/OD qualifiers, and output intent. "
                "If the move is clearly unique to one character and the user omitted the character, include that character. "
                "Do not answer the question. Do not explain anything. "
                "Return ONLY one corrected query, or NONE if you are not confident."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Rewrite this Street Fighter 6 lookup query so a parser can understand it.\n"
                f"Query: {raw_query}\n"
                "Examples:\n"
                "- adement flame framedata -> akuma adamant flame framedata\n"
                "- jinra hk gif -> jinrai hk gif\n"
                "- stocekd air sa2 -> stocked air sa2\n"
                "Return ONLY the corrected query or NONE."
            ),
        },
    ]
    try:
        rewritten = await get_llm_response(llm_messages)
    except Exception as e:
        print(f"[parser-llm] rewrite error: {e}", flush=True)
        return None

    rewritten = sanitize_llm_lookup_query(rewritten)
    if not rewritten or rewritten.upper() == "NONE":
        return None

    rewritten_lower = rewritten.lower()
    original_lower = raw_query.lower()
    if rewritten_lower == original_lower:
        return None

    original_strength_hint = extract_lookup_strength_hint(original_lower)
    rewritten_strength_hint = extract_lookup_strength_hint(rewritten_lower)
    if original_strength_hint and not rewritten_strength_hint:
        intent_match = re.search(r"\b(?:gif|gifs|hitbox|hitboxes|framedata|frame\s*data|frames?)\b", rewritten_lower)
        if intent_match:
            insert_at = intent_match.start()
            rewritten = f"{rewritten[:insert_at].rstrip()} {original_strength_hint} {rewritten[insert_at:].lstrip()}".strip()
        else:
            rewritten = f"{rewritten} {original_strength_hint}".strip()
        rewritten_lower = rewritten.lower()

    if "gif" in output_hints and not re.search(r"\b(?:gif|gifs|hitbox|hitboxes)\b", rewritten_lower):
        rewritten = f"{rewritten} gif"
        rewritten_lower = rewritten.lower()
    if "framedata" in output_hints and not re.search(r"\b(?:framedata|frame\s*data|frames?)\b", rewritten_lower):
        rewritten = f"{rewritten} framedata"

    return rewritten.strip()


def get_daily_random_slots(day_start, count, excluded_slots=None):
    excluded_seconds = set()
    for slot in excluded_slots or []:
        if slot.date() != day_start.date():
            continue
        excluded_seconds.add(int((slot - day_start).total_seconds()))

    available_seconds = [second for second in range(86400) if second not in excluded_seconds]
    if count <= 0 or not available_seconds:
        return []
    sample_count = min(count, len(available_seconds))
    second_slots = sorted(random.sample(available_seconds, sample_count))
    return [day_start + datetime.timedelta(seconds=slot) for slot in second_slots]


async def background_task():
    global NEXT_RUN_TIME
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print(f"[daily-message] Could not find channel with ID {CHANNEL_ID}", flush=True)
        return

    print("[daily-message] Scheduling started.", flush=True)

    while not client.is_closed():
        now = datetime.datetime.now()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        random_seconds = random.randint(0, 86399)
        target_time = start_of_day + datetime.timedelta(seconds=random_seconds)

        if target_time < now:
            start_of_tomorrow = start_of_day + datetime.timedelta(days=1)
            random_seconds_tomorrow = random.randint(0, 86399)
            target_time = start_of_tomorrow + datetime.timedelta(seconds=random_seconds_tomorrow)
            print(f"[daily-message] Daily slot elapsed. Next cycle at {target_time}", flush=True)
        else:
            print(f"[daily-message] Current cycle scheduled at {target_time}", flush=True)

        NEXT_RUN_TIME = target_time
        wait_seconds = (target_time - datetime.datetime.now()).total_seconds()
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
        if client.is_closed():
            return

        await send_daily_messages(channel)

        next_day = (
            datetime.datetime.now() + datetime.timedelta(days=1)
        ).replace(hour=0, minute=0, second=0, microsecond=0)
        seconds_until_tomorrow = (next_day - datetime.datetime.now()).total_seconds()
        print(
            f"[daily-message] Done for today. Waiting {seconds_until_tomorrow / 3600:.2f} hours until midnight regeneration.",
            flush=True,
        )
        NEXT_RUN_TIME = None
        if seconds_until_tomorrow > 0:
            await asyncio.sleep(seconds_until_tomorrow)


async def background_encouragement_task():
    global NEXT_ENCOURAGEMENT_TIME
    await client.wait_until_ready()
    if DAILY_ENCOURAGEMENT_MESSAGES <= 0:
        print("[encouragement] Disabled: DAILY_ENCOURAGEMENT_MESSAGES <= 0", flush=True)
        return

    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print(f"[encouragement] Could not find channel with ID {CHANNEL_ID}", flush=True)
        return

    print(
        f"[encouragement] Scheduling started. Target={DAILY_ENCOURAGEMENT_MESSAGES} LLM messages per day. "
        f"context_chance={ENCOURAGEMENT_CONTEXT_CHANCE:.2f} source={ENCOURAGEMENT_CONTEXT_SOURCE}",
        flush=True,
    )

    while not client.is_closed():
        now = datetime.datetime.now()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_slots = get_daily_random_slots(day_start, DAILY_ENCOURAGEMENT_MESSAGES)
        remaining_slots = [slot for slot in day_slots if slot > now]

        if not remaining_slots:
            day_start = day_start + datetime.timedelta(days=1)
            remaining_slots = get_daily_random_slots(day_start, DAILY_ENCOURAGEMENT_MESSAGES)

        slot_log = ", ".join(slot.strftime("%Y-%m-%d %H:%M:%S") for slot in remaining_slots)
        print(f"[encouragement] Slots ({len(remaining_slots)}): {slot_log}", flush=True)

        for index, slot_time in enumerate(remaining_slots, start=1):
            NEXT_ENCOURAGEMENT_TIME = slot_time
            wait_seconds = (slot_time - datetime.datetime.now()).total_seconds()
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            if client.is_closed():
                return
            print(
                f"[encouragement] Dispatching scheduled encouragement {index}/{len(remaining_slots)}.",
                flush=True,
            )
            await send_generated_encouragement(channel, source_label="scheduled")

        NEXT_ENCOURAGEMENT_TIME = None


async def background_damn_gg_task():
    global NEXT_DAMN_GG_TIME
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print(f"Could not find channel with ID {CHANNEL_ID}")
        return

    print("Damn gg scheduling started.", flush=True)

    while not client.is_closed():
        now = datetime.datetime.now()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_slots = get_daily_random_slots(day_start, DAILY_DAMN_GG_MESSAGES)
        remaining_slots = [slot for slot in day_slots if slot > now]

        if not remaining_slots:
            day_start = day_start + datetime.timedelta(days=1)
            remaining_slots = get_daily_random_slots(day_start, DAILY_DAMN_GG_MESSAGES)

        slot_log = ", ".join(slot.strftime("%Y-%m-%d %H:%M:%S") for slot in remaining_slots)
        print(f"Damn gg slots: {slot_log}", flush=True)

        for slot_time in remaining_slots:
            NEXT_DAMN_GG_TIME = slot_time
            wait_seconds = (slot_time - datetime.datetime.now()).total_seconds()
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            if client.is_closed():
                return
            await send_daily_damn_gg(channel, source_label="scheduled")

        NEXT_DAMN_GG_TIME = None



async def time_handler(request):
    data = {
        "target_time": str(NEXT_RUN_TIME) if NEXT_RUN_TIME else None,
        "daily_message_time": str(NEXT_RUN_TIME) if NEXT_RUN_TIME else None,
        "encouragement_time": str(NEXT_ENCOURAGEMENT_TIME) if NEXT_ENCOURAGEMENT_TIME else None,
        "damn_gg_time": str(NEXT_DAMN_GG_TIME) if NEXT_DAMN_GG_TIME else None,
        "video_time": str(NEXT_VIDEO_TIME) if NEXT_VIDEO_TIME else None,
    }
    return web.json_response(data)

async def start_web_server():
    app = web.Application()
    app.router.add_get('/time', time_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("Web server started on port 8080")


# message queue - initialized in on_ready to avoid event loop issues
message_queue = None
worker_task = None
background_task_handle = None
background_encouragement_task_handle = None
background_damn_gg_task_handle = None
background_video_task_handle = None
reminder_task_handle = None
web_server_task = None
LAST_DAILY_VIDEO_ID = {}
SPECIAL_STRENGTH_PROMPT_MODE = {}
SPECIAL_STRENGTH_PROMPT_MODE_MAX = 300

ACTIVE_QUIZZES = {}  # channel_id -> quiz_state; one active quiz per channel at a time
QUIZ_PENDING_ANOTHER = {}  # channel_id -> {"created_at": utc_dt, "message_id": int|None}
QUIZ_PENDING_MODE = {}  # channel_id -> {"created_at": utc_dt, "message_id": int|None}
QUIZ_PENDING_ANOTHER_TIMEOUT_TASKS = {}  # channel_id -> asyncio.Task
QUIZ_LEADERBOARD_FILE = os.getenv("QUIZ_LEADERBOARD_FILE", "quiz_leaderboard.json")
QUIZ_GLOBAL_LEADERBOARD = {}  # user_id -> lifetime quiz points
QUIZ_GLOBAL_LEADERBOARD_NAMES = {}  # user_id -> latest seen display name
QUIZ_LEADERBOARD_LOCK = asyncio.Lock()
QUIZ_INTENT_RE = re.compile(
    r"\bquiz\b|\bquizz|\bguess.*\bframe|\bframe.*\bguess|\btest\s+me\b",
    re.IGNORECASE,
)
QUIZ_LEADERBOARD_REQUEST_RE = re.compile(
    r"\b(quiz\s+leaderboard|leaderboard\s+for\s+quiz|show\s+(?:the\s+)?(?:quiz\s+)?leaderboard|who\s+tops\s+(?:the\s+)?(?:quiz\s+)?leaderboard)\b",
    re.IGNORECASE,
)
QUIZ_LEADERBOARD_TOP_RE = re.compile(r"\btop\s+(\d{1,2})\b", re.IGNORECASE)
QUIZ_NAME_PREFIX_RE = re.compile(r"^\s*(?:hey\s+)?(?:korean\s+)?bub\b", re.IGNORECASE)
QUIZ_ESCAPE_REQUEST_RE = re.compile(
    r"\b(framedata|frame\s*data|gif|range|startup|damage|on\s+hit|on\s+block|bnb|oki|coach|compare|comparison|vs|versus|punish|stats?|health|reversal|cfn|remind(?:er)?|time)\b",
    re.IGNORECASE,
)
QUIZ_GUESS_AGAIN_RE = re.compile(
    r"\b(guess\s+again|again|continue|keep\s+guessing|try\s+again)\b",
    re.IGNORECASE,
)
QUIZ_REVEAL_END_RE = re.compile(
    r"\b(answer|reveal|show|tell|what'?s\s+the\s+answer|whats\s+the\s+answer|give\s+up|forfeit|forefeit|forfiet|surrender|concede|you\s+win|i\s+lose|end|stop|quit|cancel)\b",
    re.IGNORECASE,
)
QUIZ_ANOTHER_YES_RE = re.compile(
    r"\b(yes|yea|yeah|yep|yup|sure|ok|okay|another|again|continue|new\s+question)\b",
    re.IGNORECASE,
)
QUIZ_ANOTHER_NO_RE = re.compile(
    r"\b(no|nah|nope|naw|not\s+now|later|done|stop|end|quit|cancel|no\s+thanks|im\s+good|i'?m\s+good)\b",
    re.IGNORECASE,
)
QUIZ_FORFEIT_RE = re.compile(
    r"\b(give\s+up|forfeit|forefeit|forfiet|surrender|concede|you\s+win|i\s+lose)\b",
    re.IGNORECASE,
)
QUIZ_CHEAT_LOOKUP_RE = re.compile(
    r"\b(framedata|frame\s*data|gif|gifs|hit\s*box(?:es)?|hitbox(?:es)?)\b",
    re.IGNORECASE,
)
QUIZ_MODE_RE = re.compile(r"\b(easy|medium|hard)\b", re.IGNORECASE)
QUIZ_PENDING_ANOTHER_TTL_SECONDS = 300
QUIZ_PENDING_MODE_TTL_SECONDS = 600
QUIZ_INTRO_BUTTON_RE = re.compile(
    r"\b(?:st|cr|j)\s*(?:lp|mp|hp|lk|mk|hk)\b|\b(?:standing|crouching|jumping)\s+(?:light|medium|heavy)\s+(?:punch|kick)\b|\b(?:[1-9]\d{0,2}(?:lp|mp|hp|lk|mk|hk))\b|\b(?:236|214|623|421|41236|63214|22|66|44)\b|\b(?:sa1|sa2|sa3|ca|level\s*[123])\b",
    re.IGNORECASE,
)
QUIZ_INTRO_DATA_TERM_RE = re.compile(
    r"\b(startup|active|recovery|on\s+hit|on\s+block|damage|range|guard|cancel|total|block\s+advantage|frame\s+advantage)\b",
    re.IGNORECASE,
)
QUIZ_CHARACTER_TERMS_CACHE = None
QUIZ_MOVE_NAME_TERMS_CACHE = None
QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE = None
QUIZ_VALID_MODES = {"easy", "medium", "hard"}
QUIZ_START_LOCK = asyncio.Lock()


# ==================== QUIZ FEATURE ====================

def _quiz_row_has_data(row):
    """Return True if a frame data row has enough real values to make a useful question."""
    numcmd = str(row.get("numCmd", "")).strip()
    if not numcmd or numcmd.lower() in ("-", "nan", ""):
        return False
    for field in ("startup", "dmg"):
        val = str(row.get(field, "")).strip()
        if val and val.lower() not in ("-", "nan", "") and re.search(r"\d", val):
            return True
    return False


def _quiz_normalize_mode(mode, default="hard"):
    mode_text = str(mode or "").strip().lower()
    if mode_text in QUIZ_VALID_MODES:
        return mode_text
    return default


def _quiz_extract_mode_from_text(text):
    match = QUIZ_MODE_RE.search(str(text or "").lower())
    if not match:
        return None
    return match.group(1).lower()


def _quiz_row_is_shared_mechanic(row):
    move_type = str(row.get("moveType", "")).strip().lower()
    if move_type in {"system", "drive", "throw", "taunt"}:
        return True

    combined = " ".join(
        str(row.get(key, "")).lower().strip()
        for key in ("moveName", "cmnName", "numCmd", "plnCmd")
    )
    return any(
        re.search(pattern, combined)
        for pattern in (
            r"\bdrive impact\b",
            r"\bdrive reversal\b",
            r"\bdrive rush\b",
            r"\bdrive parry\b",
            r"\b(?:forward|back)?\s*throw\b",
            r"\btaunt\b",
        )
    )


def _quiz_row_is_jump_normal(row):
    move_type = str(row.get("moveType", "")).strip().lower()
    if move_type != "normal":
        return False

    move_name = str(row.get("moveName", "")).lower().strip()
    cmn_name = str(row.get("cmnName", "")).lower().strip()
    num_cmd = str(row.get("numCmd", "")).lower().strip()
    pln_cmd = str(row.get("plnCmd", "")).lower().strip()
    return (
        move_name.startswith("jump ")
        or cmn_name.startswith("jump ")
        or num_cmd.startswith(("7", "8", "9"))
        or pln_cmd.startswith(("u+", "ub+", "uf+", "j"))
    )


def _quiz_row_allowed_for_mode(row, mode):
    mode_key = _quiz_normalize_mode(mode)
    move_type = str(row.get("moveType", "")).strip().lower()

    if _quiz_row_is_shared_mechanic(row):
        return False

    if mode_key == "easy":
        return move_type == "normal" and not _quiz_row_is_jump_normal(row)

    if mode_key == "medium":
        return move_type in {"normal", "special", "command-grab", "movement-special"}

    if mode_key == "hard":
        return move_type in {"normal", "special", "movement-special", "command-grab", "super"}
    return True


def _safe_first_int(text):
    """Parse the first integer from a frame data value string like '5', '3+5', '2(2)2'."""
    m = re.search(r"\d+", str(text or ""))
    return int(m.group()) if m else None


def _compute_total_frames(row):
    """Try to compute total frames = startup + active + recovery (first integers only)."""
    s = _safe_first_int(row.get("startup", ""))
    a = _safe_first_int(row.get("active", ""))
    r = _safe_first_int(row.get("recovery", ""))
    if s is not None and a is not None and r is not None:
        return s + a + r
    return None


def _fmt_quiz_field(row, key):
    """Return a display-ready string for a row field, or '-' if empty/missing."""
    val = str(row.get(key, "")).strip()
    if not val or val.lower() in ("nan", ""):
        return "-"
    return val


def build_quiz_question_text(round_num, total_rounds, row, mode="hard"):
    """Build the quiz question message from a frame data row, hiding character and move name."""
    mode_key = _quiz_normalize_mode(mode)
    mode_label = mode_key.capitalize()
    startup   = _fmt_quiz_field(row, "startup")
    active    = _fmt_quiz_field(row, "active")
    recovery  = _fmt_quiz_field(row, "recovery")
    total     = _compute_total_frames(row)
    on_hit    = _fmt_quiz_field(row, "onHit")
    on_block  = _fmt_quiz_field(row, "onBlock")
    damage    = _fmt_quiz_field(row, "dmg")
    guard     = _fmt_quiz_field(row, "atkLvl")
    cancel    = clean_embed_value(row.get("xx", ""), default="-", strip_brackets=True) or "-"
    atk_range = _fmt_quiz_field(row, "atkRange")
    # Use existing is_missing_attack_range_value to suppress placeholder text
    if is_missing_attack_range_value(atk_range):
        atk_range = "-"

    timing_parts = [
        f"Startup: **{startup}**",
        f"Active: **{active}**",
        f"Recovery: **{recovery}**",
    ]
    if total is not None:
        timing_parts.append(f"Total: **{total}**")

    prop_parts = [
        f"Damage: **{damage}**",
        f"Guard: **{guard}**",
        f"Cancel: **{cancel}**",
    ]
    if atk_range != "-":
        prop_parts.append(f"Range: **{atk_range}**")

    lines = [
        f"**FRAME DATA QUIZ ({mode_label})**",
        "Guess the character and the move.",
        "",
        " | ".join(timing_parts),
        f"On Hit: **{on_hit}** | On Block: **{on_block}**",
        " | ".join(prop_parts),
        "",
        "Answer by mention or reply with: `Character Move`",
        "Example: `Ryu 5LP` or `Cammy spiral arrow`",
    ]
    return "\n".join(lines)


def build_quiz_frame_embed(row, mode="hard"):
    """Build a quiz embed using the standard frame table format without answer identity."""
    mode_key = _quiz_normalize_mode(mode)
    mode_label = mode_key.capitalize()
    embed = build_frame_embed(row)
    embed.title = truncate_embed_value(f"FRAME DATA QUIZ ({mode_label})", 256)
    embed.description = None

    footer_text = getattr(getattr(embed, "footer", None), "text", "")
    if footer_text:
        censored_footer = _quiz_censor_character_names(footer_text)
        embed.set_footer(text=truncate_embed_value(censored_footer, 2048))

    return embed


def _sanitize_quiz_ascii_line(text):
    """Normalize quiz LLM text to plain ASCII, single line, and no em dash."""
    cleaned = str(text or "")
    cleaned = cleaned.replace("\u2014", "-").replace("\u2013", "-")
    cleaned = cleaned.replace("\r", " ").replace("\n", " ")
    cleaned = cleaned.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _normalize_quiz_words(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _get_quiz_character_terms():
    global QUIZ_CHARACTER_TERMS_CACHE
    if QUIZ_CHARACTER_TERMS_CACHE is not None:
        return QUIZ_CHARACTER_TERMS_CACHE

    terms = set()
    for name in FRAME_DATA.keys():
        normalized = _normalize_quiz_words(name)
        if normalized:
            terms.add(normalized)

    for name in CHARACTER_ALIASES.keys():
        normalized = _normalize_quiz_words(name)
        if normalized:
            terms.add(normalized)

    for name in CHARACTER_ALIASES.values():
        normalized = _normalize_quiz_words(name)
        if normalized:
            terms.add(normalized)

    QUIZ_CHARACTER_TERMS_CACHE = sorted(terms, key=len, reverse=True)
    return QUIZ_CHARACTER_TERMS_CACHE


def _get_quiz_character_censor_patterns():
    global QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE
    if QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE is not None:
        return QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE

    patterns = []
    seen_patterns = set()
    for term in _get_quiz_character_terms():
        words = [word for word in str(term or "").split() if word]
        if not words:
            continue
        pattern_text = r"\b" + r"\W*".join(re.escape(word) for word in words) + r"\b"
        if pattern_text in seen_patterns:
            continue
        seen_patterns.add(pattern_text)
        patterns.append(re.compile(pattern_text, re.IGNORECASE))

    QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE = patterns
    return QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE


def _quiz_censor_character_names(text):
    raw_text = str(text or "")
    if not raw_text:
        return raw_text

    def mask_match(match):
        matched = match.group(0)
        alnum_count = len(re.sub(r"[^A-Za-z0-9]", "", matched))
        return "*" * max(1, alnum_count)

    censored = raw_text
    for pattern in _get_quiz_character_censor_patterns():
        censored = pattern.sub(mask_match, censored)
    return censored


def _get_quiz_move_name_terms():
    global QUIZ_MOVE_NAME_TERMS_CACHE
    if QUIZ_MOVE_NAME_TERMS_CACHE is not None:
        return QUIZ_MOVE_NAME_TERMS_CACHE

    terms = set()
    for rows in FRAME_DATA.values():
        for row in rows:
            normalized = _normalize_quiz_words(row.get("moveName", ""))
            if not normalized:
                continue
            words = normalized.split()
            if len(words) >= 2 or len(normalized) >= 7:
                terms.add(normalized)

    QUIZ_MOVE_NAME_TERMS_CACHE = sorted(terms, key=len, reverse=True)
    return QUIZ_MOVE_NAME_TERMS_CACHE


def _quiz_intro_has_specific_answer_hint(text):
    normalized = _normalize_quiz_words(text)
    if not normalized:
        return True

    if re.search(r"\d", normalized):
        return True
    if QUIZ_INTRO_BUTTON_RE.search(normalized):
        return True
    if QUIZ_INTRO_DATA_TERM_RE.search(normalized):
        return True

    padded = f" {normalized} "
    for term in _get_quiz_character_terms():
        if f" {term} " in padded:
            return True

    for term in _get_quiz_move_name_terms():
        if f" {term} " in padded:
            return True
    return False


async def build_quiz_persona_intro(channel, round_num, total_rounds, mode="hard"):
    """Generate a short in-character quiz intro line via LLM, with safe fallback."""
    mode_key = _quiz_normalize_mode(mode)
    fallback = f"One {mode_key} quiz question is ready. Guess the character and move from the data."
    if not LLM_ENABLED:
        return fallback

    try:
        selected_figures_str = get_selected_figures_str(getattr(channel, "guild", None))
        llm_messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(selected_figures_str=selected_figures_str),
            },
            {
                "role": "user",
                "content": (
                    "Write one short in-character line introducing a Street Fighter 6 frame data quiz round. "
                    "This quiz has one question only. "
                    f"Difficulty mode is {mode_key}. "
                    "Do not mention any specific character, move, input, frame value, or answer clue. "
                    "Do not use numbers. "
                    "One sentence only. Keep it concise. No emojis. No em dash. ASCII only."
                ),
            },
        ]
        intro = await get_llm_response(llm_messages)
        intro = _sanitize_quiz_ascii_line(intro)
        if _quiz_intro_has_specific_answer_hint(intro):
            return fallback
        return intro or fallback
    except Exception as e:
        print(f"[quiz] intro llm error: {e}", flush=True)
        return fallback


async def build_quiz_question_message(channel, round_num, total_rounds, row, mode="hard"):
    """Build quiz prompt text + embed using the standard frame table layout."""
    intro = await build_quiz_persona_intro(channel, round_num, total_rounds, mode=mode)
    intro = _quiz_censor_character_names(intro)
    quiz_embed = build_quiz_frame_embed(row, mode=mode)
    prompt_text = f"{intro}\nAnswer by mention or reply with: `Character Move`"
    return prompt_text, quiz_embed


async def _quiz_send_thinking_message(message, text="Thinking..."):
    """Send an immediate quiz placeholder reply while longer work runs."""
    try:
        return await message.reply(text)
    except Exception as e:
        if is_deleted_message_reference_error(e):
            try:
                return await message.channel.send(text)
            except Exception as send_error:
                print(f"[quiz] thinking send error: {send_error}", flush=True)
                return None
        print(f"[quiz] thinking reply error: {e}", flush=True)
        try:
            return await message.channel.send(text)
        except Exception as send_error:
            print(f"[quiz] thinking fallback send error: {send_error}", flush=True)
            return None


async def _quiz_publish_from_placeholder(channel, placeholder_message, text, embed=None):
    """Edit placeholder message into final quiz output, or send a fallback."""
    if placeholder_message is not None:
        try:
            await placeholder_message.edit(content=text, embed=embed)
            return placeholder_message
        except Exception as e:
            print(f"[quiz] placeholder edit error: {e}", flush=True)

    try:
        return await channel.send(text, embed=embed)
    except Exception as e:
        print(f"[quiz] placeholder fallback send error: {e}", flush=True)
        return None


async def build_quiz_decline_message(channel):
    """Generate a short in-character reply when user declines another quiz question."""
    fallback = "Understood. We can run another question whenever you want."
    if not LLM_ENABLED:
        return fallback

    try:
        selected_figures_str = get_selected_figures_str(getattr(channel, "guild", None))
        llm_messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(selected_figures_str=selected_figures_str),
            },
            {
                "role": "user",
                "content": (
                    "The user declined another frame data quiz question. "
                    "Write one short in-character acknowledgement and end the flow. "
                    "One sentence only. No emojis. No em dash. ASCII only."
                ),
            },
        ]
        reply_text = await get_llm_response(llm_messages)
        reply_text = _sanitize_quiz_ascii_line(reply_text)
        return reply_text or fallback
    except Exception as e:
        print(f"[quiz] decline llm error: {e}", flush=True)
        return fallback


async def build_quiz_wrong_guess_message(channel):
    """Generate an in-character wrong-answer acknowledgement without revealing clues."""
    fallback = "Incorrect. Stay sharp and try again."
    if not LLM_ENABLED:
        return fallback

    try:
        selected_figures_str = get_selected_figures_str(getattr(channel, "guild", None))
        llm_messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(selected_figures_str=selected_figures_str),
            },
            {
                "role": "user",
                "content": (
                    "The user guessed wrong in a frame data quiz. "
                    "Write one short in-character acknowledgement that they are not correct yet. "
                    "Do not reveal the answer or any clues. "
                    "Do not mention any specific character, move, input, button, or frame value. "
                    "One sentence only. No emojis. No em dash. ASCII only."
                ),
            },
        ]
        reply_text = await get_llm_response(llm_messages)
        reply_text = _sanitize_quiz_ascii_line(reply_text)
        if _quiz_intro_has_specific_answer_hint(reply_text):
            llm_messages[-1]["content"] = (
                "Rewrite in one sentence as an in-character wrong-answer acknowledgement. "
                "No character names, move names, inputs, buttons, numbers, or frame terms. "
                "No emojis. No em dash. ASCII only."
            )
            reply_text = await get_llm_response(llm_messages)
            reply_text = _sanitize_quiz_ascii_line(reply_text)
            if _quiz_intro_has_specific_answer_hint(reply_text):
                return fallback
        return reply_text or fallback
    except Exception as e:
        print(f"[quiz] wrong-guess llm error: {e}", flush=True)
        return fallback


async def build_quiz_cheating_warning_message(channel):
    """Generate an in-character warning for frame/gif lookup attempts during quiz mode."""
    fallback = "Aiya, caught cheating: no framedata or gif scouting mid-quiz, so drop the scrolls and answer like a warrior."
    if not LLM_ENABLED:
        return fallback

    try:
        selected_figures_str = get_selected_figures_str(getattr(channel, "guild", None))
        llm_messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(selected_figures_str=selected_figures_str),
            },
            {
                "role": "user",
                "content": (
                    "The user tried to request frame data or a gif while a quiz is active. "
                    "Write one short in-character anti-cheat warning that is playful, sharp, and a little aggressive. "
                    "Call out the cheating attempt and tell them to answer the quiz directly from memory. "
                    "Do not reveal any answer clues. "
                    "One sentence only. No emojis. No em dash. ASCII only."
                ),
            },
        ]
        reply_text = await get_llm_response(llm_messages)
        reply_text = _sanitize_quiz_ascii_line(reply_text)
        if _quiz_intro_has_specific_answer_hint(reply_text):
            return fallback
        return reply_text or fallback
    except Exception as e:
        print(f"[quiz] cheating-warning llm error: {e}", flush=True)
        return fallback


async def build_quiz_correct_guess_message(channel):
    """Generate an in-character correct-answer acknowledgement."""
    fallback = "Yes, that is correct."
    if not LLM_ENABLED:
        return fallback

    try:
        selected_figures_str = get_selected_figures_str(getattr(channel, "guild", None))
        llm_messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(selected_figures_str=selected_figures_str),
            },
            {
                "role": "user",
                "content": (
                    "The user guessed correctly in a frame data quiz. "
                    "Write one short in-character acknowledgement that the guess is correct. "
                    "One sentence only. No emojis. No em dash. ASCII only."
                ),
            },
        ]
        reply_text = await get_llm_response(llm_messages)
        reply_text = _sanitize_quiz_ascii_line(reply_text)
        return reply_text or fallback
    except Exception as e:
        print(f"[quiz] correct-guess llm error: {e}", flush=True)
        return fallback


async def classify_quiz_post_answer_choice_intent(channel, user_text):
    """Classify post-wrong-answer choice intent as reveal, guess_again, or none."""
    text = str(user_text or "").strip()
    if not text or not LLM_ENABLED:
        return None

    try:
        selected_figures_str = get_selected_figures_str(getattr(channel, "guild", None))
        llm_messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(selected_figures_str=selected_figures_str),
            },
            {
                "role": "user",
                "content": (
                    "Classify the user's message in a quiz flow after they were told: "
                    "'Try again or give up and find out the answer'. "
                    "Return exactly one token: REVEAL, GUESS, or NONE. "
                    "REVEAL means they want to forfeit/reveal/end this question "
                    "(e.g., give up, i surrender, you win, reveal answer). "
                    "GUESS means they want to continue guessing. "
                    "NONE means unrelated/unclear. "
                    f"Message: {text}"
                ),
            },
        ]
        reply_text = await get_llm_response(llm_messages)
        reply_upper = str(reply_text or "").upper()
        if "REVEAL" in reply_upper:
            return "reveal"
        if "GUESS" in reply_upper:
            return "guess_again"
        return None
    except Exception as e:
        print(f"[quiz] post-answer intent llm error: {e}", flush=True)
        return None


async def classify_quiz_another_question_intent(channel, user_text):
    """Classify another-question follow-up intent as yes, no, or none."""
    text = str(user_text or "").strip()
    if not text or not LLM_ENABLED:
        return None

    try:
        selected_figures_str = get_selected_figures_str(getattr(channel, "guild", None))
        llm_messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(selected_figures_str=selected_figures_str),
            },
            {
                "role": "user",
                "content": (
                    "Classify the user's reply to the question: 'Would you like another question?'. "
                    "Return exactly one token: YES, NO, or NONE. "
                    "YES means they want another quiz question (affirmative/continue). "
                    "NO means they want to end/decline (negative/stop). "
                    "NONE means unclear or unrelated. "
                    f"Message: {text}"
                ),
            },
        ]
        reply_text = await get_llm_response(llm_messages)
        reply_upper = str(reply_text or "").upper()

        token_match = re.search(r"\b(YES|NO|NONE)\b", reply_upper)
        if token_match:
            token = token_match.group(1)
            if token == "YES":
                return "yes"
            if token == "NO":
                return "no"
            return None

        if "YES" in reply_upper:
            return "yes"
        if "NO" in reply_upper:
            return "no"
        return None
    except Exception as e:
        print(f"[quiz] another-question intent llm error: {e}", flush=True)
        return None


def _normalize_quiz_numcmd(text):
    normalized = str(text or "").strip().lower()
    normalized = re.sub(r"[\[\]\(\)\{\}]", " ", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    return re.sub(r"[^a-z0-9>]", "", normalized)


def _quiz_has_explicit_strength(text):
    lowered = str(text or "").lower()
    tokens = re.findall(r"[a-z0-9]+", lowered)
    explicit_tokens = {
        "lp",
        "mp",
        "hp",
        "lk",
        "mk",
        "hk",
        "pp",
        "kk",
        "od",
        "ex",
        "light",
        "medium",
        "heavy",
    }
    if any(token in explicit_tokens for token in tokens):
        return True

    # Alex stance follow-ups like "stance 6p" or "2pp 2lplk" are exact
    # follow-up notations even though they are not regular strength words.
    if re.search(
        r"\b(?:stance|2pp)\s+(?:6p|6|4|lplk|5lplk|2lplk)\b",
        lowered,
    ):
        return True

    compact = re.sub(r"[^a-z0-9>]", "", lowered)
    return bool(re.search(r"(lp|mp|hp|lk|mk|hk|pp|kk)$", compact))


def _quiz_genericize_numcmd_suffix(numcmd):
    value = str(numcmd or "")
    qualifiers = []
    while True:
        matched_suffix = None
        for suffix in ("air", "hold", "bomb", "charged"):
            if value.endswith(suffix):
                matched_suffix = suffix
                break
        if not matched_suffix:
            break
        qualifiers.append(matched_suffix)
        value = value[: -len(matched_suffix)]

    value = re.sub(r"(lp|mp|hp)$", "p", value)
    value = re.sub(r"(lk|mk|hk)$", "k", value)
    value = re.sub(r"pp$", "p", value)
    value = re.sub(r"kk$", "k", value)

    if qualifiers:
        value = f"{value}{''.join(reversed(qualifiers))}"
    return value


def _quiz_numcmd_variant_info(numcmd):
    normalized = _normalize_quiz_numcmd(numcmd)
    if not normalized:
        return None

    main_segment = ""
    for segment in normalized.split(">"):
        if segment:
            main_segment = segment
            break
    if not main_segment:
        return None

    family_tags = []
    while True:
        matched_suffix = None
        for suffix in ("air", "hold", "bomb", "charged"):
            if main_segment.endswith(suffix):
                matched_suffix = suffix
                break
        if not matched_suffix:
            break
        family_tags.append(matched_suffix)
        main_segment = main_segment[: -len(matched_suffix)]

    if not main_segment:
        return None

    family_suffix = f"|{'|'.join(reversed(family_tags))}" if family_tags else ""

    if main_segment.endswith("pp"):
        return {
            "family": f"{main_segment[:-2]}p{family_suffix}",
            "variant": "od",
            "channel": "p",
        }
    if main_segment.endswith("kk"):
        return {
            "family": f"{main_segment[:-2]}k{family_suffix}",
            "variant": "od",
            "channel": "k",
        }

    if main_segment.endswith(("lp", "mp", "hp")):
        return {
            "family": f"{main_segment[:-2]}p{family_suffix}",
            "variant": "specific",
            "channel": "p",
        }
    if main_segment.endswith(("lk", "mk", "hk")):
        return {
            "family": f"{main_segment[:-2]}k{family_suffix}",
            "variant": "specific",
            "channel": "k",
        }

    if main_segment.endswith("p"):
        return {
            "family": f"{main_segment}{family_suffix}",
            "variant": "generic",
            "channel": "p",
        }
    if main_segment.endswith("k"):
        return {
            "family": f"{main_segment}{family_suffix}",
            "variant": "generic",
            "channel": "k",
        }

    return None


def _quiz_numcmd_family_profile(char_key, numcmd):
    info = _quiz_numcmd_variant_info(numcmd)
    if not info:
        return None

    family = info["family"]
    profile = {
        "family": family,
        "generic": 0,
        "od": 0,
        "specific": 0,
        "total": 0,
    }
    seen_numcmds = set()

    for row in FRAME_DATA.get(char_key, []):
        row_numcmd = str(row.get("numCmd", "")).strip().lower()
        if not row_numcmd or row_numcmd in seen_numcmds:
            continue

        row_info = _quiz_numcmd_variant_info(row_numcmd)
        if not row_info or row_info.get("family") != family:
            continue

        seen_numcmds.add(row_numcmd)
        row_variant = row_info.get("variant")
        if row_variant in ("generic", "od", "specific"):
            profile[row_variant] += 1
            profile["total"] += 1

    return profile


def _quiz_correct_row_allows_generic_strength(char_key, correct_numcmd):
    info = _quiz_numcmd_variant_info(correct_numcmd)
    if not info:
        return False

    profile = _quiz_numcmd_family_profile(char_key, correct_numcmd)
    if not profile:
        return False

    is_regular_od_only_family = (
        profile.get("specific") == 0
        and profile.get("generic", 0) >= 1
        and profile.get("od", 0) >= 1
    )
    return is_regular_od_only_family and info.get("variant") == "generic"


def _quiz_is_generic_numcmd_notation(text):
    compact = _normalize_quiz_numcmd(text)
    return bool(re.fullmatch(r"\d+[pk]", compact))


def _quiz_is_exact_move_name_answer(move_text, row):
    query_name = _normalize_quiz_name(move_text)
    if not query_name:
        return False
    move_name = _normalize_quiz_name((row or {}).get("moveName", ""))
    return bool(move_name) and query_name == move_name


def _quiz_numcmd_variants(numcmd, include_generic=False):
    normalized = _normalize_quiz_numcmd(numcmd)
    if not normalized:
        return set()

    variants = {normalized}
    if ">" in normalized:
        parts = [segment for segment in normalized.split(">") if segment]
        variants.update(parts)
        if parts:
            variants.add(parts[-1])

    if include_generic:
        generic_variants = {
            _quiz_genericize_numcmd_suffix(value)
            for value in list(variants)
            if value
        }
        variants.update(value for value in generic_variants if value)

    return variants


def _quiz_genericize_combo_numcmd(numcmd):
    normalized = _normalize_quiz_numcmd(numcmd)
    if not normalized:
        return ""
    parts = [part for part in normalized.split(">") if part]
    if not parts:
        return normalized
    return ">".join(_quiz_genericize_numcmd_suffix(part) for part in parts)


def _quiz_row_numcmd_matches_correct(row, correct_numcmd, allow_generic=False):
    candidate_numcmd = str((row or {}).get("numCmd", "")).strip().lower()
    if not candidate_numcmd:
        return False

    candidate_norm = _normalize_quiz_numcmd(candidate_numcmd)
    correct_norm = _normalize_quiz_numcmd(correct_numcmd)
    if ">" in correct_norm or ">" in candidate_norm:
        if candidate_norm == correct_norm:
            return True
        if not allow_generic:
            return False
        return _quiz_genericize_combo_numcmd(candidate_norm) == _quiz_genericize_combo_numcmd(correct_norm)

    candidate_strict = _quiz_numcmd_variants(candidate_numcmd, include_generic=False)
    correct_strict = _quiz_numcmd_variants(correct_numcmd, include_generic=False)
    if candidate_strict & correct_strict:
        return True

    if not allow_generic:
        return False

    candidate_generic = _quiz_numcmd_variants(candidate_numcmd, include_generic=True)
    correct_generic = _quiz_numcmd_variants(correct_numcmd, include_generic=True)
    return bool(candidate_generic & correct_generic)


def _normalize_quiz_name(text):
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def _extract_char_and_move_from_text(text):
    """
    Try to parse (char_key, move_text) from a user answer string.
    Tries progressively longer word prefixes for the character name.
    Returns (char_key, move_text) or (None, None).
    """
    words = text.strip().lower().split()
    if not words:
        return None, None
    for prefix_len in range(min(3, len(words)), 0, -1):
        char_candidate = " ".join(words[:prefix_len])
        char_key = resolve_character_key(char_candidate)
        if char_key:
            move_text = " ".join(words[prefix_len:]).strip()
            return char_key, move_text
    return None, None


def check_quiz_answer(quiz_state, text):
    """
    Return True if `text` is a correct answer to the active quiz round.
    Checks character match, then uses lookup_frame_data to match the move.
    """
    correct_char = quiz_state["char_key"]
    correct_numcmd = quiz_state["numcmd"]
    correct_row = quiz_state.get("row") or {}
    if not correct_numcmd:
        return False

    def quiz_row_is_ca_variant(row):
        move_name = str((row or {}).get("moveName", "")).lower()
        cmn_name = str((row or {}).get("cmnName", "")).lower()
        num_cmd = str((row or {}).get("numCmd", "")).lower()
        return (
            "critical art" in move_name
            or "critical art" in cmn_name
            or bool(re.search(r"\(\s*ca\s*\)", num_cmd))
        )

    char_key, move_text = _extract_char_and_move_from_text(text)
    if not char_key or not move_text:
        return False
    if char_key != correct_char:
        return False

    user_move_compact = _normalize_quiz_numcmd(move_text)
    user_has_explicit_strength = _quiz_has_explicit_strength(move_text)
    allow_generic_strength = (
        not user_has_explicit_strength
        and _quiz_correct_row_allows_generic_strength(correct_char, correct_numcmd)
    )
    if _quiz_is_generic_numcmd_notation(move_text) and not allow_generic_strength:
        return False

    if user_move_compact:
        direct_user_row = {"numCmd": user_move_compact}
        if _quiz_row_numcmd_matches_correct(
            direct_user_row,
            correct_numcmd,
            allow_generic=allow_generic_strength,
        ):
            return True

    candidate_rows = []

    direct_row = lookup_frame_data(char_key, move_text)
    if direct_row is not None:
        candidate_rows.append(direct_row)

    if quiz_row_is_ca_variant(correct_row) and re.search(r"\b(?:ca|critical(?:\s+art)?)\b", move_text):
        ca_row = lookup_frame_data(char_key, "critical art")
        if ca_row is not None and ca_row not in candidate_rows:
            candidate_rows.append(ca_row)

    if re.search(r"\b(tc|target\s+combo|targetcombo)\b", move_text):
        parser_query = f"{char_key} {move_text}".strip().lower()
        parser_payload = find_moves_in_text(parser_query)
        parsed_rows = parser_payload.get("rows", [])
        for parsed_row in parsed_rows:
            row_char = resolve_character_key(str(parsed_row.get("char_name", "")))
            if row_char != char_key:
                continue
            if parsed_row not in candidate_rows:
                candidate_rows.append(parsed_row)

    for row in candidate_rows:
        if _quiz_row_numcmd_matches_correct(row, correct_numcmd, allow_generic=False):
            if not user_has_explicit_strength:
                row_profile = _quiz_numcmd_family_profile(correct_char, row.get("numCmd", ""))
                if row_profile and row_profile.get("specific", 0) > 0:
                    if not _quiz_is_exact_move_name_answer(move_text, row):
                        continue
            return True

        if _quiz_row_numcmd_matches_correct(
            row,
            correct_numcmd,
            allow_generic=allow_generic_strength,
        ):
            return True
    # Fuzzy match fallback for misspellings in move names/common names.
    user_move_name = str(move_text or "").strip().lower()
    if not user_move_name:
        return False

    fuzzy_name_candidates = []
    for row in FRAME_DATA.get(char_key, []):
        if not _quiz_row_has_data(row):
            continue
        if not _quiz_row_allowed_for_mode(row, quiz_state.get("mode", "hard")):
            continue
        move_name = str(row.get("moveName", "")).strip().lower()
        cmn_name = str(row.get("cmnName", "")).strip().lower()
        for candidate_name in (move_name, cmn_name):
            if len(candidate_name) < 4:
                continue
            fuzzy_name_candidates.append((candidate_name, row))

    if fuzzy_name_candidates:
        fuzzy_choices = [name for name, _ in fuzzy_name_candidates]
        close_names = difflib.get_close_matches(user_move_name, fuzzy_choices, n=2, cutoff=0.84)
        for close_name in close_names:
            for candidate_name, row in fuzzy_name_candidates:
                if candidate_name != close_name:
                    continue
                if _quiz_row_numcmd_matches_correct(
                    row,
                    correct_numcmd,
                    allow_generic=allow_generic_strength,
                ):
                    return True
    return False


def _quiz_clean_display_name(name):
    cleaned = re.sub(r"\s+", " ", str(name or "")).strip()
    return cleaned or "Unknown"


def _quiz_user_display_name(user):
    return _quiz_clean_display_name(
        getattr(user, "display_name", None) or getattr(user, "name", None)
    )


def _quiz_score_line(name, points):
    safe_name = _quiz_clean_display_name(name)
    try:
        safe_points = int(points)
    except Exception:
        safe_points = 0
    return f"{safe_name}- {safe_points}"


def _format_quiz_scores(scores, score_names=None):
    """Format leaderboard lines as `username- points` sorted by highest points."""
    if not scores:
        return "No points scored."

    score_names = score_names or {}

    def sort_key(item):
        uid, pts = item
        try:
            point_value = int(pts)
        except Exception:
            point_value = 0
        display = _quiz_clean_display_name(score_names.get(uid, f"User {uid}"))
        return (-point_value, display.lower())

    lines = []
    for uid, pts in sorted(scores.items(), key=sort_key):
        display = _quiz_clean_display_name(score_names.get(uid, f"User {uid}"))
        lines.append(_quiz_score_line(display, pts))
    return "\n".join(lines)


def _quiz_build_crown_line(scores, score_names=None):
    """Build an in-character crown line for the highest scorer(s)."""
    if not scores:
        return "No one scored this session, so the crown remains unclaimed."

    score_names = score_names or {}
    normalized_points = {}
    for uid, pts in scores.items():
        try:
            normalized_points[uid] = int(pts)
        except Exception:
            normalized_points[uid] = 0

    top_points = max(normalized_points.values())
    winners = [uid for uid, pts in normalized_points.items() if pts == top_points]
    winner_names = [
        _quiz_clean_display_name(score_names.get(uid, f"User {uid}"))
        for uid in winners
    ]

    if len(winner_names) == 1:
        return (
            f"By decree of Bub, {winner_names[0]} takes the crown with "
            f"{top_points} point{'s' if top_points != 1 else ''}."
        )

    joined_winners = ", ".join(winner_names)
    return (
        f"By decree of Bub, the crown is shared by {joined_winners} at "
        f"{top_points} point{'s' if top_points != 1 else ''} each."
    )


def _quiz_unique_rows_for_char(char_key, asked=None, mode="hard"):
    """Return mode-filtered rows whose moveName is unique within the character sheet."""
    mode_key = _quiz_normalize_mode(mode)
    asked = asked or set()
    rows = FRAME_DATA.get(char_key, [])
    if not rows:
        return []

    name_counts = {}
    for row in rows:
        if not _quiz_row_has_data(row):
            continue
        if not _quiz_row_allowed_for_mode(row, mode_key):
            continue
        name_key = _normalize_quiz_name(row.get("moveName", ""))
        if not name_key:
            continue
        name_counts[name_key] = name_counts.get(name_key, 0) + 1

    unique_rows = []
    for row in rows:
        if not _quiz_row_has_data(row):
            continue
        if not _quiz_row_allowed_for_mode(row, mode_key):
            continue
        numcmd = str(row.get("numCmd", "")).strip().lower()
        if (char_key, numcmd) in asked:
            continue
        name_key = _normalize_quiz_name(row.get("moveName", ""))
        if name_counts.get(name_key, 0) == 1:
            unique_rows.append(row)

    return unique_rows


def pick_quiz_move(asked=None, mode="hard"):
    """
    Pick a random (char_key, row) from FRAME_DATA suitable for a quiz question.
    `asked` is an optional set of (char_key, numcmd) tuples already used this session.
    """
    mode_key = _quiz_normalize_mode(mode)
    asked = asked or set()
    if not FRAME_DATA:
        return None, None
    char_keys = [k for k, rows in FRAME_DATA.items() if rows]
    if not char_keys:
        return None, None

    # Try up to 30 random picks, prioritizing rows with unique move names.
    for _ in range(30):
        char_key = random.choice(char_keys)
        rows = _quiz_unique_rows_for_char(char_key, asked=asked, mode=mode_key)
        if rows:
            return char_key, random.choice(rows)

    # Fallback 1: unique move-name rows (ignore asked dedup)
    random.shuffle(char_keys)
    for char_key in char_keys:
        rows = _quiz_unique_rows_for_char(char_key, asked=set(), mode=mode_key)
        if rows:
            return char_key, random.choice(rows)

    # Fallback 2: any valid row
    random.shuffle(char_keys)
    for char_key in char_keys:
        rows = [
            r
            for r in FRAME_DATA[char_key]
            if _quiz_row_has_data(r) and _quiz_row_allowed_for_mode(r, mode_key)
        ]
        if rows:
            return char_key, random.choice(rows)
    return None, None


async def start_quiz(
    message,
    mode="hard",
    session_scores=None,
    session_score_names=None,
    session_round=1,
    session_owner_user_id=None,
    session_message_ids=None,
):
    """Initialize and send one quiz question in the channel."""
    mode_key = _quiz_normalize_mode(mode)
    channel_id = message.channel.id
    if QUIZ_START_LOCK.locked():
        try:
            await message.reply("A quiz is already being prepared. Please wait a moment.")
        except Exception as e:
            if is_deleted_message_reference_error(e):
                try:
                    await message.channel.send("A quiz is already being prepared. Please wait a moment.")
                except Exception as send_error:
                    print(f"[quiz] locked-start send error: {send_error}", flush=True)
            else:
                print(f"[quiz] locked-start reply error: {e}", flush=True)
        return

    async with QUIZ_START_LOCK:
        if channel_id in ACTIVE_QUIZZES:
            try:
                await message.reply(
                    "A quiz is already running. Mention me and say `stop quiz` to end it."
                )
            except Exception as e:
                print(f"[quiz] already-running reply error: {e}", flush=True)
            return

        char_key, row = pick_quiz_move(mode=mode_key)
        if not char_key:
            try:
                await message.reply(f"No frame data is available for {mode_key} mode.")
            except Exception as e:
                print(f"[quiz] no-data reply error: {e}", flush=True)
            return

        normalized_scores = {}
        if isinstance(session_scores, dict):
            for raw_uid, raw_points in session_scores.items():
                try:
                    uid = int(raw_uid)
                    pts = int(raw_points)
                except Exception:
                    continue
                if pts < 0:
                    continue
                normalized_scores[uid] = pts

        normalized_score_names = {}
        if isinstance(session_score_names, dict):
            for raw_uid, raw_name in session_score_names.items():
                try:
                    uid = int(raw_uid)
                except Exception:
                    continue
                normalized_score_names[uid] = _quiz_clean_display_name(raw_name)

        for uid in normalized_scores.keys():
            if uid not in normalized_score_names:
                normalized_score_names[uid] = _quiz_clean_display_name(f"User {uid}")

        try:
            round_num = max(1, int(session_round))
        except Exception:
            round_num = 1

        try:
            owner_user_id = int(session_owner_user_id)
        except Exception:
            owner_user_id = int(message.author.id)

        normalized_message_ids = _quiz_normalize_message_ids(session_message_ids)

        numcmd = str(row.get("numCmd", "")).strip().lower()
        quiz_state = {
            "channel_id": channel_id,
            "owner_user_id": owner_user_id,
            "total_rounds": 1,
            "round": round_num,
            "scores": normalized_scores,
            "score_names": normalized_score_names,
            "char_key": char_key,
            "numcmd": numcmd,
            "row": row,
            "mode": mode_key,
            "answered": False,
            "awaiting_choice": False,
            "asked": {(char_key, numcmd)},
            "message_ids": normalized_message_ids,
        }

        answer_char = str(row.get("char_name", char_key.capitalize())).strip()
        answer_move = str(row.get("moveName", "?")).strip()
        answer_numcmd = str(row.get("numCmd", "?")).strip()
        print(
            f"[quiz] answer-key channel_id={channel_id} round={round_num} mode={mode_key} "
            f"char={answer_char} move={answer_move} numcmd={answer_numcmd}",
            flush=True,
        )

        ACTIVE_QUIZZES[channel_id] = quiz_state
        QUIZ_PENDING_ANOTHER.pop(channel_id, None)
        _quiz_cancel_pending_another_timeout(channel_id)
        QUIZ_PENDING_MODE.pop(channel_id, None)

        thinking_message = await _quiz_send_thinking_message(message)

        question_text, question_embed = await build_quiz_question_message(
            message.channel,
            round_num,
            1,
            row,
            mode=mode_key,
        )
        sent = await _quiz_publish_from_placeholder(
            message.channel,
            thinking_message,
            question_text,
            embed=question_embed,
        )
        if sent is None:
            ACTIVE_QUIZZES.pop(channel_id, None)
            return

        _quiz_track_message_id(quiz_state, getattr(sent, "id", None))


async def prompt_quiz_mode_selection(
    message,
    session_mode=None,
    session_scores=None,
    session_score_names=None,
    session_round=1,
    session_owner_user_id=None,
    session_message_ids=None,
):
    """Prompt user to specify quiz difficulty and track pending mode selection."""
    channel_id = message.channel.id
    prompt_text = (
        "Specify quiz difficulty: `easy`, `medium`, or `hard`. "
        "Easy = normals only. Medium = normals + specials. Hard = everything."
    )

    stored_mode = str(session_mode or "").strip().lower()
    if stored_mode not in QUIZ_VALID_MODES:
        stored_mode = None

    try:
        owner_user_id = int(session_owner_user_id)
    except Exception:
        owner_user_id = int(message.author.id)

    normalized_message_ids = _quiz_normalize_message_ids(session_message_ids)

    pending_payload = {
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "message_id": None,
        "owner_user_id": owner_user_id,
        "mode": stored_mode,
        "scores": dict(session_scores or {}),
        "score_names": dict(session_score_names or {}),
        "round": session_round,
        "message_ids": normalized_message_ids,
    }

    try:
        sent = await message.reply(prompt_text)
        pending_payload["message_id"] = getattr(sent, "id", None)
        QUIZ_PENDING_MODE[channel_id] = pending_payload
    except Exception as e:
        if is_deleted_message_reference_error(e):
            sent = await message.channel.send(prompt_text)
            pending_payload["message_id"] = getattr(sent, "id", None)
            QUIZ_PENDING_MODE[channel_id] = pending_payload
        else:
            print(f"[quiz] mode-prompt send error: {e}", flush=True)


async def stop_quiz(message):
    """Cancel the active quiz in the channel and reveal the current answer."""
    channel_id = message.channel.id
    quiz = ACTIVE_QUIZZES.pop(channel_id, None)
    if not quiz:
        try:
            await message.reply("No quiz is running right now.")
        except Exception as e:
            print(f"[quiz] stop-no-quiz reply error: {e}", flush=True)
        return

    row = quiz["row"]
    char_key = quiz["char_key"]
    char_display = str(row.get("char_name", char_key.capitalize())).strip()
    move_name = str(row.get("moveName", "?")).strip()
    num_cmd = str(row.get("numCmd", "?")).strip()
    reply_text = (
        f"Quiz ended. The answer was **{char_display}'s {move_name} ({num_cmd})**.\n"
        "Would you like another question?"
    )
    try:
        sent = await message.reply(reply_text)
        QUIZ_PENDING_ANOTHER[channel_id] = {
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "message_id": getattr(sent, "id", None),
            "mode": quiz.get("mode", "hard"),
            "owner_user_id": quiz.get("owner_user_id"),
            "scores": dict(quiz.get("scores") or {}),
            "score_names": dict(quiz.get("score_names") or {}),
            "round": quiz.get("round", 1),
            "message_ids": _quiz_build_message_history(quiz, getattr(sent, "id", None)),
        }
        _quiz_schedule_pending_another_timeout(channel_id, message.channel)
    except Exception as e:
        if is_deleted_message_reference_error(e):
            sent = await message.channel.send(reply_text)
            QUIZ_PENDING_ANOTHER[channel_id] = {
                "created_at": datetime.datetime.now(datetime.timezone.utc),
                "message_id": getattr(sent, "id", None),
                "mode": quiz.get("mode", "hard"),
                "owner_user_id": quiz.get("owner_user_id"),
                "scores": dict(quiz.get("scores") or {}),
                "score_names": dict(quiz.get("score_names") or {}),
                "round": quiz.get("round", 1),
                "message_ids": _quiz_build_message_history(quiz, getattr(sent, "id", None)),
            }
            _quiz_schedule_pending_another_timeout(channel_id, message.channel)
        else:
            print(f"[quiz] stop send error: {e}", flush=True)


def _is_reply_to_quiz_msg(message):
    """True if the message replies to any tracked quiz-related bot message."""
    ref = getattr(message, "reference", None)
    if not ref:
        return False
    channel_id = message.channel.id
    quiz = ACTIVE_QUIZZES.get(channel_id)
    if not quiz:
        return False

    quiz_message_ids = quiz.get("message_ids")
    if isinstance(quiz_message_ids, list):
        try:
            ref_id = int(ref.message_id)
        except Exception:
            ref_id = ref.message_id
        if ref_id in quiz_message_ids:
            return True

    last_id = quiz.get("last_message_id")
    return last_id is not None and ref.message_id == last_id


def _quiz_track_message_id(quiz_state, message_id):
    """Track quiz-related bot message IDs so replies stay addressable."""
    if not isinstance(quiz_state, dict) or not message_id:
        return

    try:
        normalized_id = int(message_id)
    except Exception:
        return

    message_ids = quiz_state.get("message_ids")
    if not isinstance(message_ids, list):
        message_ids = []

    if normalized_id not in message_ids:
        message_ids.append(normalized_id)
    if len(message_ids) > 40:
        message_ids = message_ids[-40:]

    quiz_state["message_ids"] = message_ids
    quiz_state["last_message_id"] = normalized_id


def _quiz_normalize_message_ids(raw_message_ids):
    """Normalize and dedupe message id history while preserving order."""
    temp_state = {}
    if isinstance(raw_message_ids, list):
        for raw_id in raw_message_ids:
            _quiz_track_message_id(temp_state, raw_id)
    return list(temp_state.get("message_ids") or [])


def _quiz_build_message_history(state, appended_message_id=None):
    """Build message-id history from existing state plus an optional new message id."""
    temp_state = {
        "message_ids": _quiz_normalize_message_ids(
            (state or {}).get("message_ids", []) if isinstance(state, dict) else []
        )
    }
    if isinstance(state, dict):
        _quiz_track_message_id(temp_state, state.get("last_message_id"))
    _quiz_track_message_id(temp_state, appended_message_id)
    return list(temp_state.get("message_ids") or [])


def _is_reply_to_quiz_followup_msg(message):
    """True if message replies to the most recent 'another question' prompt."""
    ref = getattr(message, "reference", None)
    if not ref:
        return False
    pending = QUIZ_PENDING_ANOTHER.get(message.channel.id)
    if not pending:
        return False
    pending_id = pending.get("message_id")
    return pending_id is not None and ref.message_id == pending_id


def _is_reply_to_quiz_mode_prompt(message):
    """True if message replies to the most recent difficulty prompt."""
    ref = getattr(message, "reference", None)
    if not ref:
        return False
    pending = QUIZ_PENDING_MODE.get(message.channel.id)
    if not pending:
        return False
    pending_id = pending.get("message_id")
    return pending_id is not None and ref.message_id == pending_id


def _quiz_cancel_pending_another_timeout(channel_id):
    task = QUIZ_PENDING_ANOTHER_TIMEOUT_TASKS.pop(channel_id, None)
    if task and not task.done():
        task.cancel()


def _quiz_timeout_expiry_message(pending_state):
    scores = dict((pending_state or {}).get("scores") or {})
    score_names = dict((pending_state or {}).get("score_names") or {})
    crown_line = _quiz_build_crown_line(scores, score_names)
    score_text = _format_quiz_scores(scores, score_names)
    return (
        "By decree of Bub, the 5-minute window for another question has closed.\n"
        f"{crown_line}\n"
        f"{score_text}"
    )


def _quiz_schedule_pending_another_timeout(channel_id, channel):
    _quiz_cancel_pending_another_timeout(channel_id)

    async def _timeout_worker():
        try:
            await asyncio.sleep(QUIZ_PENDING_ANOTHER_TTL_SECONDS)
            pending = QUIZ_PENDING_ANOTHER.get(channel_id)
            if not pending:
                return

            created_at = pending.get("created_at")
            if created_at:
                age = (datetime.datetime.now(datetime.timezone.utc) - created_at).total_seconds()
                remaining = QUIZ_PENDING_ANOTHER_TTL_SECONDS - age
                if remaining > 0:
                    await asyncio.sleep(remaining)

            pending = QUIZ_PENDING_ANOTHER.get(channel_id)
            if not pending:
                return

            created_at = pending.get("created_at")
            if created_at:
                age = (datetime.datetime.now(datetime.timezone.utc) - created_at).total_seconds()
                if age <= QUIZ_PENDING_ANOTHER_TTL_SECONDS:
                    return

            expired_state = QUIZ_PENDING_ANOTHER.pop(channel_id, None)
            if not expired_state:
                return

            expiry_text = _quiz_timeout_expiry_message(expired_state)
            try:
                await channel.send(expiry_text)
            except Exception as send_error:
                print(f"[quiz] pending-expiry send error: {send_error}", flush=True)
        except asyncio.CancelledError:
            return
        finally:
            tracked_task = QUIZ_PENDING_ANOTHER_TIMEOUT_TASKS.get(channel_id)
            if tracked_task is asyncio.current_task():
                QUIZ_PENDING_ANOTHER_TIMEOUT_TASKS.pop(channel_id, None)

    QUIZ_PENDING_ANOTHER_TIMEOUT_TASKS[channel_id] = asyncio.create_task(_timeout_worker())


def _quiz_pending_another_active(channel_id):
    pending = QUIZ_PENDING_ANOTHER.get(channel_id)
    if not pending:
        return False
    created_at = pending.get("created_at")
    if not created_at:
        QUIZ_PENDING_ANOTHER.pop(channel_id, None)
        _quiz_cancel_pending_another_timeout(channel_id)
        return False
    age = (datetime.datetime.now(datetime.timezone.utc) - created_at).total_seconds()
    if age > QUIZ_PENDING_ANOTHER_TTL_SECONDS:
        expired_state = QUIZ_PENDING_ANOTHER.pop(channel_id, None)
        _quiz_cancel_pending_another_timeout(channel_id)
        if expired_state:
            return False
        return False
    return True


def _quiz_pending_mode_active(channel_id):
    pending = QUIZ_PENDING_MODE.get(channel_id)
    if not pending:
        return False
    created_at = pending.get("created_at")
    if not created_at:
        QUIZ_PENDING_MODE.pop(channel_id, None)
        return False
    age = (datetime.datetime.now(datetime.timezone.utc) - created_at).total_seconds()
    if age > QUIZ_PENDING_MODE_TTL_SECONDS:
        QUIZ_PENDING_MODE.pop(channel_id, None)
        return False
    return True


def _quiz_answer_display(quiz):
    row = quiz["row"]
    char_key = quiz["char_key"]
    char_display = str(row.get("char_name", char_key.capitalize())).strip()
    move_name = str(row.get("moveName", "?")).strip()
    num_cmd = str(row.get("numCmd", "?")).strip()
    return char_display, move_name, num_cmd


def _quiz_owner_user_id(state):
    if not isinstance(state, dict):
        return None
    raw_owner = state.get("owner_user_id")
    try:
        return int(raw_owner)
    except Exception:
        return None


def _quiz_user_can_end(state, user_id):
    # Quiz ending is communal: any participant can end the session.
    return True


def _quiz_owner_only_end_message(state):
    owner_id = _quiz_owner_user_id(state)
    if owner_id is None:
        return "Only the user who started this quiz can end it."
    return f"Only <@{owner_id}> can end this quiz."


def _quiz_leaderboard_file_path():
    path_text = str(QUIZ_LEADERBOARD_FILE or "quiz_leaderboard.json").strip()
    if os.path.isabs(path_text):
        return path_text
    return os.path.join(os.path.dirname(__file__), path_text)


def load_quiz_leaderboard():
    """Load persistent global quiz leaderboard from disk."""
    global QUIZ_GLOBAL_LEADERBOARD, QUIZ_GLOBAL_LEADERBOARD_NAMES

    file_path = _quiz_leaderboard_file_path()
    if not os.path.exists(file_path):
        QUIZ_GLOBAL_LEADERBOARD = {}
        QUIZ_GLOBAL_LEADERBOARD_NAMES = {}
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        print(f"[quiz] leaderboard load error: {e}", flush=True)
        QUIZ_GLOBAL_LEADERBOARD = {}
        QUIZ_GLOBAL_LEADERBOARD_NAMES = {}
        return

    if not isinstance(payload, dict):
        print("[quiz] leaderboard load warning: payload is not an object", flush=True)
        QUIZ_GLOBAL_LEADERBOARD = {}
        QUIZ_GLOBAL_LEADERBOARD_NAMES = {}
        return

    loaded_scores = {}
    loaded_names = {}
    for raw_uid, raw_pts in dict(payload.get("scores") or {}).items():
        try:
            uid = int(raw_uid)
            pts = int(raw_pts)
        except Exception:
            continue
        if pts < 0:
            continue
        loaded_scores[uid] = pts

    for raw_uid, raw_name in dict(payload.get("score_names") or {}).items():
        try:
            uid = int(raw_uid)
        except Exception:
            continue
        loaded_names[uid] = _quiz_clean_display_name(raw_name)

    for uid in loaded_scores.keys():
        if uid not in loaded_names:
            loaded_names[uid] = _quiz_clean_display_name(f"User {uid}")

    QUIZ_GLOBAL_LEADERBOARD = loaded_scores
    QUIZ_GLOBAL_LEADERBOARD_NAMES = loaded_names


def save_quiz_leaderboard():
    """Persist global quiz leaderboard to disk."""
    file_path = _quiz_leaderboard_file_path()
    payload = {
        "version": 1,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scores": {str(uid): int(points) for uid, points in QUIZ_GLOBAL_LEADERBOARD.items()},
        "score_names": {
            str(uid): _quiz_clean_display_name(name)
            for uid, name in QUIZ_GLOBAL_LEADERBOARD_NAMES.items()
        },
    }

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, indent=2, sort_keys=True)
    except Exception as e:
        print(f"[quiz] leaderboard save error: {e}", flush=True)


def _quiz_extract_leaderboard_top_limit(text, default=10, maximum=25):
    match = QUIZ_LEADERBOARD_TOP_RE.search(str(text or ""))
    if not match:
        return default
    try:
        parsed = int(match.group(1))
    except Exception:
        return default
    return max(1, min(maximum, parsed))


def _quiz_is_leaderboard_request(text):
    return bool(QUIZ_LEADERBOARD_REQUEST_RE.search(str(text or "")))


def _quiz_format_global_leaderboard_reply(limit=10):
    scores = dict(QUIZ_GLOBAL_LEADERBOARD)
    names = dict(QUIZ_GLOBAL_LEADERBOARD_NAMES)
    if not scores:
        return "No global quiz wins recorded yet. Win one round and claim your first point."

    sorted_items = sorted(
        scores.items(),
        key=lambda item: (
            -int(item[1]),
            _quiz_clean_display_name(names.get(item[0], f"User {item[0]}")).lower(),
        ),
    )
    top_items = sorted_items[: max(1, int(limit))]
    top_scores = {uid: pts for uid, pts in top_items}
    score_block = _format_quiz_scores(top_scores, names)
    top_uid, top_points = top_items[0]
    top_name = _quiz_clean_display_name(names.get(top_uid, f"User {top_uid}"))
    return (
        f"Global Quiz Leaderboard (Top {len(top_items)}):\n"
        f"{score_block}\n"
        f"Top scorer right now: {top_name} with {top_points} point{'s' if int(top_points) != 1 else ''}."
    )


async def _quiz_record_global_win(user_id, display_name, points=1):
    """Record lifetime quiz points for a user and persist leaderboard."""
    try:
        uid = int(user_id)
        delta = int(points)
    except Exception:
        return
    if delta <= 0:
        return

    async with QUIZ_LEADERBOARD_LOCK:
        current_points = int(QUIZ_GLOBAL_LEADERBOARD.get(uid, 0))
        QUIZ_GLOBAL_LEADERBOARD[uid] = current_points + delta
        QUIZ_GLOBAL_LEADERBOARD_NAMES[uid] = _quiz_clean_display_name(display_name)
        save_quiz_leaderboard()


async def handle_quiz_post_answer_choice(message):
    """Handle follow-up choice after a wrong guess prompt."""
    channel_id = message.channel.id
    quiz = ACTIVE_QUIZZES.get(channel_id)
    if not quiz or not quiz.get("awaiting_choice"):
        return False

    text = strip_discord_mentions(message.content or "").strip().lower()
    if not text:
        return False

    wants_guess_again = bool(QUIZ_GUESS_AGAIN_RE.search(text))
    wants_reveal = bool(QUIZ_REVEAL_END_RE.search(text))

    if not wants_guess_again and not wants_reveal:
        inferred_intent = await classify_quiz_post_answer_choice_intent(message.channel, text)
        if inferred_intent == "guess_again":
            wants_guess_again = True
        elif inferred_intent == "reveal":
            wants_reveal = True

    if wants_guess_again:
        quiz["awaiting_choice"] = False
        try:
            sent = await message.reply("Guess again.")
            _quiz_track_message_id(quiz, getattr(sent, "id", None))
        except Exception as e:
            if is_deleted_message_reference_error(e):
                sent = await message.channel.send("Guess again.")
                _quiz_track_message_id(quiz, getattr(sent, "id", None))
            else:
                print(f"[quiz] guess-again reply error: {e}", flush=True)
        return True

    if wants_reveal:
        if not _quiz_user_can_end(quiz, message.author.id):
            deny_text = _quiz_owner_only_end_message(quiz)
            try:
                sent = await message.reply(deny_text)
                _quiz_track_message_id(quiz, getattr(sent, "id", None))
            except Exception as e:
                if is_deleted_message_reference_error(e):
                    sent = await message.channel.send(deny_text)
                    _quiz_track_message_id(quiz, getattr(sent, "id", None))
                else:
                    print(f"[quiz] owner-only reveal reply error: {e}", flush=True)
            return True

        ACTIVE_QUIZZES.pop(channel_id, None)
        char_display, move_name, num_cmd = _quiz_answer_display(quiz)
        score_text = _format_quiz_scores(
            dict(quiz.get("scores") or {}),
            dict(quiz.get("score_names") or {}),
        )
        reply_text = (
            f"The answer was **{char_display}'s {move_name} ({num_cmd})**.\n"
            f"{score_text}\n"
            "Would you like another question?"
        )
        try:
            sent = await message.reply(reply_text)
            QUIZ_PENDING_ANOTHER[channel_id] = {
                "created_at": datetime.datetime.now(datetime.timezone.utc),
                "message_id": getattr(sent, "id", None),
                "mode": quiz.get("mode", "hard"),
                "owner_user_id": quiz.get("owner_user_id"),
                "scores": dict(quiz.get("scores") or {}),
                "score_names": dict(quiz.get("score_names") or {}),
                "round": quiz.get("round", 1),
                "message_ids": _quiz_build_message_history(quiz, getattr(sent, "id", None)),
            }
            _quiz_schedule_pending_another_timeout(channel_id, message.channel)
        except Exception as e:
            if is_deleted_message_reference_error(e):
                sent = await message.channel.send(reply_text)
                QUIZ_PENDING_ANOTHER[channel_id] = {
                    "created_at": datetime.datetime.now(datetime.timezone.utc),
                    "message_id": getattr(sent, "id", None),
                    "mode": quiz.get("mode", "hard"),
                    "owner_user_id": quiz.get("owner_user_id"),
                    "scores": dict(quiz.get("scores") or {}),
                    "score_names": dict(quiz.get("score_names") or {}),
                    "round": quiz.get("round", 1),
                    "message_ids": _quiz_build_message_history(quiz, getattr(sent, "id", None)),
                }
                _quiz_schedule_pending_another_timeout(channel_id, message.channel)
            else:
                print(f"[quiz] reveal-end reply error: {e}", flush=True)
        return True

    return False


async def handle_quiz_answer(message):
    """
    Process a message as a potential quiz answer.
    Returns True if message was handled as a quiz answer attempt.
    Returns False when message is not a usable answer format.
    """
    channel_id = message.channel.id
    quiz = ACTIVE_QUIZZES.get(channel_id)
    if not quiz or quiz.get("answered"):
        return False

    text = strip_discord_mentions(message.content or "").strip().lower()
    if not text:
        return False

    parsed_char, parsed_move = _extract_char_and_move_from_text(text)
    if not parsed_char or not parsed_move:
        return False

    if not check_quiz_answer(quiz, text):
        quiz["awaiting_choice"] = True
        thinking_message = await _quiz_send_thinking_message(message)
        wrong_reply = await build_quiz_wrong_guess_message(message.channel)
        wrong_followup = "Try again or give up and find out the answer"
        wrong_text = f"{wrong_reply}\n{wrong_followup}" if wrong_reply else wrong_followup
        sent = await _quiz_publish_from_placeholder(
            message.channel,
            thinking_message,
            wrong_text,
        )
        _quiz_track_message_id(quiz, getattr(sent, "id", None))
        return True

    scores = quiz.setdefault("scores", {})
    score_names = quiz.setdefault("score_names", {})
    winner_id = int(message.author.id)
    winner_name = _quiz_user_display_name(message.author)
    winner_points = int(scores.get(winner_id, 0)) + 1
    scores[winner_id] = winner_points
    score_names[winner_id] = winner_name
    await _quiz_record_global_win(winner_id, winner_name, points=1)

    ACTIVE_QUIZZES.pop(channel_id, None)
    thinking_message = await _quiz_send_thinking_message(message)
    char_display, move_name, num_cmd = _quiz_answer_display(quiz)
    correct_reply = await build_quiz_correct_guess_message(message.channel)
    score_text = _format_quiz_scores(dict(scores), dict(score_names))
    result_lines = [correct_reply, score_text]
    result_lines.append(f"The answer was **{char_display}'s {move_name} ({num_cmd})**.")
    result_lines.append("Would you like another question?")
    result_text = "\n".join(result_lines)
    sent = await _quiz_publish_from_placeholder(
        message.channel,
        thinking_message,
        result_text,
    )
    if sent is None:
        print("[quiz] correct-reply send failed", flush=True)
        return True

    QUIZ_PENDING_ANOTHER[channel_id] = {
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "message_id": getattr(sent, "id", None),
        "mode": quiz.get("mode", "hard"),
        "owner_user_id": quiz.get("owner_user_id"),
        "scores": dict(scores),
        "score_names": dict(score_names),
        "round": quiz.get("round", 1),
        "message_ids": _quiz_build_message_history(quiz, getattr(sent, "id", None)),
    }
    _quiz_schedule_pending_another_timeout(channel_id, message.channel)

    return True


# ==================== END QUIZ FEATURE ====================


def remember_special_strength_prompt_mode(message_id, mode):
    if not message_id or not mode:
        return
    SPECIAL_STRENGTH_PROMPT_MODE[int(message_id)] = str(mode)
    while len(SPECIAL_STRENGTH_PROMPT_MODE) > SPECIAL_STRENGTH_PROMPT_MODE_MAX:
        oldest_key = next(iter(SPECIAL_STRENGTH_PROMPT_MODE))
        SPECIAL_STRENGTH_PROMPT_MODE.pop(oldest_key, None)


async def send_deleted_message_failsafe(channel):
    reply_text = DELETED_MESSAGE_FAILSAFE_FALLBACK
    if LLM_ENABLED:
        try:
            selected_figures_str = get_selected_figures_str(channel.guild)
            llm_messages = [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT.format(selected_figures_str=selected_figures_str),
                },
                {
                    "role": "user",
                    "content": DELETED_MESSAGE_FAILSAFE_PROMPT,
                },
            ]
            reply_text = await get_llm_response(llm_messages)
        except Exception as e:
            print(f"Deleted-message failsafe LLM error: {e}", flush=True)
    try:
        await channel.send(reply_text)
        print("Deleted-message failsafe sent.", flush=True)
    except Exception as e:
        print(f"Deleted-message failsafe error: {e}", flush=True)


def is_deleted_message_reference_error(error):
    if isinstance(error, discord.NotFound):
        return True
    if isinstance(error, discord.HTTPException):
        text = str(error).lower()
        if "message_reference" in text and "unknown message" in text:
            return True
    return False

async def worker():
    print("Worker started...")
    while True:
        # get msg from queue
        ctx = await message_queue.get()
        if len(ctx) == 6:
            message, llm_messages, fallback_reply, reply_prefix, reply_embeds, reply_embed_rows = ctx
        elif len(ctx) == 5:
            message, llm_messages, fallback_reply, reply_prefix, reply_embeds = ctx
            reply_embed_rows = []
        elif len(ctx) == 4:
            message, llm_messages, fallback_reply, reply_prefix = ctx
            reply_embeds = []
            reply_embed_rows = []
        elif len(ctx) == 3:
            message, llm_messages, fallback_reply = ctx
            reply_prefix = None
            reply_embeds = []
            reply_embed_rows = []
        else:
            message, llm_messages = ctx
            fallback_reply = None
            reply_prefix = None
            reply_embeds = []
            reply_embed_rows = []

        embeds_sent = False
        try:
            memory_context = build_memory_context(max_entries=10, char_budget=1400)
            if memory_context:
                insert_at = 1 if llm_messages and llm_messages[0].get("role") == "system" else 0
                llm_messages = (
                    llm_messages[:insert_at]
                    + [
                        {"role": "user", "content": f"Long-term Discord memory:\n{memory_context}"},
                        {"role": "assistant", "content": "Understood. I will keep that memory in mind."},
                    ]
                    + llm_messages[insert_at:]
                )

            # extract user query and determine if search should be used
            user_query = ""
            for msg in llm_messages:
                if msg.get("role") == "user":
                    candidate_query = str(msg.get("content", "") or "")
                    if candidate_query.startswith("Long-term Discord memory:"):
                        continue
                    user_query = candidate_query
                    break
            enable_search = should_use_search(user_query)
            if enable_search:
                print(f"Google Search enabled for query: {user_query[:50]}...")

            async with message.channel.typing():
                if reply_embeds:
                    try:
                        await send_frame_embeds_with_views(
                            message.channel,
                            reply_embed_rows,
                            embeds=reply_embeds,
                        )
                        embeds_sent = True
                        asyncio.create_task(
                            capture_message_exchange_memory(
                                message,
                                source_label="worker-embed",
                            )
                        )
                    except Exception as embed_error:
                        print(f"Embed send failed: {embed_error}", flush=True)
                    continue

                reply_text = await get_llm_response(llm_messages, enable_search=enable_search)
                final_reply = f"{reply_prefix}\n\n{reply_text}" if reply_prefix else reply_text
                try:
                    await message.reply(final_reply)
                    asyncio.create_task(
                        capture_message_exchange_memory(
                            message,
                            source_label="worker-reply",
                        )
                    )
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Worker reply target deleted before send. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        raise
        except Exception as e:
            print(f"Worker error: {e}")
            error_detail = str(e)
            try:
                if reply_embeds:
                    if not embeds_sent:
                        try:
                            await send_frame_embeds_with_views(
                                message.channel,
                                reply_embed_rows,
                                embeds=reply_embeds,
                            )
                        except Exception as embed_error:
                            print(f"Worker embed error send failed: {embed_error}", flush=True)
                else:
                    if fallback_reply:
                        error_reply = f"{fallback_reply}\n\nLLM error: {error_detail}"
                        if reply_prefix and fallback_reply != reply_prefix:
                            error_reply = f"{reply_prefix}\n\n{error_reply}"
                        await message.reply(error_reply)
                    else:
                        if reply_prefix:
                            await message.reply(f"{reply_prefix}\n\nLLM error: {error_detail}")
                        else:
                            await message.reply(f"LLM error: {error_detail}")
            except Exception as reply_error:
                if not reply_embeds and is_deleted_message_reference_error(reply_error):
                    print("Worker error reply target deleted. Triggering failsafe.", flush=True)
                    await send_deleted_message_failsafe(message.channel)
                    continue
                print(f"Worker fallback reply error: {reply_error}", flush=True)
        finally:
            message_queue.task_done()

@client.event
async def on_ready():
    global message_queue
    global worker_task
    global background_task_handle
    global background_encouragement_task_handle
    global background_damn_gg_task_handle
    global background_video_task_handle
    global reminder_task_handle
    global web_server_task
    print(f'Logged in as {client.user}')
    # create queue in the correct event loop
    if message_queue is None:
        message_queue = asyncio.Queue()
    # start bg task
    if background_task_handle is None or background_task_handle.done():
        background_task_handle = client.loop.create_task(background_task())
    # start encouragement task
    if background_encouragement_task_handle is None or background_encouragement_task_handle.done():
        background_encouragement_task_handle = client.loop.create_task(background_encouragement_task())
    # start damn gg task
    if background_damn_gg_task_handle is None or background_damn_gg_task_handle.done():
        background_damn_gg_task_handle = client.loop.create_task(background_damn_gg_task())
    # start worker
    if worker_task is None or worker_task.done():
        worker_task = client.loop.create_task(worker())
    # start web server
    if web_server_task is None or web_server_task.done():
        web_server_task = client.loop.create_task(start_web_server())
    # start reminder loop
    if reminder_task_handle is None or reminder_task_handle.done():
        reminder_task_handle = client.loop.create_task(reminder_loop())
        print("Reminder loop task created.", flush=True)
    print(
        "[scheduler] Expected behavior active: 1 random daily 'do the thing' batch (no startup dispatch); "
        f"{DAILY_ENCOURAGEMENT_MESSAGES} scheduled LLM encouragements per day.",
        flush=True,
    )
    ensure_memory_file_exists()
    print(f"[memory] loaded entries={len(load_memory_entries())}", flush=True)
    load_quiz_leaderboard()
    print(
        f"[quiz] global leaderboard loaded entries={len(QUIZ_GLOBAL_LEADERBOARD)}",
        flush=True,
    )
    # load frame data
    load_frame_data()

@client.event
async def on_message(message):
    # ignore bot msgs
    if message.author == client.user:
        return

    content_raw = message.content or ""
    content_no_mentions = strip_discord_mentions(content_raw)
    content_lower = content_no_mentions.lower()

    # check mention + phrase
    if client.user.mentioned_in(message) and "do the thing" in content_lower:
        print(f"[daily-message] Manual trigger received from user_id={message.author.id}", flush=True)
        await send_daily_messages(message.channel)
        return

    if await handle_cfn_command(message):
        return

    # Quiz flow
    channel_id = message.channel.id
    in_quiz = channel_id in ACTIVE_QUIZZES
    quiz_state = ACTIVE_QUIZZES.get(channel_id)
    requested_quiz_mode = _quiz_extract_mode_from_text(content_lower)
    answer_is_addressed = client.user.mentioned_in(message) or _is_reply_to_quiz_msg(message)
    mode_prompt_reply = _is_reply_to_quiz_mode_prompt(message)
    command_is_addressed = (
        client.user.mentioned_in(message)
        or bool(QUIZ_NAME_PREFIX_RE.search(content_lower))
        or _is_reply_to_quiz_followup_msg(message)
        or mode_prompt_reply
    )

    if command_is_addressed and _quiz_is_leaderboard_request(content_lower):
        top_limit = _quiz_extract_leaderboard_top_limit(content_lower)
        leaderboard_reply = _quiz_format_global_leaderboard_reply(limit=top_limit)
        try:
            await message.reply(leaderboard_reply)
        except Exception as e:
            if is_deleted_message_reference_error(e):
                await message.channel.send(leaderboard_reply)
            else:
                print(f"[quiz] leaderboard reply error: {e}", flush=True)
        return

    # Follow-up after ending a quiz
    if (
        not in_quiz
        and _quiz_pending_another_active(channel_id)
        and (command_is_addressed or requested_quiz_mode in QUIZ_VALID_MODES)
    ):
        pending = QUIZ_PENDING_ANOTHER.get(channel_id, {})
        pending_scores = dict(pending.get("scores") or {})
        pending_score_names = dict(pending.get("score_names") or {})
        pending_owner_user_id = pending.get("owner_user_id")
        pending_message_ids = list(pending.get("message_ids") or [])
        try:
            next_round = max(1, int(pending.get("round", 1))) + 1
        except Exception:
            next_round = 2

        wants_another_no = bool(QUIZ_ANOTHER_NO_RE.search(content_lower))
        wants_another_yes = bool(QUIZ_ANOTHER_YES_RE.search(content_lower))

        if not wants_another_no and not wants_another_yes:
            inferred_followup_intent = await classify_quiz_another_question_intent(
                message.channel,
                content_lower,
            )
            if inferred_followup_intent == "no":
                wants_another_no = True
            elif inferred_followup_intent == "yes":
                wants_another_yes = True

        if wants_another_no:
            if not _quiz_user_can_end(pending, message.author.id):
                deny_text = _quiz_owner_only_end_message(pending)
                try:
                    await message.reply(deny_text)
                except Exception as e:
                    if is_deleted_message_reference_error(e):
                        await message.channel.send(deny_text)
                    else:
                        print(f"[quiz] owner-only pending-end reply error: {e}", flush=True)
                return

            QUIZ_PENDING_ANOTHER.pop(channel_id, None)
            _quiz_cancel_pending_another_timeout(channel_id)
            QUIZ_PENDING_MODE.pop(channel_id, None)
            thinking_message = await _quiz_send_thinking_message(message)
            crown_line = _quiz_build_crown_line(pending_scores, pending_score_names)
            score_text = _format_quiz_scores(pending_scores, pending_score_names)
            decline_reply = await build_quiz_decline_message(message.channel)
            final_reply = f"{crown_line}\n{score_text}\n{decline_reply}"
            await _quiz_publish_from_placeholder(
                message.channel,
                thinking_message,
                final_reply,
            )
            return

        if requested_quiz_mode in QUIZ_VALID_MODES:
            QUIZ_PENDING_ANOTHER.pop(channel_id, None)
            _quiz_cancel_pending_another_timeout(channel_id)
            await start_quiz(
                message,
                mode=requested_quiz_mode,
                session_scores=pending_scores,
                session_score_names=pending_score_names,
                session_round=next_round,
                session_owner_user_id=pending_owner_user_id,
                session_message_ids=pending_message_ids,
            )
            return

        if wants_another_yes or QUIZ_INTENT_RE.search(content_lower):
            followup_mode = str(requested_quiz_mode or pending.get("mode") or "").strip().lower()
            QUIZ_PENDING_ANOTHER.pop(channel_id, None)
            _quiz_cancel_pending_another_timeout(channel_id)
            if followup_mode not in QUIZ_VALID_MODES:
                await prompt_quiz_mode_selection(
                    message,
                    session_mode=pending.get("mode"),
                    session_scores=pending_scores,
                    session_score_names=pending_score_names,
                    session_round=next_round,
                    session_owner_user_id=pending_owner_user_id,
                    session_message_ids=pending_message_ids,
                )
                return
            await start_quiz(
                message,
                mode=followup_mode,
                session_scores=pending_scores,
                session_score_names=pending_score_names,
                session_round=next_round,
                session_owner_user_id=pending_owner_user_id,
                session_message_ids=pending_message_ids,
            )
            return

    # Pending difficulty selection
    if not in_quiz and _quiz_pending_mode_active(channel_id):
        pending_mode = QUIZ_PENDING_MODE.get(channel_id, {})
        pending_mode_scores = dict(pending_mode.get("scores") or {})
        pending_mode_score_names = dict(pending_mode.get("score_names") or {})
        pending_mode_round = pending_mode.get("round", 1)
        pending_mode_owner_user_id = pending_mode.get("owner_user_id")
        pending_mode_message_ids = list(pending_mode.get("message_ids") or [])

        if requested_quiz_mode in QUIZ_VALID_MODES:
            QUIZ_PENDING_MODE.pop(channel_id, None)
            await start_quiz(
                message,
                mode=requested_quiz_mode,
                session_scores=pending_mode_scores,
                session_score_names=pending_mode_score_names,
                session_round=pending_mode_round,
                session_owner_user_id=pending_mode_owner_user_id,
                session_message_ids=pending_mode_message_ids,
            )
            return

        if command_is_addressed:
            if re.search(r'\b(stop|end|quit|cancel)\b', content_lower):
                if not _quiz_user_can_end(pending_mode, message.author.id):
                    deny_text = _quiz_owner_only_end_message(pending_mode)
                    try:
                        await message.reply(deny_text)
                    except Exception as e:
                        if is_deleted_message_reference_error(e):
                            await message.channel.send(deny_text)
                        else:
                            print(f"[quiz] owner-only mode-cancel reply error: {e}", flush=True)
                    return

                QUIZ_PENDING_MODE.pop(channel_id, None)
                try:
                    await message.reply("Quiz setup cancelled.")
                except Exception as e:
                    if is_deleted_message_reference_error(e):
                        await message.channel.send("Quiz setup cancelled.")
                    else:
                        print(f"[quiz] mode-cancel reply error: {e}", flush=True)
                return

            if mode_prompt_reply or QUIZ_INTENT_RE.search(content_lower):
                await prompt_quiz_mode_selection(
                    message,
                    session_mode=pending_mode.get("mode"),
                    session_scores=pending_mode_scores,
                    session_score_names=pending_mode_score_names,
                    session_round=pending_mode_round,
                    session_owner_user_id=pending_mode_owner_user_id,
                    session_message_ids=pending_mode_message_ids,
                )
                return

    # Active quiz interactions (answer attempts require mention or reply)
    if in_quiz and answer_is_addressed:
        if re.search(r'\b(stop|end|quit|cancel)\b', content_lower):
            if not _quiz_user_can_end(quiz_state, message.author.id):
                deny_text = _quiz_owner_only_end_message(quiz_state)
                try:
                    sent = await message.reply(deny_text)
                    _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
                except Exception as e:
                    if is_deleted_message_reference_error(e):
                        sent = await message.channel.send(deny_text)
                        _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
                    else:
                        print(f"[quiz] owner-only stop reply error: {e}", flush=True)
                return

            await stop_quiz(message)
            return

        if quiz_state and not quiz_state.get("awaiting_choice") and QUIZ_FORFEIT_RE.search(content_lower):
            if not _quiz_user_can_end(quiz_state, message.author.id):
                deny_text = _quiz_owner_only_end_message(quiz_state)
                try:
                    sent = await message.reply(deny_text)
                    _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
                except Exception as e:
                    if is_deleted_message_reference_error(e):
                        sent = await message.channel.send(deny_text)
                        _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
                    else:
                        print(f"[quiz] owner-only forfeit reply error: {e}", flush=True)
                return

            await stop_quiz(message)
            return

        if QUIZ_CHEAT_LOOKUP_RE.search(content_lower):
            cheat_reply = await build_quiz_cheating_warning_message(message.channel)
            try:
                sent = await message.reply(cheat_reply)
                _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
            except Exception as e:
                if is_deleted_message_reference_error(e):
                    sent = await message.channel.send(cheat_reply)
                    _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
                else:
                    print(f"[quiz] cheating-warning reply error: {e}", flush=True)
            return

        if quiz_state and quiz_state.get("awaiting_choice"):
            if await handle_quiz_answer(message):
                return
            if await handle_quiz_post_answer_choice(message):
                return
            if not QUIZ_INTENT_RE.search(content_lower):
                return
        else:
            if not QUIZ_INTENT_RE.search(content_lower):
                if await handle_quiz_answer(message):
                    return
                return

    # Start or stop a single-question quiz
    if command_is_addressed and QUIZ_INTENT_RE.search(content_lower):
        if re.search(r'\b(stop|end|quit|cancel)\b', content_lower):
            if in_quiz and not _quiz_user_can_end(quiz_state, message.author.id):
                deny_text = _quiz_owner_only_end_message(quiz_state)
                try:
                    sent = await message.reply(deny_text)
                    _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
                except Exception as e:
                    if is_deleted_message_reference_error(e):
                        sent = await message.channel.send(deny_text)
                        _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
                    else:
                        print(f"[quiz] owner-only stop-command reply error: {e}", flush=True)
                return
            await stop_quiz(message)
        else:
            if requested_quiz_mode not in QUIZ_VALID_MODES:
                await prompt_quiz_mode_selection(message)
            else:
                await start_quiz(message, mode=requested_quiz_mode)
        return

    if "tarkus" in content_lower:
        await message.reply("My brother is African American. Our love language is slurs and assaulting each other.")
        return

    
    if "clanker" in content_lower:
        await message.reply("please can we not say slurs thanks <:sponge:1416270403923480696>")
        return


    if "verbatim" in content_lower:
        await message.reply("it's less how i think and more so the nature of existence. free will is an illusion. everything that happens in the universe has been metaphysically set in stone since the big bang. menaRD was always going to be the best. if i were destined for more, it would've happened already. <:sponge:1416270403923480696>")
        return


    if client.user.mentioned_in(message) and "link the mod" in content_lower:
        await message.reply("This message was sponsored by LL. Download the LL hitbox viewer mod now from the link below! 'I am Daigo Umehara and I endorse this message' - Daigo Umehara <https://github.com/LL5270/sf6mods>  <:sponge:1416270403923480696>")
        return

    pending_key = (message.author.id, message.channel.id)
    if pending_key in PENDING_REMINDERS:
        pending = PENDING_REMINDERS[pending_key]
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        if (now_utc - pending["created_at"]).total_seconds() > REMINDER_PENDING_TTL_SECONDS:
            del PENDING_REMINDERS[pending_key]
            print(
                "Pending reminder expired: user_id="
                f"{message.author.id} channel_id={message.channel.id}",
                flush=True,
            )
        else:
            if is_reminder_request_text(content_lower):
                del PENDING_REMINDERS[pending_key]
            else:
                tz_match = TZ_REGEX.search(content_no_mentions)
                if tz_match:
                    tz_str = tz_match.group(0)
                    tzinfo, tz_label = parse_timezone(tz_str)
                    if not tzinfo:
                        await message.reply("Unknown timezone. Use GMT/UTC, UTC+2, or IANA like America/New_York.")
                        return
                    now_tz = datetime.datetime.now(tzinfo)
                    if pending["date_str"]:
                        reminder_date = date.fromisoformat(pending["date_str"])
                    elif pending["rel"] == "tomorrow":
                        reminder_date = (now_tz + datetime.timedelta(days=1)).date()
                    else:
                        reminder_date = now_tz.date()
                    reminder_dt = datetime.datetime(
                        reminder_date.year,
                        reminder_date.month,
                        reminder_date.day,
                        pending["hour"],
                        pending["minute"],
                        tzinfo=tzinfo,
                    )
                    if reminder_dt < now_tz and pending["rel"] is None and pending["date_str"] is None:
                        reminder_dt = reminder_dt + datetime.timedelta(days=1)
                    elif reminder_dt < now_tz:
                        await message.reply("That time has already passed. Please choose a future time.")
                        return
                    reminder_utc = reminder_dt.astimezone(datetime.timezone.utc)
                    notify_user_ids = get_reminder_target_user_ids(
                        message,
                        existing_ids=pending.get("notify_user_ids"),
                    )
                    REMINDERS.append({
                        "user_id": message.author.id,
                        "channel_id": message.channel.id,
                        "task": pending["task"],
                        "when_utc": reminder_utc,
                        "notify_user_ids": notify_user_ids,
                    })
                    print(
                        "Pending reminder scheduled: user_id="
                        f"{message.author.id} channel_id={message.channel.id} "
                        f"when_utc={reminder_utc.isoformat()} tz={tz_label} targets={notify_user_ids}",
                        flush=True,
                    )
                    del PENDING_REMINDERS[pending_key]
                    reply_text = await build_reminder_ack_text(
                        pending["task"],
                        reminder_dt,
                        tz_label,
                        message.guild,
                    )
                    await message.reply(reply_text)
                    return

    if client.user.mentioned_in(message) and is_reminder_request_text(content_lower):
        notify_user_ids = get_reminder_target_user_ids(message)
        task, reminder_dt, reminder_utc, tz_label, error, pending = parse_reminder_request(
            content_no_mentions,
            allow_missing_tz=True,
        )
        if pending:
            PENDING_REMINDERS[pending_key] = {
                **pending,
                "notify_user_ids": notify_user_ids,
                "created_at": datetime.datetime.now(datetime.timezone.utc),
            }
            print(
                "Pending reminder created: user_id="
                f"{message.author.id} channel_id={message.channel.id} "
                f"task={pending['task']} time={pending['hour']:02d}:{pending['minute']:02d} "
                f"rel={pending['rel']} date={pending['date_str']} targets={notify_user_ids}",
                flush=True,
            )
            await message.reply("Please include a timezone (e.g., GMT, UTC+2, America/New_York).")
            return
        if error:
            await message.reply(error)
            return
        REMINDERS.append({
            "user_id": message.author.id,
            "channel_id": message.channel.id,
            "task": task,
            "when_utc": reminder_utc,
            "notify_user_ids": notify_user_ids,
        })
        print(
            "Reminder scheduled: user_id="
            f"{message.author.id} channel_id={message.channel.id} "
            f"when_utc={reminder_utc.isoformat()} tz={tz_label} targets={notify_user_ids}",
            flush=True,
        )
        reply_text = await build_reminder_ack_text(
            task,
            reminder_dt,
            tz_label,
            message.guild,
        )
        await message.reply(reply_text)
        return

    # logic flags
    check_media = False
    replied_context = None  # store bub's original message if replying to bot
    special_strength_reply_mode = None
    is_reply_to_bot = False
    
    
    # check mentions
    if client.user.mentioned_in(message):
        check_media = True

    replied_context = None 
    is_coach_mode = "coach" in content_lower
    

    fd_context_payload = find_moves_in_text(content_lower)
    fd_context_data = fd_context_payload.get("data", "")
    fd_context_mode = fd_context_payload.get("mode", "none")
    fd_context_rows = fd_context_payload.get("rows", [])
    startup_alias_query = bool(fd_context_payload.get("startup_alias_query"))
    hitconfirm_alias_query = bool(fd_context_payload.get("hitconfirm_alias_query"))
    super_gain_alias_query = bool(fd_context_payload.get("super_gain_alias_query"))
    range_alias_query = bool(fd_context_payload.get("range_alias_query"))
    wants_comparison = bool(fd_context_payload.get("wants_comparison"))
    property_only_query = bool(fd_context_payload.get("property_only_query"))
    target_combo_query = bool(fd_context_payload.get("target_combo_query"))
    missing_scrolls_query = bool(fd_context_payload.get("missing_scrolls_query"))
    gif_query = bool(fd_context_payload.get("gif_query"))
    explicit_move_attempt = bool(fd_context_payload.get("explicit_move_attempt"))
    fallback_reply = fd_context_data if fd_context_data else None

    def row_matches_requested_strength(row, query_text):
        move_name = str(row.get("moveName", "")).lower().strip()
        cmn_name = str(row.get("cmnName", "")).lower().strip()
        num_cmd = str(row.get("numCmd", "")).lower().strip()
        num_cmd_compact = re.sub(r"[^a-z0-9]", "", num_cmd)

        if re.search(r"\b(?:od|ex)\b", query_text):
            return (
                move_name.startswith(("od ", "ex "))
                or cmn_name.startswith(("od ", "ex "))
                or num_cmd_compact.endswith(("pp", "kk"))
            )

        strength_groups = [
            ({"light", "l", "lp", "lk"}, {"lp", "lk"}),
            ({"medium", "m", "mp", "mk"}, {"mp", "mk"}),
            ({"heavy", "h", "hp", "hk"}, {"hp", "hk"}),
        ]
        requested_suffixes = set()
        for token_group, suffixes in strength_groups:
            if any(re.search(rf"\b{re.escape(token)}\b", query_text) for token in token_group):
                requested_suffixes.update(suffixes)
        if not requested_suffixes:
            return False

        if any(
            move_name.startswith(f"{suffix} ") or cmn_name.startswith(f"{suffix} ")
            for suffix in requested_suffixes
        ):
            return True
        return num_cmd_compact.endswith(tuple(requested_suffixes))

    def row_has_explicit_strength(row):
        move_name = str(row.get("moveName", "")).lower().strip()
        cmn_name = str(row.get("cmnName", "")).lower().strip()
        num_cmd_compact = re.sub(r"[^a-z0-9]", "", str(row.get("numCmd", "")).lower())
        return (
            move_name.startswith(("lp ", "mp ", "hp ", "lk ", "mk ", "hk ", "od ", "ex "))
            or cmn_name.startswith(("lp ", "mp ", "hp ", "lk ", "mk ", "hk ", "od ", "ex "))
            or num_cmd_compact.endswith(("lp", "mp", "hp", "lk", "mk", "hk", "pp", "kk"))
        )

    query_requests_explicit_strength = bool(
        re.search(r"\b(?:od|ex|lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b", content_lower)
    )
    payload_strength_mismatch = bool(
        query_requests_explicit_strength
        and fd_context_rows
        and any(row_has_explicit_strength(row) for row in fd_context_rows)
        and not any(row_matches_requested_strength(row, content_lower) for row in fd_context_rows)
    )

    should_try_llm_lookup_rewrite = bool(
        client.user.mentioned_in(message)
        and (fd_context_payload.get("gif_query") or re.search(r"\b(?:framedata|frame\s*data|frames?)\b", content_lower))
        and (not fd_context_rows or payload_strength_mismatch)
        and "Special Strength Options" not in str(fd_context_data)
        and "Target Combo Options" not in str(fd_context_data)
        and not startup_alias_query
        and not hitconfirm_alias_query
        and not super_gain_alias_query
        and not range_alias_query
    )
    if should_try_llm_lookup_rewrite:
        rewritten_lookup_query = await rewrite_sf_lookup_query_with_llm(
            content_no_mentions,
            guild=message.guild,
        )
        if rewritten_lookup_query:
            rewritten_payload = find_moves_in_text(rewritten_lookup_query.lower())
            rewritten_data = str(rewritten_payload.get("data", "") or "")
            rewritten_rows = rewritten_payload.get("rows", []) or []
            if (
                rewritten_rows
                or "Special Strength Options" in rewritten_data
                or "Target Combo Options" in rewritten_data
            ):
                content_no_mentions = rewritten_lookup_query
                content_lower = rewritten_lookup_query.lower()
                fd_context_payload = rewritten_payload
                fd_context_data = rewritten_payload.get("data", "")
                fd_context_mode = rewritten_payload.get("mode", "none")
                fd_context_rows = rewritten_rows
                startup_alias_query = bool(rewritten_payload.get("startup_alias_query"))
                hitconfirm_alias_query = bool(rewritten_payload.get("hitconfirm_alias_query"))
                super_gain_alias_query = bool(rewritten_payload.get("super_gain_alias_query"))
                range_alias_query = bool(rewritten_payload.get("range_alias_query"))
                wants_comparison = bool(rewritten_payload.get("wants_comparison"))
                property_only_query = bool(rewritten_payload.get("property_only_query"))
                target_combo_query = bool(rewritten_payload.get("target_combo_query"))
                missing_scrolls_query = bool(rewritten_payload.get("missing_scrolls_query"))
                gif_query = bool(rewritten_payload.get("gif_query"))
                explicit_move_attempt = bool(rewritten_payload.get("explicit_move_attempt"))
                fallback_reply = fd_context_data if fd_context_data else None
                print(f"[parser-llm] rewritten query: {rewritten_lookup_query}", flush=True)

    if gif_query and not client.user.mentioned_in(message):
        return

    explicit_frame_request = (
        "framedata" in content_lower
        or "frame data" in content_lower
        or re.search(r"\bframes?\b", content_lower)
        or re.search(r"\bhow\s+fast\b", content_lower)
        or re.search(r"\bhow\s+quick\b", content_lower)
        or re.search(r"\bspeed\s+of\b", content_lower)
        or (
            re.search(r"\bfast\b", content_lower)
            and re.search(r"\b[1-9][0-9]*[a-zA-Z]{1,3}\b", content_lower)
        )
    )
    force_verbatim_frame_reply = bool(
        fd_context_mode == "frame"
        and not property_only_query
        and fd_context_rows
    )
    frame_reply_embeds = (
        build_frame_embeds(fd_context_rows)
        if force_verbatim_frame_reply and fd_context_rows
        else []
    )
    frame_reply_rows = (
        iter_unique_frame_rows(fd_context_rows)
        if force_verbatim_frame_reply and fd_context_rows
        else []
    )
    if frame_reply_embeds:
        print(
            "Frame embed mode active: "
            f"count={len(frame_reply_embeds)} property_only={property_only_query}",
            flush=True,
        )
    

    
    should_handle_direct_frame = (
        client.user.mentioned_in(message)
        or ".framedata" in content_lower
    )
    combined_frame_gif_request = bool(
        gif_query
        and explicit_frame_request
        and fd_context_mode == "frame"
        and not property_only_query
        and not startup_alias_query
        and not hitconfirm_alias_query
        and not super_gain_alias_query
        and not range_alias_query
    )

    vague_move_query_without_output_intent = False
    if (
        client.user.mentioned_in(message)
        and not message.reference
        and not gif_query
        and not explicit_frame_request
        and not property_only_query
        and not target_combo_query
        and not startup_alias_query
        and not hitconfirm_alias_query
        and not super_gain_alias_query
        and not range_alias_query
        and not re.search(
            r"\b(punish|punishable|compare|comparison|versus|vs|stats?|health|reversal|combo|bnb|oki|playstyle|overview|coach)\b",
            content_lower,
        )
    ):
        implied_frame_payload = find_moves_in_text(f"{content_lower} framedata")
        implied_data = implied_frame_payload.get("data", "")
        implied_rows = implied_frame_payload.get("rows", [])
        implied_mode = implied_frame_payload.get("mode", "none")
        implied_explicit_move_attempt = bool(implied_frame_payload.get("explicit_move_attempt"))
        implied_has_special_prompt = "Special Strength Options" in implied_data
        vague_move_query_without_output_intent = bool(
            implied_explicit_move_attempt
            and (
                (implied_mode == "frame" and implied_rows)
                or implied_has_special_prompt
            )
        )

    if (
        not vague_move_query_without_output_intent
        and client.user.mentioned_in(message)
        and not message.reference
        and target_combo_query
        and explicit_move_attempt
        and fd_context_mode == "frame"
        and fd_context_rows
        and not gif_query
        and not explicit_frame_request
        and not property_only_query
        and not startup_alias_query
        and not hitconfirm_alias_query
        and not super_gain_alias_query
        and not range_alias_query
    ):
        vague_move_query_without_output_intent = True

    if should_handle_direct_frame:
        if vague_move_query_without_output_intent:
            await message.reply(
                "While Yimbo is an awesome and handsome programmer, I cannot read minds. Please specify whether you want a GIF, frame data, "
                "or a specific value. For example: \"chun l sbk framedata\"."
            )
            return

        if combined_frame_gif_request and client.user.mentioned_in(message):
            if "Special Strength Options" in fd_context_data:
                try:
                    sent_prompt = await message.reply(fd_context_data)
                    remember_special_strength_prompt_mode(sent_prompt.id, "both")
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Special strength options both reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Special strength options both reply error: {reply_error}", flush=True)
                return

            if not explicit_move_attempt:
                await message.reply("Tell me the exact move too, like 'aki 5hp gif framedata'.")
                return

            if missing_scrolls_query:
                missing_msg = (
                    f"I don't have the scrolls for that move. "
                    f"<@{SCROLLS_MAINTAINER_USER_ID}> {SCROLLS_FIX_REQUEST_TEXT}"
                )
                try:
                    await message.reply(missing_msg)
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Missing-scrolls both reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Missing-scrolls both reply error: {reply_error}", flush=True)
                return

            if fd_context_rows:
                await send_frame_table_response(message, fd_context_rows, fd_context_data)

                gif_frame_rows = fd_context_rows
                if wants_comparison and fd_context_rows:
                    comparison_rows = []
                    seen_comparison_chars = set()
                    for row in fd_context_rows:
                        row_char = normalize_char_name(row.get("char_name", ""))
                        if not row_char or row_char in seen_comparison_chars:
                            continue
                        seen_comparison_chars.add(row_char)
                        comparison_rows.append(row)
                    if len(comparison_rows) >= 2:
                        gif_frame_rows = comparison_rows

                gif_limit = 3
                if wants_comparison and gif_frame_rows:
                    gif_limit = max(2, min(6, len(gif_frame_rows)))

                gif_links = collect_hitbox_gif_links_from_text(
                    content_no_mentions,
                    frame_rows=gif_frame_rows,
                    limit=gif_limit,
                )
                if gif_links:
                    await send_gif_links_response(
                        message,
                        gif_links,
                        wants_comparison=wants_comparison,
                    )
                    return

                missing_gif_msg = (
                    f"I have frame data for that move but no hitbox gif link yet. "
                    f"<@{SCROLLS_MAINTAINER_USER_ID}> {SCROLLS_FIX_REQUEST_TEXT}"
                )
                try:
                    await message.reply(missing_gif_msg)
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Missing-gif both reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Missing-gif both reply error: {reply_error}", flush=True)
                return

        if gif_query and client.user.mentioned_in(message):
            if "Special Strength Options" in fd_context_data:
                try:
                    sent_prompt = await message.reply(fd_context_data)
                    remember_special_strength_prompt_mode(sent_prompt.id, "gif")
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Special strength options gif reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Special strength options gif reply error: {reply_error}", flush=True)
                return

            if not explicit_move_attempt:
                await message.reply("Tell me the exact move too, like 'aki 5hp gif'.")
                return

            gif_frame_rows = fd_context_rows
            if wants_comparison and fd_context_rows:
                comparison_rows = []
                seen_comparison_chars = set()
                for row in fd_context_rows:
                    row_char = normalize_char_name(row.get("char_name", ""))
                    if not row_char or row_char in seen_comparison_chars:
                        continue
                    seen_comparison_chars.add(row_char)
                    comparison_rows.append(row)
                if len(comparison_rows) >= 2:
                    gif_frame_rows = comparison_rows

            gif_limit = 3
            if wants_comparison and gif_frame_rows:
                gif_limit = max(2, min(6, len(gif_frame_rows)))

            gif_links = collect_hitbox_gif_links_from_text(
                content_no_mentions,
                frame_rows=gif_frame_rows,
                limit=gif_limit,
            )
            if gif_links:
                await send_gif_links_response(
                    message,
                    gif_links,
                    wants_comparison=wants_comparison,
                )
                return

            if fd_context_rows:
                missing_gif_msg = (
                    f"I have frame data for that move but no hitbox gif link yet. "
                    f"<@{SCROLLS_MAINTAINER_USER_ID}> {SCROLLS_FIX_REQUEST_TEXT}"
                )
                try:
                    await message.reply(missing_gif_msg)
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Missing-gif reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Missing-gif reply error: {reply_error}", flush=True)
                return

        if missing_scrolls_query:
            missing_msg = (
                f"I don't have the scrolls for that move. "
                f"<@{SCROLLS_MAINTAINER_USER_ID}> {SCROLLS_FIX_REQUEST_TEXT}"
            )
            try:
                await message.reply(missing_msg)
            except Exception as reply_error:
                if is_deleted_message_reference_error(reply_error):
                    print("Missing-scrolls reply target deleted. Triggering failsafe.", flush=True)
                    await send_deleted_message_failsafe(message.channel)
                else:
                    print(f"Missing-scrolls reply error: {reply_error}", flush=True)
            return
        if "Target Combo Options" in fd_context_data:
            try:
                await message.reply(fd_context_data)
            except Exception as reply_error:
                if is_deleted_message_reference_error(reply_error):
                    print("Target combo options reply target deleted. Triggering failsafe.", flush=True)
                    await send_deleted_message_failsafe(message.channel)
                else:
                    print(f"Target combo options reply error: {reply_error}", flush=True)
            return
        if "Special Strength Options" in fd_context_data:
            try:
                sent_prompt = await message.reply(fd_context_data)
                remember_special_strength_prompt_mode(
                    sent_prompt.id,
                    "gif" if gif_query else "frame",
                )
            except Exception as reply_error:
                if is_deleted_message_reference_error(reply_error):
                    print("Special strength options reply target deleted. Triggering failsafe.", flush=True)
                    await send_deleted_message_failsafe(message.channel)
                else:
                    print(f"Special strength options reply error: {reply_error}", flush=True)
            return
        if target_combo_query and fd_context_mode == "frame" and fd_context_rows:
            await send_frame_table_response(message, fd_context_rows, fd_context_data)
            return
        if range_alias_query and fd_context_mode == "frame" and fd_context_rows:
            range_reply = format_range_only_reply(fd_context_rows)
            if range_reply:
                try:
                    await message.reply(range_reply)
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Direct range reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Direct range reply error: {reply_error}", flush=True)
                return
        if super_gain_alias_query and fd_context_mode == "frame" and fd_context_rows:
            super_gain_reply = format_super_gain_only_reply(fd_context_rows)
            if super_gain_reply:
                try:
                    await message.reply(super_gain_reply)
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Direct super gain reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Direct super gain reply error: {reply_error}", flush=True)
                return
        if hitconfirm_alias_query and fd_context_mode == "frame" and fd_context_rows:
            hitconfirm_reply = format_hitconfirm_only_reply(fd_context_rows)
            if hitconfirm_reply:
                try:
                    await message.reply(hitconfirm_reply)
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Direct hitconfirm reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Direct hitconfirm reply error: {reply_error}", flush=True)
                return
        if startup_alias_query and fd_context_mode == "frame" and fd_context_rows:
            startup_reply = format_startup_only_reply(fd_context_rows)
            if startup_reply:
                try:
                    await message.reply(startup_reply)
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Direct startup reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Direct startup reply error: {reply_error}", flush=True)
                return

        if (
            explicit_frame_request
            and fd_context_mode == "frame"
            and fd_context_rows
            and not property_only_query
            and not target_combo_query
            and not startup_alias_query
            and not hitconfirm_alias_query
            and not super_gain_alias_query
            and not range_alias_query
            and not gif_query
        ):
            if not LLM_ENABLED:
                await send_frame_table_response(message, fd_context_rows, fd_context_data)
                return

        # If Coach Mode, pre-pend some advice instruction
        coach_instruction = ""
        if is_coach_mode:
            coach_instruction = (
                "MODE: COACH\n"
                "You are a Fighting Game Coach. Focus on improvement, frame advantage, and punishment.\n"
                "Guide the player towards better habits.\n"
            )
            
        if fd_context_data:
            if fd_context_mode == "frame":
                # Found relevant frame data! Inject it.
                if frame_reply_embeds:
                    replied_context = (
                        f"{coach_instruction}"
                        f"USER QUERY: {content_no_mentions}\n"
                        f"AVAILABLE DATA:\n{fd_context_data}\n"
                        f"{MOVE_DEFINITIONS}\n"
                        "INSTRUCTION: The full frame table is already shown above your reply.\n"
                        " - Write a short follow-up comment (1-2 sentences) underneath the table.\n"
                        " - Do NOT reprint or restate the full table.\n"
                        " - Do NOT output labels like Startup/Active/Recovery/Range/On Hit/On Block/Drive/Super/Hit Confirm/Notes.\n"
                        " - Do NOT include move lines like 'Move Name (numCmd)'.\n"
                        " - If the user asked for a comparison or takeaway, give a brief practical note using AVAILABLE DATA.\n"
                        " - If data is missing for what they asked, say you don't have the scrolls for that part.\n"
                        "CRITICAL: Do NOT invent frame data not present in AVAILABLE DATA."
                    )
                elif property_only_query:
                    replied_context = (
                        f"{coach_instruction}"
                        f"USER QUERY: {content_no_mentions}\n"
                        f"AVAILABLE DATA:\n{fd_context_data}\n"
                        f"{MOVE_DEFINITIONS}\n"
                        "INSTRUCTION: Answer with ONLY the specific value the user asked for in plain text.\n"
                        " - Do NOT output the full frame table for this request.\n"
                        " - If they ask startup/active/recovery/on hit/on block/cancel/damage/drive/super gain/stun/hit confirm/range, return those exact values only.\n"
                        " - Keep it concise (1-2 sentences max).\n"
                        "CRITICAL: Do NOT invent values not present in AVAILABLE DATA."
                    )
                else:
                    replied_context = (
                        f"{coach_instruction}"
                        f"USER QUERY: {content_no_mentions}\n"
                        f"AVAILABLE DATA:\n{fd_context_data}\n"
                        f"{MOVE_DEFINITIONS}\n"
                        "INSTRUCTION: Use the AVAILABLE DATA to answer the user's question.\n"
                        " - If the user asks for 'frame data', 'stats', or general info, output the full data block VERBATIM.\n"
                        " - If the user asks for a SPECIFIC property (e.g. 'what is the recovery?', 'is it plus?', 'damage?'), answer DIRECTLY with just that value in a sentence. Do NOT output the full chart unless asked.\n"
                        " - Examples:\n"
                        "   User: 'Startup of Ryu 5LP?' -> Bot: 'Ryu's Stand LP has 4 frames of startup.'\n"
                        "   User: 'Ryu 5LP frame data' -> Bot: [Outputs Full Chart]\n"
                        "Even if the user asks for a comparison (like 'who is faster?'), FIRST list the full stats for valid moves, THEN add a brief 1-sentence comparison.\n"
                        "If the user asks about stats (health, reversal, etc.), use the provided **Stats** block.\n"
                        "CRITICAL: If a move's frame data is not listed in AVAILABLE DATA above, DO NOT INVENT IT. Just say you don't have the scrolls for it.\n"
                        "CRITICAL: The 'Cancel' field corresponds to the 'xx' column in the data. \n"
                        " - If Cancel is 'sp', it means Special Cancellable.\n"
                        " - If Cancel is 'su', it means Super Cancellable.\n"
                        " - If Cancel is '-' or 'No', it is NOT cancellable. Do NOT suggest canceling it.\n"
                        "Format for Moves: \n"
                        "**Move Name**\n"
                        "Startup: X // Active: Y ...\n"
                        "(Repeat for all moves)\n\n"
                        "Comparison: [Your 1 sentence comparison]"
                    )
                should_respond = True
            elif fd_context_mode == "combo":
                replied_context = (
                    f"{coach_instruction}"
                    f"USER QUERY: {content_no_mentions}\n"
                    f"AVAILABLE DATA:\n{fd_context_data}\n"
                    "INSTRUCTION: Use ONLY the combo/oki data in AVAILABLE DATA.\n"
                    " - Do NOT invent frame data, move inputs, or stats that are not explicitly listed.\n"
                    " - If the question asks for frame data or a move not shown, say the scrolls do not include it."
                )
                should_respond = True
            elif fd_context_mode == "overview":
                replied_context = (
                    f"{coach_instruction}"
                    f"USER QUERY: {content_no_mentions}\n"
                    f"AVAILABLE DATA:\n{fd_context_data}\n"
                    "INSTRUCTION: Use ONLY the overview text in AVAILABLE DATA.\n"
                    " - Do NOT invent moves, inputs, frame data, or specific anti-air buttons unless they appear in the overview.\n"
                    " - Answer in prose, not a table.\n"
                    " - If the overview does not mention the requested detail, say the scrolls do not cover it."
                )
                should_respond = True
            else:
                replied_context = (
                    f"{coach_instruction}"
                    f"USER QUERY: {content_no_mentions}\n"
                    f"AVAILABLE DATA:\n{fd_context_data}\n"
                    "INSTRUCTION: Use ONLY the AVAILABLE DATA to answer the user's question."
                )
                should_respond = True
        elif is_coach_mode:
            # Coach mode but no specific frame data found? 
            # Still provide a coached response.
             replied_context = (
                f"{coach_instruction}"
                f"USER QUERY: {content_no_mentions}\n"
                f"{MOVE_DEFINITIONS}\n"
                "Answer as a helpful coach."
            )
             should_respond = True

    if replied_context is None and message.reference:
        try:
            if message.reference.cached_message:
                replied_msg = message.reference.cached_message
            else:
                replied_msg = await message.channel.fetch_message(message.reference.message_id)
            
            # replying to bot
            if replied_msg.author == client.user:
                check_media = True # check media on reply
                is_reply_to_bot = True
                if replied_msg.id == LAST_DAILY_VIDEO_ID.get(message.channel.id):
                    replied_context = "Has anyone improved?"
                elif "Target Combo Options" in replied_msg.content:
                    replied_context = replied_msg.content  # capture only TC prompt
                elif "Special Strength Options" in replied_msg.content:
                    replied_context = replied_msg.content
                    special_strength_reply_mode = SPECIAL_STRENGTH_PROMPT_MODE.get(replied_msg.id)
                    if (
                        not special_strength_reply_mode
                        and replied_msg.reference
                        and replied_msg.reference.message_id
                    ):
                        try:
                            if replied_msg.reference.cached_message:
                                prompt_source_msg = replied_msg.reference.cached_message
                            else:
                                prompt_source_msg = await message.channel.fetch_message(
                                    replied_msg.reference.message_id
                                )
                            prompt_source_text = strip_discord_mentions(
                                prompt_source_msg.content or ""
                            ).lower()
                            if (
                                re.search(r"\bgif(?:s)?\b", prompt_source_text)
                                or re.search(r"\bhit\s*box(?:es)?\b", prompt_source_text)
                                or re.search(r"\bhitbox(?:es)?\b", prompt_source_text)
                                or ".gif" in prompt_source_text
                                or ".hitbox" in prompt_source_text
                            ):
                                special_strength_reply_mode = "gif"
                        except Exception:
                            pass

        except discord.NotFound:
            pass
        except discord.Forbidden:
            pass
        except Exception as e:
            print(f"Reply logic error: {e}")

    if replied_context and "Target Combo Options" in replied_context:
        match = re.search(r"Target Combo Options \(([^)]+)\)", replied_context)
        char_hint = match.group(1).strip() if match else ""
        tc_query = (content_no_mentions or "").strip()
        tc_query_lower = tc_query.lower()
        if char_hint:
            normalized_hint = normalize_char_name(char_hint)
            if normalized_hint not in tc_query_lower:
                tc_query = f"{char_hint} {tc_query}".strip()
                tc_query_lower = tc_query.lower()
        if not re.search(r"\b(tc|target\s+combo|targetcombo)\b", tc_query_lower):
            tc_query = f"{tc_query} target combo".strip()
            tc_query_lower = tc_query.lower()
        if not (
            "framedata" in tc_query_lower
            or "frame data" in tc_query_lower
            or re.search(r"\bframes?\b", tc_query_lower)
        ):
            tc_query = f"{tc_query} framedata".strip()
        tc_payload = find_moves_in_text(tc_query.lower())
        tc_data = tc_payload.get("data", "")
        tc_rows = tc_payload.get("rows", [])
        if "Target Combo Options" in tc_data:
            await message.reply(tc_data)
            return
        if tc_payload.get("mode") == "frame" and tc_rows and tc_data:
            await send_frame_table_response(message, tc_rows, tc_data)
            return

    if replied_context and "Special Strength Options" in replied_context:
        char_match = re.search(r"Special Strength Options \(([^)]+)\)", replied_context)
        char_hint = char_match.group(1).strip() if char_match else ""
        base_match = re.search(r"\n([^\n]+) variants:", replied_context)
        base_hint = base_match.group(1).strip().lower() if base_match else ""

        option_matches = []

        def parse_special_option_line(option_line):
            line = str(option_line or "").strip()
            if not line:
                return None, None
            if "::" in line:
                left, right = line.split("::", 1)
                option_name = left.strip()
                option_cmd = right.strip()
                if option_name and option_cmd:
                    return option_name, option_cmd
                return None, None
            if not line.endswith(")"):
                return None, None

            depth = 0
            split_idx = None
            for idx in range(len(line) - 1, -1, -1):
                ch = line[idx]
                if ch == ")":
                    depth += 1
                elif ch == "(":
                    depth -= 1
                    if depth == 0:
                        split_idx = idx
                        break

            if split_idx is None:
                return None, None

            option_name = line[:split_idx].strip()
            option_cmd = line[split_idx + 1 : -1].strip()
            if option_name and option_cmd:
                return option_name, option_cmd
            return None, None

        for raw_line in replied_context.splitlines():
            line = raw_line.strip()
            if not line.startswith(("-", "•", "·")):
                continue
            option_line = re.sub(r"^[\s\-•·]+", "", line).strip()
            if not option_line:
                continue
            option_name, option_cmd = parse_special_option_line(option_line)
            if not option_name or not option_cmd:
                continue
            option_matches.append((option_name, option_cmd))

        def compact_token(value):
            return re.sub(r"[^a-z0-9]", "", str(value or "").lower())

        strength_aliases = {
            "l": {"lp", "lk", "light"},
            "light": {"lp", "lk", "light"},
            "m": {"mp", "mk", "medium"},
            "medium": {"mp", "mk", "medium"},
            "h": {"hp", "hk", "heavy"},
            "heavy": {"hp", "hk", "heavy"},
            "lp": {"lp", "light"},
            "mp": {"mp", "medium"},
            "hp": {"hp", "heavy"},
            "lk": {"lk", "light"},
            "mk": {"mk", "medium"},
            "hk": {"hk", "heavy"},
            "od": {"od", "ex", "pp", "kk"},
            "ex": {"od", "ex", "pp", "kk"},
        }

        special_query = (content_no_mentions or "").strip()
        raw_special_reply_lower = special_query.lower()
        special_query_lower = raw_special_reply_lower
        if special_strength_reply_mode == "both":
            special_request_mode = "both"
        elif special_strength_reply_mode == "gif" or gif_query:
            special_request_mode = "gif"
        else:
            special_request_mode = "frame"

        selected_option_name = None
        selected_option_cmd = None
        reply_compact = compact_token(raw_special_reply_lower)
        if option_matches and reply_compact:
            exact_option_matches = []
            for option_name, option_cmd in option_matches:
                option_name_lower = option_name.lower()
                option_name_fireball_alias = re.sub(r"hadou?ken", "fireball", option_name_lower)
                if (
                    reply_compact == compact_token(option_name)
                    or reply_compact == compact_token(option_name_fireball_alias)
                    or reply_compact == compact_token(option_cmd)
                ):
                    exact_option_matches.append((option_name, option_cmd))
            if len(exact_option_matches) == 1:
                selected_option_name, selected_option_cmd = exact_option_matches[0]
            elif not exact_option_matches and raw_special_reply_lower in strength_aliases:
                alias_tokens = strength_aliases[raw_special_reply_lower]
                for option_name, option_cmd in option_matches:
                    option_name_tokens = set(re.findall(r"[a-z0-9]+", option_name.lower()))
                    option_cmd_tokens = set(re.findall(r"[a-z0-9]+", option_cmd.lower()))
                    if alias_tokens & option_name_tokens or alias_tokens & option_cmd_tokens:
                        selected_option_name = option_name
                        selected_option_cmd = option_cmd
                        break

            if not selected_option_name and not selected_option_cmd:
                reply_tokens = set(re.findall(r"[a-z0-9]+", raw_special_reply_lower))
                scored_matches = []
                for option_name, option_cmd in option_matches:
                    option_name_tokens = set(re.findall(r"[a-z0-9]+", option_name.lower()))
                    overlap = len(reply_tokens & option_name_tokens)
                    if overlap > 0:
                        scored_matches.append((overlap, option_name, option_cmd))
                if scored_matches:
                    scored_matches.sort(key=lambda item: item[0], reverse=True)
                    top_score = scored_matches[0][0]
                    top_matches = [item for item in scored_matches if item[0] == top_score]
                    if len(top_matches) == 1:
                        _, selected_option_name, selected_option_cmd = top_matches[0]

        if selected_option_name or selected_option_cmd:
            selected_value = selected_option_cmd or selected_option_name
            if char_hint:
                resolved_char = resolve_character_key(char_hint) or normalize_char_name(char_hint)
                for direct_value in (selected_option_cmd, selected_option_name):
                    if not direct_value:
                        continue
                    direct_row = None
                    direct_value_norm = str(direct_value).lower().strip()
                    for candidate_row in FRAME_DATA.get(resolved_char, []):
                        candidate_num_cmd = str(candidate_row.get("numCmd", "")).lower().strip()
                        if candidate_num_cmd == direct_value_norm:
                            direct_row = candidate_row
                            break
                    if direct_row is None:
                        direct_row = lookup_frame_data(resolved_char, direct_value)
                    if direct_row:
                        if special_request_mode == "gif":
                            gif_links = []
                            direct_link = lookup_hitbox_gif_link(direct_row)
                            if direct_link:
                                gif_links.append(direct_link)
                            else:
                                gif_links = collect_hitbox_gif_links_from_text(
                                    f"{char_hint} {direct_value} gif",
                                    frame_rows=[direct_row],
                                    limit=1,
                                )
                            if gif_links:
                                await message.reply(gif_links[0])
                            else:
                                missing_gif_msg = (
                                    "I have frame data for that move but no hitbox gif link yet. "
                                    f"<@{SCROLLS_MAINTAINER_USER_ID}> {SCROLLS_FIX_REQUEST_TEXT}"
                                )
                                await message.reply(missing_gif_msg)
                        elif special_request_mode == "both":
                            await send_frame_table_response(message, [direct_row], format_frame_data(direct_row))
                            gif_links = []
                            direct_link = lookup_hitbox_gif_link(direct_row)
                            if direct_link:
                                gif_links.append(direct_link)
                            else:
                                gif_links = collect_hitbox_gif_links_from_text(
                                    f"{char_hint} {direct_value} gif",
                                    frame_rows=[direct_row],
                                    limit=1,
                                )
                            if gif_links:
                                await send_gif_links_response(message, gif_links)
                            else:
                                missing_gif_msg = (
                                    "I have frame data for that move but no hitbox gif link yet. "
                                    f"<@{SCROLLS_MAINTAINER_USER_ID}> {SCROLLS_FIX_REQUEST_TEXT}"
                                )
                                await message.reply(missing_gif_msg)
                        else:
                            await send_frame_table_response(message, [direct_row], format_frame_data(direct_row))
                        return
            special_query = f"{char_hint} {selected_value}".strip()
            special_query_lower = special_query.lower()

        if char_hint:
            normalized_hint = normalize_char_name(char_hint)
            if normalized_hint not in special_query_lower:
                special_query = f"{char_hint} {special_query}".strip()
                special_query_lower = special_query.lower()

        if base_hint and base_hint not in special_query_lower and not selected_option_cmd:
            if re.fullmatch(r"(lp|mp|hp|lk|mk|hk|od|ex|light|medium|heavy|l|m|h)", raw_special_reply_lower):
                special_query = f"{special_query} {base_hint}".strip()
            elif not re.search(r"\b(lp|mp|hp|lk|mk|hk|od|ex|light|medium|heavy|l|m|h)\b", special_query_lower):
                special_query = f"{special_query} {base_hint}".strip()
            special_query_lower = special_query.lower()

        if special_request_mode == "gif":
            if not re.search(r"\b(gif|gifs|hitbox|hitboxes)\b", special_query_lower):
                special_query = f"{special_query} gif".strip()
        elif special_request_mode == "both":
            if not re.search(r"\b(gif|gifs|hitbox|hitboxes)\b", special_query_lower):
                special_query = f"{special_query} gif framedata".strip()
        elif not (
            "framedata" in special_query_lower
            or "frame data" in special_query_lower
            or re.search(r"\bframes?\b", special_query_lower)
        ):
            special_query = f"{special_query} framedata".strip()

        special_payload = find_moves_in_text(special_query.lower())
        special_data = special_payload.get("data", "")
        special_rows = special_payload.get("rows", [])
        if "Special Strength Options" in special_data:
            sent_prompt = await message.reply(special_data)
            remember_special_strength_prompt_mode(
                sent_prompt.id,
                special_request_mode,
            )
            return
        if special_request_mode == "gif" and special_rows:
            gif_links = []
            if len(special_rows) == 1:
                direct_link = lookup_hitbox_gif_link(special_rows[0])
                if direct_link:
                    gif_links.append(direct_link)
            if not gif_links:
                gif_links = collect_hitbox_gif_links_from_text(
                    special_query,
                    frame_rows=special_rows,
                    limit=1,
                )
            if gif_links:
                await message.reply(gif_links[0])
                return
            missing_gif_msg = (
                "I have frame data for that move but no hitbox gif link yet. "
                f"<@{SCROLLS_MAINTAINER_USER_ID}> {SCROLLS_FIX_REQUEST_TEXT}"
            )
            await message.reply(missing_gif_msg)
            return
        if special_request_mode == "both" and special_rows:
            await send_frame_table_response(message, special_rows, special_data)
            gif_links = []
            if len(special_rows) == 1:
                direct_link = lookup_hitbox_gif_link(special_rows[0])
                if direct_link:
                    gif_links.append(direct_link)
            if not gif_links:
                gif_links = collect_hitbox_gif_links_from_text(
                    special_query,
                    frame_rows=special_rows,
                    limit=1,
                )
            if gif_links:
                await send_gif_links_response(message, gif_links)
                return
            missing_gif_msg = (
                "I have frame data for that move but no hitbox gif link yet. "
                f"<@{SCROLLS_MAINTAINER_USER_ID}> {SCROLLS_FIX_REQUEST_TEXT}"
            )
            await message.reply(missing_gif_msg)
            return
        if special_payload.get("mode") == "frame" and special_rows and special_data:
            await send_frame_table_response(message, special_rows, special_data)
            return
        await message.reply(replied_context)
        return



    # media check
    media_found = False
    if check_media:
        # check gif embeds
        has_gif = any("tenor.com" in str(e.url or "") or "giphy.com" in str(e.url or "") or (e.type == "gifv") for e in message.embeds)
        # check gif links
        if not has_gif:
            has_gif = "tenor.com" in content_lower or "giphy.com" in content_lower or ".gif" in content_lower
        
        # check images
        has_image = any(att.content_type and att.content_type.startswith("image/") for att in message.attachments)
        
        if has_gif or has_image:
            media_found = True

    # llm response (mentioned OR replying to bot)
    should_respond = client.user.mentioned_in(message) or is_reply_to_bot or replied_context is not None
    if should_respond:
        prompt = content_no_mentions
        media_parts = []
        media_notes = []
        attachments = await get_message_media_items(message)
        if attachments:
            if GEMINI_ENABLED:
                media_parts, media_notes = await build_gemini_media_parts(attachments)
            elif MIMO_ENABLED:
                media_parts, media_notes = build_mimo_media_parts(attachments)
            else:
                for attachment in attachments:
                    filename = attachment.get("filename") or "media"
                    url = attachment.get("url") or ""
                    media_notes.append(f"{filename}: {url}".strip(": "))
        media_context = get_media_context(attachments, media_parts, media_notes)
        has_prompt_or_media = bool(prompt) or bool(media_parts) or bool(media_notes)
        if has_prompt_or_media and not LLM_ENABLED:
            offline_reason = LLM_PROVIDER_ERROR or (
                "Enable one of USE_GEMINI_API, USE_OPENROUTER_API, or USE_MIMO_API and configure its API key."
            )
            await message.reply(
                f"Aiya! The oracle is offline. {offline_reason}"
            )
            return
        if has_prompt_or_media and LLM_ENABLED:
             try:
                # build msg list
                selected_figures_str = get_selected_figures_str(message.guild)
                
                # check if replying to improvement message
                is_improvement_reply = replied_context and "improved" in replied_context.lower()
                
                if is_improvement_reply:
                    active_prompt = IMPROVEMENT_PROMPT.format(
                        selected_figures_str=selected_figures_str
                    )
                else:
                    active_prompt = SYSTEM_PROMPT.format(selected_figures_str=selected_figures_str)

                history_char_budget = estimate_llm_context_history_char_budget(
                    active_prompt,
                    prompt,
                    replied_context,
                    media_context,
                    MOVE_DEFINITIONS,
                )
                context_history = await build_llm_context_history(
                    message,
                    char_budget=history_char_budget,
                )
                context_str = "\n".join(context_history)
                 
                llm_messages = [
                    {"role": "system", "content": active_prompt}
                ]
                
                # add context msg
                if context_str:
                        llm_messages.append({"role": "user", "content": f"Here is the recent chat context:\n{context_str}"})
                        llm_messages.append({"role": "assistant", "content": "Understood. I have the context."})
                
                # if replying to bub's message, add that as explicit context
                user_parts = []
                user_content = prompt
                if media_context:
                    user_content = f"{user_content}\n\n{media_context}" if user_content else media_context
                if replied_context:
                    llm_messages.append({"role": "assistant", "content": replied_context})
                    if prompt:
                        user_parts.append({"text": f"(Replying to your message above) {prompt}"})
                else:
                    if prompt:
                        user_parts.append({"text": prompt})
                if media_parts:
                    user_parts.extend(media_parts)
                if media_notes:
                    user_parts.append({"text": f"Media notes: {'; '.join(media_notes)}"})
                if media_context:
                    user_parts.append({"text": media_context})
                if user_parts:
                    user_message = {
                        "role": "user",
                        "content": user_content,
                        "parts": user_parts,
                    }
                    llm_messages.append(user_message)
                
                # push to queue
                await message_queue.put((message, llm_messages, fallback_reply, None, frame_reply_embeds, frame_reply_rows))

             except Exception as e:
                await message.reply(f"Error generating response: {e}")

if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found in .env")
    else:
        client.run(TOKEN)
