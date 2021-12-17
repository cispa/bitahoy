from __future__ import annotations  # Allows to use MAC as typing hint instead of 'MAC'

import socket
from binascii import unhexlify
from struct import pack, unpack
from typing import Union

# Some nice classes to make stuff readable :)

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


class Interface:
    def __init__(self, name: str, mtu: int = 1500):
        self.name = name
        self.mtu = mtu

    def __eq__(self, other):
        return type(self) == type(other) and self.name == other.name and self.mtu == other.mtu

    def __str__(self):
        return self.name

    def __repr__(self):
        return str(self)

    def todict(self):
        return {"name": self.name, "mtu": self.mtu}

    @staticmethod
    def fromdict(data):
        return Interface(data["name"], data["mtu"])

    def serialize(self):
        return [self.mtu] + list(self.name.encode().ljust(30, b"\x00"))

    @staticmethod
    def unserialize(name):
        string = bytes(name[1:30]) + b"\x00"
        return Interface(string[: string.index(b"\x00")].decode(), name[0])


class MAC:
    def __init__(self, mac: Union[str, MAC, bytes]):
        self.mac: bytes
        if type(mac) == MAC:
            self.mac = mac.mac
        elif type(mac) == str:
            assert len(mac) == 6 * 2 + 5
            self.mac = unhexlify(mac.replace(":", ""))
        elif type(mac) == bytes:
            assert len(mac) == 6
            self.mac = mac
        else:
            raise NotImplementedError("MAC constructor does not support " + type(mac).__name__)

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
            with open("./data/oui.txt") as f:
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
    __slots__ = ["ip"]

    def __init__(self, ip: Union[str, int, bytes, IP]):
        if type(ip) == str:
            self.ip = socket.inet_aton(ip)
        elif type(ip) == int:
            self.ip = p32(ip)
        elif type(ip) == bytes:
            assert len(ip) == 4
            self.ip = ip
        elif type(ip) == type(self):
            self.ip = ip.ip
        else:
            raise NotImplementedError(f"Unsupported type '{type(ip)}' with value '{ip}'")
        assert len(self.ip) == 4

    def __eq__(self, other):
        if type(self) == type(other):
            return self.ip == other.ip
        else:
            return IP(other).ip == self.ip

    def debug(self):
        return socket.inet_ntoa(self.ip)

    def is_broadcast(self, network: Network):
        if self.ip == b"\xff\xff\xff\xff":
            return True
        elif network is None:
            return False
        else:
            return self.__eq__(network.broadcast())

    def __str__(self):
        return socket.inet_ntoa(self.ip)

    def __repr__(self):
        return f"IP({str(self)})"

    def __int__(self):
        return u32(self.ip)

    def __hash__(self):
        return hash(u32(self.ip))

    def __bytes__(self):
        return self.ip

    def __radd__(self, other):
        return other + self.__bytes__()

    def __add__(self, other):
        return self.__bytes__() + other

    def __getitem__(self, index):
        return self.ip[index]

    def __setitem__(self, index, value):
        self.ip[index] = value

    def serialize(self):
        return self.__int__()

    @staticmethod
    def unserialize(i):
        return IP(i)


class Network:
    def __init__(self, definition: str = None, ip: IP = None, range: int = -1):  # noqa: A002, VNE003
        if definition:
            self.ip = IP(definition.split("/")[0])
            self.range = int(definition.split("/")[1])
        elif ip and range != -1:
            self.ip = ip
            self.range = range
        else:
            raise ValueError()

    def __eq__(self, other):
        return type(self) == type(other) and self.ip == other.ip and self.range == other.range

    def __len__(self):
        return (2 ** (32 - self.range)) - 2

    def __str__(self):
        return f"{self.ip}/{self.range}"

    def __repr__(self):
        return str(self)

    def netmask(self):
        return IP(2 ** 32 - 1 - (2 ** (32 - self.range) - 1))

    def __contains__(self, addr_: IP):
        addr = int(addr_)
        ip = int(self.ip)
        return addr > ip and addr < ip + (2 ** (32 - self.range)) - 1

    def broadcast(self):
        return IP(int(self.ip) + (2 ** (32 - self.range)) - 1)

    def todict(self):
        return {"ip": self.ip.debug(), "range": self.range}

    @staticmethod
    def fromdict(data):
        return Network(ip=IP(data["ip"]), range=data["range"])

    def generator(self):
        ip = self.ip
        nrange = self.range

        def gen():
            for i in range(int(ip) + 1, int(ip) + (2 ** (32 - nrange)) - 1):
                yield IP(i)

        return gen

    def serialize(self):
        return (self.ip.serialize() << 6) | self.range

    @staticmethod
    def unserialize(i):
        return Network(ip=IP.unserialize(i >> 6), range=i & 0b111111)


class ArpNode:
    def __init__(self, ip: IP, mac: MAC):
        assert type(ip) == IP and type(mac) == MAC
        self.mac, self.ip = mac, ip

    def __eq__(self, other):
        return type(self) == type(other) and self.ip == other.ip and self.mac == other.mac

    def __str__(self):
        return "ArpNode(%s|%s)" % (self.mac, self.ip)

    def __repr__(self):
        return str(self)

    def todict(self):
        return {"ip": self.ip.debug(), "mac": str(self.mac)}

    @staticmethod
    def fromdict(data):
        return ArpNode(IP(data["ip"]), MAC(data["mac"]))


class NetConfig:
    def __init__(self, dev: Interface, box: ArpNode, gateway: ArpNode, network: Network):
        assert type(dev) == Interface
        assert type(box) == ArpNode
        assert type(gateway) == ArpNode
        assert type(network) == Network
        self.dev = dev
        self.box = box
        self.gateway = gateway
        self.network = network

    def __eq__(self, other):
        return (
            type(self) == type(other)
            and self.dev == other.dev
            and self.box == other.box
            and self.gateway == other.gateway
            and self.network == other.network
        )

    def __str__(self):
        return f"NetConfig(dev={self.dev}, gw={self.gateway}, net={self.network}, box={self.box})"

    def __repr__(self):
        return self.__str__()

    def todict(self):
        return {"dev": self.dev.todict(), "box": self.box.todict(), "gateway": self.gateway.todict(), "network": self.network.todict()}

    @staticmethod
    def fromdict(data):
        return NetConfig(
            Interface.fromdict(data["dev"]),
            ArpNode.fromdict(data["box"]),
            ArpNode.fromdict(data["gateway"]),
            Network.fromdict(data["network"]),
        )
