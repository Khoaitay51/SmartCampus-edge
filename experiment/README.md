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
