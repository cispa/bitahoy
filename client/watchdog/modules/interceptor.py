import asyncio
import socket

from watchdog.core.config import Config
from watchdog.core.modules import Module
from watchdog.hardware.setup import setup_interface
from watchdog.ipc.event import ADDONFILTERS, NODECONFIG, EventListener
from watchdog.ipc.queue import QueueClosed
from watchdog.network.bpf import attach_custom_tcpdump_filter
from watchdog.network.correct import (
    correct_ethernet_header_receive,
    correct_ethernet_header_send,
)
from watchdog.network.packet import FailedLookup, fragment
from watchdog.network.utils import IP, MAC


def avg(args):
    return sum(args) / len(args)


ENABLE_SANITY_CHECKS = True and False  # noqa: SIM223


class InterceptorModule(Module):
    def get_own_ip_tcpdump_filter(self):
        """
        Create tcpdump filter for the own ip and id.
        The filtering per id is based on the modulo of the checksum of the ip packet and enables load balancing.
        :return: tcpdump filter
        """
        return (
            f"(not(ether src {MAC(self.ownmac)} || net 10.199.0.0/16 || src {IP(self.ownip)} || dst {IP(self.ownip)} || dst 255.255.255.255 || net 224.0.0.0/4 || "
            f"dst 0.0.0.0 || dst 127.0.0.1)) and (ip[10] & {self.queues['total_ids'] - 1} == {self.queues['id']})"
        )

    async def on_nodeconfig_event(self, event):
        nodes = event.data["nodes"]
        conf = event.data["conf"]
        ownip = bytes(conf.box.ip)
        ownmac = conf.box.mac
        self.macs = {bytes(node.ip): node.mac for node in nodes}
        self.ips = {bytes(node.mac): node.ip for node in nodes}
        if self.ownip != ownip or self.iface != conf.dev.name or self.ownmac != ownmac:
            self.reload = True
            self.ownip = ownip
            self.iface = conf.dev.name
            self.ownmac = ownmac
            self.conf = conf
            async with self.config_condition:
                self.config_condition.notify_all()

    async def on_addonfilters_event(self, event):
        # Await nodeconfig before creating the filter as we need to know our own IP
        try:
            if not self.ownip:
                async with self.config_condition:
                    await self.config_condition.wait()
            self.filters = event.data["block_filters"] + event.data["active_filters"]
            self.listeners = event.data["passive_filters"]
            if self.filters:
                # Since we get a list of filters we create an tcpdump filter, compile it to bpf and apply it to the socket
                trafficfilter = self.filters[0]["trafficfilter"]
                for listener in self.filters[1:]:
                    trafficfilter = trafficfilter.add_or_filter(listener["trafficfilter"])
                trafficfilter = trafficfilter.negate()
                # this is the translation of get_ownip to a tcpdump rule due to concatenation problems
                # and missing bitwise and in the trafficFilter class
                tcpdump_filter_update = self.get_own_ip_tcpdump_filter() + "and " + trafficfilter.get_ast().to_tcpdump_expr()
                await attach_custom_tcpdump_filter(self.recv_socket, tcpdump_filter_update)
                await self.async_logger.info("Applied tcpdump filter to recv socket: " + tcpdump_filter_update)
            else:
                # Replace the existing filter with the default one
                await attach_custom_tcpdump_filter(self.recv_socket, self.get_own_ip_tcpdump_filter())
                await self.async_logger.info("Applied default tcpdump filter to recv socket")

        except Exception as e:
            await self.async_logger.error("Failed to apply addonfilters: {}".format(e))
            await self.async_logger.traceback()

    def correct_target_mac(self, eth):
        """
        Spoofed clients think the packet is supposed to be sent to us,
        whereas the packet should look like a traffic capture between the 2 devices.
        Therefore we rewrite the addresses in the Ethernet header to mimic this behavior
        """
        return correct_ethernet_header_receive(eth, self.conf.gateway.mac, self.macs, self.conf.network)

    def correct_target_mac_send(self, eth):
        """
        Correct packet before send!
        Since the packet was patched in correct_target_mac we need to restore it,
        so it looks like it was sent from us, because the spoofed device thinks we are the real communication partner
        """
        return correct_ethernet_header_send(eth, self.conf.gateway.mac, self.conf.box.mac, self.macs, self.conf.network)

    async def apply_filter(self, pfilter, packets):
        packets_list = []
        timestamps_list = []
        for packet, packet_timestamp in packets:
            packets_list.append(packet)
            timestamps_list.append(packet_timestamp)
        # get all matching
        matching = []
        for packet_tuple in packets:
            packet, packet_timestamp = packet_tuple
            if pfilter["trafficfilter"].evaluate(packet):
                matching.append(packet_tuple)
        if matching:
            if pfilter["interceptorid"] not in self.addon_queues:
                queue = pfilter["queue"]
                self.addon_queues[pfilter["interceptorid"]] = (queue, await queue.open().__aenter__())
            try:
                await self.addon_queues[pfilter["interceptorid"]][1](
                    {"packets": matching, "interceptorid": pfilter["interceptorid"], "listenerid": pfilter["listenerid"]}
                )
            except QueueClosed:
                del self.addon_queues[pfilter["interceptorid"]]
        return matching
        # await self.logger.verbose("Packet matches filter ({}, }): {}".format(pfilter["interceptorid"], pfilter["listenerid"], repr(packet)))

    async def sanity_check(self, packet):
        """
        Sanity check for packets
        """
        # not good for performance and all these checks are handled in kernel by BPF anyways. only enable if bpf things seem to be broken
        src = packet[0x1A : 0x1A + 4]
        dst = packet[0x1A + 4 : 0x1A + 8]
        src_mac = packet[6:12]
        # if (packet[25] % self.queues["total_ids"]) != self.queues["id"]:
        #    await self.async_logger.error(f"Load balancing failed {packet[25] % self.queues['total_ids']} != {self.queues['id']}")
        if src == self.ownip or dst == self.ownip:
            await self.async_logger.error("BPF should only allow foreign packets :/ ip packed pased through")
            return
        if src_mac == self.ownmac:
            await self.async_logger.error("BPF should not capture outgoing packets :/ srcmac was ownmac")
            return
        if (src not in self.macs or self.macs[src] is None) and src_mac != bytes(self.conf.gateway.mac):
            await self.async_logger.warn("incoming internet-traffic from non-gateway node", str(IP(src)), str(MAC(src_mac)))
            return
        if (src in self.macs and self.macs[src] is not None) and bytes(self.macs[src]) != src_mac:
            await self.async_logger.verbose("spoofed traffic", str(IP(src)), str(MAC(src_mac)))
            # seems to be benign bahavior in some router setups

    async def handle_incoming_packet(self, packet):
        if ENABLE_SANITY_CHECKS:
            await self.sanity_check(packet)

        try:
            if ENABLE_SANITY_CHECKS:
                for pfilter in self.filters:
                    if pfilter["trafficfilter"].evaluate(packet):
                        await self.async_logger.verbose(
                            "blocked packet based on filter {}".format(pfilter["trafficfilter"].get_ast().to_tcpdump_expr())
                        )
                        try:
                            from scapy.all import Ether

                            await self.async_logger.verbose(f"{Ether(packet).show()}")
                        except Exception:
                            await self.async_logger.verbose("could not parse packet")
                        return

            if packet[6:12] == packet[0:6]:
                await self.async_logger.warn(
                    "{} ({}) -> {} ({}): equal dst and src".format(
                        MAC(packet[6:12]), IP(packet[26:30]), MAC(packet[0:6]), IP(packet[30:34])
                    )
                )
            if self.print_stats:
                smac = "{} -> {}".format(MAC(packet[6:12]), MAC(packet[0:6]))
                if smac in self.by_sender:
                    self.by_sender[smac] += 1
                else:
                    self.by_sender[smac] = 1

                self.pcount += 1
            await self.send_packet(packet)
        except FailedLookup as _:
            await self.async_logger.warn("Failed lookup:", _)

    async def send_packet(self, packet):
        try:
            pckt = self.correct_target_mac_send(packet)
        except FailedLookup:
            return

        for sp in fragment(pckt):
            if self.send_socket:
                await self.loop.sock_sendall(self.send_socket, sp)

    async def packet_listener(self):
        while True:
            while not self.ownip or not self.iface or not self.ownmac:
                async with self.config_condition:
                    await self.config_condition.wait()
                    setup_interface(self.iface, self.config.get("interceptor.disable", False))
                    if self.config.get("interceptor.disable", False):
                        await self.async_logger.warn("The 'interceptor.disable' flag is active, shutting down proxy-receiver...")
                        return

            self.recv_socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x800))
            self.recv_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 ** 30)

            self.send_socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x800))

            # as we only enter this loop rarely, we can overwrite the other filters
            await self.async_logger.info("Attaching tcpdump filter to recvsocket: " + self.get_own_ip_tcpdump_filter())
            await attach_custom_tcpdump_filter(self.recv_socket, self.get_own_ip_tcpdump_filter())

            self.recv_socket.setblocking(False)
            self.send_socket.setblocking(False)

            self.recv_socket.bind((self.iface, 0))
            self.send_socket.bind((self.iface, 0))

            self.reload = False

            while not self.reload:
                packet = await self.loop.sock_recv(self.recv_socket, 0xFFFF)
                await self.handle_incoming_packet(packet)

            self.recv_socket.close()
            self.send_socket.close()

    async def stats(self):
        history = []
        if self.print_stats:
            while True:
                await asyncio.sleep(5)
                history = (history + [self.pcount])[-12 * 5 :]
                self.pcount = 0
                await self.async_logger.info(
                    "Packets received (5s average): \n    5s: %d\n   30s: %d\n   60s: %d\n    5m: %d"
                    % (avg(history[-1:]), avg(history[-6:]), avg(history[-12:]), avg(history))
                )
                await self.async_logger.info(history)
                await self.async_logger.info(self.by_sender)

    async def run(self):
        self.loop = asyncio.get_event_loop()
        self.condition = asyncio.Condition()
        self.config_condition = asyncio.Condition()
        self.recv_socket = None
        self.send_socket = None
        self.reload = False
        self.ownip = None
        self.iface = None
        self.ownmac = None
        self.pcount = 0
        self.packets = []
        self.filters = []
        self.listeners = []
        self.exclusive_filters = []
        self.by_sender = {}
        self.addon_queues = {}
        self.config = Config()
        self.print_stats = self.config.get("interceptor.stats", False)
        self.event_listener = EventListener(self.events_in_queue, self.async_logger)
        self.event_listener.on_event[NODECONFIG] = self.on_nodeconfig_event
        self.event_listener.on_event[ADDONFILTERS] = self.on_addonfilters_event
        await asyncio.gather(self.event_listener.listen(), self.packet_listener(), self.stats())
