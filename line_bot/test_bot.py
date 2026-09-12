#!/usr/bin/env python3
"""LINE Bot 測試腳本"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from bot_core import handle_query

print("=" * 50)
print("🤖 LINE Bot 外匯查詢機器人 - 功能測試")
print("=" * 50)

test_cases = [
    ("USD", "美元代碼"),
    ("JPY", "日圓代碼"),
    ("歐元", "中文名稱"),
    ("匯率", "查看所有匯率"),
    ("說明", "查看說明"),
    ("分析 美元", "分析功能"),
]

for query, desc in test_cases:
    print(f"\n📩 測試: {desc} ('{query}')")
    print("-" * 40)
    try:
        result = handle_query(query)
        print(result[:200] + "..." if len(result) > 200 else result)
    except Exception as e:
        print(f"❌ 錯誤: {e}")

print("\n" + "=" * 50)
print("✅ 測試完成")
print("=" * 50)
