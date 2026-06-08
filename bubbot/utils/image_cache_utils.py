"""Import generated move-image cache modules and merge nested URL dicts."""

import importlib


def import_cache_module(module_name, log_prefix):
    try:
        return importlib.import_module(module_name)
    except Exception as exc:
        if not isinstance(exc, ModuleNotFoundError):
            print(f"[{log_prefix}] failed to load {module_name}: {exc}", flush=True)
        return None


def merge_nested_url_cache(target, data, *, char_key_fn, move_key_fn, url_fn=lambda url: str(url or "").strip()):
    loaded = 0
    for char_key, moves in (data or {}).items():
        if not isinstance(moves, dict):
            continue
        normalized_char = char_key_fn(char_key)
        for move_key, url in moves.items():
            clean_url = url_fn(url)
            if not clean_url:
                continue
            target[(normalized_char, move_key_fn(move_key))] = clean_url
            loaded += 1
    return loaded
