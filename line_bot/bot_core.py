"""
LINE Bot — 外匯行情查詢機器人

支援功能：
  - 即時匯率查詢（輸入幣別代碼或中文名）
  - 技術指標分析（RSI、MACD、MA 趨勢）
  - 貨幣強弱排名
  - 快速指令（/rates, /help）
"""

from datetime import datetime, timedelta
import logging
from typing import Optional

import pandas as pd
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────
# 幣別對照表（支援中文/英文/代碼）
# ──────────────────────────────────────
CURRENCY_ALIASES: dict[str, str] = {
    # 代碼
    "USD": "USD", "JPY": "JPY", "EUR": "EUR", "GBP": "GBP",
    "AUD": "AUD", "CAD": "CAD", "CHF": "CHF", "CNY": "CNY",
    "HKD": "HKD", "SGD": "SGD", "NZD": "NZD", "SEK": "SEK",
    "ZAR": "ZAR", "THB": "THB", "PHP": "PHP", "IDR": "IDR",
    "KRW": "KRW", "VND": "VND", "MYR": "MYR",
    # 中文名稱
    "美元": "USD", "日圓": "JPY", "歐元": "EUR", "英鎊": "GBP",
    "澳幣": "AUD", "加幣": "CAD", "瑞士法郎": "CHF", "人民幣": "CNY",
    "港幣": "HKD", "新加坡幣": "SGD", "紐幣": "NZD", "瑞典克朗": "SEK",
    "南非幣": "ZAR", "泰銖": "THB", "菲律賓披索": "PHP", "印尼盾": "IDR",
    "韓元": "KRW", "越南盾": "VND", "馬來幣": "MYR",
    # 其他常見輸入
    "美金": "USD", "台幣": "TWD",
}

FINMIND_API_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_DATASET = "TaiwanExchangeRate"
API_TIMEOUT = 10


def _fetch_exchange_data(currency_code: str, days: int = 90) -> list[dict]:
    """從 FinMind 取得歷史匯率資料。"""
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
            return payload.get("data", [])
    except Exception as e:
        logger.error("API 錯誤 [%s]: %s", currency_code, e)
    return []


def resolve_currency(query: str) -> Optional[str]:
    """解析關鍵字，回傳幣別代碼。"""
    q = query.strip().upper()
    if q in CURRENCY_ALIASES:
        return CURRENCY_ALIASES[q]
    # 嘗試中文匹配
    for alias, code in CURRENCY_ALIASES.items():
        if query.lower() in alias.lower() or alias.lower() in query.lower():
            return code
    return None


def get_latest_rate(currency_code: str) -> Optional[dict]:
    """取得最新匯率。"""
    records = _fetch_exchange_data(currency_code, days=7)
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


def calc_technical_indicators(currency_code: str) -> Optional[dict]:
    """計算技術指標（MA、RSI、MACD）。"""
    records = _fetch_exchange_data(currency_code, days=120)
    if len(records) < 30:
        return None

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # 使用 spot_sell 作為收盤價
    close_col = "spot_sell" if "spot_sell" in df.columns else "cash_sell"
    if close_col not in df.columns:
        return None

    df[close_col] = pd.to_numeric(df[close_col], errors="coerce")
    df = df.dropna(subset=[close_col])

    if len(df) < 30:
        return None

    result = {}

    # MA20, MA50
    df["MA20"] = df[close_col].rolling(window=20).mean()
    df["MA50"] = df[close_col].rolling(window=50).mean()

    last = df.iloc[-1]
    result["close"] = float(last[close_col])
    result["ma20"] = float(last["MA20"]) if pd.notna(last["MA20"]) else None
    result["ma50"] = float(last["MA50"]) if pd.notna(last["MA50"]) else None

    # RSI14
    delta = df[close_col].diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/14, min_periods=14).mean()
    loss = (-delta).where(delta < 0, 0).ewm(alpha=1/14, min_periods=14).mean()
    rs = gain / loss.replace(0, float('nan'))
    rsi = 100 - (100 / (1 + rs))
    result["rsi"] = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else None

    # MACD
    ema12 = df[close_col].ewm(span=12).mean()
    ema26 = df[close_col].ewm(span=26).mean()
    df["DIF"] = ema12 - ema26
    df["DEA"] = df["DIF"].ewm(span=9).mean()
    result["dif"] = float(df["DIF"].iloc[-1]) if pd.notna(df["DIF"].iloc[-1]) else None
    result["dea"] = float(df["DEA"].iloc[-1]) if pd.notna(df["DEA"].iloc[-1]) else None

    # 漲跌幅
    prev = df.iloc[-2][close_col] if len(df) >= 2 else None
    result["change_pct"] = ((result["close"] - prev) / prev * 100) if prev else None

    return result


def analyze_currency(currency_code: str) -> dict:
    """綜合分析單一幣別。"""
    rate = get_latest_rate(currency_code)
    tech = calc_technical_indicators(currency_code)

    if not rate or not tech:
        return {"error": f"無法取得 {currency_code} 的資料"}

    # 技術面情緒
    score = 0
    signals = []

    if tech["ma20"] and tech["ma50"]:
        if tech["ma20"] > tech["ma50"]:
            score += 1
            signals.append("📈 MA 多頭排列")
        else:
            score -= 1
            signals.append("📉 MA 空頭排列")

    if tech["rsi"]:
        if tech["rsi"] < 30:
            score += 1
            signals.append("💚 RSI 超賣（可能反彈）")
        elif tech["rsi"] > 70:
            score -= 1
            signals.append("❤️ RSI 超買（可能回落）")
        else:
            signals.append("➖ RSI 中性")

    if tech["dif"] is not None and tech["dea"] is not None:
        if tech["dif"] > tech["dea"]:
            score += 1
            signals.append("📊 MACD 金叉")
        else:
            score -= 1
            signals.append("📊 MACD 死叉")

    # 情緒標籤
    if score >= 2:
        mood = "🟢 強烈看多"
    elif score >= 1:
        mood = "🟢 偏多"
    elif score <= -2:
        mood = "🔴 強烈看空"
    elif score <= -1:
        mood = "🔴 偏空"
    else:
        mood = "⚪ 中性"

    return {
        "rate": rate,
        "tech": tech,
        "mood": mood,
        "signals": signals,
        "score": score,
    }


def format_rate_message(result: dict) -> str:
    """格式化匯率訊息。"""
    if "error" in result:
        return f"⚠️ {result['error']}"

    r = result["rate"]
    t = result["tech"]
    date = r["date"]
    spot_sell = r["spot_sell"]

    lines = [
        f"💱 {r['currency']} 匯率報價",
        f"📅 日期：{date}",
        f"💰 即期賣出：{spot_sell:.4f}",
        f"💵 現金賣出：{r['cash_sell']:.4f}",
    ]

    if t["change_pct"] is not None:
        sign = "+" if t["change_pct"] > 0 else ""
        lines.append(f"📊 日漲跌幅：{sign}{t['change_pct']:.2f}%")

    lines.append(f"\n{result['mood']}")
    lines.extend(result["signals"])

    if t["rsi"] is not None:
        lines.append(f"\n📈 RSI(14)：{t['rsi']:.1f}")
    if t["ma20"] and t["ma50"]:
        lines.append(f"📊 MA20：{t['ma20']:.4f} | MA50：{t['ma50']:.4f}")
    if t["dif"] is not None and t["dea"] is not None:
        lines.append(f"📉 MACD DIF：{t['dif']:.4f} | DEA：{t['dea']:.4f}")

    return "\n".join(lines)


def format_multi_rates(codes: list[str]) -> str:
    """格式化多幣別匯率比較。"""
    lines = ["💱 多幣別匯率比較\n"]
    for code in codes[:10]:  # 最多顯示 10 個
        result = analyze_currency(code)
        if "error" not in result:
            r = result["rate"]
            lines.append(f"{code}: {r['spot_sell']:.4f} {result['mood']}")
    return "\n".join(lines)


def handle_query(text: str) -> str:
    """處理用戶輸入，回傳回覆訊息。"""
    text = text.strip()

    # 指令處理
    if text.lower() in ["/help", "說明", "幫助", "help"]:
        return """📋 可使用的指令：

💰 匯率查詢：
  • 輸入幣別代碼（如 USD、JPY）
  • 輸入中文名稱（如 美元、日圓）
  • 範例：美元、USD、日圓

📊 技術分析：
  • 輸入「分析 幣別」（如 分析 美元）
  • 將顯示 RSI、MACD、MA 趨勢

📈 市場概覽：
  • 輸入「匯率」或「/rates」查看主要貨幣
  • 輸入「strongest」查看最強勢幣別

❓ 說明：
  • 輸入「說明」或「/help」查看此訊息

⚠️ 免責聲明：以上資料僅供參考，不構成投資建議。"""

    if text.lower() in ["/rates", "匯率", "匯率報價"]:
        # 主要貨幣匯率
        major_codes = ["USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD"]
        lines = ["💱 主要貨幣匯率報價\n"]
        for code in major_codes:
            result = analyze_currency(code)
            if "error" not in result:
                r = result["rate"]
                lines.append(f"{code}: {r['spot_sell']:.4f} {result['mood']}")
        return "\n".join(lines)

    # 分析指令
    if text.lower().startswith("分析"):
        query = text[2:].strip()
        code = resolve_currency(query)
        if code:
            return format_rate_message(analyze_currency(code))
        return f"⚠️ 無法識別幣別：{query}\n請輸入正確的幣別代碼或中文名稱"

    # 一般查詢
    code = resolve_currency(text)
    if code:
        return format_rate_message(analyze_currency(code))

    # 搜尋最強勢幣別
    if "strongest" in text.lower() or "最強" in text:
        return format_multi_rates(["USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "HKD", "SGD"])

    return f"⚠️ 無法識別指令：{text}\n請輸入「說明」查看可用指令"
