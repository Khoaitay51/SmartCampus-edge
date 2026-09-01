# SmartCampus AI Agent — Integration Guide

> **Audience**: AI agent developer working in a separate submodule.
> Backend chưa xong — doc này là **contract** giữa backend và AI agent.
> Mọi thứ dưới đây là interface cam kết. Nếu thay đổi sẽ update ở đây.

---

## Tổng quan kiến trúc

```
ESP32 sensors
     │  MQTT
     ▼
┌──────────────┐     ┌──────────────────┐
│  Mosquitto   │────▶│  FastAPI Gateway  │──── TimescaleDB
│  (broker)    │◀────│  (edge server)    │
└──────────────┘     └────────┬─────────┘
                              │ REST API + WebSocket
                              ▼
                     ┌──────────────────┐
                     │   AI Agent       │  ◀── BẠN LÀM CÁI NÀY
                     │   (submodule)    │
                     └──────────────────┘
```

**AI agent KHÔNG kết nối trực tiếp MQTT hay DB.**
Mọi tương tác đều qua **REST API** của FastAPI gateway.

---

## 1. AI Agent nhận gì?

### 1.1. Event notification (Gateway → Agent)

Gateway sẽ gọi agent khi có event cần xử lý. Agent expose 1 endpoint:

```
POST /evaluate
```

Gateway gửi:

```json
{
  "event_id": "uuid",
  "event_type": "smoke_detected | occupancy_change | temperature_anomaly | rfid_unknown | manual_trigger",
  "room_id": "uuid",
  "timestamp": "2026-09-01T20:00:00+07:00",
  "event_data": {},
  "operational_context": {}
}
```

#### Event types và event_data:

| event_type | event_data | Khi nào trigger |
|---|---|---|
| `smoke_detected` | `{"smoke_value": 520, "smoke_threshold": 400, "smoke_state": "suspected"}` | MQ2 vượt ngưỡng |
| `occupancy_change` | `{"direction": "in", "current_count": 15, "room_capacity": 40}` | IR sensor detect |
| `temperature_anomaly` | `{"temperature": 42.5, "humidity": 85.0, "avg_temp_15m": 28.0}` | Temp bất thường |
| `rfid_unknown` | `{"card_uid": "A1:B2:C3:D4", "room_id": "uuid"}` | Thẻ chưa đăng ký |
| `manual_trigger` | `{"source": "dtwin_button", "action": "evaluate_room"}` | User bấm nút trên UI |

### 1.2. Operational Context format

Mỗi event đều kèm `operational_context` — snapshot 15 phút gần nhất:

```json
{
  "room": {
    "room_id": "550e8400-e29b-41d4-a716-446655440001",
    "room_name": "Room 101",
    "room_type": "classroom",
    "current_mode": "lecture",
    "door_state": "unlocked",
    "smoke_state": "normal"
  },
  "telemetry_summary": {
    "window_start": "2026-09-01T19:45:00+07:00",
    "window_end": "2026-09-01T20:00:00+07:00",
    "temperature": {"min": 26.5, "max": 29.0, "avg": 27.8, "latest": 28.5},
    "humidity": {"min": 55.0, "max": 68.0, "avg": 62.0, "latest": 65.0},
    "co2": {"min": 400, "max": 600, "avg": 480, "latest": 520},
    "smoke_value": {"min": 80, "max": 150, "avg": 110, "latest": 120}
  },
  "occupancy": {
    "current_count": 12,
    "total_in": 15,
    "total_out": 3,
    "trend": "stable"
  },
  "active_session": {
    "session_id": "uuid",
    "lecturer_name": "Nguyen Van A",
    "class_code": "CS101",
    "started_at": "2026-09-01T19:30:00+07:00",
    "attendance_deadline": "2026-09-01T19:45:00+07:00",
    "is_exam": false,
    "checked_in_count": 10,
    "enrolled_count": 35
  },
  "recent_events": [
    {"type": "rfid_checkin", "user": "Tran Thi B", "time": "2026-09-01T19:42:00+07:00"},
    {"type": "occupancy_in", "count": 1, "time": "2026-09-01T19:43:00+07:00"}
  ]
}
```

> `active_session` = `null` nếu không có session đang chạy.

---

## 2. AI Agent trả về gì?

Agent trả về **tool recommendation**, KHÔNG tự execute:

```json
{
  "event_id": "uuid-echo-lại",
  "recommendation": {
    "tool_name": "set_fan",
    "tool_params": {"room_id": "uuid", "state": "on"},
    "reason": "CO2 đang tăng liên tục 15 phút, occupancy 12 người, bật quạt để cải thiện.",
    "confidence": 0.85,
    "urgency": "medium"
  },
  "alternatives": [
    {
      "tool_name": "send_alert",
      "tool_params": {"room_id": "uuid", "message": "CO2 cao, cân nhắc mở cửa sổ"},
      "reason": "Nếu không muốn bật quạt, có thể gửi thông báo thay thế.",
      "confidence": 0.6
    }
  ],
  "analysis": "Nhiệt độ ổn định 27.8°C avg. CO2 tăng 20 phần trăm trong 15 phút...",
  "skip": false,
  "skip_reason": null
}
```

Nếu agent đánh giá **không cần action**:

```json
{
  "event_id": "uuid",
  "recommendation": null,
  "alternatives": [],
  "analysis": "Tất cả chỉ số trong ngưỡng bình thường.",
  "skip": true,
  "skip_reason": "no_action_needed"
}
```

---

## 3. Tool List (cố định)

Agent chỉ được recommend từ danh sách tool dưới đây. Mọi tool khác sẽ bị gateway reject.

| Tool name | Params | Mô tả |
|---|---|---|
| `set_fan` | `room_id: uuid, state: "on" or "off"` | Bật/tắt quạt |
| `set_door` | `room_id: uuid, state: "locked" or "unlocked"` | Lock/unlock cửa |
| `set_mode` | `room_id: uuid, mode: string` | Chuyển room mode |
| `trigger_buzzer` | `room_id: uuid, pattern: "short" or "long" or "double" or "emergency"` | Kêu buzzer |
| `send_alert` | `room_id: uuid, message: string` | Gửi notification lên DTwin |
| `set_led` | `room_id: uuid, color: string, effect: "solid" or "blink"` | Đổi LED strip |

### 3b. RAG Query Tools (read-only, không cần approval)

Agent dùng các tool này để **tự query thông tin** trước khi đưa ra recommendation.
Đây là phần agentic RAG — agent tự quyết định cần tra cứu gì.

| Tool name | Params | Mô tả | Return |
|---|---|---|---|
| `search_history` | `query: string, room_id: uuid or null, time_range: "1h" or "6h" or "24h" or "7d"` | Semantic search qua pgvector embeddings trên telemetry summaries | `{"results": [{"text": "...", "score": 0.87, "timestamp": "..."}]}` |
| `get_telemetry` | `room_id: uuid, metric: "temperature" or "humidity" or "co2" or "smoke" or "occupancy", window: "15m" or "1h" or "6h"` | Query raw time-series data cho 1 metric cụ thể | `{"data": [{"value": 28.5, "timestamp": "..."}], "stats": {"min": ..., "max": ..., "avg": ...}}` |
| `get_attendance` | `room_id: uuid or null, session_id: uuid or null, class_code: string or null` | Query attendance records | `{"records": [{"student": "...", "time": "...", "late": false}], "summary": {"total": 30, "present": 25, "late": 3, "absent": 5}}` |
| `compare_rooms` | `room_ids: list of uuid, metric: string, window: "1h" or "6h" or "24h"` | So sánh metrics giữa các phòng | `{"comparison": [{"room_id": "...", "room_name": "...", "avg": ..., "max": ...}]}` |
| `get_room_history` | `room_id: uuid, hours: int` | Lịch sử state transitions | `{"transitions": [{"from": "SAVING", "to": "LECTURE", "at": "...", "trigger": "rfid_checkin"}]}` |
| `get_schedule` | `room_id: uuid or null, date: "YYYY-MM-DD" or null` | Query lịch học theo phòng hoặc ngày | `{"classes": [{"class_code": "CS101", "lecturer": "...", "start": "...", "end": "..."}]}` |
| `get_predictions` | `room_id: uuid, metric: "temperature" or "co2", horizon: "15m" or "30m"` | EWMA prediction cho metric | `{"current": 28.5, "predicted": 30.2, "trend": "rising", "confidence": 0.75}` |

> RAG tools **không cần human approval** — chúng chỉ đọc data, không thay đổi state.
> Agent có thể gọi nhiều RAG tools trước khi đưa ra 1 recommendation.

### Tool Permission Matrix

Không phải tool nào cũng được phép ở mọi state:

| Tool | SAVING | SELF_STUDY | LECTURE | EXAM | LOCK | SUSPECTED | EMERGENCY |
|---|---|---|---|---|---|---|---|
| `set_fan` | Yes | Yes | Yes | Yes | No | Yes | No |
| `set_door` | Yes | Yes | Yes | No* | No | Yes | Yes |
| `set_mode` | Yes | Yes | Yes | Yes | No | No | No |
| `trigger_buzzer` | Yes | Yes | Yes | Yes | No | Yes | Yes |
| `send_alert` | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| `set_led` | Yes | Yes | Yes | Yes | No | No | No |
| **RAG tools** | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| **Getting Metadata** | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| 


> *EXAM: `set_door unlocked` chỉ allowed khi EMERGENCY override.

---

## 3c. Agent Operating States

AI agent có **2 state**, chuyển đổi qua API hoặc DTwin toggle:

```
┌─────────────────────┐          ┌─────────────────────┐
│   SELF_EXECUTE      │  ◄────►  │  HUMAN_INTERVENTION │
│                     │  toggle  │                     │
│  Agent nhận event   │          │  Agent nhận event   │
│  → evaluate         │          │  → evaluate         │
│  → chọn tool        │          │  → chọn tool        │
│  → EXECUTE LUÔN     │          │  → GỬI RECOMMENDATION│
│  → log + notify     │          │  → CHỜ USER APPROVE │
└─────────────────────┘          └─────────────────────┘
```

### State 1: SELF_EXECUTE

- Agent nhận event → tự quyết định → **tự gọi tool execute** → log kết quả
- DTwin nhận notification post-hoc (đã thực hiện rồi)
- Phù hợp khi: hệ thống đã stable, agent đã được validate, cần phản hồi nhanh

```
Event → Agent evaluate → Tool execute → Log + Notify DTwin
```

### State 2: HUMAN_INTERVENTION

- Agent nhận event → tự quyết định → **gửi recommendation lên DTwin** → chờ user approve/reject
- User bấm [Execute] hoặc [Ignore] trên DTwin popup
- Recommendation expire sau 5 phút nếu không có response
- Phù hợp khi: đang development, cần audit, môi trường nhạy cảm

```
Event → Agent evaluate → Recommendation → DTwin popup → User decide → Execute or Discard
```

### Chuyển state

```
POST /api/ai/mode
  Body: {"mode": "self_execute"}   // hoặc "human_intervention"
  → switch agent state

GET /api/ai/mode
  → {"mode": "self_execute", "switched_at": "...", "switched_by": "admin"}
```

> Admin có thể toggle trên DTwin UI hoặc qua API.
> Default khi khởi động: **HUMAN_INTERVENTION** (an toàn).

### Safety rails cho SELF_EXECUTE

| Rule | Giá trị | Mục đích |
|---|---|---|
| Confidence gate | >= 0.8 mới execute, dưới thì fallback sang human | Tránh execute khi không chắc |
| Cooldown | 60s giữa 2 lần execute cùng tool + cùng room | Tránh lặp |
| Daily cap | Max 50 executions per room per day | Giới hạn tác động |
| Kill switch | `POST /api/ai/kill-switch` force về HUMAN_INTERVENTION | Emergency brake |
| Blocked tools | `set_door`, `set_mode` LUÔN cần human dù ở SELF_EXECUTE | Bảo vệ critical actions |
| Audit log | Mọi execution đều log đầy đủ | Traceability |

> **Blocked tools**: một số tool quá nguy hiểm để auto-execute.
> Khi agent ở SELF_EXECUTE mà recommend blocked tool → tự động fallback sang HUMAN_INTERVENTION cho tool đó.

### Agent response format

```json
{
  "event_id": "uuid",
  "recommendation": {
    "tool_name": "set_fan",
    "tool_params": {"room_id": "uuid", "state": "on"},
    "reason": "CO2 tăng liên tục...",
    "confidence": 0.9,
    "urgency": "medium"
  },
  "executed": true,
  "execution_result": {
    "success": true,
    "executed_at": "2026-09-01T20:00:05+07:00",
    "mode": "self_execute"
  }
}
```

Khi ở HUMAN_INTERVENTION, `executed` = `false` và `execution_result` = `null`:

```json
{
  "event_id": "uuid",
  "recommendation": { "..." : "..." },
  "executed": false,
  "execution_result": null,
  "pending_approval_id": "uuid"
}
```

### Audit log

```
GET /api/ai/audit-log?mode=self_execute&limit=50
GET /api/ai/audit-log?mode=human_intervention&status=approved&limit=50
```

Mỗi entry chứa: event, context snapshot, recommendation, mode, executed, result, timestamp

---

## 3d. Agentic RAG Flow

Agent hoạt động theo **ReAct pattern**: Observe → Think → Act

```
Gateway gọi POST /evaluate với event + context
  │
  ▼
Agent nhận event → phân tích operational_context
  │
  ▼
Agent TỰ QUYẾT ĐỊNH cần thêm thông tin không?
  │
  ├── Cần → gọi RAG tools (search_history, get_telemetry, ...)
  │         có thể gọi NHIỀU tools, mỗi tool 1 query
  │         │
  │         ▼
  │         Tổng hợp kết quả RAG + context gốc
  │
  ▼
Agent đưa ra recommendation (hoặc skip)
  │
  ▼
Gateway check execution mode config
  │
  ├── auto → execute ngay + log + notify DTwin
  └── human → hiện popup DTwin → chờ approve
```

### Ví dụ: Agent xử lý temperature_anomaly

1. Nhận event: temp = 42.5 tại Room 101
2. Agent gọi `get_telemetry(room_id, "temperature", "1h")` → thấy trend tăng dần
3. Agent gọi `compare_rooms([room_101, room_102], "temperature", "1h")` → Room 102 bình thường
4. Agent gọi `search_history("nhiệt độ cao bất thường", room_id, "7d")` → tuần trước cũng xảy ra, do quên tắt máy chiếu
5. Agent kết luận: anomaly cục bộ → recommend `set_fan(on)` + `send_alert("Kiểm tra thiết bị phát nhiệt")`
6. Gateway check config: `set_fan` = human mode, `send_alert` = auto mode
7. → `send_alert` execute ngay, `set_fan` hiện popup chờ approve

### Tool call log trong agent response

Khi agent dùng RAG tools, log lại trong response để audit:

```json
{
  "event_id": "uuid",
  "tool_calls_log": [
    {"tool": "get_telemetry", "params": {"room_id": "...", "metric": "temperature", "window": "1h"}, "result_summary": "Trend tăng từ 28 lên 42.5 trong 1h"},
    {"tool": "compare_rooms", "params": {"room_ids": ["...", "..."], "metric": "temperature", "window": "1h"}, "result_summary": "Room 102 ổn định 27-28"},
    {"tool": "search_history", "params": {"query": "nhiệt độ cao", "room_id": "...", "time_range": "7d"}, "result_summary": "1 incident tương tự 5 ngày trước"}
  ],
  "recommendation": { "..": ".." },
  "analysis": "..."
}
```

---

## 4. Room FSM States

```
SAVING ←──── occupancy = 0
  │
  ▼
SELF_STUDY ← occupancy > 0, no lecturer
  │
  ▼
LECTURE ←─── lecturer RFID check-in
  │
  ▼
EXAM ←────── web/admin trigger

SUSPECTED ← smoke lần 1
  │
  ▼
EMERGENCY ← smoke lần 2 trong 5s — override tất cả trừ LOCK

LOCK ←────── admin trigger — không bị override
```

### Mode to LED mapping

| Mode | LED Color |
|---|---|
| SAVING | Tắt |
| SELF_STUDY | Xanh nhạt |
| LECTURE | Trắng |
| EXAM | Vàng amber |
| SUSPECTED | Cam |
| EMERGENCY | Đỏ nhấp nháy |
| LOCK | Xám |

---

## 5. Gateway REST API (Agent có thể gọi)

Base URL: `http://gateway:8000/api`

### Query endpoints (đọc data)

```
GET /api/rooms
  → danh sách rooms kèm current state

GET /api/rooms/{room_id}
  → room detail + latest telemetry + active session

GET /api/rooms/{room_id}/telemetry?window=15m
  → telemetry array trong 15 phút gần nhất

GET /api/rooms/{room_id}/sessions?active=true
  → active session detail + attendance list

GET /api/rooms/{room_id}/history?hours=24
  → state change history 24h
```

### RAG endpoints (agent gọi trực tiếp, không cần approval)

```
POST /api/rag/search
  Body: {"query": "string", "room_id": "uuid or null", "time_range": "24h"}
  → semantic search results from pgvector

GET /api/rag/telemetry/{room_id}?metric=temperature&window=1h
  → raw time-series data

GET /api/rag/attendance?room_id=uuid&session_id=uuid
  → attendance records

POST /api/rag/compare
  Body: {"room_ids": ["uuid", "uuid"], "metric": "co2", "window": "6h"}
  → cross-room comparison

GET /api/rag/schedule?room_id=uuid&date=2026-09-01
  → class schedule

GET /api/rag/predict/{room_id}?metric=co2&horizon=15m
  → EWMA prediction
```

### Action endpoints (cần human approval trước)

```
POST /api/ai/recommend
  Body: recommendation JSON (section 2)
  Response: {"recommendation_id": "uuid", "status": "pending_approval"}

GET /api/ai/recommendations?status=pending
  → list pending recommendations

GET /api/ai/recommendations/{id}/status
  → {"status": "approved or rejected or expired", "executed_at": "..."}
```

---

## 6. Cách dev agent mà không cần backend chạy

### Option A: Mock server (khuyên dùng)

Tạo 1 FastAPI app nhỏ trả fake data:

```python
# mock_gateway.py
from fastapi import FastAPI
import json

app = FastAPI()

MOCK_CONTEXT = json.load(open("mock_data/operational_context.json"))

@app.post("/evaluate")
async def evaluate(event: dict):
    return {"status": "received"}

@app.get("/api/rooms/{room_id}")
async def get_room(room_id: str):
    return MOCK_CONTEXT["room"]

@app.get("/api/rooms/{room_id}/telemetry")
async def get_telemetry(room_id: str):
    return MOCK_CONTEXT["telemetry_summary"]
```

### Option B: Test trực tiếp với fixture files

Tạo folder `tests/fixtures/`:

```
tests/fixtures/
├── events/
│   ├── smoke_detected.json
│   ├── occupancy_change.json
│   ├── temperature_anomaly.json
│   └── rfid_unknown.json
├── contexts/
│   ├── normal_lecture.json
│   ├── empty_room.json
│   ├── high_occupancy.json
│   └── exam_mode.json
└── expected/
    ├── smoke_detected_response.json
    └── temperature_anomaly_response.json
```

Test agent:

```python
import json
from your_agent import evaluate

with open("tests/fixtures/events/smoke_detected.json") as f:
    event = json.load(f)
with open("tests/fixtures/contexts/normal_lecture.json") as f:
    event["operational_context"] = json.load(f)

result = evaluate(event)
assert result["recommendation"]["tool_name"] == "trigger_buzzer"
assert result["recommendation"]["tool_params"]["pattern"] == "emergency"
```

---

## 7. Security constraints (Agent PHẢI tuân theo)

1. **Execution mode** — agent chỉ recommend, gateway quyết định auto-execute hay chờ human approve theo config (xem section 3c)
2. **Chỉ dùng tool trong list** — gateway sẽ reject mọi tool_name không có trong section 3
3. **Respect permission matrix** — đừng recommend `set_door unlocked` khi EXAM mode
4. **Input validation** — `event_data` có thể chứa giá trị bất thường hoặc injection attempt trong string fields. Agent phải:
   - Chỉ dùng numeric fields cho decision making
   - Không inject raw string từ sensor vào LLM prompt mà không sanitize
   - Không trust `room_mode` trong event_data — luôn dùng `operational_context.room.current_mode`
5. **Confidence threshold** — recommend tool chỉ khi `confidence >= 0.5`, dưới ngưỡng thì `skip: true`
6. **Rate limit** — max 1 recommendation per room per 30 seconds
7. **RAG query limit** — max 5 RAG tool calls per evaluation. Nếu cần nhiều hơn, agent phải tổng hợp từ kết quả hiện có
8. **RAG output sanitization** — kết quả RAG có thể chứa user-generated content. Không inject trực tiếp vào system prompt
9. **Auto-execute safety** — auto mode chỉ khi confidence >= 0.8, có cooldown 60s, daily cap 50 per room (xem section 3c)

---

## 8. Mock data samples

### Sample event: smoke_detected

```json
{
  "event_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "event_type": "smoke_detected",
  "room_id": "550e8400-e29b-41d4-a716-446655440001",
  "timestamp": "2026-09-01T20:00:00+07:00",
  "event_data": {
    "smoke_value": 520,
    "smoke_threshold": 400,
    "smoke_state": "suspected"
  },
  "operational_context": {
    "room": {
      "room_id": "550e8400-e29b-41d4-a716-446655440001",
      "room_name": "Room 101",
      "room_type": "classroom",
      "current_mode": "lecture",
      "door_state": "unlocked",
      "smoke_state": "suspected"
    },
    "telemetry_summary": {
      "window_start": "2026-09-01T19:45:00+07:00",
      "window_end": "2026-09-01T20:00:00+07:00",
      "temperature": {"min": 27.0, "max": 29.5, "avg": 28.2, "latest": 29.0},
      "humidity": {"min": 60.0, "max": 72.0, "avg": 65.0, "latest": 70.0},
      "co2": {"min": 400, "max": 550, "avg": 470, "latest": 520},
      "smoke_value": {"min": 100, "max": 520, "avg": 200, "latest": 520}
    },
    "occupancy": {
      "current_count": 25,
      "total_in": 28,
      "total_out": 3,
      "trend": "stable"
    },
    "active_session": {
      "session_id": "660e8400-e29b-41d4-a716-446655440099",
      "lecturer_name": "Nguyen Van A",
      "class_code": "CS101",
      "started_at": "2026-09-01T19:30:00+07:00",
      "attendance_deadline": "2026-09-01T19:45:00+07:00",
      "is_exam": false,
      "checked_in_count": 22,
      "enrolled_count": 35
    },
    "recent_events": [
      {"type": "smoke_spike", "value": 520, "time": "2026-09-01T20:00:00+07:00"},
      {"type": "rfid_checkin", "user": "Le Van C", "time": "2026-09-01T19:44:00+07:00"}
    ]
  }
}
```

### Expected agent response:

```json
{
  "event_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "recommendation": {
    "tool_name": "send_alert",
    "tool_params": {
      "room_id": "550e8400-e29b-41d4-a716-446655440001",
      "message": "Phát hiện khói bất thường tại Room 101. Smoke value 520 vượt threshold 400. 25 người đang trong phòng. Đề xuất kiểm tra ngay."
    },
    "reason": "Smoke vượt ngưỡng lần 1 suspected. Phòng đang có 25 người trong giờ lecture. Chưa đủ điều kiện EMERGENCY cần lần 2 trong 5s. Gửi cảnh báo để giám sát viên kiểm tra.",
    "confidence": 0.9,
    "urgency": "high"
  },
  "alternatives": [
    {
      "tool_name": "trigger_buzzer",
      "tool_params": {"room_id": "550e8400-e29b-41d4-a716-446655440001", "pattern": "short"},
      "reason": "Cảnh báo âm thanh nhẹ nếu cần chú ý ngay lập tức.",
      "confidence": 0.5
    }
  ],
  "analysis": "Smoke value tăng đột biến từ avg 200 lên 520 vượt threshold 400. Đây là lần detect đầu tiên suspected. Nếu xảy ra lần 2 trong 5s FSM sẽ tự chuyển EMERGENCY và buzzer sẽ kêu tự động ở local không qua agent. Hiện tại chỉ cần alert.",
  "skip": false,
  "skip_reason": null
}
```

---

## Liên hệ

- Backend dev: tên bạn
- MQTT contract: xem `JSON_contract_example.txt` trong repo
- Config topics: xem `config.yaml` trong repo
- Có thắc mắc về interface: tạo issue hoặc hỏi trực tiếp
