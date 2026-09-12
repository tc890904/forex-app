#!/usr/bin/env python3
"""Telegram UI / normalize 單元測試（不需 Token）"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from bot_core import BotReply, handle_query
from tg_ui import (
    build_telegram_payload,
    format_from_reply,
    normalize_telegram_text,
)

assert normalize_telegram_text("/start") == "開始"
assert normalize_telegram_text("/start@MyBot") == "開始"
assert normalize_telegram_text("/help") == "說明"
assert normalize_telegram_text("USD") == "USD"

r = handle_query("開始", user_id="tg:test")
p = build_telegram_payload(r)
assert "FOREX DESK" in p["text"]
assert p["parse_mode"] == "HTML"
assert "reply_keyboard" in p or "reply_markup" in p
print("OK welcome payload")

r2 = handle_query("USD", user_id="tg:test")
p2 = build_telegram_payload(r2)
assert "USD" in p2["text"]
assert p2.get("photo_bytes")  # 應有 K 線
assert p2["reply_markup"]["inline_keyboard"]
print("OK USD rate + chart + inline")

# HTML 不可破壞
assert "<" in format_from_reply(r2)  # 有 HTML tag
print("全部通過")
