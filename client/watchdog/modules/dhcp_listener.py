import asyncio

from watchdog.core.modules import Module
from watchdog.ipc.event import DEVICEIDDATA_DHCP, Event, EventListener
from watchdog.network.dhcp import DHCPPacket


class DHCPServer:
    def __init__(self, module):
        self.put = module.put
        self.logger = module.logger
        self.name = module.name

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        loop = asyncio.get_event_loop()
        loop.create_task(self.handle_income_packet(data, addr))

    async def handle_income_packet(self, data, addr):
        packet = DHCPPacket.from_bytes(data)
        if "requested_addr" in packet.options:
            ip = packet.options["requested_addr"]
            packet.options["ip"] = ip
            self.logger.info("DHCP:", ip, packet.options)
            await self.put(Event(["deviceid"], self.name, DEVICEIDDATA_DHCP, packet.options))


class DhcpListenerModule(Module):
    async def dhcp_listener(self):
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(lambda: DHCPServer(self), local_addr=("0.0.0.0", 67))  # nosec
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            transport.close()

    async def run(self):
        self.event_listener = EventListener(self.events_in_queue, self.async_logger)
        async with self.events_out_queue.open() as self.put:
            await asyncio.gather(self.dhcp_listener(), self.event_listener.listen())
