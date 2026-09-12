"""
risk_calc.py — 風控計算模組

所有函式只做計算並回傳數值 / dict / DataFrame，
不包含任何 Streamlit 或 Plotly 邏輯。

支援計算：
  - ATR（Average True Range）
  - 動態停損停利
  - 凱利公式（Kelly Criterion）
  - 槓桿風險評估
"""

import pandas as pd
import numpy as np

from indicators import pick_ohlc_columns


# ──────────────────────────────────────
# ATR 計算
# ──────────────────────────────────────

def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    計算 Average True Range（ATR）。

    True Range = max(High - Low, |High - 前 Close|, |Low - 前 Close|)
    ATR = True Range 的 period 日指數移動平均。

    使用 cash_sell 當 High、cash_buy 當 Low，Close 由
    pick_ohlc_columns 自動選取（spot_sell 或 fallback cash_sell）。

    Parameters
    ----------
    df : pd.DataFrame
        歷史匯率 DataFrame（含 date, cash_buy, cash_sell, spot_buy, spot_sell）。
    period : int
        ATR 計算期數，預設 14。

    Returns
    -------
    pd.DataFrame
        新增 TR 與 ATR 欄位的 DataFrame 複本。
    """
    result = df.copy()
    ohlc = pick_ohlc_columns(result)

    high = result[ohlc["high"]].ffill()
    low = result[ohlc["low"]].ffill()
    close = result[ohlc["close"]].ffill()
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    result["TR"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    result["ATR"] = result["TR"].ewm(span=period, adjust=False, min_periods=period).mean()
    return result


# ──────────────────────────────────────
# 動態停損停利計算
# ──────────────────────────────────────

def calc_stop_levels(
    entry_price: float,
    atr_value: float,
    atr_multiplier: float = 1.5,
    risk_reward_ratio: float = 2.0,
    direction: str = "long",
) -> dict[str, float]:
    """
    根據 ATR 計算建議停損與停利價位。

    Parameters
    ----------
    entry_price : float
        進場價位。
    atr_value : float
        目前 ATR 值。
    atr_multiplier : float
        ATR 倍數，預設 1.5。
    risk_reward_ratio : float
        風險報酬比（停利距離 = 停損距離 × 此值），預設 2.0。
    direction : str
        交易方向，"long"（做多）或 "short"（做空）。

    Returns
    -------
    dict[str, float]
        stop_loss: 停損價
        take_profit: 停利價
        stop_distance: 停損點數（絕對值）
        profit_distance: 停利點數（絕對值）
        stop_pct: 停損百分比
        profit_pct: 停利百分比
    """
    stop_distance = atr_value * atr_multiplier
    profit_distance = stop_distance * risk_reward_ratio

    if direction == "long":
        stop_loss = entry_price - stop_distance
        take_profit = entry_price + profit_distance
    else:
        stop_loss = entry_price + stop_distance
        take_profit = entry_price - profit_distance

    stop_pct = (stop_distance / entry_price * 100) if entry_price != 0 else 0.0
    profit_pct = (profit_distance / entry_price * 100) if entry_price != 0 else 0.0

    return {
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "stop_distance": stop_distance,
        "profit_distance": profit_distance,
        "stop_pct": stop_pct,
        "profit_pct": profit_pct,
    }


# ──────────────────────────────────────
# 凱利公式
# ──────────────────────────────────────

def calc_kelly(
    win_rate: float,
    payoff_ratio: float,
    total_capital: float = 10000.0,
) -> dict[str, float]:
    """
    計算凱利公式（Kelly Criterion）建議倉位。

    f* = (b × p - q) / b
      b = 盈虧比（payoff_ratio）
      p = 勝率（win_rate，0~1）
      q = 1 - p

    Parameters
    ----------
    win_rate : float
        歷史勝率（0 ~ 1 之間）。
    payoff_ratio : float
        平均盈虧比（平均獲利 / 平均虧損）。
    total_capital : float
        總資金，預設 10,000。

    Returns
    -------
    dict[str, float]
        kelly_pct: 凱利建議比例（%）
        kelly_amount: 凱利建議金額
        half_kelly_pct: 保守建議比例（f*/2，%）
        half_kelly_amount: 保守建議金額
        is_viable: 策略是否可行（f* > 0）
    """
    p = max(0.0, min(1.0, win_rate))
    q = 1.0 - p
    b = max(0.001, payoff_ratio)  # 避免除以零

    kelly_f = (b * p - q) / b
    kelly_pct = kelly_f * 100
    kelly_amount = total_capital * max(0.0, kelly_f)

    half_kelly_f = kelly_f / 2
    half_kelly_pct = half_kelly_f * 100
    half_kelly_amount = total_capital * max(0.0, half_kelly_f)

    return {
        "kelly_pct": kelly_pct,
        "kelly_amount": kelly_amount,
        "half_kelly_pct": half_kelly_pct,
        "half_kelly_amount": half_kelly_amount,
        "is_viable": kelly_f > 0,
    }


# ──────────────────────────────────────
# 槓桿風險計算
# ──────────────────────────────────────

def calc_leverage_risk(
    capital: float,
    leverage: int,
    atr_value: float | None = None,
    current_price: float | None = None,
    margin_call_pct: float = 50.0,
) -> dict[str, float | str]:
    """
    計算槓桿風險指標。

    Parameters
    ----------
    capital : float
        本金（USD）。
    leverage : int
        槓桿倍數。
    atr_value : float | None
        目前 ATR 值（用於估算波動風險）。
    current_price : float | None
        目前匯率（用於計算強制平倉距離）。
    margin_call_pct : float
        強制平倉保證金維持率門檻（%），預設 50%。

    Returns
    -------
    dict[str, float | str]
        position_value: 持倉市值
        used_margin: 已用保證金
        margin_ratio: 保證金維持率（%）
        liquidation_move_pct: 觸發強平的價格反向波動百分比
        risk_level: 風險等級（低/中/高/極高）
        atr_days_to_liquidation: ATR 波動觸達強平所需天數估算
    """
    position_value = capital * leverage
    used_margin = capital
    margin_ratio = (capital / position_value * 100) if position_value != 0 else 0.0

    # 強制平倉距離：保證金維持率降到 margin_call_pct 時的價格變動
    # 初始保證金比例 = 1/leverage，強平門檻 = margin_call_pct/100 * 1/leverage
    # 價格反向波動 = 1/leverage - margin_call_pct/100 * 1/leverage
    #              = (1 - margin_call_pct/100) / leverage
    liquidation_move_pct = (1.0 - margin_call_pct / 100.0) / leverage * 100.0

    # 風險等級
    if leverage <= 5:
        risk_level = "低"
    elif leverage <= 20:
        risk_level = "中"
    elif leverage <= 50:
        risk_level = "高"
    else:
        risk_level = "極高"

    # ATR 估算觸達強平天數
    atr_days = None
    if atr_value and current_price and atr_value > 0 and current_price > 0:
        daily_move_pct = atr_value / current_price * 100
        if daily_move_pct > 0:
            atr_days = liquidation_move_pct / daily_move_pct

    return {
        "position_value": position_value,
        "used_margin": used_margin,
        "margin_ratio": margin_ratio,
        "liquidation_move_pct": liquidation_move_pct,
        "risk_level": risk_level,
        "atr_days_to_liquidation": atr_days,
    }
