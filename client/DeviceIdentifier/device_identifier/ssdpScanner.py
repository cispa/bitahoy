#!/usr/bin/env python3
"""Send out a M-SEARCH request and listening for responses."""
import asyncio
import socket
import urllib
import traceback
import http.client
import io
import logging

from pprint import pprint
from typing import List

import ssdp  # python3 -m pip install ssdp
import xmltodict
import requests
import aiohttp

from bitahoy_sdk.addon.scanner import NetworkScanner
from bitahoy_sdk.network_utils import IPv4

__all__ = ["SSDPScanner"]

logger = logging.getLogger(__name__)

class SSDPResponse(object):
    class _FakeSocket(io.BytesIO):
        def makefile(self, *args, **kw):
            return self

    def __init__(self, response):
        r = http.client.HTTPResponse(self._FakeSocket(response))
        r.begin()
        self.location = r.getheader("location")
        self.usn = r.getheader("usn")
        self.st = r.getheader("st")
        self.cache = r.getheader("cache-control").split("=")[1]

    def __repr__(self):
        return "<SSDPResponse({location}, {st}, {usn})>".format(**self.__dict__)


def discover(service, timeout=5, retries=1, mx=3):
    group = ("239.255.255.250", 1900)
    message = "\r\n".join([
        'M-SEARCH * HTTP/1.1',
        'HOST: {0}:{1}',
        'MAN: "ssdp:discover"',
        'ST: {st}', 'MX: {mx}', '', ''])
    socket.setdefaulttimeout(timeout)
    responses = {}
    for _ in range(retries):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.sendto(message.format(*group, st=service, mx=mx).encode('utf-8'), group)
        while True:
            try:
                response = SSDPResponse(sock.recv(1024))
                responses[response.location] = response
                logger.debug('Got response from ' + str(response.location))
            except socket.timeout:
                break
    return list(responses.values())


services = {}  # Global variable used to add found devices in MyProtocol


class MyProtocol(ssdp.SimpleServiceDiscoveryProtocol):
    """Protocol to handle responses and requests."""

    def __init__(self):
        super().__init__()
        self.visited = set()
        # self.services = {}

    def response_received(self, response: ssdp.SSDPResponse, addr: tuple):
        """Handle an incoming response."""
        global services
        for name, value in response.headers:
            if name == 'LOCATION' and value not in self.visited:
                try:
                    url = urllib.parse.urlparse(value)
                    hostname = url.hostname
                    if hostname not in services:
                        services[hostname] = {}
                    xml = requests.get(value).text
                    parsed = xmltodict.parse(xml)
                    if value not in services[hostname]:
                        services[hostname][value] = parsed
                    self.visited.add(value)
                    # pprint(services)
                except Exception as e:
                    logger.info(f'Exception occured when communicating with {addr}')
                    logger.debug(traceback.format_exc())
                    continue

    def request_received(self, request: ssdp.SSDPRequest, addr: tuple):
        """Handle an incoming request."""
        pass

    def connection_lost(self, exc):
        print("Some strange error occured with ssdp. This ovwewrite prevents stopping the event loop")


class SSDPScanner(NetworkScanner):
    raw_flag = 'ssdp_raw'

    async def async_scan(self, devices: List[IPv4], options: dict):
        global services
        services = {}
        # Start the asyncio loop.
        loop = asyncio.get_event_loop()
        connect = loop.create_datagram_endpoint(MyProtocol, family=socket.AF_INET)
        transport, protocol = await connect

        # Send out an M-SEARCH request, requesting all service types.
        device_types = ['upnp:rootdevice', 'ssdp:all', 'urn:dslforum-org:device:InternetGatewayDevice:1']
        for device_type in device_types:
            search_request = ssdp.SSDPRequest(
                "M-SEARCH",
                headers={
                    "HOST": "239.255.255.250:1900",
                    "MAN": '"ssdp:discover"',
                    "MX": "4",
                    "ST": device_type,
                },
            )
            for _ in range(2):
                search_request.sendto(transport, (MyProtocol.MULTICAST_ADDRESS, 1900))
                await asyncio.sleep(0.2)
        await asyncio.sleep(5)
        transport.close()
        return services

    async def scan(self, devices: List[IPv4], options: dict):
        visited = set()
        devices = discover('ssdp:all')
        for device in devices:
            try:
                location = device.location
                if location not in visited:
                    url = urllib.parse.urlparse(location)
                    hostname = url.hostname
                    if hostname not in services:
                        services[hostname] = {}
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1.5)) as session:
                        async with session.get(location) as response:
                            xml = await response.text()
                    parsed = xmltodict.parse(xml)
                    if location not in services[hostname]:
                        services[hostname][location] = parsed
                    visited.add(location)
                    logger.debug(f'Got information from {location}')
            except aiohttp.client_exceptions.ClientConnectorError as e:
                logger.debug(f'Endpoint {location} is not reachable')
            except asyncio.TimeoutError as e:
                logger.debug(f'Connection with {location} timed out')
            except Exception as e:
                logger.info(f'Exception thrown when trying to parse ssdp info: {e}')
                logger.debug(traceback.format_exc())
        return services

    @staticmethod
    def parse_result(raw_dict) -> dict:
        """
        Use this function to parse the entries such that you get a dict with the desired fields
        name, model and manufacturer. They are empty if nothing usable was found.
        :return: dict of str
        """
        name = model = manufacturer = ''
        for endpoint, orderedDict in raw_dict.items():
            if 'root' in orderedDict and 'device' in orderedDict['root']:
                orderedDict = orderedDict['root']['device']
            if not name and 'friendlyName' in orderedDict:
                name = orderedDict['friendlyName']
            if not model and 'modelDescription' in orderedDict:
                model = orderedDict['modelDescription']
            if not model and 'modelName' in orderedDict:
                model = orderedDict['modelName']
            if not manufacturer and 'manufacturer' in orderedDict:
                manufacturer = orderedDict['manufacturer']
        return {'name': name,
                'model': model,
                'manufacturer': manufacturer,
                }


def main():
    # Start the asyncio loop.
    logging.basicConfig(level=logging.DEBUG)
    logger.setLevel(logging.DEBUG)
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(SSDPScanner().scan([], {}))
    print("Finished scan")
    pprint(result)
    for ip, data in result.items():
        print(SSDPScanner.parse_result(data))
    loop.close()


if __name__ == "__main__":
    main()
