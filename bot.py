"""Compatibility launcher. Delegates to bubbot.runtime.bot so systemd and
regressions can keep using `python bot.py` and `import bot`."""

import sys

from bubbot.runtime import bot as _runtime_bot


if __name__ == "__main__":
    _runtime_bot.main()
else:
    sys.modules[__name__] = _runtime_bot
