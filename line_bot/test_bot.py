#!/usr/bin/env python3
"""LINE Bot UI / 功能測試"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from bot_core import BotReply, handle_query
from ui import to_flex_message

print("=" * 50)
print("FOREX DESK — UI / 功能測試")
print("=" * 50)

cases = [
    ("USD", "美元"),
    ("匯率", "市場速覽"),
    ("說明", "說明選單"),
    ("分析 日圓", "分析"),
    ("", "空輸入輪播"),
    ("xyz", "未知指令"),
]

failed = 0
for query, desc in cases:
    print(f"\n[{desc}] {query!r}")
    print("-" * 40)
    try:
        reply = handle_query(query)
        assert isinstance(reply, BotReply)
        assert reply.flex is not None, "必須有 Flex"
        assert reply.alt_text, "必須有 alt_text"
        msg = to_flex_message(reply.flex, reply.alt_text)
        payload = msg.to_dict()
        assert payload["type"] == "flex"
        print(f"alt: {reply.alt_text}")
        print(f"flex type: {payload['contents']['type']}")
        print(f"image: {'yes' if reply.image_bytes else 'no'}")
        print(f"fallback: {reply.text_fallback[:80]}...")
    except Exception as e:
        failed += 1
        print(f"FAIL: {e}")

print("\n" + "=" * 50)
if failed:
    print(f"失敗 {failed} 項")
    sys.exit(1)
print("全部通過")
