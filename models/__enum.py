from enum import Enum


class AttendanceEventType(Enum):
    CHECK_IN = "CHECK_IN"
    CHECK_OUT = "CHECK_OUT"
    REJECT = "REJECT"


class UserRole(Enum):
    ADMIN = "ADMIN"
    LECTURER = "LECTURER"
    STUDENT = "STUDENT"
    UNKNOWN = "UNKNOWN"


class RoomType(Enum):
    CLASSROOM = "CLASSROOM"
    CORRIDOR = "CORRIDOR"


class RoomStatus(Enum):
    online = "online"
    offline = "offline"


class RoomModeEnum(Enum):
    SAVING = "SAVING"
    SELF_STUDY = "SELF_STUDY"
    LECTURE = "LECTURE"
    EXAM = "EXAM"
    LOCK = "LOCK"
    SUSPECTED = "SUSPECTED"
    EMERGENCY = "EMERGENCY"


class SmokeState(Enum):
    NORMAL = "NORMAL"
    SUSPECTED = "SUSPECTED"
    EMERGENCY = "EMERGENCY"


class DeviceStatusEnum(Enum):
    online = "online"
    offline = "offline"


class IRSignalType(Enum):
    IN = "IN"
    OUT = "OUT"


class DoorStateEnum(Enum):
    LOCKED = "LOCKED"
    UNLOCKED = "UNLOCKED"
