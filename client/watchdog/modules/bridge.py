import asyncio
import json
import time

from watchdog.core.addon import AddonReference
from watchdog.core.cloud import (
    AddonBackend,
    AuthBackend,
    ControlBackend,
    MonitoringBackend,
)
from watchdog.core.config import Config
from watchdog.core.modules import Module
from watchdog.ipc.event import (
    ADDONCONFIG,
    ADDONLIST,
    CLOUDLOGGING,
    DEVICEID_NEWDEVICE,
    NOTIFICATION,
    WHITELIST,
    Event,
    EventListener,
)
from watchdog.network.utils import MAC


class Bridge(Module):
    async def reload_deviceinfo(self, response=None):
        await self.async_logger.debug("reload device info")
        self.devicecontrol_info = await self.control.request_info()
        ignored = []
        await self.async_logger.debug("Got info of {} devices from dc backend".format(len(self.devicecontrol_info)))
        for device in self.devicecontrol_info.values():
            if device["status"] == 0:
                ignored += [MAC(device["deviceid.mac"])]
        self.whitelist_event = Event(["spoofer"], self.name, WHITELIST, ignored)
        await self.put_event(self.whitelist_event)

    async def broadcast_loop(self):
        while True:
            if self.whitelist_event:
                await self.put_event(self.whitelist_event)
            await asyncio.sleep(10)

    async def heartbeat(self):
        self.control.ws.register_callback("updateStatus", self.reload_deviceinfo)
        while True:
            await self.reload_deviceinfo()  # just reload for the case that we miss a notification from the backend and get out-of-sync
            # await self.devices.debug(self.async_logger)
            await asyncio.sleep(25)

    # TODO: rewrite this s.t. we register a ws callback for the respective action from the addon service that indicates changes to the addons
    async def refresh_addons(self):
        installed_addons = []
        while True:
            data = await self.addon.get_installed_addons()
            await self.async_logger.info("installed addons:", data)
            if data is not None:
                installed_addons = data["addonsList"]
            addons = [
                # (AddonReference("Adblocker", "adblocker-addon.git", "ffa698920181b926f288d3f3614ce32bf6dc5a13"), {}),
                # (AddonReference("Core_Addon", "core_addon.git", "cf8d997492c82b7fa348ea2ed756563354b4df66"), {}),
                # (AddonReference("ML_Addon", "ml_addon.git", "a2c297d39e10b6cabfb78790df33903c74f675b0"), {}),
            ]
            # TODO: get config for those addons, query endpoint for addon names
            # for addon in self.config.get("cloud.addons", []):
            #     config = await self.addon.get_config(addon[0], "NULL")
            #     addons += [(AddonReference(addon[0], addon[1], addon[2]), config)]
            # two for loops for legacy support of self.config
            for addon in installed_addons:
                addons += [(AddonReference(addon["addonName"], addon["gitURL"], addon["commitHash"]), addon["defaultConfig"])]
            addon_dict = {}
            for addon, _ in addons:
                addon_dict[addon.hash] = {"hash": addon.hash, "name": addon.name, "repo": addon.repo, "commit": addon.commit}
            # await self.async_logger.info("addons:", addon_dict)
            await self.put_event(Event(["addon_manager"], self.name, ADDONLIST, addon_dict))

            # TODO: here we sometimes send the ADDONCONFIG event before the ADDONLIST was processed,
            # TODO: the addon is not yet active, no major problem
            # send config event
            await asyncio.sleep(1)
            for addon, config in addons:
                # broadcast to all interceptors of this addon
                await self.put_event(Event([f"addon.{addon.hash}."], "bridge", ADDONCONFIG, config))

            await asyncio.sleep(5)

    async def debug_loop(self):
        # send some hand-crafted events for testing before the actual features are implemented
        await self.monitoring.uploadNotifications([{"level": 20, "time": time.time(), "sender": "Bridge", "message": "Watchdog started"}])
        while True:
            # await put_event(Event(["spoofer"], self.name, WHITELIST, [ArpNode(IP(0), MAC(m)) for m in [
            #     '22:a6:2f:1d:0f:dd',
            #     'b4:2e:99:f6:a0:01',
            #     '5c:41:5a:c4:18:a5',
            #     '00:1a:22:0f:32:90',
            #     # '44:09:b8:8d:0d:88',
            #     'c8:ff:77:7d:1c:0f',
            #     # 'dc:dc:e2:a7:e1:62',
            #     '04:d6:aa:c8:a6:30',
            # ]]))
            await asyncio.sleep(30)

    async def worker(self):
        queue = []
        while True:
            async with self.worker_cond:
                await self.worker_cond.wait()
                queue, self.worker_queue = self.worker_queue, []
            for x in queue:
                await x
            queue = []

    async def run_in_worker(self, task):
        async with self.worker_cond:
            self.worker_queue += [task]
            self.worker_cond.notify()

    async def on_deviceid_newdevice_event(self, event):
        # self.logger.verbose("newdevice", data)
        deviceid = event.data["id"]
        is_new_device = (await self.control.register_device(deviceid, 0))["success"]
        # self.logger.verbose("newdevice", data.items())
        for key, value in event.data.items():
            if not is_new_device and key == "first_seen":
                continue
            if value is None:
                continue
            # self.logger.verbose("updating option ", "deviceid.{}".format(key), value, deviceid)
            await self.control.update_option("deviceid.{}".format(key), value, deviceid=deviceid)
            # self.logger.verbose(resp)
        if is_new_device:
            await self.monitoring.uploadNotifications(
                [
                    {
                        "level": 20,
                        "time": event.data["first_seen"] if "first_seen" in event.data else time.time(),
                        "sender": "Device-Identification",
                        "message": "New device: " + json.dumps(event.data),
                    }
                ]
            )

    async def on_cloudlogging_event(self, event):
        await self.monitoring.uploadLogs(event.data["data"])

    async def on_notification_event(self, event):
        await self.monitoring.uploadNotifications(event.data["data"])

    async def run(self):
        self.worker_cond = asyncio.Condition()
        self.worker_queue = []
        self.whitelist_event = None
        self.config = Config()
        self.auth = AuthBackend(self.config.get("cloud.auth"), self.logger.inherit("auth"))
        self.control = ControlBackend(self.config.get("cloud.control"), self.auth, self.logger.inherit("control"))
        self.addon = AddonBackend(self.config.get("cloud.addon"), self.auth, self.logger.inherit("addon"))
        self.monitoring = MonitoringBackend(self.config.get("cloud.monitoring"), self.auth, self.logger.inherit("monitoring"))
        self.devicecontrol_info = {}
        self.event_listener = EventListener(self.events_in_queue, self.async_logger)
        self.event_listener.on_event[DEVICEID_NEWDEVICE] = self.on_deviceid_newdevice_event
        self.event_listener.on_event[CLOUDLOGGING] = self.on_cloudlogging_event
        self.event_listener.on_event[NOTIFICATION] = self.on_notification_event
        async with self.events_out_queue.open() as self.put_event:
            await asyncio.gather(
                self.control.ws.authenticate(),
                self.addon.ws.authenticate(),
                self.monitoring.ws.authenticate(),
            )
            await asyncio.gather(
                self.heartbeat(),
                self.event_listener.listen(),
                self.debug_loop(),
                self.worker(),
                self.broadcast_loop(),
                self.refresh_addons(),
            )
