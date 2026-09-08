# Smart Campus BMS — Technical Documentation & Architecture Specification

> **Hệ thống Quản lý Tòa nhà Thông minh (Building Management System - BMS) cho Khuôn viên Đại học**  
> **Edge Gateway & Backend Service** xây dựng trên nền tảng **FastAPI**, **AsyncIO**, **AioMQTT**, **TimescaleDB (PostgreSQL 17)**, và **Eclipse Mosquitto Broker**.

---

## Mục lục
1. [Tổng quan hệ thống & Kiến trúc (System Architecture)](#1-tổng-quan-hệ-thống--kiến-trúc-system-architecture)
2. [Bản đồ đặc tả yêu cầu chức năng (FR Traceability Matrix)](#2-bản-đồ-đặc-tả-yêu-cầu-chức-năng-fr-traceability-matrix)
   - [1. Device Management (Quản lý thiết bị)](#1-device-management-quản-lý-thiết-bị)
   - [2. Sensor Data Collection (Thu thập dữ liệu cảm biến)](#2-sensor-data-collection-thu-thập-dữ-liệu-cảm-biến)
   - [3. Room State Machine - FSM (Máy trạng thái phòng)](#3-room-state-machine---fsm-máy-trạng-thái-phòng)
   - [4. Actuator Control (Điều khiển cơ cấu chấp hành)](#4-actuator-control-điều-khiển-cơ-cấu-chấp-hành)
   - [5. RFID & Access Control (Xác thực & Kiểm soát truy cập)](#5-rfid--access-control-xác-thực--kiểm-soát-truy-cập)
   - [6. Session & Attendance Management (Quản lý phiên học & Điểm danh)](#6-session--attendance-management-quản-lý-phiên-học--điểm-danh)
   - [7. AI Pipeline & Decision Engine (Hệ thống AI & Đưa ra quyết định)](#7-ai-pipeline--decision-engine-hệ-thống-ai--đưa-ra-quyết-định)
   - [8. Scenario Manager (Quản lý kịch bản mô phỏng)](#8-scenario-manager-quản-lý-kịch-bản-mô-phỏng)
   - [9. Digital Twin (Bản sao số Unity 2D)](#9-digital-twin-bản-sao-số-unity-2d)
   - [10. Evaluation Framework (Đánh giá hiệu năng)](#10-evaluation-framework-đánh-giá-hiệu-năng)
3. [Giao thức truyền thông MQTT & JSON Message Contracts](#3-giao-thức-truyền-thông-mqtt--json-message-contracts)
4. [Cơ sở dữ liệu & TimescaleDB Hypertables](#4-cơ-sở-dữ-liệu--timescaledb-hypertables)
5. [Cấu trúc mã nguồn dự án (Codebase Structure)](#5-cấu-trúc-mã-nguồn-dự-án-codebase-structure)
6. [Hướng dẫn cài đặt, vận hành & Kịch bản thực nghiệm (Deployment & Demo)](#6-hướng-dẫn-cài-đặt-vận-hành--kịch-bản-thực-nghiệm-deployment--demo)

---

## 1. Tổng quan hệ thống & Kiến trúc (System Architecture)

Hệ thống **Smart Campus Building Management System (BMS)** là giải pháp toàn diện kết hợp giữa phần cứng IoT biên (ESP32 Nodes), Gateway xử lý biên tốc độ cao (FastAPI + AsyncIO), Broker truyền tin thời gian thực (Eclipse Mosquitto), Cơ sở dữ liệu chuỗi thời gian tối ưu hóa (TimescaleDB trên PostgreSQL 17), mô hình AI suy luận hỗ trợ ra quyết định (Qwen 1B / Gemini), và giao diện điều hành trực quan hóa 2D (Unity Digital Twin).

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                      IoT Edge Device Layer (ESP32)                      │
 │   DHT22 (Temp/Hum) │ Dual IR (Occupancy) │ MQ2 (Smoke) │ RC522 (RFID)   │
 │   WS2812B (LED)    │ Door Servo (Lock)   │ Buzzer      │ OLED Display   │
 └────────────────────────────────────┬────────────────────────────────────┘
                                      │ MQTT (TCP 1883 / TLS)
                                      ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                  MQTT Messaging Broker (Eclipse Mosquitto)              │
 │   - QoS 1 Delivery Guarantee   - LWT (Last Will & Testament)            │
 │   - Retained Topics for States - Dynamic Topic Namespace: smartcampus/v1│
 └────────────────────────────────────┬────────────────────────────────────┘
                                      │ Async MQTT Pub/Sub
                                      ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                       SmartCampus-edge Backend                          │
 │  ┌───────────────────────────────────────────────────────────────────┐  │
 │  │               FastAPI Async Gateway (main.py)                     │  │
 │  │  - Lifespan MQTT Worker Listener (aiomqtt)                        │  │
 │  │  - REST APIs: System Health, Hypertable Metadata, Room Status    │  │
 │  │  - WebSocket Server for Digital Twin Realtime Sync (< 200ms)      │  │
 │  └───────────────────┬───────────────────────────────┬───────────────┘  │
 │                      ▼                               ▼                  │
 │  ┌────────────────────────────────┐  ┌───────────────────────────────┐  │
 │  │  Room FSM Engine (statemachine)│  │  RFID & Attendance Service    │  │
 │  │  - 7 Discrete Operating States │  │  - Check-in / Check-out Window│  │
 │  │  - State Recovery & Escalation │  │  - Realtime Discrepancy Engine│  │
 │  │  - Hardware Actuator Dispatch  │  │  - Anti-passback & Validation │  │
 │  └───────────────────┬────────────┘  └───────────────┬───────────────┘  │
 └──────────────────────┼───────────────────────────────┼──────────────────┘
                        │ SQLAlchemy 2.0 (asyncpg)      │
                        ▼                               ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                TimescaleDB / PostgreSQL 17 Storage Engine               │
 │  - Relational Core: users, classes, room, room_sessions, device, command│
 │  - 8 Time-series Hypertables: environment, occupancy, attendance_events,│
 │    device_heartbeat, room_state, room_door_state, room_smoke_state...   │
 └────────────────────────────────────┬────────────────────────────────────┘
                                      │ REST API / RAG Embeddings
                                      ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                     AI Pipeline & Decision Engine                       │
 │  - Operational Context Generator (15-min sliding window telemetry)      │
 │  - SLM Tool Calling Agent (Qwen 1B ReAct) & Natural Lang Bot (Gemini)   │
 │  - Cosine Validation (Hallucination filter) & EWMA Sensor Forecasting   │
 └────────────────────────────────────┬────────────────────────────────────┘
                                      │ WebSocket (< 200ms)
                                      ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                    Digital Twin 2D Dashboard (Unity)                    │
 │  - Realtime Campus Map: Room color synced with FSM State                │
 │  - Telemetry Sidebar, Attendance Notifications, Unknown Card Popups     │
 │  - Human-in-the-loop Action Approval Modal ([Execute] / [Ignore])       │
 └─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Bản đồ đặc tả yêu cầu chức năng (FR Traceability Matrix)

Hệ thống đáp ứng trọn vẹn 10 nhóm yêu cầu chức năng (Functional Requirements - FR) từ cấp độ thiết bị, truyền thông, máy trạng thái, kiểm soát truy cập đến trí tuệ nhân tạo:

### 1. Device Management (Quản lý thiết bị)

| Mã FR | Tên yêu cầu | Mô tả chi tiết chức năng | Hiện thực trong mã nguồn & Cơ chế hoạt động |
|---|---|---|---|
| **FR-DM-01** | Auto provisioning | Khi ESP32 boot lần đầu chưa có config, đọc MAC từ Wi-Fi chip và gửi request đăng ký lên broker. | - **Topic**: `smartcampus/v1/device/provision/request`<br>- **Worker**: `_handle_provision_request()` trong `feature/mqtt/mqtt_worker.py`<br>- **DB**: Ghi vào bảng `device` / bản ghi provisioning với trạng thái `PENDING`, lưu `mac_address`, `firmware_version`. |
| **FR-DM-02** | Room assignment | Admin gán `room_id` cho node qua popup trên Digital Twin; mapping lưu DB và gửi về lưu NVS ESP32. | - **Topic**: `smartcampus/v1/device/provision/response/{mac_address}` (`retain=True`)<br>- **Hàm**: `publish_provisioning_response()` trong `feature/mqtt/publisher.py`<br>- **ESP32**: Đón gói tin cấu hình có `room_id`, `device_id`, `heartbeat_interval` và ghi vào bộ nhớ Flash NVS. |
| **FR-DM-03** | OTA update | Hỗ trợ cập nhật firmware từ xa qua MQTT mà không cần cáp nạp vật lý. | - **Topic**: `smartcampus/v1/command/device/{mac_address}`<br>- **Enum & Function**: `DeviceCommandEnum.OTA`, hàm `publish_device_command()` trong `publisher.py`<br>- **Flow**: ESP32 nhận link binary HTTP/HTTPS, download phân vùng OTA, switch boot slot và phản hồi qua `command_ack`. |
| **FR-DM-04** | Heartbeat monitoring | ESP32 gửi heartbeat định kỳ 30s. Nếu quá 90s không nhận được tín hiệu -> kích hoạt cảnh báo offline. | - **Topic**: `smartcampus/v1/device/{device_id}/heartbeat`<br>- **Hypertable**: Lưu vào `device_heartbeat` (`alive`, `uptime`, `firmware_version`)<br>- **Worker**: `_handle_heartbeat()` trong `mqtt_worker.py`<br>- **Timeout**: Watchdog quét sau $3 	imes 30	ext{s} = 90	ext{s}$ không có heartbeat -> cập nhật `DeviceStatusEnum.offline` và gửi thông báo. |
| **FR-DM-05** | Last Will Testament (LWT) | Broker tự động phát hiện mất kết nối đột ngột (mất điện, đứt Wi-Fi) và broadcast báo offline. | - **MQTT LWT Configuration**: Khi ESP32 kết nối đến Mosquitto, thiết lập LWT message:<br>  - Topic: `smartcampus/v1/device/{mac_address}/status`<br>  - Payload: `{"device_status": "offline", "reason": "connection_lost"}`<br>  - Flag: `retain=True`, `QoS=1`<br>- Mosquitto tự động phát tán LWT ngay khi phát hiện TCP keepalive timeout. |

---

### 2. Sensor Data Collection (Thu thập dữ liệu cảm biến)

| Mã FR | Tên yêu cầu | Mô tả chi tiết chức năng | Hiện thực trong mã nguồn & Cơ chế hoạt động |
|---|---|---|---|
| **FR-SD-01** | Temperature & Humidity | Cảm biến DHT22 đọc nhiệt độ và độ ẩm mỗi 2 giây, publish gói tin JSON chuẩn lên broker. | - **Topic**: `smartcampus/v1/telemetry/room/{room_id}/environment`<br>- **Worker**: `_handle_environment_telemetry()` trong `feature/mqtt/mqtt_worker.py`<br>- **Hypertable**: Ghi vào bảng `environment` (TimescaleDB hypertable theo `environment_timestamp`). |
| **FR-SD-02** | Occupancy counting | Cảm biến hồng ngoại kép Dual IR (IR_A, IR_B) đếm người vào/ra dựa trên thứ tự kích hoạt chân cảm biến. | - **Hướng di chuyển**: IR_A trước IR_B -> Người vào (`IN`), ngược lại -> Người ra (`OUT`).<br>- **Topic**: `smartcampus/v1/telemetry/room/{room_id}/occupancy`<br>- **Khóa đồng thời**: Sử dụng `select(...).with_for_update()` trong transaction `db.begin()` để tính `new_count = max(last_count + delta, 0)` chống race condition.<br>- **Kích hoạt tự động**: Khi `new_count == 0` -> kích hoạt FSM phòng chuyển về `SAVING`. |
| **FR-SD-03** | Smoke detection | Cảm biến MQ2 quét nồng độ khói liên tục. Vượt ngưỡng lần 1 -> SUSPECTED, lần 2 trong 5s -> EMERGENCY. | - **Hypertable**: `room_smoke_state` và `environment`<br>- **Xử lý**: `handle_smoke_event()` trong `feature/FSM/statemachine.py`<br>- **Escalation**: Trạng thái khói leo thang từ `SUSPECTED` sang `EMERGENCY` nếu nhận cảnh báo tiếp theo trong khoảng thời gian cửa sổ. |
| **FR-SD-04** | RFID scanning | Đầu đọc RC522 đọc UID thẻ tại 2 vị trí kiến trúc: Hành lang (đăng ký) và Cửa phòng (điểm danh/truy cập). | - **Topic**: `smartcampus/v1/event/room/{room_id}/rfid`<br>- **Worker**: `_handle_rfid_event()` điều phối tới `attendance.handle_signed_user()` hoặc `attendance.handle_unsigned_user()`. |
| **FR-SD-05** | Air quality | Giám sát chất lượng không khí, nồng độ khí CO2/IAQ và publish realtime. | - **Topic**: `smartcampus/v1/telemetry/room/{room_id}/environment`<br>- **Trường dữ liệu**: `co2` (ppm), `air_quality` (chỉ số AQI/IAQ) lưu trữ vào hypertable `environment`, phục vụ thuật toán dự báo xu hướng EWMA. |

---

### 3. Room State Machine - FSM (Máy trạng thái phòng)

Được quản lý bởi module độc lập `feature/FSM/statemachine.py`. Hệ thống hỗ trợ 7 trạng thái vận hành riêng biệt với thứ tự ưu tiên (Priority): `NORMAL` (0), `WARNING` (50), `EMERGENCY` (100).

```
                ┌──────────────────────────────────────────────┐
                │                                              │
                ▼                                              │
          ┌───────────┐         IR count > 0, no GV            │
          │  SAVING   ├──────────────────────────────────────┐ │
          └─────┬─────┘                                      │ │
                │                                            ▼ │
                │ IR count = 0                     ┌───────────────┐
                ├──────────────────────────────────┤  SELF_STUDY   │
                │                                  └───────┬───────┘
                │ GV quét thẻ RFID                         │ GV quét thẻ RFID
                ▼                                          ▼
          ┌───────────┐    Admin/Web Trigger        ┌─────────────┐
          │  LECTURE  ├────────────────────────────►│    EXAM     │
          └─────┬─────┘◄────────────────────────────┴──────┬──────┘
                │       EXAM kết thúc                      │
                │                                          │
    Admin Lock  │                                          │ Admin Lock
                ▼                                          ▼
          ┌───────────┐                              ┌───────────┐
          │   LOCK    │◄─────────────────────────────┤ EMERGENCY │
          └───────────┘  (LOCK KHÔNG BỊ OVERRIDE)    └─────▲─────┘
                ▲                                          │
                │                                          │ Smoke #2 (<= 5s)
                │                                    ┌─────┴─────┐
                └────────────────────────────────────┤ SUSPECTED │
                     Smoke #1                        └───────────┘
```

| Mã FR | Tên yêu cầu | Chi tiết thực thi |
|---|---|---|
| **FR-FSM-01** | 7 Discrete States | 7 trạng thái chuẩn: `SAVING`, `SELF_STUDY`, `LECTURE`, `EXAM`, `LOCK`, `SUSPECTED`, `EMERGENCY` (`RoomState` enum kế thừa `BaseState`). |
| **FR-FSM-02** | Auto transition | Ma trận chuyển đổi tự động kiểm tra tính hợp lệ qua `_ROOM_TRANSITIONS` trong `statemachine.py`. Tự động chuyển mode dựa trên tín hiệu cảm biến IR, RFID giảng viên, sự kiện khói hoặc lệnh điều khiển web. |
| **FR-FSM-03** | Emergency override | `EMERGENCY` (Priority 100) ghi đè tức thì mọi trạng thái khác. **Đặc biệt**: Trạng thái `LOCK` được bảo vệ tuyệt đối và không bị ghi đè bởi `EMERGENCY` (bảo an phòng trống). |
| **FR-FSM-04** | State persistence & Recovery | Khi thoát tình huống khẩn cấp, hàm `state_recovery()` truy vấn bản ghi trạng thái không-EMERGENCY gần nhất trong `room_state` để đưa phòng trở lại trạng thái trước đó (VD: `LECTURE` hoặc `SELF_STUDY`) và reset `SmokeState` về `NORMAL`. |
| **FR-FSM-05** | State publish | Mỗi khi trạng thái thay đổi, hệ thống gọi `publish_room_state()` gửi lên topic `smartcampus/v1/room/{room_id}/state` với cờ `retain=True` và `QoS=1`. |

---

### 4. Actuator Control (Điều khiển cơ cấu chấp hành)

| Mã FR | Thiết bị chấp hành | Cơ chế điều khiển & Logic tự động |
|---|---|---|
| **FR-AC-01** | WS2812B LED strip | Báo hiệu màu sắc trực quan theo trạng thái FSM:<br>- `SAVING`: Tắt hoàn toàn<br>- `SELF_STUDY`: Xanh nhạt (Light Cyan)<br>- `LECTURE`: Trắng (White)<br>- `EXAM`: Vàng hổ phách (Amber Yellow)<br>- `SUSPECTED`: Cam (Orange)<br>- `EMERGENCY`: Đỏ nhấp nháy (Blinking Red)<br>- `LOCK`: Xám mờ (Dim Grey) |
| **FR-AC-02** | Servo Door Lock | FSM Servo cửa độc lập với Room FSM gồm 2 trạng thái: `LOCKED` và `UNLOCKED` (lưu vào hypertable `room_door_state`).<br>- Vào chế độ `EXAM` -> Tự động kích hoạt `publish_room_command(DOOR, LOCKED)`<br>- Vào chế độ `EMERGENCY` -> Ngay lập tức mở chốt `publish_room_command(DOOR, UNLOCKED)` mở lối thoát hiểm. |
| **FR-AC-03** | Fan Control | Quạt thông gió điều khiển qua lệnh `publish_room_command(FAN, ON/OFF)`. Chỉ kích hoạt theo khuyến nghị của AI hoặc lệnh thủ công từ quản trị viên sau khi có xác nhận (Human-in-the-loop). |
| **FR-AC-04** | Buzzer (Còi báo) | - `EMERGENCY`: Hú còi liên tục ngay lập tức ở cấp độ phần cứng ESP32 local (không phụ thuộc vào đường truyền cloud/gateway).<br>- `EXAM start`: 2 tiếng beep ngắn.<br>- `RFID reject`: 1 tiếng buzzer kéo dài.<br>- `RFID success`: 1 tiếng beep ngắn xác nhận. |
| **FR-AC-05** | OLED Display | Màn hình I2C tại cửa hiển thị 3 vùng thông tin: (1) Họ tên và vai trò người vừa quét thẻ (GV/SV), (2) Chỉ số môi trường thời gian thực (Temp/Hum/CO2), (3) Trạng thái kết nối WiFi và MQTT. |

---

### 5. RFID & Access Control (Xác thực & Kiểm soát truy cập)

Module `feature/RFID/attendance.py` đảm nhận toàn bộ luồng nghiệp vụ kiểm soát truy cập và định danh người dùng:

- **FR-RF-01 — Unknown card registration**: Khi một thẻ chưa có UID trong bảng `users` được quét tại node hành lang, gateway kích hoạt `handle_unsigned_user()`, ghi nhận sự kiện `AttendanceEventType.REJECT` vào `attendance_events`, đồng thời đẩy thông báo kèm UID lên Digital Twin để Admin gán thông tin sinh viên/giảng viên.
- **FR-RF-02 — Lecturer check-in**: Khi giảng viên quét thẻ hợp lệ:
  - Nếu phòng chưa có phiên học: Tự động khởi tạo phiên học (`RoomSession`), chuyển FSM phòng sang `LECTURE`, mở cửa sổ điểm danh 15 phút, bật đèn và quạt thông qua lệnh MQTT.
  - Nếu phòng đang có phiên học của chính giảng viên đó: Xem như giảng viên kết thúc ca dạy (Check-out) -> đóng phiên học và đưa phòng về `SAVING`.
- **FR-RF-03 — Student check-in**: Sinh viên quét thẻ tại cửa phòng:
  - Hệ thống kiểm tra sinh viên có trong danh sách ghi danh của lớp học (`class_enrollments`).
  - Trong vòng 15 phút đầu (`timestamp <= attendance_deadline`): Ghi nhận có mặt đúng giờ (`late = false`) vào bảng `attendance_records`.
  - Sau 15 phút đầu: Ghi nhận đi muộn (`late = true`).
  - Không có tên trong lớp: Bị từ chối (`REJECT`) và còi báo vang lên.
- **FR-RF-04 — Unauthorized access**: Thẻ không tồn tại hoặc không đủ thẩm quyền -> Kích hoạt lệnh `BUZZER -> ON` (tiếng dài), ghi log từ chối vào `attendance_events` và cảnh báo lên Digital Twin.
- **FR-RF-05 — Exam mode access**: Trong chế độ `EXAM`, cửa khóa tự động. Chỉ những sinh viên thuộc danh sách phòng thi mới được cấp quyền mở cửa vào phòng; sinh viên lớp khác quét thẻ sẽ bị từ chối ngay lập tức.

---

### 6. Session & Attendance Management (Quản lý phiên học & Điểm danh)

- **FR-SA-01 — Session creation**: Khởi tạo ngay khi giảng viên check-in thành công: `session_start_timestamp = NOW()`, `attendance_deadline_timestamp = NOW() + 15 phút`, lưu vào bảng `room_sessions`.
- **FR-SA-02 — Session closure**: Đóng phiên học theo thứ tự ưu tiên:
  1. *Ưu tiên 1*: Giảng viên quét thẻ check-out kết thúc ca học.
  2. *Ưu tiên 2*: Đến giờ kết thúc ca học theo thời khóa biểu cấu hình sẵn.
  3. *Fallback*: Tự động đóng sau thời gian tối đa (`started_at + 45 phút` hoặc timeout cấu hình).
- **FR-SA-03 — Absence tracking (Theo dõi vắng mặt)**: Khi phiên học kết thúc, hệ thống đối soát bảng ghi danh `class_enrollments` với `attendance_records`. Sinh viên vắng mặt là người có tên trong lớp nhưng không có bản ghi điểm danh tương ứng.
- **FR-SA-04 — Late tracking (Theo dõi đi muộn)**: Đánh dấu cờ `late = True` cho các lượt điểm danh sau thời hạn 15 phút đầu giờ.
- **FR-SA-05 — Orphan cleanup & Discrepancy Engine**:
  - Worker định kỳ quét các phiên học quá 45 phút chưa đóng để tự động kết thúc ca.
  - **Công cụ phát hiện gian lận (Discrepancy Engine)**: Hàm `check_and_publish_discrepancy()` trong `attendance.py` tự động so sánh số người do cảm biến IR đếm được (`occupancy_count`) với số sinh viên đã quét thẻ điểm danh (`attendance_count`):
    $$	ext{Discrepancy} = 	ext{Occupancy} - 	ext{Attendance}$$
    Publish định kỳ lên topic `smartcampus/v1/room/{room_id}/discrepancy` với các trạng thái `MATCH` ($\Delta = 0$), `EXTRA_PEOPLE` ($\Delta > 0$, có người lạ hoặc trốn điểm danh), hoặc `MISSING_PEOPLE` ($\Delta < 0$).

---

### 7. AI Pipeline & Decision Engine (Hệ thống AI & Đưa ra quyết định)

Kiến trúc tích hợp chi tiết được quy định trong tài liệu hợp đồng `AI_AGENT_INTEGRATION.md`:

```
┌────────────────────────┐      POST /evaluate       ┌────────────────────────┐
│  FastAPI Gateway       ├──────────────────────────►│   AI Agent Service     │
│  (Edge Backend)        │◄──────────────────────────┤   (Qwen 1B / ReAct)    │
└───────────┬────────────┘   Recommendation JSON     └───────────┬────────────┘
            │                                                    │
            │ RAG Query Endpoints                                │ Tool Calls
            │ (search_history, get_telemetry, compare_rooms)    │
            ▼                                                    ▼
┌────────────────────────┐                           ┌────────────────────────┐
│  TimescaleDB + pgvector│                           │ Digital Twin Dashboard │
│  (15-min Context Snapshot)                         │ (Popup [Execute]/[Ignore])
└────────────────────────┘                           └────────────────────────┘
```

- **FR-AI-01 — LLM Summarizer**: Scheduler định kỳ (1h / 1d / 1w) gom dữ liệu chuỗi thời gian, gọi mô hình ngôn ngữ tóm tắt hành vi phòng học và lưu trữ vector nhúng vào PostgreSQL thông qua tiện ích **pgvector**.
- **FR-AI-02 — Cosine validation**: Đánh giá độ tương đồng Cosine giữa vector tóm tắt mới và vector ngữ cảnh cũ. Dựa trên độ lệch số liệu cảm biến thô (Delta) kết hợp Cosine score để phân biệt chính xác giữa hiện tượng ảo giác (Hallucination) và sự kiện bất thường có thật (Significant Event).
- **FR-AI-03 — Operational context generation**: Khi xảy ra sự kiện bất thường, Gateway tự động tổng hợp snapshot 15 phút gần nhất: thông tin trạng thái phòng, Min/Max/Avg nhiệt độ, độ ẩm, CO2, biến động người vào/ra và tình trạng phiên học để làm đầu vào cho Agent.
- **FR-AI-04 — Tool calling agent (Qwen 1B)**: Mô hình SLM Qwen 1B áp dụng kỹ thuật ReAct, chọn hành động tối ưu từ danh mục tool cố định: `set_fan`, `set_door`, `set_mode`, `trigger_buzzer`, `send_alert`, `set_led`.
- **FR-AI-05 — Human-in-the-loop (HITL)**:
  - Chế độ `HUMAN_INTERVENTION`: Agent gửi đề xuất, Digital Twin hiển thị popup để người vận hành bấm `[Execute]` hoặc `[Ignore]`. Đề xuất hết hạn sau 5 phút nếu không có phản hồi.
  - Chế độ `SELF_EXECUTE`: Tự động thi hành khi độ tin cậy $\ge 0.8$, kèm cơ chế an toàn: Cooldown 60s, giới hạn tối đa 50 lệnh/phòng/ngày, và các lệnh can thiệp cửa/mode luôn yêu cầu phê duyệt thủ công.
- **FR-AI-06 — Natural Language Chatbot (Gemini API)**: Cho phép truy vấn hệ thống bằng ngôn ngữ tự nhiên, tự động phân tích và chuyển đổi các mốc thời gian tương đối ("hôm qua", "tuần trước", "tiết trước") thành khoảng thời gian chính xác để truy vấn cơ sở dữ liệu.
- **FR-AI-07 — Sensor Prediction (EWMA)**: Thuật toán dự báo Exponentially Weighted Moving Average phân tích xu hướng nhiệt độ và khí CO2, đưa ra dự báo trước 15 phút và phát trực tiếp lên Digital Twin.

---

### 8. Scenario Manager (Quản lý kịch bản mô phỏng)

- **FR-SM-01 — Button scenarios**: Hỗ trợ 4 nút bấm vật lý (hoặc trigger qua MQTT/UI) tại hành lang để kích hoạt nhanh các kịch bản diễn tập:
  - `BTN1 - Emergency`: Kích hoạt báo cháy giả lập (MQ2 nồng độ cao -> `SUSPECTED` -> `EMERGENCY`).
  - `BTN2 - Exam Mode`: Chuyển đổi bật/tắt nhanh chế độ thi cử (khóa cửa, đổi màu đèn Amber).
  - `BTN3 - Occupancy Overflow`: Giả lập lưu lượng người vượt quá sức chứa tối đa của phòng.
  - `BTN4 - Lock All / Unlock All`: Khóa khẩn cấp toàn bộ tòa nhà hoặc giải tỏa mở cửa đồng loạt.
- **FR-SM-02 — Fake telemetry**: Thư mục `experiment/` cung cấp đầy đủ các script mô phỏng: `publish_telemetry.py`, `simulate_attendance.py`, và `run_all_demo.py` phát sinh dữ liệu cảm biến và sự kiện thẻ giống 100% gói tin từ phần cứng thật.

---

### 9. Digital Twin (Bản sao số Unity 2D)

- **FR-DT-01 — Campus map 2D**: Bản đồ mặt bằng Unity 2D trực quan hóa 2 phòng học và hành lang; màu nền phòng cập nhật tức thời theo trạng thái FSM tương ứng.
- **FR-DT-02 — Room detail sidebar**: Bấm vào từng phòng để mở sidebar theo dõi chi tiết: Nhiệt độ, Độ ẩm, Nồng độ CO2, Số lượng người hiện tại, Trạng thái cửa, Trạng thái quạt, và Phiên học đang diễn ra.
- **FR-DT-03 — AI recommendation popup**: Khi AI Agent đề xuất giải pháp, popup hiển thị tên công cụ, lý do, mức độ khẩn cấp cùng 2 nút hành động `[Execute]` và `[Ignore]`.
- **FR-DT-04 — RFID assignment popup**: Hiển thị hộp thoại khi có thẻ chưa đăng ký quét tại hành lang, hỗ trợ nhập nhanh tên sinh viên/giảng viên và gán thẻ trực tiếp.
- **FR-DT-05 — Attendance notification**: Toast notification thông báo kết quả điểm danh theo thời gian thực (Họ tên, Trạng thái đúng giờ / đi muộn / bị từ chối).
- **FR-DT-06 — Prediction display**: Hiển thị biểu đồ so sánh xu hướng 15 phút tiếp theo giữa 2 kịch bản: Giữ nguyên hiện trạng vs Kích hoạt quạt thông gió.
- **FR-DT-07 — Realtime sync**: Kênh truyền WebSocket bảo đảm độ trễ đồng bộ từ node ESP32 đến giao diện Digital Twin dưới 200ms.
- **FR-DT-08 — Chatbot panel**: Khung chat tích hợp hỗ trợ người quản trị truy vấn báo cáo chuyên cần, so sánh môi trường giữa các phòng học.

---

### 10. Evaluation Framework (Đánh giá hiệu năng)

- **FR-EV-01 — Retrieval metrics**: Đánh giá hiệu quả tìm kiếm ngữ nghĩa của Chatbot RAG thông qua các chỉ số khoa học: **MRR** (Mean Reciprocal Rank), **MAP** (Mean Average Precision), và **Precision@K** theo mô hình phân cấp Parent-Offspring.
- **FR-EV-02 — Ablation study**: Phân tích đóng góp của từng thành phần trong mô hình AI Agent Qwen 1B qua 3 điều kiện thử nghiệm:
  - *Condition A*: Đầu vào chỉ gồm chuỗi JSON thô từ cảm biến.
  - *Condition B*: Đầu vào gồm Operational Context (ngữ cảnh 15 phút).
  - *Condition C*: Kết hợp Operational Context và cơ chế gọi công cụ (Combined Context + Tool Calling).
- **FR-EV-03 — Validation metrics**: Đánh giá độ tin cậy của thuật toán Cosine Validation: Xây dựng ma trận nhầm lẫn (Confusion Matrix), đo lường tỉ lệ dương tính giả (FPR), âm tính giả (FNR), và tỉ lệ trôi dạt ngữ nghĩa (Drift Rate).

---

## 3. Giao thức truyền thông MQTT & JSON Message Contracts

Hệ thống sử dụng không gian tên chuẩn: `smartcampus/v1/...`

### 3.1. Cấu trúc phong bì gói tin chuẩn (Standard Message Envelope)
Mọi gói tin truyền nhận qua MQTT giữa Gateway và các thiết bị đều tuân thủ cấu trúc envelope:
```json
{
  "message_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "source_timestamp": "2026-09-08T14:30:00.000000Z",
  "payload": {
    "...": "Dữ liệu payload nghiệp vụ cụ thể"
  }
}
```

### 3.2. Bảng danh mục Topic MQTT

| Nhóm chức năng | Chiều truyền | MQTT Topic Template | QoS | Retain | Ý nghĩa & Dữ liệu payload |
|---|---|---|:---:|:---:|---|
| **Provisioning Request** | Node -> Broker | `smartcampus/v1/device/provision/request` | 1 | False | Yêu cầu cấp phát: `mac_address`, `firmware_version`, `hardware_revision` |
| **Provisioning Response**| Gateway -> Node | `smartcampus/v1/device/provision/response/{mac_address}` | 1 | **True** | Trả cấu hình: `device_id`, `room_id`, `room_type`, `heartbeat_interval` |
| **Device Heartbeat** | Node -> Broker | `smartcampus/v1/device/{device_id}/heartbeat` | 1 | False | Báo sống định kỳ: `device_id`, `alive`, `firmware_version`, `uptime` |
| **Device Status** | Gateway/LWT -> All| `smartcampus/v1/device/{mac_address}/status` | 1 | **True** | Trạng thái kết nối: `device_status` (online/offline), `reason` |
| **Environment** | Node -> Gateway | `smartcampus/v1/telemetry/room/{room_id}/environment` | 1 | False | Dữ liệu môi trường: `temperature`, `humidity`, `smoke_state`, `co2` |
| **Occupancy** | Node -> Gateway | `smartcampus/v1/telemetry/room/{room_id}/occupancy` | 1 | False | Đếm người: `occupancy_type` (in/out), `occupancy_count` |
| **RFID Event** | Node -> Gateway | `smartcampus/v1/event/room/{room_id}/rfid` | 1 | False | Sự kiện quẹt thẻ: `room_id`, `card_uid`, `event_type` |
| **Room State** | Gateway -> All | `smartcampus/v1/room/{room_id}/state` | 1 | **True** | Trạng thái phòng FSM: `room_id`, `room_mode`, `room_status` |
| **Room Command** | Gateway -> Node | `smartcampus/v1/command/room/{room_id}` | 1 | False | Lệnh chấp hành: `command_type` (door/fan/light/buzzer), `command_value` |
| **Device Command** | Gateway -> Node | `smartcampus/v1/command/device/{mac_address}` | 1 | False | Lệnh quản trị thiết bị: `command_type` (ota/restart), `command_value` |
| **Command ACK** | Node -> Gateway | `smartcampus/v1/ack/device/{mac}/command/{command_id}` | 1 | False | Xác nhận thực thi: `command_id`, `success`, `error_message` |
| **Discrepancy** | Gateway -> All | `smartcampus/v1/room/{room_id}/discrepancy` | 1 | False | Độ lệch quân số: `occupancy_count`, `attendance_count`, `discrepancy`, `status` |
| **Scenario Trigger** | Any -> Broker | `smartcampus/v1/scenario/{scenario_id}` | 1 | False | Kích hoạt kịch bản diễn tập: `action`, `triggered_by` |

---

## 4. Cơ sở dữ liệu & TimescaleDB Hypertables

Hệ thống tích hợp **TimescaleDB trên PostgreSQL 17** tối ưu hóa lưu trữ chuỗi thời gian và đảm bảo toàn vẹn dữ liệu quan hệ.

```
 ┌──────────────────────┐         ┌──────────────────────┐
 │        users         │         │         room         │
 │  user_id (PK)        │         │  room_id (PK)        │
 │  card_uid (UK)       │         │  room_name           │
 │  role (Enum)         │         │  room_type (Enum)    │
 └──────────┬───────────┘         └──────────┬───────────┘
            │                                │
            │ 1:N                            │ 1:N
            ▼                                ▼
 ┌──────────────────────┐         ┌──────────────────────┐
 │    room_sessions     │         │        device        │
 │  session_id (PK)     │◄────────┤  device_id (PK)      │
 │  room_id (FK)        │         │  mac_address (UK)    │
 │  lecturer_id (FK)    │         │  room_id (FK)        │
 │  attendance_deadline │         │  device_status       │
 └──────────┬───────────┘         └──────────────────────┘
            │ 1:N
            ▼
 ┌──────────────────────┐
 │  attendance_records  │ (Bảng điểm danh chính thức: user_id, session_id, late)
 └──────────────────────┘

 ═════════════════════ TIMESCALEDB HYPERTABLES (Chuỗi thời gian) ═════════════════════
 1. environment       (environment_timestamp, room_id, temp, humidity, smoke_state, co2)
 2. occupancy         (occupancy_timestamp, room_id, occupancy_type, occupancy_count)
 3. attendance_events (attendance_timestamp, room_id, user_id, card_uid, event_type)
 4. device_heartbeat  (heartbeat_timestamp, device_id, alive, uptime, firmware_version)
 5. room_state        (room_state_timestamp, room_id, room_mode, room_status)
 6. room_door_state   (room_door_state_timestamp, room_id, door_state)
 7. room_smoke_state  (room_smoke_state_timestamp, room_id, smoke_state)
 8. room_event        (room_event_timestamp, room_id, room_mode, peripheral_action_id)
```

- **Hypertables**: Tự động phân mảnh (chunk partitioning) theo thời gian, tăng tốc độ ghi dữ liệu cảm biến đồng thời và hỗ trợ tính toán aggregate cực nhanh.
- **Concurrency Control**: Áp dụng cơ chế khóa bi quan (`with_for_update()`) cho các thao tác đếm người IR để loại trừ hoàn toàn hiện tượng lệch số đếm khi nhiều người bước qua cửa cùng lúc.

---

## 5. Cấu trúc mã nguồn dự án (Codebase Structure)

```
SmartCampus-edge/
├── alembic/                      # Quản lý migration cơ sở dữ liệu
│   ├── env.py                    # Cấu hình kết nối Async Alembic
│   └── versions/                 # Các file migration (hypertables, schema, models)
│       ├── 560716a1684b_initial_schema.py
│       ├── 41f6e90c15cf_add_door_smoke_state_models.py
│       └── a1b2c3d4e5f6_add_alive_column_to_device_heartbeat.py
├── feature/                      # Các module nghiệp vụ cốt lõi
│   ├── config/
│   │   └── config.py             # Đọc config.yaml và biến môi trường
│   ├── enum.py                   # Enum lệnh và trạng thái thiết bị
│   ├── FSM/
│   │   ├── __init__.py
│   │   └── statemachine.py       # Finite State Machine 7 trạng thái, priority, recovery
│   ├── mqtt/
│   │   ├── mqtt_worker.py        # Worker lắng nghe MQTT, phân luồng sự kiện và ghi DB
│   │   └── publisher.py          # Hàm đóng gói envelope và publish MQTT topics
│   └── RFID/
│       ├── __init__.py
│       └── attendance.py         # Nghiệp vụ điểm danh, kiểm tra hợp lệ, tính độ lệch
├── models/                       # Định nghĩa SQLAlchemy Models & Hypertables
│   ├── __enum.py                 # Định nghĩa Enum (UserRole, RoomMode, DoorState...)
│   ├── __init__.py               # Export các models
│   ├── attendance_record.py      # Bảng attendance_records
│   ├── classroom.py              # Bảng classes, class_enrollments
│   ├── command.py                # Bảng command theo dõi lịch sử lệnh
│   ├── device.py                 # Bảng device, device_status, device_heartbeat
│   ├── peripheral.py             # Bảng peripheral, peripheral_action
│   ├── room.py                   # Bảng room, room_state, room_door_state, room_smoke_state
│   ├── session.py                # Bảng room_sessions
│   ├── user.py                   # Bảng users
│   └── telemetry/                # Các models tương ứng Hypertables
│       ├── attendance_event.py
│       ├── environment.py
│       └── occupancy.py
├── mosquitto/                    # Cấu hình MQTT Broker
│   └── config/
│       ├── mosquitto.conf        # Cấu hình Mosquitto listener và auth
│       └── passwordfile          # File tài khoản phân quyền Mosquitto
├── experiment/                   # Công cụ mô phỏng, test bench và demo
│   ├── check_database.py         # Kiểm tra dữ liệu hiện có trong DB
│   ├── listen_mqtt_responses.py  # Lắng nghe các bản tin phản hồi qua MQTT
│   ├── publish_telemetry.py      # Phát dữ liệu cảm biến ảo
│   ├── seed_data.py              # Nạp dữ liệu mẫu (users, rooms, classes)
│   ├── simulate_attendance.py    # Giả lập quét thẻ điểm danh đúng giờ / đi muộn
│   └── run_all_demo.py           # Kịch bản chạy kiểm thử tích hợp toàn bộ hệ thống
├── config.yaml                   # File cấu hình định tuyến topic MQTT và lệnh
├── database.py                   # Thiết lập Async Engine & Session (asyncpg)
├── docker-compose.yml            # Khởi chạy Postgres (TimescaleDB), Mosquitto, Gateway API
├── dockerfile                    # Docker build cho FastAPI edge service
├── main.py                       # FastAPI application entrypoint & Lifespan worker
├── AI_AGENT_INTEGRATION.md       # Tài liệu đặc tả hợp đồng tích hợp AI Agent
├── JSON_contract_example.txt     # Bản mẫu các hợp đồng JSON qua MQTT
└── requirement.txt               # Danh mục thư viện Python
```

---

## 6. Hướng dẫn cài đặt, vận hành & Kịch bản thực nghiệm (Deployment & Demo)

### 6.1. Yêu cầu hệ thống (Prerequisites)
- Docker & Docker Compose v2 trở lên.
- Python 3.11+ (nếu chạy môi trường dev ngoài Docker).
- Mosquitto Clients (`mosquitto_pub`, `mosquitto_sub`) để kiểm tra thủ công.

### 6.2. Khởi chạy toàn bộ hệ thống qua Docker Compose

1. **Khởi tạo biến môi trường**:
   ```sh
   cp .env.example .env
   # Chỉnh sửa mật khẩu Database và tài khoản MQTT trong .env nếu cần
   ```

2. **Build và kích hoạt containers**:
   ```sh
   docker compose up --build -d
   ```
   *Quá trình trên tự động:*
   - Khởi động TimescaleDB (PostgreSQL 17).
   - Thiết lập tài khoản và khởi động Mosquitto Broker.
   - Thực thi `alembic upgrade head` để tạo bảng và 8 Hypertables.
   - Khởi chạy FastAPI Gateway tại cổng `8000`.

3. **Kiểm tra trạng thái hoạt động**:
   - Truy cập kiểm tra API Health: `curl http://localhost:8000/health` -> `{"status":"ok"}`
   - Xem danh sách Hypertables: `curl http://localhost:8000/`
   - Kiểm tra kết nối MQTT Broker: `curl http://localhost:8000/mqtt_check` -> `{"status":"ok"}`

### 6.3. Chạy demo kiểm thử tích hợp (End-to-End Test Suite)

Dự án cung cấp bộ script mô phỏng hoàn chỉnh trong thư mục `experiment/`:

```sh
# 1. Nạp dữ liệu nền tảng ban đầu (Phòng mẫu, Giảng viên, Sinh viên, Lớp học)
python experiment/seed_data.py

# 2. Giả lập luồng điểm danh tự động (Giảng viên mở lớp -> Sinh viên quét thẻ -> Tính độ lệch)
python experiment/simulate_attendance.py

# 3. Phát dữ liệu cảm biến thời gian thực (Nhiệt độ, độ ẩm, người ra vào)
python experiment/publish_telemetry.py

# 4. Kiểm tra dữ liệu được ghi nhận vào cơ sở dữ liệu
python experiment/check_database.py

# HOẶC: Chạy toàn bộ kịch bản demo tích hợp chỉ với 1 lệnh
python experiment/run_all_demo.py
```

---
*Tài liệu kỹ thuật được xây dựng đồng bộ và bám sát trực tiếp mã nguồn thực tế của hệ thống Smart Campus BMS Edge Gateway.*
