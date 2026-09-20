"""Thin wrappers around execute_room_command for AI agent tool calling."""
import logging
from uuid import UUID

from aiomqtt import Client
from feature.command.executor import execute_room_command

logger = logging.getLogger(__name__)


async def fan_control(
    mqtt_client: Client,
    room_id: str | UUID,
    status: str,
    source: str = "ai_agent",
) -> dict:
    return await execute_room_command(
        room_id=UUID(str(room_id)),
        command_type="fan",
        command_value=str(status).lower(),
        mqtt_client=mqtt_client,
        source=source,
    )


async def buzzer_control(
    mqtt_client: Client,
    room_id: str | UUID,
    status: str,
    source: str = "ai_agent",
) -> dict:
    return await execute_room_command(
        room_id=UUID(str(room_id)),
        command_type="buzzer",
        command_value=str(status).lower(),
        mqtt_client=mqtt_client,
        source=source,
    )


async def light_control(
    mqtt_client: Client,
    room_id: str | UUID,
    status: str,
    source: str = "ai_agent",
) -> dict:
    return await execute_room_command(
        room_id=UUID(str(room_id)),
        command_type="light",
        command_value=str(status).lower(),
        mqtt_client=mqtt_client,
        source=source,
    )


async def door_control(
    mqtt_client: Client,
    room_id: str | UUID,
    status: str,
    source: str = "ai_agent",
) -> dict:
    return await execute_room_command(
        room_id=UUID(str(room_id)),
        command_type="door",
        command_value=str(status).lower(),
        mqtt_client=mqtt_client,
        source=source,
    )
