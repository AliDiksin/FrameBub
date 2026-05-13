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
