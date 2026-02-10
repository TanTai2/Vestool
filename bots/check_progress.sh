#!/bin/bash
##############################################
# Check Crawler Progress
##############################################

if [ -f /tmp/vestool_crawler.pid ]; then
    PID=$(cat /tmp/vestool_crawler.pid)
    
    if ps -p $PID > /dev/null 2>&1; then
        echo "✅ Crawler đang chạy (PID: $PID)"
        echo ""
        
        # Count apps
        if [ -f /root/VesTool/data/apps.json ]; then
            APPS=$(python3 -c "import json; print(len(json.load(open('/root/VesTool/data/apps.json'))))" 2>/dev/null || echo "?")
            echo "📱 Apps crawled: $APPS"
        fi
        
        # Count versions
        if [ -d /root/VesTool/data/versions ]; then
            VERSIONS=$(ls /root/VesTool/data/versions/*.json 2>/dev/null | wc -l)
            echo "📚 Apps with versions: $VERSIONS"
        fi
        
        echo ""
        echo "📝 Latest log (last 15 lines):"
        echo "----------------------------------------"
        # Find latest log
        LOG=$(ls -t /tmp/vestool_crawler_*.log 2>/dev/null | head -1)
        if [ -n "$LOG" ]; then
            tail -15 "$LOG"
            echo "----------------------------------------"
            echo "📊 Full log: $LOG"
        else
            echo "No log found"
        fi
    else
        echo "❌ Crawler đã dừng (PID $PID không còn chạy)"
        echo ""
        echo "📝 Check log:"
        LOG=$(ls -t /tmp/vestool_crawler_*.log 2>/dev/null | head -1)
        if [ -n "$LOG" ]; then
            echo "   tail -50 $LOG"
        fi
    fi
else
    echo "❌ Crawler chưa chạy hoặc PID file không tồn tại"
    echo ""
    echo "🚀 Start crawler:"
    echo "   cd /root/VesTool/bots"
    echo "   bash run_crawler_background.sh"
fi
