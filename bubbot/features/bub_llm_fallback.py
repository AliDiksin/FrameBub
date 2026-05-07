import os
import re


ENCOURAGEMENT_ANECDOTE_PROMPT = ""
ENCOURAGEMENT_CONTEXT_CHANCE = 0.0
ENCOURAGEMENT_CONTEXT_SOURCE = "fallback"
ENCOURAGEMENT_PROMPTS = []
GEMINI_ENABLED = False
IMPROVEMENT_PROMPT = "{selected_figures_str}"
LLM_ENABLED = False
LLM_PROVIDER_ERROR = "bub_llm.py is missing; LLM features are disabled."
MEMORY_PROMPT = ""
MIMO_ENABLED = False
MOVE_DEFINITIONS = ""
OPENROUTER_ENABLED = False
SYSTEM_PROMPT = "{selected_figures_str}"


def log_llm_provider_status():
    print("[config] bub_llm.py missing; LLM features disabled.", flush=True)


def ensure_memory_file_exists(memory_file):
    if not memory_file:
        return
    if not os.path.exists(memory_file):
        with open(memory_file, "w", encoding="utf-8") as handle:
            handle.write("")


def load_memory_entries(memory_file, *args, **kwargs):
    if not memory_file or not os.path.exists(memory_file):
        return []
    try:
        with open(memory_file, "r", encoding="utf-8") as handle:
            return [line.rstrip("\n") for line in handle if line.strip()]
    except Exception:
        return []


def build_memory_context(memory_file, max_entries=10, char_budget=1400):
    entries = load_memory_entries(memory_file)[-max_entries:]
    text = "\n".join(entries)
    return text[-char_budget:] if char_budget else text


async def capture_discord_memory(*args, **kwargs):
    return None


def capture_message_exchange_memory(*args, **kwargs):
    return None


def estimate_llm_context_history_char_budget(*args, **kwargs):
    return 0


async def build_llm_context_history(*args, **kwargs):
    return []


def build_prompting_user_identity(message):
    author = getattr(message, "author", None)
    display = getattr(author, "display_name", None) or getattr(author, "name", None) or "User"
    return f"Prompting user: {display}"


def get_selected_figures_str(*args, **kwargs):
    return ""


async def get_llm_response(*args, **kwargs):
    return "LLM features are disabled because bub_llm.py is not installed."


def should_use_search(*args, **kwargs):
    return False


async def get_message_media_items(*args, **kwargs):
    return []


async def build_gemini_media_parts(*args, **kwargs):
    return [], []


async def build_mimo_media_parts(*args, **kwargs):
    return [], []


def get_media_context(*args, **kwargs):
    return ""


async def rewrite_sf_lookup_query_with_llm(*args, **kwargs):
    return None


async def rewrite_ggst_lookup_query_with_llm(*args, **kwargs):
    return None


async def send_generated_encouragement(*args, **kwargs):
    return None


async def send_deleted_message_failsafe(channel):
    try:
        await channel.send("That reply target disappeared, so I cannot attach the response there.")
    except Exception:
        pass


async def build_reminder_ack_text(*args, **kwargs):
    return "Reminder set."


async def build_reminder_fire_text(*args, **kwargs):
    return "Reminder."


async def build_streetfighterdle_reminder_text(*args, **kwargs):
    return "Do Streetfighterdle today."


def sanitize_ascii_line(text):
    return re.sub(r"[^\x00-\x7F]+", "", str(text or "")).strip()


async def build_quiz_persona_intro(channel, round_num, total_rounds, mode, sanitize_ascii_func, has_hint_func):
    mode_key = str(mode or "hard").strip().lower()
    return f"One {mode_key} quiz question is ready. Guess the character and move from the data."


async def build_quiz_decline_message(*args, **kwargs):
    return "Understood. We can run another question whenever you want."


async def build_quiz_wrong_guess_message(*args, **kwargs):
    return "Incorrect. Stay sharp and try again."


async def build_quiz_correct_guess_message(*args, **kwargs):
    return "Correct."


async def build_quiz_cheating_warning_message(*args, **kwargs):
    return "No framedata or gif scouting mid-quiz. Answer directly."


async def classify_quiz_another_question_intent(*args, **kwargs):
    return None


async def classify_quiz_post_answer_choice_intent(*args, **kwargs):
    return None
