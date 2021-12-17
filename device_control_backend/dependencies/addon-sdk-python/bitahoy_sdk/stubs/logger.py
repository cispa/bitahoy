from bitahoy_sdk.exceptions import StubError

class Logger:

    ERROR : int = 0
    WARNING : int = 10
    NOTICE : int = 20
    INFO : int = 30
    DEBUG : int = 40
    VERBOSE : int = 50

    def __init__(self):
        raise StubError("you cannot create a logger. It is passed to the Addons by the framework code.")

    async def inherit(self, name: str):
        """
        spawns a child-logger. somehow simp
        """
        pass

    async def log(self, level, *message : str):
        pass

    async def error(self, *message : str):
        pass

    async def warn(self, *message : str):
        pass

    async def notice(self, *message : str):
        pass

    async def info(self, *message : str):
        pass

    async def debug(self, *message : str):
        pass

    async def verbose(self, *message : str):
        pass

    async def traceback(self, level : int = ERROR):
        pass