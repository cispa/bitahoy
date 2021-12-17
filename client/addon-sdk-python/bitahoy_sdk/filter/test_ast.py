from bitahoy_sdk.filter import TrafficFilter, IPv4, UDP, Ethernet

p1 = b"\x38\x10\xd5\x1d\xb8\x64\xb4\x2e\x99\xf6\xa0\x01\x08\x00\x45\x00\x00\x3f\x7c\xdb\x00\x00\x80\x11\x00\x00\xc0\xa8\xb2\x1e\xc0\xa8\xb2\x01\xe1\xb7\x00\x35\x00\x2b\xe5\xad\x71\x08\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x0d\x73\x74\x61\x63\x6b\x6f\x76\x65\x72\x66\x6c\x6f\x77\x03\x63\x6f\x6d\x00\x00\x01\x00\x01"

def test_traffic_filter_packet_match():
    f = TrafficFilter()

    # you can add an arbitrary number of conditions to the traffic filter. The filter matches a packet iff all conditions evaluate to True. An empty filter matches all packets

    # there are some protocol-specific filters predefined, which should suffice for most use-cases. For more flexible filters, have a look at the low_level_example.py which implements the same filter without using protocol helpers

    f.add(Ethernet.assert_ipv4 & IPv4.assert_udp & ((UDP.dst_port == 53) | (UDP.src_port == 53)))

    print(f.get_ast()) # prints out the AST of the filter for debugging

    assert f.evaluate(p1) # evaluates the filter on a packet