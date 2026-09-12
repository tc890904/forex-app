"""
views/signals.py — 技術指標與訊號頁

多指標綜合訊號面板：
  - 5 項條件評分（MA 趨勢、MA 交叉、RSI、MACD、布林位置）
  - 綜合判定 + 自動文字摘要
  - 多幣別比較模式
"""

from datetime import timedelta

import numpy as np
import pandas as pd
import streamlit as st

from config import ALL_CURRENCY_CODES, CURRENCY_NAMES
from data import get_history_rate
from indicators import (
    pick_close_column,
    calc_all_indicators,
    detect_crossovers,
)
from sentiment import calc_technical_sentiment


# ──────────────────────────────────────
# 常數
# ──────────────────────────────────────
EXTRA_LOOKBACK: int = 250  # 額外回看天數（供 MA200 計算）


# ══════════════════════════════════════
# 評分邏輯
# ══════════════════════════════════════

def _score_single_currency(code: str) -> dict | None:
    """
    計算單一幣別的 5 項指標評分。

    Parameters
    ----------
    code : str
        幣別代碼。

    Returns
    -------
    dict | None
        包含各項指標數值、判定、得分的字典；資料不足時回傳 None。
    """
    df_raw = get_history_rate(code, days=365 + EXTRA_LOOKBACK)
    if df_raw.empty or len(df_raw) < 30:
        return None

    close_col = pick_close_column(df_raw)
    df = calc_all_indicators(df_raw)

    if df.empty:
        return None

    last = df.iloc[-1]
    items: list[dict] = []
    total_score = 0

    # --- 1. MA 趨勢 ---
    ma20 = last.get("MA20")
    ma50 = last.get("MA50")
    if pd.notna(ma20) and pd.notna(ma50):
        if ma20 > ma50:
            score, verdict = 1, "偏多"
        elif ma20 < ma50:
            score, verdict = -1, "偏空"
        else:
            score, verdict = 0, "中性"
        val_text = f"MA20={ma20:.4f}  MA50={ma50:.4f}"
    else:
        score, verdict, val_text = 0, "資料不足", "—"
    items.append({"條件": "MA 趨勢", "數值": val_text, "判定": verdict, "得分": score})
    total_score += score

    # --- 2. MA 交叉（近 5 日） ---
    crosses = detect_crossovers(df, "MA20", "MA50")
    if not crosses.empty:
        cutoff = df["date"].max() - timedelta(days=5)
        recent = crosses[crosses["date"] >= cutoff]
        if not recent.empty:
            last_cross = recent.iloc[-1]
            if last_cross["signal"] == "golden_cross":
                score, verdict = 1, "近期金叉"
            else:
                score, verdict = -1, "近期死叉"
            val_text = f'{last_cross["date"].strftime("%m/%d")} {verdict}'
        else:
            score, verdict, val_text = 0, "無近期交叉", "—"
    else:
        score, verdict, val_text = 0, "無交叉", "—"
    items.append({"條件": "MA 交叉", "數值": val_text, "判定": verdict, "得分": score})
    total_score += score

    # --- 3. RSI ---
    rsi = last.get("RSI")
    if pd.notna(rsi):
        if rsi < 30:
            score, verdict = 1, "超賣反彈機會"
        elif rsi > 70:
            score, verdict = -1, "超買回落風險"
        else:
            score, verdict = 0, "中性"
        val_text = f"{rsi:.1f}"
    else:
        score, verdict, val_text = 0, "資料不足", "—"
    items.append({"條件": "RSI", "數值": val_text, "判定": verdict, "得分": score})
    total_score += score

    # --- 4. MACD ---
    dif = last.get("MACD_DIF")
    dea = last.get("MACD_DEA")
    hist = last.get("MACD_Hist")
    if pd.notna(dif) and pd.notna(dea) and pd.notna(hist):
        if dif > dea and hist > 0:
            score, verdict = 1, "動能偏多"
        elif dif < dea and hist < 0:
            score, verdict = -1, "動能偏空"
        else:
            score, verdict = 0, "中性"
        val_text = f"DIF={dif:.6f}  DEA={dea:.6f}"
    else:
        score, verdict, val_text = 0, "資料不足", "—"
    items.append({"條件": "MACD", "數值": val_text, "判定": verdict, "得分": score})
    total_score += score

    # --- 5. 布林位置 ---
    close_val = last.get(close_col)
    bb_upper = last.get("BB_upper")
    bb_lower = last.get("BB_lower")
    if pd.notna(close_val) and pd.notna(bb_upper) and pd.notna(bb_lower):
        if close_val < bb_lower:
            score, verdict = 1, "低於下軌，可能反彈"
        elif close_val > bb_upper:
            score, verdict = -1, "高於上軌，可能回落"
        else:
            score, verdict = 0, "通道內"
        val_text = f"價格={close_val:.4f}  上軌={bb_upper:.4f}  下軌={bb_lower:.4f}"
    else:
        score, verdict, val_text = 0, "資料不足", "—"
    items.append({"條件": "布林位置", "數值": val_text, "判定": verdict, "得分": score})
    total_score += score

    return {
        "code": code,
        "name": CURRENCY_NAMES.get(code, code),
        "items": items,
        "total_score": total_score,
        "ma20": ma20, "ma50": ma50,
        "rsi": rsi, "dif": dif, "dea": dea,
    }


def _overall_verdict(score: int) -> tuple[str, str, str]:
    """
    根據總分回傳綜合判定結果。

    Returns
    -------
    tuple[str, str, str]
        (判定文字, 背景色, 文字色)
    """
    if score >= 3:
        return "強烈看多", "#065f46", "#d1fae5"
    elif score >= 1:
        return "偏多", "#10b981", "#ecfdf5"
    elif score == 0:
        return "中性", "#6b7280", "#f3f4f6"
    elif score >= -2:
        return "偏空", "#ef4444", "#fef2f2"
    else:
        return "強烈看空", "#991b1b", "#fee2e2"


def _generate_summary(result: dict) -> str:
    """
    根據評分結果自動產生文字摘要。

    Parameters
    ----------
    result : dict
        _score_single_currency 的回傳值。

    Returns
    -------
    str
        技術面摘要文字。
    """
    parts: list[str] = []

    ma20, ma50 = result.get("ma20"), result.get("ma50")
    if pd.notna(ma20) and pd.notna(ma50):
        if ma20 > ma50:
            parts.append("目前 MA20 位於 MA50 上方，短期趨勢偏多")
        else:
            parts.append("目前 MA20 位於 MA50 下方，短期趨勢偏空")

    rsi = result.get("rsi")
    if pd.notna(rsi):
        if rsi >= 70:
            parts.append(f"RSI 為 {rsi:.1f}，已進入超買區間，留意回落風險")
        elif rsi <= 30:
            parts.append(f"RSI 為 {rsi:.1f}，已進入超賣區間，可能存在反彈機會")
        else:
            parts.append(f"RSI 為 {rsi:.1f}，處於中性區間")

    dif, dea = result.get("dif"), result.get("dea")
    if pd.notna(dif) and pd.notna(dea):
        if dif > dea:
            parts.append("MACD 快線高於慢線，動能偏多")
        else:
            parts.append("MACD 快線低於慢線，動能偏空")

    score = result["total_score"]
    verdict, _, _ = _overall_verdict(score)
    parts.append(f"綜合評估{verdict}，但建議搭配風控工具設定停損")

    return "；".join(parts) + "。"


# ══════════════════════════════════════
# 介面渲染
# ══════════════════════════════════════

def _render_single_analysis(code: str) -> None:
    """
    渲染單一幣別的訊號分析結果。

    Parameters
    ----------
    code : str
        幣別代碼。
    """
    with st.spinner(f"正在分析 {code}..."):
        result = _score_single_currency(code)

    if result is None:
        st.error(f"⚠️ {code} 資料不足，無法進行訊號分析。")
        return

    score = result["total_score"]
    verdict, fg_color, bg_color = _overall_verdict(score)
    name = result["name"]

    # 大字體綜合判定
    sign = "+" if score > 0 else ""
    st.markdown(
        f"<div style='background:{bg_color}; padding:20px; border-radius:10px; "
        f"text-align:center; margin-bottom:16px;'>"
        f"<span style='font-size:1.8rem; font-weight:700; color:{fg_color};'>"
        f"{code}/TWD — {verdict}（{sign}{score}）</span></div>",
        unsafe_allow_html=True,
    )

    # 評分細項表格
    df_items = pd.DataFrame(result["items"])
    # 得分欄位格式化
    df_items["得分"] = df_items["得分"].apply(
        lambda x: f"+{x}" if x > 0 else str(x)
    )
    st.dataframe(
        df_items,
        width='stretch',
        hide_index=True,
        column_config={
            "條件": st.column_config.TextColumn(width="small"),
            "數值": st.column_config.TextColumn(width="large"),
            "判定": st.column_config.TextColumn(width="small"),
            "得分": st.column_config.TextColumn(width="small"),
        },
    )

    # 文字摘要
    summary = _generate_summary(result)
    st.info(summary)

    # 免責聲明
    st.caption("⚠️ 以上訊號僅為技術面觀察結果，不構成投資建議。")


def _render_multi_comparison(codes: list[str]) -> None:
    """
    渲染多幣別比較表格。

    Parameters
    ----------
    codes : list[str]
        幣別代碼清單。
    """
    if not codes:
        st.info("請選擇至少一個幣別進行比較。")
        return

    rows: list[dict] = []
    progress = st.progress(0, text="正在分析多幣別訊號...")
    for i, code in enumerate(codes):
        result = _score_single_currency(code)
        if result:
            row = {"幣別": f"{code} {result['name']}"}
            for item in result["items"]:
                row[item["條件"]] = item["得分"]
            row["綜合得分"] = result["total_score"]
            verdict, _, _ = _overall_verdict(result["total_score"])
            row["綜合判定"] = verdict
            # 技術面情緒
            try:
                _df = get_history_rate(code, days=90)
                _s = calc_technical_sentiment(_df)
                row["情緒"] = f'{_s["label"]} {_s["text"]}'
            except Exception:
                row["情緒"] = "⚪ —"
            rows.append(row)
        progress.progress((i + 1) / len(codes), text=f"已分析 {i + 1}/{len(codes)}")

    progress.empty()

    if not rows:
        st.warning("所有選擇的幣別皆資料不足。")
        return

    df_compare = pd.DataFrame(rows)
    # 將得分欄位轉為 int 以便排序
    score_cols = ["MA 趨勢", "MA 交叉", "RSI", "MACD", "布林位置"]
    for col in score_cols:
        if col in df_compare.columns:
            df_compare[col] = pd.to_numeric(df_compare[col], errors="coerce").fillna(0).astype(int)

    df_compare = df_compare.sort_values("綜合得分", ascending=False).reset_index(drop=True)

    st.dataframe(
        df_compare,
        width='stretch',
        hide_index=True,
    )
    st.caption("⚠️ 以上訊號僅為技術面觀察結果，不構成投資建議。")


# ══════════════════════════════════════
# 主渲染函式
# ══════════════════════════════════════

def render() -> None:
    """渲染技術指標與訊號頁面（主進入點）。"""
    st.title("📡 技術指標與訊號")
    st.caption("基於 MA、RSI、MACD、布林通道的多指標綜合訊號評分系統")

    # ── 幣別選擇 ──
    labels = [f"{c} {CURRENCY_NAMES.get(c, c)}" for c in ALL_CURRENCY_CODES]
    label_to_code = dict(zip(labels, ALL_CURRENCY_CODES))

    selected_label = st.selectbox(
        "選擇貨幣",
        options=labels,
        index=0,
        key="signals_currency",
    )
    code = label_to_code[selected_label]

    # ── 單一幣別分析 ──
    _render_single_analysis(code)

    # ── 多幣別比較 ──
    st.markdown("---")
    multi_mode = st.checkbox("🔄 啟用多幣別比較", key="signals_multi_mode")

    if multi_mode:
        selected_multi = st.multiselect(
            "選擇要比較的幣別",
            options=labels,
            default=labels[:7],  # 預設主要貨幣
            key="signals_multi_select",
        )
        multi_codes = [label_to_code[lbl] for lbl in selected_multi]
        if multi_codes:
            _render_multi_comparison(multi_codes)
