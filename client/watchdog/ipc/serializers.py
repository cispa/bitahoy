import json
import pickle  # nosec
import time
from binascii import hexlify, unhexlify


class Serializer:
    @staticmethod
    def serialize(data):
        out = []
        for char in data:
            if char == 0x13:
                out.append(0x13)
            out.append(char)
        out.append(0x13)
        out.append(0)
        result = bytes(out)
        return result

    @staticmethod
    def parse(data):
        escape = False
        for index, char in enumerate(data):
            if escape and char == 0:
                return data[: index + 1], data[index + 1 :]
            escape = char == 0x13 and not escape
        return None, data

    @staticmethod
    def deserialize(data):
        out = []
        escape = False
        end = False
        for char in data:
            if escape and char == 0:
                end = True
                continue
            if char == 0x13:
                if escape:
                    if char == 0x13:
                        pass
                    else:
                        raise AssertionError()
                else:
                    escape = True
                    continue
            escape = False
            assert not end
            out.append(char)
        assert end
        return bytes(out)


class PickleSerializer(Serializer):
    @staticmethod
    def serialize(obj):
        data = pickle.dumps(obj)
        return Serializer.serialize(data)

    @staticmethod
    def deserialize(data):
        data = Serializer.deserialize(data)
        return pickle.loads(data)  # nosec


class VerbosePickleSerializer(Serializer):
    @staticmethod
    def serialize(obj):
        data = pickle.dumps(obj)
        data = {
            "data": hexlify(data).decode(),
            "len": len(data),
            "time": int(time.time()),
        }
        return Serializer.serialize(json.dumps(data).encode())

    @staticmethod
    def deserialize(data):
        data = json.loads(Serializer.deserialize(data).decode())
        raw_data = unhexlify(data["data"].encode())
        assert len(raw_data) == data["len"]
        return pickle.loads(raw_data)  # nosec
