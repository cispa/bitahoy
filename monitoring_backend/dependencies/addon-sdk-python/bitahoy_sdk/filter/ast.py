from bitahoy_sdk.filter.bpf_building.bpf_builder import get_bpf_bytecode_from_tcpdump
from bitahoy_sdk.filter.eval import unpack


class ASTNode:

    ops = ["LD", "EQ", "LDI", "LDB", "EXISTS", "NOT", "TRUE", "AND", "OR"]

    def __init__(self, op, l=None, r=None):  # noqa: E741
        self.op = op
        self.l = l  # noqa: E741
        self.r = r  # noqa: E741

    def __str__(self):
        return "({}, {}, {})".format(self.op, self.l, self.r)

    def __repr__(self):
        return str(self)

    def to_c_bpf(self):
        if self.op == "TRUE":
            return "true"
        elif self.op == "NOT":
            return "!" + self.l.to_c_bpf()
        elif self.op == "EQ":
            return "(" + self.l.to_c_bpf() + " == " + self.r.to_c_bpf() + ")"
        elif self.op == "AND":
            return "(" + self.l.to_c_bpf() + " && " + self.r.to_c_bpf() + ")"
        elif self.op == "OR":
            return "(" + self.l.to_c_bpf() + " || " + self.r.to_c_bpf() + ")"
        elif self.op == "LD":
            return f"getnum({self.l}, {self.r})"
        elif self.op == "LDI":
            return str(self.l)
        elif self.op == "LDB":
            return str(unpack(self.l))
        return ValueError("Unknown Opperand")

    def to_tcpdump_expr(self):
        if self.op == "TRUE":
            return "(1==1)"
        elif self.op == "NOT":
            return "not" + self.l.to_tcpdump_expr()
        elif self.op == "EQ":
            return (
                "(" + self.l.to_tcpdump_expr() + " == " + self.r.to_tcpdump_expr() + ")"
            )
        elif self.op == "AND":
            return (
                "(" + self.l.to_tcpdump_expr() + " && " + self.r.to_tcpdump_expr() + ")"
            )
        elif self.op == "OR":
            return (
                "(" + self.l.to_tcpdump_expr() + " || " + self.r.to_tcpdump_expr() + ")"
            )
        elif self.op == "LD":
            return (
                f"ether[{self.l}:{self.r - self.l}]"  # tcp dump expr ether[start:len]
            )
        elif self.op == "LDI":
            return str(self.l)
        elif self.op == "LDB":
            return str(unpack(self.l))

    async def to_bpf_bytecode(self):
        return await get_bpf_bytecode_from_tcpdump(self.to_tcpdump_expr())


class SymbolicBool:
    def __init__(self, astnode: ASTNode):
        self.ast = astnode

    def negate(self):
        astnode = ASTNode("NOT", self.ast)
        return SymbolicBool(astnode)

    def __and__(self, other):
        assert isinstance(other, SymbolicBool)
        astnode = ASTNode("AND", self.ast, other.ast)
        return SymbolicBool(astnode)

    def __or__(self, other):
        assert isinstance(other, SymbolicBool)
        astnode = ASTNode("OR", self.ast, other.ast)
        return SymbolicBool(astnode)

    def __and1__(self):
        return NeedOtherOperand  # noqa: F821

    def __or1__(self):
        return NeedOtherOperand  # noqa: F821

    def __bool__(self):
        raise Exception(
            "Do not use logical operators ('or' or 'and' or 'not') for traffic filters. Use bitwise ones ('|' or '&')"
        )

    def __str__(self):
        return str(self.ast)

    def __repr__(self):
        return str(self)


class SymbolicField:
    def __init__(self, astnode):
        assert astnode.op == "LD"
        self.ast = astnode

    def __len__(self):
        assert self.ast.op == "LD"
        return self.ast.r - self.ast.l

    def __boolop(self, other, op):
        if isinstance(other, SymbolicField):
            assert len(self) == len(
                other
            ), "You can only compare fields/values of same size ({} != {})".format(
                len(self), len(other)
            )
            astnode = ASTNode(op, self.ast, other.ast)
            return SymbolicBool(astnode)
        elif isinstance(other, int):
            assert 0 < other < 2 ** 32
            astnode = ASTNode(op, self.ast, ASTNode("LDI", other))
            return SymbolicBool(astnode)
        elif isinstance(other, bytes):
            assert len(self) == len(
                other
            ), "You can only compare fields/values of same size ({} != {})".format(
                len(self), len(other)
            )
            astnode = ASTNode(op, self.ast, ASTNode("LDB", other))
            return SymbolicBool(astnode)
        else:
            raise ValueError("Unknown or incompatible operand: " + type(other))

    def __eq__(self, other) -> SymbolicBool:
        return self.__boolop(other, "EQ")

    def __ne__(self, other) -> SymbolicBool:
        return self.__boolop(other, "EQ").__not__()


class SymbolicPacket:
    def __getitem__(self, key):
        if isinstance(key, int):
            assert isinstance(key, int)
            assert key >= 0
            astnode = ASTNode("LD", key, key + 1)
            return SymbolicField(astnode)
        elif isinstance(key, slice):
            assert isinstance(key.start, int), "Only fixed-size slices allowed"
            assert isinstance(key.stop, int), "Only fixed-size slices allowed"
            assert key.step is None, "Slice steps are not supported"
            assert key.start >= 0
            assert key.stop > key.start
            astnode = ASTNode("LD", key.start, key.stop)
            return SymbolicField(astnode)
        else:
            raise ValueError("Unknown or incompatible operand: " + type(key))
