from bitahoy_sdk.exceptions import StubError
from bitahoy_sdk.stubs.logger import Logger
from bitahoy_sdk.addon.utils import ScanResult
from bitahoy_sdk.filter import TrafficFilter
from bitahoy_sdk.backend import BackendWS


class Addon:
    logger: Logger


class Scanner(Addon):

    def __init__(self):
        raise StubError("Do not use this class directly")

    async def report_result(self, result: ScanResult):
        # Reports back the scanner result for a device. Will be implemented by the framework. Calling this function multiple times will create multiple results, e.g. one result for each port in a portscan or one result for each detected vulnerability.
        pass


class RegisteredFilter:

    def __init__(self, interceptor):
        self.parent = interceptor

    async def remove(self):
        raise StubError("This method is implemented by the framework or emulator")

class InterceptorAPIDevices():


    def __init__(self, interceptorAPI):
        self._parent = interceptorAPI

    async def get_devices(self):
        raise StubError("This method is implemented by the framework or emulator")

class InterceptorAPI():

    def __init__(self, interceptor):
        self.interceptor = interceptor
        self.devices = InterceptorAPIDevices(self)
        raise StubError("Do not use this class")

    async def register_listener(self, on_packet: callable, trafficfilter: TrafficFilter, exclusive=False, avg_delay=60) -> RegisteredFilter:
        # registers a listener. Will be implemented by the framework.
        raise StubError("This method is implemented by the framework or emulator")

    async def set_config_callback(self, on_packet: callable):
        # sets a config callback. Will be implemented by the framework.
        raise StubError("This method is implemented by the framework or emulator")

    async def block_traffic(self, trafficfilter: TrafficFilter) -> RegisteredFilter:
        # blocks traffic based on a filter Will be implemented by the framework
        raise StubError("This method is implemented by the framework or emulator")

    async def connect_websocket(self, url: str, anonymous=False) -> BackendWS:
        if anonymous:
            get_token = None
        else:
            def get_token():
                return self.__emulator__get_token(url)
        return BackendWS(url, self.event_loop, get_token=get_token, logger=self.logger)


class Interceptor(Addon):

    def __init__(self):
        self.API = InterceptorAPI()
        raise StubError("Do not use this class directly. use bitahoy_sdk.addon.interceptor.Interceptor")

