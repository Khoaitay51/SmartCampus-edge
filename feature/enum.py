from enum import Enum


class RoomCommandType(Enum):
    MODE = "mode"
    DOOR = "door"
    FAN = "fan"
    LIGHT = "light"
    BUZZER = "buzzer"
    LED_STRIP = "led_strip"


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

class SessionStatusEnum(Enum):
    ACTIVE = "active"
    ENDED = "ended"
    CANCELED = "canceled"


class LedStripStatus(Enum):
    STATIC = "static"
    BREATHE = "breathe"
    STROBE = "strobe"
