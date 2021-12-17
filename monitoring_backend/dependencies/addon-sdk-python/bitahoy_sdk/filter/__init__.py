from . import ast as ast

from . import ipv4 as IPv4
from . import udp as UDP
from . import tcp as TCP
from . import ethernet as Ethernet
from . import ipv6 as IPv6
from . import arp as ARP
from . import dhcpv6 as DHCPv6

class TrafficFilter:

    def __init__(self, condition=None):
        self.__symbool = ast.SymbolicBool(ast.ASTNode("TRUE", None, None))
        if condition is not None:
            assert isinstance(condition, ast.SymbolicBool)
            if self.__symbool.ast.op == "TRUE":
                self.__symbool = condition
            else:
                self.__symbool &= condition

    def add(self, condition: ast.SymbolicBool):
        return TrafficFilter(self.__symbool & condition)

    def add_or_filter(self, filter: "TrafficFilter"):
        assert isinstance(filter, type(self))
        return TrafficFilter(self.__symbool | filter.__symbool)

    def negate(self):
        return TrafficFilter(self.__symbool.negate())

    def get_ast(self):
        return self.__symbool.ast

    def __repr__(self):
        return f"TrafficFilter({repr(self.get_ast())})"

    def __str__(self):
        return repr(self)

    def evaluate(self, packet):
        assert isinstance(packet, bytes)
        from bitahoy_sdk.filter.eval import Evaluator
        evaluator = Evaluator(self)
        return evaluator.evaluate(packet)



def dissect_packet(packet):
    assert isinstance(packet, bytes)
    return DissectedPacket(packet)


class DissectedPacket:

    def __init__(self, packet):
        self.packet = packet

    def get(self, attribute):
        l = attribute.ast.l
        r = attribute.ast.r
        # assert statement return True/False
        # assume its always a comparison between astnode and integer
        if isinstance(l, ast.ASTNode):
            return self.packet[l.l:l.r] == r.l
        return self.packet[l:r]


symbolic_packet = ast.SymbolicPacket()
