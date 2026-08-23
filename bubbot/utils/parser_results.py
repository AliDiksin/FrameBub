"""Stable dictionaries shared by frame-data parsers."""
# The envelope is intentionally small: parsers add game-specific fields without changing callers.


def parser_result(mode="none", rows=None, data="", **fields):
    """Build the common parser payload without changing parser-specific fields."""
    result = {
        "mode": str(mode or "none"),
        "rows": rows if rows is not None else [],
        "data": "" if data is None else str(data),
    }
    result.update(fields)
    return result


def frame_result(rows=None, data="", **fields):
    return parser_result("frame", rows, data, **fields)


def gif_result(rows=None, data="", **fields):
    return parser_result("gif", rows, data, **fields)


def options_result(rows=None, data="", **fields):
    return parser_result("options", rows, data, **fields)


def empty_result(**fields):
    return parser_result("none", [], "", **fields)
