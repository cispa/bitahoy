#    Representation of DHCP packet from https://tools.ietf.org/html/rfc2131#section-2
#    0                   1                   2                   3
#    0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
#    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#    |     op (1)    |   htype (1)   |   hlen (1)    |   hops (1)    |
#    +---------------+---------------+---------------+---------------+
#    |                            xid (4)                            |
#    +-------------------------------+-------------------------------+
#    |           secs (2)            |           flags (2)           |
#    +-------------------------------+-------------------------------+
#    |                          ciaddr  (4)                          |
#    +---------------------------------------------------------------+
#    |                          yiaddr  (4)                          |
#    +---------------------------------------------------------------+
#    |                          siaddr  (4)                          |
#    +---------------------------------------------------------------+
#    |                          giaddr  (4)                          |
#    +---------------------------------------------------------------+
#    |                                                               |
#    |                          chaddr  (16)                         |
#    |                                                               |
#    |                                                               |
#    +---------------------------------------------------------------+
#    |                                                               |
#    |                          sname   (64)                         |
#    +---------------------------------------------------------------+
#    |                                                               |
#    |                          file    (128)                        |
#    +---------------------------------------------------------------+
#    |                                                               |
#    |                          options (variable)                   |
#    +---------------------------------------------------------------+

# UDP 68         UDP 67     |
# c                s        |
#     Discovery             | Client sends broadcast to discover severs
# c -------------> s        |
#       Offer               | Server sends offer containing IP and metadata
# c <------------- s        |
#      Request              | Client acknowledges the request from the server
# c -------------> s        |
#     Acknowledge           | Server send another acknowledgement
# c <------------- s        |
from __future__ import annotations

import logging
import socket
import struct
import time
from typing import List

from watchdog.network.utils import IP, MAC, Network


class DHCPOptions(dict):
    _map_ = {
        1: ("subnet", 4),  # subnet
        51: ("lease_time", 4),  # lease time in seconds
        50: ("requested_addr", 4),  # requestsed ip
        60: ("vendor_class_id", -1),  # vendor class
        12: ("hostname", -1),  # host name
        -1: ("ip", 4),  # ip (not part of DHCP)
    }

    def __init__(self, *args, **kwargs):
        self.update(*args, **kwargs)

    def __getitem__(self, key):
        if type(key) == str:
            for num, data in self._map_.items():
                if key == data[0]:
                    result = dict.__getitem__(self, num)
                    break
        else:
            result = dict.__getitem__(self, key)
        return result

    def __setitem__(self, key, value):
        if type(key) == str:
            for num, data in self._map_.items():
                if key == data[0]:
                    dict.__setitem__(self, num, value)
                    break
            else:
                raise KeyError(key)
        else:
            dict.__setitem__(self, key, value)

    def __repr__(self):
        dictrepr = dict.__repr__(self)
        return "%s(%s)" % (type(self).__name__, dictrepr)

    def __bytes__(self):
        data = b""
        for key, value in self.items():
            data += bytes([key]) + bytes([len(value)]) + value
        assert type(data) == bytes
        return data + b"\xff"  # terminate properly

    def __contains__(self, item):
        if type(item) == str:
            for num, data in self._map_.items():
                if item == data[0]:
                    return super().__contains__(num)
        # no else because item could be e string that is not mapped to a dhcp option
        return super().__contains__(item)

    def update(self, *args, **kwargs):
        for key, value in dict(*args, **kwargs).items():
            self[key] = value

    def set_lease_time(self, time: int) -> None:
        self[51] = struct.pack(">I", time)

    def set_renewal_time(self, time: int) -> None:
        self[58] = struct.pack(">I", time)

    def set_rebind_time(self, time: int) -> None:
        self[59] = struct.pack(">I", time)

    def set_subnet(self, subnet: IP) -> None:
        self[1] = bytes(subnet)

    def set_broadcast_addr(self, broadcast: IP) -> None:
        self[28] = bytes(broadcast)

    def set_router(self, router: IP) -> None:
        self[3] = bytes(router)

    def set_dns_servers(self, dns_server: List[IP]) -> None:
        self[6] = b"".join([bytes(s) for s in dns_server])

    def set_tftp_server_name(self, tftp):
        self[66] = 0

    def set_boot_file(self, pxe_bin):
        self[67] = 0

    def set_boot_file_prefix(self, file_prefix):
        self[210] = 0

    def set_boot_file_configuration(self, file_prefix):
        self[209] = 0

    def set_identifier(self, addr: IP) -> None:
        self[54] = bytes(addr)

    def set_type(self, typ: str) -> None:
        if typ == "OFFER":
            self[53] = b"\x02"
        elif typ == "ACK":
            self[53] = b"\x05"
        else:
            raise NotImplementedError()


class DHCPPacket:
    magic_cookie = b"\x63\x82\x53\x63"  # BOOTP and a DHCP are the same protocol -> DHCP uses magic to clarify proto: Just append to options
    _fields_ = [
        ("op", 1),  # 1 = BOOTREQUEST, 2 = BOOTREPLY
        ("htype", 1),  # Hardware address type
        ("hlen", 1),  # Hardware address length (e.g.  '6' for 10mb ethernet)
        ("hops", 1),  # Client sets to zero, optionally used by relay agents when booting via a relay agent.
        ("xid", 1 * 4),  # Transaction ID, a random number from c, used as session cookie.
        ("secs", 1 * 2),  # Filled in by client, seconds elapsed since client began address acquisition or renewal process.
        ("flags", 1 * 2),  # Transaction ID, a random number from c, used as session cookie.
        (
            "ciaddr",
            1 * 4,
        ),  # Client IP address; only filled in if client is in BOUND, RENEW or REBINDING state and can respond to ARP requests.
        ("yiaddr", 1 * 4),  # 'your' (client) IP address.
        ("siaddr", 1 * 4),  # IP address of next server to use in bootstrap; returned in DHCPOFFER, DHCPACK by server.
        ("giaddr", 1 * 4),  # Relay agent IP address, used in booting via a relay agent.
        ("chaddr", 1 * 16),  # Client hardware address.
        ("sname", 1 * 64),  # Optional server host name, null terminated string.
        (
            "file",
            1 * 128,
        ),  # Boot file name, null terminated string; "generic" name or null in DHCPDISCOVER, fully qualified directory-path name in DHCPOFFER.
        # VARIABLE SIZE OPTIONS (can be up to 312 bytes long)
    ]

    def __init__(self):
        offset = 0
        self.options = DHCPOptions()
        for name, size in self._fields_:
            setattr(self, name, b"\x00" * size)
            offset += size

    @classmethod
    def prepare_basic_offer(cls, query) -> DHCPPacket:
        packet = cls()
        packet.op = b"\x02"  # Offer
        packet.htype = b"\x01"  # Ethernet
        packet.hlen = b"\x06"  # Len of MAC address
        packet.hops = bytes([ord(query.hops) + 1])

        packet.xid = query.xid
        packet.secs = struct.pack(">H", 0)  # dynamic time not supported
        packet.flags = b"\x80\x00" if query.flags[0] == b"\x00" else b"\x00\x00"
        packet.sname = b"Bitahoy Ghetto VLAN"
        packet.chaddr = query.chaddr  # set mac of client so broadcasts are recognizes
        return packet

    @classmethod
    def from_bytes(cls, data) -> DHCPPacket:
        packet = cls()
        assert type(data) == bytes
        offset = 0
        if len(data) > 236:
            options = data[236:]
            packet.parse_options(options)
            data = data[:236]

        for name, size in cls._fields_:
            setattr(packet, name, data[offset : offset + size])
            offset += size
        return packet

    def __bytes__(self):
        output = b""
        for name, size in self._fields_:
            param = getattr(self, name)
            if len(param) != size:
                raise ValueError(f"param size mismatch for {name}")
            output += param

        return output + self.magic_cookie + bytes(self.options)

    def __setattr__(self, key, value):
        fields = self._fields_
        for name, size in fields:
            if name == key:
                assert len(value) <= size, "Size for attribute " + str(len(value)) + " too large"
                if type(value) == str:
                    value = bytes(value, "ascii")
                elif type(value) != bytes:
                    raise AttributeError("You need to set this property to str or bytes")
                super().__setattr__(key, value.ljust(size, b"\x00"))
                return
        super().__setattr__(key, value)

    def __eq__(self, other):
        is_equal = False
        if type(other) == bytes:
            is_equal = bytes(self) == other
        elif type(other) == type(self):
            is_equal = bytes(other) == bytes(self)
        return is_equal

    def parse_options(self, data):
        assert len(data) <= 312 and data.startswith(DHCPPacket.magic_cookie)
        data = data[4:]  # skip cookie
        pos = 0
        while pos < len(data):
            typ = data[pos]
            if typ == 255:
                break
            length = data[pos + 1]
            if pos + 2 + length > len(data):
                # index out of bounds
                break
            self.options[typ] = data[pos + 2 : pos + 2 + length]
            pos += 2 + length


class LeaseDB:
    def __init__(self, network: Network, nodes: List[Lease]):
        self.network = network
        self.nodes = nodes

    def get_next_ip(self):
        for ip in self.network.generator()():
            if any(map(lambda lease: lease.octet == ip[2], self.nodes)):  # noqa: SIM114
                continue
            elif ip[2] == 0 or ip[3] == 0:  # reserve the 0 IP for the Router
                continue
            else:
                return ip

    def next_free_octet(self):
        ip = self.get_next_ip()
        return ip[2]

    def add_node(self, node):
        self.nodes.append(node)

    def get_lease(self, mac: MAC):
        for lease in self.nodes:
            if lease.mac == mac:
                return lease

    def safe(self, filename):
        raise NotImplementedError()


class Lease:
    def __init__(self, mac: MAC, ip: IP, lease_time=10000, netmask=None):
        if netmask is None:
            netmask = Network("192.168.0.0/18")
        self.ip = ip
        self.octet = ip[2]
        self.netmask = netmask
        self.mac = mac
        self.lease_time = time.time() + lease_time
        self.active = False
        if self.ip not in netmask:
            raise ValueError(f"{self.ip} not in {self.netmask}")

    def is_expired(self):
        return time.time() > self.lease_time


class DHCPServer:
    def __init__(self, interface, database: LeaseDB, bind_to="255.255.255.255"):
        self.interface = interface
        self.db = database
        self.socket = None
        self.bind_to = IP(bind_to)  # Should respond as IPv4 broadcast or not
        self.cache_db = False
        # config options
        self.dns_servers = [IP("8.8.8.8")]
        self.logger = logging.getLogger()
        self.gateway = IP("192.168.1.1")
        self.own_ip = IP("192.168.1.2")
        self.lease_time = 60 * 60 * 24  # in seconds
        self.logger = logging.getLogger("DHCPServer")
        self.logger.setLevel(logging.DEBUG)

    async def listen(self):
        """
        Start listening on UDP port 67
        """
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # UDP

        # https://www.freepascal.org/docs-html/current/rtl/sockets/index-2.html
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # Not sure we need this:
        self.socket.setsockopt(
            socket.SOL_SOCKET, 25, bytes(self.interface, "ascii") + b"\0"
        )  # http://fxr.watson.org/fxr/source/net/wanrouter/af_wanpipe.c?v=linux-2.6
        self.socket.bind(b"255.255.255.255", 67)  # And lets listen on port 67 broadcasts (UDP)
        self.main_so_id = self.socket.fileno()

        data, addr = self.socket.recvfrom(8192)  # Could potentially lower tihs value, not sure if that would gain anything tho.
        response = self.handle_client(data, addr)

        if response != DHCPPacket:
            if self.bind_to == "255.255.255.255":
                print("[-] Broadcasting back response")  # noqa: T001
                self.socket.sendto(response, ("255.255.255.255", 68))
            else:
                print("[-] Sending directly to {addr}")  # noqa: T001
                self.socket.sendto(response, (addr[0], 67))

            if self.cache_db:
                self.db.save(self.cache_dir + "/" + self.cache_db)

    def handle_client(self, data: bytes, addr) -> DHCPPacket:
        parsed_packet = DHCPPacket.from_bytes(data)
        msg_type = ord(parsed_packet.op)  # type: ignore
        response = DHCPPacket()
        if msg_type == 1:
            # BOOTREQUEST
            if 53 in parsed_packet.options:
                option = ord(parsed_packet.options[53])
                """
                1 = DHCP Discover message (DHCPDiscover).
                2 = DHCP Offer message (DHCPOffer).
                3 = DHCP Request message (DHCPRequest).
                4 = DHCP Decline message (DHCPDecline).
                5 = DHCP Acknowledgment message (DHCPAck).
                6 = DHCP Negative Acknowledgment message (DHCPNak).
                7 = DHCP Release message (DHCPRelease).
                8 = DHCP Informational message (DHCPInform).
                """
                if option == 1:
                    response = self.handle_discover(parsed_packet)
                elif option == 3:
                    response = self.handle_request(parsed_packet)

        elif msg_type == 2:
            # BOOTREPLY
            self.logger.warning("WARNING: ANOTHER DHCPServer found at " + str(addr))
        return response

    def create_main_response(self, query):
        response = DHCPPacket.prepare_basic_offer(query)
        response.options.set_identifier(self.bind_to)  # could be self.own_ip if broadcast flag is not set

        # We don't honor these, so we're generous with them:
        response.options.set_lease_time(43200)
        response.options.set_renewal_time(21600)
        response.options.set_rebind_time(37800)

        return response

    def handle_discover(self, discover: DHCPPacket) -> DHCPPacket:
        """Parse DHCPDISCOVER and return DHCPOFFER"""
        response = self.create_main_response(discover)
        response.options.set_type("OFFER")
        # give out appropriate IP and network details
        client_mac = MAC(discover.chaddr[:6])
        free_octet = self.db.next_free_octet()
        if free_octet is None:
            raise ValueError("Out of IPs")
        free_ip = IP(f"192.168.{free_octet}.{free_octet}")
        self.logger.debug(f"Got free IP {free_ip} from DB")
        response.yiaddr = bytes(free_ip)
        netmask = IP("255.255.255.0")  # TODO check if we assign ip to gateway  # noqa: T101

        response.options.set_subnet(netmask)
        response.options.set_broadcast_addr(IP(f"192.168.{free_octet}.255"))
        response.options.set_router(IP(f"192.168.{free_octet}.1"))
        response.options.set_dns_servers(self.dns_servers)  # TODO if dns severs are local adapt octet  # noqa: T101

        self.db.add_node(Lease(client_mac, free_ip))

        self.logger.info(f"Got DHCPDISCOVER request from {MAC(discover.chaddr[:6])} offering {free_ip}")
        return response

    def handle_request(self, request: DHCPPacket) -> DHCPPacket:
        """Parse DHCPREQUEST and return DHCPACK"""
        mac = MAC(request.chaddr[:6])
        response = self.create_main_response(request)
        response.options.set_type("ACK")
        self.logger.info(f"Got DHCPREQUEST request from {mac} acking known {self.db.get_lease(mac)}")
        return response

    def handle_release(self, release: DHCPPacket) -> bool:
        """Parse DHCPRELEASE and delete it from db. Returns True if entry was in db"""
        pass

    def generate_new_lease(self):
        return bytes(DHCPPacket())
