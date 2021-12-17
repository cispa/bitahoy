from bitahoy_sdk.stubs.logger import Logger
from datetime import datetime
import traceback

class EmuLogger(Logger):

    """
    A custom logger for the emulator. Do not use this in your module and do not write another one. Its only to provide a logger for testing purposes.
    """

    appr = {
        0: "ERR",
        10: "WARN",
        20: "NOTICE",
        30: "INFO",
        40: "DEBUG",
        50: "VERBOSE"
    }
    
    splitafter = 200

    def __init__(self, name, logger="logger"):
        self.name = name
        self.logger = logger

    async def inherit(self, name):
        return EmuLogger(name + "@" + self.name, self.logger)

    async def log(self, level, *message):
        m = [x if type(x) == str else repr(x) for x in message]
        m = " ".join(m)
        splitted = m.split("\n")
        messages = []
        for message in splitted:
            messages += [message[i:i+self.splitafter] for i in range(0, len(message), self.splitafter)]
        level = self.appr[level] if level in self.appr else str(level)
        prefix = level.ljust(10, " ")
        prefix += " | "
        prefix += datetime.now().strftime("%d-%b-%Y %H:%M:%S")
        prefix += " | "
        prefix += self.name.ljust(50, " ")
        m = prefix + " | "
        m += ("\n" + len(prefix)*" " + " | ").join(messages)
        print(m)

    async def error(self, *message):
        return await self.log(self.ERROR, *message)

    async def warn(self, *message):
        return await self.log(self.WARNING, *message)

    async def notice(self, *message):
        return await self.log(self.NOTICE, *message)

    async def info(self, *message):
        return await self.log(self.INFO, *message)

    async def debug(self, *message):
        return await self.log(self.DEBUG, *message)

    async def verbose(self, *message):
        return await self.log(self.VERBOSE, *message)

    async def traceback(self, level=0):
        return await self.log(level, traceback.format_exc())