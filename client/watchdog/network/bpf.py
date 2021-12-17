from ctypes import addressof, create_string_buffer
from socket import MSG_DONTWAIT, SOL_SOCKET, socket
from struct import pack, unpack
from typing import Union

from bitahoy_sdk.filter import TrafficFilter
from bitahoy_sdk.filter.bpf_building.bpf_builder import get_bpf_bytecode_from_tcpdump

from watchdog.network.utils import IP, MAC

# As defined in asm/socket.h
SO_ATTACH_FILTER = 26

# A subset of Berkeley Packet Filter constants and macros, as defined in
# linux/filter.h.

# Instruction classes
BPF_LD = 0x00
BPF_JMP = 0x05
BPF_RET = 0x06
BPF_ALU = 0x07

# ld/ldx fields
BPF_W = 0x0
BPF_H = 0x08
BPF_B = 0x10
BPF_DW = 0x18
BPF_ABS = 0x20

BPF_MODIMM = 0x94

# alu/jmp fields
BPF_JEQ = 0x10
BPF_K = 0x00


def bpf_jump(op_code, condition, jump_target, jump_fail):
    # https://github.com/iovisor/bpf-docs/blob/master/eBPF.md
    return pack("HBBI", op_code, jump_target, jump_fail, condition)


def bpf_stmt(op_code, immediate):
    return bpf_jump(op_code, immediate, 0, 0)


def attach_arp_reply_filter(sock: socket, ownmac) -> None:

    ownmac1, ownmac2 = unpack("IH", bytes(ownmac))
    # Ordering of the filters is backwards of what would be intuitive for
    # performance reasons: the check that is most likely to fail is first.
    filters_list = [
        # eth src
        bpf_stmt(BPF_LD | BPF_W | BPF_ABS, 6),
        bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, int(ownmac1), 5, 0),
        # Must be ARP reply (check opcode field at byte offset 20)
        bpf_stmt(BPF_LD | BPF_H | BPF_ABS, 20),
        bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, 0x2, 0, 3),
        # Must be ARP (check ethertype field at byte offset 12)
        bpf_stmt(BPF_LD | BPF_H | BPF_ABS, 12),
        bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, 0x0806, 0, 1),
        bpf_stmt(BPF_RET | BPF_K, 0x0FFFFFFF),  # pass
        bpf_stmt(BPF_RET | BPF_K, 0),  # reject
    ]

    filters = b"".join(filters_list)
    attach_custom_bpf(sock, filters)


def attach_ownip_filter(sock: socket, ownip, ownmac, filter_id, modulo) -> None:

    # Ordering of the filters is backwards of what would be intuitive for
    # performance reasons: the check that is most likely to fail is first.
    ownmac1, ownmac2 = unpack("IH", bytes(ownmac))
    filters_list = [
        bpf_stmt(BPF_LD | BPF_B | BPF_ABS, 25),
        bpf_stmt(BPF_MODIMM | BPF_B, modulo),
        bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, int(filter_id), 0, 10),
        # IP dst
        bpf_stmt(BPF_LD | BPF_W | BPF_ABS, 30),
        bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, int(ownip), 8, 0),
        bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, int(IP("127.0.0.1")), 7, 0),
        bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, int(IP("255.255.255.255")), 6, 0),
        bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, int(IP("224.0.0.251")), 5, 0),
        # IP src
        bpf_stmt(BPF_LD | BPF_W | BPF_ABS, 26),
        bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, int(ownip), 3, 0),
        bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, int(IP("127.0.0.1")), 2, 0),
        bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, int(IP("0.0.0.0")), 1, 0),  # nosec
        bpf_stmt(BPF_RET | BPF_K, 0x0FFFFFFF),  # pass
        bpf_stmt(BPF_RET | BPF_K, 0),  # reject
    ]

    filters = b"".join(filters_list)
    attach_custom_bpf(sock, filters)


async def attach_ownip_filter_tcpdump(sock: socket, ownip: IP, ownmac: MAC, filter_id: int) -> None:
    tcpdump_filter = f"not (ip dst {ownip} || ip dst 255.255.255.255 || ip dst 0.0.0.0 || ip dst 127.0.0.1) and "
    await attach_custom_tcpdump_filter(sock, tcpdump_filter)


def attach_dhcp_filter(sock: socket, dst) -> None:

    # Ordering of the filters is backwards of what would be intuitive for
    # performance reasons: the check that is most likely to fail is first.
    filters_list = [
        # IP dst
        bpf_stmt(BPF_LD | BPF_W | BPF_ABS, 30),
        bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, int(dst), 0, 5),
        # is UDP
        bpf_stmt(BPF_LD | BPF_B | BPF_ABS, 23),
        bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, 17, 0, 3),
        # UDP port
        bpf_stmt(BPF_LD | BPF_H | BPF_ABS, 36),
        bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, 67, 0, 1),
        bpf_stmt(BPF_RET | BPF_K, 0x0FFFFFFF),  # pass
        bpf_stmt(BPF_RET | BPF_K, 0),  # reject
    ]
    filters = b"".join(filters_list)
    attach_custom_bpf(sock, filters)


async def attach_dhcp_filter_tcpdump(sock: socket, dst: Union[IP, str]) -> None:
    tcpdump_filter = f"not (udp dst port 23 && ip dst {dst})"
    await attach_custom_tcpdump_filter(sock, tcpdump_filter)


def attach_custom_bpf(sock: socket, code: bytes) -> None:
    assert len(code) % 8 == 0  # bpf instructions are of constant size 8
    # Create filters struct and fprog struct to be used by SO_ATTACH_FILTER, as
    # defined in linux/filter.h.
    buf = create_string_buffer(code)  # literally allocate the bytes in memory
    buf_addr = addressof(buf)
    """
    from https://www.kernel.org/doc/html/latest/networking/filter.html
    struct sock_fprog {                     /* Required for SO_ATTACH_FILTER. */
        unsigned short             len; /* Number of filter blocks */
        struct sock_filter __user *filter;
    };
    """
    bpf_prog_metadata = pack("HL", len(code) // 8, buf_addr)

    # Drain the socket after attaching a non-passable filter to ensure only packets matching the filter are received.
    filter_all = create_string_buffer(bpf_stmt(BPF_RET | BPF_K, 0))
    filter_all_addr = addressof(filter_all)
    sock.setsockopt(SOL_SOCKET, SO_ATTACH_FILTER, pack("HL", len(filter_all) // 8, filter_all_addr))
    while True:
        try:
            data = sock.recv(1, MSG_DONTWAIT)
            if not data:
                break
        except BlockingIOError:
            break
    return sock.setsockopt(SOL_SOCKET, SO_ATTACH_FILTER, bpf_prog_metadata)


async def attach_custom_filter(sock: socket, traffic_filter: TrafficFilter) -> None:
    code = await traffic_filter.ast.to_bpf_bytecode()
    return attach_custom_bpf(sock, code)


async def attach_custom_tcpdump_filter(sock: socket, traffic_filter: str) -> None:
    code = await get_bpf_bytecode_from_tcpdump(traffic_filter)
    return attach_custom_bpf(sock, code)
