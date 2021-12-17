# https://github.com/bauerj/mac_vendor_lookup/blob/master/mac_vendor_lookup.py

# !/usr/bin/env python3
"""
Scanner collecting information about a device such as SSDP, mDNS and a couple more through the NetDisco Lib, plus a Netbios scanner written by Peter
Python modules 'requests' and 'xmltodict' are required
"""
import asyncio
import logging
import re
import sys
from typing import List
from pprint import pprint, pformat


from bitahoy_sdk.network_utils import IPv4
from bitahoy_sdk.addon.scanner import NetworkScanner
from bitahoy_sdk.addon.utils import Device

from device_identifier.mdnsScanner import MDNSScanner
from device_identifier.netbiosScanner import NETBIOSScanner
from device_identifier.ssdpScanner import SSDPScanner


def validate_ip(ip):
    return re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip)


def sanitize_name_model(attr):
    # check if IP addr is in string and remove it
    # attr = 'phl (192.168.0.1) @#$#%^^&%*((*!@   >><><?>:' #test
    found_ip_list = re.findall(r'[0-9]+(?:\.[0-9]+){3}', attr)
    if found_ip_list:
        for f_ip in found_ip_list:
            attr = attr.replace(f_ip, '')
    # remove special chars, besides single spaces
    no_special_char_attr = re.sub('([^a-zA-Z0-9 .,&_-])', '', attr)
    no_multi_space = re.sub(' +', ' ', no_special_char_attr)
    no_multi_space.strip()
    return no_special_char_attr

class NetDiscoScanner(NetworkScanner):
    """
    Scanner class returning ssdp, netbios and port scan information in json format
    """

    def __init__(self):
        pass

    async def scan(self, devices: List[IPv4], add_raw_to_output=True, raw_flag=False, xml_parse=False):
        """
        Scan device for information and return a dict with all device-results from network.
        Then filter them based on the flags stated (normally filter for queried device ip)
        :param devices: specific list of devices to target with non-broadcasting protocols
        :param options: methods key includes an array of possible flags: 'raw'
            'raw' flag to get raw output for debugging
            'xml_parse' flag to query XML links if available in SSDP results
        :return: return results for the target IP (if found) as a IdResult class that MUST include fields: name, model and manufacturer.
        """

        # execute the actual scan from the NetDisco Lib
        mdns = MDNSScanner()
        ssdp = SSDPScanner()
        netbios = NETBIOSScanner()
        mdns, ssdp, netbios = await asyncio.gather(
            mdns.scan(devices, {}),
            ssdp.scan(devices, {}),
            netbios.scan(devices, {}),
        )

        # neatly parse the scan results and pack them into one dict
        results = {}  # keep results

        def addinfo(result, new_result):
            """Add new parsed information to result. This allows to not overwrite attributes with an empty string"""
            if 'name' in new_result and new_result['name']:
                result['name'] = new_result['name']
            if 'model' in new_result and new_result['model']:
                result['model'] = new_result['model']
            if 'manufacturer' in new_result and new_result['manufacturer']:
                result['manufacturer'] = new_result['manufacturer']

        def createResults(results, result, type):
            for ip, data in result.items():
                if ip in results:
                    addinfo(results[ip], type.parse_result(data))
                else:
                    results[ip] = type.parse_result(data)
                if add_raw_to_output:
                    if type.raw_flag in results[ip]:
                        results[ip][type.raw_flag] += [data]
                    else:
                        results[ip][type.raw_flag] = [data]

        createResults(results, mdns, MDNSScanner)
        createResults(results, ssdp, SSDPScanner)
        createResults(results, netbios, NETBIOSScanner)

        # Set Default Values
        default_val = 'UNKNOWN'
        for ip, data in results.items():
            if not data['name']:
                data['name'] = default_val
            if not data['model']:
                data['model'] = default_val
            if not data['manufacturer']:
                data['manufacturer'] = default_val

        if raw_flag:  # for debugging
            print("\n\n-------------------------- ALL discovered devices results ----------------------------\n")
            pprint(results)
            print("\n\n------------------------------------Raw Data START------------------------------------\n")
            print("SSDP")
            pprint(ssdp)
            print("MDNS")
            pprint(mdns)
            print("NETBIOS")
            pprint(netbios)
            print("\nDevice ID Scan discovered {} devices in the network".format(len(results)))
            print("\n-------------------------------------Raw Data END---------------------------------------\n")

        return results


async def main():
    # Logging
    scan_logger = logging.getLogger(__name__)
    scan_logger = logging.getLogger()
    scan_logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    scan_logger.addHandler(handler)

    if len(sys.argv) >= 2:
        if validate_ip(sys.argv[1]):
            raw_flag = True if len(sys.argv) >= 3 and (sys.argv[2] == 'raw') else False

            scanner = NetDiscoScanner()
            res = await scanner.scan([IPv4(sys.argv[1])], raw_flag=raw_flag)

            print("---------------------------------------------------------------------------------------------")
            print(res)
            for ip, data in res.items():
                name, model, manufacturer = tuple(data.values())[0:3]
                print("Parsed result for IP {}: found a device called {} with the model-name {} manufactured by {}".format(ip, name, model, manufacturer))
        else:
            print("Invalid IP address format: ", sys.argv[1])
    else:
        print("Usage: ./DeviceIdentifier.py <ip> {raw= Boolean}")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
