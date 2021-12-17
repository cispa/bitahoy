import socket

import pytest
from bitahoy_sdk.filter import UDP, Ethernet, IPv4

from watchdog.network.bpf import (
    attach_custom_bpf,
    attach_custom_filter,
    attach_custom_tcpdump_filter,
)


@pytest.mark.asyncio
@pytest.mark.networktest
async def test_attach_custom_bpf_no_exception():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    TrafficFilter = Ethernet.assert_ipv4 & IPv4.assert_udp & ((UDP.dst_port == 53) | (UDP.src_port == 53))
    code = await TrafficFilter.ast.to_bpf_bytecode()
    attach_custom_bpf(sock, code)
    sock.close()


@pytest.mark.asyncio
@pytest.mark.networktest
async def test_attach_custom_TrafficFilter_no_exception():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    TrafficFilter = Ethernet.assert_ipv4 & IPv4.assert_udp & ((UDP.dst_port == 53) | (UDP.src_port == 53))
    await attach_custom_filter(sock, TrafficFilter)
    sock.close()


@pytest.mark.asyncio
@pytest.mark.networktest
async def test_attach_custom_tcpdump_TrafficFilter_no_exception():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    await attach_custom_tcpdump_filter(sock, "ether[0] == 24")
    sock.close()
