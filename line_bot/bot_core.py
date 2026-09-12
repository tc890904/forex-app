"""
LINE Bot — 外匯行情查詢機器人

回傳結構化 BotReply（Flex UI + 可選圖卡）。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

import pandas as pd
import requests

from ui import (
    build_error_flex,
    build_help_flex,
    build_hint_carousel,
    build_market_flex,
    build_rate_flex,
    generate_rate_card_image,
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
]

FINMIND_API_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_DATASET = "TaiwanExchangeRate"
API_TIMEOUT = 8

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL_SEC = 60.0


@dataclass
class BotReply:
    """統一回覆結構：Flex 為主、文字備援、圖卡可選。"""

    alt_text: str
    flex: Any
    text_fallback: str
    image_bytes: Optional[bytes] = None


def _cache_get(key: str) -> Optional[list[dict]]:
    item = _CACHE.get(key)
    if not item:
        return None
    ts, data = item
    if datetime.now().timestamp() - ts > _CACHE_TTL_SEC:
        _CACHE.pop(key, None)
        return None
    return data


def _cache_set(key: str, data: list[dict]) -> None:
    _CACHE[key] = (datetime.now().timestamp(), data)


def _fetch_exchange_data(currency_code: str, days: int = 90) -> list[dict]:
    cache_key = f"{currency_code}:{days}"
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

    return {"rate": rate, "tech": tech, "mood": mood, "signals": signals, "score": score}


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


def _reply_currency(code: str, with_image: bool = True) -> BotReply:
    name = CURRENCY_NAMES.get(code, code)
    result = analyze_currency(code)
    if "error" in result:
        return BotReply(
            alt_text=f"{code} 暫無資料",
            flex=build_error_flex("查無資料", result["error"]),
            text_fallback=result["error"],
        )
    image = generate_rate_card_image(result, name) if with_image else None
    alt = f"{code} {result['rate']['spot_sell']:.4f} {result['mood']}"
    return BotReply(
        alt_text=alt,
        flex=build_rate_flex(result, name),
        text_fallback=_rate_text_fallback(result, name),
        image_bytes=image,
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


def handle_query(text: str) -> BotReply:
    """處理用戶輸入，回傳 BotReply。"""
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
            text_fallback="輸入幣別代碼或中文名稱查詢匯率。輸入「匯率」查看市場速覽。",
        )

    if text.lower() in ["/rates", "匯率", "匯率報價", "市場", "速覽"]:
        return _reply_market()

    if "strongest" in text.lower() or "最強" in text:
        return _reply_market()

    if text.lower().startswith("分析") or text.lower().startswith("analyze"):
        query = text[2:].strip() if text.lower().startswith("分析") else text[7:].strip()
        code = resolve_currency(query)
        if code and code != "TWD":
            return _reply_currency(code, with_image=True)
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
        return _reply_currency(code, with_image=True)

    return BotReply(
        alt_text="無法識別指令",
        flex=build_error_flex(
            "無法識別",
            f'找不到「{text}」。可點下方按鈕，或輸入 USD、美元、匯率、說明。',
        ),
        text_fallback=f"無法識別：{text}。請輸入「說明」。",
    )
