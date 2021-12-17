def unpack(b):
    res = 0
    for i in b:
        res = 256*res+i
    return res


class Evaluator:
    def __init__(self, filter):
        self.__ast = filter.get_ast()
        self.ops = {
            "and": self.__op_and,
            "or": self.__op_or,
            "eq": self.__op_eq,
            "not": self.__op_not,
            "true": self.__op_true,
            "ld": self.__op_ld,         # has l, r as range
            "ldi": self.__op_ldi,
            "ldb": self.__op_ldb,       # unpacks from l
        }


    def evaluate(self, packet):
        self.packet = packet
        return self.__eval_op(self.__ast)

    def __eval_op(self, ast):
        return self.ops[ast.op.lower()](ast.l, ast.r)

    def __op_and(self, l, r):
        rl = self.__eval_op(l) 
        rr = self.__eval_op(r) 
        assert isinstance(rl, bool)
        assert isinstance(rr, bool)
        return rl and rr

    def __op_or(self, l, r):
        rl = self.__eval_op(l) 
        rr = self.__eval_op(r) 
        assert isinstance(rl, bool)
        assert isinstance(rr, bool)
        return rl or rr

    def __op_eq(self, l, r):
        rl = self.__eval_op(l) 
        rr = self.__eval_op(r)
        return rl == rr

    def __op_not(self, l, r):
        return not self.__eval_op(l)

    def __op_true(self, l, r):
        return True

    def __op_ld(self, l, r):
        assert isinstance(l, int)
        assert isinstance(r, int)
        assert l >= 0
        assert r > l
        return unpack(self.packet.ljust(r-l, b"\x00")[l:r])

    def __op_ldi(self, l, r):
        assert isinstance(l, int)
        return l

    def __op_ldb(self, l, r):
        assert isinstance(l, bytes)
        return unpack(l)