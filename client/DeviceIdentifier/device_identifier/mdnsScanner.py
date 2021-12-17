#!/usr/bin/env python3
"""
mDNS service browser for device identification

"""

import argparse
import logging
import time
import asyncio
from abc import ABC
from typing import cast, Optional, Union, Tuple, Set, List

from bitahoy_sdk.addon.scanner import NetworkScanner
from bitahoy_sdk.network_utils import IPv4

from zeroconf import IPVersion, \
    ServiceBrowser, \
    ServiceStateChange, \
    Zeroconf, \
    DNSQuestion, DNSOutgoing, \
    current_time_millis, \
    _TYPE_PTR, _CLASS_IN, _FLAGS_QR_QUERY, ServiceListener, \
    InterfacesType, InterfaceChoice

logger = logging.getLogger(__name__)

# These search queries should find all available devices
# They also include the queries that the ZeroconfSerivceTypes.find looks for
# This list can be extended and I plan to using the devices FING queries
_SERVICES = ['_http._tcp.local.',
             '_hap._tcp.local.',
             '_device-info._tcp.local.',
             '_services._dns-sd._udp.local.',
             '_smb._tcp.local.'
             ]


# We create our own ServiceBrowser that sends queries in a constant interval
class ConstantDelayServiceBrowser(ServiceBrowser):
    def run(self) -> None:
        questions = [DNSQuestion(type_, _TYPE_PTR, _CLASS_IN) for type_ in self.types]
        self.zc.add_listener(self, questions)

        while True:
            now = current_time_millis()
            # Wait for the type has the smallest next time
            next_time = min(self._next_time.values())
            if len(self._handlers_to_call) == 0 and next_time > now:
                self.zc.wait(next_time - now)
            if self.zc.done or self.done:
                return
            now = current_time_millis()
            for type_ in self.types:
                if self._next_time[type_] > now:
                    continue
                out = DNSOutgoing(_FLAGS_QR_QUERY, multicast=self.multicast)
                out.add_question(DNSQuestion(type_, _TYPE_PTR, _CLASS_IN))
                for record in self._services[type_].values():
                    if not record.is_stale(now):
                        out.add_answer_at_time(record, now)

                self.zc.send(out, addr=self.addr, port=self.port)
                self._next_time[type_] = now + self._delay[type_]
                # Disable delay increase
                # self._delay[type_] = min(_BROWSER_BACKOFF_LIMIT * 1000, self._delay[type_] * 2)

            if len(self._handlers_to_call) > 0 and not self.zc.done:
                with self.zc._handlers_lock:
                    (name, service_type_state_change) = self._handlers_to_call.popitem(False)
                self._service_state_changed.fire(
                    zeroconf=self.zc,
                    service_type=service_type_state_change[0],
                    name=name,
                    state_change=service_type_state_change[1],
                )


class AggressiveZeroconfServiceTypes(ServiceListener, ABC):
    """
    Return all of the advertised services on any local networks
    """

    def __init__(self) -> None:
        self.found_services = set()  # type: Set[str]

    def add_service(self, zc: 'Zeroconf', type_: str, name: str) -> None:
        self.found_services.add(name)

    def remove_service(self, zc: 'Zeroconf', type_: str, name: str) -> None:
        pass

    @classmethod
    def find(
            cls,
            zc: Optional['Zeroconf'] = None,
            timeout: Union[int, float] = 10,
            interfaces: InterfacesType = InterfaceChoice.All,
            ip_version: Optional[IPVersion] = None,
            services=_SERVICES
    ) -> Tuple[str, ...]:
        """
        Return all of the advertised services on any local networks.

        :param zc: Zeroconf() instance.  Pass in if already have an
                instance running or if non-default interfaces are needed
        :param timeout: seconds to wait for any responses
        :param interfaces: interfaces to listen on.
        :param ip_version: IP protocol version to use.
        :return: tuple of service type strings
        """
        local_zc = zc or Zeroconf(interfaces=interfaces, ip_version=ip_version)
        listener = cls()
        browser = ConstantDelayServiceBrowser(local_zc, services, listener=listener, delay=750)

        # wait for responses
        time.sleep(timeout)

        # close down anything we opened
        if zc is None:
            local_zc.close()
        else:
            browser.cancel()

        return tuple(sorted(listener.found_services))


class mDNS_Scanner:
    """
    Scan for mDNS Services
    """

    def __init__(self, services: Union[str, list] = _SERVICES):
        self.zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
        self.services = services
        self.hosts = dict()

    def on_service_state_change(
            self, zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange
    ) -> None:
        logger.debug("Service %s of type %s state changed: %s" % (name, service_type, state_change))

        if state_change is ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)

            logger.debug("Info from zeroconf.get_service_info: %r" % (info))
            if info:
                addresses = ["%s:%d" % (addr, cast(int, info.port)) for addr in info.parsed_addresses()]
                logger.debug("  Addresses: %s" % ", ".join(addresses))
                logger.debug("  Weight: %d, priority: %d" % (info.weight, info.priority))
                logger.debug("  Server: %s" % (info.server,))
                if info.properties:
                    logger.debug("  Properties are:")
                    for key, value in info.properties.items():
                        logger.debug("    %s: %s" % (key, value))
                else:
                    logger.debug("  No properties")
                key = info.parsed_addresses(version=IPVersion.V4Only)[0]
                if key in self.hosts:
                    if info.name not in self.hosts[key]['Services']:
                        self.hosts[key]['Services'].append(info.name)
                else:
                    self.hosts[key] = {'Name': info.server,
                                       'Services': [info.name],
                                       'Addresses': info.parsed_addresses(),
                                       'Properties': []
                                       }
                if info.properties:
                    self.hosts[key]['Properties'] += [{info.server: info.properties}]
            else:
                logger.debug("  No info")


    def scan(self, min_runtime: Union[int, float] = 20):
        """
        Start the scan
        :param min_runtime: Minumin runtime in milliseconds
        :return: The list of discovered services
        """
        logger.debug("Looking for different services")
        services = list(AggressiveZeroconfServiceTypes.find(zc=self.zeroconf, timeout=int(min_runtime * 0.33)))
        logger.debug("Found services:" + str(services))
        if services:
            logger.debug("Now looking for more verbose service information")
            self.browser = ConstantDelayServiceBrowser(self.zeroconf, services, handlers=[self.on_service_state_change],
                                                       delay=1000)
        return services

    def stop(self):
        if hasattr(self, 'browser'):
            self.browser.cancel()
        self.zeroconf.close()

    @property
    def devices(self) -> dict:
        return self.hosts


class MDNSScanner(NetworkScanner):
    """
    Broadcast mdns PTR queries and parse responses for device discovery
    """
    raw_flag = 'mdns_raw'

    async def scan(self, devices: List[IPv4], options: dict):
        mdns = mDNS_Scanner()
        # only sleep when services were found during the discovery scan
        services = mdns.scan()
        if services:
            await asyncio.sleep(10)
        else:
            logger.debug('Aborting since no service names were discovered')
        mdns.stop()
        return mdns.devices

    @staticmethod
    def parse_result(raw_dict) -> dict:
        name = model = manufacturer = ''
        if 'Properties' in raw_dict:
            for property in raw_dict['Properties']:
                for key, data in property.items():
                    logger.debug(str(key) + ' ' + str(data))
                    if not name and b'fn' in data:
                        name = data[b'fn']
                    if not name and b'n' in data:
                        name = data[b'n']
                    if b'md' in data:
                        model = data[b'md']
                        manufacturer = model  # no better field present
        return {'name': name,
                'model': model,
                'manufacturer': manufacturer,
                }


def main():
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    from pprint import pprint

    loop = asyncio.get_event_loop()
    result = (loop.run_until_complete(MDNSScanner().scan([], {})))
    pprint(result)
    for ip, data in result.items():
        print(f'{ip}: {MDNSScanner.parse_result(data)}')


if __name__ == '__main__':
    main()