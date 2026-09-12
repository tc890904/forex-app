"""
views/research.py — 回測與研究頁

功能清單：
  A. 簡易回測摘要（MA 交叉策略 + ATR 停損停利）
     - 交易紀錄表格
     - 績效摘要卡片
     - 權益曲線圖
     - 每月報酬率熱力圖
  B. 技術面情緒標籤總覽
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from config import ALL_CURRENCY_CODES, CURRENCY_NAMES
from data import get_history_rate
from backtest import run_ma_cross_backtest
from sentiment import batch_sentiment


# ──────────────────────────────────────
# 常數
# ──────────────────────────────────────
EXTRA_LOOKBACK: int = 300  # 額外回看天數供 MA200 計算


# ══════════════════════════════════════
# Part A：回測
# ══════════════════════════════════════

def _render_backtest() -> None:
    """渲染回測區塊。"""
    st.subheader("📈 MA 交叉策略回測")
    st.caption("進場：MA20 上穿 MA50（金叉）｜出場：死叉 / ATR 停損 / ATR 停利（先到先觸發）")

    # ── 使用者輸入 ──
    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
    with c1:
        labels = [f"{c} {CURRENCY_NAMES.get(c, c)}" for c in ALL_CURRENCY_CODES]
        label_to_code = dict(zip(labels, ALL_CURRENCY_CODES))
        selected = st.selectbox("選擇貨幣", labels, index=0, key="bt_currency")
        code = label_to_code[selected]
    with c2:
        today = datetime.today().date()
        one_year_ago = today - timedelta(days=365)
        date_range = st.date_input(
            "回測區間",
            value=(one_year_ago, today),
            key="bt_dates",
        )
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            start_d, end_d = date_range
        else:
            start_d, end_d = one_year_ago, today
    with c3:
        sl_mult = st.slider("停損 ATR 倍數", 1.0, 3.0, 1.5, 0.5, key="bt_sl")
    with c4:
        tp_mult = st.slider("停利 ATR 倍數", 1.5, 5.0, 3.0, 0.5, key="bt_tp")

    # ── 執行回測 ──
    total_days = (end_d - start_d).days + EXTRA_LOOKBACK
    with st.spinner("正在執行回測..."):
        df_raw = get_history_rate(code, days=total_days)
        result = run_ma_cross_backtest(
            df_raw,
            start_date=datetime.combine(start_d, datetime.min.time()),
            end_date=datetime.combine(end_d, datetime.min.time()),
            atr_sl_mult=sl_mult,
            atr_tp_mult=tp_mult,
        )

    trades = result["trades"]
    summary = result["summary"]
    equity = result["equity_curve"]

    if trades.empty:
        st.info("📭 回測期間內沒有觸發任何交易訊號。可嘗試延長回測區間或換一個幣別。")
        return

    # ── 績效摘要卡片 ──
    st.markdown("#### 績效摘要")
    m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    m1.metric("總交易次數", f'{summary["total_trades"]}')
    m2.metric("勝率", f'{summary["win_rate"]:.1f}%')
    m3.metric("平均報酬", f'{summary["avg_return"]:.2f}%')
    m4.metric("累計報酬", f'{summary["cum_return"]:.2f}%')
    m5.metric("最大單筆虧損", f'{summary["max_loss"]:.2f}%')
    m6.metric("最大連虧次數", f'{summary["max_consec_loss"]}')
    m7.metric("最大回撤", f'{summary["max_drawdown"]:.2f}%')

    # ── 權益曲線 ──
    st.markdown("#### 權益曲線")
    if not equity.empty:
        fig_eq = go.Figure()
        # 使用相對基準線填色（初始資金 10000）
        baseline = 10000.0
        fig_eq.add_trace(go.Scatter(
            x=equity["date"], y=[baseline] * len(equity),
            mode="lines", line=dict(width=0),
            hoverinfo="skip", showlegend=False,
        ))
        fig_eq.add_trace(go.Scatter(
            x=equity["date"], y=equity["equity"],
            mode="lines+markers",
            line=dict(color="#3b82f6", width=2),
            marker=dict(size=4),
            name="權益",
            fill="tonexty",
            fillcolor="rgba(59,130,246,0.12)",
        ))
        fig_eq.add_hline(y=10000, line=dict(color="gray", dash="dash", width=1))
        fig_eq.update_layout(
            height=350,
            margin=dict(l=10, r=10, t=10, b=10),
            yaxis_title="資產（USD）",
            xaxis_title="日期",
            hovermode="x unified",
        )
        st.plotly_chart(fig_eq, width='stretch', key="equity_curve")

    # ── 交易紀錄 + 每月報酬率 ──
    col_trades, col_heatmap = st.columns([1, 1])

    with col_trades:
        st.markdown("#### 交易紀錄")
        display_trades = trades.copy()
        display_trades["進場日"] = pd.to_datetime(display_trades["進場日"]).dt.strftime("%Y-%m-%d")
        display_trades["出場日"] = pd.to_datetime(display_trades["出場日"]).dt.strftime("%Y-%m-%d")
        display_trades["進場價"] = display_trades["進場價"].apply(lambda x: f"{x:.4f}")
        display_trades["出場價"] = display_trades["出場價"].apply(lambda x: f"{x:.4f}")
        display_trades["損益"] = display_trades["損益"].apply(lambda x: f"{x:+.6f}")
        display_trades["報酬率(%)"] = display_trades["報酬率(%)"].apply(lambda x: f"{x:+.2f}%")
        st.dataframe(display_trades, width='stretch', hide_index=True)

    with col_heatmap:
        st.markdown("#### 每月報酬率")
        _render_monthly_heatmap(trades)


def _render_monthly_heatmap(trades: pd.DataFrame) -> None:
    """
    繪製每月報酬率熱力圖。

    Parameters
    ----------
    trades : pd.DataFrame
        交易紀錄 DataFrame。
    """
    if trades.empty:
        st.info("無交易紀錄。")
        return

    df = trades.copy()
    df["出場日"] = pd.to_datetime(df["出場日"])
    df["year"] = df["出場日"].dt.year
    df["month"] = df["出場日"].dt.month

    # 每月平均報酬率
    monthly = df.groupby(["year", "month"])["報酬率(%)"].mean().reset_index()
    pivot = monthly.pivot(index="year", columns="month", values="報酬率(%)")
    pivot = pivot.reindex(columns=range(1, 13))
    pivot.columns = [f"{m}月" for m in range(1, 13)]

    fig = px.imshow(
        pivot.values,
        x=list(pivot.columns),
        y=[str(y) for y in pivot.index],
        color_continuous_scale="RdYlGn",
        text_auto=".2f",
        aspect="auto",
        labels={"color": "報酬率(%)"},
    )
    fig.update_layout(
        height=max(200, len(pivot) * 60 + 80),
        margin=dict(l=10, r=10, t=10, b=10),
    )
    st.plotly_chart(fig, width='stretch', key="monthly_heatmap")


# ══════════════════════════════════════
# Part B：技術面情緒總覽
# ══════════════════════════════════════

def _render_sentiment_overview() -> None:
    """渲染技術面情緒總覽區塊。"""
    st.subheader("🧠 技術面情緒總覽")
    st.caption(
        "基於 MA 趨勢 + RSI + MACD 的綜合技術面情緒指標。"
        "此為技術面分析結果，非新聞情緒。"
    )

    with st.spinner("正在計算各幣別技術面情緒..."):
        sentiments = batch_sentiment(
            ALL_CURRENCY_CODES,
            get_history_rate,
            days=90,
        )

    # 建立表格
    rows = []
    for code in ALL_CURRENCY_CODES:
        s = sentiments.get(code, {})
        rows.append({
            "幣別": f"{code} {CURRENCY_NAMES.get(code, code)}",
            "情緒": s.get("label", "⚪"),
            "判定": s.get("text", "—"),
            "得分": s.get("score", 0),
        })

    df_sent = pd.DataFrame(rows)
    df_sent = df_sent.sort_values("得分", ascending=False).reset_index(drop=True)

    # 統計
    bullish = sum(1 for r in rows if r["得分"] > 0)
    bearish = sum(1 for r in rows if r["得分"] < 0)
    neutral = sum(1 for r in rows if r["得分"] == 0)

    s1, s2, s3 = st.columns(3)
    s1.metric("🟢 偏多", f"{bullish} 幣別")
    s2.metric("⚪ 中性", f"{neutral} 幣別")
    s3.metric("🔴 偏空", f"{bearish} 幣別")

    st.dataframe(df_sent, width='stretch', hide_index=True)


# ══════════════════════════════════════
# 主渲染函式
# ══════════════════════════════════════

def render() -> None:
    """渲染回測與研究頁面（主進入點）。"""
    st.title("🧪 回測與研究")

    _render_backtest()

    st.markdown("---")

    _render_sentiment_overview()

    st.caption("⚠️ 回測績效不代表未來實際報酬，技術面情緒僅供參考，不構成投資建議。")
