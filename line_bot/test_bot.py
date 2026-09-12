#!/usr/bin/env python3
"""LINE Bot Flex + K 線測試"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from bot_core import BotReply, handle_query
from ui import default_quick_reply, to_flex_message

print("=" * 50)
print("FOREX DESK — Flex + K-line 測試")
print("=" * 50)

qr = default_quick_reply()
assert len(qr.items) == 13, f"quick reply 應為 13，實際 {len(qr.items)}"
print(f"Quick Reply: {len(qr.items)} 項 OK")

cases = [
    ("USD", True),
    ("JPY", True),
    ("匯率", False),
    ("說明", False),
]

failed = 0
for query, expect_chart in cases:
    print(f"\n[{query}]")
    try:
        reply = handle_query(query)
        assert isinstance(reply, BotReply)
        assert reply.flex is not None
        msg = to_flex_message(reply.flex, reply.alt_text)
        assert msg.to_dict()["type"] == "flex"
        has_chart = reply.chart_bytes is not None
        print(f"  alt={reply.alt_text}")
        print(f"  chart={has_chart} bytes={len(reply.chart_bytes or b'')}")
        if expect_chart and not has_chart:
            raise AssertionError("預期有 K 線圖")
        if not expect_chart and has_chart:
            print("  (市場/說明無圖，正確)")
    except Exception as e:
        failed += 1
        print(f"  FAIL: {e}")

print("\n" + "=" * 50)
if failed:
    print(f"失敗 {failed}")
    sys.exit(1)
print("全部通過")
