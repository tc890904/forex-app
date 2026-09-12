"""
data.py — 共用資料層

封裝所有 FinMind API 呼叫邏輯，提供三個主要函式：
  - get_latest_rate()   : 單一幣別最新匯率
  - get_all_rates()     : 批次取得多幣別最新匯率
  - get_history_rate()  : 單一幣別歷史匯率

所有函式皆加上 Streamlit 快取（ttl=300 秒），避免短時間重複打 API。
"""

from datetime import datetime, timedelta
import logging

import pandas as pd
import requests
import streamlit as st

from config import (
    FINMIND_API_URL,
    FINMIND_DATASET,
    API_TIMEOUT,
    ALL_CURRENCY_CODES,
    CURRENCY_NAMES,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────
# 內部輔助函式
# ──────────────────────────────────────

def _fetch_from_finmind(
    data_id: str,
    start_date: str,
    end_date: str | None = None,
) -> list[dict]:
    """
    向 FinMind API 發送 GET 請求，回傳原始 JSON 中的 data 陣列。

    Parameters
    ----------
    data_id : str
        幣別代碼，例如 "USD"。
    start_date : str
        查詢起始日期，格式 "YYYY-MM-DD"。
    end_date : str | None
        查詢結束日期，格式 "YYYY-MM-DD"。若為 None 則不傳。

    Returns
    -------
    list[dict]
        FinMind 回傳的資料列表；若查無資料或發生錯誤則回傳空 list。

    Raises
    ------
    不主動 raise；所有例外皆在內部捕獲並記錄 log。
    """
    params: dict = {
        "dataset": FINMIND_DATASET,
        "data_id": data_id,
        "start_date": start_date,
    }
    if end_date:
        params["end_date"] = end_date

    try:
        resp = requests.get(FINMIND_API_URL, params=params, timeout=API_TIMEOUT)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        logger.error("API 請求超時：%s（%s）", data_id, start_date)
        st.warning(f"⚠️ 查詢 {data_id} 時連線逾時，請稍後再試。")
        return []
    except requests.exceptions.ConnectionError:
        logger.error("API 連線失敗：%s", data_id)
        st.warning(f"⚠️ 無法連線至資料來源，請檢查網路狀態。")
        return []
    except requests.exceptions.HTTPError as exc:
        logger.error("API HTTP 錯誤：%s — %s", data_id, exc)
        st.warning(f"⚠️ 資料來源回傳錯誤（HTTP {resp.status_code}），請稍後再試。")
        return []
    except requests.exceptions.RequestException as exc:
        logger.error("API 未預期錯誤：%s — %s", data_id, exc)
        st.warning(f"⚠️ 查詢 {data_id} 時發生未預期錯誤。")
        return []

    # 解析 JSON
    try:
        payload = resp.json()
    except ValueError:
        logger.error("API 回傳非 JSON 格式：%s", data_id)
        st.warning(f"⚠️ 資料來源回傳格式異常，請稍後再試。")
        return []

    # FinMind 回傳結構：{"msg": "success", "status": 200, "data": [...]}
    if payload.get("msg") != "success":
        logger.warning("API 回傳非成功狀態：%s — %s", data_id, payload.get("msg"))
        return []

    data = payload.get("data", [])
    if not data:
        logger.info("查無資料：%s（%s ~ %s）", data_id, start_date, end_date)
    return data


def _safe_float(value) -> float | None:
    """
    安全地將值轉換為 float；若值為空字串、None、0 或無法轉換則回傳 None。

    匯率不可能為 0，FinMind 對無報價的幣別會回傳 0，因此一併視為無效。

    Parameters
    ----------
    value : any
        欲轉換的原始值。

    Returns
    -------
    float | None
    """
    if value is None or value == "" or value == "-":
        return None
    try:
        result = float(value)
        # 匯率為 0 代表該欄位無報價（常見於冷門貨幣的即期匯率）
        return result if result != 0.0 else None
    except (ValueError, TypeError):
        return None


# ──────────────────────────────────────
# 公開 API 函式
# ──────────────────────────────────────

@st.cache_data(ttl=300, show_spinner="正在查詢最新匯率...")
def get_latest_rate(currency_code: str) -> dict | None:
    """
    取得單一幣別最新一筆匯率（現金買入/賣出、即期買入/賣出）。

    以今天為終點、往前推 7 天查詢，取最後一筆資料。
    之所以查 7 天而非只查當天，是因為假日可能無資料。

    Parameters
    ----------
    currency_code : str
        幣別代碼，例如 "USD"。

    Returns
    -------
    dict | None
        包含以下 key 的字典：
        - currency: 幣別代碼
        - date: 資料日期（str）
        - cash_buy: 現金買入（float | None）
        - cash_sell: 現金賣出（float | None）
        - spot_buy: 即期買入（float | None）
        - spot_sell: 即期賣出（float | None）
        若查無資料則回傳 None。
    """
    today = datetime.today()
    start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")

    records = _fetch_from_finmind(currency_code, start, end)
    if not records:
        return None

    # 取最後一筆（最新日期）
    latest = records[-1]
    return {
        "currency": currency_code,
        "date": latest.get("date", ""),
        "cash_buy": _safe_float(latest.get("cash_buy")),
        "cash_sell": _safe_float(latest.get("cash_sell")),
        "spot_buy": _safe_float(latest.get("spot_buy")),
        "spot_sell": _safe_float(latest.get("spot_sell")),
    }


@st.cache_data(ttl=300, show_spinner="正在載入所有匯率資料...")
def get_all_rates(currency_codes: list[str] | None = None) -> pd.DataFrame:
    """
    批次取得多種貨幣的最新匯率，每次查詢間隔 0.3 秒避免 rate limit。

    Parameters
    ----------
    currency_codes : list[str] | None
        欲查詢的幣別代碼清單。若為 None 則查詢全部 19 種。

    Returns
    -------
    pd.DataFrame
        欄位：幣別、中文名稱、日期、現金買入、現金賣出、即期買入、即期賣出。
        若全部查無資料則回傳空 DataFrame（含正確欄位）。
    """
    codes = currency_codes or ALL_CURRENCY_CODES
    columns = ["幣別", "中文名稱", "日期", "現金買入", "現金賣出", "即期買入", "即期賣出"]
    rows: list[dict] = []

    for i, code in enumerate(codes):
        rate = get_latest_rate(code)
        if rate:
            rows.append({
                "幣別": rate["currency"],
                "中文名稱": CURRENCY_NAMES.get(rate["currency"], rate["currency"]),
                "日期": rate["date"],
                "現金買入": rate["cash_buy"],
                "現金賣出": rate["cash_sell"],
                "即期買入": rate["spot_buy"],
                "即期賣出": rate["spot_sell"],
            })

    if not rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(rows, columns=columns)
    return df


@st.cache_data(ttl=300, show_spinner="正在載入歷史匯率...")
def get_history_rate(currency_code: str, days: int = 365) -> pd.DataFrame:
    """
    取得指定貨幣的歷史匯率，預設抓過去一年。

    Parameters
    ----------
    currency_code : str
        幣別代碼，例如 "USD"。
    days : int
        往前查詢的天數，預設 365。

    Returns
    -------
    pd.DataFrame
        欄位：date(datetime), cash_buy(float), cash_sell(float),
              spot_buy(float), spot_sell(float)。
        日期排序由舊到新。若查無資料則回傳空 DataFrame（含正確欄位）。
    """
    columns = ["date", "cash_buy", "cash_sell", "spot_buy", "spot_sell"]
    today = datetime.today()
    start = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")

    records = _fetch_from_finmind(currency_code, start, end)
    if not records:
        return pd.DataFrame(columns=columns)

    rows: list[dict] = []
    for r in records:
        rows.append({
            "date": r.get("date"),
            "cash_buy": _safe_float(r.get("cash_buy")),
            "cash_sell": _safe_float(r.get("cash_sell")),
            "spot_buy": _safe_float(r.get("spot_buy")),
            "spot_sell": _safe_float(r.get("spot_sell")),
        })

    df = pd.DataFrame(rows, columns=columns)

    # 轉換日期欄位為 datetime
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # 移除日期解析失敗的列
    df = df.dropna(subset=["date"])

    # 依日期由舊到新排序
    df = df.sort_values("date").reset_index(drop=True)

    return df
