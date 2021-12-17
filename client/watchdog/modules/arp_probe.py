import asyncio
from socket import AF_PACKET, SOCK_RAW, socket

from watchdog.core.modules import Module
from watchdog.ipc.event import NODECONFIG, EventListener
from watchdog.network.discovery import get_netconfig
from watchdog.network.protocols import arp_packet


class ArpProbeModule(Module):
    async def on_nodeconfig_event(self, event):
        await self.async_logger.info(event.data)
        self.config_xnodes = list(map(lambda x: str(x.ip), event.data["nodes"]))

    async def reload_netconfig(self):
        while True:
            try:
                while self.reload:
                    await asyncio.sleep(30)
                self.conf = get_netconfig()
                await self.async_logger.verbose("loaded netconfig")
                self.reload = True
            except Exception as e:
                self.logger.traceback(e)
                await asyncio.sleep(1)
                continue

    async def prober(self):
        sock = None
        while True:
            while not self.conf:
                await asyncio.sleep(2)
            conf = self.conf
            if sock:
                sock.close()
            sock = socket(AF_PACKET, SOCK_RAW)
            sock.bind((conf.dev.name, 0))
            sock.setblocking(0)
            await self.async_logger.verbose("start probing...")

            self.reload = False
            while not self.reload:
                known_devices = list(self.config_xnodes) + [str(conf.box.ip)]
                static_arp_args = (6 * b"\xff", conf.box.mac, 1, conf.box.mac, conf.box.ip, 6 * b"\xff")
                packets = [
                    arp_packet(*static_arp_args, lookup_ip)
                    for lookup_ip in filter(lambda x: str(x) not in known_devices, conf.network.generator()())
                ]
                for packet in packets:
                    await self.loop.sock_sendall(sock, packet)
                    await asyncio.sleep(0.01)
                await asyncio.sleep(10)

    async def run(self):
        self.config_xnodes = []
        self.conf = None
        self.reload = False
        self.event_listener = EventListener(self.events_in_queue, self.async_logger)
        self.event_listener.on_event[NODECONFIG] = self.on_nodeconfig_event
        await asyncio.gather(self.reload_netconfig(), self.prober(), self.event_listener.listen())
