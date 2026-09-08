import logging
from enum import Enum, IntEnum
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import aiomqtt as mqtt
from feature.mqtt.publisher import publish_room_state, publish_room_command
from feature.enum import RoomCommandType, CommandStatus

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

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Priority & State enums
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_DEFAULT_STATES: dict[type[BaseState], BaseState] = {
    RoomState: RoomState.SAVING,
    DoorState: DoorState.LOCKED,
    SmokeState: SmokeState.NORMAL,
}


class StateConfig(NamedTuple):
    """Mapping from an FSM state class to its DB model and column names."""
    model: type
    state_column: str
    timestamp_column: str


_STATE_CONFIG: dict[type[BaseState], StateConfig] = {
    RoomState: StateConfig(RoomStateModel, "room_mode", "room_state_timestamp"),
    DoorState: StateConfig(RoomDoorStateModel, "door_state", "room_door_state_timestamp"),
    SmokeState: StateConfig(RoomSmokeStateModel, "smoke_state", "room_smoke_state_timestamp"),
}


# ---------------------------------------------------------------------------
# Transition table
# ---------------------------------------------------------------------------

# LOCK -> SUSPECTED/EMERGENCY blocked (FR-FSM-03: no people in locked room)
# EMERGENCY -> * blocked (must use state_recovery)
_ROOM_TRANSITIONS: dict[RoomState, frozenset[RoomState]] = {
    RoomState.SAVING: frozenset({
        RoomState.SELF_STUDY, RoomState.LECTURE, RoomState.EXAM,
        RoomState.LOCK, RoomState.SUSPECTED, RoomState.EMERGENCY,
    }),
    RoomState.SELF_STUDY: frozenset({
        RoomState.SAVING, RoomState.LECTURE, RoomState.EXAM,
        RoomState.LOCK, RoomState.SUSPECTED, RoomState.EMERGENCY,
    }),
    RoomState.LECTURE: frozenset({
        RoomState.SAVING, RoomState.SELF_STUDY, RoomState.EXAM,
        RoomState.LOCK, RoomState.SUSPECTED, RoomState.EMERGENCY,
    }),
    RoomState.EXAM: frozenset({
        RoomState.SAVING, RoomState.SELF_STUDY, RoomState.LECTURE,
        RoomState.LOCK, RoomState.SUSPECTED, RoomState.EMERGENCY,
    }),
    RoomState.LOCK: frozenset({
        RoomState.SAVING, RoomState.SELF_STUDY, RoomState.LECTURE, RoomState.EXAM,
    }),
    RoomState.SUSPECTED: frozenset({
        RoomState.SAVING, RoomState.SELF_STUDY, RoomState.LECTURE,
        RoomState.EXAM, RoomState.LOCK, RoomState.EMERGENCY,
    }),
    RoomState.EMERGENCY: frozenset(),
}


class TransitionError(Exception):
    """Raised when a state transition is not allowed."""
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_state_priority(state: BaseState) -> Priority:
    """Get the priority of a state."""
    return state.priority


def get_state_label(state: BaseState) -> str:
    """Get the label of a state."""
    return state.value


def is_emergency_state(state: BaseState) -> bool:
    """Check if a state is an emergency state."""
    return state.priority == Priority.EMERGENCY


# ---------------------------------------------------------------------------
# DB read / write
# ---------------------------------------------------------------------------


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

    cfg = _STATE_CONFIG[state_cls]
    ts_col = getattr(cfg.model, cfg.timestamp_column)

    result = await db.execute(
        select(cfg.model)
        .where(cfg.model.room_id == room_id)
        .order_by(ts_col.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()

    if record is None:
        logger.debug(
            "Room %s: no %s record, default %s",
            room_id, state_cls.__name__, _DEFAULT_STATES[state_cls].name,
        )
        return _DEFAULT_STATES[state_cls]

    db_enum_value = getattr(record, cfg.state_column)

    try:
        return state_cls[db_enum_value.name]
    except KeyError:
        logger.warning(
            "Room %s: DB value '%s' not in %s, falling back to %s",
            room_id, db_enum_value.name, state_cls.__name__,
            _DEFAULT_STATES[state_cls].name,
        )
        return _DEFAULT_STATES[state_cls]


async def set_current_state(
    room_id: UUID,
    state: BaseState,
    db: AsyncSession,
    room_status: RoomStatus = RoomStatus.online,
    emergency_source_id: int | None = None,
    mqtt_client: mqtt.Client | None = None,
) -> BaseState:
    """Persist a new state record to the database.

    Uses ``db.flush()`` so the caller controls the transaction boundary.
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
    await db.flush()

    if mqtt_client and state_cls == RoomState:
        await publish_room_state(mqtt_client, str(room_id), state.name, room_status.name)

    logger.info(
        "Room %s: persisted %s = %s",
        room_id, state_cls.__name__, state.name,
    )
    return state


# ---------------------------------------------------------------------------
# Transition logic
# ---------------------------------------------------------------------------


async def transition_to(
    room_id: UUID,
    target: RoomState,
    db: AsyncSession,
    room_status: RoomStatus = RoomStatus.online,
    emergency_source_id: int | None = None,
    mqtt_client: mqtt.Client | None = None,
) -> tuple[RoomState, RoomState]:
    """Validate and perform a room state transition.

    Returns ``(old_state, new_state)`` on success.
    Raises :class:`TransitionError` if the transition is not allowed.
    """
    current = await get_current_state(room_id, RoomState, db)

    if current == target:
        logger.debug("Room %s: already in %s, skipping", room_id, current.name)
        return current, current

    allowed = _ROOM_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        msg = (
            f"Room {room_id}: transition {current.name} ? {target.name} "
            f"is not allowed"
        )
        logger.warning(msg)
        raise TransitionError(msg)

    await set_current_state(
        room_id, target, db,
        room_status=room_status,
        emergency_source_id=emergency_source_id,
        mqtt_client=mqtt_client,
    )

    logger.info(
        "Room %s: transition %s ? %s",
        room_id, current.name, target.name,
    )

    if mqtt_client:
        if target == RoomState.EMERGENCY:
            await publish_room_command(
                mqtt_client, str(room_id),
                RoomCommandType.DOOR, CommandStatus.UNLOCKED
            )
            await publish_room_command(
                mqtt_client, str(room_id),
                RoomCommandType.BUZZER, CommandStatus.ON
            )
        elif target == RoomState.EXAM:
            await publish_room_command(
                mqtt_client, str(room_id),
                RoomCommandType.DOOR, CommandStatus.LOCKED
            )

    return current, target


# ---------------------------------------------------------------------------
# Smoke event handler
# ---------------------------------------------------------------------------


async def handle_smoke_event(
    room_id: UUID,
    smoke_state_str: str,
    db: AsyncSession,
    emergency_source_id: int | None = None,
    mqtt_client: mqtt.Client | None = None,
) -> tuple[SmokeState, RoomState | None]:
    """Process a smoke sensor event and update both SmokeState and RoomState.

    Returns ``(new_smoke_state, new_room_state)`` where ``new_room_state``
    is ``None`` when no room transition was triggered.
    """
    try:
        new_smoke = SmokeState[smoke_state_str]
    except KeyError:
        logger.warning(
            "Room %s: unknown smoke_state '%s', ignoring",
            room_id, smoke_state_str,
        )
        return SmokeState.NORMAL, None

    await set_current_state(room_id, new_smoke, db, mqtt_client=mqtt_client)

    room_target: RoomState | None = None

    if new_smoke == SmokeState.SUSPECTED:
        room_target = RoomState.SUSPECTED
    elif new_smoke == SmokeState.EMERGENCY:
        room_target = RoomState.EMERGENCY
    elif new_smoke == SmokeState.NORMAL:
        logger.info("Room %s: smoke returned to NORMAL", room_id)
        return new_smoke, None

    try:
        _, actual_room_state = await transition_to(
            room_id, room_target, db,
            emergency_source_id=emergency_source_id,
            mqtt_client=mqtt_client,
        )
        return new_smoke, actual_room_state
    except TransitionError:
        logger.info(
            "Room %s: smoke ? %s but room transition to %s blocked",
            room_id, new_smoke.name, room_target.name,
        )
        return new_smoke, None


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------


async def state_recovery(
    room_id: UUID,
    db: AsyncSession,
    mqtt_client: mqtt.Client | None = None,
) -> bool:
    """Recover from EMERGENCY by reverting to the last non-emergency room state.

    Returns True if recovery was performed, False otherwise.
    """
    current = await get_current_state(room_id, RoomState, db)
    if current != RoomState.EMERGENCY:
        logger.debug(
            "Room %s: not in EMERGENCY (%s), recovery skipped",
            room_id, current.name,
        )
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

    if recovery_record is None:
        logger.warning(
            "Room %s: no non-EMERGENCY record found, falling back to SAVING",
            room_id,
        )
        await set_current_state(room_id, RoomState.SAVING, db, mqtt_client=mqtt_client)
        return True

    fsm_state = RoomState[recovery_record.room_mode.name]
    await set_current_state(
        room_id,
        fsm_state,
        db,
        room_status=recovery_record.room_status,
        mqtt_client=mqtt_client,
    )
    await set_current_state(room_id, SmokeState.NORMAL, db, mqtt_client=mqtt_client)

    logger.info(
        "Room %s: recovered from EMERGENCY ? %s",
        room_id, fsm_state.name,
    )
    return True
