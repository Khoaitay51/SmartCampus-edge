import yaml
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"

with open(_CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

mqtt_config = config["mqtt"]

# -- MQTT topic helpers --------------------------------------------------

# Subscribe topics (used for matching incoming messages)
TOPIC_PROVISIONING_REQUEST = mqtt_config["subscribe"]["provisioning_request"]["topic"]
TOPIC_DEVICE_HEARTBEAT     = mqtt_config["subscribe"]["device_heartbeat"]["topic"]
TOPIC_ENV_TELEMETRY        = mqtt_config["subscribe"]["environment_telemetry"]["topic"]
TOPIC_OCCUPANCY_TELEMETRY  = mqtt_config["subscribe"]["occupancy_telemetry"]["topic"]
TOPIC_ROOM_RFID_EVENT      = mqtt_config["subscribe"]["room_rfid_event"]["topic"]
TOPIC_COMMAND_ACK          = mqtt_config["subscribe"]["command_ack"]["topic"]
TOPIC_SCENARIO             = mqtt_config["subscribe"]["scenario"]["topic"]

# Publish topics (templates with placeholders like {mac}, {room_id})
TOPIC_PUB_PROVISIONING_RESPONSE = mqtt_config["publish"]["provisioning_response"]["topic"]
TOPIC_PUB_ROOM_STATE            = mqtt_config["publish"]["room_state"]["topic"]
TOPIC_PUB_DEVICE_STATUS         = mqtt_config["publish"]["device_status"]["topic"]
TOPIC_PUB_ROOM_COMMAND          = mqtt_config["publish"]["room_command"]["topic"]
TOPIC_PUB_DEVICE_COMMAND        = mqtt_config["publish"]["device_command"]["topic"]
TOPIC_PUB_COMMAND_ACK           = mqtt_config["publish"]["command_ack"]["topic"]

# Global subscribe pattern (namespace + wildcard)
TOPIC_SUBSCRIBE_ALL = mqtt_config["namespace"] + "/#"

MQTT_KEEPALIVE = mqtt_config["broker"]["keepalive"]
