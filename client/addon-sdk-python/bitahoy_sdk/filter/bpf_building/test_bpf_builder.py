import os.path
import socket

import pytest
from bitahoy_sdk.filter.bpf_building.bpf_builder import (
    get_bpf_bytecode_from_c,
    get_bpf_bytecode_from_tcpdump,
)

SO_ATTACH_BPF = 50
SO_ATTACH_FILTER = 26


@pytest.fixture
async def bpf_object_always_pass():
    cond = "1"
    return await get_bpf_bytecode_from_c(cond)


@pytest.mark.skip("Deprecated as we use tcpdump now")
@pytest.mark.asyncio
async def test_build_succeeds():
    cond = "(((getnum(12, 14) == 2048) && (packet[24] == 17)) && ((getnum(36, 38) == 53) || (getnum(34, 36) == 53)))"
    obj_file_path = await get_bpf_bytecode_from_c(cond)
    assert os.path.exists(obj_file_path)


@pytest.mark.skip("Deprecated as we use tcpdump now")
@pytest.mark.asyncio
async def test_attach_to_socket(bpf_object_always_pass):
    file = open(bpf_object_always_pass, "rb")
    fd = file.fileno()
    print(fd)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # define SO_ATTACH_BPF  50
    sock.setsockopt(socket.SOL_SOCKET, SO_ATTACH_BPF, fd)


@pytest.mark.asyncio
async def test_attach_so_attach_filter_from_tcpdump_bpfcode():
    cond = "(((ether[12:2] == 2048) && (ether[23:1] == 17)) && ((ether[36:2] == 53) || (ether[34:2] == 53)))"
    code = await get_bpf_bytecode_from_tcpdump(cond)
    assert code
    assert type(code) == bytes
    assert len(code) % 8 == 0
