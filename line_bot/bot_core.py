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
from datetime import date, datetime, timedelta
from typing import Any, Optional

import pandas as pd
import requests

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
    build_help_flex,
    build_hint_carousel,
    build_kelly_flex,
    build_leverage_flex,
    build_market_flex,
    build_ranking_flex,
    build_rate_flex,
    build_sentiment_flex,
    build_signals_flex,
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

_CACHE: dict[str, tuple[str, list[dict]]] = {}
_WARM_DAY: Optional[str] = None
_WARM_LOCK = threading.Lock()


@dataclass
class BotReply:
    """Flex 分析卡 + 可選 K 線 PNG（由 server 掛成 Flex hero）。"""

    alt_text: str
    flex: Any
    text_fallback: str
    chart_bytes: Optional[bytes] = None
    _rate_result: Optional[dict] = field(default=None, repr=False)
    _currency_name: Optional[str] = field(default=None, repr=False)


def _today() -> str:
    return date.today().isoformat()


def _cache_get(key: str) -> Optional[list[dict]]:
    item = _CACHE.get(key)
    if not item:
        return None
    cache_day, data = item
    if cache_day != _today():
        _CACHE.pop(key, None)
        return None
    return data


def _cache_set(key: str, data: list[dict]) -> None:
    _CACHE[key] = (_today(), data)


def _fetch_exchange_data(currency_code: str, days: int = 120) -> list[dict]:
    cache_key = f"{_today()}:{currency_code}:{days}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    today = datetime.today()
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
            _cache_set(cache_key, data)
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
        _WARM_DAY = today

    def _warm() -> None:
        logger.info("開始每日預熱 %s 幣別（%s）", len(MAJOR_CURRENCIES), today)
        with ThreadPoolExecutor(max_workers=5) as ex:
            list(ex.map(lambda c: _fetch_exchange_data(c, 120), MAJOR_CURRENCIES))
        logger.info("每日預熱完成 %s", today)

    threading.Thread(target=_warm, daemon=True, name="forex-daily-warm").start()


def resolve_currency(query: str) -> Optional[str]:
    raw = query.strip()
    if not raw:
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
    if len(raw) >= 2:
        for alias, code in CURRENCY_ALIASES.items():
            if lower in alias.lower() or alias.lower() in lower:
                return code
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
    if not rate or not tech:
        return {"error": f"無法取得 {currency_code} 的資料"}

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
        "signal_detail": score_signals(records_to_df(records)),
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


def _reply_currency(code: str) -> BotReply:
    name = CURRENCY_NAMES.get(code, code)
    result = analyze_currency(code)
    if "error" in result:
        return BotReply(
            alt_text=f"{code} 暫無資料",
            flex=build_error_flex("查無資料", result["error"]),
            text_fallback=result["error"],
        )

    chart = None
    try:
        chart = generate_kline_png(
            result.get("records") or [],
            title=f"{code}/TWD 日K",
            limit=40,
        )
    except Exception:
        logger.exception("產生 K 線失敗 [%s]", code)

    alt = f"{code} {result['rate']['spot_sell']:.4f} {result['mood']}"
    return BotReply(
        alt_text=alt,
        flex=build_rate_flex(result, name, chart_url=None),
        text_fallback=_rate_text_fallback(result, name),
        chart_bytes=chart,
        _rate_result=result,
        _currency_name=name,
    )


def _reply_market() -> BotReply:
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
    )


def _reply_ranking() -> BotReply:
    results = _collect_market(MAJOR_CURRENCIES)
    rows = strength_ranking(results)
    if not rows:
        return BotReply(
            alt_text="強弱排行暫無資料",
            flex=build_error_flex("暫無資料", "無法計算漲跌排行，請稍後再試。"),
            text_fallback="強弱排行暫無資料",
        )
    lines = [f"{r['code']} {r['change_pct']:+.2f}%" for r in rows]
    return BotReply(
        alt_text="強弱排行",
        flex=build_ranking_flex(rows),
        text_fallback="\n".join(lines),
    )


def _reply_signals_compare() -> BotReply:
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
        )
    return BotReply(
        alt_text="訊號比較",
        flex=build_signals_flex(rows),
        text_fallback="\n".join(f"{x['code']} {x['mood']} ({x['total_score']:+d})" for x in rows),
    )


def _reply_atr(code: str, direction: str = "long") -> BotReply:
    name = CURRENCY_NAMES.get(code, code)
    result = analyze_currency(code)
    if "error" in result:
        return BotReply(
            alt_text="停損計算失敗",
            flex=build_error_flex("查無資料", result["error"]),
            text_fallback=result["error"],
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
        )
    stops = calc_atr_stops(entry, atr, direction=direction)
    return BotReply(
        alt_text=f"{code} ATR 停損",
        flex=build_atr_flex(code, name, stops),
        text_fallback=f"{code} 停損 {stops['stop_loss']:.4f} 停利 {stops['take_profit']:.4f}",
    )


def _reply_kelly(parts: list[str]) -> BotReply:
    # 凱利 [勝率] [盈虧比] [資金]
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
    )


def _reply_leverage(text: str) -> BotReply:
    # 槓桿 [倍數] [幣別]
    leverage = 10
    code = "USD"
    tokens = text.replace("槓桿", "").strip().split()
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
    data = calc_leverage(10000.0, leverage, atr=atr, price=price)
    return BotReply(
        alt_text=f"槓桿風險 {leverage}x",
        flex=build_leverage_flex(data),
        text_fallback=f"槓桿 {leverage}x 風險{data['risk_level']}",
    )


def _reply_correlation() -> BotReply:
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
        )
    matrix = {a: {b: float(corr.loc[a, b]) for b in corr.columns} for a in corr.index}
    return BotReply(
        alt_text="貨幣相關",
        flex=build_corr_flex(matrix, list(corr.columns)),
        text_fallback="貨幣相關矩陣已產生",
    )


def _reply_backtest(code: str) -> BotReply:
    name = CURRENCY_NAMES.get(code, code)
    records = _fetch_exchange_data(code, 400)
    summary = simple_ma_backtest(records_to_df(records))
    return BotReply(
        alt_text=f"{code} 回測",
        flex=build_backtest_flex(code, name, summary),
        text_fallback=str(summary),
    )


def _reply_sentiment() -> BotReply:
    results = _collect_market(MAJOR_CURRENCIES)
    rows = []
    for code in MAJOR_CURRENCIES:
        r = results.get(code)
        if not r or "error" in r:
            continue
        detail = r.get("signal_detail")
        if not detail:
            continue
        # map score -3..3 style from total_score roughly
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
        )
    return BotReply(
        alt_text="技術面情緒總覽",
        flex=build_sentiment_flex(rows),
        text_fallback="\n".join(f"{x['code']} {x['text']}" for x in rows),
    )


def _extract_currency_from_command(text: str, prefixes: tuple[str, ...]) -> Optional[str]:
    t = text.strip()
    lower = t.lower()
    for p in prefixes:
        if lower.startswith(p.lower()):
            rest = t[len(p) :].strip()
            # 停損空 USD
            rest = rest.replace("空", " ").replace("多", " ").strip()
            if not rest:
                return "USD"
            code = resolve_currency(rest.split()[0] if rest.split() else rest)
            return code
    return None


def handle_query(text: str) -> BotReply:
    """處理用戶輸入，回傳 BotReply。"""
    schedule_daily_warm()
    text = (text or "").strip()

    if not text:
        return BotReply(
            alt_text="請選擇要查詢的貨幣",
            flex=build_hint_carousel(),
            text_fallback="請輸入幣別或「說明」查看指令。",
        )

    if text.lower() in ["/help", "說明", "幫助", "help", "選單", "menu"]:
        return BotReply(
            alt_text="FOREX DESK 使用說明",
            flex=build_help_flex(),
            text_fallback="輸入「說明」查看全部指令。",
        )

    if text.lower() in ["/rates", "匯率", "匯率報價", "貨幣", "市場", "速覽"]:
        return _reply_market()

    if text.lower() in ["強弱", "最強", "最弱", "排行", "strongest"]:
        return _reply_ranking()

    if text.lower() in ["訊號", "信號", "signals", "比較"]:
        return _reply_signals_compare()

    if text.lower() in ["相關", "關聯", "corr", "correlation"]:
        return _reply_correlation()

    if text.lower() in ["情緒", "sentiment"]:
        return _reply_sentiment()

    if text.lower().startswith("凱利") or text.lower().startswith("kelly"):
        raw = text.split(None, 1)
        parts = raw[1].split() if len(raw) > 1 else []
        return _reply_kelly(parts)

    if text.lower().startswith("槓桿") or text.lower().startswith("leverage"):
        return _reply_leverage(text)

    # 停損 / ATR
    if text.lower().startswith("停損") or text.lower().startswith("atr"):
        direction = "short" if ("空" in text or "short" in text.lower()) else "long"
        code = _extract_currency_from_command(text, ("停損空", "停損多", "停損", "atr"))
        if code and code != "TWD":
            return _reply_atr(code, direction=direction)
        return BotReply(
            alt_text="請指定幣別",
            flex=build_error_flex("請指定幣別", "範例：停損 USD 或 停損空 JPY"),
            text_fallback="請輸入：停損 USD",
        )

    if text.lower().startswith("回測") or text.lower().startswith("backtest"):
        code = _extract_currency_from_command(text, ("回測", "backtest"))
        if code and code != "TWD":
            return _reply_backtest(code)
        return BotReply(
            alt_text="請指定幣別",
            flex=build_error_flex("請指定幣別", "範例：回測 USD"),
            text_fallback="請輸入：回測 USD",
        )

    if "strongest" in text.lower() or "最強" in text:
        return _reply_ranking()

    if text.lower().startswith("分析") or text.lower().startswith("analyze"):
        query = text[2:].strip() if text.lower().startswith("分析") else text[7:].strip()
        code = resolve_currency(query)
        if code and code != "TWD":
            return _reply_currency(code)
        return BotReply(
            alt_text="無法識別幣別",
            flex=build_error_flex("無法識別", "請改輸入代碼，例如：分析 USD"),
            text_fallback=f"無法識別幣別：{query}",
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
            )
        return _reply_currency(code)

    return BotReply(
        alt_text="無法識別指令",
        flex=build_error_flex(
            "無法識別",
            f'找不到「{text}」。輸入「說明」查看匯率、訊號、停損、回測等指令。',
        ),
        text_fallback=f"無法識別：{text}。請輸入「說明」。",
    )
