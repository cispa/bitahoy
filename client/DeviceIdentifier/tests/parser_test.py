import unittest
from constants import *
from device_identifier.mdnsScanner import MDNSScanner
from device_identifier.ssdpScanner import SSDPScanner


class TestParsingMethods(unittest.TestCase):
    def test_ssdp_parsing_archermr(self):
        result = {'name': 'Archer_MR200', 'model': 'AC750 Wireless Dual Band 4G LTE Router', 'manufacturer': 'TP-Link'}
        self.assertEqual(result, SSDPScanner.parse_result(ssdp_archer))

    def test_ssdp_parsing_sonos(self):
        result = {'manufacturer': 'Sonos, Inc.', 'model': 'Sonos One SL', 'name': '192.168.2.105 - Sonos One SL'}
        self.assertEqual(result, SSDPScanner.parse_result(ssdp_sonos))

    def test_ssdp_fritz_igd(self):
        result = {'manufacturer': 'AVM Berlin', 'model': 'FRITZ!Box 6660 Cable', 'name': 'InternetGatewayDeviceV2 - FRITZ!Box 6660 Cable'}
        self.assertEqual(result, SSDPScanner.parse_result(ssdp_fritz_igd))

    def test_ssdp_fritz_media(self):
        result = {'manufacturer': 'AVM Berlin', 'model': 'FRITZ!Box 6660 Cable', 'name': 'AVM FRITZ!Mediaserver'}

        self.assertEqual(result, SSDPScanner.parse_result(ssdp_fritz_media))

    def test_ssdp_fritz_router(self):
        result = {'manufacturer': 'AVM Berlin', 'model': 'FRITZ!Box 6660 Cable', 'name': 'FRITZ!Box 6660 Cable'}
        self.assertEqual(result, SSDPScanner.parse_result(ssdp_fritz_router))

    def test_mdns_parsing_googlehome(self):
        result = {'manufacturer': b'Google Home', 'model': b'Google Home', 'name': b'Lab speaker'}
        self.assertEqual(result, MDNSScanner.parse_result(mdns_google_home))


if __name__ == '__main__':
    unittest.main()