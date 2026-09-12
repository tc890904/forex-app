"""
LINE Bot — 外匯行情查詢機器人

支援：即時匯率、技術指標、圖卡、貨幣速覽、快速指令。
"""

from __future__ import annotations

import io
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from PIL import Image, ImageDraw, ImageFont

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

CURRENCY_ICONS = {
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

# 簡易記憶體快取，降低同一請求內重複打 API
_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL_SEC = 60.0


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
    """從 FinMind 取得歷史匯率資料（含短快取）。"""
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
    """解析關鍵字，回傳幣別代碼。"""
    raw = query.strip()
    if not raw:
        return None

    q = raw.upper()
    if q in CURRENCY_ALIASES:
        return CURRENCY_ALIASES[q]

    # 精確中文別名（大小寫敏感比對原始字串）
    if raw in CURRENCY_ALIASES:
        return CURRENCY_ALIASES[raw]

    lower = raw.lower()
    for alias, code in CURRENCY_ALIASES.items():
        if lower == alias.lower():
            return code

    # 子字串比對（避免過短誤判）
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
    result["change_pct"] = (
        ((result["close"] - prev) / prev * 100) if prev else None
    )
    return result


def get_latest_rate(currency_code: str) -> Optional[dict]:
    """取得最新匯率。"""
    records = _fetch_exchange_data(currency_code, days=14)
    return _records_to_rate(currency_code, records)


def calc_technical_indicators(currency_code: str) -> Optional[dict]:
    """計算技術指標（MA、RSI、MACD）。"""
    records = _fetch_exchange_data(currency_code, days=120)
    return _records_to_tech(records)


def analyze_currency(currency_code: str) -> dict:
    """綜合分析單一幣別（只打一次 FinMind）。"""
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
    }


def _load_fonts() -> tuple:
    """跨平台字體載入（macOS / Linux Render / 預設）。"""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return (
                    ImageFont.truetype(path, 28),
                    ImageFont.truetype(path, 56),
                    ImageFont.truetype(path, 22),
                    ImageFont.truetype(path, 18),
                )
            except OSError:
                continue
    default = ImageFont.load_default()
    return default, default, default, default


def generate_rate_card(currency_code: str) -> Optional[bytes]:
    """生成匯率圖卡圖片。"""
    result = analyze_currency(currency_code)
    if "error" in result:
        return None

    r = result["rate"]
    t = result["tech"]

    width, height = 420, 320
    img = Image.new("RGB", (width, height), color="#1a1a2e")
    draw = ImageDraw.Draw(img)

    font_title, font_currency, font_body, font_small = _load_fonts()

    icon = CURRENCY_ICONS.get(currency_code, currency_code)
    draw.text((25, 25), f"{icon}/TWD", fill="white", font=font_title)
    draw.text((25, 65), f"Date: {r['date']}", fill="#888888", font=font_small)

    rate_text = f"{r['spot_sell']:.4f}"
    draw.text((25, 110), rate_text, fill="white", font=font_currency)
    draw.text((25 + len(rate_text) * 18, 125), "TWD", fill="#888888", font=font_body)

    if t["change_pct"] is not None:
        change_text = f"{t['change_pct']:+.2f}%"
        change_color = "#10b981" if t["change_pct"] > 0 else "#ef4444"
        draw.text((25, 190), change_text, fill=change_color, font=font_body)

    mood_color = (
        "#10b981"
        if result["score"] > 0
        else ("#ef4444" if result["score"] < 0 else "#f59e0b")
    )
    draw.text((25, 230), result["mood"], fill=mood_color, font=font_body)

    if t["rsi"] is not None:
        rsi_color = (
            "#ef4444"
            if t["rsi"] > 70
            else ("#10b981" if t["rsi"] < 30 else "#f59e0b")
        )
        draw.text((25, 270), f"RSI: {t['rsi']:.1f}", fill=rsi_color, font=font_small)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


def format_rate_message(result: dict) -> str:
    """格式化匯率訊息。"""
    if "error" in result:
        return f"⚠️ {result['error']}"

    r = result["rate"]
    t = result["tech"]

    lines = [
        f"💱 {r['currency']} 匯率報價",
        f"📅 日期：{r['date']}",
        f"💰 即期賣出：{r['spot_sell']:.4f}",
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

    lines.append("\n⚠️ 資料僅供參考，不構成投資建議。")
    return "\n".join(lines)


def format_multi_rates(codes: list[str]) -> str:
    """格式化多幣別匯率比較（並行請求）。"""
    codes = codes[:10]
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

    lines = ["💱 主要貨幣匯率速覽\n"]
    for code in codes:
        result = results.get(code) or {"error": "無資料"}
        if "error" not in result:
            r = result["rate"]
            lines.append(f"{code}: {r['spot_sell']:.4f}  {result['mood']}")
        else:
            lines.append(f"{code}: 暫無資料")
    lines.append("\n⚠️ 資料僅供參考，不構成投資建議。")
    return "\n".join(lines)


def handle_query(text: str) -> tuple[str, Optional[bytes]]:
    """處理用戶輸入，回傳 (回覆文字, 可選圖片 bytes)。"""
    text = (text or "").strip()
    if not text:
        return "請輸入幣別或「說明」查看指令。", None

    if text.lower() in ["/help", "說明", "幫助", "help"]:
        help_msg = """📋 可使用的指令：

💰 匯率查詢：
  • 幣別代碼（USD、JPY）
  • 中文名稱（美元、日圓）

📊 技術分析：
  • 「分析 美元」→ RSI / MACD / MA

📈 市場概覽：
  • 「匯率」或 /rates
  • 「最強」查看主要貨幣

❓ 「說明」顯示此訊息

⚠️ 資料僅供參考，不構成投資建議。"""
        return help_msg, None

    if text.lower() in ["/rates", "匯率", "匯率報價"]:
        return format_multi_rates(MAJOR_CURRENCIES), None

    if text.lower().startswith("分析") or text.lower().startswith("analyze"):
        query = text[2:].strip() if text.lower().startswith("分析") else text[7:].strip()
        code = resolve_currency(query)
        if code:
            # 圖卡會再呼叫 analyze；快取可避免重複打 API
            result = analyze_currency(code)
            card = generate_rate_card(code)
            return format_rate_message(result), card
        return f"⚠️ 無法識別幣別：{query}\n請輸入正確的幣別代碼或中文名稱", None

    code = resolve_currency(text)
    if code:
        if code == "TWD":
            return "台幣為基準貨幣（TWD），請查詢其他幣別對 TWD 的匯率。", None
        result = analyze_currency(code)
        card = generate_rate_card(code)
        return format_rate_message(result), card

    if "strongest" in text.lower() or "最強" in text:
        return format_multi_rates(MAJOR_CURRENCIES), None

    return f"⚠️ 無法識別指令：{text}\n請輸入「說明」查看可用指令", None
