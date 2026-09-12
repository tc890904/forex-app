#!/usr/bin/env python3
"""全面功能測試"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from bot_core import BotReply, handle_query
from ui import default_quick_reply, to_flex_message

print("=" * 50)
print("FOREX DESK — 全功能測試")
print("=" * 50)

assert len(default_quick_reply().items) == 13

cases = [
    "USD",
    "匯率",
    "強弱",
    "訊號",
    "停損 USD",
    "凱利",
    "槓桿 10",
    "相關",
    "回測 USD",
    "情緒",
    "說明",
]

failed = 0
for q in cases:
    try:
        r = handle_query(q)
        assert isinstance(r, BotReply) and r.flex is not None
        to_flex_message(r.flex, r.alt_text).to_dict()
        chart = "chart" if r.chart_bytes else "-"
        print(f"OK  {q:12}  alt={r.alt_text[:40]:40} {chart}")
    except Exception as e:
        failed += 1
        print(f"FAIL {q}: {e}")

print("=" * 50)
if failed:
    print(f"失敗 {failed}")
    sys.exit(1)
print("全部通過")
