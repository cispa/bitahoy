import asyncio
import contextlib
import itertools
import os
import signal
import socket
import time
import traceback

from bitahoy_sdk.backend import BackendWS
from bitahoy_sdk.filter import TrafficFilter
from bitahoy_sdk.stubs.addon import RegisteredFilter

import watchdog.core.processes
from watchdog.core.addon import AddonReference, cleanup
from watchdog.core.cloud import AuthBackend
from watchdog.core.modules import Module
from watchdog.ipc.event import (
    ADDONCONFIG,
    ADDONFILTERS,
    ADDONLIST,
    ADDONQUEUE,
    DEVICEID_DEVICELIST,
    NODECONFIG,
    NOTIFICATION,
    Event,
    EventListener,
)
from watchdog.ipc.queue import ZMQueueManager
from watchdog.modules.deviceid import Devices
from watchdog.network.bpf import attach_custom_tcpdump_filter
from watchdog.network.checksums import fix_tcp_checksum, fix_udp_checksum
from watchdog.network.correct import (
    correct_ethernet_header_receive,
    correct_ethernet_header_send,
)
from watchdog.network.packet import FailedLookup, fragment
from watchdog.network.utils import IP, MAC


class AddonFilterManager:
    def __init__(self, logger):
        self.listeners = []
        self.filters = []
        self.logger = logger.asyncio()
        self.listenerid = 0
        self.devices = Devices()
        self.authBackend = AuthBackend(logger=self.logger.inherit("AuthBackend"))
        self.config_callback = None

    async def register_event_listener(self):
        await self.send_event(Event(["master"], "addon.{}".format(self.interceptor_id), ADDONQUEUE, self.events_queue.sender()))
        await self.send_event(Event(["deviceid"], "addon.{}".format(self.interceptor_id), ADDONQUEUE, None))

    async def update_filters(self):
        listeners = [
            {
                "trafficfilter": f.trafficfilter,
                "interceptorid": self.interceptor_id,
                "listenerid": f.listenerid,
                "queue": self.packet_queue.sender(),
                "exclusive": f.exclusive,
                "interval": f.avg_delay,
            }
            for f in self.listeners
            if f is not None
        ]
        filters = [{"trafficfilter": f.trafficfilter, "interceptorid": self.interceptor_id} for f in self.filters if f is not None]
        await self.send_event(
            Event(
                ["addon_manager"],
                "addon.{}".format(self.interceptor_id),
                ADDONFILTERS,
                {
                    "block_filters": filters,  # traffic to be blocked for everything
                    "active_filters": list(
                        filter(lambda x: x["exclusive"], listeners)
                    ),  # traffic that should be forwarded to one specific addon
                    "passive_filters": list(
                        filter(lambda x: not x["exclusive"], listeners)
                    ),  # traffic that is forwarded to an addon and may be resent immediately
                    "interceptorid": self.interceptor_id,
                },
            )
        )

    async def addon__get_websocket(self, url: str, anonymous=False) -> BackendWS:
        if anonymous:
            get_token = None
        else:
            get_token = self.authBackend.request_token
        return BackendWS(url, get_token=get_token, logger=self.interceptor.API.logger)

    async def addon_set_config_callback(self, config_callback):
        self.config_callback = config_callback

    async def addon__register_listener(self, on_packet: callable, trafficfilter: TrafficFilter, exclusive=False, avg_delay=60):
        assert isinstance(avg_delay, int)
        if avg_delay <= 0:
            await self.logger.warn("avg_delay is set to 0 or less, which means real-time traffic interceptions. Please use with care.")
        else:
            await self.logger.warn(
                "Unfortunately, delayed interception is not yet implemented. The traffic will be processed similar to real-time interception"
            )

        rf = RegisteredFilter(self.interceptor)
        rf.trafficfilter = trafficfilter
        rf.on_packet = on_packet
        rf.avg_delay = avg_delay
        rf.exclusive = exclusive
        rf.socket = None
        rf.task = None
        loop = asyncio.get_event_loop()

        async def active_listener():
            while True:
                try:
                    while not self.__sender_iface:
                        await asyncio.sleep(1)
                    rf.socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x800))
                    rf.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 ** 30)
                    rf.socket.setblocking(False)

                    tcpdump_filter = (
                        f"(not(ether src {str(MAC(self.__sender_conf.box.mac))} || host {str(IP(self.__sender_conf.box.ip))} || net 224.0.0.0/4 || dst 255.255.255.255 || dst 0.0.0.0 || dst 127.0.0.1)) and "
                        + trafficfilter.get_ast().to_tcpdump_expr()
                    )
                    await self.logger.info("attaching socket ", tcpdump_filter)
                    await attach_custom_tcpdump_filter(rf.socket, tcpdump_filter)

                    iface = self.__sender_iface
                    rf.socket.bind((iface, 0))

                    try:
                        while iface == self.__sender_iface:
                            eth = await loop.sock_recv(rf.socket, 0xFFFF)
                            try:
                                eth = (
                                    correct_ethernet_header_receive(
                                        eth, self.__sender_conf.gateway.mac, self.__sender_macs, self.__sender_conf.network
                                    ),
                                    time.time(),
                                )
                                loop.create_task(on_packet(eth))
                            except FailedLookup:
                                pass
                    finally:
                        rf.socket.close()
                        rf.socket = None
                except Exception:
                    await self.logger.traceback()
                    await asyncio.sleep(1)

        rf.task = asyncio.create_task(active_listener())

        async def remove(self, xself):
            if xself.socket is not None:
                xself.socket.close()
                xself.socket = None
            if rf.task and not rf.task.cancelled():
                rf.task.cancel()
            self.listeners.remove(xself)
            await self.update_filters()

        rf.remove = lambda: remove(self, rf)
        self.listeners += [rf]
        rf.listenerid = self.listenerid
        self.listenerid += 1
        await self.update_filters()
        return rf

    async def addon__send_packets(self, packets):
        errorset = []
        if not self.__sender_s:
            return errorset
        for sp in packets:
            try:
                sp = self.correct_target(sp)
            except FailedLookup:
                errorset += sp
                continue
            sp = fix_udp_checksum(sp)
            sp = fix_tcp_checksum(sp)
            for packet in fragment(sp):
                await self.__sender_loop.sock_sendall(self.__sender_s, packet)
        return errorset

    async def addon__block_traffic(self, trafficfilter: TrafficFilter):
        rf = RegisteredFilter(self.interceptor)
        rf.trafficfilter = trafficfilter
        rf.exclusive = False

        async def remove(self, xself):
            self.filters.remove(xself)
            await self.update_filters()

        rf.remove = lambda: remove(self, rf)
        self.filters += [rf]
        await self.update_filters()
        return rf

    async def addon_send_notifications(self, notifications):
        await self.send_event(
            Event(
                ["bridge"],
                "addon.{}".format(self.interceptor_id),
                NOTIFICATION,
                {"data": notifications},
            )
        )

    async def packet_listener(self):
        loop = asyncio.get_event_loop()
        async with self.packet_queue.receiver().open() as get_packets:
            while True:
                data = await get_packets()
                listenerid = data["listenerid"]
                listener = self.listeners[listenerid]
                if listener:
                    for packet in data["packets"]:
                        # if not listener.trafficfilter.evaluate(packet):
                        #     await self.logger.error("broken listener")
                        loop.create_task(listener.on_packet(packet))
                else:
                    await self.logger.warn("listener not found: ", listenerid)

    async def on_config_event(self, event):
        if callable(self.config_callback):
            await self.config_callback(event.data)

    async def on_deviceid_devicelist_event(self, event):
        devices = Devices()
        for device in event.data.values():
            await devices.add(device)
        self.devices = devices

    async def on_nodeconfig_event(self, event):
        await self.logger.debug("got nodeconfig")
        nodes = event.data["nodes"]
        conf = event.data["conf"]
        ownip = bytes(conf.box.ip)
        ownmac = conf.box.mac
        self.__sender_macs = {bytes(node.ip): node.mac for node in nodes}
        if self.__sender_ownip != ownip or self.__sender_iface != conf.dev.name or self.__sender_ownmac != ownmac:
            self.__sender_reload = True
            self.__sender_ownip = ownip
            self.__sender_iface = conf.dev.name
            self.__sender_ownmac = ownmac
            self.__sender_conf = conf

    def correct_target(self, eth):
        return correct_ethernet_header_send(
            eth, self.__sender_conf.gateway.mac, self.__sender_conf.box.mac, self.__sender_macs, self.__sender_conf.network
        )

    async def packet_sender(self):
        while True:
            while not self.__sender_ownip or not self.__sender_iface or not self.__sender_ownmac:
                await asyncio.sleep(1)
            await self.logger.error("starting socket")
            self.__sender_s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x800))
            self.__sender_s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 ** 30)

            self.__sender_s.setblocking(False)

            self.__sender_s.bind((self.__sender_iface, 0))

            self.__sender_reload = False

            while not self.__sender_reload:
                await asyncio.sleep(5)
            self.__sender_s.close()

    async def main(self):
        self.__sender_reload = False
        self.__sender_ownip = None
        self.__sender_iface = None
        self.__sender_ownmac = None
        self.__sender_s = None
        self.__sender_loop = asyncio.get_event_loop()
        self.event_listener = EventListener(self.events_queue.receiver(), self.logger.inherit("AddonEventListener").asyncio())
        self.event_listener.on_event[NODECONFIG] = self.on_nodeconfig_event
        self.event_listener.on_event[DEVICEID_DEVICELIST] = self.on_deviceid_devicelist_event
        self.event_listener.on_event[ADDONCONFIG] = self.on_config_event
        self.__sender_loop.create_task(self.event_listener.listen())
        await self.register_event_listener()
        await self.logger.info("cwd is {}".format(os.getcwd()))
        while True:
            await asyncio.gather(self.interceptor.main(), self.packet_listener(), self.packet_sender())


class DevicesAPI:  # noqa: SIM119
    def __init__(self, interceptorAPI):
        self._parent = interceptorAPI

    async def get_devices(self):
        return list(self._parent._afm.devices.by_id.values())


class InterceptorAPI:  # noqa: SIM119
    def __init__(self, interceptor, afm, logger, loop):
        self.interceptor = interceptor
        self._afm = afm
        self.logger = logger
        self.event_loop = loop
        self.devices = DevicesAPI(self)
        self.config_callback = None

    async def set_config_callback(self, config_callback: callable):
        return await self._afm.addon_set_config_callback(config_callback)
        # return await self._afm.addon__set_config(config_callback)

    async def register_listener(self, on_packet: callable, trafficfilter: TrafficFilter, exclusive=False, avg_delay=60) -> RegisteredFilter:
        return await self._afm.addon__register_listener(on_packet, trafficfilter, exclusive, avg_delay)

    async def block_traffic(self, trafficfilter: TrafficFilter) -> RegisteredFilter:
        return await self._afm.addon__block_traffic(trafficfilter)

    async def connect_websocket(self, url: str, anonymous=False) -> BackendWS:
        return await self._afm.addon__get_websocket(url, anonymous)

    async def send_packets(self, packets: list) -> BackendWS:
        return self.event_loop.create_task(self._afm.addon__send_packets(packets))

    async def send_notifications(self, notifications: list) -> BackendWS:
        return await self._afm.addon_send_notifications(notifications)


class AddonManagerModule(Module):
    class AddonEntry:
        def __init__(self, addondict, events_out_queue, logger):
            self.ref = AddonReference(addondict["name"], addondict["repo"], addondict["commit"])
            self.logger = logger.inherit(addondict["name"]).asyncio()
            self.ref.logger = logger.inherit("{}(Setup)".format(addondict["name"])).asyncio()
            self.events_out_queue = events_out_queue
            self.processes = {}
            pass

        async def install(self):
            await self.ref.install()

        async def start(self):
            for interceptor in self.ref.get_interceptors():
                await self.logger.info("starting interceptor", interceptor.path)
                await self.start_interceptor(interceptor)

        async def restart_terminated(self):
            for interceptor in self.ref.get_interceptors():
                if interceptor.path in self.processes and not self.processes[interceptor.path].is_alive():
                    await self.logger.info("restarting terminated interceptor", interceptor.path)
                    await self.start_interceptor(interceptor)

        async def start_interceptor(self, interceptor):
            if interceptor.path in self.processes:
                assert not self.processes[interceptor.path].is_alive()
            ref = self.ref

            afm = AddonFilterManager(self.logger.inherit(interceptor.name + "(API)"))

            def run(logger, afm: AddonFilterManager, events_out_queue):
                with contextlib.redirect_stdout(logger.get_file()), contextlib.redirect_stderr(logger.get_file(logger.ERROR)):
                    try:
                        import asyncio

                        interceptor_clazz = __import__(".".join(interceptor.path.split(".")[:-1]))
                        os.chdir(ref.path)
                        for elem in interceptor.path.split(".")[1:]:
                            interceptor_clazz = getattr(interceptor_clazz, elem)
                        with ZMQueueManager(
                            "addon_pckq({})".format(ref.hash[5:] + "." + interceptor.name[15:])
                        ) as afm.packet_queue, ZMQueueManager(
                            "addon_evq({})".format(ref.hash[5:] + "." + interceptor.name[15:])
                        ) as afm.events_queue:
                            interceptor_instance = interceptor_clazz()
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)

                            async def starter():
                                async with events_out_queue.open() as send_event:
                                    afm.send_event = send_event
                                    afm.interceptor_id = ref.hash + "." + interceptor.name
                                    afm.addon_id = ref.hash
                                    afm.interceptor = interceptor_instance
                                    interceptor_instance.API = InterceptorAPI(interceptor_instance, afm, logger.asyncio(), loop)
                                    interceptor_instance.loop = loop
                                    await afm.main()

                            loop.run_until_complete(starter())
                    except KeyboardInterrupt:
                        pass
                    except BaseException:
                        try:
                            logger.error(traceback.format_exc())
                            time.sleep(3)
                        except KeyboardInterrupt:
                            exit()

            self.processes[interceptor.path] = watchdog.core.processes.Process(
                target=run,
                args=(self.logger.inherit(interceptor.name).syncio(), afm, self.events_out_queue),
                name="Addon (%s) Interceptor (%s)" % (self.ref.name, interceptor.name),
            )
            self.processes[interceptor.path].start()

        def close(self):
            for key in list(self.processes.keys()):
                process = self.processes[key]
                if process.is_alive():
                    process.terminate()
                    time.sleep(0.1)
                if process.is_alive():
                    try:
                        process.kill()
                    except AttributeError:
                        os.kill(process.pid, signal.SIGKILL)
                del self.processes[key]

    async def activate_addon(self, addondict):
        if addondict["hash"] not in self.active_addons:
            entry = self.AddonEntry(addondict, self.events_out_queue, self.logger)
            await self.async_logger.warn("activating addon: ", entry.ref.name)
            if not entry.ref.is_installed():
                await entry.install()
            await entry.start()
            self.active_addons[addondict["hash"]] = entry

    async def deactivate_addon(self, addonhash):
        if addonhash in self.active_addons:
            entry = self.active_addons[addonhash]
            await self.async_logger.warn("deactivating addon: ", entry.ref.name)
            entry.close()
            del self.active_addons[addonhash]
            pass

    async def healthcheck(self):
        while True:
            for addon in list(self.active_addons.values()):
                await addon.restart_terminated()
            await self.async_logger.verbose(
                "everything ok. active addons: {}".format(
                    list(map(lambda x: (x.ref.name, x.ref.repo, x.ref.commit, x.ref.path), self.active_addons.values()))
                )
            )
            await asyncio.sleep(10)

    async def on_addonlist_event(self, event):
        for addonhash in list(self.active_addons.keys()):
            addon = self.active_addons[addonhash]
            if addon.ref.hash not in event.data:
                await self.deactivate_addon(addon.ref.hash)
        for addonhash in event.data:
            await self.activate_addon(event.data[addonhash])

    async def on_addonfilters_event(self, event):
        self.block_filters[event.data["interceptorid"]] = event.data["block_filters"]
        self.passive_filters[event.data["interceptorid"]] = event.data["passive_filters"]
        self.active_filters[event.data["interceptorid"]] = event.data["active_filters"]
        await self.async_logger.info("updating filters", event.data)
        await self.send_event(
            Event(
                ["proxy-processors", "proxy-receivers"],
                "addon_manager",
                ADDONFILTERS,
                {
                    "block_filters": list(itertools.chain.from_iterable(self.block_filters.values())),
                    "active_filters": list(itertools.chain.from_iterable(self.active_filters.values())),
                    "passive_filters": list(itertools.chain.from_iterable(self.passive_filters.values())),
                },
            )
        )

    async def run(self):
        cleanup()
        self.passive_filters = {}
        self.active_filters = {}
        self.block_filters = {}
        self.active_addons = {}
        self.event_listener = EventListener(self.events_in_queue, self.async_logger)
        self.event_listener.on_event[ADDONFILTERS] = self.on_addonfilters_event
        self.event_listener.on_event[ADDONLIST] = self.on_addonlist_event
        async with self.events_out_queue.open() as self.send_event:
            try:
                await asyncio.gather(self.healthcheck(), self.event_listener.listen())
            finally:
                for addon in list(self.active_addons.values()):
                    await self.deactivate_addon(addon)
