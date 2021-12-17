import asyncio
import itertools
from socket import AF_PACKET, SOCK_RAW, socket
from typing import Iterator, List, Tuple

from watchdog.core.config import Config
from watchdog.core.modules import Module
from watchdog.ipc.event import NODECONFIG, WHITELIST
from watchdog.network.arpspoof import Spoofer, build_arp_packets
from watchdog.network.utils import ArpNode


class SpooferModule(Module):
    async def event_listener(self):
        nodes = None
        onodes = None
        conf = None
        self.blacklist = None
        async with self.events_in_queue.open() as get_event:
            while True:
                event = await get_event()
                if event.type == NODECONFIG:
                    onodes = event.data["nodes"]
                    if self.blacklist is not None:
                        nodes = list(filter(lambda n: str(n.mac) not in self.blacklist, onodes))
                    else:
                        nodes = onodes
                    conf = event.data["conf"]
                    # await self.async_logger.debug("got nodes:", nodes)
                elif event.type == WHITELIST:
                    self.blacklist = [str(elem) for elem in event.data]
                    if onodes is not None:
                        nodes = list(filter(lambda n: str(n.mac) not in self.blacklist, onodes))
                    # await self.async_logger.debug("got whitelist:", self.blacklist)
                if nodes and conf:
                    packet_gen = Spoofer(nodes, conf.gateway, conf.box.mac, conf.dev, self.config)
                    # await self.async_logger.verbose(list(map(str, packet_gen.comb)))
                    # await self.async_logger.verbose("spoofer configured")
                    await self.async_logger.verbose("Devices:", onodes)
                    await self.async_logger.verbose("Whitelist:", self.blacklist)
                    await self.async_logger.info("Spoofing:", nodes)
                    self.nodes = nodes  # safe the nodes, so we can revert the spoofing in on_terminate
                    self.packets = packet_gen.packets
                    self.iname = packet_gen.interface.name
                else:
                    self.packets = []
                    self.iname = None

    async def spoof(self):
        sock = None
        iname = None

        PACKET_INTERVAL = float(self.config.get("spoofer.packet_interval", 0.2))
        REFRESH_INTERVAL = float(self.config.get("spoofer.refresh_interval", 5.0))
        while True:
            while not self.iname or self.blacklist is None:
                await asyncio.sleep(1.5)
            if sock:
                sock.close()
                sock = None
            sock = socket(AF_PACKET, SOCK_RAW)
            sock.bind((self.iname, 0))
            sock.setblocking(False)
            iname = self.iname
            await self.async_logger.verbose("Started spoofer on interface", iname)
            while self.iname == iname:
                for packets in self.packets:
                    for packet in packets:
                        await self.loop.sock_sendall(sock, packet)
                    await asyncio.sleep(PACKET_INTERVAL)
                await asyncio.sleep(REFRESH_INTERVAL)

    async def run(self):
        self.packets = []
        self.iname = None
        self.nodes = []
        self.config = Config()
        if self.config.get("spoofer.disabled", False):
            await self.async_logger.warn("Spoofing disabled. Check your config (spoofer.disabled = true)")
            await self.event_listener()
        else:
            await asyncio.gather(self.event_listener(), self.spoof())

    async def on_terminate(self):
        """
        Restore the arp configuration to the state before spoofer was launched
        :return: None
        """
        if len(self.nodes) < 2:
            return
        loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()  # get the new loop since the old one crashed
        combinations: Iterator[Tuple[ArpNode, ArpNode]] = itertools.permutations(self.nodes, 2)
        packets: List[bytes] = []
        for node1, node2 in combinations:
            packets += build_arp_packets(node1, node2, node2.mac, broadcast=self.config.get("spoofer.arp_broadcast", True))
        sock = socket(AF_PACKET, SOCK_RAW)
        sock.setblocking(False)
        sock.bind((self.iname, 0))
        for _ in range(2):
            for packet in packets:
                await loop.sock_sendall(sock, packet)
                await asyncio.sleep(0.05)
