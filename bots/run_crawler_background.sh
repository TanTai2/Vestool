#!/bin/bash
##############################################
# Auto Crawler - Chạy background 30k apps
# Cào apps + versions + auto upload Telegram
##############################################

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOG_FILE="/tmp/vestool_crawler_$(date +%Y%m%d_%H%M%S).log"

echo "=========================================="
echo "🚀 VesTool Auto Crawler"
echo "=========================================="
echo "📊 Target: 30,000 apps"
echo "📚 Versions: Enabled (30/app)"
echo "📤 Telegram: Auto-upload"
echo "📝 Log: $LOG_FILE"
echo "=========================================="
echo ""
echo "Starting crawler in background..."

cd "$SCRIPT_DIR"
nohup python3 uptodown_crawler.py > "$LOG_FILE" 2>&1 &
PID=$!

echo "✅ Crawler started!"
echo "   PID: $PID"
echo "   Log: $LOG_FILE"
echo ""
echo "📊 Monitor progress:"
echo "   tail -f $LOG_FILE"
echo ""
echo "⏹️  Stop crawler:"
echo "   kill $PID"
echo ""
echo "🌙 Safe to close terminal and sleep!"
echo "=========================================="

# Save PID for later
echo $PID > /tmp/vestool_crawler.pid
