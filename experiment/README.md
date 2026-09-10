# Thu Muc Thu Nghiem & Demo (Experiment)

Thu muc nay chua cac script doc lap giup ban tu thu nghiem, test gui MQTT message va kiem tra phan hoi cua he thong.

---

## Cach 1: Chay 1 lenh demo toan bo kich ban tu dong

Chay kich ban hoan chinh (Tao du lieu mau -> Ban telemetry -> Quet the GV mo lop -> Quet the SV diem danh -> Quet the la -> Kiem tra DB):

```bash
cd /home/user_kma_chinh/SmartCampus-edge
.venv/bin/python experiment/run_all_demo.py
```

---

## Cach 2: Tu thu nghiem tung buoc bang tay

### Buoc 1: Khoi tao du lieu mau (Phong 402, Giang vien, Sinh vien, Admin)
```bash
.venv/bin/python experiment/seed_data.py
```

### Buoc 2: Bat Listener de xem realtime Backend phan hoi MQTT
Mo **Terminal 1**:
```bash
.venv/bin/python experiment/listen_mqtt_responses.py
```
*(Giu nguyen terminal nay de xem backend tu phat lenh bat den/quat/coi khi ban thao tac).*

---

### Buoc 3: Thao tac gui du lieu o Terminal 2:

#### A. Gia lap cam bien Moi Truong & Nguoi
- Gui thong so moi truong binh thuong:
  ```bash
  .venv/bin/python experiment/publish_telemetry.py env
  ```
- Gui nguoi vao phong (`IN`):
  ```bash
  .venv/bin/python experiment/publish_telemetry.py in
  ```
- Gia lap bao chay (`EMERGENCY` - Cua tu mo + coi keu lien tuc):
  ```bash
  .venv/bin/python experiment/publish_telemetry.py smoke
  ```

#### B. Gia lap quet the RFID
- **Giang vien quet the** (Chuyen phong sang `LECTURE`, mo Session han 15p, bat Den, Quat, Coi):
  ```bash
  .venv/bin/python experiment/simulate_attendance.py gv
  ```
- **Sinh vien 1 quet the diem danh**:
  ```bash
  .venv/bin/python experiment/simulate_attendance.py sv1
  ```
- **Quan tri vien quet the mo cua**:
  ```bash
  .venv/bin/python experiment/simulate_attendance.py admin
  ```
- **The la chua dang ky quet** (Bi tu choi `REJECT` + coi bao):
  ```bash
  .venv/bin/python experiment/simulate_attendance.py unknown
  ```

---

### Buoc 4: Kiem tra du lieu duoc luu trong Database
Bat cu luc nao ban muon xem bang diem danh, trang thai phong FSM, telemetry moi nhat:
```bash
.venv/bin/python experiment/check_database.py
```

---

### Buoc 5: Kiem tra co che tu dong dong Session (Auto-end Session khi het gio)

File `experiment/test_auto_end_session.py` cung cap cac che do test:

#### A. Chay test tu dong tu A -> Z (Tao session het han 3s -> Doi -> Auto-end -> Assert ket qua):
```bash
.venv/bin/python experiment/test_auto_end_session.py demo
```

#### B. Test voi `main.py` dang chay thuc te:
1. Tao 1 session o trang thai ACTIVE nhung da qua gio ket thuc:
   ```bash
   .venv/bin/python experiment/test_auto_end_session.py setup
   ```
2. Quan sat terminal cua `main.py` (Polling task `auto_end_loop` se quet va log:
   `Found 1 room(s) with expired sessions` va `Automatically ended session ...`).
   *(Tip: Khi test co the set bien moi truong `SESSION_AUTO_END_POLL_INTERVAL=5` khi chay `main.py` de poll moi 5 giay thay vi 5 phut)*.
3. Kiem tra lai trang thai trong database:
   ```bash
   .venv/bin/python experiment/test_auto_end_session.py status
   ```
4. Kich hoat dong session ngay lap tuc bang tay (neu muon):
   ```bash
   .venv/bin/python experiment/test_auto_end_session.py trigger
   ```
