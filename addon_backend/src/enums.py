from enum import Enum
class AddonType(Enum):
    UNKNOWN = 0
    ADBLOCK = 1
    ML = 2

    @classmethod
    def from_name(cls, name):
        if isinstance(name, int):
            return name
        # TODO: further sanitization, more involved check
        name = name.upper()
        for type in AddonType:
            if type.name == name:
                return type.value
        raise ValueError('{} is not a valid AddonType name'.format(name))

    def to_name(self):
        return AddonType[self.value]
