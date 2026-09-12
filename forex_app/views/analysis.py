"""
pages/analysis.py — 單一幣別分析頁

功能清單：
  1. K 線圖 + 布林通道 + MA 線（含黃金/死亡交叉標記）
  2. RSI 指標圖（超買/超賣區域填色）
  3. RSI 儀表板（Gauge）
  4. MACD 指標圖（含柱狀圖 + 交叉偵測）
  5. 訊號摘要卡片（MA 趨勢 / RSI / MACD / 布林位置）

K 線、RSI、MACD 三張子圖共享 x 軸，可同步縮放與拖曳。
"""

from datetime import timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from config import ALL_CURRENCY_CODES, CURRENCY_NAMES
from data import get_history_rate
from indicators import (
    pick_ohlc_columns,
    pick_close_column,
    calc_all_indicators,
    detect_crossovers,
    bollinger_position,
)

# ──────────────────────────────────────
# 常數
# ──────────────────────────────────────
PERIOD_OPTIONS: dict[str, int] = {
    "近一週": 7,
    "近一個月": 30,
    "近三個月": 90,
    "近一年": 365,
}
# MA200 需至少 200 個交易日，額外多抓的天數
EXTRA_LOOKBACK_DAYS: int = 250


# ══════════════════════════════════════
# 資料準備
# ══════════════════════════════════════

@st.cache_data(ttl=300, show_spinner="正在載入歷史資料與計算指標...")
def _load_and_compute(code: str, display_days: int) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """
    載入歷史資料、計算所有指標，並裁切為顯示區間。

    Parameters
    ----------
    code : str
        幣別代碼。
    display_days : int
        使用者選擇的顯示天數。

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame, str]
        (顯示區間 DataFrame, 完整計算 DataFrame, 收盤價欄位名稱)
    """
    total_days = display_days + EXTRA_LOOKBACK_DAYS
    df_raw = get_history_rate(code, days=total_days)

    if df_raw.empty:
        return pd.DataFrame(), pd.DataFrame(), "spot_sell"

    close_col = pick_close_column(df_raw)
    df_full = calc_all_indicators(df_raw)

    # 裁切顯示區間
    if not df_full.empty:
        cutoff = df_full["date"].max() - timedelta(days=display_days)
        df_display = df_full[df_full["date"] >= cutoff].copy()
    else:
        df_display = df_full.copy()

    return df_display, df_full, close_col


# ══════════════════════════════════════
# 功能 5：訊號摘要卡片
# ══════════════════════════════════════

def _render_signal_cards(df: pd.DataFrame, close_col: str) -> None:
    """
    渲染訊號摘要卡片：MA 趨勢、RSI、MACD、布林位置。

    Parameters
    ----------
    df : pd.DataFrame
        含所有指標欄位的顯示區間 DataFrame。
    close_col : str
        收盤價欄位名稱。
    """
    if df.empty:
        st.warning("資料不足，無法顯示訊號摘要。")
        return

    last = df.iloc[-1]

    # --- MA 趨勢 ---
    ma20 = last.get("MA20")
    ma50 = last.get("MA50")
    if pd.notna(ma20) and pd.notna(ma50):
        if ma20 > ma50:
            ma_text, ma_signal = "MA20 > MA50 偏多", "bullish"
        elif ma20 < ma50:
            ma_text, ma_signal = "MA20 < MA50 偏空", "bearish"
        else:
            ma_text, ma_signal = "MA20 ≈ MA50 中性", "neutral"
    else:
        ma_text, ma_signal = "資料不足", "neutral"

    # --- RSI ---
    rsi_val = last.get("RSI")
    if pd.notna(rsi_val):
        if rsi_val >= 70:
            rsi_text = f"RSI {rsi_val:.1f} 超買"
            rsi_signal = "bearish"
        elif rsi_val <= 30:
            rsi_text = f"RSI {rsi_val:.1f} 超賣"
            rsi_signal = "bullish"
        else:
            rsi_text = f"RSI {rsi_val:.1f} 中性"
            rsi_signal = "neutral"
    else:
        rsi_text, rsi_signal = "資料不足", "neutral"

    # --- MACD ---
    dif = last.get("MACD_DIF")
    dea = last.get("MACD_DEA")
    if pd.notna(dif) and pd.notna(dea):
        if dif > dea:
            macd_text, macd_signal = "DIF > DEA 偏多", "bullish"
        elif dif < dea:
            macd_text, macd_signal = "DIF < DEA 偏空", "bearish"
        else:
            macd_text, macd_signal = "DIF ≈ DEA 中性", "neutral"
    else:
        macd_text, macd_signal = "資料不足", "neutral"

    # --- 布林位置 ---
    close_val = last.get(close_col)
    bb_upper = last.get("BB_upper")
    bb_mid = last.get("BB_mid")
    bb_lower = last.get("BB_lower")
    bb_text, bb_signal = bollinger_position(close_val, bb_upper, bb_mid, bb_lower)

    # --- 渲染 ---
    cards = [
        ("📈 MA 趨勢", ma_text, ma_signal),
        ("📊 RSI", rsi_text, rsi_signal),
        ("📉 MACD", macd_text, macd_signal),
        ("🎯 布林位置", bb_text, bb_signal),
    ]

    color_map = {
        "bullish": "#d1fae5",   # 淡綠
        "bearish": "#fee2e2",   # 淡紅
        "neutral": "#f3f4f6",   # 淡灰
    }
    text_color_map = {
        "bullish": "#065f46",
        "bearish": "#991b1b",
        "neutral": "#374151",
    }

    cols = st.columns(4)
    for i, (title, text, signal) in enumerate(cards):
        bg = color_map.get(signal, "#f3f4f6")
        fg = text_color_map.get(signal, "#374151")
        with cols[i]:
            st.markdown(
                f"<div style='background:{bg}; padding:12px 16px; "
                f"border-radius:8px; text-align:center;'>"
                f"<div style='font-size:0.85rem; color:#6b7280;'>{title}</div>"
                f"<div style='font-size:1rem; font-weight:600; color:{fg}; "
                f"margin-top:4px;'>{text}</div></div>",
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════
# 功能 1–4：主圖表（K 線 + RSI + MACD）
# ══════════════════════════════════════

def _build_main_chart(
    df_display: pd.DataFrame,
    df_full: pd.DataFrame,
    close_col: str,
    code: str,
) -> go.Figure:
    """
    建構包含 K 線圖、RSI 圖、MACD 圖的三面板子圖。

    Parameters
    ----------
    df_display : pd.DataFrame
        顯示區間的 DataFrame（含所有指標欄位）。
    df_full : pd.DataFrame
        完整資料（用於交叉偵測跨區間計算）。
    close_col : str
        收盤價欄位名稱。
    code : str
        幣別代碼，用於圖表標題。

    Returns
    -------
    go.Figure
        包含三個子圖的 Plotly Figure。
    """
    ohlc = pick_ohlc_columns(df_display)

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.55, 0.20, 0.25],
        subplot_titles=[
            f"{code} {CURRENCY_NAMES.get(code, '')} K 線圖",
            "RSI（14）",
            "MACD（12, 26, 9）",
        ],
    )

    dates = df_display["date"]

    # ────────────────────────────────
    # Row 1：K 線圖
    # ────────────────────────────────

    # 處理 OHLC 欄位中的 NaN（用 close 填補）
    open_vals = df_display[ohlc["open"]].fillna(df_display[ohlc["close"]])
    high_vals = df_display[ohlc["high"]].fillna(df_display[ohlc["close"]])
    low_vals = df_display[ohlc["low"]].fillna(df_display[ohlc["close"]])
    close_vals = df_display[ohlc["close"]]

    fig.add_trace(
        go.Candlestick(
            x=dates,
            open=open_vals,
            high=high_vals,
            low=low_vals,
            close=close_vals,
            name="K 線",
            increasing_line_color="#10b981",
            decreasing_line_color="#ef4444",
        ),
        row=1, col=1,
    )

    # MA 線
    ma_styles = [
        ("MA20", "#3b82f6", 1.2),   # 藍色
        ("MA50", "#f97316", 1.2),   # 橘色
        ("MA200", "#ef4444", 1.0),  # 紅色
    ]
    for col_name, color, width in ma_styles:
        if col_name in df_display.columns:
            fig.add_trace(
                go.Scatter(
                    x=dates, y=df_display[col_name],
                    mode="lines",
                    name=col_name,
                    line=dict(color=color, width=width),
                ),
                row=1, col=1,
            )

    # 布林通道
    if "BB_upper" in df_display.columns:
        fig.add_trace(
            go.Scatter(
                x=dates, y=df_display["BB_upper"],
                mode="lines",
                name="布林上軌",
                line=dict(color="#93c5fd", width=1, dash="dash"),
                showlegend=True,
            ),
            row=1, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=dates, y=df_display["BB_lower"],
                mode="lines",
                name="布林下軌",
                line=dict(color="#93c5fd", width=1, dash="dash"),
                fill="tonexty",
                fillcolor="rgba(147, 197, 253, 0.12)",
                showlegend=True,
            ),
            row=1, col=1,
        )

    # MA 交叉標記
    ma_crosses = detect_crossovers(df_full, "MA20", "MA50")
    if not ma_crosses.empty:
        display_start = dates.min()
        display_end = dates.max()
        ma_crosses_vis = ma_crosses[
            (ma_crosses["date"] >= display_start) & (ma_crosses["date"] <= display_end)
        ]
        for _, row in ma_crosses_vis.iterrows():
            cross_date = row["date"]
            # 取該日的收盤價作為 y 座標
            match = df_display[df_display["date"] == cross_date]
            if match.empty:
                continue
            y_val = match.iloc[0][close_col]
            if pd.isna(y_val):
                continue

            is_golden = row["signal"] == "golden_cross"
            fig.add_trace(
                go.Scatter(
                    x=[cross_date],
                    y=[y_val],
                    mode="markers+text",
                    marker=dict(
                        symbol="triangle-up" if is_golden else "triangle-down",
                        size=14,
                        color="#10b981" if is_golden else "#ef4444",
                        line=dict(width=1, color="white"),
                    ),
                    text=["MA 金叉" if is_golden else "MA 死叉"],
                    textposition="top center" if is_golden else "bottom center",
                    textfont=dict(size=9, color="#10b981" if is_golden else "#ef4444"),
                    name="MA 金叉" if is_golden else "MA 死叉",
                    showlegend=False,
                ),
                row=1, col=1,
            )

    # MACD 交叉標記（也放在 K 線圖上）
    macd_crosses = detect_crossovers(df_full, "MACD_DIF", "MACD_DEA")
    if not macd_crosses.empty:
        display_start = dates.min()
        display_end = dates.max()
        macd_crosses_vis = macd_crosses[
            (macd_crosses["date"] >= display_start) & (macd_crosses["date"] <= display_end)
        ]
        for _, row in macd_crosses_vis.iterrows():
            cross_date = row["date"]
            match = df_display[df_display["date"] == cross_date]
            if match.empty:
                continue
            y_val = match.iloc[0][close_col]
            if pd.isna(y_val):
                continue

            is_golden = row["signal"] == "golden_cross"
            fig.add_trace(
                go.Scatter(
                    x=[cross_date],
                    y=[y_val],
                    mode="markers+text",
                    marker=dict(
                        symbol="diamond" if is_golden else "diamond",
                        size=10,
                        color="#059669" if is_golden else "#dc2626",
                        line=dict(width=1, color="white"),
                    ),
                    text=["MACD 金叉" if is_golden else "MACD 死叉"],
                    textposition="bottom center" if is_golden else "top center",
                    textfont=dict(size=9, color="#059669" if is_golden else "#dc2626"),
                    name="MACD 金叉" if is_golden else "MACD 死叉",
                    showlegend=False,
                ),
                row=1, col=1,
            )

    # ────────────────────────────────
    # Row 2：RSI
    # ────────────────────────────────
    if "RSI" in df_display.columns:
        rsi_vals = df_display["RSI"]

        fig.add_trace(
            go.Scatter(
                x=dates, y=rsi_vals,
                mode="lines",
                name="RSI(14)",
                line=dict(color="#8b5cf6", width=1.5),
            ),
            row=2, col=1,
        )

        # 超買超賣水平線
        fig.add_hline(y=70, line=dict(color="#ef4444", width=1, dash="dash"),
                      row=2, col=1)
        fig.add_hline(y=30, line=dict(color="#10b981", width=1, dash="dash"),
                      row=2, col=1)

        # 超買區域填色（70 以上）
        rsi_overbought = rsi_vals.copy()
        rsi_overbought[rsi_overbought < 70] = 70
        fig.add_trace(
            go.Scatter(
                x=dates, y=rsi_overbought,
                mode="lines", line=dict(width=0),
                showlegend=False, hoverinfo="skip",
            ),
            row=2, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=dates, y=[70] * len(dates),
                mode="lines", line=dict(width=0),
                fill="tonexty",
                fillcolor="rgba(239, 68, 68, 0.10)",
                showlegend=False, hoverinfo="skip",
            ),
            row=2, col=1,
        )

        # 超賣區域填色（30 以下）
        rsi_oversold = rsi_vals.copy()
        rsi_oversold[rsi_oversold > 30] = 30
        fig.add_trace(
            go.Scatter(
                x=dates, y=[30] * len(dates),
                mode="lines", line=dict(width=0),
                showlegend=False, hoverinfo="skip",
            ),
            row=2, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=dates, y=rsi_oversold,
                mode="lines", line=dict(width=0),
                fill="tonexty",
                fillcolor="rgba(16, 185, 129, 0.10)",
                showlegend=False, hoverinfo="skip",
            ),
            row=2, col=1,
        )

    # ────────────────────────────────
    # Row 3：MACD
    # ────────────────────────────────
    if "MACD_DIF" in df_display.columns:
        # DIF 線
        fig.add_trace(
            go.Scatter(
                x=dates, y=df_display["MACD_DIF"],
                mode="lines",
                name="DIF",
                line=dict(color="#3b82f6", width=1.5),
            ),
            row=3, col=1,
        )
        # DEA 線
        fig.add_trace(
            go.Scatter(
                x=dates, y=df_display["MACD_DEA"],
                mode="lines",
                name="DEA",
                line=dict(color="#f97316", width=1.5),
            ),
            row=3, col=1,
        )
        # 柱狀圖（正值綠、負值紅）
        hist = df_display["MACD_Hist"]
        colors = ["#10b981" if v >= 0 else "#ef4444" for v in hist]
        fig.add_trace(
            go.Bar(
                x=dates, y=hist,
                name="MACD 柱",
                marker_color=colors,
                opacity=0.6,
            ),
            row=3, col=1,
        )

    # ────────────────────────────────
    # 全域佈局
    # ────────────────────────────────
    fig.update_layout(
        height=900,
        margin=dict(l=10, r=10, t=40, b=60),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.05,
            xanchor="center",
            x=0.5,
            font=dict(size=10),
        ),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
    )

    # RSI y 軸範圍
    fig.update_yaxes(range=[0, 100], row=2, col=1, title_text="RSI")
    fig.update_yaxes(row=1, col=1, title_text="匯率")
    fig.update_yaxes(row=3, col=1, title_text="MACD")
    fig.update_xaxes(row=3, col=1, title_text="日期")

    return fig


# ══════════════════════════════════════
# 功能 3：RSI 儀表板
# ══════════════════════════════════════

def _build_rsi_gauge(rsi_val: float | None) -> go.Figure:
    """
    建構 RSI 儀表板（Gauge）。

    Parameters
    ----------
    rsi_val : float | None
        目前 RSI 值。

    Returns
    -------
    go.Figure
        Plotly Indicator Figure。
    """
    display_val = rsi_val if (rsi_val is not None and not np.isnan(rsi_val)) else 50

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=display_val,
            number={"font": {"size": 36}},
            gauge=dict(
                axis=dict(range=[0, 100], tickwidth=1),
                bar=dict(color="#6b7280"),
                steps=[
                    dict(range=[0, 30], color="#d1fae5"),    # 超賣 — 綠
                    dict(range=[30, 70], color="#fef9c3"),   # 中性 — 黃
                    dict(range=[70, 100], color="#fee2e2"),  # 超買 — 紅
                ],
                threshold=dict(
                    line=dict(color="#1f2937", width=3),
                    thickness=0.8,
                    value=display_val,
                ),
            ),
        )
    )
    fig.update_layout(
        height=250,
        margin=dict(l=30, r=30, t=30, b=60),
    )
    return fig


def _rsi_status_text(rsi_val: float | None) -> tuple[str, str]:
    """
    根據 RSI 值產生狀態文字與顏色。

    Parameters
    ----------
    rsi_val : float | None

    Returns
    -------
    tuple[str, str]
        (狀態文字, 顏色 hex)
    """
    if rsi_val is None or np.isnan(rsi_val):
        return "資料不足", "#6b7280"
    if rsi_val >= 70:
        return "超買 — 留意反轉風險", "#dc2626"
    elif rsi_val <= 30:
        return "超賣 — 可能存在買入機會", "#059669"
    else:
        return "中性", "#6b7280"


# ══════════════════════════════════════
# 主渲染函式
# ══════════════════════════════════════

def render() -> None:
    """渲染單一幣別分析頁面（主進入點）。"""
    st.title("🔍 單一幣別分析")

    # ────────────────────────────────
    # 頁面頂部選擇器
    # ────────────────────────────────
    sel_col1, sel_col2 = st.columns([2, 3])

    with sel_col1:
        options = ALL_CURRENCY_CODES
        labels = [f"{c} {CURRENCY_NAMES.get(c, c)}" for c in options]
        label_to_code = dict(zip(labels, options))

        selected_label = st.selectbox(
            "選擇貨幣",
            options=labels,
            index=0,
            key="analysis_currency",
        )
        code = label_to_code[selected_label]

    with sel_col2:
        period_label = st.radio(
            "時間範圍",
            options=list(PERIOD_OPTIONS.keys()),
            index=3,  # 預設「近一年」
            horizontal=True,
            key="analysis_period",
        )
        display_days = PERIOD_OPTIONS[period_label]

    # ────────────────────────────────
    # 載入資料 + 計算指標
    # ────────────────────────────────
    df_display, df_full, close_col = _load_and_compute(code, display_days)

    if df_display.empty:
        st.error(f"⚠️ 查無 {code} 的歷史匯率資料，請稍後再試或換一個幣別。")
        return

    st.caption(
        f"資料範圍：{df_display['date'].min().strftime('%Y-%m-%d')} ～ "
        f"{df_display['date'].max().strftime('%Y-%m-%d')}　"
        f"（共 {len(df_display)} 筆交易日資料）"
    )

    # ────────────────────────────────
    # 功能 5：訊號摘要卡片
    # ────────────────────────────────
    _render_signal_cards(df_display, close_col)
    st.markdown("")  # 間距

    # ────────────────────────────────
    # 功能 1–4：主圖表 + RSI 儀表板
    # ────────────────────────────────
    chart_col, gauge_col = st.columns([4, 1])

    with chart_col:
        fig = _build_main_chart(df_display, df_full, close_col, code)
        st.plotly_chart(
            fig,
            width='stretch',
            key=f"main_chart_{code}_{display_days}",
        )

    with gauge_col:
        st.markdown("#### RSI 儀表板")
        rsi_val = df_display.iloc[-1].get("RSI") if not df_display.empty else None
        gauge_fig = _build_rsi_gauge(rsi_val)
        st.plotly_chart(
            gauge_fig,
            width='stretch',
            key=f"rsi_gauge_{code}_{display_days}",
        )

        # RSI 狀態文字
        status_text, status_color = _rsi_status_text(rsi_val)
        st.markdown(
            f"<div style='text-align:center; padding:8px; "
            f"border-radius:6px; background:{status_color}22;'>"
            f"<span style='color:{status_color}; font-weight:600;'>"
            f"{status_text}</span></div>",
            unsafe_allow_html=True,
        )

        # 附加資訊
        if not df_display.empty:
            last = df_display.iloc[-1]
            dif = last.get("MACD_DIF")
            dea = last.get("MACD_DEA")
            ma20 = last.get("MA20")
            ma50 = last.get("MA50")

            st.markdown("---")
            st.markdown("##### 指標數值")
            info_lines = []
            if pd.notna(ma20):
                info_lines.append(f"MA20: {ma20:.4f}")
            if pd.notna(ma50):
                info_lines.append(f"MA50: {ma50:.4f}")
            if pd.notna(dif):
                info_lines.append(f"DIF: {dif:.6f}")
            if pd.notna(dea):
                info_lines.append(f"DEA: {dea:.6f}")
            if pd.notna(rsi_val):
                info_lines.append(f"RSI: {rsi_val:.1f}")

            for line in info_lines:
                st.caption(line)
