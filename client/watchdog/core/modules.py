import asyncio

from watchdog.core.logging import AsyncLogger, Logger
from watchdog.ipc.queue import QueueReceiver, QueueSender


class Module:  # noqa SIM119

    name: str = None
    loop = None
    logger: Logger
    async_logger: AsyncLogger
    queues: list
    events_in_queue: QueueReceiver
    events_out_queue: QueueSender

    def __init__(self, name, loop, queues, logger, events_in_queue, events_out_queue):
        self.name = name
        self.loop: asyncio.AbstractEventLoop = loop
        self.logger = logger
        self.async_logger = logger.asyncio()
        self.queues = queues
        self.events_in_queue = events_in_queue
        self.events_out_queue = events_out_queue

    async def run(self):
        raise Exception("implement me")

    async def on_terminate(self):
        """
        This method should be overwritten if the module has important task to do before terminating
        :return: None
        """
        """
        # start httpserver with `python3 -m http.server` to check if all modules executed on_terminate
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1.5)) as session:
            async with session.get(f"http://127.0.0.1:8000/async/{self.name}") as response:
                pass
        """
        await self.async_logger.info(f"Terminating module {self.name}")
