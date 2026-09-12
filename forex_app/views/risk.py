"""
views/risk.py — 風控計算器頁

功能清單：
  1. ATR 動態停損計算器 + 價位圖
  2. 風險報酬比視覺化
  3. 凱利公式倉位建議
  4. 槓桿風險儀表板
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import ALL_CURRENCY_CODES, CURRENCY_NAMES
from data import get_history_rate, get_latest_rate
from indicators import pick_close_column
from risk_calc import calc_atr, calc_stop_levels, calc_kelly, calc_leverage_risk


# ──────────────────────────────────────
# 輔助函式
# ──────────────────────────────────────

def _get_current_price(code: str) -> float | None:
    """
    取得幣別目前匯率（即期賣出優先，fallback 現金賣出）。

    Parameters
    ----------
    code : str
        幣別代碼。

    Returns
    -------
    float | None
    """
    rate = get_latest_rate(code)
    if rate is None:
        return None
    return rate.get("spot_sell") or rate.get("cash_sell")


@st.cache_data(ttl=300, show_spinner="正在計算 ATR...")
def _get_atr_value(code: str) -> float | None:
    """
    取得幣別目前的 14 日 ATR 值。

    Parameters
    ----------
    code : str

    Returns
    -------
    float | None
    """
    df = get_history_rate(code, days=60)
    if df.empty or len(df) < 20:
        return None
    df_atr = calc_atr(df, period=14)
    last_atr = df_atr["ATR"].dropna()
    if last_atr.empty:
        return None
    return float(last_atr.iloc[-1])


# ══════════════════════════════════════
# 功能 1：ATR 動態停損計算器
# ══════════════════════════════════════

def _render_atr_stoploss(code: str, current_price: float | None) -> None:
    """
    渲染 ATR 動態停損計算器。

    Parameters
    ----------
    code : str
        幣別代碼。
    current_price : float | None
        目前匯率。
    """
    st.subheader("📐 ATR 動態停損計算器")

    atr_val = _get_atr_value(code)
    if atr_val is None:
        st.warning(f"⚠️ {code} 資料不足，無法計算 ATR。")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        default_price = round(current_price, 4) if current_price else 30.0
        entry_price = st.number_input(
            "進場價位",
            min_value=0.0001,
            value=default_price,
            format="%.4f",
            key="risk_entry_price",
        )
    with col2:
        direction = st.radio(
            "交易方向",
            options=["做多", "做空"],
            horizontal=True,
            key="risk_direction",
        )
    with col3:
        atr_mult = st.slider(
            "ATR 倍數",
            min_value=1.0,
            max_value=3.0,
            value=1.5,
            step=0.5,
            key="risk_atr_mult",
        )

    dir_str = "long" if direction == "做多" else "short"
    rr_ratio = st.session_state.get("risk_rr_ratio", 2.0)
    levels = calc_stop_levels(entry_price, atr_val, atr_mult, rr_ratio, dir_str)

    # 顯示結果指標
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("14 日 ATR", f"{atr_val:.6f}")
    m2.metric("建議停損", f"{levels['stop_loss']:.4f}", f"-{levels['stop_pct']:.2f}%")
    m3.metric("建議停利", f"{levels['take_profit']:.4f}", f"+{levels['profit_pct']:.2f}%")
    m4.metric("停損點數", f"{levels['stop_distance']:.6f}")

    # 價位圖
    _render_level_chart(entry_price, levels, current_price, dir_str)


def _render_level_chart(
    entry: float,
    levels: dict,
    current: float | None,
    direction: str,
) -> None:
    """
    繪製停損停利水平價位圖。

    Parameters
    ----------
    entry : float
        進場價。
    levels : dict
        calc_stop_levels 的回傳值。
    current : float | None
        目前市價。
    direction : str
        "long" 或 "short"。
    """
    sl = levels["stop_loss"]
    tp = levels["take_profit"]

    points = [("停損", sl, "#ef4444"), ("進場", entry, "#3b82f6"), ("停利", tp, "#10b981")]
    if current:
        points.append(("目前", current, "#f59e0b"))
    points.sort(key=lambda x: x[1])

    fig = go.Figure()
    for label, price, color in points:
        fig.add_trace(go.Scatter(
            x=[price], y=[0],
            mode="markers+text",
            marker=dict(size=16, color=color, symbol="diamond"),
            text=[f"{label}<br>{price:.4f}"],
            textposition="top center",
            textfont=dict(size=11, color=color),
            name=label,
            showlegend=False,
        ))

    # 停損停利區域
    if direction == "long":
        fig.add_vrect(x0=sl, x1=entry, fillcolor="rgba(239,68,68,0.08)",
                      line_width=0, annotation_text="虧損區", annotation_position="bottom left")
        fig.add_vrect(x0=entry, x1=tp, fillcolor="rgba(16,185,129,0.08)",
                      line_width=0, annotation_text="獲利區", annotation_position="bottom right")
    else:
        fig.add_vrect(x0=entry, x1=sl, fillcolor="rgba(239,68,68,0.08)",
                      line_width=0, annotation_text="虧損區", annotation_position="bottom right")
        fig.add_vrect(x0=tp, x1=entry, fillcolor="rgba(16,185,129,0.08)",
                      line_width=0, annotation_text="獲利區", annotation_position="bottom left")

    fig.update_layout(
        height=200,
        margin=dict(l=10, r=10, t=40, b=10),
        yaxis=dict(visible=False, range=[-0.5, 0.5]),
        xaxis=dict(title="匯率"),
        title="停損 / 停利 價位圖",
    )
    st.plotly_chart(fig, width='stretch', key="level_chart")


# ══════════════════════════════════════
# 功能 2：風險報酬比視覺化
# ══════════════════════════════════════

def _render_risk_reward() -> None:
    """渲染風險報酬比視覺化。"""
    st.subheader("⚖️ 風險報酬比視覺化")

    rr = st.slider(
        "風險報酬比",
        min_value=1.0,
        max_value=5.0,
        value=2.0,
        step=0.5,
        format="1:%.1f",
        key="risk_rr_ratio",
    )

    risk_amount = 1.0
    reward_amount = rr

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=[""],
        x=[-risk_amount],
        orientation="h",
        name="潛在虧損",
        marker_color="#ef4444",
        text=[f"虧損 {risk_amount:.1f} 元（100%）"],
        textposition="inside",
        textfont=dict(color="white", size=13),
    ))
    fig.add_trace(go.Bar(
        y=[""],
        x=[reward_amount],
        orientation="h",
        name="潛在獲利",
        marker_color="#10b981",
        text=[f"獲利 {reward_amount:.1f} 元（{rr*100:.0f}%）"],
        textposition="inside",
        textfont=dict(color="white", size=13),
    ))
    fig.update_layout(
        barmode="relative",
        height=120,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=False,
    )
    st.plotly_chart(fig, width='stretch', key="rr_chart")
    st.markdown(
        f"📌 每承擔 **1 元**風險，預期可獲得 **{rr:.1f} 元**報酬。"
    )


# ══════════════════════════════════════
# 功能 3：凱利公式倉位建議
# ══════════════════════════════════════

def _render_kelly() -> None:
    """渲染凱利公式倉位建議。"""
    st.subheader("🎯 凱利公式倉位建議")

    c1, c2, c3 = st.columns(3)
    with c1:
        win_rate_pct = st.number_input(
            "歷史勝率（%）",
            min_value=0.0,
            max_value=100.0,
            value=50.0,
            step=5.0,
            key="kelly_win_rate",
        )
    with c2:
        payoff = st.number_input(
            "平均盈虧比",
            min_value=0.1,
            max_value=10.0,
            value=2.0,
            step=0.1,
            key="kelly_payoff",
        )
    with c3:
        capital = st.number_input(
            "總資金（USD）",
            min_value=100.0,
            value=10000.0,
            step=1000.0,
            key="kelly_capital",
        )

    result = calc_kelly(win_rate_pct / 100.0, payoff, capital)

    if not result["is_viable"]:
        st.error("⚠️ 目前勝率與盈虧比組合不適合交易，凱利值為負。建議暫停並檢視策略。")

    # Gauge
    gauge_val = max(0, min(100, result["kelly_pct"]))
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=gauge_val,
        number={"suffix": "%", "font": {"size": 32}},
        gauge=dict(
            axis=dict(range=[0, 100]),
            bar=dict(color="#3b82f6"),
            steps=[
                dict(range=[0, 25], color="#d1fae5"),
                dict(range=[25, 50], color="#fef9c3"),
                dict(range=[50, 100], color="#fee2e2"),
            ],
        ),
    ))
    fig.update_layout(height=230, margin=dict(l=30, r=30, t=30, b=10))

    g_col, info_col = st.columns([1, 1])
    with g_col:
        st.plotly_chart(fig, width='stretch', key="kelly_gauge")
    with info_col:
        if result["is_viable"]:
            st.metric("凱利建議比例", f'{result["kelly_pct"]:.1f}%')
            st.metric("凱利建議金額", f'${result["kelly_amount"]:,.0f}')
            st.metric("保守建議（Half-Kelly）", f'{result["half_kelly_pct"]:.1f}%  /  ${result["half_kelly_amount"]:,.0f}')
            st.caption("💡 實務上建議使用 Half-Kelly，降低資金曲線波動。")
        else:
            st.metric("凱利值", f'{result["kelly_pct"]:.1f}%')
            st.caption("凱利值為負代表期望值為負，長期交易必然虧損。")


# ══════════════════════════════════════
# 功能 4：槓桿風險儀表板
# ══════════════════════════════════════

def _render_leverage(code: str, current_price: float | None) -> None:
    """
    渲染槓桿風險儀表板。

    Parameters
    ----------
    code : str
        幣別代碼。
    current_price : float | None
        目前匯率。
    """
    st.subheader("⚡ 槓桿風險儀表板")

    c1, c2 = st.columns(2)
    with c1:
        lev_capital = st.number_input(
            "本金（USD）",
            min_value=100.0,
            value=10000.0,
            step=1000.0,
            key="lev_capital",
        )
    with c2:
        leverage = st.select_slider(
            "槓桿倍數",
            options=[1, 5, 10, 20, 50, 100],
            value=20,
            key="lev_leverage",
        )

    atr_val = _get_atr_value(code)
    result = calc_leverage_risk(
        lev_capital, leverage, atr_val, current_price,
    )

    # Gauge — 保證金維持率
    mr = result["margin_ratio"]
    if mr >= 100:
        gauge_color = "#10b981"
    elif mr >= 50:
        gauge_color = "#f59e0b"
    else:
        gauge_color = "#ef4444"

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=mr,
        number={"suffix": "%", "font": {"size": 32}},
        gauge=dict(
            axis=dict(range=[0, 200]),
            bar=dict(color=gauge_color),
            steps=[
                dict(range=[0, 50], color="#fee2e2"),
                dict(range=[50, 100], color="#fef9c3"),
                dict(range=[100, 200], color="#d1fae5"),
            ],
            threshold=dict(line=dict(color="red", width=3), thickness=0.8, value=50),
        ),
        title={"text": "保證金維持率"},
    ))
    fig.update_layout(height=260, margin=dict(l=30, r=30, t=50, b=10))

    g_col, info_col = st.columns([1, 1])
    with g_col:
        st.plotly_chart(fig, width='stretch', key="lev_gauge")

    with info_col:
        st.metric("持倉市值", f'${result["position_value"]:,.0f}')
        st.metric("已用保證金", f'${result["used_margin"]:,.0f}')
        st.metric("強平波動距離", f'{result["liquidation_move_pct"]:.2f}%')

        # 風險等級標示
        risk = result["risk_level"]
        risk_colors = {"低": "#10b981", "中": "#f59e0b", "高": "#ef4444", "極高": "#991b1b"}
        rc = risk_colors.get(risk, "#6b7280")
        st.markdown(
            f"<span style='background:{rc}; color:white; padding:4px 12px; "
            f"border-radius:4px; font-weight:600;'>風險等級：{risk}</span>",
            unsafe_allow_html=True,
        )

    # 文字摘要
    liq_pct = result["liquidation_move_pct"]
    atr_days = result.get("atr_days_to_liquidation")
    summary = f"目前槓桿 {leverage} 倍，價格只要反向波動約 **{liq_pct:.2f}%** 即會觸發強制平倉。"
    if atr_days is not None and atr_days > 0:
        summary += f" 以目前 ATR 估算，約 **{atr_days:.1f}** 個交易日的平均波動即可觸達。"
    st.info(summary)


# ══════════════════════════════════════
# 主渲染函式
# ══════════════════════════════════════

def render() -> None:
    """渲染風控計算器頁面（主進入點）。"""
    st.title("🛡️ 風控計算器")
    st.caption("提供 ATR 動態停損、風險報酬比、凱利公式、槓桿風險等實用工具")

    # ── 幣別選擇（全頁共用） ──
    labels = [f"{c} {CURRENCY_NAMES.get(c, c)}" for c in ALL_CURRENCY_CODES]
    label_to_code = dict(zip(labels, ALL_CURRENCY_CODES))
    selected_label = st.selectbox(
        "選擇交易貨幣",
        options=labels,
        index=0,
        key="risk_currency",
    )
    code = label_to_code[selected_label]
    current_price = _get_current_price(code)

    if current_price:
        st.caption(f"💰 {code}/TWD 目前匯率：{current_price:.4f}")
    else:
        st.warning(f"⚠️ 無法取得 {code} 的最新匯率。")

    st.markdown("---")

    # ── 功能 1 & 2 ──
    _render_atr_stoploss(code, current_price)
    st.markdown("")
    _render_risk_reward()

    st.markdown("---")

    # ── 功能 3 ──
    _render_kelly()

    st.markdown("---")

    # ── 功能 4 ──
    _render_leverage(code, current_price)
