"""
LINE Bot UI — Flex Message 視覺系統

視覺方向：FOREX DESK（深松綠 × 紙白）
"""

from __future__ import annotations

from typing import Any, Optional

from linebot.v3.messaging import (
    FlexBlockStyle,
    FlexBox,
    FlexBubble,
    FlexBubbleStyles,
    FlexButton,
    FlexCarousel,
    FlexImage,
    FlexMessage,
    FlexSeparator,
    FlexText,
    MessageAction,
    QuickReply,
    QuickReplyItem,
)

# ── 設計 token ──────────────────────────────────────────
INK = "#0B1F1C"
PAPER = "#FAFAF8"
ACCENT = "#1F6F63"
ACCENT_SOFT = "#7A9E96"
MUTED = "#6B7280"
LINE = "#E5E7EB"
UP = "#1F6F63"
DOWN = "#B42318"
NEUTRAL = "#9A7B4F"
HEADER_BG = "#0B1F1C"
WHITE = "#FFFFFF"

BRAND = "FOREX DESK"
DISCLAIMER = "資料僅供參考，不構成投資建議"


def default_quick_reply() -> QuickReply:
    """LINE Quick Reply 最多 13 個：幣別 + 進階功能。"""
    return QuickReply(
        items=[
            QuickReplyItem(action=MessageAction(label="美元", text="USD")),
            QuickReplyItem(action=MessageAction(label="日圓", text="JPY")),
            QuickReplyItem(action=MessageAction(label="歐元", text="EUR")),
            QuickReplyItem(action=MessageAction(label="英鎊", text="GBP")),
            QuickReplyItem(action=MessageAction(label="市場", text="匯率")),
            QuickReplyItem(action=MessageAction(label="強弱", text="強弱")),
            QuickReplyItem(action=MessageAction(label="訊號", text="訊號")),
            QuickReplyItem(action=MessageAction(label="停損", text="停損 USD")),
            QuickReplyItem(action=MessageAction(label="凱利", text="凱利")),
            QuickReplyItem(action=MessageAction(label="槓桿", text="槓桿")),
            QuickReplyItem(action=MessageAction(label="相關", text="相關")),
            QuickReplyItem(action=MessageAction(label="回測", text="回測 USD")),
            QuickReplyItem(action=MessageAction(label="說明", text="說明")),
        ]
    )


def _change_color(pct: Optional[float]) -> str:
    if pct is None:
        return MUTED
    if pct > 0:
        return UP
    if pct < 0:
        return DOWN
    return NEUTRAL


def _mood_color(score: int) -> str:
    if score > 0:
        return UP
    if score < 0:
        return DOWN
    return NEUTRAL


def _kv_row(label: str, value: str, value_color: str = INK) -> FlexBox:
    return FlexBox(
        layout="baseline",
        spacing="sm",
        contents=[
            FlexText(text=label, size="sm", color=MUTED, flex=3, wrap=True),
            FlexText(
                text=value,
                size="sm",
                color=value_color,
                align="end",
                flex=4,
                weight="bold",
                wrap=True,
            ),
        ],
    )


def _footer_actions(*pairs: tuple[str, str]) -> FlexBox:
    """pairs: (label, message_text)"""
    buttons = []
    for i, (label, text) in enumerate(pairs[:4]):
        if i == 0:
            buttons.append(
                FlexButton(
                    style="primary",
                    color=ACCENT,
                    height="sm",
                    action=MessageAction(label=label[:20], text=text),
                )
            )
        else:
            buttons.append(
                FlexButton(
                    style="link",
                    height="sm",
                    action=MessageAction(label=label[:20], text=text),
                )
            )
    return FlexBox(
        layout="vertical",
        spacing="sm",
        padding_all="12px",
        contents=buttons,
    )


def _styles() -> FlexBubbleStyles:
    return FlexBubbleStyles(
        header=FlexBlockStyle(background_color=HEADER_BG),
        body=FlexBlockStyle(background_color=PAPER),
        footer=FlexBlockStyle(background_color=PAPER, separator=True, separator_color=LINE),
    )


def build_rate_flex(
    result: dict,
    currency_name: str,
    chart_url: Optional[str] = None,
) -> FlexBubble:
    """單一幣別分析卡（可選 HTTPS K 線圖）。"""
    r = result["rate"]
    t = result["tech"]
    code = r["currency"]
    change = t.get("change_pct")
    change_text = f"{change:+.2f}%" if change is not None else "—"
    change_col = _change_color(change)

    body_rows: list[Any] = [
        FlexText(text="即期賣出", size="xs", color=MUTED),
        FlexText(
            text=f"{r['spot_sell']:.4f}",
            size="3xl",
            weight="bold",
            color=INK,
        ),
        FlexBox(
            layout="baseline",
            spacing="md",
            contents=[
                FlexText(text=change_text, size="md", weight="bold", color=change_col),
                FlexText(text="TWD", size="sm", color=MUTED),
            ],
        ),
        FlexSeparator(margin="lg", color=LINE),
        FlexBox(
            layout="vertical",
            background_color=(
                "#EEF6F4"
                if result.get("score", 0) > 0
                else ("#FDF2F0" if result.get("score", 0) < 0 else "#F5F1E8")
            ),
            corner_radius="8px",
            padding_all="12px",
            contents=[
                FlexText(
                    text=result["mood"],
                    size="md",
                    weight="bold",
                    color=_mood_color(result.get("score", 0)),
                ),
            ],
        ),
    ]

    for sig in result.get("signals", [])[:3]:
        body_rows.append(FlexText(text=f"· {sig}", size="xs", color=MUTED, wrap=True))

    # 5 項評分明細（若有）
    detail = result.get("signal_detail")
    if detail and detail.get("items"):
        body_rows.append(FlexSeparator(margin="lg", color=LINE))
        body_rows.append(
            FlexText(
                text=f"五維評分 {detail['total_score']:+d}",
                size="sm",
                weight="bold",
                color=INK,
            )
        )
        for it in detail["items"]:
            body_rows.append(
                _kv_row(
                    it["name"],
                    f"{it['verdict']} ({it['score']:+d})",
                    _mood_color(it["score"]),
                )
            )
        if detail.get("summary"):
            body_rows.append(
                FlexText(text=detail["summary"], size="xxs", color=MUTED, wrap=True, margin="md")
            )

    body_rows.append(FlexSeparator(margin="lg", color=LINE))
    body_rows.append(_kv_row("現金賣出", f"{r['cash_sell']:.4f}"))
    if t.get("rsi") is not None:
        body_rows.append(_kv_row("RSI (14)", f"{t['rsi']:.1f}"))
    if t.get("ma20") and t.get("ma50"):
        body_rows.append(_kv_row("MA20 / MA50", f"{t['ma20']:.4f} / {t['ma50']:.4f}"))
    if t.get("dif") is not None and t.get("dea") is not None:
        body_rows.append(_kv_row("MACD", f"{t['dif']:.4f} / {t['dea']:.4f}"))
    body_rows.append(
        FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True, margin="lg")
    )

    hero = None
    if chart_url and chart_url.startswith("https://"):
        hero = FlexImage(
            url=chart_url,
            size="full",
            aspect_ratio="20:9",
            aspect_mode="cover",
        )

    return FlexBubble(
        size="mega",
        styles=_styles(),
        header=FlexBox(
            layout="vertical",
            spacing="xs",
            padding_all="20px",
            contents=[
                FlexText(text=BRAND, size="xxs", color=ACCENT_SOFT, weight="bold"),
                FlexText(
                    text=f"{code} / TWD",
                    size="xl",
                    color=WHITE,
                    weight="bold",
                ),
                FlexText(
                    text=f"{currency_name} · {r.get('date', '')} · 日K",
                    size="xs",
                    color=ACCENT_SOFT,
                ),
            ],
        ),
        hero=hero,
        body=FlexBox(
            layout="vertical",
            spacing="sm",
            padding_all="20px",
            contents=body_rows,
        ),
        footer=_footer_actions(
            ("ATR 停損", f"停損 {code}"),
            ("回測", f"回測 {code}"),
            ("市場速覽", "匯率"),
        ),
    )


def build_market_flex(results: dict[str, dict], order: list[str]) -> FlexBubble:
    """市場速覽：單卡列表，易掃讀。"""
    rows: list[Any] = [
        FlexText(text="主要貨幣對台幣", size="xs", color=MUTED, margin="none"),
        FlexSeparator(margin="md", color=LINE),
    ]

    for code in order:
        result = results.get(code) or {"error": "無資料"}
        if "error" in result:
            rows.append(_kv_row(code, "暫無資料", MUTED))
            continue
        r = result["rate"]
        change = result["tech"].get("change_pct")
        change_s = f"{change:+.2f}%" if change is not None else ""
        value = f"{r['spot_sell']:.4f}  {change_s}".rstrip()
        rows.append(_kv_row(f"{code}", value, _change_color(change)))

    rows.append(
        FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True, margin="lg")
    )

    return FlexBubble(
        size="mega",
        styles=_styles(),
        header=FlexBox(
            layout="vertical",
            spacing="xs",
            padding_all="20px",
            contents=[
                FlexText(text=BRAND, size="xxs", color=ACCENT_SOFT, weight="bold"),
                FlexText(text="市場速覽", size="xl", color=WHITE, weight="bold"),
                FlexText(text="即期賣出 · 日漲跌", size="xs", color=ACCENT_SOFT),
            ],
        ),
        body=FlexBox(
            layout="vertical",
            spacing="md",
            padding_all="20px",
            contents=rows,
        ),
        footer=_footer_actions(
            ("查美元", "USD"),
            ("查日圓", "JPY"),
            ("使用說明", "說明"),
        ),
    )


def build_help_flex() -> FlexBubble:
    return FlexBubble(
        size="mega",
        styles=_styles(),
        header=FlexBox(
            layout="vertical",
            spacing="xs",
            padding_all="20px",
            contents=[
                FlexText(text=BRAND, size="xxs", color=ACCENT_SOFT, weight="bold"),
                FlexText(text="使用說明", size="xl", color=WHITE, weight="bold"),
                FlexText(text="點按鈕或輸入指令", size="xs", color=ACCENT_SOFT),
            ],
        ),
        body=FlexBox(
            layout="vertical",
            spacing="sm",
            padding_all="20px",
            contents=[
                FlexText(text="查價 / 分析", size="sm", weight="bold", color=INK),
                FlexText(
                    text="USD、美元、分析 日圓 → 匯率 + 技術面 + 日K",
                    size="xs",
                    color=MUTED,
                    wrap=True,
                ),
                FlexSeparator(margin="md", color=LINE),
                FlexText(text="市場工具", size="sm", weight="bold", color=INK),
                _kv_row("匯率 / 貨幣", "市場速覽"),
                _kv_row("強弱 / 最強", "漲跌排行"),
                _kv_row("訊號", "多幣訊號比較"),
                _kv_row("相關", "主要貨幣相關"),
                _kv_row("情緒", "技術面情緒總覽"),
                FlexSeparator(margin="md", color=LINE),
                FlexText(text="風控 / 研究", size="sm", weight="bold", color=INK),
                _kv_row("停損 USD", "ATR 停損停利"),
                _kv_row("凱利", "凱利倉位建議"),
                _kv_row("槓桿", "槓桿風險"),
                _kv_row("回測 USD", "MA 交叉回測"),
                FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True, margin="lg"),
            ],
        ),
        footer=_footer_actions(
            ("市場速覽", "匯率"),
            ("訊號比較", "訊號"),
            ("停損 USD", "停損 USD"),
            ("強弱排行", "強弱"),
        ),
    )


def build_error_flex(title: str, detail: str) -> FlexBubble:
    return FlexBubble(
        size="kilo",
        styles=_styles(),
        header=FlexBox(
            layout="vertical",
            padding_all="18px",
            contents=[
                FlexText(text=BRAND, size="xxs", color=ACCENT_SOFT, weight="bold"),
                FlexText(text=title, size="lg", color=WHITE, weight="bold"),
            ],
        ),
        body=FlexBox(
            layout="vertical",
            spacing="md",
            padding_all="18px",
            contents=[
                FlexText(text=detail, size="sm", color=MUTED, wrap=True),
            ],
        ),
        footer=_footer_actions(("使用說明", "說明"), ("市場速覽", "匯率")),
    )


def build_hint_carousel() -> FlexCarousel:
    """歡迎／未知指令時的快捷幣別輪播。"""
    codes = [
        ("USD", "美元"),
        ("JPY", "日圓"),
        ("EUR", "歐元"),
        ("GBP", "英鎊"),
        ("AUD", "澳幣"),
        ("CNY", "人民幣"),
        ("HKD", "港幣"),
        ("SGD", "新幣"),
    ]
    bubbles = []
    for code, name in codes:
        bubbles.append(
            FlexBubble(
                size="nano",
                styles=FlexBubbleStyles(
                    body=FlexBlockStyle(background_color=PAPER),
                    footer=FlexBlockStyle(
                        background_color=PAPER, separator=True, separator_color=LINE
                    ),
                ),
                body=FlexBox(
                    layout="vertical",
                    spacing="sm",
                    padding_all="16px",
                    contents=[
                        FlexText(text=code, size="lg", weight="bold", color=INK),
                        FlexText(text=name, size="xs", color=MUTED),
                    ],
                ),
                footer=FlexBox(
                    layout="vertical",
                    padding_all="8px",
                    contents=[
                        FlexButton(
                            style="primary",
                            color=ACCENT,
                            height="sm",
                            action=MessageAction(label="查詢", text=code),
                        )
                    ],
                ),
            )
        )
    return FlexCarousel(contents=bubbles)


def to_flex_message(contents: Any, alt_text: str, quick_reply: bool = True) -> FlexMessage:
    return FlexMessage(
        alt_text=alt_text[:400],
        contents=contents,
        quick_reply=default_quick_reply() if quick_reply else None,
    )


def build_signals_flex(rows: list[dict]) -> FlexBubble:
    """多幣別訊號比較。"""
    body: list[Any] = [
        FlexText(text="5 項評分加總（高→低）", size="xs", color=MUTED),
        FlexSeparator(margin="md", color=LINE),
    ]
    for row in rows[:12]:
        score = row["total_score"]
        body.append(
            _kv_row(
                f"{row['code']} {row.get('name', '')}".strip(),
                f"{row['mood']} ({score:+d})",
                _mood_color(score),
            )
        )
    body.append(FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True, margin="lg"))
    return FlexBubble(
        size="mega",
        styles=_styles(),
        header=FlexBox(
            layout="vertical",
            padding_all="20px",
            spacing="xs",
            contents=[
                FlexText(text=BRAND, size="xxs", color=ACCENT_SOFT, weight="bold"),
                FlexText(text="訊號比較", size="xl", color=WHITE, weight="bold"),
                FlexText(text="MA / 交叉 / RSI / MACD / 布林", size="xs", color=ACCENT_SOFT),
            ],
        ),
        body=FlexBox(layout="vertical", spacing="sm", padding_all="20px", contents=body),
        footer=_footer_actions(("市場速覽", "匯率"), ("強弱排行", "強弱"), ("說明", "說明")),
    )


def build_ranking_flex(rows: list[dict]) -> FlexBubble:
    body: list[Any] = [
        FlexText(text="依日漲跌幅排序", size="xs", color=MUTED),
        FlexSeparator(margin="md", color=LINE),
    ]
    for i, row in enumerate(rows[:12], 1):
        ch = row["change_pct"]
        body.append(
            _kv_row(
                f"{i}. {row['code']}",
                f"{row['rate']:.4f}  {ch:+.2f}%",
                _change_color(ch),
            )
        )
    body.append(FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True, margin="lg"))
    return FlexBubble(
        size="mega",
        styles=_styles(),
        header=FlexBox(
            layout="vertical",
            padding_all="20px",
            spacing="xs",
            contents=[
                FlexText(text=BRAND, size="xxs", color=ACCENT_SOFT, weight="bold"),
                FlexText(text="強弱排行", size="xl", color=WHITE, weight="bold"),
                FlexText(text="最強 → 最弱", size="xs", color=ACCENT_SOFT),
            ],
        ),
        body=FlexBox(layout="vertical", spacing="sm", padding_all="20px", contents=body),
        footer=_footer_actions(("市場速覽", "匯率"), ("訊號比較", "訊號"), ("說明", "說明")),
    )


def build_atr_flex(code: str, name: str, stops: dict) -> FlexBubble:
    direction = "做多" if stops["direction"] == "long" else "做空"
    body = [
        _kv_row("方向", direction),
        _kv_row("進場參考", f"{stops['entry']:.4f}"),
        _kv_row("ATR(14)", f"{stops['atr']:.4f}"),
        _kv_row("ATR 倍數", f"{stops['atr_mult']:.1f}"),
        FlexSeparator(margin="md", color=LINE),
        _kv_row("建議停損", f"{stops['stop_loss']:.4f}", DOWN),
        _kv_row("建議停利", f"{stops['take_profit']:.4f}", UP),
        _kv_row("停損幅度", f"{stops['stop_pct']:.2f}%"),
        _kv_row("停利幅度", f"{stops['profit_pct']:.2f}%"),
        _kv_row("風險報酬", f"1 : {stops['rr']:.1f}"),
        FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True, margin="lg"),
    ]
    return FlexBubble(
        size="mega",
        styles=_styles(),
        header=FlexBox(
            layout="vertical",
            padding_all="20px",
            spacing="xs",
            contents=[
                FlexText(text=BRAND, size="xxs", color=ACCENT_SOFT, weight="bold"),
                FlexText(text=f"ATR 停損 · {code}", size="xl", color=WHITE, weight="bold"),
                FlexText(text=name, size="xs", color=ACCENT_SOFT),
            ],
        ),
        body=FlexBox(layout="vertical", spacing="sm", padding_all="20px", contents=body),
        footer=_footer_actions(
            ("再查匯率", code),
            ("做空停損", f"停損空 {code}"),
            ("凱利", "凱利"),
        ),
    )


def build_kelly_flex(data: dict) -> FlexBubble:
    viable = "可行" if data["viable"] else "不建議（f*≤0）"
    body = [
        _kv_row("假設勝率", f"{data['win_rate']*100:.0f}%"),
        _kv_row("盈虧比", f"{data['payoff']:.2f}"),
        _kv_row("總資金", f"{data['capital']:.0f}"),
        FlexSeparator(margin="md", color=LINE),
        _kv_row("凱利比例", f"{data['kelly_pct']:.1f}%"),
        _kv_row("凱利金額", f"{data['kelly_amount']:.0f}"),
        _kv_row("半凱利比例", f"{data['half_kelly_pct']:.1f}%", ACCENT),
        _kv_row("半凱利金額", f"{data['half_kelly_amount']:.0f}", ACCENT),
        _kv_row("策略評估", viable),
        FlexText(
            text="預設參數可改：凱利 0.6 2 10000（勝率 盈虧比 資金）",
            size="xxs",
            color=MUTED,
            wrap=True,
            margin="lg",
        ),
        FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True),
    ]
    return FlexBubble(
        size="mega",
        styles=_styles(),
        header=FlexBox(
            layout="vertical",
            padding_all="20px",
            spacing="xs",
            contents=[
                FlexText(text=BRAND, size="xxs", color=ACCENT_SOFT, weight="bold"),
                FlexText(text="凱利倉位", size="xl", color=WHITE, weight="bold"),
                FlexText(text="建議使用半凱利更保守", size="xs", color=ACCENT_SOFT),
            ],
        ),
        body=FlexBox(layout="vertical", spacing="sm", padding_all="20px", contents=body),
        footer=_footer_actions(("槓桿風險", "槓桿"), ("停損 USD", "停損 USD"), ("說明", "說明")),
    )


def build_leverage_flex(data: dict) -> FlexBubble:
    body = [
        _kv_row("本金", f"{data['capital']:.0f}"),
        _kv_row("槓桿", f"{data['leverage']}x"),
        _kv_row("持倉市值", f"{data['position_value']:.0f}"),
        _kv_row("保證金維持率", f"{data['margin_ratio']:.1f}%"),
        _kv_row("強平波動", f"{data['liquidation_move_pct']:.2f}%", DOWN),
        _kv_row("風險等級", data["risk_level"], DOWN if data["leverage"] > 20 else NEUTRAL),
    ]
    if data.get("atr_days") is not None:
        body.append(_kv_row("約達強平(ATR日)", f"{data['atr_days']:.1f} 日"))
    body.append(
        FlexText(
            text="預設：槓桿 10；可輸入「槓桿 20」或「槓桿 20 USD」",
            size="xxs",
            color=MUTED,
            wrap=True,
            margin="lg",
        )
    )
    body.append(FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True))
    return FlexBubble(
        size="mega",
        styles=_styles(),
        header=FlexBox(
            layout="vertical",
            padding_all="20px",
            spacing="xs",
            contents=[
                FlexText(text=BRAND, size="xxs", color=ACCENT_SOFT, weight="bold"),
                FlexText(text="槓桿風險", size="xl", color=WHITE, weight="bold"),
                FlexText(text="保證金與強平距離估算", size="xs", color=ACCENT_SOFT),
            ],
        ),
        body=FlexBox(layout="vertical", spacing="sm", padding_all="20px", contents=body),
        footer=_footer_actions(("凱利", "凱利"), ("停損 USD", "停損 USD"), ("說明", "說明")),
    )


def build_corr_flex(matrix: dict[str, dict[str, float]], codes: list[str]) -> FlexBubble:
    body: list[Any] = [
        FlexText(text="主要貨幣 90 日報酬相關（文字版）", size="xs", color=MUTED, wrap=True),
        FlexSeparator(margin="md", color=LINE),
    ]
    # show upper triangle pairs for readability
    shown = 0
    for i, a in enumerate(codes):
        for b in codes[i + 1 :]:
            if a not in matrix or b not in matrix[a]:
                continue
            v = matrix[a][b]
            body.append(_kv_row(f"{a}-{b}", f"{v:+.2f}", UP if v >= 0 else DOWN))
            shown += 1
            if shown >= 15:
                break
        if shown >= 15:
            break
    if shown == 0:
        body.append(FlexText(text="相關資料不足", size="sm", color=MUTED))
    body.append(FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True, margin="lg"))
    return FlexBubble(
        size="mega",
        styles=_styles(),
        header=FlexBox(
            layout="vertical",
            padding_all="20px",
            spacing="xs",
            contents=[
                FlexText(text=BRAND, size="xxs", color=ACCENT_SOFT, weight="bold"),
                FlexText(text="貨幣相關", size="xl", color=WHITE, weight="bold"),
                FlexText(text="熱力圖文字精簡版", size="xs", color=ACCENT_SOFT),
            ],
        ),
        body=FlexBox(layout="vertical", spacing="sm", padding_all="20px", contents=body),
        footer=_footer_actions(("強弱排行", "強弱"), ("市場速覽", "匯率"), ("說明", "說明")),
    )


def build_backtest_flex(code: str, name: str, summary: dict) -> FlexBubble:
    if "error" in summary:
        return build_error_flex("回測失敗", summary["error"])
    body = [
        _kv_row("策略", summary.get("note", "MA 交叉")),
        _kv_row("交易次數", str(summary["trades"])),
        _kv_row("勝率", f"{summary['win_rate']:.1f}%"),
        _kv_row("總報酬", f"{summary['total_return_pct']:+.2f}%", _change_color(summary["total_return_pct"])),
        _kv_row("最大回撤", f"{summary['max_drawdown_pct']:.2f}%", DOWN),
        _kv_row("期末資金", f"{summary['final_equity']:.0f}"),
    ]
    if "avg_pnl" in summary:
        body.append(_kv_row("平均每筆", f"{summary['avg_pnl']:+.2f}%"))
    body.append(FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True, margin="lg"))
    return FlexBubble(
        size="mega",
        styles=_styles(),
        header=FlexBox(
            layout="vertical",
            padding_all="20px",
            spacing="xs",
            contents=[
                FlexText(text=BRAND, size="xxs", color=ACCENT_SOFT, weight="bold"),
                FlexText(text=f"回測 · {code}", size="xl", color=WHITE, weight="bold"),
                FlexText(text=name, size="xs", color=ACCENT_SOFT),
            ],
        ),
        body=FlexBox(layout="vertical", spacing="sm", padding_all="20px", contents=body),
        footer=_footer_actions(("再查匯率", code), ("停損 " + code, f"停損 {code}"), ("訊號", "訊號")),
    )


def build_sentiment_flex(rows: list[dict]) -> FlexBubble:
    body: list[Any] = [
        FlexText(text="技術面情緒（非新聞）", size="xs", color=MUTED),
        FlexSeparator(margin="md", color=LINE),
    ]
    for row in rows:
        body.append(
            _kv_row(
                row["code"],
                f"{row['text']} ({row['score']:+d})",
                _mood_color(row["score"]),
            )
        )
    body.append(FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True, margin="lg"))
    return FlexBubble(
        size="mega",
        styles=_styles(),
        header=FlexBox(
            layout="vertical",
            padding_all="20px",
            spacing="xs",
            contents=[
                FlexText(text=BRAND, size="xxs", color=ACCENT_SOFT, weight="bold"),
                FlexText(text="情緒總覽", size="xl", color=WHITE, weight="bold"),
                FlexText(text="RSI + MACD + MA", size="xs", color=ACCENT_SOFT),
            ],
        ),
        body=FlexBox(layout="vertical", spacing="sm", padding_all="20px", contents=body),
        footer=_footer_actions(("訊號比較", "訊號"), ("強弱排行", "強弱"), ("說明", "說明")),
    )

