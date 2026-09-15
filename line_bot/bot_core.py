"""
LINE Bot — 外匯行情查詢機器人

回傳結構化 BotReply（Flex 分析卡 + 可選 K 線圖 bytes）。
資料快取以「當日」為單位，確保每天更新。
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

import pandas as pd
import requests

TAIPEI = ZoneInfo("Asia/Taipei")

from charts import generate_kline_png
from analytics import (
    calc_atr_stops,
    calc_kelly,
    calc_leverage,
    correlation_matrix,
    records_to_df,
    score_signals,
    simple_ma_backtest,
    strength_ranking,
)
from ui import (
    build_atr_flex,
    build_backtest_flex,
    build_corr_flex,
    build_error_flex,
    build_help_carousel,
    build_kelly_flex,
    build_leverage_flex,
    build_market_flex,
    build_ranking_flex,
    build_rate_detail_flex,
    build_rate_summary_flex,
    build_sentiment_flex,
    build_signals_flex,
    build_watchlist_flex,
    build_welcome_flex,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CURRENCY_ALIASES: dict[str, str] = {
    "USD": "USD",
    "JPY": "JPY",
    "EUR": "EUR",
    "GBP": "GBP",
    "AUD": "AUD",
    "CAD": "CAD",
    "CHF": "CHF",
    "CNY": "CNY",
    "HKD": "HKD",
    "SGD": "SGD",
    "NZD": "NZD",
    "SEK": "SEK",
    "ZAR": "ZAR",
    "THB": "THB",
    "PHP": "PHP",
    "IDR": "IDR",
    "KRW": "KRW",
    "VND": "VND",
    "MYR": "MYR",
    "美元": "USD",
    "日圓": "JPY",
    "歐元": "EUR",
    "英鎊": "GBP",
    "澳幣": "AUD",
    "加幣": "CAD",
    "瑞士法郎": "CHF",
    "人民幣": "CNY",
    "港幣": "HKD",
    "新加坡幣": "SGD",
    "紐幣": "NZD",
    "瑞典克朗": "SEK",
    "南非幣": "ZAR",
    "泰銖": "THB",
    "菲律賓披索": "PHP",
    "印尼盾": "IDR",
    "韓元": "KRW",
    "越南盾": "VND",
    "馬來幣": "MYR",
    "美金": "USD",
    "台幣": "TWD",
    "瑞郎": "CHF",
    "新幣": "SGD",
}

CURRENCY_NAMES = {
    "USD": "美元",
    "JPY": "日圓",
    "EUR": "歐元",
    "GBP": "英鎊",
    "AUD": "澳幣",
    "CAD": "加幣",
    "CHF": "瑞士法郎",
    "CNY": "人民幣",
    "HKD": "港幣",
    "SGD": "新加坡幣",
    "NZD": "紐幣",
    "SEK": "瑞典克朗",
    "ZAR": "南非幣",
    "THB": "泰銖",
    "PHP": "菲律賓披索",
    "IDR": "印尼盾",
    "KRW": "韓元",
    "VND": "越南盾",
    "MYR": "馬來幣",
}

MAJOR_CURRENCIES = [
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "CHF",
    "AUD",
    "CAD",
    "HKD",
    "SGD",
    "CNY",
    "NZD",
]

FINMIND_API_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_DATASET = "TaiwanExchangeRate"
API_TIMEOUT = 8

_CACHE: dict[str, tuple[str, float, list[dict]]] = {}
_CACHE_TTL_SEC = 3600.0  # 當日內最長 1 小時，避免盤中不更新
_WARM_DAY: Optional[str] = None
_WARM_LOCK = threading.Lock()
_CACHE_LOCK = threading.Lock()

# —— 通知佇列與訂閱系統（Telegram 每日報告 / 價格觸發）——————————————————
from queue import Queue

_NotiQueue = Queue
_NOTIFICATION_QUEUE: _NotiQueue = _NotiQueue()
_SUBSCRIPTIONS: dict[str, dict] = {}  # {user_id: {"daily_rates": bool, "alerts": list[AlertSpec]}}
_SUB_LOCK = threading.Lock()


@dataclass
class AlertSpec:
    code: str
    operator: str  # ">" or "<"
    threshold: float
    last_notified_ts: float = 0.0  # 防止頻繁通知（至少間隔 30 分鐘）


ALERT_MIN_INTERVAL = 1800  # 30 分鐘內不重複通知同一條件
ALERT_CHECK_INTERVAL = 120  # 每 2 分鐘檢查一次


# —— 訂閱/通知 API ——————————————————————————————————————————————


def subscribe_daily_rates(user_id: str) -> bool:
    """訂閱每日匯率報告（早上 9 點推送）。"""
    with _SUB_LOCK:
        sub = _SUBSCRIPTIONS.setdefault(user_id, {"daily_rates": False, "alerts": []})
        if sub["daily_rates"]:
            return False  # 已訂閱
        sub["daily_rates"] = True
        logger.info("用戶 %s 訂閱每日匯率報告", user_id)
        return True


def unsubscribe_daily_rates(user_id: str) -> bool:
    """取消訂閱每日匯率報告。"""
    with _SUB_LOCK:
        sub = _SUBSCRIPTIONS.get(user_id)
        if not sub or not sub.get("daily_rates"):
            return False
        sub["daily_rates"] = False
        logger.info("用戶 %s 取消訂閱每日匯率報告", user_id)
        return True


def subscribe_alert(user_id: str, code: str, operator: str, threshold: float) -> bool:
    """訂閱價格觸發通知。"""
    alert = AlertSpec(code=code, operator=operator, threshold=threshold)
    with _SUB_LOCK:
        sub = _SUBSCRIPTIONS.setdefault(user_id, {"daily_rates": False, "alerts": []})
        for existing in sub["alerts"]:
            if existing.code == code and existing.operator == operator and abs(existing.threshold - threshold) < 0.001:
                return False  # 已存在
        sub["alerts"].append(alert)
        logger.info("用戶 %s 訂閱 %s %s %.4f", user_id, code, operator, threshold)
        return True


def unsubscribe_alert(user_id: str, code: str, operator: str, threshold: float) -> bool:
    """取消訂閱價格觸發通知。"""
    with _SUB_LOCK:
        sub = _SUBSCRIPTIONS.get(user_id)
        if not sub:
            return False
        before = len(sub["alerts"])
        sub["alerts"] = [
            a for a in sub["alerts"]
            if not (a.code == code and a.operator == operator and abs(a.threshold - threshold) < 0.001)
        ]
        if len(sub["alerts"]) < before:
            logger.info("用戶 %s 取消訂閱 %s %s %.4f", user_id, code, operator, threshold)
            return True
        return False


def get_subscriptions(user_id: str) -> dict:
    """取得用戶的訂閱狀態。"""
    with _SUB_LOCK:
        sub = _SUBSCRIPTIONS.get(user_id, {"daily_rates": False, "alerts": []})
        return {
            "daily_rates": sub.get("daily_rates", False),
            "alerts": [
                {"code": a.code, "operator": a.operator, "threshold": a.threshold}
                for a in sub.get("alerts", [])
            ],
        }


def enqueue_notification(chat_id: int, message: str, reply_markup=None) -> None:
    """將通知加入佇列，由背景線程負責發送。"""
    _NOTIFICATION_QUEUE.put((chat_id, message, reply_markup))
    logger.info("通知已加入佇列 chat=%s", chat_id)


# —— 每日報告與價格監控背景線程 —————————————————————————————


def _start_notification_daemon(tg_sender) -> None:
    """啟動通知發送背景線程。"""

    def _daemon() -> None:
        logger.info("通知發送線程啟動")
        while True:
            try:
                chat_id, message, reply_markup = _NOTIFICATION_QUEUE.get(timeout=5)
                if tg_sender.enabled:
                    tg_sender.send_message(chat_id, message, reply_markup=reply_markup)
            except Exception:
                pass  # 超時或出錯都繼續

    threading.Thread(target=_daemon, daemon=True, name="tg-notification").start()


def _daily_report_loop(
    sender,
    schedule_hour: int = 9,
    schedule_minute: int = 0,
    currencies: Optional[list[str]] = None,
) -> None:
    """在指定時間（默認台北時間 9 AM）發送每日匯率報告。"""
    import time as _time

    currencies = currencies or ["USD", "JPY", "EUR", "GBP"]
    keyboard = {
        "inline_keyboard": [[{"text": "匯率速覽", "callback_data": "匯率"}]]
    }
    last_run_date: Optional[str] = None

    while True:
        try:
            now = datetime.now(TAIPEI)
            today_str = now.date().isoformat()
            target_time = now.replace(
                hour=schedule_hour, minute=schedule_minute, second=0, microsecond=0
            )
            if now >= target_time and last_run_date != today_str:
                logger.info("發送每日匯率報告 %s", today_str)
                results = {code: analyze_currency(code) for code in currencies}
                lines = [
                    "<b>FOREX DESK 每日匯率</b>",
                    f"日期 {today_str}",
                    "",
                ]
                for code in currencies:
                    r = results.get(code)
                    if r and "error" not in r:
                        name = CURRENCY_NAMES.get(code, code)
                        rate = r["rate"]["spot_sell"]
                        mood = r["mood"]
                        lines.append(f"{code} {name}: <b>{rate:.4f}</b> {mood}")
                    else:
                        lines.append(f"{code}: 暫無資料")
                lines.extend(["", "輸入「說明」查看完整功能"])
                message = "\n".join(lines)

                with _SUB_LOCK:
                    subscribers = [
                        uid for uid, sub in _SUBSCRIPTIONS.items() if sub.get("daily_rates")
                    ]
                for uid in subscribers:
                    try:
                        chat_id = uid.replace("tg:", "")
                        if chat_id and sender.enabled:
                            sender.send_message(
                                int(chat_id), message, reply_markup=keyboard
                            )
                            logger.info("每日報告已發送 chat=%s", chat_id)
                    except Exception:
                        logger.exception("發送每日報告失敗 chat=%s", uid)
                last_run_date = today_str
            _time.sleep(60)
        except Exception:
            logger.exception("每日報告線程出錯")
            _time.sleep(60)


def _price_alert_loop(
    sender,
    currencies: Optional[list[str]] = None,
    check_interval: int = ALERT_CHECK_INTERVAL,
) -> None:
    """每 N 秒檢查一次價格觸發條件。"""
    import time as _time

    currencies = currencies or ["USD", "JPY", "EUR", "GBP"]
    while True:
        try:
            results = {code: analyze_currency(code) for code in currencies}
            now = _time.time()
            with _SUB_LOCK:
                subscribers = list(_SUBSCRIPTIONS.items())

            for uid, sub in subscribers:
                for alert in sub.get("alerts", []):
                    if now - alert.last_notified_ts < ALERT_MIN_INTERVAL:
                        continue
                    rate_data = results.get(alert.code)
                    if not rate_data or "error" in rate_data:
                        continue
                    rate = rate_data["rate"]["spot_sell"]
                    triggered = (
                        (alert.operator == ">" and rate > alert.threshold)
                        or (alert.operator == "<" and rate < alert.threshold)
                    )
                    if not triggered:
                        continue
                    chat_id = uid.replace("tg:", "")
                    if chat_id and sender.enabled:
                        message = (
                            f"<b>價格觸發通知</b>\n\n"
                            f"{alert.code} 目前 <b>{rate:.4f}</b>\n"
                            f"條件：{alert.operator} {alert.threshold}"
                        )
                        sender.send_message(int(chat_id), message)
                        alert.last_notified_ts = now
                        logger.info(
                            "價格通知已發送 chat=%s %s %.4f", chat_id, alert.code, rate
                        )
            _time.sleep(check_interval)
        except Exception:
            logger.exception("價格監控線程出錯")
            _time.sleep(check_interval)


def start_push_schedulers(tg_sender, schedule_hour: int = 9, schedule_minute: int = 0) -> None:
    """以 daemon thread 啟動每日報告與價格監控（不可同步阻塞）。"""
    if not getattr(tg_sender, "enabled", False):
        logger.warning("Telegram 未啟用，略過推播排程")
        return
    _start_notification_daemon(tg_sender)
    threading.Thread(
        target=_daily_report_loop,
        kwargs={
            "sender": tg_sender,
            "schedule_hour": schedule_hour,
            "schedule_minute": schedule_minute,
        },
        daemon=True,
        name="tg-daily-report",
    ).start()
    threading.Thread(
        target=_price_alert_loop,
        kwargs={"sender": tg_sender},
        daemon=True,
        name="tg-price-alert",
    ).start()
    logger.info("Telegram 推播排程已啟動（每日 %02d:%02d + 價格監控）", schedule_hour, schedule_minute)


# 相容舊名稱（勿直接呼叫；會阻塞）
def _daily_report_scheduled(*args, **kwargs):
    raise RuntimeError("請改用 start_push_schedulers()，勿同步呼叫排程迴圈")


def _price_alert_monitor(*args, **kwargs):
    raise RuntimeError("請改用 start_push_schedulers()，勿同步呼叫排程迴圈")


@dataclass
class BotReply:
    """Flex 分析卡 + 可選 K 線；附情境 QR 資訊。"""

    alt_text: str
    flex: Any
    text_fallback: str
    chart_bytes: Optional[bytes] = None
    _rate_result: Optional[dict] = field(default=None, repr=False)
    _currency_name: Optional[str] = field(default=None, repr=False)
    card_mode: str = "summary"  # summary | detail
    qr_mode: str = "home"  # home | currency | tools | market
    last_code: Optional[str] = None
    kind: str = "generic"  # welcome | help | rate | error | generic


# 使用者狀態（記憶體；重啟後清空）
_USER_STATE: dict[str, dict] = {}
_USER_LOCK = threading.Lock()


def _set_last(user_id: Optional[str], code: str) -> None:
    if not user_id:
        return  # 無 user_id 不寫入個人狀態（避免群組共用 _anon）
    with _USER_LOCK:
        st = _USER_STATE.setdefault(user_id, {"last_code": "USD", "watchlist": []})
        st["last_code"] = code


def _get_last(user_id: Optional[str]) -> str:
    if not user_id:
        return "USD"
    with _USER_LOCK:
        st = _USER_STATE.get(user_id) or {}
        return st.get("last_code") or "USD"


def _today() -> str:
    """台灣日曆日（牌告／快取鍵）。"""
    return datetime.now(TAIPEI).date().isoformat()


def _cache_get(key: str) -> Optional[list[dict]]:
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if not item:
            return None
        cache_day, ts, data = item
        if cache_day != _today():
            _CACHE.pop(key, None)
            return None
        if datetime.now().timestamp() - ts > _CACHE_TTL_SEC:
            _CACHE.pop(key, None)
            return None
        return data


def _cache_set(key: str, data: list[dict]) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (_today(), datetime.now().timestamp(), data)


def _fetch_exchange_data(currency_code: str, days: int = 120) -> list[dict]:
    cache_key = f"{_today()}:{currency_code}:{days}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    today = datetime.now(TAIPEI)
    start = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    params = {
        "dataset": FINMIND_DATASET,
        "data_id": currency_code,
        "start_date": start,
        "end_date": end,
    }
    try:
        resp = requests.get(FINMIND_API_URL, params=params, timeout=API_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("msg") == "success":
            data = payload.get("data", []) or []
            if data:
                _cache_set(cache_key, data)
            # 空資料不寫長快取
            return data
        logger.warning("FinMind 非 success [%s]: %s", currency_code, payload.get("msg"))
    except Exception as e:
        logger.error("API 錯誤 [%s]: %s", currency_code, e)
    return []


def schedule_daily_warm() -> None:
    """背景預熱主要貨幣，確保當日資料就緒。"""
    global _WARM_DAY
    today = _today()
    with _WARM_LOCK:
        if _WARM_DAY == today:
            return
        # 先佔位避免重複啟動；失敗時清除
        _WARM_DAY = today

    def _warm() -> None:
        global _WARM_DAY
        try:
            logger.info("開始每日預熱 %s 幣別（%s）", len(MAJOR_CURRENCIES), today)
            with ThreadPoolExecutor(max_workers=5) as ex:
                list(ex.map(lambda c: _fetch_exchange_data(c, 120), MAJOR_CURRENCIES))
            logger.info("每日預熱完成 %s", today)
        except Exception:
            logger.exception("每日預熱失敗，允許稍後重試")
            with _WARM_LOCK:
                if _WARM_DAY == today:
                    _WARM_DAY = None

    threading.Thread(target=_warm, daemon=True, name="forex-daily-warm").start()


def resolve_currency(query: str) -> Optional[str]:
    """
    嚴格解析幣別：精確別名或 3 碼代碼。
    不接受子字串 contains（避免 USDJPY / ca / please USD 誤判）。
    """
    raw = (query or "").strip()
    if not raw:
        return None
    # 貨幣對 6 碼（如 USDJPY）→ 不自動拆
    if len(raw) == 6 and raw.isalpha() and raw.isascii():
        return None
    q = raw.upper()
    if q in CURRENCY_ALIASES:
        return CURRENCY_ALIASES[q]
    if raw in CURRENCY_ALIASES:
        return CURRENCY_ALIASES[raw]
    lower = raw.lower()
    for alias, code in CURRENCY_ALIASES.items():
        if lower == alias.lower():
            return code
    # 純 3 碼英文字母且在別名表
    if len(q) == 3 and q.isalpha() and q.isascii() and q in CURRENCY_ALIASES:
        return CURRENCY_ALIASES[q]
    return None


def _records_to_rate(currency_code: str, records: list[dict]) -> Optional[dict]:
    if not records:
        return None
    latest = records[-1]
    return {
        "currency": currency_code,
        "date": latest.get("date", ""),
        "cash_buy": float(latest.get("cash_buy", 0) or 0),
        "cash_sell": float(latest.get("cash_sell", 0) or 0),
        "spot_buy": float(latest.get("spot_buy", 0) or 0),
        "spot_sell": float(latest.get("spot_sell", 0) or 0),
    }


def _records_to_tech(records: list[dict]) -> Optional[dict]:
    if len(records) < 30:
        return None
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    close_col = "spot_sell" if "spot_sell" in df.columns else "cash_sell"
    if close_col not in df.columns:
        return None
    df[close_col] = pd.to_numeric(df[close_col], errors="coerce")
    df = df.dropna(subset=[close_col])
    if len(df) < 30:
        return None

    result: dict = {}
    df["MA20"] = df[close_col].rolling(window=20).mean()
    df["MA50"] = df[close_col].rolling(window=50).mean()
    last = df.iloc[-1]
    result["close"] = float(last[close_col])
    result["ma20"] = float(last["MA20"]) if pd.notna(last["MA20"]) else None
    result["ma50"] = float(last["MA50"]) if pd.notna(last["MA50"]) else None

    delta = df[close_col].diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1 / 14, min_periods=14).mean()
    loss = (-delta).where(delta < 0, 0).ewm(alpha=1 / 14, min_periods=14).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    result["rsi"] = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else None

    ema12 = df[close_col].ewm(span=12).mean()
    ema26 = df[close_col].ewm(span=26).mean()
    df["DIF"] = ema12 - ema26
    df["DEA"] = df["DIF"].ewm(span=9).mean()
    result["dif"] = float(df["DIF"].iloc[-1]) if pd.notna(df["DIF"].iloc[-1]) else None
    result["dea"] = float(df["DEA"].iloc[-1]) if pd.notna(df["DEA"].iloc[-1]) else None

    prev = df.iloc[-2][close_col] if len(df) >= 2 else None
    result["change_pct"] = ((result["close"] - prev) / prev * 100) if prev else None
    return result


def analyze_currency(currency_code: str) -> dict:
    records = _fetch_exchange_data(currency_code, days=120)
    rate = _records_to_rate(currency_code, records)
    tech = _records_to_tech(records)
    if not rate:
        return {"error": f"無法取得 {currency_code} 的資料"}

    detail = score_signals(records_to_df(records))

    # 技術指標不足時仍回傳匯率；評分改用 signal_detail 或降級
    if not tech:
        tech = {
            "close": rate["spot_sell"],
            "ma20": None,
            "ma50": None,
            "rsi": None,
            "dif": None,
            "dea": None,
            "change_pct": None,
        }
        if len(records) >= 2:
            try:
                prev = float(records[-2].get("spot_sell") or records[-2].get("cash_sell") or 0)
                cur = rate["spot_sell"]
                if prev:
                    tech["change_pct"] = (cur - prev) / prev * 100
            except (TypeError, ValueError):
                pass

    score = 0
    signals: list[str] = []
    if tech["ma20"] and tech["ma50"]:
        if tech["ma20"] > tech["ma50"]:
            score += 1
            signals.append("MA 多頭排列")
        else:
            score -= 1
            signals.append("MA 空頭排列")
    if tech["rsi"] is not None:
        if tech["rsi"] < 30:
            score += 1
            signals.append("RSI 超賣（可能反彈）")
        elif tech["rsi"] > 70:
            score -= 1
            signals.append("RSI 超買（可能回落）")
        else:
            signals.append("RSI 中性")
    if tech["dif"] is not None and tech["dea"] is not None:
        if tech["dif"] > tech["dea"]:
            score += 1
            signals.append("MACD 金叉")
        else:
            score -= 1
            signals.append("MACD 死叉")

    # 與五維評分對齊，避免同卡矛盾
    if detail:
        score = detail["total_score"]
        mood = detail["mood"]
        signals = [f"{it['name']}{it['verdict']}" for it in detail["items"]]
    else:
        if score >= 2:
            mood = "強烈看多"
        elif score >= 1:
            mood = "偏多"
        elif score <= -2:
            mood = "強烈看空"
        elif score <= -1:
            mood = "偏空"
        else:
            mood = "中性"

    return {
        "rate": rate,
        "tech": tech,
        "mood": mood,
        "signals": signals,
        "score": score,
        "records": records,
        "signal_detail": detail,
    }


def _rate_text_fallback(result: dict, name: str) -> str:
    if "error" in result:
        return result["error"]
    r = result["rate"]
    t = result["tech"]
    change = t.get("change_pct")
    change_s = f"{change:+.2f}%" if change is not None else "—"
    return (
        f"{r['currency']} {name}\n"
        f"即期賣出 {r['spot_sell']:.4f}（{change_s}）\n"
        f"{result['mood']}\n"
        f"資料日期 {r['date']}"
    )


def _collect_market(codes: list[str]) -> dict[str, dict]:
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(analyze_currency, code): code for code in codes}
        for fut in as_completed(futures):
            code = futures[fut]
            try:
                results[code] = fut.result()
            except Exception as e:
                logger.error("分析失敗 [%s]: %s", code, e)
                results[code] = {"error": str(e)}
    return results


def _watchlist_get(user_id: Optional[str]) -> list[str]:
    if not user_id:
        return []
    with _USER_LOCK:
        st = _USER_STATE.get(user_id) or {}
        return list(st.get("watchlist") or [])


def _watchlist_add(user_id: Optional[str], code: str) -> tuple[list[str], bool]:
    if not user_id:
        return [], False
    with _USER_LOCK:
        st = _USER_STATE.setdefault(user_id, {"last_code": "USD", "watchlist": []})
        wl = st.setdefault("watchlist", [])
        if code in wl:
            return list(wl), True
        if len(wl) >= 10:
            return list(wl), False
        wl.append(code)
        return list(wl), True


def _watchlist_remove(user_id: Optional[str], code: str) -> list[str]:
    if not user_id:
        return []
    with _USER_LOCK:
        st = _USER_STATE.setdefault(user_id, {"last_code": "USD", "watchlist": []})
        wl = st.setdefault("watchlist", [])
        st["watchlist"] = [c for c in wl if c != code]
        return list(st["watchlist"])


def _reply_watchlist(user_id: Optional[str]) -> BotReply:
    codes = _watchlist_get(user_id)
    return BotReply(
        alt_text="我的清單",
        flex=build_watchlist_flex(codes, CURRENCY_NAMES),
        text_fallback="清單：" + (", ".join(codes) if codes else "（空）"),
        qr_mode="home",
        last_code=_get_last(user_id),
    )


def _reply_currency(
    code: str,
    user_id: Optional[str] = None,
    detail: bool = False,
) -> BotReply:
    name = CURRENCY_NAMES.get(code, code)
    result = analyze_currency(code)
    if "error" in result:
        return BotReply(
            alt_text=f"{code} 暫無資料",
            flex=build_error_flex(
                "查無報價",
                result["error"],
                "可能是資料源暫時無回應，請稍後再試或改查其他幣別。",
            ),
            text_fallback=result["error"],
            qr_mode="home",
            last_code=_get_last(user_id),
        )

    _set_last(user_id, code)
    chart = None
    try:
        chart = generate_kline_png(
            result.get("records") or [],
            title=f"{code}/TWD 日K",
            limit=40,
        )
    except Exception:
        logger.exception("產生 K 線失敗 [%s]", code)

    builder = build_rate_detail_flex if detail else build_rate_summary_flex
    alt = f"{code} {result['rate']['spot_sell']:.4f} {result['mood']}"
    return BotReply(
        alt_text=alt,
        flex=builder(result, name, chart_url=None),
        text_fallback=_rate_text_fallback(result, name),
        chart_bytes=chart,
        _rate_result=result,
        _currency_name=name,
        card_mode="detail" if detail else "summary",
        qr_mode="currency",
        last_code=code,
        kind="rate",
    )


def _reply_market(user_id: Optional[str] = None) -> BotReply:
    results = _collect_market(MAJOR_CURRENCIES)
    lines = ["市場速覽"]
    for code in MAJOR_CURRENCIES:
        r = results.get(code)
        if r and "error" not in r:
            lines.append(f"{code} {r['rate']['spot_sell']:.4f}")
    return BotReply(
        alt_text="市場速覽 · 主要貨幣匯率",
        flex=build_market_flex(results, MAJOR_CURRENCIES),
        text_fallback="\n".join(lines),
        qr_mode="market",
        last_code=_get_last(user_id),
    )


def _reply_ranking(user_id: Optional[str] = None) -> BotReply:
    results = _collect_market(MAJOR_CURRENCIES)
    rows = strength_ranking(results)
    if not rows:
        return BotReply(
            alt_text="強弱排行暫無資料",
            flex=build_error_flex("暫無資料", "無法計算漲跌排行，請稍後再試。"),
            text_fallback="強弱排行暫無資料",
            qr_mode="market",
            last_code=_get_last(user_id),
        )
    lines = [f"{r['code']} {r['change_pct']:+.2f}%" for r in rows]
    return BotReply(
        alt_text="強弱排行",
        flex=build_ranking_flex(rows),
        text_fallback="\n".join(lines),
        qr_mode="market",
        last_code=_get_last(user_id),
    )


def _reply_signals_compare(user_id: Optional[str] = None) -> BotReply:
    results = _collect_market(MAJOR_CURRENCIES)
    rows = []
    for code in MAJOR_CURRENCIES:
        r = results.get(code)
        if not r or "error" in r:
            continue
        detail = r.get("signal_detail") or score_signals(records_to_df(r.get("records") or []))
        if not detail:
            continue
        rows.append(
            {
                "code": code,
                "name": CURRENCY_NAMES.get(code, ""),
                "total_score": detail["total_score"],
                "mood": detail["mood"],
            }
        )
    rows.sort(key=lambda x: x["total_score"], reverse=True)
    if not rows:
        return BotReply(
            alt_text="訊號暫無資料",
            flex=build_error_flex("暫無資料", "無法計算訊號比較。"),
            text_fallback="訊號暫無資料",
            qr_mode="market",
            last_code=_get_last(user_id),
        )
    return BotReply(
        alt_text="訊號比較",
        flex=build_signals_flex(rows),
        text_fallback="\n".join(f"{x['code']} {x['mood']} ({x['total_score']:+d})" for x in rows),
        qr_mode="market",
        last_code=_get_last(user_id),
    )


def _reply_atr(
    code: str,
    direction: str = "long",
    user_id: Optional[str] = None,
) -> BotReply:
    name = CURRENCY_NAMES.get(code, code)
    _set_last(user_id, code)
    result = analyze_currency(code)
    if "error" in result:
        return BotReply(
            alt_text="停損計算失敗",
            flex=build_error_flex("查無資料", result["error"]),
            text_fallback=result["error"],
            qr_mode="tools",
            last_code=code,
        )
    detail = result.get("signal_detail") or {}
    atr = detail.get("atr")
    entry = result["rate"]["spot_sell"]
    if not atr:
        df = records_to_df(result.get("records") or [])
        scored = score_signals(df)
        atr = scored.get("atr") if scored else None
    if not atr or not entry:
        return BotReply(
            alt_text="ATR 不足",
            flex=build_error_flex("ATR 不足", f"{code} 無法計算 ATR 停損。"),
            text_fallback="ATR 不足",
            qr_mode="tools",
            last_code=code,
        )
    stops = calc_atr_stops(entry, atr, direction=direction)
    return BotReply(
        alt_text=f"{code} ATR 停損",
        flex=build_atr_flex(code, name, stops),
        text_fallback=f"{code} 停損 {stops['stop_loss']:.4f} 停利 {stops['take_profit']:.4f}",
        qr_mode="tools",
        last_code=code,
    )


def _reply_kelly(parts: list[str], user_id: Optional[str] = None) -> BotReply:
    win_rate, payoff, capital = 0.55, 1.5, 10000.0
    try:
        if len(parts) >= 1:
            win_rate = float(parts[0])
            if win_rate > 1:
                win_rate /= 100.0
        if len(parts) >= 2:
            payoff = float(parts[1])
        if len(parts) >= 3:
            capital = float(parts[2])
    except ValueError:
        pass
    data = calc_kelly(win_rate, payoff, capital)
    return BotReply(
        alt_text="凱利倉位建議",
        flex=build_kelly_flex(data),
        text_fallback=f"半凱利 {data['half_kelly_pct']:.1f}% / {data['half_kelly_amount']:.0f}",
        qr_mode="tools",
        last_code=_get_last(user_id),
    )


def _reply_leverage(text: str, user_id: Optional[str] = None) -> BotReply:
    leverage = 10
    code = _get_last(user_id)
    tokens = text.replace("槓桿", "").replace("leverage", "").strip().split()
    for tok in tokens:
        if tok.isdigit():
            leverage = int(tok)
        else:
            c = resolve_currency(tok)
            if c and c != "TWD":
                code = c
    atr = None
    price = None
    result = analyze_currency(code)
    if "error" not in result:
        price = result["rate"]["spot_sell"]
        detail = result.get("signal_detail") or {}
        atr = detail.get("atr")
        _set_last(user_id, code)
    data = calc_leverage(10000.0, leverage, atr=atr, price=price)
    return BotReply(
        alt_text=f"槓桿風險 {leverage}x",
        flex=build_leverage_flex(data),
        text_fallback=f"槓桿 {leverage}x 風險{data['risk_level']}",
        qr_mode="tools",
        last_code=code,
    )


def _reply_correlation(user_id: Optional[str] = None) -> BotReply:
    codes = MAJOR_CURRENCIES[:8]
    series_map = {}
    for code in codes:
        records = _fetch_exchange_data(code, 120)
        df = records_to_df(records)
        if df.empty:
            continue
        col = "spot_sell" if df["spot_sell"].fillna(0).ne(0).sum() > 5 else "cash_sell"
        s = df.set_index("date")[col].pct_change().dropna()
        series_map[code] = s
    corr = correlation_matrix(series_map)
    if corr.empty:
        return BotReply(
            alt_text="相關不足",
            flex=build_error_flex("相關不足", "無法計算貨幣相關矩陣。"),
            text_fallback="相關不足",
            qr_mode="market",
            last_code=_get_last(user_id),
        )
    matrix = {a: {b: float(corr.loc[a, b]) for b in corr.columns} for a in corr.index}
    return BotReply(
        alt_text="貨幣相關",
        flex=build_corr_flex(matrix, list(corr.columns)),
        text_fallback="貨幣相關矩陣已產生",
        qr_mode="market",
        last_code=_get_last(user_id),
    )


def _reply_backtest(code: str, user_id: Optional[str] = None) -> BotReply:
    name = CURRENCY_NAMES.get(code, code)
    _set_last(user_id, code)
    records = _fetch_exchange_data(code, 400)
    summary = simple_ma_backtest(records_to_df(records))
    return BotReply(
        alt_text=f"{code} 回測",
        flex=build_backtest_flex(code, name, summary),
        text_fallback=str(summary),
        qr_mode="tools",
        last_code=code,
    )


def _reply_sentiment(user_id: Optional[str] = None) -> BotReply:
    results = _collect_market(MAJOR_CURRENCIES)
    rows = []
    for code in MAJOR_CURRENCIES:
        r = results.get(code)
        if not r or "error" in r:
            continue
        detail = r.get("signal_detail")
        if not detail:
            continue
        rows.append(
            {
                "code": code,
                "score": detail["total_score"],
                "text": detail["mood"],
            }
        )
    if not rows:
        return BotReply(
            alt_text="情緒暫無資料",
            flex=build_error_flex("暫無資料", "無法計算情緒總覽。"),
            text_fallback="情緒暫無資料",
            qr_mode="market",
            last_code=_get_last(user_id),
        )
    rows.sort(key=lambda x: x["score"], reverse=True)
    return BotReply(
        alt_text="技術面情緒總覽",
        flex=build_sentiment_flex(rows),
        text_fallback="\n".join(f"{x['code']} {x['text']}" for x in rows),
        qr_mode="market",
        last_code=_get_last(user_id),
    )


def _extract_currency_from_command(text: str, prefixes: tuple[str, ...]) -> Optional[str]:
    t = text.strip()
    lower = t.lower()
    skip = {"short", "long", "多", "空", "atr"}
    for p in prefixes:
        if lower.startswith(p.lower()):
            rest = t[len(p) :].strip()
            rest = rest.replace("空", " ").replace("多", " ").strip()
            if not rest:
                return None
            for tok in rest.replace(",", " ").split():
                if tok.lower() in skip or tok in skip:
                    continue
                code = resolve_currency(tok)
                if code and code != "TWD":
                    return code
            return None
    return None


_KNOWN_CMDS = (
    "說明",
    "幫助",
    "匯率",
    "貨幣",
    "市場",
    "強弱",
    "訊號",
    "相關",
    "情緒",
    "凱利",
    "槓桿",
    "停損",
    "回測",
    "詳情",
    "加入",
    "移除",
    "我的清單",
    "開始",
)


def _fuzzy_command(text: str) -> Optional[str]:
    """容錯：僅對短字、高相似度；避免「說明書」「回測中」誤傷。"""
    import difflib

    t = text.strip().lower().replace(" ", "")
    if len(t) < 2 or len(t) > 4:
        return None
    # 已是完整指令前綴則交給後續邏輯
    for c in _KNOWN_CMDS:
        if t.startswith(c.lower()) and t != c.lower():
            return None
    matches = difflib.get_close_matches(
        t, [c.lower() for c in _KNOWN_CMDS], n=1, cutoff=0.85
    )
    if not matches:
        return None
    for c in _KNOWN_CMDS:
        if c.lower() == matches[0]:
            return c
    return None


def handle_query(text: str, user_id: Optional[str] = None) -> BotReply:
    """處理用戶輸入，回傳 BotReply。"""
    schedule_daily_warm()
    text = (text or "").strip()
    # Telegram /start /help 等（webhook 會先 normalize；此處雙保險）
    if text.startswith("/"):
        cmd = text[1:].split("@", 1)[0].split(None, 1)
        name = (cmd[0] or "").lower()
        mapping = {
            "start": "開始",
            "help": "說明",
            "menu": "說明",
            "rates": "匯率",
            "subscribe": "訂閱",
            "unsubscribe": "取消訂閱",
        }
        if name in mapping:
            text = mapping[name]
    last = _get_last(user_id)

    if not text or text.lower() in ("hi", "hello", "你好", "嗨", "開始", "start", "歡迎"):
        return BotReply(
            alt_text="歡迎使用 FOREX DESK",
            flex=build_welcome_flex(),
            text_fallback="輸入幣別代碼（如 USD）或「說明」開始。",
            qr_mode="home",
            last_code=last,
            kind="welcome",
        )

    # 模糊指令容錯
    fuzzy = _fuzzy_command(text)
    if fuzzy and resolve_currency(text) is None:
        text = fuzzy

    if text.lower() in ("/help", "說明", "幫助", "help", "選單", "menu"):
        return BotReply(
            alt_text="FOREX DESK 使用說明",
            flex=build_help_carousel(),
            text_fallback="輸入「說明」查看全部指令。",
            qr_mode="home",
            last_code=last,
            kind="help",
        )

    if text in ("我的清單", "清單", "watchlist"):
        return _reply_watchlist(user_id)

    # 訂閱系統指令
    if text.lower() in ("訂閱", "訂閱每日匯率", "/subscribe"):
        if not user_id:
            return BotReply(
                alt_text="需登入 Telegram",
                flex=build_error_flex("無使用者", "需在 Telegram 私訊中使用。"),
                text_fallback="請在 Telegram 私訊中使用此功能。",
                kind="error",
            )
        if subscribe_daily_rates(user_id):
            return BotReply(
                alt_text="已訂閱每日匯率",
                flex=build_welcome_flex(),
                text_fallback=f"✅ 已訂閱每日 9:00 匯率報告\n輸入「取消訂閱」可取消",
                kind="welcome",
            )
        return BotReply(
            alt_text="已經訂閱",
            flex=build_welcome_flex(),
            text_fallback="你已經訂閱了每日匯率報告。",
            kind="welcome",
        )

    if text.lower() in ("取消訂閱", "unsubscribe", "/unsubscribe"):
        if not user_id:
            return BotReply(
                alt_text="需登入 Telegram",
                flex=build_error_flex("無使用者", "需在 Telegram 私訊中使用。"),
                text_fallback="請在 Telegram 私訊中使用此功能。",
                kind="error",
            )
        if unsubscribe_daily_rates(user_id):
            return BotReply(
                alt_text="已取消訂閱",
                flex=build_welcome_flex(),
                text_fallback="✅ 已取消每日匯率報告訂閱。",
                kind="welcome",
            )
        return BotReply(
            alt_text="尚未訂閱",
            flex=build_welcome_flex(),
            text_fallback="你尚未訂閱每日匯率報告。",
            kind="welcome",
        )

    if text.lower() in ("我的訂閱", "訂閱清單", "/subscriptions"):
        if not user_id:
            return BotReply(
                alt_text="需登入 Telegram",
                flex=build_error_flex("無使用者", "需在 Telegram 私訊中使用。"),
                text_fallback="請在 Telegram 私訊中使用此功能。",
                kind="error",
            )
        sub = get_subscriptions(user_id)
        lines = ["📋 我的訂閱"]
        lines.append(f"每日匯率報告: {'✅ 已訂閱' if sub['daily_rates'] else '❌ 未訂閱'}")
        if sub["alerts"]:
            lines.append("")
            lines.append("價格監聽：")
            for a in sub["alerts"]:
                op = "↑ 高於" if a.operator == ">" else "↓ 低於"
                lines.append(f"  • {a.code} {op} {a.threshold:.4f}")
        else:
            lines.append("價格監聽：無")
        lines.append("")
        lines.append("指令：「訂閱」/「取消訂閱」")
        lines.append("指令：「監視 USD > 32」/「取消監視 USD > 32」")
        return BotReply(
            alt_text="訂閱狀態",
            flex=build_error_flex("訂閱清單", "\n".join(lines)),
            text_fallback="\n".join(lines),
            kind="generic",
        )

    # 價格觸發訂閱
    m = re.match(r"^監視\s+(\w+)\s*([<>])\s*(\d+\.?\d*)$", text, re.IGNORECASE)
    if m:
        code = resolve_currency(m.group(1))
        operator = m.group(2).upper()
        threshold = float(m.group(3))
        if not code or code == "TWD":
            return BotReply(
                alt_text="幣別錯誤",
                flex=build_error_flex("幣別錯誤", f"無法識別 {m.group(1)}，請使用有效幣別代碼。"),
                text_fallback=f"無法識別幣別：{m.group(1)}",
                kind="error",
            )
        if operator not in (">", "<"):
            return BotReply(
                alt_text="操作符錯誤",
                flex=build_error_flex("操作符錯誤", "請使用 > 或 <，例如：監視 USD > 32"),
                text_fallback="操作符錯誤",
                kind="error",
            )
        if not user_id:
            return BotReply(
                alt_text="需登入 Telegram",
                flex=build_error_flex("無使用者", "需在 Telegram 私訊中使用此功能。"),
                text_fallback="請在 Telegram 私訊中使用此功能。",
                kind="error",
            )
        if subscribe_alert(user_id, code, operator, threshold):
            return BotReply(
                alt_text=f"已監聽 {code}",
                flex=build_welcome_flex(),
                text_fallback=f"✅ 已設置監聽：{code} {operator} {threshold:.4f}\n當價格觸發時會通知你。",
                kind="welcome",
            )
        return BotReply(
            alt_text="已存在監聽",
            flex=build_welcome_flex(),
            text_fallback=f"你已經監聽 {code} {operator} {threshold:.4f}。",
            kind="welcome",
        )

    m2 = re.match(r"^取消監視\s+(\w+)\s*([<>])\s*(\d+\.?\d*)$", text, re.IGNORECASE)
    if m2:
        code = resolve_currency(m2.group(1))
        operator = m2.group(2).upper()
        threshold = float(m2.group(3))
        if not user_id:
            return BotReply(
                alt_text="需登入 Telegram",
                flex=build_error_flex("無使用者", "需在 Telegram 私訊中使用此功能。"),
                text_fallback="請在 Telegram 私訊中使用此功能。",
                kind="error",
            )
        if unsubscribe_alert(user_id, code, operator, threshold):
            return BotReply(
                alt_text=f"已取消監聽 {code}",
                flex=build_welcome_flex(),
                text_fallback=f"✅ 已取消監聽 {code} {operator} {threshold:.4f}",
                kind="welcome",
            )
        return BotReply(
            alt_text="監聽不存在",
            flex=build_welcome_flex(),
            text_fallback=f"你沒有監聽 {code} {operator} {threshold:.4f}。",
            kind="welcome",
        )

    if text.startswith("加入") or text.lower().startswith("add "):
        rest = text[2:].strip() if text.startswith("加入") else text[4:].strip()
        code = resolve_currency(rest) if rest else last
        if not code or code == "TWD":
            return BotReply(
                alt_text="請指定幣別",
                flex=build_error_flex("請指定幣別", "範例：加入 USD"),
                text_fallback="請輸入：加入 USD",
                qr_mode="home",
                last_code=last,
                kind="error",
            )
        wl, added = _watchlist_add(user_id, code)
        if not added:
            return BotReply(
                alt_text="清單已滿",
                flex=build_error_flex(
                    "清單已滿",
                    f"最多 10 幣，無法加入 {code}。請先「移除」其他幣別。",
                    "輸入「我的清單」查看。",
                ),
                text_fallback=f"清單已滿，無法加入 {code}",
                qr_mode="home",
                last_code=last,
                kind="error",
            )
        _set_last(user_id, code)
        return BotReply(
            alt_text=f"已加入 {code}",
            flex=build_watchlist_flex(wl, CURRENCY_NAMES),
            text_fallback=f"已加入 {code}",
            qr_mode="home",
            last_code=code,
        )

    if text.startswith("移除") or text.lower().startswith("remove "):
        rest = text[2:].strip() if text.startswith("移除") else text[7:].strip()
        code = resolve_currency(rest) if rest else last
        if not code:
            return BotReply(
                alt_text="請指定幣別",
                flex=build_error_flex("請指定幣別", "範例：移除 USD"),
                text_fallback="請輸入：移除 USD",
                qr_mode="home",
                last_code=last,
            )
        wl = _watchlist_remove(user_id, code)
        return BotReply(
            alt_text=f"已移除 {code}",
            flex=build_watchlist_flex(wl, CURRENCY_NAMES),
            text_fallback=f"已移除 {code}",
            qr_mode="home",
            last_code=last,
        )

    if text.startswith("詳情") or text.lower().startswith("detail"):
        rest = text[2:].strip() if text.startswith("詳情") else text[6:].strip()
        code = resolve_currency(rest) if rest else last
        if code and code != "TWD":
            return _reply_currency(code, user_id=user_id, detail=True)
        return BotReply(
            alt_text="請先查詢幣別",
            flex=build_error_flex("請指定幣別", "先輸入 USD，再按「詳情」。"),
            text_fallback="請輸入：詳情 USD",
            qr_mode="home",
            last_code=last,
        )

    if text.lower() in ("/rates", "匯率", "匯率報價", "貨幣", "市場", "速覽"):
        return _reply_market(user_id)

    if text.lower() in ("強弱", "最強", "最弱", "排行", "strongest"):
        return _reply_ranking(user_id)

    if text.lower() in ("訊號", "信號", "signals", "比較"):
        return _reply_signals_compare(user_id)

    if text.lower() in ("相關", "關聯", "corr", "correlation"):
        return _reply_correlation(user_id)

    if text.lower() in ("情緒", "sentiment"):
        return _reply_sentiment(user_id)

    if text.lower().startswith("凱利") or text.lower().startswith("kelly"):
        raw = text.split(None, 1)
        parts = raw[1].split() if len(raw) > 1 else []
        return _reply_kelly(parts, user_id)

    if text.lower().startswith("槓桿") or text.lower().startswith("leverage"):
        return _reply_leverage(text, user_id)

    if text.lower().startswith("停損") or text.lower().startswith("atr"):
        direction = "short" if ("空" in text or "short" in text.lower()) else "long"
        code = _extract_currency_from_command(text, ("停損空", "停損多", "停損", "atr"))
        code = code or last
        if code and code != "TWD":
            return _reply_atr(code, direction=direction, user_id=user_id)
        return BotReply(
            alt_text="請指定幣別",
            flex=build_error_flex(
                "請指定幣別",
                "範例：停損 USD 或 停損空 JPY",
                "也可先查幣別，再按 Quick Reply「停損」。",
            ),
            text_fallback="請輸入：停損 USD",
            qr_mode="tools",
            last_code=last,
        )

    if text.lower().startswith("回測") or text.lower().startswith("backtest"):
        code = _extract_currency_from_command(text, ("回測", "backtest"))
        code = code or last
        if code and code != "TWD":
            return _reply_backtest(code, user_id)
        return BotReply(
            alt_text="請指定幣別",
            flex=build_error_flex("請指定幣別", "範例：回測 USD"),
            text_fallback="請輸入：回測 USD",
            qr_mode="tools",
            last_code=last,
        )

    if "strongest" in text.lower() or text == "最強":
        return _reply_ranking(user_id)

    if text.lower().startswith("分析") or text.lower().startswith("analyze"):
        query = text[2:].strip() if text.lower().startswith("分析") else text[7:].strip()
        code = resolve_currency(query) or last
        if code and code != "TWD":
            return _reply_currency(code, user_id=user_id)
        return BotReply(
            alt_text="無法識別幣別",
            flex=build_error_flex("無法識別", "請改輸入代碼，例如：分析 USD"),
            text_fallback=f"無法識別幣別：{query}",
            qr_mode="home",
            last_code=last,
        )

    code = resolve_currency(text)
    if code:
        if code == "TWD":
            return BotReply(
                alt_text="台幣為基準貨幣",
                flex=build_error_flex(
                    "基準貨幣",
                    "台幣（TWD）為報價基準，請查詢其他幣別對 TWD 的匯率。",
                ),
                text_fallback="台幣為基準貨幣，請查詢其他幣別。",
                qr_mode="home",
                last_code=last,
            )
        return _reply_currency(code, user_id=user_id)

    return BotReply(
        alt_text="無法識別指令",
        flex=build_error_flex(
            "無法識別",
            f'找不到「{text}」。',
            "試試 USD、匯率、強弱，或輸入「說明」。",
        ),
        text_fallback=f"無法識別：{text}。請輸入「說明」。",
        qr_mode="home",
        last_code=last,
    )
