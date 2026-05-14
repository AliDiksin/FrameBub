import re


def append_unique(items, token, *, front=False):
    if not token or token in items:
        return False
    if front:
        items.insert(0, token)
    else:
        items.append(token)
    return True


def append_first_matching_alias(text_lower, extra_inputs, alias_patterns, *, front=False):
    for pattern, alias_token in alias_patterns:
        if re.search(pattern, text_lower):
            append_unique(extra_inputs, alias_token, front=front)
            return alias_token
    return None


def append_all_matching_aliases(text_lower, extra_inputs, alias_patterns):
    matched = []
    for pattern, alias_token in alias_patterns:
        if re.search(pattern, text_lower):
            append_unique(extra_inputs, alias_token)
            matched.append(alias_token)
    return matched
