from bitahoy_sdk.addon.utils import Device
from bitahoy_sdk.stubs.addon import Scanner
from typing import List

class DeviceScanner(Scanner):

    def __init__(self):
        pass

    async def scan(self, device: Device, options: dict):
        raise NotImplementedError("")

class NetworkScanner(Scanner):

    def __init__(self):
        pass

    async def scan(self, devices: List[Device], options: dict):
        raise NotImplementedError("")