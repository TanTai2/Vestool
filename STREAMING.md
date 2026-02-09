# 📦 VesTool Telegram APK Streaming Server

Giải pháp streaming APK từ Telegram qua VPS, **tối ưu cho VPS 1GB RAM**.

## ⚡ Tính năng

- **RAM không tràn**: Dùng kỹ thuật chunked transfer, file 2GB chỉ tốn ~1-2MB RAM
- **Tốc độ cao**: Upload 360Mbps → ~15 người tải đồng thời với vài MB/s mỗi người  
- **Direct download**: Link trực tiếp, trình duyệt tự động tải, không nhảy app
- **Hỗ trợ file lớn**: Tới 2GB (qua local Bot API server)

## 🚀 Cài đặt nhanh

### 1. Lấy Telegram API Credentials

1. Truy cập https://my.telegram.org/apps
2. Đăng nhập và tạo Application
3. Lưu lại `api_id` và `api_hash`

### 2. Tạo file .env

```bash
cp .env.example .env
nano .env
```

Điền thông tin:
```env
TG_API_ID=12345678
TG_API_HASH=abcdef1234567890abcdef
TELEGRAM_BOT_TOKEN=123456:ABC-xxx
TELEGRAM_CHANNEL_ID=-1001234567890
```

### 3. Chạy với Docker Compose

```bash
# Chạy tất cả services
docker-compose up -d

# Hoặc chỉ stream server
docker-compose up -d stream telegram-bot-api
```

### 4. Chạy trực tiếp (không Docker)

```bash
# Cài dependencies
pip install aiohttp telethon

# Export env vars
export TG_API_ID=xxx
export TG_API_HASH=xxx
export TELEGRAM_BOT_TOKEN=xxx
export TELEGRAM_CHANNEL_ID=xxx

# Chạy server
cd api
python telegram_stream.py
```

## 📡 API Endpoints

### Stream Server (Port 8088)

| Endpoint | Mô tả |
|----------|-------|
| `GET /stream/{message_id}` | Stream file theo message ID |
| `GET /stream/link?url=...` | Stream file theo Telegram link |
| `GET /health` | Health check |
| `GET /` | Status page |

### Flask API (Port 8006)

| Endpoint | Mô tả |
|----------|-------|
| `GET /api/stream/{message_id}` | Proxy stream qua Flask |
| `GET /api/stream/link?url=...` | Stream theo link |
| `GET /api/download?link=...` | Download với fallback |

## 🔧 Ví dụ sử dụng

### Stream theo Message ID
```bash
curl -O "http://vps-ip:8088/stream/123?name=spotify.apk&channel=-100123456789"
```

### Stream theo Telegram Link
```bash
curl -O "http://vps-ip:8088/stream/link?url=https://t.me/c/123456789/123&name=app.apk"
```

### Trong Frontend
```javascript
// Tạo link download trực tiếp
const streamUrl = `${API_BASE}/api/stream/${messageId}?name=${appName}.apk`;
window.location.href = streamUrl;
```

## 📊 Cấu hình cho VPS 1GB RAM

Đã tối ưu sẵn trong code:

| Config | Giá trị | Lý do |
|--------|---------|-------|
| `CHUNK_SIZE` | 1MB | Cân bằng tốc độ/RAM |
| `MAX_CONNECTIONS` | 15 | Với 360Mbps upload |

Có thể điều chỉnh qua env vars:
```env
STREAM_PORT=8088
```

## 🏗️ Kiến trúc

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   User Browser  │───▶│   VPS Stream     │───▶│ Telegram Servers │
│                 │◀───│   Server (8088)  │◀───│                   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
        │                      │
        │ Chunk by chunk       │ iter_download()
        │ (1MB/chunk)          │ (1MB/chunk)
        ▼                      ▼
   RAM: 0 bytes           RAM: ~1-2MB
```

**Kỹ thuật Streaming:**
1. Telegram server gửi chunk 1MB → Stream server
2. Stream server forward ngay chunk đó → User browser
3. Không buffer, không lưu file → RAM luôn thấp

## ⚠️ Lưu ý

1. **Bot phải là admin** của channel chứa file APK
2. **Channel ID format**: `-100xxxxxxxxxx` cho private channel
3. **Bandwidth**: Kiểm tra VPS có unmetered bandwidth không
4. **First run**: Telethon cần xác thực lần đầu - làm theo hướng dẫn terminal

## 🔍 Troubleshooting

### "Cannot get entity"
- Kiểm tra bot có quyền admin trong channel
- Kiểm tra channel ID đúng format `-100xxx`

### "Connection refused"
- Stream server chưa chạy: `docker-compose up stream`
- Kiểm tra port 8088 đã mở

### "Telethon not installed"
```bash
pip install telethon aiohttp
```

### RAM vẫn cao
- Giảm `CHUNK_SIZE` trong code (mặc định 1MB)
- Giảm `MAX_CONNECTIONS` (mặc định 15)

## 📝 License

MIT
