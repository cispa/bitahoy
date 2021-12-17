import time
from math import ceil

from watchdog.network.checksums import fix_ip_checksum
from watchdog.network.utils import IP, MAC, p16, u16


class FailedLookup(Exception):
    pass


class Packet:
    def __init__(self, eth, macs, conf):
        self.bytes = eth
        self.__box_mac = conf.box.mac
        self.__macs = macs
        self.__network = conf.network
        self.__gateway = conf.gateway.mac
        self.__broadcast = False  # IP(dst).is_broadcast(conf.network)
        self.__payload = eth[0xC:]
        self.__sendable_packet = None
        self.__received_at = time.time()

    def __lookup_ip(self, dst):
        if dst not in self.__macs or self.__macs[dst] is None:
            if IP(dst) in self.__network:
                raise FailedLookup(str(IP(dst)))
            return self.__gateway
        else:
            return self.__macs[dst]

    def get_sendable_packet(self):
        data = self.bytes
        srcip = IP(data[30:34])
        return self.__lookup_ip(bytes(srcip)) + bytes(self.__box_mac) + data[12:]

    def src_ip(self):
        return IP(self.get_sendable_packet()[0x1A : 0x1A + 4])

    def dst_ip(self):
        return IP(self.get_sendable_packet()[0x1A + 4 : 0x1A + 8])

    def src_mac(self):
        return MAC(self.__src_mac)

    def dst_mac(self):
        return MAC(self.__dst_mac)

    def received_at(self):
        return self.__received_at

    def transport_protocol(self):
        return self.get_sendable_packet()[23]

    def was_broadcast(self):
        return self.__broadcast

    def src_port(self):

        if self.transport_protocol() in [6, 17]:
            return (self.get_sendable_packet()[34] << 8) + self.get_sendable_packet()[35]
        return None

    def dst_port(self):
        if self.transport_protocol() in [6, 17]:
            return (self.get_sendable_packet()[36] << 8) + self.get_sendable_packet()[37]
        return None


def ip_header_length(raw_packet):
    return 4 * (raw_packet[14] & 0xF)


def transport_layer_offset(raw_packet):
    return 14 + 4 * (raw_packet[14] & 0xF)


def fragment(packet, chunksize=1480):
    """
    Fragment a packet into chunks of size chunksize.
    :param packet: The packet to fragment
    :return: A list of packets
    """
    assert chunksize % 8 == 0
    if len(packet) < 34:
        return [packet]
    eth, ip, payload = packet[0:14], packet[14:34], packet[34:]
    if chunksize <= 0 or len(payload) <= chunksize or len(ip) != 20 or eth[12:14] != b"\x08\x00":
        return [packet]
    else:
        res = []
        chunks = ceil(len(payload) / chunksize)
        for i in range(chunks):
            chunk = payload[i * chunksize : (i + 1) * chunksize]
            fo = u16(ip[6:8])
            flags = fo >> 13
            if (fo & 0b10) != 0:
                return [packet]
            mf = (flags & 0b1) != 0
            fo = (fo & 0b1111111111111) + (i * (chunksize // 8))
            fo |= (1 if i < (chunks - 1) else mf) << 13
            res.append(fix_ip_checksum(eth + ip[:2] + p16(len(chunk) + 20) + ip[4:6] + p16(fo) + ip[8:] + chunk))
        return res


def is_ip_fragment(packet):
    if len(packet) < 34:
        return False
    eth, ip, _ = packet[0:14], packet[14:34], packet[34:]
    if len(ip) != 20 or eth[12:14] != b"\x08\x00":
        return False
    fo = u16(ip[6:8])
    return fo not in [0, 0x4000, 0x8000]
