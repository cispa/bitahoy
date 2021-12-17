#!/usr/bin/env python3
"""Module that implements netbios scans"""
import asyncio
import ipaddress
import socket
import select
from pprint import pprint
from typing import Optional, List
import os
import socket
import logging

from bitahoy_sdk.addon.scanner import NetworkScanner
from bitahoy_sdk.network_utils import IPv4

logger = logging.getLogger(__name__)


def decode_name(name):
    assert (len(name) == 32)
    assert (all(ord('A') <= ord(c) <= ord('P') for c in name))
    res = ""
    for upper, lower in zip(name[::2], name[1::2]):
        lower, upper = ord(lower), ord(upper)
        val = ((upper - 0x41) << 4) + (lower - 0x41)
        res += chr(val)
    assert (len(res) == 16)
    return res


assert (decode_name("EEEFFGEFEMEPFAENEFEOFECACACACACA") == "DEVELOPMENT     ")


def encode_name(name):
    assert (len(name) == 16)
    res = ""
    for c in name:
        res += chr(0x41 + (ord(c) >> 4))
        res += chr(0x41 + (ord(c) & 0x0f))
    assert (len(res) == 32)
    return res


assert (encode_name("DEVELOPMENT     ") == "EEEFFGEFEMEPFAENEFEOFECACACACACA")


def create_netbios_status(name="*") -> bytes:
    """Create NetBios NodeStatus request packet"""
    data = os.urandom(2) + \
           b"\x00\x00\x00\x01\x00\x00\x00\x00" + \
           b"\x00\x00\x20\x43\x4b\x41\x41\x41" + \
           b"\x41\x41\x41\x41\x41\x41\x41\x41" + \
           b"\x41\x41\x41\x41\x41\x41\x41\x41" + \
           b"\x41\x41\x41\x41\x41\x41\x41\x41" + \
           b"\x41\x41\x41\x00\x00\x21\x00\x01"
    name = "".join(encode_name(name.ljust(16, "\x00")))
    data = data[:13] + name.encode('utf-8') + data[-5:]
    return data


'''
print(encode_name("*".ljust(16, "\x00")))
print()
print(create_netbios_status())
print(create_netbios_status(name="\x01\x02__MSBROWSE__\x02\x01"))
print()
'''


def get_netbios_status_sync(ip: str, port: int = 137, timeout: int = 2) -> Optional[str]:
    """Synchronous alternative to get_netbios_status"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setblocking(False)
        #req = create_netbios_status(name="\x01\x02__MSBROWSE__\x02\x01")
        req = create_netbios_status()
        # print(len(req), repr(req))
        s.sendto(req, (ip, port))
        ready = select.select([s], [], [], timeout)
        if ready[0]:
            data = s.recv(256)
            return parse_nbstat(data)
    except OSError as e:
        return
    return


def parse_nbstat(data):
    if len(data) < 157:
        return
    data = data[50:]
    name_count = data[6]
    names = []
    data = data[7:]
    for i in range(name_count):
        names.append(data[:18])
        data = data[18:]
    result = {}
    for name in names:
        flags = (name[-2] << 8) + name[-1]
        if flags >> 15 == 1 and ((flags << 5) % 0xffff) >> 15 == 1:  # check if groupname and active
            result['groupname'] = name[:-3].strip()
        elif flags >> 15 == 0 and ((flags << 5) % 0xffff) >> 15 == 1:  # check if hostname and active
            result['hostname'] = name[:-3].strip()
    return result


t = b'c%\x84\x00\x00\x00\x00\x01\x00\x00\x00\x00 CKAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\x00\x00!\x00\x01\x00\x00\x00\x00\x00e\x03BITAHOYBATTLEST\x00\x04\x00WORKGROUP      \x00\x84\x00BITAHOYBATTLEST \x04\x00\xa8\xa1Y>\xee\xc9\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00t'
assert (parse_nbstat(t) == {'hostname': b'BITAHOYBATTLEST', 'groupname': b'WORKGROUP'})


def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def get_subnet(ip=get_ip()):
    """
    Assumption: subnet is /24, but could be bigger
    :param ip: String of local ip address
    :return: Easily iterable IPv4Network
    """
    return ipaddress.ip_network(ip + '/24', strict=False)


class Netbios:
    def __init__(self):
        self.entries = {}

    def scan(self, ips):
        # addresses = get_subnet()
        for ip in ips:
            ip = str(ip)
            logger.debug('Scanning ' + ip)
            res = get_netbios_status_sync(ip)
            if res:
                self.entries[ip] = res
        return self.entries


class NetbiosEntry:
    def __init__(self, ip: str, data: dict):
        self.ip = ip
        for key, value in data.items():
            setattr(self, key, value)


class NETBIOSScanner(NetworkScanner):
    """
    Broadcast mdns PTR queries and parse responses for device discovery
    """
    raw_flag = 'netbios_raw'

    async def scan(self, devices: List[IPv4], options: dict):
        if 'ip' in options and type(options['ip']) == list:
            ips = options['ip']
        elif devices:
            ips = [d.ip for d in devices]
        else:
            logger.warning('No ips provided! Netbios scan will be aborted due too time consumption')
            return {}
            ips = get_subnet()
        netbios = Netbios()
        netbios.scan(ips)
        return netbios.entries

    @staticmethod
    def parse_result(raw_dict) -> dict:
        """
        Use this function to parse the entries such that you get a dict with the desired fields
        name, model and manufacturer. They are empty if nothing usable was found.
        :return: dict of str
        """
        # example input {'192.168.1.104': {'groupname': b'WORKGROUP', 'hostname': b'BITAHOYBATTLEST'}}
        name = model = manufacturer = ''
        if 'hostname' in raw_dict:
            name = model = raw_dict['hostname']
        manufacturer = 'Microsoft'
        return {'name': name,
                'model': model,
                'manufacturer': manufacturer,
                }


def main():
    import sys
    logger.setLevel(logging.DEBUG)
    loop = asyncio.get_event_loop()
    if len(sys.argv) > 1:
        pprint(loop.run_until_complete(NETBIOSScanner().scan([IPv4(sys.argv[1])], {})))
    else:
        pprint(loop.run_until_complete(NETBIOSScanner().scan([], {})))


if __name__ == '__main__':
    main()
