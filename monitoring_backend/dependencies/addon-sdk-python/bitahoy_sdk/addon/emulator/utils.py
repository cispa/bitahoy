import random
import time
import socket
from binascii import unhexlify
from struct import pack, unpack
import pkg_resources

class devices:
    pass

class Device:

    def __init__(self, mac, ip):
        self.mac = MAC(mac)
        self.tmp_ipv4 = IP(ip)
        self.first_seen = time.time()
        self.last_update = self.first_seen
        # != arpjet
        self.id = random.randint(0, 999999999)
        self.dhcp_vendor_class_id = None
        self.dhcp_hostname = None
        self.devicename = None
        self.devicemodel = None
        self.manufacturer = None

    def serialize(self):
        return {"id": str(self.id), "mac": str(self.mac), "ipv4": str(self.tmp_ipv4),
                "last_update": self.last_update, "first_seen": self.first_seen,
                "dhcp_vendor_class_id": self.dhcp_vendor_class_id, "dhcp_hostname": self.dhcp_hostname,
                "devicename": self.devicename, "devicemodel": self.devicemodel, "manufacturer": self.manufacturer}

    def debug(self):
        return str(self.serialize())


_MAC__vendors = None


def u64(data):
    return unpack(">Q", data.ljust(8, b"\x00"))[0]


def p64(data):
    return pack(">Q", data)


def u32(data):
    return unpack(">I", data.ljust(4, b"\x00"))[0]


def p32(data):
    return pack(">I", data)


def u16(data):
    """Unpack 2 or less bytes from Network byte order (Big Endian)
    >>> u16(b'\\x00\\x01')
    1

    >>> u16(b'\\x10\\x00')
    4096
    """
    return unpack(">H", data.ljust(2, b"\x00"))[0]


def p16(data):
    """Pack 16 bit unsigned to 16 bit Network byte order (Big Endian)
    >>> p16(1)
    b'\\x00\\x01'

    >>> p16(4096)
    b'\\x10\\x00'
    """
    return pack(">H", data)

class MAC:
    def __init__(self, mac):
        self.mac = mac
        if type(mac) == MAC:
            self.mac = mac.mac
        elif type(mac) == str:
            self.mac = unhexlify(mac.replace(":", ""))

    def __eq__(self, other):
        return type(self) == type(other) and self.mac == other.mac

    def __bytes__(self):
        return self.mac

    def __str__(self):
        return ":".join([hex(c)[2:].rjust(2, "0") for c in self.mac])

    def __radd__(self, other):
        return other + self.__bytes__()

    def __add__(self, other):
        return self.__bytes__() + other

    def vendor(self):
        global __vendors
        if not __vendors:
            __vendors = {}
            vendor_file = pkg_resources.resource_filename('bitahoy_sdk', 'data/oui.txt')
            with open(vendor_file) as f:
                for line in f.readlines():
                    if "base 16" not in line:
                        continue
                    __vendors[unhexlify(line[:6])] = line[22:-1]
        try:
            return __vendors[self.mac[:3]]
        except Exception:
            return "unknown"

    def serialize(self):
        return u64(self.mac.ljust(8, b"\x00"))

    @staticmethod
    def unserialize(i):
        return MAC(p64(i)[0:6])


class IP:
    def __init__(self, ip):
        if type(ip) == str:
            self.ip = socket.inet_aton(ip)
        elif type(ip) == int:
            self.ip = p32(ip)
        else:
            self.ip = ip

    def __eq__(self, other):
        return type(self) == type(other) and self.ip == other.ip

    def debug(self):
        return socket.inet_ntoa(self.ip)

    def is_broadcast(self, network):
        if self.ip == b"\xff\xff\xff\xff":
            return True
        elif network is None:
            return False
        else:
            return self.__eq__(network.broadcast())

    def __str__(self):
        return socket.inet_ntoa(self.ip)

    def __int__(self):
        return u32(self.ip)

    def __bytes__(self):
        return self.ip

    def __radd__(self, other):
        return other + self.__bytes__()

    def __add__(self, other):
        return self.__bytes__() + other

    def serialize(self):
        return self.__int__()

    @staticmethod
    def unserialize(i):
        return IP(i)