import asyncio
import logging
import sys

from pprint import pprint

from device_identifier import NetDiscoScanner
from bitahoy_sdk.network_utils import IPv4

# Roman logging
scan_logger = logging.getLogger()
scan_logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
scan_logger.addHandler(handler)


loop = asyncio.get_event_loop()
devices = loop.run_until_complete(NetDiscoScanner().scan([IPv4('192.168.1.104')], add_raw_to_output=True))
pprint(devices)
for ip, info in devices.items():
    print("Parsed result for IP {}: found a device called {} with the model-name {} manufactured by {}".format(ip,
                                                                                                               info['name'],
                                                                                                               info['model'],
                                                                                                               info['manufacturer']))
