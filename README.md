# SmartCampus-edge

Edge backend for SmartCampus devices. It receives device events through MQTT,
persists operational data in TimescaleDB, and exposes an HTTP API.

## Run locally

If `.env` does not exist, copy the environment template. Otherwise add any
missing keys from the template. Change the local database password, then start
the stack:

```sh
cp .env.example .env
docker compose up --build
```

Compose starts PostgreSQL/TimescaleDB and Mosquitto, runs `alembic upgrade
head`, then starts the API at `http://localhost:8000`. Confirm the stack with
`GET /health`. The migration creates the TimescaleDB extension and telemetry
hypertables.

Mosquitto requires `MQTT_USERNAME` and `MQTT_PASSWORD` from `.env`. Compose
creates its local password file automatically; do not commit that generated
file or use the example password outside development.

To run the API outside Docker, keep the database running and set
`DATABASE_URL` in `.env`, then run:

```sh
uvicorn main:app --reload
```
