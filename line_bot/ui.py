"""
LINE Bot UI — FOREX DESK Flex 視覺系統（摘要／詳情分離 + 情境導覽）
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

INK = "#0B1F1C"
PAPER = "#FAFAF8"
ACCENT = "#1F6F63"
ACCENT_SOFT = "#7A9E96"
MUTED = "#64748B"
LINE = "#E5E7EB"
UP = "#0F766E"
DOWN = "#B91C1C"
NEUTRAL = "#A16207"
HEADER_BG = "#0B1F1C"
WHITE = "#FFFFFF"
BRAND = "FOREX DESK"
DISCLAIMER = "資料僅供參考，不構成投資建議"


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
    buttons = []
    for i, (label, text) in enumerate(pairs[:4]):
        buttons.append(
            FlexButton(
                style="primary" if i == 0 else "link",
                color=ACCENT if i == 0 else None,
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
        footer=FlexBlockStyle(
            background_color=PAPER, separator=True, separator_color=LINE
        ),
    )


def contextual_quick_reply(
    mode: str = "home",
    last_code: Optional[str] = None,
) -> QuickReply:
    """依情境產生 Quick Reply（最多 13）。"""
    code = last_code or "USD"
    if mode == "currency":
        items = [
            ("詳情", f"詳情 {code}"),
            ("停損", f"停損 {code}"),
            ("回測", f"回測 {code}"),
            ("市場", "匯率"),
            ("強弱", "強弱"),
            ("訊號", "訊號"),
            ("美元", "USD"),
            ("日圓", "JPY"),
            ("歐元", "EUR"),
            ("英鎊", "GBP"),
            ("加入清單", f"加入 {code}"),
            ("我的清單", "我的清單"),
            ("說明", "說明"),
        ]
    elif mode == "tools":
        items = [
            ("停損", f"停損 {code}"),
            ("回測", f"回測 {code}"),
            ("凱利", "凱利"),
            ("槓桿", "槓桿"),
            ("相關", "相關"),
            ("情緒", "情緒"),
            ("訊號", "訊號"),
            ("強弱", "強弱"),
            ("市場", "匯率"),
            (code, code),
            ("美元", "USD"),
            ("日圓", "JPY"),
            ("說明", "說明"),
        ]
    elif mode == "market":
        items = [
            ("強弱", "強弱"),
            ("訊號", "訊號"),
            ("相關", "相關"),
            ("情緒", "情緒"),
            ("美元", "USD"),
            ("日圓", "JPY"),
            ("歐元", "EUR"),
            ("英鎊", "GBP"),
            ("澳幣", "AUD"),
            ("人民幣", "CNY"),
            ("港幣", "HKD"),
            ("新幣", "SGD"),
            ("說明", "說明"),
        ]
    else:  # home / welcome
        items = [
            ("查美元", "USD"),
            ("市場速覽", "匯率"),
            ("強弱排行", "強弱"),
            ("訊號比較", "訊號"),
            ("風控工具", "停損"),
            ("日圓", "JPY"),
            ("歐元", "EUR"),
            ("英鎊", "GBP"),
            ("相關", "相關"),
            ("回測", "回測"),
            ("我的清單", "我的清單"),
            ("情緒", "情緒"),
            ("說明", "說明"),
        ]
    return QuickReply(
        items=[
            QuickReplyItem(action=MessageAction(label=lab[:20], text=txt))
            for lab, txt in items[:13]
        ]
    )


def default_quick_reply() -> QuickReply:
    return contextual_quick_reply("home")


def to_flex_message(
    contents: Any,
    alt_text: str,
    quick_reply: Optional[QuickReply] = None,
) -> FlexMessage:
    return FlexMessage(
        alt_text=alt_text[:400],
        contents=contents,
        quick_reply=quick_reply or contextual_quick_reply("home"),
    )


def _conflict_note(result: dict) -> Optional[str]:
    """日線方向與中期情緒衝突時提示。"""
    ch = (result.get("tech") or {}).get("change_pct")
    score = result.get("score", 0)
    if ch is None:
        return None
    if ch > 0 and score < 0:
        return "日線上漲，但中期技術面偏空"
    if ch < 0 and score > 0:
        return "日線下跌，但中期技術面偏多"
    return None


def build_rate_summary_flex(
    result: dict,
    currency_name: str,
    chart_url: Optional[str] = None,
) -> FlexBubble:
    """精簡摘要卡：價、漲跌、情緒、K線、導向詳情。"""
    r = result["rate"]
    t = result["tech"]
    code = r["currency"]
    change = t.get("change_pct")
    change_text = f"{change:+.2f}%" if change is not None else "—"
    note = _conflict_note(result)

    body: list[Any] = [
        FlexText(text="即期賣出", size="xs", color=MUTED),
        FlexText(text=f"{r['spot_sell']:.4f}", size="3xl", weight="bold", color=INK),
        FlexBox(
            layout="baseline",
            spacing="md",
            contents=[
                FlexText(text=change_text, size="md", weight="bold", color=_change_color(change)),
                FlexText(text="TWD", size="sm", color=MUTED),
                FlexText(text=result["mood"], size="sm", weight="bold", color=_mood_color(result.get("score", 0))),
            ],
        ),
    ]
    if note:
        body.append(
            FlexBox(
                layout="vertical",
                background_color="#F5F1E8",
                corner_radius="8px",
                padding_all="10px",
                margin="md",
                contents=[FlexText(text=note, size="xs", color=NEUTRAL, wrap=True)],
            )
        )
    body.append(FlexText(text=f"資料 {r.get('date', '')} · 近 40 日日K", size="xxs", color=MUTED, margin="md"))
    body.append(FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True, margin="sm"))

    hero = None
    if chart_url and chart_url.startswith("https://"):
        hero = FlexImage(url=chart_url, size="full", aspect_ratio="20:10", aspect_mode="cover")

    # 情境 footer：偏空導向停損
    score = result.get("score", 0)
    if score < 0:
        foot = _footer_actions(("查看詳情", f"詳情 {code}"), ("ATR 停損", f"停損 {code}"), ("市場速覽", "匯率"))
    elif score > 0:
        foot = _footer_actions(("查看詳情", f"詳情 {code}"), ("回測", f"回測 {code}"), ("強弱排行", "強弱"))
    else:
        foot = _footer_actions(("查看詳情", f"詳情 {code}"), ("停損", f"停損 {code}"), ("訊號比較", "訊號"))

    return FlexBubble(
        size="mega",
        styles=_styles(),
        header=FlexBox(
            layout="vertical",
            spacing="xs",
            padding_all="18px",
            contents=[
                FlexText(text=BRAND, size="xxs", color=ACCENT_SOFT, weight="bold"),
                FlexText(text=f"{code} / TWD", size="xl", color=WHITE, weight="bold"),
                FlexText(text=currency_name, size="xs", color=ACCENT_SOFT),
            ],
        ),
        hero=hero,
        body=FlexBox(layout="vertical", spacing="sm", padding_all="18px", contents=body),
        footer=foot,
    )


def build_rate_detail_flex(
    result: dict,
    currency_name: str,
    chart_url: Optional[str] = None,
) -> FlexBubble:
    """詳情卡：五維評分 + 指標。"""
    r = result["rate"]
    t = result["tech"]
    code = r["currency"]
    change = t.get("change_pct")
    body: list[Any] = [
        FlexText(text=f"{r['spot_sell']:.4f} TWD", size="xl", weight="bold", color=INK),
        FlexText(
            text=f"{change:+.2f}%" if change is not None else "—",
            size="sm",
            color=_change_color(change),
            weight="bold",
        ),
    ]
    note = _conflict_note(result)
    if note:
        body.append(FlexText(text=note, size="xs", color=NEUTRAL, wrap=True, margin="sm"))

    detail = result.get("signal_detail")
    if detail and detail.get("items"):
        body.append(FlexSeparator(margin="lg", color=LINE))
        body.append(
            FlexText(
                text=f"五維評分 {detail['total_score']:+d} · {detail['mood']}",
                size="sm",
                weight="bold",
                color=INK,
            )
        )
        for it in detail["items"]:
            body.append(
                _kv_row(it["name"], f"{it['verdict']} ({it['score']:+d})", _mood_color(it["score"]))
            )
        if detail.get("summary"):
            body.append(FlexText(text=detail["summary"], size="xs", color=MUTED, wrap=True, margin="md"))

    body.append(FlexSeparator(margin="lg", color=LINE))
    body.append(_kv_row("現金賣出", f"{r['cash_sell']:.4f}"))
    if t.get("rsi") is not None:
        body.append(_kv_row("RSI (14)", f"{t['rsi']:.1f}"))
    if t.get("ma20") and t.get("ma50"):
        body.append(_kv_row("MA20 / MA50", f"{t['ma20']:.4f} / {t['ma50']:.4f}"))
    if t.get("dif") is not None and t.get("dea") is not None:
        body.append(_kv_row("MACD", f"{t['dif']:.4f} / {t['dea']:.4f}"))
    body.append(FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True, margin="lg"))

    hero = None
    if chart_url and chart_url.startswith("https://"):
        hero = FlexImage(url=chart_url, size="full", aspect_ratio="20:10", aspect_mode="cover")

    return FlexBubble(
        size="mega",
        styles=_styles(),
        header=FlexBox(
            layout="vertical",
            spacing="xs",
            padding_all="18px",
            contents=[
                FlexText(text=BRAND, size="xxs", color=ACCENT_SOFT, weight="bold"),
                FlexText(text=f"{code} 技術詳情", size="xl", color=WHITE, weight="bold"),
                FlexText(text=f"{currency_name} · {r.get('date', '')}", size="xs", color=ACCENT_SOFT),
            ],
        ),
        hero=hero,
        body=FlexBox(layout="vertical", spacing="sm", padding_all="18px", contents=body),
        footer=_footer_actions(
            ("回到摘要", code),
            ("ATR 停損", f"停損 {code}"),
            ("回測", f"回測 {code}"),
        ),
    )


# 向後相容別名
def build_rate_flex(result: dict, currency_name: str, chart_url: Optional[str] = None) -> FlexBubble:
    return build_rate_summary_flex(result, currency_name, chart_url)


def build_welcome_flex() -> FlexBubble:
    return FlexBubble(
        size="mega",
        styles=_styles(),
        header=FlexBox(
            layout="vertical",
            spacing="xs",
            padding_all="22px",
            contents=[
                FlexText(text=BRAND, size="xs", color=ACCENT_SOFT, weight="bold"),
                FlexText(text="外匯桌面", size="xxl", color=WHITE, weight="bold"),
                FlexText(text="查價 · 訊號 · 風控，一則訊息搞定", size="xs", color=ACCENT_SOFT),
            ],
        ),
        body=FlexBox(
            layout="vertical",
            spacing="md",
            padding_all="20px",
            contents=[
                FlexText(text="從這裡開始", size="sm", weight="bold", color=INK),
                FlexText(
                    text="點下方按鈕，或直接輸入 USD、匯率、強弱、停損。",
                    size="sm",
                    color=MUTED,
                    wrap=True,
                ),
                FlexSeparator(margin="md", color=LINE),
                FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True),
            ],
        ),
        footer=_footer_actions(
            ("查美元匯率", "USD"),
            ("市場速覽", "匯率"),
            ("使用說明", "說明"),
        ),
    )


def build_market_flex(results: dict[str, dict], order: list[str]) -> FlexBubble:
    rows: list[Any] = [
        FlexText(text="主要貨幣對台幣 · 點幣別代號可再查", size="xs", color=MUTED),
        FlexSeparator(margin="md", color=LINE),
    ]
    for code in order:
        result = results.get(code) or {"error": "無資料"}
        if "error" in result:
            rows.append(_kv_row(code, "暫無報價", MUTED))
            continue
        r = result["rate"]
        change = result["tech"].get("change_pct")
        change_s = f"{change:+.2f}%" if change is not None else ""
        rows.append(_kv_row(code, f"{r['spot_sell']:.4f}  {change_s}".rstrip(), _change_color(change)))
    rows.append(FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True, margin="lg"))
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
        body=FlexBox(layout="vertical", spacing="md", padding_all="20px", contents=rows),
        footer=_footer_actions(("強弱排行", "強弱"), ("訊號比較", "訊號"), ("查美元", "USD")),
    )


def build_help_carousel() -> FlexCarousel:
    """說明分三頁：查價 / 市場 / 風控。"""
    pages = [
        (
            "查價",
            [
                ("USD / 美元", "摘要卡 + 日K"),
                ("詳情 USD", "五維評分明細"),
                ("分析 日圓", "同查價"),
            ],
            [("查美元", "USD"), ("詳情 USD", "詳情 USD")],
        ),
        (
            "市場",
            [
                ("匯率 / 貨幣", "市場速覽"),
                ("強弱", "漲跌排行"),
                ("訊號", "多幣評分"),
                ("相關 / 情緒", "關聯與情緒"),
            ],
            [("市場速覽", "匯率"), ("強弱排行", "強弱")],
        ),
        (
            "風控研究",
            [
                ("停損 USD", "ATR 停損停利"),
                ("凱利", "倉位建議"),
                ("槓桿", "槓桿風險"),
                ("回測 USD", "MA 交叉回測"),
                ("加入 USD", "觀察清單"),
            ],
            [("停損", "停損"), ("回測", "回測")],
        ),
    ]
    bubbles = []
    for title, rows, foots in pages:
        body = [FlexSeparator(margin="none", color=LINE)]
        for a, b in rows:
            body.append(_kv_row(a, b))
        body.append(FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True, margin="lg"))
        bubbles.append(
            FlexBubble(
                size="kilo",
                styles=_styles(),
                header=FlexBox(
                    layout="vertical",
                    padding_all="16px",
                    contents=[
                        FlexText(text=BRAND, size="xxs", color=ACCENT_SOFT, weight="bold"),
                        FlexText(text=title, size="lg", color=WHITE, weight="bold"),
                    ],
                ),
                body=FlexBox(layout="vertical", spacing="sm", padding_all="16px", contents=body),
                footer=_footer_actions(*foots),
            )
        )
    return FlexCarousel(contents=bubbles)


def build_help_flex() -> FlexCarousel:
    return build_help_carousel()


def build_error_flex(title: str, detail: str, hint: str = "輸入「說明」查看指令") -> FlexBubble:
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
                FlexText(text=hint, size="xs", color=ACCENT, wrap=True),
            ],
        ),
        footer=_footer_actions(("使用說明", "說明"), ("市場速覽", "匯率"), ("查美元", "USD")),
    )


def build_hint_carousel() -> FlexCarousel:
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


def build_signals_flex(rows: list[dict]) -> FlexBubble:
    body: list[Any] = [
        FlexText(text="五維評分 · 分數越高越偏多", size="xs", color=MUTED),
        FlexSeparator(margin="md", color=LINE),
    ]
    for i, row in enumerate(rows[:12], 1):
        score = row["total_score"]
        prefix = f"#{i} " if i <= 3 else ""
        body.append(
            _kv_row(
                f"{prefix}{row['code']}",
                f"{row['mood']} ({score:+d})",
                _mood_color(score),
            )
        )
    body.append(FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True, margin="lg"))
    top = rows[0]["code"] if rows else "USD"
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
        footer=_footer_actions((f"查 {top}", top), ("強弱排行", "強弱"), ("市場", "匯率")),
    )


def build_ranking_flex(rows: list[dict]) -> FlexBubble:
    body: list[Any] = [
        FlexText(text="日漲跌幅 · 前三名強調", size="xs", color=MUTED),
        FlexSeparator(margin="md", color=LINE),
    ]
    for i, row in enumerate(rows[:12], 1):
        ch = row["change_pct"]
        label = f"{'▲' if i <= 3 else ''}{i}. {row['code']}".lstrip("▲") if i > 3 else f"TOP{i} {row['code']}"
        if i <= 3:
            label = f"TOP{i} {row['code']}"
        else:
            label = f"{i}. {row['code']}"
        body.append(_kv_row(label, f"{row['rate']:.4f}  {ch:+.2f}%", _change_color(ch)))
    body.append(FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True, margin="lg"))
    top = rows[0]["code"] if rows else "USD"
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
        footer=_footer_actions((f"查 {top}", top), ("訊號比較", "訊號"), ("市場", "匯率")),
    )


def build_atr_flex(code: str, name: str, stops: dict) -> FlexBubble:
    direction = "做多" if stops["direction"] == "long" else "做空"
    body = [
        _kv_row("方向", direction),
        _kv_row("進場參考", f"{stops['entry']:.4f}"),
        _kv_row("ATR(14)", f"{stops['atr']:.4f}"),
        FlexSeparator(margin="md", color=LINE),
        _kv_row("建議停損", f"{stops['stop_loss']:.4f}", DOWN),
        _kv_row("建議停利", f"{stops['take_profit']:.4f}", UP),
        _kv_row("停損 / 停利", f"{stops['stop_pct']:.2f}% / {stops['profit_pct']:.2f}%"),
        _kv_row("風險報酬", f"1 : {stops['rr']:.1f}"),
        FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True, margin="lg"),
    ]
    other = "停損空" if stops["direction"] == "long" else "停損"
    other_txt = f"停損空 {code}" if stops["direction"] == "long" else f"停損 {code}"
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
        footer=_footer_actions(("再查匯率", code), (other, other_txt), ("凱利", "凱利")),
    )


def build_kelly_flex(data: dict) -> FlexBubble:
    viable = "可行" if data["viable"] else "不建議（f*≤0）"
    body = [
        _kv_row("勝率 / 盈虧比", f"{data['win_rate']*100:.0f}% / {data['payoff']:.2f}"),
        _kv_row("總資金", f"{data['capital']:.0f}"),
        FlexSeparator(margin="md", color=LINE),
        _kv_row("半凱利（建議）", f"{data['half_kelly_pct']:.1f}% · {data['half_kelly_amount']:.0f}", ACCENT),
        _kv_row("全凱利", f"{data['kelly_pct']:.1f}% · {data['kelly_amount']:.0f}"),
        _kv_row("評估", viable),
        FlexText(text="進階：凱利 0.6 2 10000", size="xxs", color=MUTED, wrap=True, margin="lg"),
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
                FlexText(text="建議使用半凱利", size="xs", color=ACCENT_SOFT),
            ],
        ),
        body=FlexBox(layout="vertical", spacing="sm", padding_all="20px", contents=body),
        footer=_footer_actions(("槓桿風險", "槓桿"), ("停損", "停損"), ("說明", "說明")),
    )


def build_leverage_flex(data: dict) -> FlexBubble:
    body = [
        _kv_row("本金 / 槓桿", f"{data['capital']:.0f} / {data['leverage']}x"),
        _kv_row("持倉市值", f"{data['position_value']:.0f}"),
        _kv_row("強平波動", f"{data['liquidation_move_pct']:.2f}%", DOWN),
        _kv_row("風險等級", data["risk_level"], DOWN if data["leverage"] > 20 else NEUTRAL),
    ]
    if data.get("atr_days") is not None:
        body.append(_kv_row("約達強平(ATR日)", f"{data['atr_days']:.1f} 日"))
    body.append(FlexText(text="範例：槓桿 20 或 槓桿 20 USD", size="xxs", color=MUTED, wrap=True, margin="lg"))
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
                FlexText(text="強平距離估算", size="xs", color=ACCENT_SOFT),
            ],
        ),
        body=FlexBox(layout="vertical", spacing="sm", padding_all="20px", contents=body),
        footer=_footer_actions(("凱利", "凱利"), ("停損", "停損"), ("說明", "說明")),
    )


def build_corr_flex(matrix: dict[str, dict[str, float]], codes: list[str]) -> FlexBubble:
    """只顯示與 USD 相關 + 最強／最弱各幾對。"""
    pairs: list[tuple[str, str, float]] = []
    for i, a in enumerate(codes):
        for b in codes[i + 1 :]:
            if a in matrix and b in matrix[a]:
                pairs.append((a, b, matrix[a][b]))
    pairs.sort(key=lambda x: x[2], reverse=True)

    body: list[Any] = [
        FlexText(text="精簡版：與 USD 相關 + 極端相關對", size="xs", color=MUTED, wrap=True),
        FlexSeparator(margin="md", color=LINE),
        FlexText(text="相對 USD", size="sm", weight="bold", color=INK),
    ]
    usd_pairs = [(a, b, v) for a, b, v in pairs if a == "USD" or b == "USD"]
    for a, b, v in usd_pairs[:7]:
        other = b if a == "USD" else a
        body.append(_kv_row(f"USD-{other}", f"{v:+.2f}", UP if v >= 0 else DOWN))

    body.append(FlexSeparator(margin="md", color=LINE))
    body.append(FlexText(text="最高相關", size="sm", weight="bold", color=INK))
    for a, b, v in pairs[:3]:
        body.append(_kv_row(f"{a}-{b}", f"{v:+.2f}", UP if v >= 0 else DOWN))
    body.append(FlexText(text="最低相關", size="sm", weight="bold", color=INK, margin="md"))
    for a, b, v in pairs[-3:]:
        body.append(_kv_row(f"{a}-{b}", f"{v:+.2f}", UP if v >= 0 else DOWN))

    if not pairs:
        body.append(FlexText(text="相關資料不足（樣本重疊日過少）", size="sm", color=MUTED, wrap=True))
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
                FlexText(text="熱力圖精簡文字版", size="xs", color=ACCENT_SOFT),
            ],
        ),
        body=FlexBox(layout="vertical", spacing="sm", padding_all="20px", contents=body),
        footer=_footer_actions(("強弱排行", "強弱"), ("市場速覽", "匯率"), ("說明", "說明")),
    )


def build_backtest_flex(code: str, name: str, summary: dict) -> FlexBubble:
    if "error" in summary:
        return build_error_flex("回測失敗", summary["error"], "請換幣別或稍後再試")
    body = [
        _kv_row("策略", summary.get("note", "MA 交叉")[:28]),
        _kv_row("交易 / 勝率", f"{summary['trades']} / {summary['win_rate']:.1f}%"),
        _kv_row("總報酬", f"{summary['total_return_pct']:+.2f}%", _change_color(summary["total_return_pct"])),
        _kv_row("最大回撤", f"{summary['max_drawdown_pct']:.2f}%", DOWN),
        _kv_row("期末資金", f"{summary['final_equity']:.0f}"),
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
                FlexText(text=f"回測 · {code}", size="xl", color=WHITE, weight="bold"),
                FlexText(text=name, size="xs", color=ACCENT_SOFT),
            ],
        ),
        body=FlexBox(layout="vertical", spacing="sm", padding_all="20px", contents=body),
        footer=_footer_actions(("再查匯率", code), ("停損", f"停損 {code}"), ("訊號", "訊號")),
    )


def build_sentiment_flex(rows: list[dict]) -> FlexBubble:
    body: list[Any] = [
        FlexText(text="技術面情緒（非新聞）", size="xs", color=MUTED),
        FlexSeparator(margin="md", color=LINE),
    ]
    for i, row in enumerate(rows, 1):
        label = f"TOP{i} {row['code']}" if i <= 3 else row["code"]
        body.append(
            _kv_row(label, f"{row['text']} ({row['score']:+d})", _mood_color(row["score"]))
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


def build_watchlist_flex(codes: list[str], names: dict[str, str]) -> FlexBubble:
    if not codes:
        body = [
            FlexText(text="清單是空的", size="sm", color=MUTED, wrap=True),
            FlexText(text="輸入「加入 USD」將幣別加入觀察清單。", size="xs", color=ACCENT, wrap=True),
        ]
    else:
        body = [FlexText(text=f"共 {len(codes)} 幣", size="xs", color=MUTED), FlexSeparator(margin="md", color=LINE)]
        for c in codes:
            body.append(_kv_row(c, names.get(c, c)))
        body.append(FlexText(text="輸入「移除 USD」可移除。", size="xxs", color=MUTED, margin="md"))
    body.append(FlexText(text=DISCLAIMER, size="xxs", color=ACCENT_SOFT, wrap=True, margin="lg"))
    first = codes[0] if codes else "USD"
    return FlexBubble(
        size="mega",
        styles=_styles(),
        header=FlexBox(
            layout="vertical",
            padding_all="20px",
            spacing="xs",
            contents=[
                FlexText(text=BRAND, size="xxs", color=ACCENT_SOFT, weight="bold"),
                FlexText(text="我的觀察清單", size="xl", color=WHITE, weight="bold"),
                FlexText(text="記憶至服務重啟前", size="xs", color=ACCENT_SOFT),
            ],
        ),
        body=FlexBox(layout="vertical", spacing="sm", padding_all="20px", contents=body),
        footer=_footer_actions((f"查 {first}", first), ("加入 USD", "加入 USD"), ("市場", "匯率")),
    )
