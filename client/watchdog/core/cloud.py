import asyncio
import time

import aiohttp
from bitahoy_sdk.backend import BackendWS

requests_exceptions = (aiohttp.ClientError,)

default_backends = {
    "auth": "https://auth.bitahoy.cloud",
    "control": "https://control.bitahoy.cloud",
    "monitoring": "https://monitoring.bitahoy.cloud",
    "update": "https://update.bitahoy.cloud",
    "addon": "https://addon.bitahoy.cloud",
    "ai": "https://ml.bitahoy.cloud",
}


class BaseBackend:  # noqa: SIM119
    def __init__(self):
        self.s = None

    async def session(self):
        if not self.s:
            self.s = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5))
        return self.s


class AuthBackend(BaseBackend):
    def __init__(self, config=None, logger=None):
        self.url = default_backends["auth"]
        self.wdcode = ""
        try:
            with open("/sys/firmware/devicetree/base/serial-number", "rb") as f:
                self.wdcode = f.read().replace(b"\x00", b"").decode().strip()
                assert len(self.wdcode) == 16
        except FileNotFoundError:
            if config and "wdcode" in config:
                self.wdcode = config["wdcode"]
        try:
            with open("./secret.txt", "r") as f:
                self.secret = f.read().strip()
        except FileNotFoundError:
            self.secret = ""
        if len(self.secret) != 16:
            with open("./secret.txt", "w") as f:
                import secrets

                self.secret = secrets.token_hex(8)
                assert len(self.secret) == 16
                f.write(self.secret)
        if config and "url" in config:
            self.url = config["url"]
        if config and "secret" in config:
            self.secret = config["secret"]
        self.__cached_token = (0, b"")

        super().__init__()

    async def request_token(self, nocache=False):
        if not nocache and self.__cached_token[0] > time.time():
            return self.__cached_token[1]
        for i in range(3):
            try:
                async with (await self.session()).get(
                    self.url + "/authenticateWatchdog", json={"wdcode": self.wdcode, "secret": self.secret}
                ) as response:
                    try:
                        assert response.status == 200
                        res = await response.json()
                        assert res["success"] is True
                        self.__cached_token = (time.time() + 60, res["token"])
                        return res["token"]
                    except Exception:
                        raise Exception(
                            (await response.text()) + " " + repr({"wdcode": self.wdcode, "secret": self.secret}), response.status
                        )
            except (aiohttp.ClientError, asyncio.exceptions.TimeoutError) as e:
                await asyncio.sleep(0.5 * (i + 1))
                if i >= 2:
                    raise e


class ControlBackend(BaseBackend):
    def __init__(self, config, auth_backend: AuthBackend, logger=None):
        self.url = default_backends["control"]
        if config and "url" in config:
            self.url = config["url"]
        self.request_token = auth_backend.request_token
        self.logger = logger.asyncio()
        self.ws = BackendWS(self.url + "/ws", self.request_token, logger=logger)
        super().__init__()

    async def ping(self):
        await self.logger.info(await self.ws.request({"action": "ping"}))

    async def register_device(self, deviceid, devicetype):
        resp = await self.ws.request({"action": "registerDevice", "deviceid": deviceid, "devicetype": devicetype})
        await self.logger.info("register_device", deviceid, devicetype, resp)
        return resp

    async def update_option(self, key, value, deviceid=0):
        return await self.ws.request({"action": "updateOption", "key": key, "value": value, "deviceid": deviceid})

    async def request_info(self):
        # await self.logger.error(await self.request_token())
        return (await self.ws.request({"action": "requestInfo"}))["data"]


class MonitoringBackend(BaseBackend):
    def __init__(self, config, auth_backend: AuthBackend, logger=None):
        self.url = default_backends["monitoring"]
        if config and "url" in config:
            self.url = config["url"]
        self.request_token = auth_backend.request_token
        self.ws = BackendWS(self.url + "/ws", self.request_token, logger=logger)
        self.logger = logger.asyncio()
        super().__init__()

    async def ping(self):
        await self.logger.info(await self.ws.request({"action": "ping"}))

    async def uploadLogs(self, logs):
        resp = await self.ws.request({"action": "uploadLogs", "logs": logs})
        await self.logger.info("uploadLogs", resp)
        return resp

    async def uploadNotifications(self, notifications):

        await self.logger.info("uploadNotifications", notifications)
        resp = await self.ws.request({"action": "uploadNotifications", "notifications": notifications})
        await self.logger.info("uploadNotifications", resp)
        return resp


class AddonBackend(BaseBackend):
    def __init__(self, config, auth_backend: AuthBackend, logger=None):
        self.url = default_backends["addon"]
        if config and "url" in config:
            self.url = config["url"]
        self.request_token = auth_backend.request_token
        self.ws = BackendWS(self.url + "/ws", self.request_token, logger=logger)
        self.logger = logger.asyncio()
        self.typesList = None
        super().__init__()

    async def get_installed_addons(self):
        resp = await self.ws.request({"action": "getAddon", "info": {"timestamp": time.time()}})
        if resp["success"]:
            return resp
        else:
            return None

    async def get_config(self, addonName, deviceName):
        resp = await self.ws.request(
            {"action": "getAddon", "info": {"addonName": addonName.lower(), "deviceName": deviceName, "timestamp": time.time()}}
        )
        if resp["success"]:
            return resp["addon"]["config"]
        else:
            return None

    async def ping(self):
        await self.logger.info(await self.ws.request({"action": "ping"}))


class AIBackend(BaseBackend):
    def __init__(self, config, auth_backend: AuthBackend, logger=None):
        self.url = default_backends["ai"]
        if config and "url" in config:
            self.url = config["url"]
        self.request_token = auth_backend.request_token
        self.ws = BackendWS(self.url + "/ws", self.request_token, logger=logger)
        self.logger = logger.asyncio()
        super().__init__()

    async def ping(self):
        await self.logger.info("ping now")
        await self.logger.info(await self.ws.request({"action": "ping"}))
        await self.logger.info("done")
