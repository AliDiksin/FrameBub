import re


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
