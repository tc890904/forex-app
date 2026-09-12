#!/usr/bin/env python3
"""LINE Bot 環境設定檢查。"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BOT_DIR = Path(__file__).resolve().parent
load_dotenv(BOT_DIR / ".env")
load_dotenv()

REQUIRED_ENV_VARS = [
    "LINE_CHANNEL_ACCESS_TOKEN",
    "LINE_CHANNEL_SECRET",
]


def main() -> int:
    print("檢查 LINE Bot 環境設定...")
    missing = []
    for var in REQUIRED_ENV_VARS:
        value = os.getenv(var)
        if value:
            display = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "(已設定)"
            print(f"  OK  {var}: {display}")
        else:
            print(f"  MISSING  {var}")
            missing.append(var)

    print(f"  PORT: {os.getenv('PORT', '8080')}")
    print(f"  SERVER_BASE_URL: {os.getenv('SERVER_BASE_URL') or os.getenv('RENDER_EXTERNAL_URL') or '(未設，將用 Render 自動變數或 localhost)'}")

    if missing:
        print("\n請複製 .env.example 為 .env 並填入 LINE Console 憑證。")
        print("Render 部署請在 Dashboard Environment 設定，勿提交 .env。")
        return 1

    print("\n環境變數就緒。啟動：")
    print("  cd line_bot && python server.py")
    print("或（repo root）：")
    print("  gunicorn line_bot.server:app --bind 0.0.0.0:$PORT --timeout 120")
    return 0


if __name__ == "__main__":
    sys.exit(main())
