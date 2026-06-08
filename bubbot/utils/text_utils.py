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
def alias_word_vocabulary(*alias_maps, min_word_len=4):
    """Build typo-correction vocabulary from human-readable alias words."""
    words = set()
    for alias_map in alias_maps:
        for alias in (alias_map or {}).keys():
            for word in word_tokens(alias):
                if len(word) >= min_word_len:
                    words.add(word)
    return sorted(words)


def correct_alias_typos(text, *alias_maps, min_word_len=4, cutoff=0.8):
    """Correct one-token typos against alias words without touching short buttons."""
    words = alias_word_vocabulary(*alias_maps, min_word_len=min_word_len)
    if not words:
        return text
    corrected_tokens = []
    changed = False
    for token in str(text or "").split():
        if len(token) < min_word_len or token in words:
            corrected_tokens.append(token)
            continue
        matches = difflib.get_close_matches(token, words, n=2, cutoff=cutoff)
        if len(matches) == 1:
            corrected_tokens.append(matches[0])
            changed = True
        else:
            corrected_tokens.append(token)
    return " ".join(corrected_tokens) if changed else text


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
