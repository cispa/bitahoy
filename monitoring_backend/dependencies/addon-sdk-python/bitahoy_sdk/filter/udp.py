from bitahoy_sdk.filter.ast import SymbolicPacket

__packet = SymbolicPacket()


src_port = __packet[34:36]
dst_port = __packet[36:38]
length = __packet[38:40]
checksum = __packet[40:42]