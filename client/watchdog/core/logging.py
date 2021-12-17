import sys
import time
import traceback
from datetime import datetime
from sys import stderr, stdout

from watchdog.ipc.event import CLOUDLOGGING, LOG, Event
from watchdog.ipc.queue import QueueSender

FATAL = 0
ERROR = 1
WARNING = 2
INFO = 3
DEBUG = 4
VERBOSE = 5

loglevel = ERROR
out_file = stdout
err_file = stderr


def __get_logger(level):
    def logger(*args, module):
        print("[" + module + "]", *args, file=err_file if level < 2 else out_file)  # noqa: T001


fatal = __get_logger(FATAL)
warning = __get_logger(WARNING)
error = __get_logger(ERROR)
info = __get_logger(INFO)
debug = __get_logger(DEBUG)
verbose = __get_logger(VERBOSE)


class Logger:

    ERROR = 0
    WARNING = 10
    NOTICE = 20
    INFO = 30
    DEBUG = 40
    VERBOSE = 50

    def __init__(self, logger_queue: QueueSender, name, logger="logger"):
        self.queue = logger_queue
        self.name = name
        self.logger = logger
        self.__put = None

    def asyncio(self):
        return AsyncLogger(self)

    def inherit(self, name):
        return Logger(self.queue, name + "@" + self.name, self.logger)

    def log(self, level, *message):
        msg = [x if type(x) == str else repr(x) for x in message]
        msg = " ".join(msg)
        if not self.__put:
            self.__put = self.queue.open().__enter__()
        self.__put(Event(self.logger, self.name, LOG, {"level": level, "message": msg}))

    def error(self, *message):
        return self.log(self.ERROR, *message)

    def warn(self, *message):
        return self.log(self.WARNING, *message)

    def notice(self, *message):
        return self.log(self.NOTICE, *message)

    def info(self, *message):
        return self.log(self.INFO, *message)

    def debug(self, *message):
        return self.log(self.DEBUG, *message)

    def verbose(self, *message):
        return self.log(self.VERBOSE, *message)

    def traceback(self, level=ERROR):
        return self.log(level, traceback.format_exc())

    def get_file(self, level=DEBUG):
        class file:
            @staticmethod
            def write(msg):
                self.log(level, msg)

        return file()


class AsyncLogger(Logger):

    ERROR = 0
    WARNING = 10
    NOTICE = 20
    INFO = 30
    DEBUG = 40
    VERBOSE = 50

    def __init__(self, logger):
        self.queue = logger.queue
        self.queue_async = logger.queue
        self.name = logger.name
        self.logger = logger.logger
        self.__put = None

    def inherit(self, name):
        return Logger(self.queue, name + "@" + self.name, self.logger).asyncio()

    def syncio(self):
        return Logger(self.queue, self.name, self.logger)

    async def log(self, level, *message):
        msg = [x if type(x) == str else repr(x) for x in message]
        msg = " ".join(msg)
        if not self.__put:
            self.__put = await self.queue_async.open().__aenter__()
        await self.__put(Event(self.logger, self.name, LOG, {"level": level, "message": msg}))

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

    async def traceback(self, level=ERROR):
        return await self.log(level, traceback.format_exc())

    def get_file(self, level=DEBUG):
        return self.syncio().get_file(level)


RED = "\033[1;31m"
YELLOW = "\033[1;33m"
WHITE = "\033[1;37m"
BLUE = "\033[1;34m"
CYAN = "\033[1;36m"
GRAY = "\033[1;90m"
GREEN = "\033[0;32m"
RESET = "\033[0;0m"
BOLD = "\033[;1m"
REVERSE = "\033[;7m"


class LogPrinter:
    def __init__(self, level=Logger.VERBOSE, realprint=sys.stdout.write, color=True, end="\n"):
        self.level = level
        self.realprint = realprint
        self.color_enabled = color
        self.end = end

    appr = {0: "ERR", 10: "WARN", 20: "NOTICE", 30: "INFO", 40: "DEBUG", 50: "VERBOSE"}

    color = {
        0: (RED,),
        10: (YELLOW,),
        20: (BLUE,),
        30: (WHITE,),
        40: (GREEN,),
        50: (GRAY,),
    }

    splitafter = 350

    def print(self, event):  # noqa: A003
        assert event.type == LOG
        level = event.data["level"]
        message = event.data["message"]
        if type(message) != str:
            message = repr(message)
        splitted = message.split("\n")
        messages = []
        for message in splitted:
            messages += [message[i : i + self.splitafter] for i in range(0, len(message), self.splitafter)]
        slevel = self.appr[level] if level in self.appr else str(level)
        color = (self.color[level][0] if level in self.color else RESET) if self.color_enabled else ""
        prefix = color
        prefix += slevel.ljust(10, " ")
        prefix += " | "
        prefix += datetime.now().strftime("%d-%b-%Y %H:%M:%S")
        prefix += " | "
        prefix += event.sender.ljust(25, " ")
        msg = prefix + " | "
        msg += ("\n" + (len(prefix) - len(color)) * " " + " | ").join(messages)
        if self.color_enabled:
            msg += RESET
        msg += self.end
        self.realprint(msg)


class CloudPrinter(LogPrinter):
    def __init__(self, masterqueue: QueueSender, level=Logger.NOTICE, realprint=lambda x: None, instant=False):
        super().__init__(level, realprint, False, "")
        self.data = []
        self.instant = instant
        self.last = time.time()
        self.mq = masterqueue
        self.put = None

    async def append(self, data):
        if not self.put:
            self.put = await self.mq.open().__aenter__()
        self.data.append(data)
        now = time.time()
        if self.instant or self.last + 5 < now:
            data = self.data
            self.data = []
            self.last = now
            await self.put(Event("bridge", "logger", CLOUDLOGGING, {"data": list(data)}))

    async def print(self, event):  # noqa: A003
        assert event.type == LOG
        level = event.data["level"]
        message = event.data["message"]
        if type(message) != str:
            message = repr(message)
        await self.append({"level": level, "time": time.time(), "sender": event.sender, "message": message})
