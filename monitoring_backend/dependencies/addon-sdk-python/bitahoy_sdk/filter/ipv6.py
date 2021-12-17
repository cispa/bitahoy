from bitahoy_sdk.filter.ast import SymbolicPacket

__packet = SymbolicPacket()

source = __packet[22:38]
destination = __packet[38:54]
# TODO: confirm this
proto = __packet[20]

assert_udp = proto == b'\x11'
assert_tcp = proto == b'\x06'
