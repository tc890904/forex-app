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
    """LINE Quick Reply 最多 13 個。"""
    return QuickReply(
        items=[
            QuickReplyItem(action=MessageAction(label="美元", text="USD")),
            QuickReplyItem(action=MessageAction(label="日圓", text="JPY")),
            QuickReplyItem(action=MessageAction(label="歐元", text="EUR")),
            QuickReplyItem(action=MessageAction(label="英鎊", text="GBP")),
            QuickReplyItem(action=MessageAction(label="澳幣", text="AUD")),
            QuickReplyItem(action=MessageAction(label="加幣", text="CAD")),
            QuickReplyItem(action=MessageAction(label="瑞郎", text="CHF")),
            QuickReplyItem(action=MessageAction(label="人民幣", text="CNY")),
            QuickReplyItem(action=MessageAction(label="港幣", text="HKD")),
            QuickReplyItem(action=MessageAction(label="新幣", text="SGD")),
            QuickReplyItem(action=MessageAction(label="紐幣", text="NZD")),
            QuickReplyItem(action=MessageAction(label="市場速覽", text="匯率")),
            QuickReplyItem(action=MessageAction(label="使用說明", text="說明")),
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
            ("市場速覽", "匯率"),
            ("再查一次", code),
            ("使用說明", "說明"),
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
                FlexText(text="點按鈕或直接輸入幣別", size="xs", color=ACCENT_SOFT),
            ],
        ),
        body=FlexBox(
            layout="vertical",
            spacing="md",
            padding_all="20px",
            contents=[
                FlexText(text="查詢方式", size="sm", weight="bold", color=INK),
                FlexText(
                    text="輸入代碼（USD）或中文（美元）。也可輸入「分析 美元」看技術面。",
                    size="sm",
                    color=MUTED,
                    wrap=True,
                ),
                FlexSeparator(margin="md", color=LINE),
                FlexText(text="常用指令", size="sm", weight="bold", color=INK),
                _kv_row("匯率 / 最強", "市場速覽"),
                _kv_row("說明", "顯示此選單"),
                FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True, margin="lg"),
            ],
        ),
        footer=_footer_actions(
            ("市場速覽", "匯率"),
            ("美元", "USD"),
            ("日圓", "JPY"),
            ("歐元", "EUR"),
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
