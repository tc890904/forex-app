"""
pages/overview.py — 匯率總覽頁

顯示所有幣別的最新牌告匯率，支援分類篩選與排序。
"""

import streamlit as st


def render() -> None:
    """渲染匯率總覽頁面。"""
    st.title("📊 匯率總覽")
    st.info("🚧 功能開發中 — 將顯示所有幣別的最新台銀牌告匯率，支援分類篩選與排序。")
