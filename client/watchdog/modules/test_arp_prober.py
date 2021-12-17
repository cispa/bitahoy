import asyncio

import pytest

from watchdog.network.discovery import get_netconfig
from watchdog.network.protocols import arp_packet


@pytest.mark.asyncio
@pytest.mark.networktest
async def test_arp_probe_correct_packets_sent(packet_capture, prober, send_packet_to_capture_last_one):
    prober, queue, logger_queue = prober
    assert bool(prober)  # check is alive
    # send blacklist through nodeconf
    await asyncio.sleep(4)
    send_packet_to_capture_last_one()
    conf = get_netconfig()
    box_mac = bytes(conf.box.mac)
    static_arp_args = (6 * b"\xff", box_mac, 1, box_mac, bytes(conf.box.ip), 6 * b"\xff")
    sent_packets = [p for description, p in packet_capture()]
    # skip first packet because box has ip .1 in test network
    expected_packets = [arp_packet(*static_arp_args, lookup_ip) for lookup_ip in conf.network.generator()()][1:]
    assert all([expected in sent_packets for expected in expected_packets])
