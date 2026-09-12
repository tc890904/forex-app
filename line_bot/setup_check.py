#!/usr/bin/env python3
"""
LINE Bot 環境設定腳本

這個腳本會：
1. 檢查必要的環境變數
2. 驗證 LINE Bot 設定
3. 提供設定指引
"""

import os
import sys
from pathlib import Path

# 專案根目錄
PROJECT_ROOT = Path(__file__).parent.parent

# 需要設定的環境變數
REQUIRED_ENV_VARS = [
    "LINE_CHANNEL_ACCESS_TOKEN",
    "LINE_CHANNEL_SECRET",
]

OPTIONAL_ENV_VARS = [
    "PORT",  # webhook 伺服器 port
]


def check_env():
    """檢查環境變數設定。"""
    print("🔍 檢查 LINE Bot 環境設定...")
    print("-" * 40)

    missing = []
    for var in REQUIRED_ENV_VARS:
        value = os.getenv(var)
        if value:
            # 顯示部分值（遮蔽中間字符）
            display = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "已設定"
            print(f"✅ {var}: {display}")
        else:
            print(f"❌ {var}: 未設定")
            missing.append(var)

    print()
    print("可選環境變數：")
    for var in OPTIONAL_ENV_VARS:
        value = os.getenv(var, "8080" if var == "PORT" else None)
        if value:
            print(f"✅ {var}: {value}")
        else:
            print(f"⚪ {var}: 使用預設值")

    return missing


def generate_sample_env():
    """產生 .env 範例檔案。"""
    env_file = PROJECT_ROOT / "line_bot" / ".env.example"
    if not env_file.exists():
        with open(env_file, "w") as f:
            f.write("# LINE Bot 環境設定\n")
            f.write("# 請複製此檔案為 .env 並填入您的設定\n\n")
            f.write("# 必填：從 LINE Developers Console 取得\n")
            f.write("LINE_CHANNEL_ACCESS_TOKEN=your_channel_access_token_here\n")
            f.write("LINE_CHANNEL_SECRET=your_channel_secret_here\n\n")
            f.write("# 選填：webhook 伺服器 port\n")
            f.write("PORT=8080\n")
        print(f"✅ 已建立範例檔案：{env_file}")
    else:
        print(f"ℹ️ 範例檔案已存在：{env_file}")


def print_setup_guide():
    """列印設定指引。"""
    print("\n" + "=" * 50)
    print("📋 LINE Bot 設定指引")
    print("=" * 50)
    print("""
1. 前往 LINE Developers Console:
   https://developers.line.biz/console/

2. 建立新的 Channel（Bot Channel）

3. 取得以下憑證：
   - Channel Access Token
   - Channel Secret

4. 設定 Webhook URL：
   - 啟用 Webhook 使用
   - 輸入您的 webhook 網址（如：https://your-domain.com/webhook）

5. 在本專案根目錄建立 .env 檔案：
   ```
   LINE_CHANNEL_ACCESS_TOKEN=your_token
   LINE_CHANNEL_SECRET=your_secret
   ```

6. 啟動 Bot 伺服器：
   ```bash
   cd line_bot
   pip install -r requirements.txt
   python server.py
   ```
""")


def main():
    """主函式。"""
    print("\n🤖 智慧外匯 LINE Bot - 設定檢查工具\n")

    missing = check_env()

    if missing:
        print(f"\n⚠️ 缺少 {len(missing)} 個必要設定")
        generate_sample_env()
        print_setup_guide()
    else:
        print("\n✅ 所有必要設定已就緒！")
        print("您可以啟動 Bot 伺服器：")
        print("  cd /Users/a000/Downloads/forex_app/line_bot")
        print("  python server.py\n")

    print("📖 更多資訊請查看 README.md")


if __name__ == "__main__":
    main()
