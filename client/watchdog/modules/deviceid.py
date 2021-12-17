import asyncio
import struct
from contextlib import suppress

from bitahoy_sdk.addon.utils import Device

from watchdog.core.modules import Module
from watchdog.ipc.event import (
    ADDONQUEUE,
    DEVICEID_DEVICELIST,
    DEVICEID_NEWDEVICE,
    DEVICEIDDATA_DHCP,
    DEVICEIDDATA_NETDISCO,
    NODECONFIG,
    Event,
    EventListener,
)

FORCE_UPDATE_AFTER = 10 * 60  # 10 minutes


def tostr(data):
    if isinstance(data, bytes):
        return data.decode()
    else:
        return str(data)


def device_id(device):

    mac = struct.unpack("<q", b"\x01\x00" + bytes(device.mac))[0]
    return str(mac)


def merge_device(device1, device2):
    assert device1.mac == device2.mac
    update = False
    update |= device1.tmp_ipv4 != device2.tmp_ipv4
    device1.tmp_ipv4 = device2.tmp_ipv4
    if update or device1.last_update + FORCE_UPDATE_AFTER <= device2.last_update:
        device1.last_update = device2.last_update
        update = True
    return device1, update


class Devices:  # noqa: SIM119
    def __init__(self):
        self.by_mac = {}
        self.by_id = {}
        self.by_ipv4 = {}
        self.updated = []
        self.updated_hook = None
        self.new_hook = None
        self.pending_data = {}

    async def add(self, device: Device):
        updated = True
        if device_id(device) not in self.by_id:
            self.by_id[device_id(device)] = device
            if self.updated_hook:
                future = self.new_hook(device)
                if future:
                    await future
        else:
            with suppress(KeyError):
                del self.by_ipv4[str(device.tmp_ipv4)]
            device, updated = merge_device(self.by_id[device_id(device)], device)
        if updated:
            self.updated += [device]
        if device.tmp_ipv4:
            self.by_ipv4[str(device.tmp_ipv4)] = device
        if device.mac:
            self.by_mac[str(device.mac)] = device
        if str(device.tmp_ipv4) in self.pending_data:
            json_before = device.serialize()
            functions = self.pending_data[str(device.tmp_ipv4)]
            for apply_data in functions:
                device = apply_data(device)
            del self.pending_data[str(device.tmp_ipv4)]
            updated = json_before != device.serialize()
        if updated and self.updated_hook:
            future = self.updated_hook(device)
            if future:
                await future
        return updated

    async def apply_nodeconfig(self, nodes):
        for node in nodes:
            device = Device(node)
            device.id = device_id(device)
            await self.add(device)

    async def apply_dhcpdata(self, data):
        def apply(device: Device):
            if "vendor_class_id" in data:
                device.dhcp_vendor_class_id = tostr(data["vendor_class_id"])
            if "hostname" in data:
                device.dhcp_hostname = tostr(data["hostname"])
            return device

        if data["ip"] not in self.pending_data:
            self.pending_data[data["ip"]] = [apply]
        else:
            self.pending_data[data["ip"]].append(apply)
        if data["ip"] in self.by_ipv4:
            await self.add(self.by_ipv4[data["ip"]])  # hacky way to apply the pending dhcpdata to an existing device

    async def apply_netdiscodata(self, data):
        def apply(device: Device):
            if "name" in data:
                device.devicename = tostr(data["name"])
            if "model" in data:
                device.devicemodel = tostr(data["model"])
            if "manufacturer" in data:
                device.manufacturer = tostr(data["manufacturer"])
            return device

        if data["ip"] not in self.pending_data:
            self.pending_data[data["ip"]] = [apply]
        else:
            self.pending_data[data["ip"]].append(apply)
        if data["ip"] in self.by_ipv4:
            await self.add(self.by_ipv4[data["ip"]])  # hacky way to apply the pending data to an existing device

    async def debug(self, async_logger):
        await async_logger.info("Debug:")
        await async_logger.info("\n".join([self.by_id[did].debug() for did in self.by_id]))


class DeviceIdModule(Module):
    async def send_device_list(self, recipients=None):
        if recipients is None:
            recipients = ["addons"]
        await self.async_logger.verbose("send device list to {}".format(recipients))
        await self.put_event(Event(recipients, "deviceid", DEVICEID_DEVICELIST, self.devices.by_id))

    async def register_new_device(self, device):
        await self.async_logger.verbose("register device", device.serialize())
        await self.put_event(Event(["bridge"], "deviceid", DEVICEID_NEWDEVICE, device.serialize()))

    async def on_nodeconfig_event(self, event):
        self.config_xnodes = list(map(lambda x: str(x.ip), event.data["nodes"]))
        await self.async_logger.info(self.config_xnodes)
        await self.devices.apply_nodeconfig(event.data["nodes"])

    async def on_deviceiddata_dhcp_event(self, event):
        await self.async_logger.debug("recvd dhcpdata", event.data)
        await self.devices.apply_dhcpdata(event.data)

    async def on_deviceiddata_netdisco_event(self, event):
        await self.async_logger.debug("recvd netdiscodata")
        await self.devices.apply_netdiscodata(event.data)

    async def on_addonqueue_event(self, event):
        await self.send_device_list([event.sender])

    async def run(self):
        self.devices = Devices()
        self.devices.updated_hook = lambda x: asyncio.gather(self.send_device_list(), self.register_new_device(x))
        self.devices.new_hook = lambda x: self.register_new_device(x)
        self.event_listener = EventListener(self.events_in_queue, self.async_logger)
        self.event_listener.on_event[NODECONFIG] = self.on_nodeconfig_event
        self.event_listener.on_event[DEVICEIDDATA_DHCP] = self.on_deviceiddata_dhcp_event
        self.event_listener.on_event[DEVICEIDDATA_NETDISCO] = self.on_deviceiddata_netdisco_event
        self.event_listener.on_event[ADDONQUEUE] = self.on_addonqueue_event
        async with self.events_out_queue.open() as self.put_event:
            await self.event_listener.listen()
