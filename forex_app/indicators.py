"""
indicators.py — 技術指標計算模組

所有函式只做計算並回傳 DataFrame / Series，
不包含任何 Streamlit 或 Plotly 邏輯。

支援指標：
  - 移動平均線（MA）
  - 布林通道（Bollinger Bands）
  - RSI（Relative Strength Index）
  - MACD（Moving Average Convergence Divergence）
  - 均線 / MACD 交叉偵測
"""

import pandas as pd
import numpy as np


# ──────────────────────────────────────
# 價格欄位選擇輔助
# ──────────────────────────────────────

def pick_ohlc_columns(df: pd.DataFrame) -> dict[str, str]:
    """
    根據資料可用性選擇 OHLC 對應欄位。

    台銀牌告匯率沒有真正的 OHLC，使用以下對應：
      Open = spot_buy, High = cash_sell, Low = cash_buy, Close = spot_sell

    若即期匯率全為 NaN / 0，fallback 到現金匯率：
      Open = cash_buy, High = cash_sell, Low = cash_buy, Close = cash_sell

    Parameters
    ----------
    df : pd.DataFrame
        包含 cash_buy, cash_sell, spot_buy, spot_sell 欄位的匯率資料。

    Returns
    -------
    dict[str, str]
        {"open": 欄位名, "high": 欄位名, "low": 欄位名, "close": 欄位名,
         "label": "即期" 或 "現金"}
    """
    has_spot = False
    if "spot_sell" in df.columns and "spot_buy" in df.columns:
        valid = df["spot_sell"].dropna()
        valid = valid[valid != 0.0]
        if len(valid) >= 1:
            has_spot = True

    if has_spot:
        return {
            "open": "spot_buy",
            "high": "cash_sell",
            "low": "cash_buy",
            "close": "spot_sell",
            "label": "即期",
        }
    else:
        return {
            "open": "cash_buy",
            "high": "cash_sell",
            "low": "cash_buy",
            "close": "cash_sell",
            "label": "現金",
        }


def pick_close_column(df: pd.DataFrame) -> str:
    """
    選擇收盤價欄位：優先 spot_sell，不足則 fallback 到 cash_sell。

    Parameters
    ----------
    df : pd.DataFrame
        歷史匯率 DataFrame。

    Returns
    -------
    str
        "spot_sell" 或 "cash_sell"。
    """
    mapping = pick_ohlc_columns(df)
    return mapping["close"]


# ──────────────────────────────────────
# 移動平均線
# ──────────────────────────────────────

def calc_moving_averages(
    df: pd.DataFrame,
    close_col: str,
    windows: list[int] | None = None,
) -> pd.DataFrame:
    """
    計算多條簡單移動平均線（SMA）。

    Parameters
    ----------
    df : pd.DataFrame
        必須包含 close_col 指定的欄位。
    close_col : str
        收盤價欄位名稱。
    windows : list[int] | None
        均線期數清單，預設 [20, 50, 200]。

    Returns
    -------
    pd.DataFrame
        原 DataFrame 複本，新增 MA{n} 欄位（例如 MA20, MA50, MA200）。
    """
    if windows is None:
        windows = [20, 50, 200]

    result = df.copy()
    for w in windows:
        result[f"MA{w}"] = result[close_col].rolling(window=w, min_periods=w).mean()
    return result


# ──────────────────────────────────────
# 布林通道
# ──────────────────────────────────────

def calc_bollinger_bands(
    df: pd.DataFrame,
    close_col: str,
    window: int = 20,
    num_std: float = 2.0,
) -> pd.DataFrame:
    """
    計算布林通道（Bollinger Bands）。

    Parameters
    ----------
    df : pd.DataFrame
        必須包含 close_col 指定的欄位。
    close_col : str
        收盤價欄位名稱。
    window : int
        移動平均與標準差的期數，預設 20。
    num_std : float
        上下軌與中軌的標準差倍數，預設 2.0。

    Returns
    -------
    pd.DataFrame
        原 DataFrame 複本，新增 BB_mid, BB_upper, BB_lower 欄位。
    """
    result = df.copy()
    rolling = result[close_col].rolling(window=window, min_periods=window)
    result["BB_mid"] = rolling.mean()
    std = rolling.std()
    result["BB_upper"] = result["BB_mid"] + num_std * std
    result["BB_lower"] = result["BB_mid"] - num_std * std
    return result


# ──────────────────────────────────────
# RSI
# ──────────────────────────────────────

def calc_rsi(
    df: pd.DataFrame,
    close_col: str,
    period: int = 14,
) -> pd.DataFrame:
    """
    計算 RSI（Relative Strength Index）。

    使用標準公式：
      RSI = 100 - 100 / (1 + RS)
      RS  = period 日平均漲幅 / period 日平均跌幅

    平均漲幅/跌幅採用 Wilder 平滑法（指數移動平均）。

    Parameters
    ----------
    df : pd.DataFrame
        必須包含 close_col 指定的欄位。
    close_col : str
        收盤價欄位名稱。
    period : int
        RSI 計算期數，預設 14。

    Returns
    -------
    pd.DataFrame
        原 DataFrame 複本，新增 RSI 欄位。
    """
    result = df.copy()
    delta = result[close_col].diff()

    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    # Wilder 平滑法
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    result["RSI"] = 100.0 - (100.0 / (1.0 + rs))
    return result


# ──────────────────────────────────────
# MACD
# ──────────────────────────────────────

def calc_macd(
    df: pd.DataFrame,
    close_col: str,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """
    計算 MACD（Moving Average Convergence Divergence）。

    Parameters
    ----------
    df : pd.DataFrame
        必須包含 close_col 指定的欄位。
    close_col : str
        收盤價欄位名稱。
    fast : int
        快線 EMA 期數，預設 12。
    slow : int
        慢線 EMA 期數，預設 26。
    signal : int
        訊號線 EMA 期數，預設 9。

    Returns
    -------
    pd.DataFrame
        原 DataFrame 複本，新增 MACD_DIF, MACD_DEA, MACD_Hist 欄位。
    """
    result = df.copy()
    ema_fast = result[close_col].ewm(span=fast, adjust=False).mean()
    ema_slow = result[close_col].ewm(span=slow, adjust=False).mean()

    result["MACD_DIF"] = ema_fast - ema_slow
    result["MACD_DEA"] = result["MACD_DIF"].ewm(span=signal, adjust=False).mean()
    result["MACD_Hist"] = result["MACD_DIF"] - result["MACD_DEA"]
    return result


# ──────────────────────────────────────
# 交叉偵測
# ──────────────────────────────────────

def detect_crossovers(
    df: pd.DataFrame,
    fast_col: str,
    slow_col: str,
) -> pd.DataFrame:
    """
    偵測兩條線的黃金交叉與死亡交叉。

    黃金交叉：前一日 fast < slow，當日 fast >= slow
    死亡交叉：前一日 fast >= slow，當日 fast < slow

    Parameters
    ----------
    df : pd.DataFrame
        必須包含 fast_col 和 slow_col 欄位。
    fast_col : str
        快線欄位名稱。
    slow_col : str
        慢線欄位名稱。

    Returns
    -------
    pd.DataFrame
        只含交叉點的 DataFrame，欄位：
        date, signal ("golden_cross" 或 "death_cross"),
        以及原始 fast/slow 值。
    """
    valid = df.dropna(subset=[fast_col, slow_col]).copy()
    if len(valid) < 2:
        return pd.DataFrame(columns=["date", "signal", fast_col, slow_col])

    prev_fast = valid[fast_col].shift(1)
    prev_slow = valid[slow_col].shift(1)
    curr_fast = valid[fast_col]
    curr_slow = valid[slow_col]

    golden = (prev_fast < prev_slow) & (curr_fast >= curr_slow)
    death = (prev_fast >= prev_slow) & (curr_fast < curr_slow)

    crosses: list[dict] = []
    for idx in valid.index[golden]:
        crosses.append({
            "date": valid.loc[idx, "date"],
            "signal": "golden_cross",
            fast_col: valid.loc[idx, fast_col],
            slow_col: valid.loc[idx, slow_col],
        })
    for idx in valid.index[death]:
        crosses.append({
            "date": valid.loc[idx, "date"],
            "signal": "death_cross",
            fast_col: valid.loc[idx, fast_col],
            slow_col: valid.loc[idx, slow_col],
        })

    result = pd.DataFrame(crosses)
    if not result.empty:
        result = result.sort_values("date").reset_index(drop=True)
    return result


# ──────────────────────────────────────
# 布林通道位置判斷
# ──────────────────────────────────────

def bollinger_position(
    close_val: float | None,
    upper: float | None,
    mid: float | None,
    lower: float | None,
) -> tuple[str, str]:
    """
    判斷目前價格在布林通道中的位置。

    Parameters
    ----------
    close_val : float | None
        目前收盤價。
    upper : float | None
        布林通道上軌。
    mid : float | None
        布林通道中軌。
    lower : float | None
        布林通道下軌。

    Returns
    -------
    tuple[str, str]
        (位置描述, 訊號方向)。訊號方向為 "bullish" / "bearish" / "neutral"。
    """
    if any(v is None or (isinstance(v, float) and np.isnan(v))
           for v in [close_val, upper, mid, lower]):
        return "資料不足", "neutral"

    band_width = upper - lower
    if band_width == 0:
        return "通道寬度為零", "neutral"

    position_pct = (close_val - lower) / band_width * 100

    if position_pct >= 80:
        return f"靠近上軌（{position_pct:.0f}%）", "bearish"
    elif position_pct <= 20:
        return f"靠近下軌（{position_pct:.0f}%）", "bullish"
    else:
        return f"通道中段（{position_pct:.0f}%）", "neutral"


# ──────────────────────────────────────
# 一次性計算所有指標
# ──────────────────────────────────────

def calc_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    一次計算所有技術指標：MA、布林通道、RSI、MACD。

    自動偵測收盤價欄位（spot_sell 優先，fallback cash_sell）。

    Parameters
    ----------
    df : pd.DataFrame
        歷史匯率 DataFrame（含 date, cash_buy, cash_sell, spot_buy, spot_sell）。

    Returns
    -------
    pd.DataFrame
        新增所有指標欄位的 DataFrame。
    """
    close_col = pick_close_column(df)

    result = df.copy()
    result = calc_moving_averages(result, close_col)
    result = calc_bollinger_bands(result, close_col)
    result = calc_rsi(result, close_col)
    result = calc_macd(result, close_col)
    return result
