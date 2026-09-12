#!/usr/bin/env python3
"""全面功能測試"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from bot_core import BotReply, handle_query
from ui import contextual_quick_reply, default_quick_reply, to_flex_message

print("=" * 50)
print("FOREX DESK — UX v2 全功能測試")
print("=" * 50)

assert len(default_quick_reply().items) == 13
assert len(contextual_quick_reply("currency", "USD").items) == 13

uid = "test-user-ux"
cases = [
    ("開始", "home"),
    ("USD", "currency"),
    ("詳情", "currency"),
    ("匯率", "market"),
    ("強弱", "market"),
    ("訊號", "market"),
    ("停損", "tools"),
    ("凱利", "tools"),
    ("槓桿 10", "tools"),
    ("相關", "market"),
    ("回測", "tools"),
    ("情緒", "market"),
    ("加入 USD", "home"),
    ("我的清單", "home"),
    ("移除 USD", "home"),
    ("說明", "home"),
]

failed = 0
for q, expect_qr in cases:
    try:
        r = handle_query(q, user_id=uid)
        assert isinstance(r, BotReply) and r.flex is not None
        to_flex_message(
            r.flex,
            r.alt_text,
            quick_reply=contextual_quick_reply(r.qr_mode, r.last_code),
        ).to_dict()
        assert r.qr_mode == expect_qr, f"qr_mode {r.qr_mode} != {expect_qr}"
        chart = "chart" if r.chart_bytes else "-"
        print(f"OK  {q:12}  qr={r.qr_mode:8} alt={r.alt_text[:36]:36} {chart}")
    except Exception as e:
        failed += 1
        print(f"FAIL {q}: {e}")

# 記住幣別
r1 = handle_query("JPY", user_id=uid)
assert r1.last_code == "JPY"
r2 = handle_query("詳情", user_id=uid)
assert r2.last_code == "JPY" and r2.card_mode == "detail"
print("OK  remember last_code + detail")

print("=" * 50)
if failed:
    print(f"失敗 {failed}")
    sys.exit(1)
print("全部通過")
