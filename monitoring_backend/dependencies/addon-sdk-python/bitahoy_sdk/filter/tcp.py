from bitahoy_sdk.filter.ast import SymbolicPacket

__packet = SymbolicPacket()


src_port = __packet[34:36]
dst_port = __packet[36:38]
seqence_number = __packet[38:42]
acknowledgment_number = __packet[42:46]
window_size = __packet[48:50]
checksum = __packet[50:52]
urgent_pointer = __packet[52:54]