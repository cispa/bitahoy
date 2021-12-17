from enum import Enum
class DeviceType(Enum):
    UNKNOWN = 0
    MISC = 1
    CAMERA = 2

    @classmethod
    def from_name(cls, name):
        if isinstance(name, int):
            return name
        # TODO: further sanitization, more involved check
        name = name.upper()
        for type in DeviceType:
            if type.name == name:
                return type.value
        raise ValueError('{} is not a valid DeviceType name'.format(name))

    def to_name(self):
        return DeviceType[self.value]
