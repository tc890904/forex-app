"""
pages/overview.py — 匯率總覽頁

功能清單：
  1. 外匯集合分類切換（全部 / 主要 / 次要 / 亞太 / 地區別）
  2. 匯率卡片 + 7 日迷你走勢圖
  3. 自選觀察清單（優先顯示）
  4. 貨幣關聯熱力圖（主要貨幣 90 日 Pearson 相關）
  5. 貨幣強弱雷達圖（主要貨幣累計報酬率）
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from config import (
    ALL_CURRENCY_CODES,
    CURRENCY_CATEGORIES,
    REGION_CATEGORIES,
    CURRENCY_NAMES,
)
from data import get_history_rate
from sentiment import calc_technical_sentiment

# ──────────────────────────────────────
# 常數
# ──────────────────────────────────────
MAJOR_CODES: list[str] = CURRENCY_CATEGORIES["主要貨幣"]
CARDS_PER_ROW: int = 3
SPARKLINE_DAYS: int = 14  # 查 14 天以確保至少有 7 個營業日


# ══════════════════════════════════════
# 輔助函式
# ══════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def _load_short_history(code: str) -> pd.DataFrame:
    """
    載入單一幣別近期歷史（14 天），供卡片迷你走勢與漲跌幅使用。

    Parameters
    ----------
    code : str
        幣別代碼。

    Returns
    -------
    pd.DataFrame
        同 get_history_rate 回傳格式，已排序由舊到新。
    """
    return get_history_rate(code, days=SPARKLINE_DAYS)


def _pick_rate_column(df: pd.DataFrame) -> str | None:
    """
    判斷應使用哪個匯率欄位：優先 spot_sell，不足則 fallback 到 cash_sell。

    同時排除 None/NaN 與 0.0（API 回傳 0 代表無報價，非真實匯率）。

    Parameters
    ----------
    df : pd.DataFrame
        歷史匯率 DataFrame（含 spot_sell、cash_sell 欄位）。

    Returns
    -------
    str | None
        可用的欄位名稱（"spot_sell" 或 "cash_sell"），皆無有效值時回傳 None。
    """
    for col in ("spot_sell", "cash_sell"):
        if col in df.columns:
            # dropna 排除 NaN/None，再排除 0.0（代表無報價）
            valid = df[col].dropna()
            valid = valid[valid != 0.0]
            if len(valid) >= 1:
                return col
    return None


def _calc_change(df: pd.DataFrame) -> tuple[float | None, float | None, str]:
    """
    根據歷史資料計算最新匯率與日漲跌幅，自動選擇可用的匯率欄位。

    優先使用即期賣出（spot_sell），若無有效值則 fallback 到現金賣出（cash_sell）。

    Parameters
    ----------
    df : pd.DataFrame
        至少包含 spot_sell 或 cash_sell 欄位的歷史資料。

    Returns
    -------
    tuple[float | None, float | None, str]
        (最新匯率, 漲跌幅百分比, 匯率類型標籤)。
        匯率類型為 "即期賣出"、"現金賣出" 或 "暫無報價"。
    """
    col = _pick_rate_column(df)
    if col is None:
        return None, None, "暫無報價"

    rate_label = "即期賣出" if col == "spot_sell" else "現金賣出"
    # 排除 NaN 與 0.0（0 代表無報價）
    valid = df.dropna(subset=[col])
    valid = valid[valid[col] != 0.0]

    if len(valid) < 2:
        if len(valid) == 1:
            return valid.iloc[-1][col], None, rate_label
        return None, None, "暫無報價"

    latest = valid.iloc[-1][col]
    prev = valid.iloc[-2][col]
    if prev == 0:
        return latest, None, rate_label
    change_pct = (latest - prev) / prev * 100
    return latest, change_pct, rate_label


def _make_sparkline(df: pd.DataFrame, code: str) -> go.Figure | None:
    """
    產生 sparkline 風格的 7 日迷你走勢圖，自動選擇可用的匯率欄位。

    Parameters
    ----------
    df : pd.DataFrame
        包含 date 與匯率欄位的歷史資料。
    code : str
        幣別代碼，用於判斷漲跌配色。

    Returns
    -------
    go.Figure | None
        Plotly Figure 物件；資料不足時回傳 None。
    """
    col = _pick_rate_column(df)
    if col is None:
        return None

    # 排除 NaN 與 0.0，取最近 7 筆
    valid = df.dropna(subset=[col])
    valid = valid[valid[col] != 0.0].tail(7)
    if len(valid) < 2:
        return None

    # 判斷整體趨勢決定線條顏色
    first_val = valid.iloc[0][col]
    last_val = valid.iloc[-1][col]
    line_color = "#10b981" if last_val >= first_val else "#ef4444"

    # 相對基準線填色（勿用 tozeroy，匯率遠離 0 會整片填滿）
    baseline = float(valid[col].min())
    r, g, b = int(line_color[1:3], 16), int(line_color[3:5], 16), int(line_color[5:7], 16)
    fill_color = f"rgba({r},{g},{b},0.12)"

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=valid["date"],
            y=[baseline] * len(valid),
            mode="lines",
            line=dict(width=0),
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=valid["date"],
            y=valid[col],
            mode="lines",
            line=dict(color=line_color, width=1.5),
            fill="tonexty",
            fillcolor=fill_color,
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        height=50,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def _render_currency_card(code: str, context: str = "default") -> None:
    """
    渲染單一貨幣的資訊卡片，包含匯率、漲跌幅與迷你走勢圖。

    即期賣出無資料時自動 fallback 到現金賣出，並在卡片上標示匯率類型。
    兩者皆無資料時顯示「暫無報價」。

    Parameters
    ----------
    code : str
        幣別代碼。
    context : str
        呼叫情境標識，用於產生唯一的 Streamlit element key。
    """
    name = CURRENCY_NAMES.get(code, code)
    df = _load_short_history(code)

    # 計算匯率、漲跌幅、匯率類型
    rate_value, change_pct, rate_label = _calc_change(df)

    # 卡片容器
    with st.container(border=True):
        # 標題列：幣別代碼 + 中文名稱 + 技術面情緒
        sent = calc_technical_sentiment(df)
        sent_label = sent.get("label", "")
        st.markdown(f"**{code}** {name} {sent_label}")

        # 匯率（大字體）+ 匯率類型標籤
        if rate_value is not None:
            # 自適應小數位數：值越小需要越多位數才能有效顯示
            if rate_value >= 1:
                fmt = f"{rate_value:.4f}"
            elif rate_value >= 0.01:
                fmt = f"{rate_value:.4f}"
            elif rate_value >= 0.001:
                fmt = f"{rate_value:.5f}"
            else:
                fmt = f"{rate_value:.6f}"
            st.markdown(
                f"<span style='font-size:1.6rem; font-weight:700;'>{fmt}</span>"
                f"&nbsp;<span style='font-size:0.75rem; color:gray;'>{rate_label}</span>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<span style='font-size:1.2rem; color:orange;'>⚠ 暫無報價</span>",
                unsafe_allow_html=True,
            )

        # 漲跌幅
        if change_pct is not None:
            if change_pct > 0:
                arrow, color = "▲", "#10b981"
            elif change_pct < 0:
                arrow, color = "▼", "#ef4444"
            else:
                arrow, color = "＝", "#6b7280"
            st.markdown(
                f"<span style='color:{color}; font-size:0.9rem;'>"
                f"{arrow} {abs(change_pct):.2f}%</span>",
                unsafe_allow_html=True,
            )
        elif rate_value is not None:
            # 有匯率但只有一筆，無法算漲跌
            st.markdown(
                "<span style='color:gray; font-size:0.85rem;'>漲跌幅：僅一筆資料</span>",
                unsafe_allow_html=True,
            )
        else:
            # 完全無資料
            st.markdown(
                "<span style='color:gray; font-size:0.85rem;'>—</span>",
                unsafe_allow_html=True,
            )

        # 迷你走勢圖
        fig = _make_sparkline(df, code)
        if fig:
            st.plotly_chart(
                fig,
                width='stretch',
                config={"displayModeBar": False},
                key=f"sparkline_{context}_{code}",
            )


def _render_card_grid(codes: list[str], context: str = "default") -> None:
    """
    將多個貨幣卡片以每行 3 張的網格排列渲染。

    Parameters
    ----------
    codes : list[str]
        要顯示的幣別代碼清單。
    context : str
        情境標識，傳遞給每張卡片以產生唯一 key。
    """
    if not codes:
        st.info("此分類目前沒有貨幣。")
        return

    for i in range(0, len(codes), CARDS_PER_ROW):
        cols = st.columns(CARDS_PER_ROW)
        batch = codes[i : i + CARDS_PER_ROW]
        for j, code in enumerate(batch):
            with cols[j]:
                _render_currency_card(code, context=context)


# ══════════════════════════════════════
# 功能 4：貨幣關聯熱力圖
# ══════════════════════════════════════

@st.cache_data(ttl=600, show_spinner="正在計算貨幣關聯性...")
def _calc_correlation_matrix() -> pd.DataFrame | None:
    """
    取主要貨幣過去 90 天 spot_sell，計算 Pearson 相關係數矩陣。

    Returns
    -------
    pd.DataFrame | None
        相關係數矩陣；資料不足時回傳 None。
    """
    price_dict: dict[str, pd.Series] = {}
    for code in MAJOR_CODES:
        df = get_history_rate(code, days=90)
        valid = df.dropna(subset=["spot_sell"])
        if not valid.empty:
            series = valid.set_index("date")["spot_sell"]
            series.name = code
            price_dict[code] = series

    if len(price_dict) < 2:
        return None

    prices_df = pd.DataFrame(price_dict)
    # 以日期做內連接，確保各幣別對齊
    prices_df = prices_df.dropna()

    if len(prices_df) < 5:
        return None

    corr = prices_df.corr(method="pearson")
    return corr


def _render_heatmap() -> None:
    """渲染主要貨幣的 Pearson 相關係數熱力圖。"""
    corr = _calc_correlation_matrix()
    if corr is None:
        st.warning("歷史資料不足，無法計算相關係數。")
        return

    labels = [f"{c} {CURRENCY_NAMES.get(c, c)}" for c in corr.columns]

    fig = px.imshow(
        corr.values,
        x=labels,
        y=labels,
        color_continuous_scale="RdBu_r",  # 紅=正相關、藍=負相關
        zmin=-1,
        zmax=1,
        text_auto=".2f",
        aspect="auto",
    )
    fig.update_layout(
        title="主要貨幣 Pearson 相關係數（90 日）",
        height=500,
        margin=dict(l=20, r=20, t=50, b=20),
        coloraxis_colorbar=dict(title="相關係數"),
    )
    fig.update_traces(textfont_size=11)
    st.plotly_chart(fig, width='stretch', key="heatmap_correlation")


# ══════════════════════════════════════
# 功能 5：貨幣強弱雷達圖
# ══════════════════════════════════════

@st.cache_data(ttl=600, show_spinner="正在計算貨幣強弱指標...")
def _calc_returns(days: int) -> dict[str, float]:
    """
    計算主要貨幣在指定天數內的 spot_sell 累計報酬率（%）。

    Parameters
    ----------
    days : int
        回看天數（7 / 30 / 90）。

    Returns
    -------
    dict[str, float]
        {幣別代碼: 報酬率百分比}。資料不足的幣別不納入。
    """
    returns: dict[str, float] = {}
    for code in MAJOR_CODES:
        df = get_history_rate(code, days=days)
        valid = df.dropna(subset=["spot_sell"])
        if len(valid) >= 2:
            first_val = valid.iloc[0]["spot_sell"]
            last_val = valid.iloc[-1]["spot_sell"]
            if first_val != 0:
                returns[code] = (last_val - first_val) / first_val * 100
    return returns


def _render_radar(selected_period: int) -> None:
    """
    渲染貨幣強弱雷達圖。

    Parameters
    ----------
    selected_period : int
        選擇的期間天數（7 / 30 / 90）。
    """
    returns = _calc_returns(selected_period)
    if not returns:
        st.warning("歷史資料不足，無法繪製雷達圖。")
        return

    codes = list(returns.keys())
    values = list(returns.values())
    labels = [f"{c} {CURRENCY_NAMES.get(c, c)}" for c in codes]

    # 閉合雷達圖（首尾相連）
    labels_closed = labels + [labels[0]]
    values_closed = values + [values[0]]

    # 根據整體報酬方向決定填充色
    avg_return = np.mean(values)
    if avg_return >= 0:
        fill_color = "rgba(16, 185, 129, 0.15)"
        line_color = "#10b981"
    else:
        fill_color = "rgba(239, 68, 68, 0.15)"
        line_color = "#ef4444"

    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=values_closed,
            theta=labels_closed,
            fill="toself",
            fillcolor=fill_color,
            line=dict(color=line_color, width=2),
            name=f"{selected_period} 日報酬率",
            text=[f"{v:+.2f}%" for v in values_closed],
            hovertemplate="%{theta}<br>報酬率：%{text}<extra></extra>",
        )
    )

    # 加一個零線參考圈
    fig.add_trace(
        go.Scatterpolar(
            r=[0] * len(labels_closed),
            theta=labels_closed,
            mode="lines",
            line=dict(color="gray", width=0.5, dash="dot"),
            showlegend=False,
            hoverinfo="skip",
        )
    )

    period_label = {7: "7 日", 30: "30 日", 90: "90 日"}.get(selected_period, f"{selected_period} 日")
    fig.update_layout(
        title=f"主要貨幣強弱雷達圖（{period_label}累計報酬率 %）",
        polar=dict(
            radialaxis=dict(visible=True, showticklabels=True, ticksuffix="%"),
        ),
        height=500,
        margin=dict(l=40, r=40, t=60, b=40),
        showlegend=False,
    )
    st.plotly_chart(fig, width='stretch', key=f"radar_{selected_period}d")


# ══════════════════════════════════════
# 主渲染函式
# ══════════════════════════════════════

def render() -> None:
    """渲染匯率總覽頁面（主進入點）。"""
    st.title("📊 匯率總覽")
    st.caption("資料來源：台灣銀行牌告匯率（透過 FinMind API）｜快取 5 分鐘自動更新")

    # ────────────────────────────────
    # 功能 3：自選觀察清單（優先區塊）
    # ────────────────────────────────
    watchlist: list[str] = st.session_state.get("watchlist", [])
    if watchlist:
        st.subheader("⭐ 我的觀察清單")
        _render_card_grid(watchlist, context="watchlist")
        st.markdown("---")

    # ────────────────────────────────
    # 功能 1 & 2：分類 Tabs + 匯率卡片
    # ────────────────────────────────
    tab_all, tab_major, tab_minor, tab_asia, tab_region = st.tabs(
        ["全部", "主要貨幣", "次要貨幣", "亞太貨幣", "地區別"]
    )

    with tab_all:
        with st.spinner("正在載入全部匯率..."):
            _render_card_grid(ALL_CURRENCY_CODES, context="all")

    with tab_major:
        _render_card_grid(CURRENCY_CATEGORIES["主要貨幣"], context="major")

    with tab_minor:
        _render_card_grid(CURRENCY_CATEGORIES["次要貨幣"], context="minor")

    with tab_asia:
        _render_card_grid(CURRENCY_CATEGORIES["亞太貨幣"], context="asia")

    with tab_region:
        region_tabs = st.tabs(list(REGION_CATEGORIES.keys()))
        for region_tab, (region_name, region_codes) in zip(
            region_tabs, REGION_CATEGORIES.items()
        ):
            with region_tab:
                _render_card_grid(region_codes, context=f"region_{region_name}")

    # ────────────────────────────────
    # 功能 4 & 5：進階分析區
    # ────────────────────────────────
    st.markdown("---")
    with st.expander("📈 貨幣關聯性分析", expanded=False):
        col_heat, col_radar = st.columns(2)

        with col_heat:
            _render_heatmap()

        with col_radar:
            period = st.radio(
                "選擇觀察期間",
                options=[7, 30, 90],
                format_func=lambda x: {7: "7 日", 30: "30 日", 90: "90 日"}[x],
                horizontal=True,
                key="radar_period",
            )
            _render_radar(period)
