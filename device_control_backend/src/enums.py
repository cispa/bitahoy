from enum import Enum
class Option(Enum):
    ALIAS = "alias"
    EMAIL = "mailPolicy"
    
class MailPolicy(Enum):
    NEVER = -1
    NORMAL = 0
    ALWAYS = 1
    
    
    
class Status(Enum):
    WHITELISTED = 0
    NORMAL = 1
    QUARANTINED = 2
    
class DeviceType(Enum):
    UNKNOWN = -1
    OTHER = 99
    