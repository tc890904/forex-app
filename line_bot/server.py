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

from bot_core import BotReply, handle_query, schedule_daily_warm
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

try:
    schedule_daily_warm()
except Exception:
    logger.exception("啟動預熱失敗")


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
    ready = bool(LINE_CHANNEL_ACCESS_TOKEN) and bool(LINE_CHANNEL_SECRET)
    return jsonify(
        {
            "status": "healthy" if ready else "degraded",
            "ready": ready,
            "service": "forex-line-bot",
            "ui": "flex-ux-v2",
            "token_set": bool(LINE_CHANNEL_ACCESS_TOKEN),
            "secret_set": bool(LINE_CHANNEL_SECRET),
            "server_base_url": SERVER_BASE_URL,
            "https_charts": SERVER_BASE_URL.startswith("https://"),
            "charts_dir": str(IMAGE_DIR),
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
# Telegram Webhook Support
# ============================================================
TELEGRAM_WEBHOOK_PATH = os.getenv("TELEGRAM_WEBHOOK_PATH", "/webhook/telegram")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or ""
TG_MAX_LEN = 4000

if TELEGRAM_BOT_TOKEN:
    logger.info("Telegram webhook 已啟用 (token: %s...)", TELEGRAM_BOT_TOKEN[:8])
else:
    logger.warning("TELEGRAM_BOT_TOKEN 未設定 — Telegram webhook 將無法運作")


def _tg_truncate(text: str) -> str:
    if len(text) <= TG_MAX_LEN:
        return text
    return text[: TG_MAX_LEN - 30] + "\n\n…（已截斷）"


@app.route(TELEGRAM_WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    """Telegram webhook — 文字 + K 線圖片。"""
    if not request.is_json:
        return jsonify({"error": "expected json"}), 400

    update_dict = request.get_json(silent=True)
    if not update_dict:
        return jsonify({"error": "empty body"}), 400

    try:
        message = update_dict.get("message", {})
        chat = message.get("chat", {})
        user = message.get("from", {})
        text = message.get("text", "").strip()
        update_id = update_dict.get("update_id")

        if not text:
            return jsonify({"status": "skipped"}), 200

        user_id = str(user.get("id", "unknown"))
        chat_id = str(chat.get("id", "unknown"))

        logger.info("Telegram 收到: %s (user=%s, chat=%s)", text, user_id, chat_id)

        reply = handle_query(text, user_id=user_id)
        if not isinstance(reply, BotReply):
            reply = BotReply(
                alt_text=text,
                flex=None,
                text_fallback=str(reply),
            )

        text_out = _tg_truncate(reply.text_fallback or reply.alt_text or "(無內容)")

        result = {"update_id": update_id, "chat_id": chat_id, "text": text_out}

        # 若有 K 線圖，編碼為 base64（前端可 decode 發送）
        if reply.chart_bytes:
            import base64
            result["photo"] = base64.b64encode(reply.chart_bytes).decode("utf-8")
            result["photo_caption"] = reply.alt_text or ""

        return jsonify(result), 200

    except Exception as exc:
        logger.exception("Telegram webhook 處理失敗")
        return jsonify({"error": str(exc)}), 500


@app.route("/telegram/health", methods=["GET"])
def telegram_health():
    ready = bool(TELEGRAM_BOT_TOKEN)
    return jsonify({
        "service": "forex-telegram-bot",
        "ready": ready,
        "token_set": bool(TELEGRAM_BOT_TOKEN),
        "webhook_path": TELEGRAM_WEBHOOK_PATH,
    }), (200 if ready else 503)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
