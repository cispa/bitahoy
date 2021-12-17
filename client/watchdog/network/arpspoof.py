import itertools
from typing import List

from watchdog.network.protocols import arp_packet, icmp_echo, ip_packet
from watchdog.network.utils import MAC, ArpNode, Interface


def build_arp_packets(
    receiver: ArpNode, to_spoof: ArpNode, target_mac: MAC, broadcast=False, gratuitous_arp_req=False, gratuitious_arp_resp=False
) -> List[bytes]:
    """
    Build Arp spoofing packets redirecting the the receiver to target_mac when connecting with to_spoof
    :param receiver: The ArpNode that should be spoofed
    :param to_spoof: The ArpNode that should be redirected to target_mac when the receiver wants to communicate with it
    :param target_mac: The MAC that should be mapped to the IP Address of to_spoof for receiver
    :param broadcast: Wheather a ARP broadcasting packet should be added as well (some routers only forward broadcasts)
    :param gratuitous_arp_req: Add gratuitous_arp_req packet to result
    :param gratuitious_arp_resp: Add gratuitious_arp_resp packet to result
    :return: List of ARP packets to send
    """
    assert type(target_mac) == MAC
    packets = []
    # Add an icmp_echo in order to force devices to respond, which forces them to do an ARP loopkup
    # Then we already send the responses that the client should be looking for
    ping = icmp_echo(payload=b"bitahoy.com", identifier=0)  # payload in icmp can be anything
    ping = ip_packet(bytes(to_spoof.ip), bytes(receiver.ip), ping, identification=1, proto=1, dontfragment=False)  # Add IP Layer
    ping_request = bytes(receiver.mac) + bytes(target_mac) + b"\x08\x00" + ping  # Add ethernet layer

    packets += [ping_request]
    packet_params = (2, target_mac, to_spoof.ip, receiver.mac, receiver.ip)
    arp_response = arp_packet(receiver.mac, target_mac, *packet_params)

    packets += [arp_response]

    if broadcast:
        # Some routers (e.g. D-Link dir-878) seem to be blocking unicast arp reponses. send broadcasts to get around this.
        # Downside: we no longer can exclude devices from being spoofed
        packets.append(arp_packet(b"\xff" * 6, target_mac, *packet_params))

    # Weird methods for arp spoofing. Ask Alex what they do
    if gratuitous_arp_req:
        packets.append(arp_packet(receiver.mac, target_mac, 1, target_mac, to_spoof.ip, receiver.mac, receiver.ip))
    if gratuitious_arp_resp:
        packets.append(arp_packet(receiver.mac, target_mac, 2, target_mac, to_spoof.ip, target_mac, to_spoof.ip))

    return packets


class Spoofer:
    def __init__(self, nodes, gateway, ownmac, interface: Interface, config):
        self.comb = list(itertools.permutations(nodes, 2))
        self.packets = []
        self.config = config
        for node1, node2 in self.comb:
            self.packets += [self.build_packets(node1, node2, ownmac)]
        self.interface = interface

    def build_packets(self, n1: ArpNode, n2: ArpNode, ownmac: MAC):
        return build_arp_packets(n1, n2, ownmac, broadcast=self.config.get("spoofer.arp_broadcast", True))
