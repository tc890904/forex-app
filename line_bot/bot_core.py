"""
LINE Bot — 外匯行情查詢機器人 (優化版)

支援功能：
  - 即時匯率查詢（輸入幣別代碼或中文名）
  - 技術指標分析（RSI、MACD、MA 趨勢）
  - 圖卡生成（匯率卡片）
  - 貨幣強弱排名
  - 快速按鈕選擇
  - 快速指令（/rates, /help）
"""

from datetime import datetime, timedelta
import io
import logging
from typing import Optional

import pandas as pd
import requests
from PIL import Image, ImageDraw, ImageFont

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
}

# 貨幣圖標 emoji
CURRENCY_ICONS = {
    "USD": "💵", "JPY": "💴", "EUR": "💶", "GBP": "💷",
    "AUD": "🇦🇺", "CAD": "🇨🇦", "CHF": "🇨🇭", "CNY": "🇨🇳",
    "HKD": "🇭🇰", "SGD": "🇸🇬", "NZD": "🇳🇿", "SEK": "🇸🇪",
    "ZAR": "🇿🇦", "THB": "🇹🇭", "PHP": "🇵🇭", "IDR": "🇮🇩",
    "KRW": "🇰🇷", "VND": "🇻🇳", "MYR": "🇲🇾",
}

# 幣別中文名
CURRENCY_NAMES = {
    "USD": "美元", "JPY": "日圓", "EUR": "歐元", "GBP": "英鎊",
    "AUD": "澳幣", "CAD": "加幣", "CHF": "瑞士法郎", "CNY": "人民幣",
    "HKD": "港幣", "SGD": "新加坡幣", "NZD": "紐幣", "SEK": "瑞典克朗",
    "ZAR": "南非幣", "THB": "泰銖", "PHP": "菲律賓披索", "IDR": "印尼盾",
    "KRW": "韓元", "VND": "越南盾", "MYR": "馬來幣",
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


def generate_rate_card(currency_code: str) -> Optional[bytes]:
    """生成匯率圖卡圖片。"""
    result = analyze_currency(currency_code)
    if "error" in result:
        return None

    r = result["rate"]
    t = result["tech"]

    # 建立圖片
    width, height = 400, 280
    img = Image.new('RGB', (width, height), color='#1a1a2e')
    draw = ImageDraw.Draw(img)

    # 嘗試載入字體
    try:
        font_title = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 24)
        font_currency = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 48)
        font_body = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 18)
        font_small = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 14)
    except:
        font_title = ImageFont.load_default()
        font_currency = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # 標題
    icon = CURRENCY_ICONS.get(currency_code, "💱")
    draw.text((20, 20), f"{icon} {currency_code}/TWD", fill='white', font=font_title)
    draw.text((20, 55), f"更新日期: {r['date']}", fill='#888888', font=font_small)

    # 匯率數字
    rate_text = f"{r['spot_sell']:.4f}"
    draw.text((20, 90), rate_text, fill='white', font=font_currency)
    draw.text((20 + len(rate_text) * 14, 100), "TWD", fill='#888888', font=font_body)

    # 漲跌幅
    if t["change_pct"] is not None:
        change_text = f"{t['change_pct']:+.2f}%"
        change_color = '#10b981' if t["change_pct"] > 0 else '#ef4444'
        draw.text((20, 150), change_text, fill=change_color, font=font_body)

    # 情緒標籤
    mood_color = '#10b981' if result["score"] > 0 else ('#ef4444' if result["score"] < 0 else '#f59e0b')
    draw.text((20, 185), result["mood"], fill=mood_color, font=font_body)

    # 技術指標
    if t["rsi"]:
        rsi_color = '#ef4444' if t["rsi"] > 70 else ('#10b981' if t["rsi"] < 30 else '#f59e0b')
        draw.text((20, 220), f"RSI: {t['rsi']:.1f}", fill=rsi_color, font=font_small)

    # 轉為 bytes
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf.getvalue()


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
    lines = ["💱 主要貨幣匯率速覽\n"]
    for code in codes[:10]:
        result = analyze_currency(code)
        if "error" not in result:
            r = result["rate"]
            lines.append(f"{code}: {r['spot_sell']:.4f} {result['mood']}")
    return "\n".join(lines)


def handle_query(text: str) -> tuple[str, Optional[bytes]]:
    """處理用戶輸入，回傳回覆訊息和圖片（可選）。"""
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

⚠️ 免責聲明：以上資料僅供參考，不構成投資建議。""", None

    if text.lower() in ["/rates", "匯率", "匯率報價"]:
        major_codes = ["USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD"]
        lines = ["💱 主要貨幣匯率報價\n"]
        for code in major_codes:
            result = analyze_currency(code)
            if "error" not in result:
                r = result["rate"]
                lines.append(f"{code}: {r['spot_sell']:.4f} {result['mood']}")
        return "\n".join(lines), None

    # 分析指令
    if text.lower().startswith("分析"):
        query = text[2:].strip()
        code = resolve_currency(query)
        if code:
            result = analyze_currency(code)
            card = generate_rate_card(code)
            return format_rate_message(result), card
        return f"⚠️ 無法識別幣別：{query}\n請輸入正確的幣別代碼或中文名稱", None

    # 一般查詢
    code = resolve_currency(text)
    if code:
        result = analyze_currency(code)
        card = generate_rate_card(code)
        return format_rate_message(result), card

    # 搜尋最強勢幣別
    if "strongest" in text.lower() or "最強" in text:
        return format_multi_rates(["USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "HKD", "SGD"]), None

    return f"⚠️ 無法識別指令：{text}\n請輸入「說明」查看可用指令", None
