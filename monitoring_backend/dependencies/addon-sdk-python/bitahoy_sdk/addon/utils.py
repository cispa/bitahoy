from bitahoy_sdk.network_utils import IP, MAC, Network
from bitahoy_sdk.exceptions import StubError
from typing import Optional
import time

class ScanResult():

    def __init__(self, device, title: str, description=None, link=None, level=50):
        self.device = device
        self.title = title
        self.description = description
        self.link = link
        self.level = level

    def __str__(self):
        return str(dict(self))

    #device: Device
    title: str
    description: Optional[str]
    link: Optional[str]
    level: int


class ScannedDevice:

    def __init__(self):
        raise StubError("Do not create this class, only use the instances passed to the module by the framework")

    def result(self, title: str, description=None, link=None, level=50) -> ScanResult:
        return ScanResult(self, title=title, description=description, link=link, level=level)

    ip: IP
    mac: MAC
    network: Network
    mac_vendor: Optional[str]
    dhcp_name: Optional[str]
    pass



class Device:

    def __init__(self, node):
        self.mac = node.mac
        self.tmp_ipv4 = node.ip
        self.first_seen = time.time()
        self.last_update = self.first_seen
        self.id = None
        self.dhcp_vendor_class_id = None
        self.dhcp_hostname = None
        self.devicename = None
        self.devicemodel = None
        self.manufacturer = None

    def serialize(self):
        return {"id": str(self.id), "mac": str(self.mac), "ipv4": str(self.tmp_ipv4), "last_update": self.last_update, "first_seen": self.first_seen, "dhcp_vendor_class_id": self.dhcp_vendor_class_id, "dhcp_hostname": self.dhcp_hostname, "devicename": self.devicename, "devicemodel": self.devicemodel, "manufacturer": self.manufacturer}

    def debug(self):
        return str(self.serialize())
