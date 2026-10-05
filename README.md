# 🌐 Smart Campus BMS — Edge Computing Gateway

> **Phân hệ Gateway Tính toán Biên & Xử lý Nghiệp vụ Thời gian thực (Edge Computing Gateway)**  
> Xây dựng trên nền tảng **FastAPI (Python 3.11+)**, **AsyncIO**, **aiomqtt**, **TimescaleDB (PostgreSQL 17)**, và **Eclipse Mosquitto Broker**.

---

## 📌 Tổng quan Phân hệ

Phân hệ **Edge Gateway** đóng vai trò là "bộ não điều hành cục bộ" đặt tại khuôn viên trường đại học, chịu trách nhiệm kết nối trực tiếp với các node IoT phần cứng ESP32 qua mạng nội bộ. Gateway đảm bảo:
* **Xử lý thời gian thực độ trễ thấp (< 50ms):** Thu thập telemetry cảm biến, điểm danh quẹt thẻ, nhận diện người ra vào.
* **Độc lập vận hành (Edge Autonomy):** Ngay cả khi mất kết nối Internet, máy trạng thái phòng (FSM) và kiểm soát mở cửa, còi báo khẩn cấp vẫn hoạt động ổn định 100%.
* **Lưu trữ chuỗi thời gian tối ưu (TimescaleDB Hypertables):** Tự động phân vùng thời gian cho hàng triệu bản ghi telemetry môi trường, người ra/vào và nhịp tim thiết bị.

---

## 🏛️ Kiến trúc Thành phần (Internal Architecture)

```
┌────────────────────────────────────────────────────────────────────────┐
│                   ESP32 Nodes (Room Nodes & Corridor Node)             │
│   DHT22 │ Dual IR │ MQ-2 │ MQ-135 │ RC522 RFID │ Servo │ Fan │ Buzzer │ OLED│
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ MQTT (TCP 1883) - QoS 1
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   Eclipse Mosquitto MQTT Broker (Cổng 1883)            │
│   - Namespace: smartcampus/v1/...                                      │
│   - Retained Topics: room state, device status, provisioning           │
│   - LWT (Last Will & Testament): Phát hiện ngắt kết nối vật lý        │
└───────────────────┬─────────────────────────────────┬──────────────────┘
                    │ Subscriptions                   │ Publish Commands
                    ▼                                 ▲
┌────────────────────────────────────────────────────────────────────────┐
│                     FastAPI Edge Service (main.py)                     │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │             Async MQTT Worker Daemon (aiomqtt)                   │  │
│  │  - _handle_provision_request()   - _handle_heartbeat()           │  │
│  │  - _handle_environment_telemetry() - _handle_occupancy_telemetry()│  │
│  │  - _handle_rfid_event()          - _handle_card_reg_request()    │  │
│  │  - _handle_card_registration_response()                          │  │
│  └──────────────────┬───────────────────────────────┬───────────────┘  │
│                     ▼                               ▼                  │
│  ┌────────────────────────────────┐  ┌──────────────────────────────┐  │
│  │  Room FSM Engine (statemachine)│  │  RFID & Attendance Service   │  │
│  │  - 7 Discrete Operating States │  │  - Giảng viên check-in/out   │  │
│  │  - Emergency Override & Recovery│  │  - Sinh viên điểm danh      │  │
│  │  - Command Execution Pipeline  │  │  - Discrepancy Engine (IR vs)│  │
│  └──────────────────┬─────────────┘  └──────────────┬───────────────┘  │
│                     │                               │                  │
│  ┌──────────────────┴───────────────────────────────┴───────────────┐  │
│  │  REST API Layer: Health, Rooms, Devices, Cards Sync, Scenarios   │  │
│  └──────────────────────────────────┬───────────────────────────────┘  │
└─────────────────────────────────────┼──────────────────────────────────┘
                                      │ SQLAlchemy 2.0 (asyncpg)
                                      ▼
┌────────────────────────────────────────────────────────────────────────┐
│               TimescaleDB on PostgreSQL 17 (Cổng 5434)                 │
│  - Relational Core: users, room, device, classes, room_sessions,       │
│    attendance_records, card_registration_requests, command             │
│  - TimescaleDB Hypertables: environment, occupancy, attendance_events, │
│    device_heartbeat, room_state, room_door_state, room_smoke_state     │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Đặc tả Yêu cầu Chức năng Hoàn thiện tại Edge

### 1. Quản lý Thiết bị & Kết nối (Device Management)
* **FR-DM-01 — Auto Provisioning:** Nhận gói tin từ node mới khởi động trên topic `smartcampus/v1/device/provision/request`. Lưu vào bảng `device` với trạng thái `PENDING`.
* **FR-DM-02 — Room Assignment:** Khi Admin gán phòng cho thiết bị qua API `POST /api/devices/{device_id}/assign-room`, Edge cập nhật DB và xuất bản `smartcampus/v1/device/provision/response/{mac_address}` (`retain=True`) gửi cấu hình gồm `room_id`, `heartbeat_interval` về lưu vào bộ nhớ flash NVS của ESP32.
* **FR-DM-03 — Heartbeat Tracking:** Định kỳ 30s ghi nhận nhịp tim vào hypertable `device_heartbeat`. Đồng thời cập nhật `last_heartbeat` trong bảng `device`.
* **FR-DM-04 — Last Will and Testament:** Mosquitto tự động phát bản tin lên `smartcampus/v1/device/{mac}/status` báo trạng thái `offline` khi đứt kết nối mạng đột ngột.

### 2. Thu thập & Xử lý Telemetry Cảm biến (Sensor Telemetry)
* **FR-SD-01 — Môi trường (DHT22 & MQ-135):** Nhận gói tin định kỳ từ `smartcampus/v1/telemetry/room/{room_id}/environment`, ghi nhận vào hypertable `environment` (`temperature`, `humidity`, `co2`, `air_quality`).
* **FR-SD-02 — Đếm người hai chiều (Dual IR):** Nhận tín hiệu `IN` hoặc `OUT` từ `smartcampus/v1/telemetry/room/{room_id}/occupancy`. Sử dụng giao dịch `db.begin()` với `with_for_update()` để tính toán số người tức thời `new_count = max(last_count + delta, 0)` chống race-condition. Tự động chuyển mode phòng về `SAVING` khi `new_count == 0`.
* **FR-SD-03 — Phát hiện khói & Leo thang trạng thái (MQ-2):** Đọc nồng độ khói, kiểm tra ngưỡng báo động. Kích hoạt leo thang: Lần 1 $\rightarrow$ chuyển FSM sang `SUSPECTED`; Lần 2 trong vòng 5 giây $\rightarrow$ chuyển FSM sang `EMERGENCY`.

### 3. Máy Trạng thái Phòng (Room Finite State Machine - FSM)
Module `feature/FSM/statemachine.py` quản lý 7 trạng thái hoạt động độc lập của từng phòng:
```
SAVING ──(IR > 0, no GV)──► SELF_STUDY ──(GV quẹt thẻ)──► LECTURE
  ▲                              ▲                            │
  │                              │                            ▼
  │ (IR = 0)                     └──────── (Kết thúc) ─────── EXAM
  └───────────────────────────────────────────────────────────┤
                                                              ▼
               LOCK ◄──(An ninh bảo vệ)── EMERGENCY ◄──(Khói)── SUSPECTED
```
* **Ma trận chuyển đổi an toàn (`_ROOM_TRANSITIONS`):** Kiểm tra tính hợp lệ trước khi cho phép chuyển mode.
* **Emergency Override:** `EMERGENCY` ghi đè mọi trạng thái để mở bung chốt cửa thoát hiểm và hú còi, ngoại trừ trạng thái `LOCK` (phòng đã khóa bảo vệ).
* **Manual Override & State Recovery:** Hỗ trợ lệnh khôi phục `recover_state()` đưa phòng từ `EMERGENCY` về trạng thái an toàn trước đó, đồng thời đặt lại trạng thái khói `NORMAL`.
* **Actuator Dispatch:** Khi trạng thái phòng thay đổi, hệ thống đồng thời phát lệnh điều khiển đèn LED chỉ báo tương ứng và gửi retained message lên `smartcampus/v1/room/{room_id}/state`.

### 4. Kiểm soát Ra vào & Điểm danh RFID (RFID & Access Control)
Module `feature/RFID/attendance.py` và `feature/RFID/sync_router.py`:
* **FR-RF-01 — Đăng ký thẻ lạ tại Hành lang:**
  * Node Hành lang gửi yêu cầu lên `smartcampus/v1/card/registration/request`.
  * Edge lưu vào bảng `card_registration_requests` (`status = PENDING`).
  * Khi Admin duyệt trên Web, Central Backend gọi REST API `POST /api/cards/sync` hoặc `POST /api/cards/sync-bulk` để cập nhật bảng `users` (`card_uid`) trên Edge Gateway.
  * Đồng thời, gói tin phản hồi `smartcampus/v1/card/registration/response/{mac_address}` được xuất bản để ESP32 chuyển LED xanh lá và cập nhật màn hình OLED.
* **FR-RF-02 — Giảng viên nhận phòng:** Quét thẻ mở phiên học (`RoomSession`), chuyển FSM sang `LECTURE`, bật tiện nghi và mở cửa sổ điểm danh 15 phút. Quẹt lại lần hai để đóng lớp và đưa phòng về `SAVING`.
* **FR-RF-03 — Sinh viên điểm danh:** Quét thẻ trong 15 phút đầu giờ ghi nhận `late = false`; quét sau 15 phút ghi nhận `late = true`; không thuộc lớp bị từ chối và phát còi dài.
* **FR-RF-04 — Động cơ phát hiện lệch quân số (Discrepancy Engine):** Tự động so sánh số lượng người do cảm biến hồng ngoại Dual IR đếm được (`occupancy_count`) với số sinh viên điểm danh (`attendance_count`):
  $$\Delta = \text{Occupancy} - \text{Attendance}$$
  Phát hiện người trốn điểm danh hoặc người lạ vào lớp, xuất bản lên `smartcampus/v1/room/{room_id}/discrepancy`.

### 5. Đường ống Thi hành Lệnh Chấp hành (Command Execution Pipeline)
Module `feature/command/executor.py` xử lý toàn bộ lệnh điều khiển từ API và AI Agent:
* **Xác thực lệnh hợp lệ:** Kiểm tra loại thiết bị (`door`, `fan`, `light`, `buzzer`, `mode`) và giá trị hợp lệ.
* **Lưu vết và phát MQTT:** Tạo bản ghi `Command` trong DB với trạng thái `PENDING`, xuất bản lệnh lên topic `smartcampus/v1/command/room/{room_id}`.
* **Xử lý ACK:** Nhận xác nhận từ ESP32 trên `smartcampus/v1/ack/device/{mac}/command/{cmd_id}` để cập nhật trạng thái `SUCCESS` hoặc `FAILED`.

---

## 🗄️ Cấu trúc Cơ sở Dữ liệu (TimescaleDB / PostgreSQL 17)

```
┌────────────────────────────────────────────────────────────────────────┐
│                        BẢNG QUAN HỆ CỐT LÕI                            │
│  - users: user_id (PK), card_uid (UK), username, full_name, role       │
│  - room: room_id (PK), room_name, room_type, capacity, is_active       │
│  - device: device_id (PK), mac_address (UK), room_id (FK), status      │
│  - classes: class_id (PK), course_code, class_name, lecturer_id (FK)   │
│  - class_enrollments: enrollment_id (PK), class_id (FK), user_id (FK)  │
│  - room_sessions: session_id (PK), room_id (FK), lecturer_id (FK),     │
│    started_at, ended_at, attendance_deadline                           │
│  - attendance_records: record_id (PK), user_id (FK), session_id (FK),  │
│    attended_at, late                                                   │
│  - card_registration_requests: request_id (PK), card_uid, device_id,   │
│    room_id, status (PENDING/APPROVED/REJECTED), assigned_user_id      │
│  - command: command_id (PK), room_id (FK), command_type, status       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────┴────────────────────────────────────┐
│                  TIMESCALEDB HYPERTABLES (Chuỗi thời gian)             │
│  1. environment       (environment_timestamp, room_id, temp, hum, co2)│
│  2. occupancy         (occupancy_timestamp, room_id, delta, count)    │
│  3. attendance_events (attendance_timestamp, room_id, card_uid, type) │
│  4. device_heartbeat  (heartbeat_timestamp, device_id, alive, uptime)  │
│  5. room_state        (state_timestamp, room_id, mode, status)         │
│  6. room_door_state   (door_timestamp, room_id, state)                 │
│  7. room_smoke_state  (smoke_timestamp, room_id, state)                │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 📂 Cấu trúc Thư mục Mã nguồn

```
edge/
├── database.py                 # Khởi tạo SQLAlchemy Async Session & TimescaleDB Engine
├── main.py                     # Ứng dụng FastAPI, Lifespan setup, đăng ký API routers
├── dockerfile                  # Docker build cho Edge Gateway service
├── docker-compose.yml          # Dựng TimescaleDB, Mosquitto, Alembic migration, Edge API
├── config.yaml                 # Cấu hình danh mục topic MQTT, QoS, Retain flags
├── requirement.txt             # Thư viện Python cần thiết
├── models/                     # Danh mục các ORM Models
│   ├── __init__.py             # Export models
│   ├── __enum.py               # Enums hệ thống (RoomModeEnum, UserRole, SmokeState...)
│   ├── user.py                 # Model Người dùng & Thẻ RFID
│   ├── room.py                 # Model Phòng học & Lịch sử trạng thái
│   ├── device.py               # Model Thiết bị & Heartbeat
│   ├── classroom.py            # Model Lớp học & Ghi danh
│   ├── session.py              # Model Phiên học thực tế
│   ├── attendance_record.py    # Model Bản ghi điểm danh chính thức
│   ├── card_registration.py   # Model Yêu cầu đăng ký thẻ hành lang
│   ├── command.py              # Model Lệnh điều khiển & ACK
│   └── telemetry/              # Models cho Hypertables
│       ├── environment.py      # Nhiệt độ, độ ẩm, CO2
│       ├── occupancy.py        # Đếm người vào/ra
│       └── attendance_event.py # Nhật ký quẹt thẻ
├── feature/                    # Module xử lý nghiệp vụ
│   ├── config/config.py        # Đọc cấu hình từ config.yaml và biến môi trường
│   ├── enum.py                 # Enums nghiệp vụ nội bộ
│   ├── FSM/
│   │   └── statemachine.py     # Room State Machine (7 trạng thái)
│   ├── RFID/
│   │   ├── attendance.py       # Xử lý quẹt thẻ điểm danh & phân loại vai trò
│   │   └── sync_router.py      # REST endpoints đồng bộ thẻ người dùng từ AI Backend
│   ├── command/
│   │   └── executor.py         # Pipeline thi hành lệnh điều khiển thiết bị
│   └── mqtt/
│       ├── mqtt_worker.py      # aiomqtt background listener & message dispatchers
│       └── publisher.py        # Các hàm xuất bản gói tin MQTT chuẩn hóa
├── mosquitto/                  # Cấu hình Mosquitto Broker
│   └── config/mosquitto.conf   # File cấu hình cổng 1883, 9001 và xác thực mật khẩu
└── experiment/                 # Bộ kịch bản kiểm thử & giả lập telemetry
    ├── seed_data.py            # Nạp dữ liệu phòng, giảng viên, sinh viên mẫu
    ├── simulate_attendance.py  # Giả lập luồng quẹt thẻ điểm danh
    ├── publish_telemetry.py    # Giả lập phát dữ liệu cảm biến thời gian thực
    └── run_all_demo.py         # Chạy toàn bộ luồng demo tích hợp
```

---

## 🚀 Hướng dẫn Cài đặt & Vận hành

### 1. Khởi chạy qua Docker Compose
```bash
cd edge
cp .env.example .env
docker compose up -d --build
```

Container tự động thực hiện:
* Khởi động TimescaleDB trên cổng `5434` (trong compose là 5432).
* Khởi động Mosquitto Broker trên cổng `1883` và WebSocket cổng `9001`.
* Thực thi tự động `alembic upgrade head` tạo toàn bộ bảng quan hệ và 7 Hypertables.
* Khởi chạy FastAPI Gateway tại cổng `8000`.

### 2. Kiểm tra Trạng thái Hoạt động
```bash
# Kiểm tra Health API
curl http://localhost:8000/health
# Trả về: {"status":"ok"}

# Xem danh sách Hypertables đã tạo trong TimescaleDB
curl http://localhost:8000/
```

### 3. Tài liệu Swagger REST API
Truy cập tài liệu tương tác tại: [http://localhost:8000/docs](http://localhost:8000/docs)

---
*Smart Campus BMS — Phân hệ Edge Computing Gateway.*
