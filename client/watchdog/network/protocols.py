from struct import pack
from typing import Union

from watchdog.network.checksums import ocooc
from watchdog.network.utils import IP, MAC, p16


def ip_packet(
    src,
    dst,
    payload,
    dsfield=0,
    identification=0,
    reserved=False,
    dontfragment=True,
    more_fragments=False,
    fragment_offset=0,
    ttl=64,
    proto=0,
) -> bytes:
    """Construct bytes of ip packet"""
    pckt = b"\x45"  # header len == 1
    pckt += bytes([dsfield])  # explicit congestion notification len == 1
    pckt += p16(len(payload) + 20)  # total length len == 2
    pckt += p16(identification)  # identification len == 2
    pckt += p16(fragment_offset | (0x4000 * dontfragment) | (0x8000 * reserved) | (0x2000 * more_fragments))  # Fragment offset
    pckt += bytes([ttl, proto])  # ttl + proto len == 2
    pckt += b"\x00\x00"  # header checksum len == 2
    pckt += bytes(src)  # Source ip len == 4
    pckt += bytes(dst)  # Destination ip len == 4
    pckt += payload
    return pckt[:10] + ocooc(pckt[:20]) + pckt[12:]  # Add checksum over headers


def arp_packet(
    dst_mac: Union[bytes, MAC],
    src_mac: Union[bytes, MAC],
    operation: int,
    sha: Union[bytes, MAC],
    spa: Union[bytes, IP],
    tha: Union[bytes, MAC],
    tpa: Union[bytes, IP],
    proto_type=0x0800,
):
    """
    Construct EthernetII frame + ARP packet with corresponding parameters
    For more information see https://en.wikipedia.org/wiki/Address_Resolution_Protocol
    Hardware type is not a parameter, since an Ethernet packet is constructed meaning it is 1
    :param dst_mac: Destination MAC
    :param src_mac: Source MAC
    :param operation: 1 for request and 2 for reply
    :param sha: Sender hardware address
    :param spa: Sender protocol address
    :param tha: Target hardware address
    :param tpa: Target protocol address
    :param proto_type: internetwork protocol for which the ARP request is intended For IPv4 value==0x800
    :return: EthernetII frame containing ARP packet in raw bytes
    """
    if type(dst_mac) == MAC:
        dst_mac = bytes(dst_mac)
    if type(src_mac) == MAC:
        src_mac = bytes(src_mac)
    if type(sha) == MAC:
        sha = bytes(sha)
    if type(tha) == MAC:
        tha = bytes(tha)
    if type(spa) == IP:
        spa = bytes(spa)
    if type(tpa) == IP:
        tpa = bytes(tpa)
    assert len(dst_mac) == len(src_mac) == 6 and type(dst_mac) == type(src_mac) == bytes
    assert 1 <= operation <= 2
    assert len(spa) == len(tpa) and type(spa) == type(tpa) == bytes and 0 < len(spa) < 256
    proto_len = len(spa)
    assert len(sha) == len(tha) and type(sha) == type(tha) == bytes and 0 < len(sha) < 256
    hw_len = len(sha)
    hw_type = 1  # Ethernet I think
    packet = dst_mac + src_mac
    packet += b"\x08\x06"  # Type ARP
    packet += p16(hw_type) + p16(proto_type)
    packet += bytes([hw_len]) + bytes([proto_len]) + p16(operation)
    packet += sha + spa + tha + tpa
    return packet


def icmp_echo(
    identifier: int = 0, sequencenumber: int = 0, timestamp: Union[int, None] = None, payload: bytes = b"bitahoy-watchdog"
) -> bytes:
    """
    Create raw icmp echo packet
    """
    pckt = bytes([8, 0, 0x00, 0x00])
    pckt += p16(identifier)
    pckt += p16(sequencenumber)
    if timestamp is not None:
        pckt += pack("<II", int(timestamp), 0)
    pckt += payload
    return pckt[:2] + ocooc(pckt) + pckt[4:]
