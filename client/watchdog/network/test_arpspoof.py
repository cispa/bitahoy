from watchdog.network.protocols import arp_packet
from watchdog.network.utils import IP, MAC, ArpNode

receiver_mac = MAC("12:34:56:78:12:45")
receiver_ip = IP("192.168.1.1")
receiver = ArpNode(receiver_ip, receiver_mac)
to_spoof_mac = MAC("4f:3d:44:55:66:77")
to_spoof_ip = IP("192.168.1.10")
to_spoof = ArpNode(to_spoof_ip, to_spoof_mac)

target_mac = b"\x01\x02\x03\x04\x05\x06"


def test_ArpConstructionWithFunction():
    # I edited alex payloads for ARP Spoofing and make sure here that they are the same when build with arp_packet
    arp_response1 = (
        receiver.mac + target_mac + b"\x08\x06\x00\x01\x08\x00\x06\x04\x00\x02" + target_mac + to_spoof.ip + receiver.mac + receiver.ip
    )
    arp_response2 = arp_packet(receiver.mac, target_mac, 2, target_mac, to_spoof.ip, receiver.mac, receiver.ip)
    assert arp_response1 == arp_response2
    gratuitous_arp_req1 = (
        receiver.mac + target_mac + b"\x08\x06\x00\x01\x08\x00\x06\x04\x00\x01" + target_mac + to_spoof.ip + receiver.mac + receiver.ip
    )
    gratuitous_arp_req2 = arp_packet(receiver.mac, target_mac, 1, target_mac, to_spoof.ip, receiver.mac, receiver.ip)
    assert gratuitous_arp_req1 == gratuitous_arp_req2
    gratuitious_arp_resp1 = receiver.mac + target_mac + b"\x08\x06\x00\x01\x08\x00\x06\x04\x00\x02" + 2 * (target_mac + to_spoof.ip)
    gratuitious_arp_resp2 = arp_packet(receiver.mac, target_mac, 2, target_mac, to_spoof.ip, target_mac, to_spoof.ip)
    assert gratuitious_arp_resp1 == gratuitious_arp_resp2
