from typing import Dict

from watchdog.network.packet import FailedLookup
from watchdog.network.utils import IP, MAC, Network


def correct_ethernet_header_receive(eth, gateway_mac: bytes, macs: Dict[IP, MAC], network: Network):
    """
    Spoofed clients think the packet is supposed to be sent to us,
    whereas the packet should look like a traffic capture between the 2 devices.
    Therefore we rewrite the addresses in the Ethernet header to mimic this behavior
    """
    dst = eth[30:34]
    src = eth[26:30]
    if dst in macs:
        dst_mac = macs[dst]
        if dst_mac is None:
            dst_mac = gateway_mac
    else:
        dst_mac = gateway_mac
        if IP(dst) in network:
            raise FailedLookup(str(IP(dst)))

    if src in macs:
        src_mac = macs[src]
        if src_mac is None:
            src_mac = gateway_mac
    else:
        src_mac = gateway_mac
        if IP(src) in network:
            raise FailedLookup(str(IP(src)))
    return dst_mac + src_mac + eth[12:]


def correct_ethernet_header_send(eth, gateway_mac: bytes, own_mac: bytes, macs: Dict[IP, MAC], network: Network):
    """
    Correct packet before send!
    Since the packet was patched in correct_target_mac we need to restore it,
    so it looks like it was sent from us, because the spoofed device thinks we are the real communication partner
    """
    dst = eth[30:34]
    dst_mac = macs.get(dst, gateway_mac)
    if dst_mac == gateway_mac and IP(dst) in network:
        raise FailedLookup(str(IP(dst)))
    src_mac = own_mac
    return dst_mac + src_mac + eth[12:]
