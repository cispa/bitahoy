import asyncio
import socket
import time

from watchdog.core.modules import Module
from watchdog.ipc.event import NODECONFIG, Event
from watchdog.network.bpf import attach_arp_reply_filter
from watchdog.network.discovery import get_netconfig
from watchdog.network.utils import IP, MAC, ArpNode


class MultiArpCache:
    def __init__(self, timeout=3600):
        self.data = {}
        self.timeout = timeout

    def add(self, mac: MAC, ip: IP, timestamp: int = None):
        new_device = False
        if not timestamp:
            timestamp = time.time()
        if str(mac) in self.data:
            entry = self.data[str(mac)]
            if str(entry[1]) != str(ip) or entry[2] + self.timeout < timestamp:
                new_device = True
        else:
            new_device = True
        self.data[str(mac)] = (mac, ip, timestamp)
        return new_device

    def nodes(self):
        return [ArpNode(x[1], x[0]) for x in self.data.values()]


class ArpListenerModule(Module):
    async def reload_netconfig(self):
        while True:
            try:
                while self.reload:
                    await asyncio.sleep(30)
                conf = get_netconfig()
                self.reload |= self.conf_mac != conf.box.mac or self.conf_dev != conf.dev.name
                self.conf_mac = conf.box.mac
                self.conf_dev = conf.dev.name
                self.conf = conf
                await self.async_logger.verbose("loaded netconfig")
                self.reload = True
            except Exception as e:
                self.logger.error(e)
                await asyncio.sleep(1)
                continue

    async def listen(self):
        arpcache = MultiArpCache(3600)
        sock = None
        while True:
            while not self.conf or not self.conf_dev or not self.conf_mac:
                await asyncio.sleep(1)

            if sock:
                sock.close()
            sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, 0x0806)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 ** 30)
            attach_arp_reply_filter(sock, self.conf_mac)

            sock.setblocking(False)

            sock.bind((self.conf_dev, 0x0806))
            await self.async_logger.info("configured")
            conf = self.conf

            last = time.time()
            self.reload = False
            while not self.reload:
                try:
                    packet = await self.loop.sock_recv(sock, 0xFFFF)
                except socket.error:
                    await asyncio.sleep(0.1)
                    continue

                if len(packet) < 32:
                    await self.async_logger.verbose("Received invalid ARP response", packet)
                    continue

                if packet[22:28] != packet[6:12]:
                    await self.async_logger.warn("ARP spoofing or proxy ARP detected", packet)

                mac = MAC(packet[22:28])
                ip = IP(packet[28:32])
                if arpcache.add(mac, ip, last):
                    self.nodeconfig = {"conf": conf, "nodes": list(arpcache.nodes())}

    async def broadcast_nodeconfig(self):
        async with self.events_out_queue.open() as put:
            while True:
                while not self.nodeconfig:
                    await asyncio.sleep(1)
                await self.async_logger.verbose(f"Broadcasting nodeconfig: {self.nodeconfig}")
                await put(
                    Event(
                        ["spoofer", "proxy-receivers", "proxy-senders", "arp-probe", "deviceid", "addons", "devicescanner"],
                        self.name,
                        NODECONFIG,
                        self.nodeconfig,
                    )
                )
                await asyncio.sleep(5)

    async def run(self):
        self.conf = None
        self.conf_mac = None
        self.conf_dev = None
        self.reload = False
        self.nodeconfig = None
        await asyncio.gather(self.listen(), self.reload_netconfig(), self.broadcast_nodeconfig())
