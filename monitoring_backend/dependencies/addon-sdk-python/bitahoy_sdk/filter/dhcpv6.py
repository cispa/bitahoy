from bitahoy_sdk.filter.ast import SymbolicPacket

__packet = SymbolicPacket()

src_port = __packet[54:56]
dst_port = __packet[56:58]