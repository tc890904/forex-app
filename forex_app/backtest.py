"""
backtest.py — 回測引擎

MA 交叉策略回測：
  進場：MA20 上穿 MA50（黃金交叉），以當日 close 買入
  出場（三擇一，先到先觸發）：
    1. MA20 下穿 MA50（死亡交叉）
    2. 虧損超過 ATR × 停損倍數
    3. 獲利超過 ATR × 停利倍數

所有函式只做計算，不碰 Streamlit / Plotly。
"""

from datetime import datetime

import numpy as np
import pandas as pd

from indicators import (
    pick_close_column,
    calc_all_indicators,
    detect_crossovers,
)
from risk_calc import calc_atr


def run_ma_cross_backtest(
    df_raw: pd.DataFrame,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    atr_sl_mult: float = 1.5,
    atr_tp_mult: float = 3.0,
    initial_capital: float = 10000.0,
) -> dict:
    """
    執行 MA 交叉策略回測。

    Parameters
    ----------
    df_raw : pd.DataFrame
        歷史匯率 DataFrame（需含足夠前置資料供 MA200 計算）。
    start_date : datetime | None
        回測起始日（含）。None 則從資料最早日開始。
    end_date : datetime | None
        回測結束日（含）。None 則到資料最晚日。
    atr_sl_mult : float
        ATR 停損倍數，預設 1.5。
    atr_tp_mult : float
        ATR 停利倍數，預設 3.0。
    initial_capital : float
        初始資金，預設 10,000。

    Returns
    -------
    dict
        trades: 交易紀錄 DataFrame
        summary: 績效摘要 dict
        equity_curve: 權益曲線 DataFrame (date, equity)
    """
    if df_raw.empty or len(df_raw) < 60:
        return _empty_result(initial_capital)

    close_col = pick_close_column(df_raw)
    df = calc_all_indicators(df_raw)
    df = calc_atr(df, period=14)

    # 確保有 MA20、MA50、ATR
    required = ["MA20", "MA50", "ATR"]
    for col in required:
        if col not in df.columns:
            return _empty_result(initial_capital)

    # 偵測 MA 交叉
    crosses = detect_crossovers(df, "MA20", "MA50")

    # 裁切回測區間
    if start_date:
        df_bt = df[df["date"] >= pd.Timestamp(start_date)].copy()
    else:
        df_bt = df.copy()
    if end_date:
        df_bt = df_bt[df_bt["date"] <= pd.Timestamp(end_date)].copy()

    if df_bt.empty:
        return _empty_result(initial_capital)

    # 建立日期索引對照（加速查找）
    df_bt = df_bt.reset_index(drop=True)
    date_to_idx = {d: i for i, d in enumerate(df_bt["date"])}

    # 篩選落在回測區間內的交叉點
    bt_start = df_bt["date"].min()
    bt_end = df_bt["date"].max()
    if not crosses.empty:
        crosses_bt = crosses[
            (crosses["date"] >= bt_start) & (crosses["date"] <= bt_end)
        ].copy()
    else:
        crosses_bt = pd.DataFrame(columns=["date", "signal"])

    # ── 模擬交易 ──
    trades: list[dict] = []
    in_position = False
    entry_price = 0.0
    entry_date = None
    entry_atr = 0.0

    for i in range(len(df_bt)):
        row = df_bt.iloc[i]
        price = row[close_col]
        atr_now = row.get("ATR")
        current_date = row["date"]

        if pd.isna(price) or price == 0:
            continue

        if not in_position:
            # 檢查是否有黃金交叉進場訊號
            if not crosses_bt.empty:
                gc = crosses_bt[
                    (crosses_bt["date"] == current_date)
                    & (crosses_bt["signal"] == "golden_cross")
                ]
                if not gc.empty and pd.notna(atr_now) and atr_now > 0:
                    in_position = True
                    entry_price = price
                    entry_date = current_date
                    entry_atr = atr_now
        else:
            # 檢查出場條件
            pnl = price - entry_price
            exit_reason = None

            # 條件 1：死亡交叉
            if not crosses_bt.empty:
                dc = crosses_bt[
                    (crosses_bt["date"] == current_date)
                    & (crosses_bt["signal"] == "death_cross")
                ]
                if not dc.empty:
                    exit_reason = "交叉出場"

            # 條件 2：停損
            if exit_reason is None and pnl < 0:
                if abs(pnl) >= entry_atr * atr_sl_mult:
                    exit_reason = "停損出場"

            # 條件 3：停利
            if exit_reason is None and pnl > 0:
                if pnl >= entry_atr * atr_tp_mult:
                    exit_reason = "停利出場"

            if exit_reason:
                ret_pct = (price - entry_price) / entry_price * 100
                trades.append({
                    "進場日": entry_date,
                    "進場價": entry_price,
                    "出場日": current_date,
                    "出場價": price,
                    "出場原因": exit_reason,
                    "損益": price - entry_price,
                    "報酬率(%)": round(ret_pct, 4),
                })
                in_position = False

    # 如果回測結束時仍持倉，以最後一筆價格平倉
    if in_position:
        last_row = df_bt.iloc[-1]
        last_price = last_row[close_col]
        if pd.notna(last_price) and last_price > 0:
            ret_pct = (last_price - entry_price) / entry_price * 100
            trades.append({
                "進場日": entry_date,
                "進場價": entry_price,
                "出場日": last_row["date"],
                "出場價": last_price,
                "出場原因": "回測結束",
                "損益": last_price - entry_price,
                "報酬率(%)": round(ret_pct, 4),
            })

    df_trades = pd.DataFrame(trades)
    summary = _calc_summary(df_trades, initial_capital)
    equity = _build_equity_curve(df_trades, initial_capital)

    return {
        "trades": df_trades,
        "summary": summary,
        "equity_curve": equity,
    }


def _empty_result(capital: float) -> dict:
    """回傳空的回測結果。"""
    return {
        "trades": pd.DataFrame(),
        "summary": {
            "total_trades": 0,
            "win_rate": 0.0,
            "avg_return": 0.0,
            "cum_return": 0.0,
            "max_loss": 0.0,
            "max_consec_loss": 0,
            "max_drawdown": 0.0,
        },
        "equity_curve": pd.DataFrame({"date": [], "equity": []}),
    }


def _calc_summary(df_trades: pd.DataFrame, capital: float) -> dict:
    """
    根據交易紀錄計算績效摘要。

    Parameters
    ----------
    df_trades : pd.DataFrame
        交易紀錄。
    capital : float
        初始資金。

    Returns
    -------
    dict
        各項績效指標。
    """
    if df_trades.empty:
        return _empty_result(capital)["summary"]

    n = len(df_trades)
    returns = df_trades["報酬率(%)"]
    wins = (returns > 0).sum()

    # 最大連續虧損次數
    max_consec = 0
    consec = 0
    for r in returns:
        if r < 0:
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 0

    # 累計報酬率（連乘）
    cum_factor = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        cum_factor *= (1 + r / 100)
        peak = max(peak, cum_factor)
        dd = (peak - cum_factor) / peak * 100
        max_dd = max(max_dd, dd)

    cum_return = (cum_factor - 1) * 100

    return {
        "total_trades": n,
        "win_rate": wins / n * 100 if n > 0 else 0.0,
        "avg_return": returns.mean(),
        "cum_return": cum_return,
        "max_loss": returns.min(),
        "max_consec_loss": max_consec,
        "max_drawdown": max_dd,
    }


def _build_equity_curve(
    df_trades: pd.DataFrame,
    capital: float,
) -> pd.DataFrame:
    """
    根據交易紀錄建構權益曲線。

    Parameters
    ----------
    df_trades : pd.DataFrame
        交易紀錄。
    capital : float
        初始資金。

    Returns
    -------
    pd.DataFrame
        欄位：date, equity。
    """
    if df_trades.empty:
        return pd.DataFrame({"date": [], "equity": []})

    dates = []
    equities = []
    equity = capital

    for _, trade in df_trades.iterrows():
        # 進場點
        dates.append(trade["進場日"])
        equities.append(equity)
        # 出場點
        ret = trade["報酬率(%)"] / 100
        equity *= (1 + ret)
        dates.append(trade["出場日"])
        equities.append(equity)

    return pd.DataFrame({"date": dates, "equity": equities})
