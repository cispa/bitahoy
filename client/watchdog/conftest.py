"""
Global pytest configuration file. You can place your hooks and stuff here
Fot more features of conftest.py refer to:
https://stackoverflow.com/questions/34466027/in-pytest-what-is-the-use-of-conftest-py-files#34520971
https://docs.pytest.org/en/latest/reference/fixtures.html?highlight=conftest#conftest-py-sharing-fixtures-across-multiple-files
"""
import asyncio
import binascii
import multiprocessing as mp
import os
import re
import signal
import subprocess as sub  # nosec
import time
from socket import AF_PACKET, SOCK_RAW, socket
from typing import List, Tuple, Type

import pytest

from watchdog.core.modules import Module
from watchdog.ipc.queue import ZMQueueManager
from watchdog.modules.arp_listener import ArpListenerModule
from watchdog.modules.arp_probe import ArpProbeModule
from watchdog.modules.master import Worker
from watchdog.modules.spoofer import SpooferModule
from watchdog.network.discovery import get_netconfig
from watchdog.network.protocols import arp_packet
from watchdog.network.utils import IP, MAC

raw_data_re = rb"^\t0x[\da-f]{4}:.*"
cmd = "tcpdump -n -c 1000 -i veth-a -B 4096 --immediate-mode -l -xx"
cmd = tuple(cmd.split(" "))


def sync_read_packets(packets: list, sub_pid: mp.Value):
    """Open tcpdump in a subprocess and parse output to packets"""
    proc = sub.Popen(cmd, stdout=sub.PIPE)  # nosec
    with sub_pid.get_lock():
        sub_pid.value = proc.pid
    pkt = b""
    for row in iter(proc.stdout.readline, b""):
        if re.match(raw_data_re, row):
            pkt += row[8:]
        else:  # new packet
            if pkt:
                packet = binascii.unhexlify(pkt.replace(b" ", b"").replace(b"\n", b""))
                packets.append((header, packet))  # noqa: F821
            header = row  # noqa: F841
            pkt = b""


def get_network_packets() -> Tuple[list, mp.Process, mp.Value]:
    manager = mp.Manager()
    packets = manager.list()
    sub_pid = mp.Value("i", 0)
    proc = mp.Process(target=sync_read_packets, args=(packets, sub_pid))
    proc.start()
    return packets, proc, sub_pid


async def start_simple_module(module: Type[Module], name: str):
    run = module
    queues = {}
    master_queue_m = ZMQueueManager("master_queue")
    master_queue = master_queue_m.__enter__()
    logger_queue_m = ZMQueueManager("logger_queue")
    logger_queue = logger_queue_m.__enter__()
    worker = Worker(run, queues, name, logger_queue.sender(), master_queue)
    await worker.start()
    worker.process.start()
    return worker, master_queue, logger_queue, master_queue_m, logger_queue_m


async def kill_simple_module(worker, master_queue, master_queue_m, logger_queue, logger_queue_m):
    if worker:
        os.kill(worker.process.pid, signal.SIGKILL)
    await worker.kill()  # kill queues
    master_queue.close()
    master_queue_m.__exit__(0, 0, 0)
    logger_queue.close()
    logger_queue_m.__exit__(0, 0, 0)


@pytest.fixture
async def prober():
    run = ArpProbeModule
    name = "arp prober"
    worker, master_queue, logger_queue, master_queue_m, logger_queue_m = await start_simple_module(run, name)
    yield worker, master_queue, logger_queue
    await kill_simple_module(worker, master_queue, master_queue_m, logger_queue, logger_queue_m)


@pytest.fixture
async def spoofer() -> Tuple[Worker, ZMQueueManager, ZMQueueManager]:
    """
    This fixture allows you to create a worker running the Spoofer module along with the queues it was started with
    :return: Started worker with required queues
    """
    run = SpooferModule
    name = "spoofer"
    worker, master_queue, logger_queue, master_queue_m, logger_queue_m = await start_simple_module(run, name)
    yield worker, master_queue, logger_queue
    await kill_simple_module(worker, master_queue, master_queue_m, logger_queue, logger_queue_m)


@pytest.fixture
async def arp_listener() -> Tuple[Worker, ZMQueueManager, ZMQueueManager]:
    """
    This fixture allows you to create a worker running the arp_listener module along with the queues it was started with
    :return: Started worker with required queues
    """
    run = ArpListenerModule
    name = "arp-listener"
    worker, master_queue, logger_queue, master_queue_m, logger_queue_m = await start_simple_module(run, name)
    yield worker, master_queue, logger_queue
    await kill_simple_module(worker, master_queue, master_queue_m, logger_queue, logger_queue_m)


@pytest.fixture
async def packet_capture():
    """
    Create a subprocess running a subprocess running tcpdump and constantly update a shared list of captured packets.

    :return: A function to call returning a list of captured packets while testing
    """
    packet_list, process, tcpdump_pid = get_network_packets()
    await asyncio.sleep(2)  # wait for the new processes to start

    def get_packets() -> List[bytes]:
        packets = list(packet_list)
        return packets

    yield get_packets
    # kill the packet capturing code
    os.kill(process.pid, signal.SIGKILL)
    with tcpdump_pid.get_lock():
        os.kill(tcpdump_pid.value, signal.SIGKILL)


@pytest.fixture
def send_packet_to_capture_last_one():
    """
    Since we read packets from stdout of tcpdump, we do not know when a packet is finished
    Hence you should send an additional packet after you assume all interesting packets were sent
    """

    def send():
        conf = get_netconfig()
        sock = socket(AF_PACKET, SOCK_RAW)
        sock.bind((conf.dev.name, 0))
        dst_mac = MAC("22:22:22:22:22:22")
        src_ip = IP("192.168.69.10")
        dst_ip = IP("192.168.69.20")
        src_mac = MAC("11:11:11:11:11:11")
        packet = arp_packet(dst_mac, src_mac, 2, src_mac, src_ip, dst_mac, dst_ip)
        sock.send(packet)
        time.sleep(0.05)

    return send
