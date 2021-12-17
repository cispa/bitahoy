from struct import pack, unpack
from binascii import unhexlify
from socket import inet_ntoa, inet_aton
from typing import Optional

def u64(data):
    return unpack(">Q", data.ljust(8, b"\x00"))[0]

def p64(data):
    return pack(">Q", data)


def u32(data):
    return unpack(">I", data.ljust(4, b"\x00"))[0]

def p32(data):
    return pack(">I", data)


class MAC:
    def __init__(self, mac):
        self.mac = mac
        if type(mac) == MAC:
            self.mac = mac.mac
        elif type(mac) == str:
            self.mac = unhexlify(mac.replace(':', ''))

    def __eq__(self, other):
        return type(self) == type(other) and self.mac == other.mac

    def __bytes__(self):
        return self.mac

    def __str__(self):
        return ":".join([hex(c)[2:].rjust(2,"0") for c in self.mac])

    def __radd__(self, other):
        return other + self.__bytes__()

    def __add__(self, other):
        return self.__bytes__() + other

class Network:
    pass

class IP:

    ip : bytes
    network : Optional[Network]

    def __init__(self):
        raise NotImplementedError("Do not use this class directly. Use IPv4 or IPv6 instead")

    def __eq__(self, other):
        return type(self) == type(other) and self.ip == other.ip

    def is_broadcast(self, network):
        if self.ip == b"\xff\xff\xff\xff":
            return True
        elif network is None:
            return False
        else:
            return self.__eq__(network.broadcast())

    def ip_version(self):
        return 4 # IPv6 support soon

    def __str__(self):
        return inet_ntoa(self.ip)

    def __int__(self):
        return u32(self.ip)

    def __bytes__(self):
        return self.ip

    def __radd__(self, other):
        return other + self.__bytes__()

    def __add__(self, other):
        return self.__bytes__() + other



class IPv4(IP):

    def __init__(self, ip):
        if type(ip) == str:
            self.ip = inet_aton(ip)
        elif type(ip) == int:
            self.ip = p32(ip)
        else:
            self.ip = ip



class IPv4Network(Network):
    def __init__(self, definition: str = None, ip: IP=None, range: int = -1):
        if definition:
            self.ip = IPv4(definition.split("/")[0])
            self.range = int(definition.split("/")[1])
        elif ip and range != -1:
            self.ip = ip
            self.range = range
        else:
            raise ValueError()

    def __eq__(self, other):
        return type(self) == type(other) and self.ip == other.ip and self.range == other.range

    def __len__(self):
        return (2**(32-self.range)) - 2

    def __contains__(self, addr_:IP):
        addr = int(addr_)
        ip = int(self.ip)
        return addr > ip and addr < ip+(2**(32-self.range))-1

    def broadcast(self):
        return IPv4(int(self.ip)+(2**(32-self.range))-1)

    def todict(self):
        return {"ip": self.ip.debug(), "range": self.range}

    @staticmethod
    def fromdict(data):
        return IPv4Network(ip=IPv4(data["ip"]), range=data["range"])

    def generator(self):
        ip = self.ip
        nrange = self.range

        def gen():
            for i in range(int(ip)+1, int(ip)+(2**(32-nrange))-1):
                yield IPv4(i)
        return gen
