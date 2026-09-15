"""
Telegram 專用 UI / UX

HTML 格式訊息 + Inline / Reply Keyboard。
"""

from __future__ import annotations

import html
from typing import Any, Optional

from bot_core import BotReply

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
    return _rkb(
        [
            ["匯率", "強弱", "訊號"],
            ["訂閱", "我的訂閱", "說明"],
            ["USD", "JPY", "EUR", "GBP"],
        ]
    )


def currency_inline(code: str) -> dict:
    return _ikb(
        [
            [("詳情", f"詳情 {code}"), ("停損", f"停損 {code}"), ("回測", f"回測 {code}")],
            [("加入清單", f"加入 {code}"), ("我的訂閱", "我的訂閱"), ("市場", "匯率")],
            [("USD", "USD"), ("JPY", "JPY"), ("EUR", "EUR"), ("說明", "說明")],
        ]
    )


def market_inline() -> dict:
    return _ikb(
        [
            [("USD", "USD"), ("JPY", "JPY"), ("EUR", "EUR"), ("GBP", "GBP")],
            [("強弱", "強弱"), ("訊號", "訊號"), ("情緒", "情緒")],
            [("訂閱", "訂閱"), ("我的訂閱", "我的訂閱"), ("說明", "說明")],
        ]
    )


def tools_inline(code: str = "USD") -> dict:
    return _ikb(
        [
            [("停損", f"停損 {code}"), ("回測", f"回測 {code}"), ("凱利", "凱利")],
            [("槓桿", "槓桿"), (code, code), ("市場", "匯率")],
            [("說明", "說明")],
        ]
    )


def home_inline() -> dict:
    return _ikb(
        [
            [("匯率速覽", "匯率"), ("強弱排行", "強弱"), ("訊號比較", "訊號")],
            [("訂閱推播", "訂閱"), ("我的訂閱", "我的訂閱"), ("推送測試", "推送測試")],
            [("USD", "USD"), ("JPY", "JPY"), ("EUR", "EUR")],
        ]
    )


def subscribe_inline() -> dict:
    return _ikb(
        [
            [("推送測試", "推送測試"), ("我的訂閱", "我的訂閱")],
            [("取消訂閱", "取消訂閱"), ("匯率", "匯率")],
            [("監視 USD>32", "監視 USD > 32"), ("說明", "說明")],
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


def format_welcome() -> str:
    return (
        "<b>FOREX DESK</b>\n"
        "台銀牌告 · 技術面速覽\n\n"
        "輸入幣別如 <code>USD</code>，或點下方按鈕。\n\n"
        "<b>自動推播</b>\n"
        "· <code>訂閱</code> — 每日台北 09:00 匯率\n"
        "· <code>監視 USD &gt; 32</code> — 價格觸發通知\n"
        "· <code>推送測試</code> — 立即預覽推播內容\n\n"
        "<i>僅供參考，非投資建議。</i>"
    )


def format_help() -> str:
    return (
        "<b>指令一覽</b>\n\n"
        "<b>行情</b>\n"
        "· 幣別代碼 → 摘要＋K線\n"
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
        "<i>僅供參考，非投資建議。</i>"
    )


def format_plain_card(title: str, body: str) -> str:
    lines = [ln for ln in body.splitlines() if ln.strip()]
    body_html = "\n".join(_esc(ln) for ln in lines)
    return f"<b>{_esc(title)}</b>\n\n{body_html}\n\n<i>僅供參考，非投資建議。</i>"


def format_rate_card(result: dict, name: str, detail: bool = False) -> str:
    r = result["rate"]
    t = result.get("tech") or {}
    code = r["currency"]
    change = t.get("change_pct")
    ch_s = f"{change:+.2f}%" if change is not None else "—"
    mood = _esc(result.get("mood", ""))
    lines = [
        f"<b>{_esc(code)} / TWD</b>  ·  {_esc(name)}",
        f"<b>{r['spot_sell']:.4f}</b>  {_change_emoji(change)} {_esc(ch_s)}",
        f"{mood}",
        f"資料 {_esc(r.get('date', ''))}",
    ]
    score = result.get("score", 0)
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
        lines.append("<b>即期</b>")
        lines.append(f"買 {_esc(sb)}  賣 {_esc(ss)}")
        lines.append("<b>現金</b>")
        lines.append(f"買 {_esc(cb)}  賣 {_esc(cs)}")
        detail_sig = result.get("signal_detail") or {}
        if detail_sig:
            lines.append("")
            lines.append(f"<b>評分</b> {detail_sig.get('total_score', score):+d}")
            for s in (result.get("signals") or [])[:6]:
                lines.append(f"· {_esc(s)}")

    lines.append("")
    lines.append("<i>僅供參考，非投資建議。</i>")
    return "\n".join(lines)


def format_from_reply(reply: BotReply) -> str:
    kind = getattr(reply, "kind", None)
    if kind == "welcome":
        return format_welcome()
    if kind == "help":
        return format_help()
    if kind in ("subscribe", "alert", "subscriptions", "push_test"):
        # push_test 的 text_fallback 已是 HTML
        if kind == "push_test":
            raw = (reply.text_fallback or "").strip()
            if raw.startswith("<b>"):
                return raw
        return format_plain_card(
            reply.alt_text or "FOREX DESK",
            reply.text_fallback or "",
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

    title = _esc(reply.alt_text or "FOREX DESK")
    lines = raw.splitlines()
    if len(lines) > 1:
        body_lines = (
            lines[1:]
            if lines[0] == (reply.alt_text or "") or lines[0] in ("市場速覽", "清單：")
            else lines
        )
        if lines[0].startswith("清單"):
            body_lines = lines
        body_lines = [ln for ln in body_lines if ln.strip()][:40]
        formatted = "\n".join(f"<code>{_esc(ln)}</code>" for ln in body_lines)
        return f"<b>{title}</b>\n\n{formatted}\n\n<i>僅供參考，非投資建議。</i>"

    body = _esc(raw)
    if raw == (reply.alt_text or ""):
        return f"<b>{title}</b>\n\n<i>僅供參考，非投資建議。</i>"
    return f"<b>{title}</b>\n\n{body}\n\n<i>僅供參考，非投資建議。</i>"


def keyboard_for(reply: BotReply) -> dict:
    kind = getattr(reply, "kind", None)
    if kind in ("subscribe", "subscriptions", "alert", "push_test"):
        return subscribe_inline()
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
        payload["photo_caption"] = _esc(reply.alt_text or "")[:900]
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
        }
        if name in mapping:
            return mapping[name]
        if len(cmd) > 1:
            return f"{name} {cmd[1]}".strip()
        return name
    return t
