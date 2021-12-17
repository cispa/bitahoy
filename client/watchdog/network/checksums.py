from typing import List, Union

from watchdog.network.utils import p16, u16


def fix_ip_checksum(packet: bytes) -> bytes:
    """
    Overwrite IPv4 checksum in EthernetII packet if it has the length of an EthernetII packet
    :param packet: EthernetII + IPv4 packet
    :return: The whole packet with the IPv4 checksum or unmodified packet if it is too short
    """
    if len(packet) < 34:
        # invalid IP packet
        return packet
    return packet[:24] + ocooc(packet[14:24] + packet[26:34]) + packet[26:]


def fix_ip_checksum_fast(packet: bytes) -> bytes:
    """
    Overwrite IPv4 checksum with zero for EthernetII packet if it has the length of an EthernetII packet
    :param packet: EthernetII + IPv4 packet
    :return: The whole packet where checksum is overwritten with b"\x00\x00" or unmodified packet it it is too short
    """
    if len(packet) < 34:
        # invalid IP packet
        return packet
    return packet[:24] + b"\x00\x00" + packet[26:]


def fix_udp_checksum_fast(packet: bytes) -> bytes:
    """
    Overwrite checksum with b"\x00\x00" as UDP checksum to an EthernetII frame
    :param packet: Raw bytes of EthernetII frame
    :return: Raw bytes of packet with b"\x00\x00" UDP checksum added
    """
    if len(packet) < 42 or packet[23] != 0x11:
        # invalid UDP packet
        return packet
    return packet[:40] + b"\x00\x00" + packet[42:]  # udp checksum is optional, so we can just set it to 0


def ocooc(data: Union[bytes, List[int]]) -> bytes:
    """Compute Internet checksum (RFC 1071)"""
    checksum = 0
    odd = 1

    for char in list(data):
        checksum += char << (8 * odd)
        odd ^= 1
    checksum = (checksum & 0xFFFF) + (checksum >> 16)
    checksum = ~checksum & 0xFFFF
    return bytes([(checksum >> 8), checksum & 0xFF])


def fix_udp_checksum(packet: bytes) -> bytes:
    if len(packet) < 42 or packet[23] != 0x11:
        # invalid UDP packet
        return packet
    ip_hdr_size = 4 * (packet[14] & 0xF)
    transport_layer_offset = ip_hdr_size + 14
    if len(packet) < transport_layer_offset + 8:
        # invalid UDP packet
        return packet
    pseudo_ip_header = packet[26:30] + packet[30:34] + bytes([0, 0x11]) + packet[transport_layer_offset + 4 : transport_layer_offset + 6]
    msg = list(packet[transport_layer_offset:])
    msg[6:8] = [0, 0]
    msg[6:8] = ocooc(list(pseudo_ip_header) + msg)
    return packet[:transport_layer_offset] + bytes(msg)


def fix_tcp_checksum(packet):
    if len(packet) < 54 or packet[23] != 6:
        # invalid TCP packet
        return packet
    ip_hdr_size = 4 * (packet[14] & 0xF)
    transport_layer_offset = ip_hdr_size + 14
    if len(packet) < transport_layer_offset:
        # invalid UDP packet
        return packet
    pseudo_ip_header = packet[26:30] + packet[30:34] + bytes([0, 6]) + p16(u16(packet[16:18]) - ip_hdr_size)
    msg = list(packet[transport_layer_offset:])
    msg[16:18] = [0, 0]
    msg[16:18] = ocooc(list(pseudo_ip_header) + msg)
    return packet[:transport_layer_offset] + bytes(msg)
