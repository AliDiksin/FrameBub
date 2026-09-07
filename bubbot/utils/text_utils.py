"""Compact lowercase keys, word tokenization, and contiguous token-sequence helpers."""

import difflib
import re


NOISE_WORDS = {
    # Pronouns
    "i", "me", "my", "you", "your", "it", "its", "we", "us", "they", "them",
    "this", "that", "these", "those",
    # Articles
    "a", "an", "the",
    # Common verbs
    "can", "could", "would", "should", "will", "shall", "might", "must",
    "need", "want", "like", "get", "show", "give", "tell", "have", "has", "had",
    "is", "are", "was", "were", "be", "been", "do", "does", "did",
    # Prepositions
    "for", "of", "to", "in", "on", "at", "by", "with", "from", "about", "into",
    "through", "during", "before", "after", "above", "below", "between",
    "off", "over", "under",
    # Conjunctions
    "and", "or", "but", "if", "while", "because", "until", "although", "though",
    "since", "unless",
    # Adverbs
    "please", "just", "so", "very", "too", "also", "again", "then", "there",
    "here", "now", "already", "still", "even",
    # Question words
    "what", "whats", "how", "when", "where", "why", "who", "which",
    # Determiners/quantifiers
    "some", "any", "all", "each", "every", "both", "few", "more", "most",
    "other", "such", "no", "not", "only", "same", "than",
    # Misc
    "kind", "lot", "lots", "bit", "much", "own", "else", "way",
}
_NOISE_PATTERN = re.compile(
    r"(?:'s\b|\b(?:" + "|".join(re.escape(w) for w in sorted(NOISE_WORDS, key=len, reverse=True)) + r")\b)"
)


def compact_key(value):
    """Return lowercase alphanumeric text for loose key comparisons."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def word_tokens(text):
    """Split text into lowercase alphanumeric word tokens."""
    return re.findall(r"[a-z0-9]+", str(text or "").lower())


def contains_token_sequence(tokens, sequence):
    """Return True when sequence appears contiguously inside tokens."""
    if not sequence:
        return False
    if len(sequence) == 1:
        return sequence[0] in tokens
    seq_len = len(sequence)
    for index in range(0, len(tokens) - seq_len + 1):
        if tokens[index:index + seq_len] == sequence:
            return True
    return False


def remove_first_token_sequence(tokens, sequence):
    """Remove the first contiguous sequence from tokens."""
    if not sequence:
        return tokens, False
    seq_len = len(sequence)
    for index in range(0, len(tokens) - seq_len + 1):
        if tokens[index:index + seq_len] == sequence:
            return tokens[:index] + tokens[index + seq_len:], True
    return tokens, False


def strip_noise_words(text):
    """Remove common English filler words and possessives from query text."""
    text = _NOISE_PATTERN.sub(" ", str(text or "").lower())
    return re.sub(r"\s+", " ", text).strip()


# Typo correction against alias vocabulary; short buttons/strengths are left alone.
_VOCAB_CACHE = {}
_TYPO_CORRECTION_CACHE = {}


def alias_word_vocabulary(*alias_maps, min_word_len=4):
    """Build typo-correction vocabulary from human-readable alias words."""
    words = set()
    for alias_map in alias_maps:
        for alias in (alias_map or {}).keys():
            for word in word_tokens(alias):
                if len(word) >= min_word_len:
                    words.add(word)
    return sorted(words)


def _cached_alias_word_vocabulary(alias_maps, min_word_len=4):
    """Reuse vocab when alias maps are unchanged; rebuild only on size/identity change."""
    key_parts = []
    for alias_map in alias_maps:
        if alias_map is None:
            key_parts.append((0, 0))
            continue
        try:
            key_parts.append((id(alias_map), len(alias_map)))
        except TypeError:
            return alias_word_vocabulary(*alias_maps, min_word_len=min_word_len)
    key = (tuple(key_parts), min_word_len)
    cached = _VOCAB_CACHE.get(key)
    if cached is not None:
        return cached
    words = alias_word_vocabulary(*alias_maps, min_word_len=min_word_len)
    # Bound growth if many distinct transient maps are seen.
    if len(_VOCAB_CACHE) > 64:
        _VOCAB_CACHE.clear()
    _VOCAB_CACHE[key] = words
    return words


def correct_alias_typos(text, *alias_maps, min_word_len=4, cutoff=0.8, ambiguity_margin=None):
    """Correct one-token typos against alias words without touching short buttons."""
    text_value = str(text or "")
    map_signature = tuple((id(alias_map), len(alias_map or {})) for alias_map in alias_maps)
    cache_key = (text_value, map_signature, min_word_len, cutoff, ambiguity_margin)
    cached = _TYPO_CORRECTION_CACHE.get(cache_key)
    if cached is not None:
        return cached
    words = _cached_alias_word_vocabulary(alias_maps, min_word_len=min_word_len)
    if not words:
        return text_value
    corrected_tokens = []
    changed = False
    for token in text_value.split():
        if len(token) < min_word_len or token in words:
            corrected_tokens.append(token)
            continue
        matches = difflib.get_close_matches(token, words, n=2, cutoff=cutoff)
        clear_winner = bool(
            ambiguity_margin is not None
            and len(matches) > 1
            and difflib.SequenceMatcher(None, token, matches[0]).ratio()
            - difflib.SequenceMatcher(None, token, matches[1]).ratio()
            >= ambiguity_margin
        )
        if len(matches) == 1 or clear_winner:
            corrected_tokens.append(matches[0])
            changed = True
        else:
            corrected_tokens.append(token)
    result = " ".join(corrected_tokens) if changed else text_value
    if len(_TYPO_CORRECTION_CACHE) > 4096:
        _TYPO_CORRECTION_CACHE.clear()
    _TYPO_CORRECTION_CACHE[cache_key] = result
    return result


QUERY_TERM_ALIASES = (
    ("framedata", ("frame data", "framedata")),
    ("gif", ("gif", "gifs", "hit box", "hit boxes", "hitbox", "hitboxes", "image", "images", "picture", "pictures")),
    ("notes", ("note", "notes")),
    ("startup", ("start up", "startup", "how fast", "how quick", "speed of")),
    ("active", ("active", "active frame", "active frames")),
    ("recovery", ("recovery",)),
    ("total", ("total", "total frame", "total frames")),
    ("on hit", ("on hit", "hit advantage")),
    ("on block", ("on block", "plus on block", "minus on block", "block advantage")),
    ("flawless block", ("flawless block",)),
    ("block damage", ("block damage",)),
    ("rev damage", ("rev damage",)),
    ("guard damage", ("guard damage",)),
    ("chip damage", ("chip damage",)),
    ("drive damage", ("drive chip", "drive dmg", "drive damage")),
    ("damage", ("damage", "dmg")),
    ("guard", ("guard",)),
    ("attack level", ("attack level", "atk lvl", "atk level")),
    ("cancel", ("cancel", "cancelable", "cancellable")),
    ("gatling", ("gatling",)),
    ("invuln", ("invuln", "invulnerability", "invul")),
    ("attribute", ("attribute",)),
    ("range", ("range", "length")),
    ("hitconfirm", ("hit confirm", "hit-confirm", "hitconfirm", "confirm window", "confirm timing", "confirmable")),
    ("super gain", ("super gain", "super meter gain", "super build", "sa gain")),
    ("meter gain", ("meter gain",)),
    ("stun", ("hitstun", "blockstun", "stun")),
    ("risc gain", ("risc gain", "risc")),
    ("proration", ("proration", "prorate")),
    ("knockdown advantage", ("knockdown advantage", "knockdown adv", "kda")),
    ("punish counter", ("punish counter",)),
    ("counter hit advantage", ("counter hit advantage", "counter hit adv")),
    ("counter hit", ("counter hit",)),
    ("frame advantage", ("frame advantage", "frame adv")),
    ("versus", ("versus",)),
    ("compare", ("compare", "comparison", "which is faster", "which is better")),
)

_QUERY_TERM_LOOKUP = {}
for _canonical_term, _term_aliases in QUERY_TERM_ALIASES:
    for _term_alias in _term_aliases:
        _QUERY_TERM_LOOKUP[_term_alias] = _canonical_term
        _QUERY_TERM_LOOKUP[compact_key(_term_alias)] = _canonical_term

_QUERY_TERM_TYPO_WORDS = {
    word
    for alias in _QUERY_TERM_LOOKUP
    for word in word_tokens(alias)
    if word not in {"frame", "data"}
}
_QUERY_TERM_TYPO_WORDS = {
    word
    for word in _QUERY_TERM_TYPO_WORDS
    if not (
        (word.endswith("s") and word[:-1] in _QUERY_TERM_TYPO_WORDS)
        or (word.endswith("es") and word[:-2] in _QUERY_TERM_TYPO_WORDS)
    )
}
_QUERY_TERM_TYPO_ALIASES = {word: word for word in _QUERY_TERM_TYPO_WORDS}
_STRIPPABLE_QUERY_TERMS = sorted({canonical for canonical, _aliases in QUERY_TERM_ALIASES}, key=len, reverse=True)
_QUERY_TERM_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:"
    + "|".join(re.escape(alias) for alias in sorted(_QUERY_TERM_LOOKUP, key=len, reverse=True))
    + r")(?![a-z0-9])"
)
_STRIPPABLE_QUERY_TERM_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:"
    + "|".join(re.escape(term) for term in _STRIPPABLE_QUERY_TERMS)
    + r")(?![a-z0-9])"
)


def normalize_query_terms(text):
    """Canonicalize compact and conservatively misspelled frame-query terms."""
    normalized = str(text or "").lower()
    normalized = correct_alias_typos(
        normalized,
        _QUERY_TERM_TYPO_ALIASES,
        ambiguity_margin=0.05,
    )
    normalized = _QUERY_TERM_PATTERN.sub(
        lambda match: _QUERY_TERM_LOOKUP[match.group(0)],
        normalized,
    )
    return re.sub(r"\s+", " ", normalized).strip()


def strip_query_terms(text):
    """Remove shared routing terms before game-specific move matching."""
    stripped = normalize_query_terms(text)
    stripped = _STRIPPABLE_QUERY_TERM_PATTERN.sub(" ", stripped)
    return re.sub(r"\s+", " ", stripped).strip()


def query_suffix_candidates(text):
    """Return progressively shorter suffixes of a query for lead-in tolerant matching."""
    cleaned = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    if not cleaned:
        return []
    candidates = [cleaned]
    tokens = re.findall(r"[a-z0-9+.,'-]+", cleaned)
    for index in range(1, len(tokens)):
        suffix = " ".join(tokens[index:])
        if suffix and suffix not in candidates:
            candidates.append(suffix)
    return candidates
