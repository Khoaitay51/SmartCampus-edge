from enum import Enum


class RoomCommandType(Enum):
    MODE = "mode"
    DOOR = "door"
    FAN = "fan"
    LIGHT = "light"
    BUZZER = "buzzer"


class CommandStatus(Enum):
    ON = "on"
    OFF = "off"
    LOCKED = "locked"
    UNLOCKED = "unlocked"


class DeviceCommandEnum(Enum):
    OTA = "ota"
    RESTART = "restart"


class DeviceStatusEnum(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
