import asyncio
import datetime
import os
import signal
import time
from pprint import pprint
from socket import AF_PACKET, SOCK_RAW, socket

import pytest

from watchdog.ipc.event import NODECONFIG, WHITELIST, Event
from watchdog.network.discovery import get_netconfig
from watchdog.network.protocols import arp_packet
from watchdog.network.utils import IP, MAC, ArpNode


@pytest.mark.networktest
def test_packet_capture_works(packet_capture):
    conf = get_netconfig()
    sock = socket(AF_PACKET, SOCK_RAW)
    sock.bind((conf.dev.name, 0))
    time.sleep(1)
    dst_mac = MAC("22:22:22:22:22:22")
    src_ip = IP("192.168.69.10")
    dst_ip = IP("192.168.69.20")
    for i in range(6):
        src_mac = MAC(f"11:11:11:11:11:1{i}")
        packet = arp_packet(dst_mac, src_mac, 2, src_mac, src_ip, dst_mac, dst_ip)
        sock.send(packet)
        time.sleep(0.05)
    time.sleep(0.1)
    packets = packet_capture()
    pprint(packets)  # noqa: T003
    # we miss the last packet, since we know a packet is finished when we get a header of a new packet
    assert len(packets) >= 5


@pytest.mark.networktest
@pytest.mark.asyncio
async def test_correct_arp_packets_sent(
    spoofer, packet_capture, send_packet_to_capture_last_one
):  # noqa: F811 pytest fixtures not known by flake8
    spoofer, queue, logger_queue = spoofer
    assert bool(spoofer)
    # Send node[s] to be spoofed
    node1 = ArpNode(IP("192.168.1.100"), MAC("12:34:56:78:9a:bc"))
    node2 = ArpNode(IP("192.168.1.50"), MAC("aa:bb:aa:cc:aa:bb"))
    conf = get_netconfig()
    iface_mac = bytes(conf.box.mac)
    node_event = Event(spoofer.module.name, "anonymous", NODECONFIG, {"nodes": [node1, node2], "conf": conf})
    await spoofer.send(node_event)
    blacklist_event = Event(spoofer.module.name, "bridge", WHITELIST, [])
    await spoofer.send(blacklist_event)
    print("Sent events on", datetime.datetime.now())  # noqa: T001

    # Verify that the correct packets were sent
    expected_packets = [
        b"\x124Vx\x9a\xbc"
        + iface_mac
        + b"\x08\x00E\x00\x00'\x00\x01\x00\x00@\x01\xf6\xee\xc0\xa8\x012\xc0\xa8\x01d\x08\x00o'\x00\x00\x00\x00bitahoy.com",
        b"\x124Vx\x9a\xbc"
        + iface_mac
        + b"\x08\x06\x00\x01\x08\x00\x06\x04\x00\x02"
        + iface_mac
        + b"\xc0\xa8\x012\x124Vx\x9a\xbc\xc0\xa8\x01d",
        b"\xff\xff\xff\xff\xff\xff"
        + iface_mac
        + b"\x08\x06\x00\x01\x08\x00\x06\x04\x00\x02"
        + iface_mac
        + b"\xc0\xa8\x012\x124Vx\x9a\xbc\xc0\xa8\x01d",
        b"\xaa\xbb\xaa\xcc\xaa\xbb"
        + iface_mac
        + b"\x08\x00E\x00\x00'\x00\x01\x00\x00@\x01\xf6\xee\xc0\xa8\x01d\xc0\xa8\x012\x08\x00o'\x00\x00\x00\x00bitahoy.com",
        b"\xaa\xbb\xaa\xcc\xaa\xbb"
        + iface_mac
        + b"\x08\x06\x00\x01\x08\x00\x06\x04\x00\x02"
        + iface_mac
        + b"\xc0\xa8\x01d\xaa\xbb\xaa\xcc\xaa\xbb\xc0\xa8\x012",
        b"\xff\xff\xff\xff\xff\xff"
        + iface_mac
        + b"\x08\x06\x00\x01\x08\x00\x06\x04\x00\x02"
        + iface_mac
        + b"\xc0\xa8\x01d\xaa\xbb\xaa\xcc\xaa\xbb\xc0\xa8\x012",
    ]
    # Check that it sent the correct packets
    await asyncio.sleep(4)
    send_packet_to_capture_last_one()
    packets_sent = [p for description, p in packet_capture()]
    print("Got ", len(packets_sent), " packets.", datetime.datetime.now())  # noqa: T001
    for packet in expected_packets:
        assert packet in packets_sent
    # Check that the spoofer sent the correct packets before terminating
    expected_shutdown_packets = [
        b"\x124Vx\x9a\xbc\xaa\xbb\xaa\xcc\xaa\xbb\x08\x00E\x00\x00'\x00\x01\x00\x00@\x01\xf6\xee\xc0\xa8\x012\xc0\xa8\x01d\x08\x00o'\x00\x00\x00\x00bitahoy.com",
        b"\x124Vx\x9a\xbc\xaa\xbb\xaa\xcc\xaa\xbb\x08\x06\x00\x01\x08\x00\x06\x04\x00\x02\xaa\xbb\xaa\xcc\xaa\xbb\xc0\xa8\x012\x124Vx\x9a\xbc\xc0\xa8\x01d",
        b"\xff\xff\xff\xff\xff\xff\xaa\xbb\xaa\xcc\xaa\xbb\x08\x06\x00\x01\x08\x00\x06\x04\x00\x02\xaa\xbb\xaa\xcc\xaa\xbb\xc0\xa8\x012\x124Vx\x9a\xbc\xc0\xa8\x01d",
        b"\xaa\xbb\xaa\xcc\xaa\xbb\x124Vx\x9a\xbc\x08\x00E\x00\x00'\x00\x01\x00\x00@\x01\xf6\xee\xc0\xa8\x01d\xc0\xa8\x012\x08\x00o'\x00\x00\x00\x00bitahoy.com",
        b"\xff\xff\xff\xff\xff\xff\xaa\xbb\xaa\xcc\xaa\xbb\x08\x06\x00\x01\x08\x00\x06\x04\x00\x02\xaa\xbb\xaa\xcc\xaa\xbb\xc0\xa8\x012\x124Vx\x9a\xbc\xc0\xa8\x01d",
        b"\xaa\xbb\xaa\xcc\xaa\xbb\x124Vx\x9a\xbc\x08\x06\x00\x01\x08\x00\x06\x04\x00\x02\x124Vx\x9a\xbc\xc0\xa8\x01d\xaa\xbb\xaa\xcc\xaa\xbb\xc0\xa8\x012",
    ]
    print("Terminating process")  # noqa: T001
    os.kill(spoofer.process.pid, signal.SIGINT)
    await asyncio.sleep(2)
    send_packet_to_capture_last_one()
    packets_sent = [p for description, p in packet_capture()]
    for packet in expected_shutdown_packets:
        assert packet in packets_sent
