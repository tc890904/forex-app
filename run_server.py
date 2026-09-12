#!/usr/bin/env python3
"""
Streamlit 持久化啟動腳本
"""
import subprocess
import sys
import time
import os

VENV_DIR = "/Users/a000/Downloads/forex_app/venv"
APP_DIR = "/Users/a000/Downloads/forex_app/forex_app"
LOG_FILE = "/tmp/forex_streamlit.log"
PORT = 8501

def check_health():
    """檢查 Streamlit 健康狀態"""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://localhost:{PORT}/_stcore/health", timeout=2) as resp:
            return resp.status == 200
    except:
        return False

def start_streamlit():
    """啟動 Streamlit 伺服器"""
    cmd = [
        f"{VENV_DIR}/bin/streamlit",
        "run", "app.py",
        "--server.headless", "true",
        f"--server.port", str(PORT),
        "--browser.gatherUsageStats", "false",
    ]
    
    print("🚀 啟動 Streamlit 伺服器...")
    with open(LOG_FILE, 'w') as log:
        proc = subprocess.Popen(
            cmd,
            cwd=APP_DIR,
            stdout=log,
            stderr=log,
            start_new_session=True
        )
    
    # 等待伺服器啟動
    for i in range(20):
        time.sleep(1)
        if check_health():
            print(f"✅ 伺服器已成功啟動 (PID: {proc.pid})")
            print(f"📍 訪問地址：http://localhost:{PORT}")
            return proc
    
    print("❌ 伺服器啟動超時，請檢查日誌：")
    os.system(f"tail -20 {LOG_FILE}")
    return None

if __name__ == "__main__":
    import webbrowser
    proc = start_streamlit()
    if proc:
        webbrowser.open(f"http://localhost:{PORT}")
        print("💡 伺服器運行中，如需停止請執行：kill", proc.pid)
        # 保持腳本運行，監控進程
        try:
            proc.wait()
        except KeyboardInterrupt:
            print("\n🛑 停止伺服器...")
            proc.terminate()
            sys.exit(0)
