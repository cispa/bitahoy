import asyncio
import binascii
import multiprocessing
import struct
from socket import AF_PACKET, SOCK_RAW, htons, inet_ntoa, socket

import pytest

from watchdog.ipc.queue import ZMQueue
from watchdog.modules.master import Worker
from watchdog.network.discovery import get_netconfig
from watchdog.network.protocols import arp_packet
from watchdog.network.utils import IP, MAC


def arp_listen():
    print("Starting arp listen in subprocess")
    rawSocket = socket(AF_PACKET, SOCK_RAW, htons(0x0003))
    while True:
        packet = rawSocket.recvfrom(2048)
        ethernet_header = packet[0][0:14]
        ethernet_detailed = struct.unpack("!6s6s2s", ethernet_header)

        arp_header = packet[0][14:42]
        arp_detailed = struct.unpack("2s2s1s1s2s6s4s6s4s", arp_header)

        # skip non-ARP packets
        ethertype = ethernet_detailed[2]
        if ethertype != b"\x08\x06":
            continue

        print("****************_ETHERNET_FRAME_****************")
        print("Dest MAC:        ", binascii.hexlify(ethernet_detailed[0]))
        print("Source MAC:      ", binascii.hexlify(ethernet_detailed[1]))
        print("Type:            ", binascii.hexlify(ethertype))
        print("************************************************")
        print("******************_ARP_HEADER_******************")
        print("Hardware type:   ", binascii.hexlify(arp_detailed[0]))
        print("Protocol type:   ", binascii.hexlify(arp_detailed[1]))
        print("Hardware size:   ", binascii.hexlify(arp_detailed[2]))
        print("Protocol size:   ", binascii.hexlify(arp_detailed[3]))
        print("Opcode:          ", binascii.hexlify(arp_detailed[4]))
        print("Source MAC:      ", binascii.hexlify(arp_detailed[5]))
        print("Source IP:       ", inet_ntoa(arp_detailed[6]))
        print("Dest MAC:        ", binascii.hexlify(arp_detailed[7]))
        print("Dest IP:         ", inet_ntoa(arp_detailed[8]))
        print("*************************************************\n")


@pytest.mark.skip(reason="Problem is that packets don't arrive in listener for some reason")
@pytest.mark.networktest
@pytest.mark.asyncio
async def test_correct_event_sent_on_arp_traffic(arp_listener):
    arp_listener: Worker
    master_queue: ZMQueue
    arp_listener, master_queue, logger_queue = arp_listener
    multiprocessing.Process(target=arp_listen, args=()).start()
    assert arp_listener
    await asyncio.sleep(5)  # make sure the arp_listener started properly
    conf = get_netconfig()
    s = socket(AF_PACKET, SOCK_RAW)
    s.bind((conf.dev.name, 0))
    dst_ip = conf.box.ip
    mac = conf.box.mac
    NODES = 100
    print("Starting packet sendage")
    for i in range(20, NODES + 21):
        src_mac = MAC(f"11:11:11:11:11:{hex(i)[2:].ljust(2, '0')}")
        src_ip = IP(f"192.168.1.{i}")
        packet = arp_packet(mac, src_mac, 2, src_mac, src_ip, mac, dst_ip)
        s.send(packet)
        await asyncio.sleep(0.02)
    with master_queue.receiver().open() as get:
        await asyncio.sleep(10)
        # throw away the first events to assure we get a recent one
        event = get()
        print(event)
        import pdb

        pdb.set_trace()

    #  print(event)
    #  nodes = event.data["nodes"]
    import pdb

    pdb.set_trace()
