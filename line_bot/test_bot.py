#!/usr/bin/env python3
"""LINE Bot 功能測試腳本"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from bot_core import handle_query

print("=" * 50)
print("LINE Bot 外匯查詢機器人 - 功能測試")
print("=" * 50)

test_cases = [
    ("USD", "美元代碼"),
    ("JPY", "日圓代碼"),
    ("歐元", "中文名稱"),
    ("匯率", "查看所有匯率"),
    ("說明", "查看說明"),
    ("分析 美元", "分析功能"),
    ("", "空字串"),
    ("xyzabc", "未知指令"),
]

failed = 0
for query, desc in test_cases:
    print(f"\n測試: {desc} ({query!r})")
    print("-" * 40)
    try:
        text, image = handle_query(query)
        assert isinstance(text, str) and text, "回覆文字不可為空"
        preview = text if len(text) <= 180 else text[:180] + "..."
        print(preview)
        print(f"[image={'yes' if image else 'no'}, bytes={len(image) if image else 0}]")
    except Exception as e:
        failed += 1
        print(f"錯誤: {e}")

print("\n" + "=" * 50)
if failed:
    print(f"完成，失敗 {failed} 項")
    sys.exit(1)
print("全部通過")
print("=" * 50)
