from bitahoy_sdk.filter.ast import SymbolicPacket

__packet = SymbolicPacket()

total_length = __packet[16:18]
identification = __packet[18:20]
fragment_offset = __packet[20:22]
ttl = __packet[22]
proto = __packet[23]
checksum = __packet[24:26]
destination = __packet[30:34]
source = __packet[26:30]


assert_udp = proto == b'\x11'
assert_tcp = proto == b'\x06'
assert_icmp = proto == b'\x01'
