from enum import Enum


class AttendanceEventType(Enum):
    CHECK_IN = "check_in"
    CHECK_OUT = "check_out"
    REJECT = "reject"


class UserRole(Enum):
    ADMIN = "admin"
    LECTURER = "lecturer"
    STUDENT = "student"
    UNKNOWN = "unknown"


class RoomType(Enum):
    CLASSROOM = "classroom"
    CORRIDOR = "corridor"


class RoomStatus(Enum):
    online = "online"
    offline = "offline"


class RoomModeEnum(Enum):
    SAVING = "saving"
    SELF_STUDY = "self_study"
    LECTURE = "lecture"
    EXAM = "exam"
    LOCK = "lock"
    SUSPECTED = "suspected"
    EMERGENCY = "emergency"


class SmokeState(Enum):
    NORMAL = "normal"
    SUSPECTED = "suspected"
    EMERGENCY = "emergency"


class DeviceStatusEnum(Enum):
    online = "online"
    offline = "offline"


class IRSignalType(Enum):
    IN = "in"
    OUT = "out"


class DoorStateEnum(Enum):
    LOCKED = "locked"
    UNLOCKED = "unlocked"
