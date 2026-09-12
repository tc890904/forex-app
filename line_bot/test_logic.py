#!/usr/bin/env python3
"""邏輯回歸測試：幣別解析、ATR、清單、TG normalize"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from bot_core import (
    BotReply,
    _extract_currency_from_command,
    _watchlist_add,
    handle_query,
    resolve_currency,
)
from tg_ui import build_telegram_payload, normalize_telegram_text
from analytics import calc_kelly

failed = 0


def check(name, cond):
    global failed
    if cond:
        print(f"OK  {name}")
    else:
        failed += 1
        print(f"FAIL {name}")


# resolve_currency
check("USD exact", resolve_currency("USD") == "USD")
check("美元 exact", resolve_currency("美元") == "USD")
check("USDJPY pair → None", resolve_currency("USDJPY") is None)
check("CADJPY → None", resolve_currency("CADJPY") is None)
check("ca short → None", resolve_currency("ca") is None)
check("us short → None", resolve_currency("us") is None)
check("please USD → None", resolve_currency("please check USD rate") is None)

# ATR extract
check(
    "atr short USD",
    _extract_currency_from_command("atr short USD", ("停損空", "停損多", "停損", "atr")) == "USD",
)
check(
    "停損空 JPY",
    _extract_currency_from_command("停損空 JPY", ("停損空", "停損多", "停損", "atr")) == "JPY",
)

# Kelly non-negative display
k = calc_kelly(0.2, 1.0)
check("kelly not viable", k["viable"] is False and k["kelly_pct"] == 0)

# watchlist full
uid = "test-wl-full"
for c in ["USD", "JPY", "EUR", "GBP", "AUD", "CAD", "CHF", "CNY", "HKD", "SGD"]:
    _watchlist_add(uid, c)
wl, added = _watchlist_add(uid, "NZD")
check("watchlist full reject", added is False and len(wl) == 10)

r = handle_query("加入 NZD", user_id=uid)
check("watchlist full message", "已滿" in r.alt_text or "已滿" in r.text_fallback)

# TG normalize
check("/start", normalize_telegram_text("/start") == "開始")
check("/start@Bot", normalize_telegram_text("/start@MyBot") == "開始")

# welcome kind
w = handle_query("開始", user_id="tg:x")
check("welcome kind", w.kind == "welcome")
p = build_telegram_payload(w)
check("welcome payload", "FOREX DESK" in p["text"] and "reply_keyboard" in p)

# sentiment sorted (smoke)
s = handle_query("情緒", user_id="tg:x")
check("sentiment flex", s.flex is not None)

print("=" * 40)
if failed:
    print(f"失敗 {failed}")
    sys.exit(1)
print("邏輯測試全部通過")
