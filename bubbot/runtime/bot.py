"""Thin runtime entrypoint. Re-exports client, tree, main, and message_router symbols.
Root bot.py delegates here so existing service and import paths keep working.
No Discord handlers live in this module."""

from bubbot.runtime import message_router as _message_router


client = _message_router.client
tree = _message_router.tree
main = _message_router.main


def __getattr__(name):
    return getattr(_message_router, name)


if __name__ == "__main__":
    main()
