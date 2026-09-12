"""
app.py — Streamlit 應用程式進入點

負責頁面配置、sidebar 導航、頁面路由與免責聲明。
啟動方式：streamlit run app.py
"""

import streamlit as st

from config import PAGE_CONFIG, DISCLAIMER
from views import overview, analysis, signals, risk, research

# ──────────────────────────────────────
# 頁面基本設定
# ──────────────────────────────────────
st.set_page_config(
    page_title="智慧外匯行情與動態風控系統",
    page_icon="💱",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────
# 頁面路由對照表
# ──────────────────────────────────────
PAGE_MODULES: dict = {
    "overview": overview,
    "analysis": analysis,
    "signals": signals,
    "risk": risk,
    "research": research,
}

# ──────────────────────────────────────
# 初始化 session state
# ──────────────────────────────────────
if "current_page" not in st.session_state:
    st.session_state.current_page = "overview"


def _switch_page(page_key: str) -> None:
    """切換當前頁面的回呼函式。"""
    st.session_state.current_page = page_key


# ──────────────────────────────────────
# Sidebar
# ──────────────────────────────────────
with st.sidebar:
    st.header("💱 智慧外匯行情與動態風控系統")
    st.markdown("---")

    # 導航按鈕
    for page in PAGE_CONFIG:
        is_active = st.session_state.current_page == page["key"]
        button_type = "primary" if is_active else "secondary"
        st.button(
            page["label"],
            key=f"nav_{page['key']}",
            on_click=_switch_page,
            args=(page["key"],),
            width='stretch',
            type=button_type,
        )

    # 自選觀察清單
    st.markdown("---")
    st.subheader("⭐ 我的觀察清單")
    if "watchlist" not in st.session_state:
        st.session_state.watchlist = []

    # 建立選項標籤：「USD 美元」格式
    from config import ALL_CURRENCY_CODES, CURRENCY_NAMES
    watchlist_options = {f"{c} {CURRENCY_NAMES.get(c, c)}": c for c in ALL_CURRENCY_CODES}
    # 反向對照：從 session_state 中的代碼還原為顯示標籤
    current_labels = [
        f"{c} {CURRENCY_NAMES.get(c, c)}"
        for c in st.session_state.watchlist
        if c in ALL_CURRENCY_CODES
    ]
    selected_labels = st.multiselect(
        "選擇幣別加入觀察清單",
        options=list(watchlist_options.keys()),
        default=current_labels,
        key="watchlist_selector",
        placeholder="搜尋並選擇幣別...",
    )
    # 將選擇結果轉回代碼，存入 session_state
    st.session_state.watchlist = [watchlist_options[lbl] for lbl in selected_labels]

    # 底部免責聲明
    st.markdown("---")
    st.caption("⚠️ 免責聲明")
    st.caption(DISCLAIMER)

# ──────────────────────────────────────
# 首頁摘要列
# ──────────────────────────────────────
from data import get_history_rate
from views.overview import _load_short_history, _calc_change, _pick_rate_column
from config import ALL_CURRENCY_CODES, CURRENCY_NAMES

@st.cache_data(ttl=300, show_spinner=False)
def _top_summary():
    """計算首頁摘要指標：最強勢 / 最弱勢幣別 + 有訊號的幣別數。"""
    changes: list[tuple[str, float]] = []
    for code in ALL_CURRENCY_CODES:
        try:
            df = _load_short_history(code)
            _, change_pct, _ = _calc_change(df)
            if change_pct is not None:
                changes.append((code, change_pct))
        except Exception:
            pass
    if not changes:
        return None, None, 0
    changes.sort(key=lambda x: x[1], reverse=True)
    strongest = changes[0]
    weakest = changes[-1]
    signal_count = sum(1 for _, c in changes if abs(c) > 0.1)
    return strongest, weakest, signal_count

try:
    strongest, weakest, sig_count = _top_summary()
    s1, s2, s3 = st.columns(3)
    if strongest:
        s1.metric(
            f"📈 今日最強 — {strongest[0]} {CURRENCY_NAMES.get(strongest[0], '')}",
            f"{strongest[1]:+.2f}%",
        )
    if weakest:
        s2.metric(
            f"📉 今日最弱 — {weakest[0]} {CURRENCY_NAMES.get(weakest[0], '')}",
            f"{weakest[1]:+.2f}%",
        )
    s3.metric("📡 顯著波動幣別", f"{sig_count} 種")
    st.markdown("---")
except Exception:
    pass  # 首頁摘要非關鍵，失敗不影響頁面

# ──────────────────────────────────────
# 主內容區：根據 session state 渲染對應頁面
# ──────────────────────────────────────
current = st.session_state.current_page
module = PAGE_MODULES.get(current)

if module and hasattr(module, "render"):
    module.render()
else:
    st.error(f"找不到頁面模組：{current}")
