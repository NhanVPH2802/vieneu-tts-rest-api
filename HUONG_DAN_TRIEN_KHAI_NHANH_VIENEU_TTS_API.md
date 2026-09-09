# HƯỚNG DẪN TRIỂN KHAI NHANH VIENEU-TTS REST API

Tài liệu này dùng để dựng lại nhanh hệ thống **VieNeu-TTS + REST API + Voice Manager** trên một Ubuntu Server mới.

Dự án được lưu ở GitHub dạng **Private**, dùng cá nhân.

---

## 1. Yêu cầu máy chủ

Khuyến nghị:

```text
Ubuntu Server 24.04 LTS
CPU: 4 vCPU trở lên
RAM: 8 GB trở lên
Disk: 40 GB trở lên
Có Internet
```

GitHub PAT cần có quyền đọc hai repository Private:

```text
NhanVPH2802/vieneu-tts-rest-api
NhanVPH2802/VieNeu-TTS
```

Không cần giữ lại IP cũ, API Key cũ hoặc Custom Voice cũ.

---

## 2. Triển khai nhanh trên server mới

### Bước 1 - Cài Git

```bash
sudo apt update
sudo apt install -y git
```

### Bước 2 - Nhập GitHub PAT

```bash
read -s -p "GitHub PAT: " GH_PAT
echo
```

PAT sẽ không hiển thị trên màn hình khi nhập.

### Bước 3 - Tạo header xác thực

```bash
AUTH=$(printf 'x-access-token:%s' "$GH_PAT" | base64 -w0)
```

### Bước 4 - Clone repository Private

```bash
cd /opt

sudo git   -c "http.extraHeader=Authorization: Basic $AUTH"   clone   https://github.com/NhanVPH2802/vieneu-tts-rest-api.git
```

### Bước 5 - Chạy bộ cài tự động

```bash
cd /opt/vieneu-tts-rest-api

sudo GH_PAT="$GH_PAT"   bash scripts/install.sh
```

Installer sẽ tự:

```text
Cài system packages
→ Clone VieNeu-TTS Private
→ Checkout đúng commit
→ Tạo Python virtual environment
→ Cài VieNeu-TTS
→ Cài PyTorch CPU cho Voice Cloning
→ Cài REST API
→ Cài Voice Manager
→ Sinh API Key mới
→ Tạo systemd service
→ Bật tự khởi động
→ Khởi động VieNeu-TTS
→ Preload model
→ Khởi động REST API
```

### Bước 6 - Xóa PAT khỏi shell

```bash
unset GH_PAT
unset AUTH
```

---

## 3. Thông tin sau khi cài

Installer sẽ hiển thị:

```text
VieNeu WebUI:
http://IP-SERVER:7860

REST API:
http://IP-SERVER:8000

Swagger:
http://IP-SERVER:8000/docs

Voice Manager:
http://IP-SERVER:8000/voice-manager

API Key:
xxxxxxxxxxxxxxxxxxxxxxxx
```

Có thể xem lại API Key bằng:

```bash
sudo grep '^VIENEU_API_KEY=' /etc/vieneu-api.env
```

Lấy API Key vào biến:

```bash
API_KEY=$(sudo sed -n   's/^VIENEU_API_KEY=//p'   /etc/vieneu-api.env)
```

---

## 4. Kiểm tra hệ thống

Kiểm tra service:

```bash
systemctl is-active vieneu
systemctl is-active vieneu-api
```

Kết quả cần là:

```text
active
active
```

Kiểm tra tự khởi động:

```bash
systemctl is-enabled vieneu
systemctl is-enabled vieneu-api
```

Kết quả:

```text
enabled
enabled
```

Kiểm tra REST API:

```bash
curl -s http://127.0.0.1:8000/api/health | jq
```

Kết quả cần có:

```json
{
  "status": "ok",
  "gradio_online": true,
  "model_ready": true
}
```

---

## 5. Giao diện sử dụng

```text
VieNeu WebUI:
http://IP-SERVER:7860

REST API:
http://IP-SERVER:8000

Swagger:
http://IP-SERVER:8000/docs

Voice Manager:
http://IP-SERVER:8000/voice-manager
```

Các giọng Preset mặc định của VieNeu-TTS sẽ có sẵn sau khi cài.

Custom Voice có thể thêm lại sau bằng Voice Manager.

---

# 6. Kết nối từ server khác

Ví dụ:

```text
VieNeu-TTS Server:
192.168.1.154

Application Server:
192.168.1.152
```

Trên server ứng dụng cấu hình:

```env
VIENEU_API_URL=http://192.168.1.154:8000
VIENEU_API_KEY=API_KEY_MOI
```

Không cần cài VieNeu-TTS trên server ứng dụng.

---

## 7. Kiểm tra kết nối từ server khác

```bash
curl -s   http://192.168.1.154:8000/api/health   | jq
```

Kết quả cần có:

```json
{
  "status": "ok",
  "gradio_online": true,
  "model_ready": true
}
```

---

## 8. Load danh sách giọng từ server khác

```bash
export VIENEU_API_KEY="API_KEY_MOI"
```

Sau đó:

```bash
curl -s   -H "X-API-Key: $VIENEU_API_KEY"   http://192.168.1.154:8000/api/voices   | jq
```

API trả về cả:

```text
Preset Voice
Custom Voice
```

Ví dụ:

```json
{
  "id": "Minh Đức",
  "name": "Minh Đức",
  "type": "preset"
}
```

Server ứng dụng chỉ cần lưu `voice_id`.

---

## 9. Tạo giọng từ server khác

```bash
curl -X POST   http://192.168.1.154:8000/api/tts   -H "X-API-Key: $VIENEU_API_KEY"   -H "Content-Type: application/json"   -d '{
    "text": "Xin chào, đây là bài kiểm tra VieNeu-TTS.",
    "voice": "Minh Đức"
  }'   --output test.wav
```

Kiểm tra:

```bash
ffprobe -hide_banner test.wav
```

Kết quả âm thanh:

```text
WAV
48000 Hz
Mono
PCM 16-bit
```

---

## 10. Ví dụ Python cho server khác

Cài:

```bash
pip install requests
```

Load danh sách giọng:

```python
import requests

API_URL = "http://192.168.1.154:8000"
API_KEY = "API_KEY_MOI"

response = requests.get(
    f"{API_URL}/api/voices",
    headers={"X-API-Key": API_KEY},
    timeout=30,
)

response.raise_for_status()

print(response.json())
```

Tạo WAV:

```python
import requests

API_URL = "http://192.168.1.154:8000"
API_KEY = "API_KEY_MOI"

response = requests.post(
    f"{API_URL}/api/tts",
    headers={
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
    },
    json={
        "text": "Xin chào, đây là nội dung cần tạo giọng.",
        "voice": "Minh Đức",
        "filename": "output.wav",
    },
    timeout=600,
)

response.raise_for_status()

with open("output.wav", "wb") as f:
    f.write(response.content)
```

---

## 11. Kết nối với Auto Video

Luồng:

```text
Auto Video
→ GET /api/voices
→ Load danh sách giọng
→ Người dùng chọn voice_id
→ POST /api/tts
→ Nhận WAV
→ Ghép vào video
```

Cấu hình:

```env
VIENEU_API_URL=http://IP-SERVER-VIENEU:8000
VIENEU_API_KEY=API_KEY_MOI
```

---

## 12. Custom Voice

Custom Voice không cần backup.

Khi dựng lại server mới, chỉ cần add lại bằng:

```text
http://IP-SERVER:8000/voice-manager
```

Khuyến nghị file mẫu:

```text
WAV
3 - 8 giây
1 người nói
Không nhạc nền
Ít noise
Giọng rõ
```

---

## 13. Xem log khi có lỗi

VieNeu-TTS:

```bash
sudo journalctl   -u vieneu   -n 100   --no-pager
```

REST API:

```bash
sudo journalctl   -u vieneu-api   -n 100   --no-pager
```

Realtime:

```bash
sudo journalctl -u vieneu-api -f
```

---

# 14. Quy trình khôi phục nhanh khi có sự cố

Chỉ cần:

```text
1. Dựng Ubuntu Server 24.04 mới
2. RAM tối thiểu 8 GB
3. Nhập GitHub PAT
4. Clone repository Private
5. Chạy scripts/install.sh
6. Lấy IP mới
7. Lấy API Key mới
8. Test /api/health
9. Cập nhật IP + API Key trên các server client
10. Add Custom Voice lại khi cần
```

Không cần giữ:

```text
IP cũ
API Key cũ
Custom Voice cũ
Python virtual environment
Model cache
Source cũ trên server hỏng
```

Toàn bộ source và bộ cài được lấy lại từ GitHub Private.
