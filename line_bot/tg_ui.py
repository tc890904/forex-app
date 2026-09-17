"""
Telegram 專用 UI / UX

HTML 格式訊息 + Inline / Reply Keyboard。
著重掃讀、分組鍵盤、錯誤引導與推播狀態可讀性。
"""

from __future__ import annotations

import html
from typing import Any, Optional

from bot_core import BotReply

# —— 幣別旗幟（掃讀用）—————————————————————————————————————

_FLAGS: dict[str, str] = {
    "TWD": "🇹🇼",
    "USD": "🇺🇸",
    "JPY": "🇯🇵",
    "EUR": "🇪🇺",
    "GBP": "🇬🇧",
    "AUD": "🇦🇺",
    "CAD": "🇨🇦",
    "CHF": "🇨🇭",
    "CNY": "🇨🇳",
    "HKD": "🇭🇰",
    "SGD": "🇸🇬",
    "NZD": "🇳🇿",
    "SEK": "🇸🇪",
    "ZAR": "🇿🇦",
    "THB": "🇹🇭",
    "PHP": "🇵🇭",
    "IDR": "🇮🇩",
    "KRW": "🇰🇷",
    "VND": "🇻🇳",
    "MYR": "🇲🇾",
}


def _flag(code: str) -> str:
    return _FLAGS.get((code or "").upper(), "💱")


# —— 鍵盤 ——————————————————————————————————————————————


def _ikb(rows: list[list[tuple[str, str]]]) -> dict:
    return {
        "inline_keyboard": [
            [{"text": lab, "callback_data": cb[:64]} for lab, cb in row]
            for row in rows
        ]
    }


def _rkb(rows: list[list[str]], resize: bool = True) -> dict:
    return {
        "keyboard": [[{"text": t} for t in row] for row in rows],
        "resize_keyboard": resize,
        "is_persistent": True,
    }


def home_reply_keyboard() -> dict:
    """底部常駐鍵盤：行情 / 推播 / 常用幣別，各一列。"""
    return _rkb(
        [
            ["匯率", "強弱", "100USD"],
            ["訂閱", "我的訂閱", "說明"],
            ["USD", "JPY", "EUR", "GBP"],
        ]
    )


def currency_inline(code: str) -> dict:
    """單幣情境：分析工具 → 清單／推播 → 切幣。"""
    c = (code or "USD").upper()
    return _ikb(
        [
            [("詳情", f"詳情 {c}"), ("停損", f"停損 {c}"), ("回測", f"回測 {c}")],
            [("加入清單", f"加入 {c}"), (f"100{c} 換匯", f"100{c}"), ("市場", "匯率")],
            [
                (f"{_flag('USD')} USD", "USD"),
                (f"{_flag('JPY')} JPY", "JPY"),
                (f"{_flag('EUR')} EUR", "EUR"),
            ],
        ]
    )


def market_inline() -> dict:
    return _ikb(
        [
            [
                (f"{_flag('USD')} USD", "USD"),
                (f"{_flag('JPY')} JPY", "JPY"),
                (f"{_flag('EUR')} EUR", "EUR"),
                (f"{_flag('GBP')} GBP", "GBP"),
            ],
            [("強弱排行", "強弱"), ("訊號比較", "訊號"), ("100USD 換匯", "100USD")],
            [("訂閱推播", "訂閱"), ("我的訂閱", "我的訂閱"), ("說明", "說明")],
        ]
    )


def tools_inline(code: str = "USD") -> dict:
    c = (code or "USD").upper()
    return _ikb(
        [
            [("停損", f"停損 {c}"), ("回測", f"回測 {c}"), ("凱利", "凱利")],
            [("槓桿", "槓桿"), (f"查 {c}", c), ("市場", "匯率")],
            [("說明", "說明"), ("訂閱", "訂閱")],
        ]
    )


def home_inline() -> dict:
    return _ikb(
        [
            [("匯率速覽", "匯率"), ("強弱排行", "強弱"), ("100USD 換匯", "100USD")],
            [("訂閱推播", "訂閱"), ("我的訂閱", "我的訂閱"), ("說明", "說明")],
            [
                (f"{_flag('USD')} USD", "USD"),
                (f"{_flag('JPY')} JPY", "JPY"),
                (f"{_flag('EUR')} EUR", "EUR"),
            ],
        ]
    )


def subscribe_inline(daily_on: Optional[bool] = None) -> dict:
    """訂閱情境鍵盤；依狀態顯示開關文案。"""
    if daily_on is True:
        daily_btn = ("取消每日訂閱", "取消訂閱")
    elif daily_on is False:
        daily_btn = ("開啟每日訂閱", "訂閱")
    else:
        daily_btn = ("訂閱／取消", "訂閱")
    return _ikb(
        [
            [("推送測試", "推送測試"), ("我的訂閱", "我的訂閱")],
            [daily_btn, ("匯率速覽", "匯率")],
            [("監視 USD>32", "監視 USD > 32"), ("說明", "說明")],
        ]
    )


def convert_inline(src: str = "USD") -> dict:
    c = (src or "USD").upper()
    if c == "TWD":
        c = "USD"
    return _ikb(
        [
            [("100USD", "100USD"), ("100JPY", "100JPY"), ("100EUR", "100EUR")],
            [("10000TWD", "10000TWD"), (f"100{c}", f"100{c}"), ("市場", "匯率")],
            [("說明", "說明"), (f"查 {c}", c)],
        ]
    )


def error_inline(hint_code: str = "USD") -> dict:
    c = (hint_code or "USD").upper()
    return _ikb(
        [
            [("說明", "說明"), ("匯率", "匯率"), (f"查 {c}", c)],
            [("訂閱", "訂閱"), ("我的訂閱", "我的訂閱")],
        ]
    )


# —— 格式化 ——————————————————————————————————————————————


def _esc(s: Any) -> str:
    return html.escape(str(s) if s is not None else "", quote=False)


def _change_emoji(change: Optional[float]) -> str:
    if change is None:
        return "·"
    if change > 0:
        return "▲"
    if change < 0:
        return "▼"
    return "—"


def _disclaimer() -> str:
    return "<i>僅供參考，非投資建議。</i>"


def format_welcome() -> str:
    return (
        "<b>FOREX DESK</b>\n"
        "台銀牌告 · 技術面速覽\n\n"
        "<b>快速開始</b>\n"
        "1. 點下方幣別，或輸入 <code>USD</code>\n"
        "2. 輸入 <code>100USD</code> 即時換成各幣別\n"
        "3. 「訂閱」開啟每日 09:00 推播\n\n"
        "<b>推播</b>\n"
        "· <code>訂閱</code> — 每日台北 09:00 主要匯率\n"
        "· <code>監視 USD &gt; 32</code> — 價格觸發\n"
        "· <code>推送測試</code> — 立刻預覽推播內容\n\n"
        f"{_disclaimer()}"
    )


def format_help() -> str:
    return (
        "<b>指令一覽</b>\n\n"
        "<b>行情</b>\n"
        "· 幣別代碼 → 摘要＋K線\n"
        "· <code>100USD</code> <code>100 美元</code> <code>10000TWD</code> → 即時換匯\n"
        "· <code>詳情</code> <code>匯率</code> <code>強弱</code>\n"
        "· <code>訊號</code> <code>情緒</code> <code>相關</code>\n\n"
        "<b>工具</b>\n"
        "· <code>停損 USD</code> <code>回測 USD</code>\n"
        "· <code>凱利</code> <code>槓桿 10</code>\n\n"
        "<b>清單</b>\n"
        "· <code>加入 USD</code> <code>我的清單</code>\n\n"
        "<b>推播</b>\n"
        "· <code>訂閱</code> / <code>取消訂閱</code>\n"
        "· <code>監視 USD &gt; 32</code>\n"
        "· <code>我的訂閱</code> <code>推送測試</code>\n\n"
        f"{_disclaimer()}"
    )


def format_plain_card(title: str, body: str, hint: str = "") -> str:
    lines = [ln for ln in body.splitlines() if ln.strip()]
    body_html = "\n".join(_esc(ln) for ln in lines)
    parts = [f"<b>{_esc(title)}</b>", "", body_html]
    if hint:
        parts.extend(["", f"<i>{_esc(hint)}</i>"])
    parts.extend(["", _disclaimer()])
    return "\n".join(parts)


def format_error_card(title: str, body: str, next_step: str = "") -> str:
    parts = [
        f"<b>{_esc(title)}</b>",
        "",
        _esc(body).strip() or "發生錯誤，請稍後再試。",
    ]
    if next_step:
        parts.extend(["", f"<b>下一步</b>\n{_esc(next_step)}"])
    else:
        parts.extend(["", "<b>下一步</b>\n輸入「說明」或幣別代碼如 <code>USD</code>"])
    parts.extend(["", _disclaimer()])
    return "\n".join(parts)


def format_rate_card(result: dict, name: str, detail: bool = False) -> str:
    r = result["rate"]
    t = result.get("tech") or {}
    code = r["currency"]
    change = t.get("change_pct")
    ch_s = f"{change:+.2f}%" if change is not None else "—"
    mood = _esc(result.get("mood", ""))
    score = result.get("score", 0)
    score_s = f"{score:+d}" if isinstance(score, (int, float)) else "—"

    lines = [
        f"{_flag(code)} <b>{_esc(code)} / TWD</b>  ·  {_esc(name)}",
        f"<b>{r['spot_sell']:.4f}</b>  {_change_emoji(change)} {_esc(ch_s)}",
        f"情緒 {mood}  ·  評分 <b>{_esc(score_s)}</b>",
        f"資料 {_esc(r.get('date', ''))}",
    ]

    if change is not None:
        if change > 0 and score < 0:
            lines.append("日線上漲，但中期技術面偏空")
        elif change < 0 and score > 0:
            lines.append("日線下跌，但中期技術面偏多")

    if detail:
        sb = f"{float(r.get('spot_buy') or 0):.4f}"
        ss = f"{float(r.get('spot_sell') or 0):.4f}"
        cb = f"{float(r.get('cash_buy') or 0):.4f}"
        cs = f"{float(r.get('cash_sell') or 0):.4f}"
        lines.append("")
        lines.append(f"<b>即期</b>  買 {_esc(sb)}  賣 {_esc(ss)}")
        lines.append(f"<b>現金</b>  買 {_esc(cb)}  賣 {_esc(cs)}")
        detail_sig = result.get("signal_detail") or {}
        if detail_sig:
            lines.append("")
            lines.append(f"<b>評分明細</b> {detail_sig.get('total_score', score):+d}")
            for s in (result.get("signals") or [])[:6]:
                lines.append(f"· {_esc(s)}")

    lines.extend(["", _disclaimer()])
    return "\n".join(lines)


def format_list_card(title: str, rows: list[str], footer: str = "") -> str:
    body = "\n".join(f"<code>{_esc(ln)}</code>" for ln in rows if ln.strip())
    parts = [f"<b>{_esc(title)}</b>", "", body or "（無資料）"]
    if footer:
        parts.extend(["", _esc(footer)])
    parts.extend(["", _disclaimer()])
    return "\n".join(parts)


def format_subscriptions_card(body: str) -> str:
    """將「我的訂閱」純文字轉成帶狀態標記的 HTML。"""
    lines_in = [ln for ln in (body or "").splitlines() if ln.strip()]
    out: list[str] = ["<b>我的訂閱</b>", ""]
    for ln in lines_in:
        s = ln.strip()
        if s.startswith("我的訂閱"):
            continue
        if "每日匯率" in s:
            on = "已開啟" in s
            mark = "✓" if on else "✗"
            out.append(f"{mark} <b>每日匯率</b>")
            out.append(
                "   台北 09:00 · USD/JPY/EUR/GBP"
                if on
                else "   輸入「訂閱」即可開啟"
            )
        elif s.startswith("價格監聽"):
            if "無" in s:
                out.append("✗ <b>價格監聽</b>  ·  無")
            else:
                out.append("✓ <b>價格監聽</b>")
        elif len(s) >= 3 and s[:3].isalpha() and s[:3].isupper():
            code = s[:3].upper()
            out.append(f"   {_flag(code)} {_esc(s)}")
        elif "訂閱" in s or "監視" in s or "推送" in s:
            continue
        else:
            out.append(_esc(s))
    out.extend(
        [
            "",
            "快速操作：下方按鈕，或輸入",
            "· <code>監視 USD &gt; 32</code>",
            "· <code>取消監視 USD &gt; 32</code>",
            "",
            _disclaimer(),
        ]
    )
    return "\n".join(out)


def format_convert_card(data: dict) -> str:
    src = data.get("src") or ""
    src_disp = data.get("src_display") or ""
    date = data.get("date") or ""
    lines = [
        "<b>即時換匯</b>",
        f"{_flag(src)} <b>{_esc(src_disp)} {_esc(src)}</b>  ·  {_esc(data.get('src_name') or '')}",
        f"台銀即期賣出交叉 · {_esc(date)}",
        "",
    ]
    for row in data.get("rows") or []:
        code = row.get("code") or ""
        disp = row.get("display") or "—"
        name = row.get("name") or ""
        lines.append(
            f"{_flag(code)} <b>{_esc(code)}</b>  {_esc(name)}  <code>{_esc(disp)}</code>"
        )
    lines.extend(
        [
            "",
            "再試 <code>100JPY</code>、<code>10000TWD</code>",
            "",
            _disclaimer(),
        ]
    )
    return "\n".join(lines)


def format_from_reply(reply: BotReply) -> str:
    kind = getattr(reply, "kind", None)
    if kind == "welcome":
        return format_welcome()
    if kind == "help":
        return format_help()
    if kind == "error":
        return format_error_card(
            reply.alt_text or "無法完成",
            reply.text_fallback or "",
            next_step="",
        )
    if kind == "subscriptions":
        return format_subscriptions_card(reply.text_fallback or "")
    if kind == "convert":
        data = getattr(reply, "_convert_result", None)
        if data and "rows" in data:
            return format_convert_card(data)
        return format_plain_card(
            reply.alt_text or "即時換匯",
            reply.text_fallback or "",
            hint="範例：100USD、100 美元、10000TWD",
        )
    if kind in ("subscribe", "alert", "push_test"):
        if kind == "push_test":
            raw = (reply.text_fallback or "").strip()
            if raw.startswith("<b>"):
                return raw
        hint = ""
        if kind == "subscribe":
            hint = "可用「推送測試」預覽，或「我的訂閱」查看狀態"
        elif kind == "alert":
            hint = "觸發後會私訊；輸入「我的訂閱」管理條件"
        return format_plain_card(
            reply.alt_text or "FOREX DESK",
            reply.text_fallback or "",
            hint=hint,
        )

    if reply._rate_result and "error" not in reply._rate_result:
        return format_rate_card(
            reply._rate_result,
            reply._currency_name or "",
            detail=(reply.card_mode == "detail"),
        )

    raw = (reply.text_fallback or reply.alt_text or "").strip()
    if not raw:
        return "（無內容）"

    title = reply.alt_text or "FOREX DESK"
    lines = raw.splitlines()
    if len(lines) > 1:
        body_lines = (
            lines[1:]
            if lines[0] == (reply.alt_text or "") or lines[0] in ("市場速覽", "清單：")
            else lines
        )
        if lines[0].startswith("清單"):
            body_lines = lines
        # 市場速覽：加上旗幟與等寬欄
        if "市場" in title or lines[0] == "市場速覽":
            pretty: list[str] = []
            for ln in body_lines:
                parts = ln.split()
                if parts and len(parts[0]) == 3 and parts[0].isalpha():
                    code = parts[0].upper()
                    rest = " ".join(parts[1:])
                    pretty.append(f"{_flag(code)} <b>{_esc(code)}</b>  {_esc(rest)}")
                elif ln.strip():
                    pretty.append(_esc(ln))
            body = "\n".join(pretty)
            return f"<b>{_esc(title)}</b>\n\n{body}\n\n{_disclaimer()}"

        body_lines = [ln for ln in body_lines if ln.strip()][:40]
        # 強弱／訊號：左側旗幟
        if any(k in title for k in ("強弱", "訊號", "情緒")):
            pretty = []
            for ln in body_lines:
                parts = ln.split()
                if parts and len(parts[0]) == 3 and parts[0].isalpha():
                    code = parts[0].upper()
                    rest = " ".join(parts[1:])
                    arrow = ""
                    if rest.startswith("+"):
                        arrow = "▲ "
                    elif rest.startswith("-"):
                        arrow = "▼ "
                    pretty.append(
                        f"{_flag(code)} <b>{_esc(code)}</b>  {arrow}{_esc(rest)}"
                    )
                else:
                    pretty.append(f"<code>{_esc(ln)}</code>")
            return f"<b>{_esc(title)}</b>\n\n" + "\n".join(pretty) + f"\n\n{_disclaimer()}"

        formatted = "\n".join(f"<code>{_esc(ln)}</code>" for ln in body_lines)
        return f"<b>{_esc(title)}</b>\n\n{formatted}\n\n{_disclaimer()}"

    body = _esc(raw)
    if raw == (reply.alt_text or ""):
        return f"<b>{_esc(title)}</b>\n\n{_disclaimer()}"
    return f"<b>{_esc(title)}</b>\n\n{body}\n\n{_disclaimer()}"


def _daily_on_from_text(text: str) -> Optional[bool]:
    t = text or ""
    if "已取消" in t or "尚未訂閱" in t or "未開啟" in t:
        return False
    if "已訂閱" in t or "已開啟" in t or "09:00" in t:
        return True
    return None


def keyboard_for(reply: BotReply) -> dict:
    kind = getattr(reply, "kind", None)
    if kind == "error":
        return error_inline(reply.last_code or "USD")
    if kind == "convert" or (reply.qr_mode or "") == "convert":
        return convert_inline(reply.last_code or "USD")
    if kind in ("subscribe", "subscriptions", "alert", "push_test"):
        daily = _daily_on_from_text(
            f"{reply.alt_text or ''}\n{reply.text_fallback or ''}"
        )
        if kind == "subscriptions":
            daily = _daily_on_from_text(reply.text_fallback or "")
        return subscribe_inline(daily_on=daily)
    mode = reply.qr_mode or "home"
    code = reply.last_code or "USD"
    if mode == "currency":
        return currency_inline(code)
    if mode == "tools":
        return tools_inline(code)
    if mode == "market":
        return market_inline()
    return home_inline()


def _safe_html_truncate(text: str, limit: int = 3900) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last_lt = cut.rfind("<")
    last_gt = cut.rfind(">")
    if last_lt > last_gt:
        cut = cut[:last_lt]
    return cut.rstrip() + "\n…"


def build_telegram_payload(reply: BotReply) -> dict[str, Any]:
    text = _safe_html_truncate(format_from_reply(reply))
    payload: dict[str, Any] = {
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": keyboard_for(reply),
        "disable_web_page_preview": True,
    }
    if getattr(reply, "kind", None) == "welcome":
        payload["reply_keyboard"] = home_reply_keyboard()

    if reply.chart_bytes:
        payload["photo_bytes"] = reply.chart_bytes
        # 圖說精簡：幣別＋價＋情緒
        cap = _esc(reply.alt_text or "")[:900]
        payload["photo_caption"] = cap
    return payload


def normalize_telegram_text(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "開始"
    if t.startswith("/"):
        cmd = t[1:].split("@", 1)[0].split(None, 1)
        name = (cmd[0] or "").lower()
        mapping = {
            "start": "開始",
            "help": "說明",
            "menu": "說明",
            "rates": "匯率",
            "usd": "USD",
            "jpy": "JPY",
            "eur": "EUR",
            "subscribe": "訂閱",
            "unsubscribe": "取消訂閱",
            "push_test": "推送測試",
            "convert": "換匯",
        }
        if name in mapping:
            mapped = mapping[name]
            if len(cmd) > 1 and name in ("convert", "usd", "jpy", "eur"):
                return f"{mapped} {cmd[1]}".strip()
            return mapped
        if len(cmd) > 1:
            return f"{name} {cmd[1]}".strip()
        return name
    return t
