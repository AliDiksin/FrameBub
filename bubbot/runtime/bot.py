from bubbot.runtime import message_router as _message_router


client = _message_router.client
tree = _message_router.tree
main = _message_router.main


def __getattr__(name):
    return getattr(_message_router, name)


if __name__ == "__main__":
    main()
