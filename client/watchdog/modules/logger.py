import asyncio

from watchdog.core.logging import CloudPrinter, LogPrinter
from watchdog.core.modules import Module
from watchdog.ipc.event import LOG, EventListener


class LoggerModule(Module):
    async def cloudprint(self):
        while True:
            while not self.events:
                async with self.cond:
                    await self.cond.wait()
            events = list(self.events)
            self.events = []
            for event in events:
                await self.cloudprinter.print(event)

    async def on_log_event(self, event):
        self.printer.print(event)
        await self.cloudprinter.print(event)
        self.events += [event]
        async with self.cond:
            self.cond.notify()

    async def run(self):
        self.printer = LogPrinter()
        self.cloudprinter = CloudPrinter(self.events_out_queue, instant=False)
        self.events = []
        self.cond = asyncio.Condition()
        self.event_listener = EventListener(self.queues["logger_queue"], self.async_logger)
        self.event_listener.on_event[LOG] = self.on_log_event
        await asyncio.gather(self.event_listener.listen(), self.cloudprint())
