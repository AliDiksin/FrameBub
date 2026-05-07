import sys

from bubbot.runtime import bot as _runtime_bot


if __name__ == "__main__":
    _runtime_bot.main()
else:
    sys.modules[__name__] = _runtime_bot
