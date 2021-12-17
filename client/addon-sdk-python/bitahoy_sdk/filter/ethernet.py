from bitahoy_sdk.filter.ast import SymbolicPacket

__packet = SymbolicPacket()


dst = __packet[0:6]
src = __packet[6:12]
proto = __packet[12:14]

assert_ipv4 = proto == b'\x08\x00'
assert_ipv6 = proto == b'\x86\xdd'
assert_arp = proto == b'\x08\x06'