"""
line_bot 內建分析引擎（不依賴 forex_app 路徑）。

涵蓋：技術 5 評分、ATR 停損、凱利、槓桿、相關、強弱、簡易回測。
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def records_to_df(records: list[dict]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records).copy()
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
    for col in ("spot_buy", "spot_sell", "cash_buy", "cash_sell"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = np.nan
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return df


def pick_close(df: pd.DataFrame) -> str:
    if "spot_sell" in df.columns:
        valid = df["spot_sell"].dropna()
        valid = valid[valid != 0]
        if len(valid) >= 5:
            return "spot_sell"
    return "cash_sell"


def enrich_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """加入 MA / RSI / MACD / 布林 / ATR。"""
    if df.empty or len(df) < 30:
        return df
    out = df.copy()
    close_col = pick_close(out)
    close = out[close_col].ffill()

    out["MA20"] = close.rolling(20).mean()
    out["MA50"] = close.rolling(50).mean()
    out["MA200"] = close.rolling(200).mean()

    delta = close.diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1 / 14, min_periods=14).mean()
    loss = (-delta).where(delta < 0, 0).ewm(alpha=1 / 14, min_periods=14).mean()
    rs = gain / loss.replace(0, np.nan)
    out["RSI"] = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    out["MACD_DIF"] = ema12 - ema26
    out["MACD_DEA"] = out["MACD_DIF"].ewm(span=9).mean()
    out["MACD_Hist"] = out["MACD_DIF"] - out["MACD_DEA"]

    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    out["BB_mid"] = mid
    out["BB_upper"] = mid + 2 * std
    out["BB_lower"] = mid - 2 * std

    # ATR via cash high/low approx
    high = out["cash_sell"].fillna(close)
    low = out["cash_buy"].fillna(close)
    prev = close.shift(1)
    tr = pd.concat([(high - low).abs(), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    out["ATR"] = tr.ewm(span=14, adjust=False, min_periods=14).mean()
    out["_close"] = close
    return out


def score_signals(df: pd.DataFrame) -> Optional[dict]:
    """5 項技術評分（與網頁 signals 頁對齊）。"""
    df = enrich_indicators(df)
    if df.empty or len(df) < 30:
        return None
    last = df.iloc[-1]
    items: list[dict] = []
    total = 0

    ma20, ma50 = last.get("MA20"), last.get("MA50")
    if pd.notna(ma20) and pd.notna(ma50):
        if ma20 > ma50:
            s, v = 1, "偏多"
        elif ma20 < ma50:
            s, v = -1, "偏空"
        else:
            s, v = 0, "中性"
        val = f"MA20={ma20:.4f} MA50={ma50:.4f}"
    else:
        s, v, val = 0, "不足", "—"
    items.append({"name": "MA 趨勢", "value": val, "verdict": v, "score": s})
    total += s

    # MA 交叉近 5 日
    cross_s, cross_v, cross_val = 0, "無近期交叉", "—"
    if "MA20" in df.columns and "MA50" in df.columns and len(df) >= 6:
        a = df["MA20"] - df["MA50"]
        recent = df.tail(6)
        for i in range(1, len(recent)):
            prev_a = a.iloc[recent.index[i - 1]]
            cur_a = a.iloc[recent.index[i]]
            if pd.isna(prev_a) or pd.isna(cur_a):
                continue
            if prev_a <= 0 < cur_a:
                cross_s, cross_v, cross_val = 1, "近期金叉", recent.iloc[i]["date"].strftime("%m/%d")
            elif prev_a >= 0 > cur_a:
                cross_s, cross_v, cross_val = -1, "近期死叉", recent.iloc[i]["date"].strftime("%m/%d")
    items.append({"name": "MA 交叉", "value": cross_val, "verdict": cross_v, "score": cross_s})
    total += cross_s

    rsi = last.get("RSI")
    if pd.notna(rsi):
        if rsi < 30:
            s, v = 1, "超賣"
        elif rsi > 70:
            s, v = -1, "超買"
        else:
            s, v = 0, "中性"
        val = f"{rsi:.1f}"
    else:
        s, v, val = 0, "不足", "—"
    items.append({"name": "RSI", "value": val, "verdict": v, "score": s})
    total += s

    dif, dea, hist = last.get("MACD_DIF"), last.get("MACD_DEA"), last.get("MACD_Hist")
    if pd.notna(dif) and pd.notna(dea):
        if dif > dea and (pd.isna(hist) or hist > 0):
            s, v = 1, "動能偏多"
        elif dif < dea and (pd.isna(hist) or hist < 0):
            s, v = -1, "動能偏空"
        else:
            s, v = 0, "中性"
        val = f"DIF={dif:.4f}"
    else:
        s, v, val = 0, "不足", "—"
    items.append({"name": "MACD", "value": val, "verdict": v, "score": s})
    total += s

    close_v = last.get("_close")
    bu, bl = last.get("BB_upper"), last.get("BB_lower")
    if pd.notna(close_v) and pd.notna(bu) and pd.notna(bl):
        if close_v < bl:
            s, v = 1, "低於下軌"
        elif close_v > bu:
            s, v = -1, "高於上軌"
        else:
            s, v = 0, "通道內"
        val = f"{close_v:.4f}"
    else:
        s, v, val = 0, "不足", "—"
    items.append({"name": "布林位置", "value": val, "verdict": v, "score": s})
    total += s

    if total >= 3:
        mood = "強烈看多"
    elif total >= 1:
        mood = "偏多"
    elif total == 0:
        mood = "中性"
    elif total >= -2:
        mood = "偏空"
    else:
        mood = "強烈看空"

    summary_parts = [f"{it['name']}{it['verdict']}" for it in items if it["score"] != 0]
    summary = "；".join(summary_parts) if summary_parts else "各指標多為中性"
    summary += f"。綜合{mood}（{total:+d}）。"

    return {
        "items": items,
        "total_score": total,
        "mood": mood,
        "summary": summary,
        "rsi": float(rsi) if pd.notna(rsi) else None,
        "atr": float(last["ATR"]) if pd.notna(last.get("ATR")) else None,
        "close": float(close_v) if pd.notna(close_v) else None,
    }


def calc_atr_stops(
    entry: float,
    atr: float,
    direction: str = "long",
    atr_mult: float = 1.5,
    rr: float = 2.0,
) -> dict:
    dist = atr * atr_mult
    profit = dist * rr
    if direction == "long":
        sl, tp = entry - dist, entry + profit
    else:
        sl, tp = entry + dist, entry - profit
    return {
        "entry": entry,
        "atr": atr,
        "atr_mult": atr_mult,
        "direction": direction,
        "stop_loss": sl,
        "take_profit": tp,
        "stop_pct": dist / entry * 100 if entry else 0,
        "profit_pct": profit / entry * 100 if entry else 0,
        "rr": rr,
    }


def calc_kelly(win_rate: float = 0.55, payoff: float = 1.5, capital: float = 10000.0) -> dict:
    p = max(0.0, min(1.0, win_rate))
    q = 1 - p
    b = max(0.001, payoff)
    f = (b * p - q) / b
    return {
        "win_rate": p,
        "payoff": b,
        "capital": capital,
        "kelly_pct": f * 100,
        "kelly_amount": capital * max(0, f),
        "half_kelly_pct": f / 2 * 100,
        "half_kelly_amount": capital * max(0, f / 2),
        "viable": f > 0,
    }


def calc_leverage(capital: float = 10000.0, leverage: int = 10, atr: float | None = None, price: float | None = None) -> dict:
    position = capital * leverage
    liq_pct = (1 - 0.5) / leverage * 100
    if leverage <= 5:
        level = "低"
    elif leverage <= 20:
        level = "中"
    elif leverage <= 50:
        level = "高"
    else:
        level = "極高"
    atr_days = None
    if atr and price and atr > 0 and price > 0:
        daily = atr / price * 100
        if daily > 0:
            atr_days = liq_pct / daily
    return {
        "capital": capital,
        "leverage": leverage,
        "position_value": position,
        "margin_ratio": capital / position * 100 if position else 0,
        "liquidation_move_pct": liq_pct,
        "risk_level": level,
        "atr_days": atr_days,
    }


def strength_ranking(results: dict[str, dict]) -> list[dict]:
    """依日漲跌排序。"""
    rows = []
    for code, r in results.items():
        if not r or "error" in r:
            continue
        ch = r.get("tech", {}).get("change_pct")
        if ch is None:
            continue
        rows.append(
            {
                "code": code,
                "rate": r["rate"]["spot_sell"],
                "change_pct": ch,
                "mood": r.get("mood", ""),
            }
        )
    rows.sort(key=lambda x: x["change_pct"], reverse=True)
    return rows


def correlation_matrix(series_map: dict[str, pd.Series]) -> pd.DataFrame:
    if len(series_map) < 2:
        return pd.DataFrame()
    frame = pd.DataFrame(series_map).dropna(how="any")
    if frame.empty or len(frame) < 10:
        return pd.DataFrame()
    return frame.corr()


def simple_ma_backtest(df: pd.DataFrame, initial: float = 10000.0) -> dict:
    """簡化 MA20/50 交叉回測摘要。"""
    df = enrich_indicators(df)
    if df.empty or len(df) < 60:
        return {"error": "資料不足，無法回測"}

    close = df["_close"]
    position = 0
    entry = 0.0
    equity = initial
    trades = []
    peak = initial
    max_dd = 0.0

    for i in range(1, len(df)):
        ma20_p, ma50_p = df["MA20"].iloc[i - 1], df["MA50"].iloc[i - 1]
        ma20, ma50 = df["MA20"].iloc[i], df["MA50"].iloc[i]
        price = float(close.iloc[i])
        atr = df["ATR"].iloc[i]
        if pd.isna(ma20) or pd.isna(ma50) or pd.isna(ma20_p) or pd.isna(ma50_p):
            continue

        # exit
        if position == 1:
            sl = entry - (float(atr) * 1.5 if pd.notna(atr) else entry * 0.02)
            tp = entry + (float(atr) * 3.0 if pd.notna(atr) else entry * 0.04)
            exit_reason = None
            if ma20_p >= ma50_p and ma20 < ma50:
                exit_reason = "死叉"
            elif price <= sl:
                exit_reason = "停損"
            elif price >= tp:
                exit_reason = "停利"
            if exit_reason:
                pnl_pct = (price - entry) / entry
                equity *= 1 + pnl_pct
                trades.append({"pnl_pct": pnl_pct * 100, "reason": exit_reason})
                position = 0

        # entry
        if position == 0 and ma20_p <= ma50_p and ma20 > ma50:
            position = 1
            entry = price

        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100 if peak else 0
        max_dd = max(max_dd, dd)

    if not trades:
        return {
            "trades": 0,
            "win_rate": 0,
            "total_return_pct": 0,
            "max_drawdown_pct": 0,
            "final_equity": initial,
            "note": "區間內無完整交易",
        }

    wins = [t for t in trades if t["pnl_pct"] > 0]
    total_ret = (equity / initial - 1) * 100
    return {
        "trades": len(trades),
        "win_rate": len(wins) / len(trades) * 100,
        "total_return_pct": total_ret,
        "max_drawdown_pct": max_dd,
        "final_equity": equity,
        "avg_pnl": float(np.mean([t["pnl_pct"] for t in trades])),
        "note": "MA20/50 交叉 + ATR 停損停利（簡化）",
    }
