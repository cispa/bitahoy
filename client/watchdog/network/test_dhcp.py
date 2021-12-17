import time
from binascii import unhexlify

import pytest
from scapy.layers.dhcp import BOOTP, DHCP

from watchdog.network.dhcp import DHCPOptions, DHCPPacket, DHCPServer, Lease, LeaseDB
from watchdog.network.utils import IP, MAC, Network


@pytest.fixture
def server():
    return DHCPServer("iface", LeaseDB(Network("192.168.0.0/18"), []))


dhcp_discover_packet = unhexlify(
    "0101060051480c46000600000000000000000000000000000"
    "00000002271e9257ca600000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000"
    "000000000000000638253633501013d07012271e9257ca639020"
    "5dc3c0f616e64726f69642d646863702d31300c094f6e65506c7"
    "5733554370a0103060f1a1c333a3b2bff00"
)

dhcp_request_packet = unhexlify(
    "0101060051480c46000600000000000000000000000000000000"
    "00002271e9257ca6000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000"
    "0000638253633501033d07012271e9257ca63204c0a8b2023604"
    "c0a8b201390205dc3c0f616e64726f69642d646863702d31300c"
    "094f6e65506c75733554370a0103060f1a1c333a3b2bff00"
)


def test_dhcp_packet_is_bytes(server):
    assert type(server.generate_new_lease()) == bytes


def test_dhcp_packet_is_long_enough(server):
    assert len(server.generate_new_lease()) >= 236 + 4  # minimal length without options except cookie


def test_dhcp_parse_options_one_option():
    options = DHCPPacket.magic_cookie
    options += b"\x35"  # id 53 : Message Type
    options += b"\x02"  # length
    options += b"AA"  # payload
    packet = DHCPPacket()
    packet.parse_options(options)
    parsed = packet.options
    assert len(parsed) == 1
    assert parsed[0x35] == b"AA"


def test_dhcp_parse_options_two_options():
    options = DHCPPacket.magic_cookie
    options += b"\x35\x02AA"
    options += b"\x36\x02BB"
    packet = DHCPPacket()
    packet.parse_options(options)
    parsed = packet.options
    assert len(parsed) == 2
    assert parsed[0x35] == b"AA"
    assert parsed[0x36] == b"BB"


def test_dhcp_parse_options_recogniezs_out_of_bounds():
    options = DHCPPacket.magic_cookie
    options += b"\x35"  # id 53 : Message Type
    options += b"\x02"  # length
    options += b"A"  # payload4
    packet = DHCPPacket()
    packet.parse_options(options)
    parsed = packet.options
    assert len(parsed) == 0


def test_dhcp_parse_options_recogniezs_out_of_bounds_two_args():
    options = DHCPPacket.magic_cookie
    options += b"\x35\x02AA"
    options += b"\x36\x03BB"  # length 3 out of bound
    packet = DHCPPacket()
    packet.parse_options(options)
    parsed = packet.options
    assert len(parsed) == 1
    assert parsed[0x35] == b"AA"


def test_dhcp_parse_options_no_read_after_termination():
    options = DHCPPacket.magic_cookie
    options += b"\x35\x02AA"
    options += b"\xff\x00"  # length 3 out of bound
    options += b"\x36\x03BB"  # length 3 out of bound
    packet = DHCPPacket()
    packet.parse_options(options)
    parsed = packet.options
    assert len(parsed) == 1
    assert parsed[0x35] == b"AA"


def test_dhcp_packet_length_check():
    packet = DHCPPacket()
    assert len(bytes(packet)) == 241


def test_dhcp_parse_packet_with_options():
    options = b"\x35\x02AA"
    packet = DHCPPacket()
    packet.chaddr = b"\xff" * 6 + b"\x00" * 10
    # skip last byte of p since it is terminating char
    parsed = DHCPPacket.from_bytes(bytes(packet)[:-1] + options)
    assert bytes(parsed.chaddr) == bytes(packet.chaddr)
    assert parsed.options[0x35] == b"AA"


def test_dhcpoptions_set_lease_time():
    opts = DHCPOptions()
    opts.set_lease_time(1000)
    assert opts[51] == b"\x00\x00\x03\xe8"


def test_dhcpoption_settings_without_tftp():
    packet = DHCPPacket.prepare_basic_offer(DHCPPacket())
    packet.options.set_lease_time(100)
    packet.options.set_renewal_time(1000)
    packet.options.set_rebind_time(10000)
    packet.options.set_subnet(IP("255.255.255.0"))
    packet.options.set_broadcast_addr(IP("1.2.3.4"))
    packet.options.set_router(IP("192.168.1.1"))
    packet.options.set_dns_servers([IP("8.8.8.8")])
    packet.options.set_identifier(IP("10.10.10.107"))
    packet.options.set_type("OFFER")
    parsed = BOOTP(bytes(packet))
    assert parsed.haslayer(DHCP)
    dhcp = parsed[DHCP]
    options = {}
    for name, setting in dhcp.options[:-1]:  # skip the 'end' in the scapy parsed options
        options[name] = setting
    assert options["lease_time"] == 100
    assert options["renewal_time"] == 1000
    assert options["rebinding_time"] == 10000
    assert options["subnet_mask"] == "255.255.255.0"
    assert options["broadcast_address"] == "1.2.3.4"
    assert options["router"] == "192.168.1.1"
    assert options["name_server"] == "8.8.8.8"
    assert options["server_id"] == "10.10.10.107"
    assert options["message-type"] == 2


def test_good_response_to_discover(server):
    BOOTP(dhcp_discover_packet).show()
    response = server.handle_client(dhcp_discover_packet, ("1.2.3.4", 68))
    BOOTP(bytes(response)).show()


def test_lease_setter():
    nw = Network.fromdict({"ip": IP("192.168.0.0"), "range": 16})
    ip = IP("192.168.1.1")
    mac = MAC("aa:aa:aa:aa:aa:aa")
    lease = Lease(mac, ip, netmask=nw)
    assert ip == lease.ip


def test_lease_detect_invalid_ip():
    nw = Network.fromdict({"ip": IP("192.168.0.0"), "range": 24})
    ip = IP("192.168.1.1")
    mac = MAC("aa:aa:aa:aa:aa:aa")
    with pytest.raises(ValueError):
        Lease(mac, ip, netmask=nw)


def test_lease_is_expired_true():
    nw = Network.fromdict({"ip": IP("192.168.0.0"), "range": 24})
    ip = IP("192.168.0.1")
    mac = MAC("aa:aa:aa:aa:aa:aa")
    lease = Lease(mac, ip, lease_time=0, netmask=nw)
    time.sleep(0.01)
    assert lease.is_expired()


def test_lease_is_expired_false():
    nw = Network.fromdict({"ip": IP("192.168.0.0"), "range": 24})
    ip = IP("192.168.0.1")
    mac = MAC("aa:aa:aa:aa:aa:aa")
    lease = Lease(mac, ip, lease_time=100, netmask=nw)
    assert not lease.is_expired()


def test_dhcp_server_returns_valid_offer(server: DHCPServer):
    server
    offer = server.handle_client(dhcp_discover_packet, "")
    BOOTP(bytes(offer)).show()

    request = DHCPPacket.from_bytes(dhcp_request_packet)

    ack = server.handle_client(bytes(request), "")
    BOOTP(bytes(ack)).show()

    # check correct db entry
    assert server.db.get_lease(MAC(offer.chaddr[:6])).ip == "192.168.1.1"


def test_dhcp_server_returns_valid_offer_no_db_collision(server: DHCPServer):
    server
    offer = server.handle_client(dhcp_discover_packet, "")
    request = DHCPPacket.from_bytes(dhcp_request_packet)
    server.handle_client(bytes(request), "")
    assert server.db.get_lease(MAC(offer.chaddr[:6])).ip == "192.168.1.1"

    o2 = DHCPPacket.from_bytes(dhcp_discover_packet)
    o2.xid = b"\xbb" * 4
    o2.chaddr = b"\xaa" * 6
    offer = server.handle_client(bytes(o2), "")
    r2 = DHCPPacket.from_bytes(dhcp_request_packet)
    r2.xid = b"\xbb" * 4
    r2.chaddr = b"\xaa" * 6
    server.handle_client(bytes(r2), "")
    assert server.db.get_lease(MAC(offer.chaddr[:6])).ip == "192.168.2.2"


def test_dhcp_options_str_key():
    opt = DHCPOptions()
    opt[12] = b"asdf"
    assert opt["hostname"] == b"asdf"
    assert "hostname" in opt


def test_dhcp_options_str_key_setting():
    opt = DHCPOptions()
    opt["hostname"] = b"asdf"
    assert opt[12] == b"asdf"
    assert "hostname" in opt
    assert 12 in opt
    with pytest.raises(KeyError):
        opt["undef"] = 123
