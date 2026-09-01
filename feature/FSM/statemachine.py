from enum import Enum, IntEnum
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.room import (
    RoomState as RoomStateModel,
    RoomDoorState as RoomDoorStateModel,
    RoomSmokeState as RoomSmokeStateModel,
)
from models.__enum import (
    RoomModeEnum,
    RoomStatus,
    DoorStateEnum,
    SmokeState as SmokeStateEnum,
)


class Priority(IntEnum):
    NORMAL = 0
    WARNING = 50
    EMERGENCY = 100


class BaseState(Enum):
    def __new__(cls, label: str, priority: Priority):
        obj = object.__new__(cls)
        obj._value_ = label
        obj.priority = priority
        return obj


class RoomState(BaseState):
    SAVING = ("Saving", Priority.NORMAL)
    SELF_STUDY = ("Self-Study", Priority.NORMAL)
    LECTURE = ("Lecture", Priority.NORMAL)
    EXAM = ("Exam", Priority.NORMAL)
    LOCK = ("Lock", Priority.NORMAL)
    SUSPECTED = ("Suspected", Priority.WARNING)
    EMERGENCY = ("Emergency", Priority.EMERGENCY)


class DoorState(BaseState):
    LOCKED = ("Locked", Priority.NORMAL)
    UNLOCKED = ("Unlocked", Priority.NORMAL)


class SmokeState(BaseState):
    NORMAL = ("Normal", Priority.NORMAL)
    SUSPECTED = ("Suspected", Priority.WARNING)
    EMERGENCY = ("Emergency", Priority.EMERGENCY)


# Default states when no record exists in the database
_DEFAULT_STATES: dict[type[BaseState], BaseState] = {
    RoomState: RoomState.SAVING,
    DoorState: DoorState.LOCKED,
    SmokeState: SmokeState.NORMAL,
}

# Mapping: FSM state class -> (DB model, state column name, timestamp column name)
_STATE_CONFIG: dict[type[BaseState], tuple] = {
    RoomState: (RoomStateModel, "room_mode", "room_state_timestamp"),
    DoorState: (RoomDoorStateModel, "door_state", "room_door_state_timestamp"),
    SmokeState: (RoomSmokeStateModel, "smoke_state", "room_smoke_state_timestamp"),
}


def get_state_priority(state: BaseState) -> Priority:
    """Get the priority of a state."""
    return state.priority


def get_state_label(state: BaseState) -> str:
    """Get the label of a state."""
    return state.value


def is_emergency_state(state: BaseState) -> bool:
    """Check if a state is an emergency state."""
    return state.priority == Priority.EMERGENCY


async def get_current_state(
    room_id: UUID,
    state_cls: type[BaseState],
    db: AsyncSession,
) -> BaseState:
    """Query the latest state of a room from the database.

    Returns the default state if no record exists for this room.
    """
    if state_cls not in _STATE_CONFIG:
        raise ValueError(f"Unknown state class: {state_cls}")

    model, col_name, ts_col_name = _STATE_CONFIG[state_cls]
    ts_col = getattr(model, ts_col_name)

    result = await db.execute(
        select(model)
        .where(model.room_id == room_id)
        .order_by(ts_col.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()

    if record is None:
        return _DEFAULT_STATES[state_cls]

    db_enum_value = getattr(record, col_name)
    return state_cls[db_enum_value.name]


async def set_current_state(
    room_id: UUID,
    state: BaseState,
    db: AsyncSession,
    room_status: RoomStatus = RoomStatus.online,
    emergency_source_id: int | None = None,
) -> BaseState:
    """Persist a new state record to the database.

    For RoomState, ``room_status`` and ``emergency_source_id`` are passed
    through to the ``room_state`` table.  They are ignored for other
    state types.
    """
    state_cls = type(state)

    if state_cls == RoomState:
        record = RoomStateModel(
            room_id=room_id,
            room_mode=RoomModeEnum[state.name],
            room_status=room_status,
            room_emergency_state_source_id=emergency_source_id,
        )
    elif state_cls == DoorState:
        record = RoomDoorStateModel(
            room_id=room_id,
            door_state=DoorStateEnum[state.name],
        )
    elif state_cls == SmokeState:
        record = RoomSmokeStateModel(
            room_id=room_id,
            smoke_state=SmokeStateEnum[state.name],
        )
    else:
        raise ValueError(f"Unknown state type: {state_cls}")

    db.add(record)
    await db.commit()
    return state


async def state_recovery(room_id: UUID, db: AsyncSession) -> bool:
    """Recover from EMERGENCY by reverting to the last non-emergency room state.

    Returns True if recovery was performed, False otherwise.
    """
    current = await get_current_state(room_id, RoomState, db)
    if current != RoomState.EMERGENCY:
        return False

    result = await db.execute(
        select(RoomStateModel)
        .where(
            RoomStateModel.room_id == room_id,
            RoomStateModel.room_mode != RoomModeEnum.EMERGENCY,
        )
        .order_by(RoomStateModel.room_state_timestamp.desc())
        .limit(1)
    )
    recovery_record = result.scalar_one_or_none()
    if recovery_record:
        fsm_state = RoomState[recovery_record.room_mode.name]
        await set_current_state(
            room_id,
            fsm_state,
            db,
            room_status=recovery_record.room_status,
        )
        return True
    return False
