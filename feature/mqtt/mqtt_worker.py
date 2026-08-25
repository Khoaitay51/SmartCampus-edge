import aiomqtt as mqtt
import logging
import os
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

def get_mqtt_config():
    """Read the MQTT connection settings used by the worker."""
    username = os.getenv("MQTT_USERNAME")
    password = os.getenv("MQTT_PASSWORD")

    if not username or not password:
        raise RuntimeError("MQTT_USERNAME and MQTT_PASSWORD must be set.")

    return {
        "hostname": os.getenv("MQTT_HOST", os.getenv("MQTT_BROKER", "localhost")),
        "port": int(os.getenv("MQTT_PORT", "1883")),
        "username": username,
        "password": password,
    }


def create_mqtt_client() -> mqtt.Client:
    """Create an authenticated MQTT client for use with ``async with``."""
    return mqtt.Client(**get_mqtt_config())

async def mqtt_listener() -> None:
    """Connect to the broker and process SmartCampus messages until cancelled."""
    async with create_mqtt_client() as client:
        await client.subscribe("smartcampus/v1/#")
        logger.info("MQTT listener subscribed to smartcampus/v1/#")

        async for message in client.messages:
            logger.info(
                "Received MQTT message on %s: %s",
                message.topic,
                message.payload.decode(errors="replace"),
            )
