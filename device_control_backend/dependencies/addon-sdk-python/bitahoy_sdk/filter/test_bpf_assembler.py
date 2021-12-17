from bitahoy_sdk.filter import UDP, Ethernet, IPv4

p1 = (
    b"\x38\x10\xd5\x1d\xb8\x64\xb4\x2e\x99\xf6\xa0\x01"
    b"\x08\x00\x45\x00\x00\x3f\x7c\xdb\x00\x00\x80\x11"
    b"\x00\x00\xc0\xa8\xb2\x1e\xc0\xa8\xb2\x01\xe1\xb7"
    b"\x00\x35\x00\x2b\xe5\xad\x71\x08\x01\x00\x00\x01"
    b"\x00\x00\x00\x00\x00\x00\x0d\x73\x74\x61\x63\x6b"
    b"\x6f\x76\x65\x72\x66\x6c\x6f\x77\x03\x63\x6f\x6d"
    b"\x00\x00\x01\x00\x01"
)


def test_asm_basic_true():
    filter = (
        Ethernet.assert_ipv4
        & IPv4.assert_udp
        & ((UDP.dst_port == 53) | (UDP.src_port == 53))
    )
    code = filter.ast.to_c_bpf()
    assert code
    assert type(code) == str


def test_asm_from_tcpdump():
    filter = (
        Ethernet.assert_ipv4
        & IPv4.assert_udp
        & ((UDP.dst_port == 53) | (UDP.src_port == 53))
    )
    code = filter.ast.to_tcpdump_expr()
    assert code
    assert type(code) == str
