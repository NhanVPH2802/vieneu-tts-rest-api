# VieNeu-TTS REST API

Bộ triển khai **VieNeu-TTS + REST API + Voice Manager** dành cho Ubuntu Server.

Dự án bổ sung REST API và giao diện quản lý giọng clone cho VieNeu-TTS, giúp các server khác có thể:

* Lấy danh sách giọng có sẵn.
* Lưu giọng clone từ file WAV.
* Gọi TTS từ xa bằng REST API.
* Tạo thử và nghe giọng trực tiếp trên trình duyệt.
* Sử dụng chung kho giọng clone từ nhiều server.
* Tự động khởi động VieNeu-TTS và REST API khi Ubuntu khởi động.

---

# 1. Kiến trúc hệ thống

```text
                    ┌──────────────────────────┐
                    │      VieNeu-TTS WebUI    │
                    │        Port 7860         │
                    └────────────┬─────────────┘
                                 │
                          Gradio Client
                                 │
                    ┌────────────▼─────────────┐
                    │   VieNeu-TTS REST API    │
                    │        Port 8000         │
                    ├──────────────────────────┤
                    │ /api/health              │
                    │ /api/voices              │
                    │ /api/tts                 │
                    │ /api/custom-voices       │
                    │ /voice-manager           │
                    └────────────┬─────────────┘
                                 │
               ┌─────────────────┴──────────────────┐
               │                                    │
       Auto Video Server                    Server / App khác
```

VieNeu-TTS chỉ chạy nội bộ trên server TTS.

Các server khác nên gọi qua REST API cổng `8000`.

---

# 2. Chức năng

## VieNeu-TTS

* VieNeu-TTS v3 Turbo.
* Model int8.
* NeuCodec Distill.
* Tạo giọng tiếng Việt.
* Hỗ trợ preset voice.
* Hỗ trợ zero-shot voice cloning.

## REST API

Các endpoint chính:

```text
GET    /api/health
GET    /api/voices
POST   /api/preload
POST   /api/tts

GET    /api/custom-voices
POST   /api/custom-voices
GET    /api/custom-voices/{voice_id}/audio
DELETE /api/custom-voices/{voice_id}
```

## Voice Manager

Giao diện:

```text
http://SERVER_IP:8000/voice-manager
```

Cho phép:

* Upload file WAV.
* Đặt tên giọng.
* Tạo Voice ID.
* Chọn giới tính.
* Chọn vùng miền.
* Chọn phong cách.
* Khử nhiễu.
* Cắt khoảng lặng.
* Lưu giọng clone.
* Nghe lại reference audio.
* Tạo giọng thử.
* Xóa giọng clone.

---

# 3. Yêu cầu máy chủ

Khuyến nghị:

```text
OS:       Ubuntu Server 24.04 LTS
CPU:      4 vCPU trở lên
RAM:      8 GB trở lên
Disk:     40 - 50 GB trở lên
Network:  LAN hoặc Internet
```

Để sử dụng **voice cloning**, nên có ít nhất:

```text
RAM: 8 GB
Swap: 4 GB
```

RAM 4 GB không khuyến nghị vì PyTorch có thể sử dụng nhiều bộ nhớ khi xử lý reference audio.

---

# 4. Các cổng sử dụng

```text
7860    VieNeu-TTS Gradio WebUI
8000    VieNeu REST API + Voice Manager
```

Ví dụ server:

```text
VieNeu WebUI:
http://192.168.1.154:7860

REST API:
http://192.168.1.154:8000

Swagger:
http://192.168.1.154:8000/docs

Voice Manager:
http://192.168.1.154:8000/voice-manager
```

Thay `192.168.1.154` bằng IP server thực tế.

---

# 5. Cấu trúc project

```text
vieneu-tts-api-release/
├── api/
│   ├── app.py
│   └── voice-manager.html
│
├── scripts/
│   └── install.sh
│
├── systemd/
│   ├── vieneu.service
│   ├── vieneu-api.service
│   └── temp.conf
│
├── .env.example
├── .gitignore
├── requirements-api.txt
├── VERSION
└── README.md
```

---

# 6. Repo VieNeu-TTS sử dụng

Phiên bản VieNeu-TTS được cố định trong file:

```text
VERSION
```

Ví dụ:

```text
UPSTREAM_REPO=https://github.com/NhanVPH2802/VieNeu-TTS.git
UPSTREAM_COMMIT=556ce97ffb3731aeafed623391587a1598ecb501
```

Installer nên checkout đúng commit này để tránh việc upstream thay đổi làm lỗi hệ thống.

---

# 7. Cài đặt nhanh

Clone repository triển khai:

```bash
cd /opt
git clone https://github.com/NhanVPH2802/vieneu-tts-rest-api.git
cd vieneu-tts-rest-api
```

Chạy installer:

```bash
sudo bash scripts/install.sh
```

Installer sẽ tự động thực hiện:

```text
Cài package Ubuntu
        ↓
Clone VieNeu-TTS
        ↓
Checkout đúng commit
        ↓
Tạo Python environment
        ↓
Cài VieNeu-TTS
        ↓
Cài PyTorch CPU
        ↓
Cài REST API
        ↓
Sinh API Key
        ↓
Tạo thư mục runtime
        ↓
Cài systemd service
        ↓
Bật autostart
        ↓
Khởi động VieNeu-TTS
        ↓
Khởi động REST API
        ↓
Preload model
```

> Nếu repository VieNeu-TTS đang để Private, GitHub sẽ yêu cầu tài khoản và PAT có quyền đọc repository.

---

# 8. Cài đặt thủ công

Phần này dùng khi không sử dụng `install.sh`.

## 8.1. Cập nhật hệ thống

```bash
sudo apt update
sudo apt upgrade -y
```

Cài package:

```bash
sudo apt install -y \
  git \
  curl \
  wget \
  jq \
  ffmpeg \
  python3 \
  python3-venv \
  python3-pip \
  build-essential
```

---

# 9. Tạo user chạy VieNeu

```bash
sudo useradd \
  --system \
  --create-home \
  --shell /bin/bash \
  vieneu 2>/dev/null || true
```

---

# 10. Clone VieNeu-TTS

```bash
cd /opt
```

```bash
sudo -u vieneu git clone \
  https://github.com/NhanVPH2802/VieNeu-TTS.git
```

Checkout phiên bản cố định:

```bash
cd /opt/VieNeu-TTS
```

```bash
sudo -u vieneu git checkout \
  556ce97ffb3731aeafed623391587a1598ecb501
```

---

# 11. Cài VieNeu-TTS

Tạo virtual environment:

```bash
sudo -u vieneu python3 -m venv \
  /opt/VieNeu-TTS/.venv
```

Cập nhật pip:

```bash
sudo -u vieneu \
  /opt/VieNeu-TTS/.venv/bin/python \
  -m pip install --upgrade pip
```

Cài project:

```bash
cd /opt/VieNeu-TTS
```

```bash
sudo -u vieneu \
  /opt/VieNeu-TTS/.venv/bin/pip \
  install -e .
```

---

# 12. Cài PyTorch cho Voice Cloning

Voice cloning sử dụng PyTorch để xử lý Reference Audio.

Cài bản CPU:

```bash
sudo -u vieneu \
  /opt/VieNeu-TTS/.venv/bin/python \
  -m pip install \
  torch torchaudio \
  --index-url https://download.pytorch.org/whl/cpu
```

Kiểm tra:

```bash
sudo -u vieneu \
  /opt/VieNeu-TTS/.venv/bin/python - <<'PY'
import torch
import torchaudio

print("Torch:", torch.__version__)
print("Torchaudio:", torchaudio.__version__)
print("CUDA:", torch.cuda.is_available())
PY
```

Với máy CPU:

```text
CUDA: False
```

là bình thường.

---

# 13. Cài REST API

Tạo thư mục:

```bash
sudo mkdir -p /opt/vieneu-api
```

Copy:

```bash
sudo cp api/app.py \
  /opt/vieneu-api/app.py
```

```bash
sudo cp api/voice-manager.html \
  /opt/vieneu-api/voice-manager.html
```

Tạo virtual environment:

```bash
sudo python3 -m venv \
  /opt/vieneu-api/.venv
```

Cài dependencies:

```bash
sudo /opt/vieneu-api/.venv/bin/pip \
  install --upgrade pip
```

```bash
sudo /opt/vieneu-api/.venv/bin/pip \
  install -r requirements-api.txt
```

Đảm bảo có:

```bash
sudo /opt/vieneu-api/.venv/bin/pip \
  install python-multipart
```

---

# 14. Tạo thư mục runtime

```bash
sudo mkdir -p \
  /opt/vieneu-api/custom_voices \
  /opt/vieneu-api/upload_tmp \
  /opt/vieneu-api/tmp \
  /opt/vieneu-api/output
```

```bash
sudo chown -R vieneu:vieneu \
  /opt/vieneu-api
```

---

# 15. Tạo API Key

Sinh key ngẫu nhiên:

```bash
openssl rand -hex 32
```

Ví dụ:

```text
e9341xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Không chia sẻ API Key công khai.

---

# 16. Tạo file cấu hình API

Tạo:

```bash
sudo nano /etc/vieneu-api.env
```

Nội dung:

```env
VIENEU_GRADIO_URL=http://127.0.0.1:7860

VIENEU_API_KEY=THAY_BANG_API_KEY_CUA_BAN

VIENEU_VOICES_FILE=/opt/VieNeu-TTS/src/vieneu/assets/voices_v3_turbo.json

VIENEU_CUSTOM_VOICES_DIR=/opt/vieneu-api/custom_voices
VIENEU_UPLOAD_TMP_DIR=/opt/vieneu-api/upload_tmp
```

Bảo vệ file:

```bash
sudo chown root:root /etc/vieneu-api.env
sudo chmod 600 /etc/vieneu-api.env
```

---

# 17. Cấu hình thư mục tạm cho Gradio

Tạo:

```bash
sudo mkdir -p /opt/VieNeu-TTS/tmp/gradio
```

```bash
sudo chown -R vieneu:vieneu \
  /opt/VieNeu-TTS/tmp
```

Tạo:

```text
/etc/systemd/system/vieneu.service.d/temp.conf
```

Nội dung:

```ini
[Service]
Environment=TMPDIR=/opt/VieNeu-TTS/tmp
Environment=GRADIO_TEMP_DIR=/opt/VieNeu-TTS/tmp/gradio
```

Việc này tránh lỗi:

```text
PermissionError: Permission denied: /tmp/gradio/...
```

---

# 18. Cài systemd service

Copy:

```bash
sudo cp systemd/vieneu.service \
  /etc/systemd/system/vieneu.service
```

```bash
sudo cp systemd/vieneu-api.service \
  /etc/systemd/system/vieneu-api.service
```

Tạo drop-in:

```bash
sudo mkdir -p \
  /etc/systemd/system/vieneu.service.d
```

```bash
sudo cp systemd/temp.conf \
  /etc/systemd/system/vieneu.service.d/temp.conf
```

Reload:

```bash
sudo systemctl daemon-reload
```

---

# 19. Bật tự khởi động

```bash
sudo systemctl enable vieneu.service
sudo systemctl enable vieneu-api.service
```

REST API nên phụ thuộc VieNeu:

```ini
[Unit]
Requires=vieneu.service
After=network-online.target vieneu.service
Wants=network-online.target
```

Sau khi reboot:

```text
Ubuntu
  ↓
vieneu.service
  ↓
VieNeu WebUI :7860
  ↓
vieneu-api.service
  ↓
REST API :8000
  ↓
Preload model
```

Không cần SSH vào server để chạy lại thủ công.

---

# 20. Khởi động dịch vụ

```bash
sudo systemctl restart vieneu
```

Chờ:

```bash
sleep 20
```

Kiểm tra:

```bash
sudo systemctl status vieneu --no-pager
```

Sau đó:

```bash
sudo systemctl restart vieneu-api
```

Chờ:

```bash
sleep 15
```

Kiểm tra:

```bash
sudo systemctl status vieneu-api --no-pager
```

---

# 21. Kiểm tra API

```bash
curl -s \
  http://127.0.0.1:8000/api/health \
  | jq
```

Kết quả đúng:

```json
{
  "status": "ok",
  "gradio_online": true,
  "model_ready": true,
  "preset_voices": 14,
  "custom_voices": 0,
  "last_error": null
}
```

---

# 22. Mở giao diện

VieNeu WebUI:

```text
http://SERVER_IP:7860
```

REST API Swagger:

```text
http://SERVER_IP:8000/docs
```

Voice Manager:

```text
http://SERVER_IP:8000/voice-manager
```

---

# 23. Lấy danh sách giọng

Trước tiên:

```bash
API_KEY="API_KEY_CUA_BAN"
```

Sau đó:

```bash
curl -s \
  -H "X-API-Key: $API_KEY" \
  http://SERVER_IP:8000/api/voices \
  | jq
```

Danh sách trả về gồm:

```text
preset
custom
```

Ví dụ:

```json
{
  "id": "Minh Đức",
  "name": "Minh Đức",
  "type": "preset"
}
```

Giọng clone:

```json
{
  "id": "anh-khoa",
  "name": "Anh Khoa",
  "type": "custom"
}
```

---

# 24. Tạo giọng bằng REST API

Ví dụ:

```bash
curl -X POST \
  http://SERVER_IP:8000/api/tts \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Xin chào, đây là bài kiểm tra VieNeu-TTS.",
    "voice": "Minh Đức",
    "filename": "test.wav"
  }' \
  --output test.wav
```

Kiểm tra:

```bash
ffprobe -hide_banner test.wav
```

Audio mặc định:

```text
WAV
48000 Hz
Mono
PCM 16-bit
```

---

# 25. Thêm giọng clone bằng giao diện

Mở:

```text
http://SERVER_IP:8000/voice-manager
```

Thực hiện:

1. Nhập API Key.
2. Chọn file WAV.
3. Nhập tên giọng.
4. Nhập hoặc để hệ thống tự tạo Voice ID.
5. Chọn giới tính.
6. Chọn vùng miền.
7. Chọn phong cách.
8. Chọn khử nhiễu nếu cần.
9. Chọn cắt khoảng lặng.
10. Bấm **Xử lý và lưu giọng**.
11. Nghe lại file Reference.
12. Tạo thử giọng.

---

# 26. File mẫu cho Voice Cloning

Khuyến nghị:

```text
Thời lượng:     3 - 8 giây
Số người nói:  1
Nhạc nền:       Không
Tiếng vọng:     Hạn chế
Độ rõ:          Cao
```

Mẫu khoảng 5 - 8 giây thường cho kết quả tốt hơn mẫu chỉ 1 - 2 giây.

Nếu file đã sạch, có thể tắt:

```text
Khử nhiễu
```

để tránh làm thay đổi âm sắc gốc.

---

# 27. Kho giọng clone

Giọng clone được lưu tại:

```text
/opt/vieneu-api/custom_voices/
```

Ví dụ:

```text
custom_voices/
└── anh-khoa/
    ├── original.wav
    ├── reference.wav
    └── voice.json
```

`voice.json` chứa metadata của giọng.

Ví dụ:

```json
{
  "id": "anh-khoa",
  "name": "Anh Khoa",
  "type": "custom",
  "gender": "Nam",
  "region": "Bắc",
  "style": "Tin tức",
  "enabled": true
}
```

Các server khác không cần giữ file WAV.

Chỉ cần gọi:

```text
GET /api/voices
```

để lấy Voice ID.

Sau đó:

```text
POST /api/tts
```

với:

```json
{
  "text": "Nội dung cần đọc",
  "voice": "anh-khoa"
}
```

---

# 28. Kiểm tra service sau reboot

```bash
systemctl is-active vieneu
systemctl is-active vieneu-api
```

Kết quả:

```text
active
active
```

Kiểm tra autostart:

```bash
systemctl is-enabled vieneu
systemctl is-enabled vieneu-api
```

Kết quả:

```text
enabled
enabled
```

---

# 29. Xem log

VieNeu:

```bash
sudo journalctl \
  -u vieneu \
  -n 100 \
  --no-pager
```

REST API:

```bash
sudo journalctl \
  -u vieneu-api \
  -n 100 \
  --no-pager
```

Theo dõi realtime:

```bash
sudo journalctl -u vieneu-api -f
```

---

# 30. Kiểm tra RAM

```bash
free -h
```

Theo dõi:

```bash
watch -n 2 \
'free -h; echo; ps -eo pid,comm,%cpu,%mem,etime --sort=-%mem | head -10'
```

Voice cloning sử dụng PyTorch nên sẽ tốn RAM hơn preset voice.

---

# 31. Swagger API

FastAPI tự tạo tài liệu Swagger tại:

```text
http://SERVER_IP:8000/docs
```

Có thể kiểm tra trực tiếp:

```text
GET /api/health
GET /api/voices
GET /api/custom-voices
POST /api/custom-voices
POST /api/tts
```

---

# 32. Bảo mật

Không commit các file sau lên GitHub:

```text
/etc/vieneu-api.env
custom_voices/
*.wav
.env
.venv/
models/
```

Không đưa API Key thật vào:

```text
README.md
app.py
.env.example
Git history
```

Nên giới hạn firewall để chỉ các server cần thiết truy cập cổng `8000`.

Ví dụ chỉ cho server `192.168.1.152`:

```bash
sudo ufw allow from 192.168.1.152 \
  to any port 8000 proto tcp
```

---

# 33. Backup giọng clone

Kho giọng quan trọng nằm ở:

```text
/opt/vieneu-api/custom_voices
```

Backup:

```bash
sudo tar -czf \
  vieneu-custom-voices-backup.tar.gz \
  /opt/vieneu-api/custom_voices
```

Khi cài server mới có thể phục hồi thư mục này để giữ toàn bộ giọng clone.

---

# 34. Cập nhật code REST API

Sau khi cập nhật:

```bash
sudo systemctl restart vieneu-api
```

Kiểm tra:

```bash
curl -s \
  http://127.0.0.1:8000/api/health \
  | jq
```

---

# 35. Khắc phục lỗi thường gặp

## API trả về 500

Xem log:

```bash
sudo journalctl \
  -u vieneu-api \
  --since "5 minutes ago" \
  --no-pager
```

---

## Không tìm thấy Torch

Lỗi:

```text
No module named 'torch'
```

Cài vào đúng environment của VieNeu:

```bash
sudo -u vieneu \
  /opt/VieNeu-TTS/.venv/bin/python \
  -m pip install \
  torch torchaudio \
  --index-url https://download.pytorch.org/whl/cpu
```

---

## Permission denied `/tmp/gradio`

Kiểm tra:

```text
/etc/systemd/system/vieneu.service.d/temp.conf
```

Phải có:

```ini
[Service]
Environment=TMPDIR=/opt/VieNeu-TTS/tmp
Environment=GRADIO_TEMP_DIR=/opt/VieNeu-TTS/tmp/gradio
```

---

## Voice cloning rất chậm

Kiểm tra:

```bash
free -h
```

Khuyến nghị tối thiểu:

```text
RAM: 8 GB
Swap: 4 GB
```

---

# 36. Tích hợp với server khác

Server khác chỉ cần:

```env
VIENEU_API_URL=http://192.168.1.154:8000
VIENEU_API_KEY=YOUR_API_KEY
```

Luồng hoạt động:

```text
Server ứng dụng
      ↓
GET /api/voices
      ↓
Người dùng chọn voice_id
      ↓
POST /api/tts
      ↓
VieNeu REST API
      ↓
VieNeu-TTS
      ↓
WAV
```

Ứng dụng phía client không cần biết VieNeu-TTS đang sử dụng Gradio hay file reference nằm ở đâu.

---

# 37. Giấy phép

REST API và Voice Manager là phần mở rộng của hệ thống triển khai.

VieNeu-TTS có repository và giấy phép riêng. Khi phân phối hoặc sử dụng thương mại, cần tuân thủ giấy phép của dự án VieNeu-TTS gốc và các model liên quan.

---

# 38. Ghi chú

Voice cloning là zero-shot cloning, không phải huấn luyện một model mới.

Chất lượng clone phụ thuộc nhiều vào:

* File reference.
* Độ dài mẫu.
* Noise.
* Microphone.
* Accent.
* Cường độ giọng.
* Nội dung cần sinh.

Chỉ sử dụng giọng của người khác khi có quyền hoặc sự đồng ý phù hợp.
