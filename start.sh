#!/bin/bash
# 智慧外匯行情系統啟動腳本
# 包含錯誤處理和自動重啟機制

APP_DIR="/Users/a000/Downloads/forex_app/forex_app"
VENV_DIR="/Users/a000/Downloads/forex_app/venv"
LOG_FILE="/tmp/forex_streamlit.log"
PID_FILE="/tmp/forex_streamlit.pid"
PORT=8501

echo "🔄 停止舊的 Streamlit 進程..."
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    kill $OLD_PID 2>/dev/null
    sleep 1
fi
pkill -f "streamlit run app.py" 2>/dev/null
sleep 1

echo "🚀 啟動 Streamlit 伺服器..."
cd "$APP_DIR"
nohup $VENV_DIR/bin/streamlit run app.py \
    --server.headless true \
    --server.port $PORT \
    --browser.gatherUsageStats false \
    > "$LOG_FILE" 2>&1 &

NEW_PID=$!
echo $NEW_PID > "$PID_FILE"

echo "⏳ 等待伺服器啟動..."
sleep 5

if curl -s http://localhost:$PORT/_stcore/health | grep -q "ok"; then
    echo "✅ 伺服器已成功啟動！"
    echo "📍 訪問地址：http://localhost:$PORT"
    open "http://localhost:$PORT"
    exit 0
else
    echo "❌ 伺服器啟動失敗，查看日誌："
    tail -20 "$LOG_FILE"
    exit 1
fi
