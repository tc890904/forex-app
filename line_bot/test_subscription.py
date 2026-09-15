#!/usr/bin/env python3
"""訂閱系統單元測試"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from bot_core import (
    _SUBSCRIPTIONS,
    _SUB_LOCK,
    subscribe_daily_rates,
    unsubscribe_daily_rates,
    subscribe_alert,
    unsubscribe_alert,
    get_subscriptions,
    handle_query,
)

failed = 0

def check(name, cond):
    global failed
    if cond:
        print(f"OK  {name}")
    else:
        failed += 1
        print(f"FAIL {name}")

uid = "tg:test_sub"

# 清空狀態
with _SUB_LOCK:
    _SUBSCRIPTIONS.pop(uid, None)

# 訂閱測試
check("subscribe daily rates", subscribe_daily_rates(uid) == True)
check("already subscribed", subscribe_daily_rates(uid) == False)
sub = get_subscriptions(uid)
check("has daily rates", sub["daily_rates"] == True)
check("no alerts yet", len(sub["alerts"]) == 0)

# 取消訂閱
check("unsubscribe daily", unsubscribe_daily_rates(uid) == True)
check("not subscribed anymore", unsubscribe_daily_rates(uid) == False)
check("daily rates removed", get_subscriptions(uid)["daily_rates"] == False)

# 價格監視測試
check("subscribe alert USD>32", subscribe_alert(uid, "USD", ">", 32.0) == True)
check("duplicate alert rejected", subscribe_alert(uid, "USD", ">", 32.0) == False)
sub = get_subscriptions(uid)
check("alert added", len(sub["alerts"]) == 1)
check("alert correct", sub["alerts"][0] == {"code": "USD", "operator": ">", "threshold": 32.0})

# 取消價格監視
check("unsubscribe alert", unsubscribe_alert(uid, "USD", ">", 32.0) == True)
check("alert removed", len(get_subscriptions(uid)["alerts"]) == 0)
check("not existing alert", unsubscribe_alert(uid, "USD", ">", 32.0) == False)

# handle_query 測試
r = handle_query("訂閱", user_id=uid)
check("subscribe command returns reply", r is not None and ("已訂閱" in r.alt_text or "已經訂閱" in r.alt_text))

r2 = handle_query("監視 EUR > 0.9", user_id=uid)
check("monitor command returns reply", r2 is not None and "EUR" in r2.alt_text)

print("=" * 40)
if failed:
    print(f"失敗 {failed}")
    sys.exit(1)
print("訂閱測試全部通過")
