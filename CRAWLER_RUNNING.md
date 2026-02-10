# 🚀 Auto Crawler - Running

## 📊 Current Status
Crawler đang chạy background cào **30,000 apps** với versions!

### ✅ Configuration
- **Target**: 30,000 apps
- **Versions**: 30 versions/app
- **Telegram Upload**: Auto (không cần confirm)
- **Categories**: 28 categories
- **Speed**: ~8 apps/second
- **ETA**: ~1 hour

## 📝 Commands

### Check Progress
```bash
cd /root/VesTool/bots
bash check_progress.sh
```

### Monitor Live Log
```bash
tail -f /tmp/vestool_crawler_*.log
```

### Check Process
```bash
ps aux | grep uptodown_crawler | grep -v grep
```

### Stop Crawler (if needed)
```bash
kill $(cat /tmp/vestool_crawler.pid)
```

## 📊 Check Results

### Total Apps
```bash
cd /root/VesTool
python3 -c "import json; print(f'Apps: {len(json.load(open(\"data/apps.json\")))}')"
```

### Apps with Versions
```bash
ls data/versions/*.json | wc -l
```

### Web Interface
Open: http://103.129.126.235:8005

## 🌙 Sleep Mode
✅ **Safe to close terminal and sleep!**
- Crawler chạy trong nohup
- Process ID lưu tại: `/tmp/vestool_crawler.pid`
- Log file: `/tmp/vestool_crawler_*.log`

## 🔄 When Finished
Crawler sẽ tự động:
1. ✅ Cào 30,000 apps metadata
2. ✅ Cào 30 versions cho mỗi app
3. ✅ Upload metadata lên Telegram
4. ✅ Lưu vào `data/apps.json` và `data/versions/`

Khi xong, web sẽ hiển thị đủ 30,000 apps với phiên bản cũ!
