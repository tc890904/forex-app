#!/usr/bin/env python3
"""邏輯回歸測試：幣別解析、ATR、清單、TG normalize"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from bot_core import (
    BotReply,
    _extract_currency_from_command,
    _watchlist_add,
    convert_via_twd,
    handle_query,
    parse_convert_query,
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

# convert parse
check("100USD", parse_convert_query("100USD") == (100.0, "USD"))
check("100 USD", parse_convert_query("100 USD") == (100.0, "USD"))
check("100美元", parse_convert_query("100美元") == (100.0, "USD"))
check("USD 50", parse_convert_query("USD 50") == (50.0, "USD"))
check("換匯 100 USD", parse_convert_query("換匯 100 USD") == (100.0, "USD"))
check("1,000 JPY", parse_convert_query("1,000 JPY") == (1000.0, "JPY"))
check("10000TWD", parse_convert_query("10000TWD") == (10000.0, "TWD"))
check("bare USD not convert", parse_convert_query("USD") is None)
check("監視 not convert", parse_convert_query("監視 USD > 32") is None)
check("槓桿 not convert", parse_convert_query("槓桿 10") is None)
check("cross math", abs(convert_via_twd(100, 32.0, 0.22) - 100 * 32 / 0.22) < 1e-9)

# convert hint
c0 = handle_query("換匯", user_id="tg:fx")
check("convert hint kind", c0.kind == "convert")
p0 = build_telegram_payload(c0)
check("convert hint text", "100USD" in p0["text"] or "換匯" in p0["text"])

# TG normalize
check("/start", normalize_telegram_text("/start") == "開始")
check("/start@Bot", normalize_telegram_text("/start@MyBot") == "開始")
check("/convert 100USD", normalize_telegram_text("/convert 100USD") == "換匯 100USD")

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
