import asyncio

from device_identifier import NetDiscoScanner

from watchdog.core.config import Config
from watchdog.core.modules import Module
from watchdog.ipc.event import DEVICEIDDATA_NETDISCO, NODECONFIG, Event, EventListener


class DeviceScannerModule(Module):
    async def scan(self):
        async with self.events_out_queue.open() as self.put_event:
            while True:
                if not self.config.get("devicescanner.disable", False):
                    scanner = NetDiscoScanner()
                    results = await scanner.scan(self.ips, raw_flag=False)

                    for ip, info in results.items():
                        data = info
                        data["ip"] = ip
                        await self.put_event(Event(["deviceid"], "devicescanner", DEVICEIDDATA_NETDISCO, data))
                        # log basic device info without the annoying raw data
                        await self.async_logger.info(
                            "Deviceid: ", {category: value for category, value in data.items() if not category.endswith("_raw")}
                        )
                else:
                    await self.async_logger.warn("Devicescanner is disabled by config.json")
                await asyncio.sleep(10)

    async def on_nodeconfig_event(self, event):
        onodes = event.data["nodes"]
        self.ips = list(map(lambda n: n.ip, onodes))
        await self.async_logger.debug("got IPs:", self.ips)

    async def run(self):
        self.ips = []
        self.config = Config()
        self.event_listener = EventListener(self.events_in_queue, self.async_logger)
        self.event_listener.on_event[NODECONFIG] = self.on_nodeconfig_event
        await asyncio.gather(self.scan(), self.event_listener.listen())
