"""
LINE Bot UI — Flex Message 與圖卡視覺系統

視覺方向：FOREX DESK（深松綠 × 紙白）
避免紫色漸層、奶油襯線、報紙排版。
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont
from linebot.v3.messaging import (
    FlexBlockStyle,
    FlexBox,
    FlexBubble,
    FlexBubbleStyles,
    FlexButton,
    FlexCarousel,
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
    return QuickReply(
        items=[
            QuickReplyItem(action=MessageAction(label="美元", text="USD")),
            QuickReplyItem(action=MessageAction(label="日圓", text="JPY")),
            QuickReplyItem(action=MessageAction(label="歐元", text="EUR")),
            QuickReplyItem(action=MessageAction(label="英鎊", text="GBP")),
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


def build_rate_flex(result: dict, currency_name: str) -> FlexBubble:
    """單一幣別分析卡。"""
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
                    text=f"{currency_name} · {r.get('date', '')}",
                    size="xs",
                    color=ACCENT_SOFT,
                ),
            ],
        ),
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
    codes = [("USD", "美元"), ("JPY", "日圓"), ("EUR", "歐元"), ("GBP", "英鎊")]
    bubbles = []
    for code, name in codes:
        bubbles.append(
            FlexBubble(
                size="nano",
                styles=FlexBubbleStyles(
                    body=FlexBlockStyle(background_color=PAPER),
                    footer=FlexBlockStyle(background_color=PAPER, separator=True, separator_color=LINE),
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


# ── PNG 圖卡（可選，需 HTTPS）────────────────────────────


def _load_fonts() -> tuple:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    bold = regular = None
    for path in candidates:
        if not Path(path).exists():
            continue
        try:
            if bold is None and ("Bold" in path or "Helvetica" in path):
                bold = path
            if regular is None:
                regular = path
        except OSError:
            continue
    if not regular:
        d = ImageFont.load_default()
        return d, d, d, d
    try:
        bpath = bold or regular
        return (
            ImageFont.truetype(bpath, 22),
            ImageFont.truetype(bpath, 64),
            ImageFont.truetype(regular, 24),
            ImageFont.truetype(regular, 16),
        )
    except OSError:
        d = ImageFont.load_default()
        return d, d, d, d


def generate_rate_card_image(result: dict, currency_name: str) -> Optional[bytes]:
    """重繪匯率圖卡：紙白底 + 左側松綠色帶。"""
    if "error" in result:
        return None

    r = result["rate"]
    t = result["tech"]
    code = r["currency"]
    change = t.get("change_pct")

    w, h = 720, 420
    img = Image.new("RGB", (w, h), color=PAPER)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, 12, h], fill=ACCENT)
    draw.rectangle([12, 0, w, 72], fill=HEADER_BG)

    font_brand, font_rate, font_body, font_small = _load_fonts()

    draw.text((36, 22), BRAND, fill=ACCENT_SOFT, font=font_small)
    draw.text((36, 42), f"{code} / TWD", fill=WHITE, font=font_brand)

    subtitle = currency_name if currency_name else code
    draw.text((36, 100), subtitle, fill=MUTED, font=font_small)

    rate_text = f"{r['spot_sell']:.4f}"
    draw.text((36, 128), rate_text, fill=INK, font=font_rate)
    # 用實際字寬對齊 TWD，避免重疊
    try:
        bbox = draw.textbbox((36, 128), rate_text, font=font_rate)
        twd_x = bbox[2] + 16
    except Exception:
        twd_x = 36 + len(rate_text) * 36
    draw.text((twd_x, 168), "TWD", fill=MUTED, font=font_body)

    y = 230
    if change is not None:
        col = UP if change > 0 else (DOWN if change < 0 else NEUTRAL)
        draw.text((36, y), f"{change:+.2f}%", fill=col, font=font_body)
        y += 42

    mood_col = _mood_color(result.get("score", 0))
    # mood 色塊
    mood = result["mood"]
    try:
        mb = draw.textbbox((0, 0), mood, font=font_body)
        mw, mh = mb[2] - mb[0] + 24, mb[3] - mb[1] + 14
    except Exception:
        mw, mh = 140, 36
    draw.rounded_rectangle([36, y, 36 + mw, y + mh], radius=8, fill=mood_col)
    draw.text((48, y + 6), mood, fill=WHITE, font=font_small)
    y += mh + 28

    draw.line([(36, y), (w - 36, y)], fill=LINE, width=1)
    y += 18
    metrics = []
    if t.get("rsi") is not None:
        metrics.append(f"RSI {t['rsi']:.1f}")
    if t.get("ma20") and t.get("ma50"):
        metrics.append(f"MA20 {t['ma20']:.4f}")
    metrics.append(r.get("date", ""))
    draw.text((36, y), "  ·  ".join(m for m in metrics if m), fill=MUTED, font=font_small)
    draw.text((36, h - 36), DISCLAIMER, fill=ACCENT_SOFT, font=font_small)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.getvalue()
