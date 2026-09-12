"""
sentiment.py — 技術面情緒分析

因免費新聞 API 需要 API key 且有額度限制，
本模組使用技術指標（RSI + MACD + MA）的綜合訊號
作為「技術面情緒」指標。

標示為「技術面情緒」而非「新聞情緒」，避免誤導使用者。

所有函式只做計算，不碰 Streamlit / Plotly。
"""

import pandas as pd
import numpy as np

from indicators import pick_close_column, calc_all_indicators


def calc_technical_sentiment(df_raw: pd.DataFrame) -> dict:
    """
    計算單一幣別的技術面情緒。

    基於三個條件評分（每項 +1 / 0 / -1）：
      1. MA 趨勢：MA20 vs MA50
      2. RSI：超買 / 超賣 / 中性
      3. MACD：DIF vs DEA

    Parameters
    ----------
    df_raw : pd.DataFrame
        歷史匯率 DataFrame（建議至少 60 天）。

    Returns
    -------
    dict
        score: 總分 (-3 ~ +3)
        label: 情緒標籤 emoji（🟢 / 🔴 / ⚪）
        text: 文字描述（偏多 / 偏空 / 中性）
    """
    if df_raw.empty or len(df_raw) < 30:
        return {"score": 0, "label": "⚪", "text": "資料不足"}

    close_col = pick_close_column(df_raw)
    df = calc_all_indicators(df_raw)

    if df.empty:
        return {"score": 0, "label": "⚪", "text": "資料不足"}

    last = df.iloc[-1]
    score = 0

    # 1. MA 趨勢
    ma20 = last.get("MA20")
    ma50 = last.get("MA50")
    if pd.notna(ma20) and pd.notna(ma50):
        score += 1 if ma20 > ma50 else -1

    # 2. RSI
    rsi = last.get("RSI")
    if pd.notna(rsi):
        if rsi < 30:
            score += 1   # 超賣可能反彈
        elif rsi > 70:
            score -= 1   # 超買可能回落

    # 3. MACD
    dif = last.get("MACD_DIF")
    dea = last.get("MACD_DEA")
    if pd.notna(dif) and pd.notna(dea):
        score += 1 if dif > dea else -1

    # 轉換為標籤
    if score >= 1:
        return {"score": score, "label": "🟢", "text": "偏多"}
    elif score <= -1:
        return {"score": score, "label": "🔴", "text": "偏空"}
    else:
        return {"score": score, "label": "⚪", "text": "中性"}


def batch_sentiment(
    codes: list[str],
    history_loader,
    days: int = 90,
) -> dict[str, dict]:
    """
    批次計算多幣別的技術面情緒。

    Parameters
    ----------
    codes : list[str]
        幣別代碼清單。
    history_loader : callable
        載入歷史資料的函式，簽名 (code, days) -> pd.DataFrame。
    days : int
        回看天數，預設 90。

    Returns
    -------
    dict[str, dict]
        {幣別代碼: sentiment_dict}。
    """
    results: dict[str, dict] = {}
    for code in codes:
        try:
            df = history_loader(code, days=days)
            results[code] = calc_technical_sentiment(df)
        except Exception:
            results[code] = {"score": 0, "label": "⚪", "text": "錯誤"}
    return results
