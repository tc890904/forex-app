#!/usr/bin/env python3
"""訂閱／推播系統測試"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

import bot_core as bc
from bot_core import (
    dispatch_daily_reports,
    format_daily_report_html,
    get_push_status,
    get_subscriptions,
    handle_query,
    subscribe_alert,
    subscribe_daily_rates,
    unsubscribe_alert,
    unsubscribe_daily_rates,
)
from tg_api import TelegramSender
from tg_ui import build_telegram_payload

failed = 0


def check(name, cond):
    global failed
    if cond:
        print(f"OK  {name}")
    else:
        failed += 1
        print(f"FAIL {name}")


# 使用暫存檔避免污染正式訂閱
tmp = Path(tempfile.mkdtemp()) / "subscriptions.json"
bc._SUB_FILE = tmp
with bc._SUB_LOCK:
    bc._SUBSCRIPTIONS.clear()

uid = "tg:999001"
chat = 999001

check("subscribe daily", subscribe_daily_rates(uid, chat_id=chat) is True)
check("chat_id stored", get_subscriptions(uid).get("chat_id") == chat)
check("persist file", tmp.exists())
check("already subscribed", subscribe_daily_rates(uid, chat_id=chat) is False)

# reload
with bc._SUB_LOCK:
    bc._SUBSCRIPTIONS.clear()
bc._load_subscriptions()
check("reload daily", get_subscriptions(uid)["daily_rates"] is True)
check("reload chat", get_subscriptions(uid)["chat_id"] == chat)

check("alert CHF", subscribe_alert(uid, "CHF", ">", 35.0, chat_id=chat) is True)
check("alert count", len(get_subscriptions(uid)["alerts"]) == 1)

# UX: subscribe reply must NOT be welcome kind content
r = handle_query("訂閱", user_id=uid, chat_id=chat)
check("subscribe kind", r.kind == "subscribe")
p = build_telegram_payload(r)
check("subscribe shows confirm", "09:00" in p["text"] or "訂閱" in p["text"])
check("not welcome override", "直接輸入幣別" not in p["text"])

r2 = handle_query("推送測試", user_id=uid, chat_id=chat)
check("push_test kind", r2.kind == "push_test")
check("push_test html", "<b>FOREX DESK 每日匯率</b>" in (r2.text_fallback or ""))
p2 = build_telegram_payload(r2)
check("push_test payload", "每日匯率" in p2["text"])

html = format_daily_report_html(["USD"])
check("daily html", "USD" in html and "<b>" in html)

# disabled sender dispatch should send 0
n = dispatch_daily_reports(TelegramSender(""))
check("dispatch no token", n == 0)

st = get_push_status()
check("push status keys", "subscribers_daily" in st and st["subscribers_daily"] >= 1)

check("unsub alert", unsubscribe_alert(uid, "CHF", ">", 35.0) is True)
check("unsub daily", unsubscribe_daily_rates(uid) is True)

print("=" * 40)
if failed:
    print(f"失敗 {failed}")
    sys.exit(1)
print("推播測試全部通過")
