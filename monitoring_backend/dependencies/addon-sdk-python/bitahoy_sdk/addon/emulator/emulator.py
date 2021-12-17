import asyncio
import os
import time

from bitahoy_sdk.backend import BackendWS

from bitahoy_sdk.addon.scanner import DeviceScanner
from bitahoy_sdk.addon.interceptor import InterceptorAddon
from bitahoy_sdk.addon.utils import Device, ScanResult
from bitahoy_sdk.addon.emulator.logger import EmuLogger
from bitahoy_sdk.network_utils import IPv4, MAC
from bitahoy_sdk.filter import TrafficFilter
from bitahoy_sdk.stubs.addon import RegisteredFilter
from typing import List, Type
import dpkt
from scapy.layers.inet import Ether, IP
from bitahoy_sdk.addon.emulator.utils import devices, Device

class EmuDevice(Device):

    def __init__(self, ip: str):
        self.ip = IPv4(ip)
        self.MAC = MAC(":".join(8 * ["00"]))
        self.network = None

    def result(self, title: str, description=None, link=None, level=50):
        return ScanResult(self, title=title, description=description, link=link, level=level)


def run_device_scanner(scanner: Type[DeviceScanner], devices=List[Device], options={}):
    async def run_all(scanner: Type[DeviceScanner], devices=List[Device], options={}):
        elo = EmuLogger("emulator")
        logger_addons = await elo.inherit("addons")
        module_logger = await logger_addons.inherit(scanner.__name__)
        logger_receive = await module_logger.inherit("results")

        async def report_result(result: ScanResult):
            await logger_receive.notice(result.__dict__)

        async def run(d: Device, scanner, module_logger, report_result):
            scanner = scanner()
            scanner.logger = await module_logger.inherit(str(d.ip))
            scanner.report_result = report_result
            await scanner.scan(d, options)

        await asyncio.wait([run(device, scanner, module_logger, report_result) for device in devices])

    asyncio.run(run_all(scanner, devices, options), debug=True)


def run_interceptor(interceptor: Type[InterceptorAddon], packet_generator=None, pcap_filename=None, devices_list=[], delay=0,
                    use_pcap_timestamps=False, send_sleep_duration=1):
    filters = []

    class API:
        pass

    async def register_listener(self, on_packet: callable, trafficfilter: TrafficFilter, exclusive=False,
                                avg_delay=60) -> RegisteredFilter:
        if exclusive:
            await self.logger.warn(
                "The listener is registered as 'exclusive', which means the traffic is only handled by the listener. which means the traffic wont be accessed by and other addon nor relayed by the framework itself. Unfortunately, this feature and its checks are not reflected in the emulator yet.")
        assert isinstance(avg_delay, int)
        if avg_delay <= 0:
            await self.logger.warn(
                "avg_delay is set to 0 or less, which means real-time traffic interceptions. Please use with care.")
        else:
            await self.logger.warn(
                "Unfortunately, delayed interception is not implemented in the emulator yet. The traffic will be processed similar to real-time interception")
        rf = RegisteredFilter(self)
        rf.callback__just_a_hack_dont_rely_on_this_field = on_packet
        rf.filter__just_a_hack_dont_rely_on_this_field = trafficfilter
        filters.append(rf)

        async def remove(self):
            filters.remove(self)

        rf.remove = lambda: remove(rf)
        return rf

    async def set_config_callback(self, on_packet: callable):
        raise NotImplementedError

    interceptor.API = API()
    # since register_listener usually is a class method we need to add the 'self' argument in the emulator manually
    interceptor.API.register_listener = lambda *args, **kwargs: register_listener(interceptor.API, *args, **kwargs)
    interceptor.API.set_config_callback = lambda *args, **kwargs: set_config_callback(interceptor.API, *args, **kwargs)

    async def block_traffic(self, trafficfilter: TrafficFilter) -> RegisteredFilter:
        rf = RegisteredFilter(self)
        rf.callback__just_a_hack_dont_rely_on_this_field = None
        rf.filter__just_a_hack_dont_rely_on_this_field = trafficfilter
        filters.append(rf)
        filters.reverse()

        async def remove(self):
            filters.remove(self)

        rf.remove = lambda: remove(rf)
        return rf

    interceptor.API.block_traffic = block_traffic

    async def get_devices(self):
        return devices_list


    interceptor.API.devices = devices()
    interceptor.API.devices.get_devices = get_devices

    async def connect_websocket(self, url: str, anonymous=False) -> BackendWS:
        if anonymous:
            get_token = None
        else:
            def get_token():
                return InterceptorAddon._InterceptorAddon__emulator__get_token(None, url)
        return BackendWS(url, get_token=get_token, logger=self.logger)

    interceptor.API.connect_websocket = lambda *args, **kwargs: connect_websocket(interceptor.API, *args, **kwargs)

    async def on_packet(packet):
        copy = list(filters)  # use copy here since the callback adds additional filters
        for f in copy:
            # if f.filter__just_a_hack_dont_rely_on_this_field.evaluate(packet):
            if True:
                if f.callback__just_a_hack_dont_rely_on_this_field:
                    await f.callback__just_a_hack_dont_rely_on_this_field(packet)
                else:
                    return
            else:
                pass

    loop = asyncio.get_event_loop()

    async def run():
        elo = EmuLogger("emulator")
        logger_addons = await elo.inherit("addons")
        addon = interceptor()
        addon.API.event_loop = loop
        addon.API.logger = await logger_addons.inherit(interceptor.__name__)
        await addon.main()

    # checks if there is a new device, for simplicity here we assume MACs are fixed and unique
    def new_device_check(devices_map, packet):
        # either empty list, or a list with 1 or 2 devices
        return_value = []
        eth_frame = Ether(packet)
        mac_dst = eth_frame.dst
        mac_src = eth_frame.src
        ip_pkt = eth_frame.payload
        try:
            ip_dst = ip_pkt.getfieldval("dst")
        except AttributeError:
            ip_dst = None
        try:
            ip_src = ip_pkt.getfieldval("src")
        except AttributeError:
            ip_src = None

        # no IPv6 support
        if ip_src is not None and ':' in ip_src:
            ip_src = None
        if ip_dst is not None and ':' in ip_dst:
            ip_dst = None

        try:
            devices_map[mac_dst].add(ip_dst)
        except KeyError:
            # new device
            devices_map[mac_dst] = set([ip_dst])
            return_value.append(Device(mac_dst, ip_dst))
        try:
            devices_map[mac_src].add(ip_src)
        except KeyError:
            devices_map[mac_src] = set([ip_src])
            return_value.append(Device(mac_src, ip_src))

        return return_value

    async def emulate(devices_list=devices_list, send_sleep_duration=send_sleep_duration):
        # own defined function that generates packets
        if callable(packet_generator):
            await asyncio.gather(run(), packet_generator(on_packet))
        # send packets from pcap
        elif os.path.isfile(pcap_filename):
            f = open(pcap_filename, 'rb')
            pcap = dpkt.pcap.Reader(f)

            async def generate_pcap_packets(send, devices_list=devices_list, send_sleep_duration=send_sleep_duration, delay=delay):
                # dirty hack to represent a general device
                devices_list += [Device("00:00:00:00:00:00", "0.0.0.0")]
                await asyncio.sleep(delay)
                last_timestamp = None
                devices_map = {}
                for timestamp_packet, packet in pcap:
                    packet_tpl = (packet, timestamp_packet)
                    # new device in this packet?
                    new_device_list = new_device_check(devices_map, packet)
                    devices_list += new_device_list
                    # send packets with time difference they were originally send with for packet_queue testing purposes
                    # first packet a little bit delayed but does not matter
                    if use_pcap_timestamps:
                        if last_timestamp is None:
                            wait_time = 0
                        else:
                            wait_time = timestamp_packet - last_timestamp
                        last_timestamp = timestamp_packet
                        await asyncio.sleep(wait_time)
                    else:
                        await asyncio.sleep(send_sleep_duration)
                    await send(packet_tpl)
            await asyncio.gather(run(), generate_pcap_packets(on_packet))
        else:
            print("No source for packets specified. Exit emulator.")

    loop.run_until_complete(emulate())
