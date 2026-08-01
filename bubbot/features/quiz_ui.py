"""Quiz prompt views and placeholder message helpers."""

import discord


def bind(**values):
    globals().update(values)
class QuizNotesButton(discord.ui.Button):
    def __init__(self, row, mode="hard", game="sf6"):
        self.frame_row = row
        self.mode = mode
        self.game = _quiz_game_key(game)
        super().__init__(
            label="Show Notes",
            style=discord.ButtonStyle.primary,
            disabled=not _quiz_row_has_notes(row, self.game),
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if not hasattr(self.view, "build_embed"):
            await interaction.response.defer()
            return
        self.view.show_notes = not self.view.show_notes
        self.label = "Hide Notes" if self.view.show_notes else "Show Notes"
        self.style = discord.ButtonStyle.secondary if self.view.show_notes else discord.ButtonStyle.primary
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view, attachments=[])


class QuizGiveUpButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Give Up", style=discord.ButtonStyle.danger, row=0)

    async def callback(self, interaction: discord.Interaction):
        channel = interaction.channel
        channel_id = getattr(channel, "id", None)
        quiz = ACTIVE_QUIZZES.get(channel_id)
        if not quiz or quiz.get("answered"):
            await interaction.response.send_message("No active quiz is running in this channel.", ephemeral=True)
            return


        ended_quiz = ACTIVE_QUIZZES.pop(channel_id, None)
        if ended_quiz is not quiz:
            if ended_quiz:
                ACTIVE_QUIZZES[channel_id] = ended_quiz
            await interaction.response.send_message("That quiz already changed. Try again.", ephemeral=True)
            return

        _quiz_cancel_active_timeout(channel_id)
        for item in getattr(self.view, "children", []):
            item.disabled = True
        await interaction.response.edit_message(view=self.view)

        reply_text = _quiz_reveal_reply_text(quiz)
        sent = await interaction.followup.send(reply_text)
        await _quiz_start_next_question(
            QuizChannelMessage(channel, author=interaction.user),
            quiz,
            result_message_id=getattr(sent, "id", None),
        )


class QuizEndButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="End Quiz", style=discord.ButtonStyle.secondary, row=0)

    async def callback(self, interaction: discord.Interaction):
        channel = interaction.channel
        channel_id = getattr(channel, "id", None)
        quiz = ACTIVE_QUIZZES.get(channel_id)
        if not quiz or quiz.get("answered"):
            await interaction.response.send_message("No active quiz is running in this channel.", ephemeral=True)
            return


        ended_quiz = ACTIVE_QUIZZES.pop(channel_id, None)
        if ended_quiz is not quiz:
            if ended_quiz:
                ACTIVE_QUIZZES[channel_id] = ended_quiz
            await interaction.response.send_message("That quiz already changed. Try again.", ephemeral=True)
            return

        _quiz_cancel_active_timeout(channel_id)
        for item in getattr(self.view, "children", []):
            item.disabled = True
        await interaction.response.edit_message(view=self.view)

        char_display, move_name, num_cmd = _quiz_answer_display(quiz)
        score_text = _format_quiz_scores(
            dict(quiz.get("scores") or {}),
            dict(quiz.get("score_names") or {}),
        )
        await interaction.followup.send(
            f"Quiz ended. The answer was **{char_display}'s {move_name} ({num_cmd})**.\n{score_text}"
        )


class QuizQuestionView(discord.ui.View):
    def __init__(self, row, mode="hard", game="sf6"):
        super().__init__(timeout=QUIZ_ACTIVE_TTL_SECONDS)
        self.frame_row = row
        self.mode = mode
        self.game = _quiz_game_key(game)
        self.show_notes = False
        self.add_item(QuizNotesButton(row, mode=mode, game=self.game))
        self.add_item(QuizGiveUpButton())
        self.add_item(QuizEndButton())

    def build_embed(self):
        return build_quiz_frame_embed(self.frame_row, mode=self.mode, show_notes=self.show_notes, game=self.game)


# Answer hint censoring (hide char/move names in intro text)
def _normalize_quiz_words(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _get_quiz_character_terms(game="sf6"):
    global QUIZ_CHARACTER_TERMS_CACHE
    game = _quiz_game_key(game)
    if not isinstance(QUIZ_CHARACTER_TERMS_CACHE, dict):
        QUIZ_CHARACTER_TERMS_CACHE = {}
    if game in QUIZ_CHARACTER_TERMS_CACHE:
        return QUIZ_CHARACTER_TERMS_CACHE[game]

    terms = set()
    config = _quiz_game_config(game)
    data = _quiz_game_data(game)
    aliases = config.get("aliases") or {}
    for name in data.keys():
        normalized = _normalize_quiz_words(name)
        if normalized:
            terms.add(normalized)

    for name in aliases.keys():
        normalized = _normalize_quiz_words(name)
        if normalized:
            terms.add(normalized)

    for name in aliases.values():
        normalized = _normalize_quiz_words(name)
        if normalized:
            terms.add(normalized)

    QUIZ_CHARACTER_TERMS_CACHE[game] = sorted(terms, key=len, reverse=True)
    return QUIZ_CHARACTER_TERMS_CACHE[game]


def _get_quiz_character_censor_patterns(game="sf6"):
    global QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE
    game = _quiz_game_key(game)
    if not isinstance(QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE, dict):
        QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE = {}
    if game in QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE:
        return QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE[game]

    patterns = []
    seen_patterns = set()
    for term in _get_quiz_character_terms(game):
        words = [word for word in str(term or "").split() if word]
        if not words:
            continue
        pattern_text = r"\b" + r"\W*".join(re.escape(word) for word in words) + r"\b"
        if pattern_text in seen_patterns:
            continue
        seen_patterns.add(pattern_text)
        patterns.append(re.compile(pattern_text, re.IGNORECASE))

    QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE[game] = patterns
    return QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE[game]


def _quiz_censor_character_names(text, game="sf6"):
    raw_text = str(text or "")
    if not raw_text:
        return raw_text

    def mask_match(match):
        matched = match.group(0)
        alnum_count = len(re.sub(r"[^A-Za-z0-9]", "", matched))
        return "*" * max(1, alnum_count)

    censored = raw_text
    for pattern in _get_quiz_character_censor_patterns(game):
        censored = pattern.sub(mask_match, censored)
    return censored


def _get_quiz_move_name_terms(game="sf6"):
    global QUIZ_MOVE_NAME_TERMS_CACHE
    game = _quiz_game_key(game)
    if not isinstance(QUIZ_MOVE_NAME_TERMS_CACHE, dict):
        QUIZ_MOVE_NAME_TERMS_CACHE = {}
    if game in QUIZ_MOVE_NAME_TERMS_CACHE:
        return QUIZ_MOVE_NAME_TERMS_CACHE[game]

    terms = set()
    for rows in _quiz_game_data(game).values():
        for row in rows:
            normalized = _normalize_quiz_words(row.get("moveName", ""))
            if not normalized:
                continue
            words = normalized.split()
            if len(words) >= 2 or len(normalized) >= 7:
                terms.add(normalized)

    QUIZ_MOVE_NAME_TERMS_CACHE[game] = sorted(terms, key=len, reverse=True)
    return QUIZ_MOVE_NAME_TERMS_CACHE[game]


def _quiz_intro_has_specific_answer_hint(text, game="sf6"):
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
    for term in _get_quiz_character_terms(game):
        if f" {term} " in padded:
            return True

    for term in _get_quiz_move_name_terms(game):
        if f" {term} " in padded:
            return True
    return False


async def build_quiz_question_message(channel, round_num, total_rounds, row, mode="hard", game="sf6"):
    """Build quiz prompt text + embed using the standard frame table layout."""
    game_key = _quiz_game_key(game)
    intro = await build_quiz_persona_intro(
        channel,
        round_num,
        total_rounds,
        mode,
        sanitize_ascii_line,
        lambda text: _quiz_intro_has_specific_answer_hint(text, game=game_key),
    )
    intro = _quiz_censor_character_names(intro, game=game_key)
    quiz_view = QuizQuestionView(row, mode=mode, game=game_key)
    quiz_embed = quiz_view.build_embed()
    prompt_text = f"{intro}\nAnswer by mention or reply with: `Character Move`"
    return prompt_text, quiz_embed, quiz_view


async def _quiz_send_thinking_message(message, text="Thinking...", *, reply_to_user=True):
    """Send an immediate quiz placeholder while longer work runs."""
    if not reply_to_user:
        try:
            return await message.channel.send(text)
        except Exception as send_error:
            print(f"[quiz] thinking send error: {send_error}", flush=True)
            return None
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


async def _quiz_publish_from_placeholder(channel, placeholder_message, text, embed=None, view=None):
    """Edit placeholder message into final quiz output, or send a fallback."""
    if placeholder_message is not None:
        try:
            await placeholder_message.edit(content=text, embed=embed, view=view, attachments=[])
            return placeholder_message
        except Exception as e:
            print(f"[quiz] placeholder edit error: {e}", flush=True)

    try:
        return await channel.send(text, embed=embed, view=view)
    except Exception as e:
        print(f"[quiz] placeholder fallback send error: {e}", flush=True)
        return None


class QuizChannelMessage:
    def __init__(self, channel, author=None):
        self.channel = channel
        self.author = author or type("QuizAuthor", (), {"id": 0, "display_name": "Bub"})()
        self.content = ""
        self.id = None
        self.reference = None
        self.embeds = []
        self.attachments = []

    async def reply(self, content=None, **kwargs):
        return await self.channel.send(content, **kwargs)


