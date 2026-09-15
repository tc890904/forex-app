"""
LINE Bot Webhook Server

Flex 分析卡 + HTTPS K 線圖（嵌在 Flex hero）。
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

_BOT_DIR = Path(__file__).resolve().parent
load_dotenv(_BOT_DIR / ".env")
load_dotenv()

sys.path.insert(0, str(_BOT_DIR))

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import (
    ImageMessageContent,
    MessageEvent,
    StickerMessageContent,
    TextMessageContent,
)

from bot_core import (
    BotReply,
    get_push_status,
    handle_query,
    schedule_daily_warm,
    start_push_schedulers,
)
from ui import (
    build_error_flex,
    build_rate_detail_flex,
    build_rate_summary_flex,
    contextual_quick_reply,
    default_quick_reply,
    to_flex_message,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

LINE_TEXT_MAX_LEN = 5000

app = Flask(__name__)

IMAGE_DIR = _BOT_DIR / "static" / "charts"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

LINE_CHANNEL_ACCESS_TOKEN = (os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or "").strip()
LINE_CHANNEL_SECRET = (os.getenv("LINE_CHANNEL_SECRET") or "").strip()

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    logger.warning(
        "LINE_CHANNEL_ACCESS_TOKEN or LINE_CHANNEL_SECRET not set — "
        "webhook replies will fail until env vars are configured"
    )
    if os.getenv("RENDER"):
        logger.error(
            "Render 環境缺少 LINE 憑證：請在 Dashboard Environment 設定 "
            "LINE_CHANNEL_ACCESS_TOKEN 與 LINE_CHANNEL_SECRET"
        )

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

SERVER_BASE_URL = (
    os.getenv("SERVER_BASE_URL")
    or os.getenv("RENDER_EXTERNAL_URL")
    or "http://localhost:8080"
).rstrip("/")

# Telegram（與 LINE 共用同一 Flask app）
from tg_api import TelegramSender
from tg_ui import build_telegram_payload, home_inline, normalize_telegram_text

TELEGRAM_WEBHOOK_PATH = os.getenv("TELEGRAM_WEBHOOK_PATH", "/webhook/telegram")
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
TELEGRAM_WEBHOOK_SECRET = (os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()
TELEGRAM_ADMIN_KEY = (os.getenv("TELEGRAM_ADMIN_KEY") or "").strip()
tg_sender = TelegramSender(TELEGRAM_BOT_TOKEN)

if tg_sender.enabled:
    logger.info("Telegram 已啟用 (token: %s...)", TELEGRAM_BOT_TOKEN[:8])
else:
    logger.warning("TELEGRAM_BOT_TOKEN 未設定 — Telegram 無法回覆")
if TELEGRAM_WEBHOOK_SECRET:
    logger.info("Telegram webhook secret 已啟用")
else:
    logger.warning("TELEGRAM_WEBHOOK_SECRET 未設定 — webhook 未驗證來源（建議設定）")

try:
    schedule_daily_warm()
except Exception:
    logger.exception("啟動預熱失敗")

# 啟動通知背景線程（必須 daemon，不可同步跑 while True）
if tg_sender.enabled:
    try:
        start_push_schedulers(tg_sender, schedule_hour=9, schedule_minute=0)
    except Exception:
        logger.exception("啟動通知線程失敗")


def _truncate_text(text: str) -> str:
    if len(text) <= LINE_TEXT_MAX_LEN:
        return text
    return text[: LINE_TEXT_MAX_LEN - 20] + "\n…(內容過長已截斷)"


def save_chart(image_bytes: bytes, currency: str = "chart") -> str:
    """同一幣別當日覆寫，避免磁碟堆積。"""
    safe_cur = "".join(c for c in currency if c.isalnum())[:8] or "chart"
    filename = f"{safe_cur}_{datetime.now().strftime('%Y%m%d')}.png"
    path = IMAGE_DIR / filename
    with open(path, "wb") as f:
        f.write(image_bytes)
    return f"{SERVER_BASE_URL}/static/charts/{filename}"


def _reply(reply_token: str, messages: list) -> None:
    with ApiClient(configuration) as api_client:
        messaging_api = MessagingApi(api_client)
        messaging_api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=messages)
        )


def _qr_for(reply: BotReply):
    return contextual_quick_reply(reply.qr_mode or "home", reply.last_code)


def _rebuild_rate_flex(reply: BotReply, chart_url: str | None):
    if reply._rate_result is None:
        return reply.flex
    name = reply._currency_name or ""
    if reply.card_mode == "detail":
        return build_rate_detail_flex(reply._rate_result, name, chart_url=chart_url)
    return build_rate_summary_flex(reply._rate_result, name, chart_url=chart_url)


def _build_messages(reply: BotReply) -> list:
    """Flex 卡；若有 K 線且為 HTTPS，嵌成 hero。"""
    flex = reply.flex
    qr = _qr_for(reply)

    if reply.chart_bytes and reply._rate_result is not None:
        try:
            chart_url = save_chart(
                reply.chart_bytes,
                currency=reply._rate_result["rate"]["currency"],
            )
            logger.info("K 線已保存: %s", chart_url)
            if chart_url.startswith("https://"):
                flex = _rebuild_rate_flex(reply, chart_url)
            else:
                logger.info("非 HTTPS，Flex 不嵌入 K 線（LINE 要求 https 圖）")
        except Exception:
            logger.exception("掛載 K 線失敗")

    if flex is not None:
        return [
            to_flex_message(
                flex,
                reply.alt_text or "FOREX DESK",
                quick_reply=qr,
            )
        ]
    return [
        TextMessage(
            text=_truncate_text(reply.text_fallback or "（無內容）"),
            quick_reply=qr,
        )
    ]


@app.route("/static/charts/<path:filename>")
def serve_chart(filename: str):
    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename:
        return jsonify({"error": "invalid filename"}), 400
    return send_from_directory(IMAGE_DIR, safe_name)


def _user_id_from_event(event: MessageEvent) -> str | None:
    try:
        src = event.source
        return getattr(src, "user_id", None)
    except Exception:
        return None


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event: MessageEvent) -> None:
    try:
        user_text = event.message.text
        user_id = _user_id_from_event(event)
        logger.info("收到訊息: %s (user=%s)", user_text, user_id)

        reply = handle_query(user_text, user_id=user_id)
        if not isinstance(reply, BotReply):
            reply = BotReply(
                alt_text="訊息",
                flex=None,
                text_fallback=str(reply),
            )

        messages = _build_messages(reply)
        _reply(event.reply_token, messages)
        logger.info("已回覆成功（%d 則）", len(messages))

    except Exception as exc:
        logger.exception("處理訊息時出錯: %s", exc)
        try:
            _reply(
                event.reply_token,
                [
                    to_flex_message(
                        build_error_flex(
                            "暫時無法處理",
                            "伺服器忙碌或資料源異常，請稍後再試。",
                            "也可輸入「說明」查看指令。",
                        ),
                        "暫時無法處理",
                        quick_reply=default_quick_reply(),
                    )
                ],
            )
        except Exception:
            logger.exception("錯誤回覆也失敗")


@handler.add(MessageEvent, message=StickerMessageContent)
@handler.add(MessageEvent, message=ImageMessageContent)
def handle_non_text(event: MessageEvent) -> None:
    """貼圖／圖片：導向歡迎與說明。"""
    try:
        user_id = _user_id_from_event(event)
        reply = handle_query("開始", user_id=user_id)
        _reply(event.reply_token, _build_messages(reply))
    except Exception:
        logger.exception("非文字訊息處理失敗")
        try:
            _reply(
                event.reply_token,
                [
                    TextMessage(
                        text="請輸入幣別代碼（如 USD）或「說明」。",
                        quick_reply=default_quick_reply(),
                    )
                ],
            )
        except Exception:
            logger.exception("非文字錯誤回覆失敗")


@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    if not signature:
        logger.error("Missing X-Line-Signature header")
        return jsonify({"error": "Missing signature"}), 400

    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature")
        return jsonify({"error": "Invalid signature"}), 400
    except Exception as e:
        logger.exception("Webhook processing error: %s", e)
        return jsonify({"status": "ok", "note": "handler error logged"}), 200

    return jsonify({"status": "ok"}), 200


@app.route("/health", methods=["GET"])
def health():
    line_ready = bool(LINE_CHANNEL_ACCESS_TOKEN) and bool(LINE_CHANNEL_SECRET)
    tg_ready = tg_sender.enabled
    # 任一通道就緒即視為存活（避免僅開 TG 時被 Render 判死）
    ready = line_ready or tg_ready
    return jsonify(
        {
            "status": "healthy" if ready else "degraded",
            "ready": ready,
            "service": "forex-line-bot",
            "ui": "flex-ux-v2",
            "line_ready": line_ready,
            "token_set": bool(LINE_CHANNEL_ACCESS_TOKEN),
            "secret_set": bool(LINE_CHANNEL_SECRET),
            "telegram_token_set": tg_ready,
            "telegram_webhook": TELEGRAM_WEBHOOK_PATH,
            "telegram_secret_set": bool(TELEGRAM_WEBHOOK_SECRET),
            "server_base_url": SERVER_BASE_URL,
            "https_charts": SERVER_BASE_URL.startswith("https://"),
            "charts_dir": str(IMAGE_DIR),
            "note": "state is in-memory; keep gunicorn workers=1",
        }
    ), (200 if ready else 503)


@app.route("/", methods=["GET"])
def index():
    return jsonify(
        {
            "service": "forex-line-bot",
            "webhook": "/webhook",
            "health": "/health",
        }
    )


def _test_endpoint_enabled() -> bool:
    if os.getenv("ENABLE_TEST_ENDPOINT", "0") == "1":
        return True
    return not bool(os.getenv("RENDER"))


@app.route("/test", methods=["POST"])
def test():
    if not _test_endpoint_enabled():
        return jsonify({"error": "disabled"}), 404

    data = request.get_json(silent=True)
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' field"}), 400

    text = data["text"]
    user_id = data.get("user_id")
    try:
        reply = handle_query(text, user_id=user_id)
        chart_url = None
        flex = reply.flex
        if reply.chart_bytes and reply._rate_result is not None:
            chart_url = save_chart(
                reply.chart_bytes,
                currency=reply._rate_result["rate"]["currency"],
            )
            # 本機測試也重建 flex（http 則不掛圖）
            flex = _rebuild_rate_flex(
                reply,
                chart_url if chart_url.startswith("https://") else None,
            )

        flex_dict = None
        if flex is not None:
            flex_dict = to_flex_message(
                flex,
                reply.alt_text,
                quick_reply=_qr_for(reply),
            ).to_dict()

        return jsonify(
            {
                "original": text,
                "alt_text": reply.alt_text,
                "reply": reply.text_fallback,
                "card_mode": reply.card_mode,
                "qr_mode": reply.qr_mode,
                "last_code": reply.last_code,
                "has_flex": flex is not None,
                "has_chart": reply.chart_bytes is not None,
                "chart_url": chart_url,
                "flex": flex_dict,
                "success": True,
            }
        )
    except Exception as e:
        logger.exception("Test error: %s", e)
        return jsonify({"error": str(e), "success": False}), 500


# ============================================================
# Telegram Webhook Routes
# ============================================================


def _tg_admin_ok() -> bool:
    """管理 API：若有設 TELEGRAM_ADMIN_KEY 則需帶 X-Admin-Key。"""
    if not TELEGRAM_ADMIN_KEY:
        return True  # 未設密鑰時維持相容（建議正式環境一定要設）
    return request.headers.get("X-Admin-Key", "") == TELEGRAM_ADMIN_KEY


def _tg_secret_ok() -> bool:
    if not TELEGRAM_WEBHOOK_SECRET:
        return True
    return request.headers.get("X-Telegram-Bot-Api-Secret-Token", "") == TELEGRAM_WEBHOOK_SECRET


def _tg_should_handle_chat(chat: dict, message: dict) -> bool:
    """預設僅 private；群組需 @mention 或回覆 bot。"""
    ctype = (chat.get("type") or "private").lower()
    if ctype == "private":
        return True
    text = message.get("text") or ""
    # 指令 /start 在群組也允許
    if text.startswith("/"):
        return True
    entities = message.get("entities") or []
    for ent in entities:
        if ent.get("type") == "mention":
            return True
        if ent.get("type") == "text_mention":
            return True
    # 回覆訊息
    if message.get("reply_to_message"):
        return True
    return False


def _tg_process_text(chat_id: str, user_id: str, text: str) -> None:
    """解析指令 → handle_query → 發送訊息／圖片。"""
    norm = normalize_telegram_text(text)
    logger.info("Telegram 處理: raw=%r norm=%r user=%s chat=%s", text, norm, user_id, chat_id)

    tg_sender.send_chat_action(chat_id, "typing")

    try:
        cid = int(chat_id) if str(chat_id).lstrip("-").isdigit() else None
        reply = handle_query(norm, user_id=f"tg:{user_id}", chat_id=cid)
    except Exception:
        logger.exception("Telegram handle_query 失敗")
        tg_sender.send_message(
            chat_id,
            "暫時無法處理，請稍後再試。\n輸入 <b>說明</b> 查看指令。",
            reply_markup=home_inline(),
        )
        return

    if not isinstance(reply, BotReply):
        reply = BotReply(alt_text="訊息", flex=None, text_fallback=str(reply))

    payload = build_telegram_payload(reply)
    tg_sender.deliver(chat_id, payload)


@app.route(TELEGRAM_WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    """
    Telegram 會 POST update JSON 到此。
    必須呼叫 sendMessage / sendPhoto；回傳給 TG 的 body 不會顯示給使用者。
    """
    if not _tg_secret_ok():
        logger.warning("Telegram webhook secret 不符")
        return jsonify({"ok": False, "error": "forbidden"}), 403

    update = request.get_json(silent=True)
    if not update:
        return jsonify({"ok": False, "error": "empty"}), 400

    if not tg_sender.enabled:
        logger.error("收到 Telegram update 但未設定 TELEGRAM_BOT_TOKEN")
        return jsonify({"ok": False, "error": "token missing"}), 503

    try:
        # 忽略 edited_message（避免重跑昂貴查詢）
        if update.get("edited_message") and not update.get("message"):
            return jsonify({"ok": True, "skipped": "edited"})

        cb = update.get("callback_query")
        if cb:
            cb_id = cb.get("id")
            data = (cb.get("data") or "").strip()
            msg = cb.get("message") or {}
            chat = msg.get("chat") or {}
            user = cb.get("from") or {}
            chat_id = str(chat.get("id") or "")
            user_id = str(user.get("id") or "unknown")
            tg_sender.answer_callback(cb_id or "", "查詢中…")
            if chat_id and data:
                _tg_process_text(chat_id, user_id, data)
            return jsonify({"ok": True})

        message = update.get("message") or {}
        chat = message.get("chat") or {}
        user = message.get("from") or {}
        chat_id = str(chat.get("id") or "")
        user_id = str(user.get("id") or "unknown")
        text = (message.get("text") or "").strip()

        if not chat_id:
            return jsonify({"ok": True, "skipped": "no chat"})

        if not _tg_should_handle_chat(chat, message):
            return jsonify({"ok": True, "skipped": "group_no_mention"})

        if not text:
            # 私訊貼圖／圖片 → 歡迎；群組非文字略過
            if (chat.get("type") or "").lower() == "private":
                _tg_process_text(chat_id, user_id, "開始")
            return jsonify({"ok": True})

        _tg_process_text(chat_id, user_id, text)
        return jsonify({"ok": True})

    except Exception:
        logger.exception("Telegram webhook 未預期錯誤")
        return jsonify({"ok": True, "note": "error logged"})


@app.route("/telegram/health", methods=["GET"])
def telegram_health():
    ready = tg_sender.enabled
    return jsonify(
        {
            "service": "forex-telegram-bot",
            "ready": ready,
            "token_set": ready,
            "webhook_path": TELEGRAM_WEBHOOK_PATH,
            "secret_set": bool(TELEGRAM_WEBHOOK_SECRET),
            "push": get_push_status(),
        }
    ), (200 if ready else 503)


@app.route("/telegram/push_status", methods=["GET"])
def telegram_push_status():
    """推播排程與訂閱統計。"""
    return jsonify(
        {
            "ok": True,
            "telegram_enabled": tg_sender.enabled,
            **get_push_status(),
            "note": (
                "Free 方案若休眠，09:00 可能漏推；"
                "可用外部 cron 打 /health 保活，或輸入「推送測試」驗證內容。"
            ),
        }
    )


@app.route("/telegram/set_webhook", methods=["POST"])
def telegram_set_webhook():
    """POST JSON {\"url\": \"https://.../webhook/telegram\"}；省略 url 則用 SERVER_BASE_URL。"""
    if not _tg_admin_ok():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    if not tg_sender.enabled:
        return jsonify({"ok": False, "error": "TELEGRAM_BOT_TOKEN missing"}), 503
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        url = f"{SERVER_BASE_URL.rstrip('/')}{TELEGRAM_WEBHOOK_PATH}"
    if not url.startswith("https://"):
        return jsonify({"ok": False, "error": "url must be https", "resolved": url}), 400
    payload: dict = {
        "url": url,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": True,
    }
    if TELEGRAM_WEBHOOK_SECRET:
        payload["secret_token"] = TELEGRAM_WEBHOOK_SECRET
    result = tg_sender.call("setWebhook", payload)
    return jsonify({"requested_url": url, **result}), (200 if result.get("ok") else 400)


@app.route("/telegram/webhook_info", methods=["GET"])
def telegram_webhook_info():
    if not _tg_admin_ok():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    if not tg_sender.enabled:
        return jsonify({"ok": False, "error": "token missing"}), 503
    return jsonify(tg_sender.call("getWebhookInfo"))


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
