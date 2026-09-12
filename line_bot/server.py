"""
LINE Bot Webhook Server

純 LINE Bot SDK v3：WebhookHandler + MessagingApi + Flex UI。
"""

from __future__ import annotations

import logging
import os
import sys
import traceback
import uuid
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
    ImageMessage,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from bot_core import BotReply, handle_query
from ui import default_quick_reply, to_flex_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

LINE_TEXT_MAX_LEN = 5000

app = Flask(__name__, static_folder="static")

IMAGE_DIR = _BOT_DIR / "static" / "images"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

LINE_CHANNEL_ACCESS_TOKEN = (os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or "").strip()
LINE_CHANNEL_SECRET = (os.getenv("LINE_CHANNEL_SECRET") or "").strip()

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    logger.warning(
        "LINE_CHANNEL_ACCESS_TOKEN or LINE_CHANNEL_SECRET not set — "
        "webhook replies will fail until env vars are configured"
    )

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

SERVER_BASE_URL = (
    os.getenv("SERVER_BASE_URL")
    or os.getenv("RENDER_EXTERNAL_URL")
    or "http://localhost:8080"
).rstrip("/")


def _truncate_text(text: str) -> str:
    if len(text) <= LINE_TEXT_MAX_LEN:
        return text
    return text[: LINE_TEXT_MAX_LEN - 20] + "\n…(內容過長已截斷)"


def save_image_to_disk(image_bytes: bytes, filename: str | None = None) -> str:
    if filename is None:
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError("invalid image filename")
    filepath = IMAGE_DIR / filename
    with open(filepath, "wb") as f:
        f.write(image_bytes)
    return f"{SERVER_BASE_URL}/static/images/{filename}"


def _reply(reply_token: str, messages: list) -> None:
    with ApiClient(configuration) as api_client:
        messaging_api = MessagingApi(api_client)
        messaging_api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=messages)
        )


def _build_messages(reply: BotReply) -> list:
    """Flex 為主；HTTPS 時附加圖卡；最後一則帶 Quick Reply。"""
    messages: list = []

    if reply.image_bytes:
        try:
            image_url = save_image_to_disk(reply.image_bytes)
            logger.info("圖片已保存: %s", image_url)
            if image_url.startswith("https://"):
                messages.append(
                    ImageMessage(
                        original_content_url=image_url,
                        preview_image_url=image_url,
                    )
                )
            else:
                logger.info("本機非 HTTPS，略過 ImageMessage（Flex 仍會送出）")
        except Exception:
            logger.exception("保存圖片時出錯")

    if reply.flex is not None:
        messages.append(
            to_flex_message(reply.flex, reply.alt_text or "FOREX DESK", quick_reply=True)
        )
    else:
        messages.append(
            TextMessage(
                text=_truncate_text(reply.text_fallback or "（無內容）"),
                quick_reply=default_quick_reply(),
            )
        )

    return messages


@app.route("/static/images/<path:filename>")
def serve_image(filename: str):
    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename:
        return jsonify({"error": "invalid filename"}), 400
    return send_from_directory(IMAGE_DIR, safe_name)


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event: MessageEvent) -> None:
    try:
        user_text = event.message.text
        logger.info("收到訊息: %s", user_text)

        reply = handle_query(user_text)
        if not isinstance(reply, BotReply):
            # 向後相容：舊 tuple
            if isinstance(reply, tuple):
                reply = BotReply(
                    alt_text=str(reply[0])[:40],
                    flex=None,
                    text_fallback=str(reply[0]),
                    image_bytes=reply[1] if len(reply) > 1 else None,
                )
            else:
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
                    TextMessage(
                        text="暫時無法處理，請稍後再試。",
                        quick_reply=default_quick_reply(),
                    )
                ],
            )
        except Exception:
            logger.exception("錯誤回覆也失敗")


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
    return jsonify(
        {
            "status": "healthy",
            "service": "forex-line-bot",
            "ui": "flex-v1",
            "token_set": bool(LINE_CHANNEL_ACCESS_TOKEN),
            "secret_set": bool(LINE_CHANNEL_SECRET),
            "server_base_url": SERVER_BASE_URL,
            "images_dir": str(IMAGE_DIR),
        }
    )


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
    try:
        reply = handle_query(text)
        image_url = None
        if reply.image_bytes:
            image_url = save_image_to_disk(reply.image_bytes)

        flex_dict = None
        if reply.flex is not None:
            flex_dict = to_flex_message(reply.flex, reply.alt_text).to_dict()

        return jsonify(
            {
                "original": text,
                "alt_text": reply.alt_text,
                "reply": reply.text_fallback,
                "image_url": image_url,
                "has_image": reply.image_bytes is not None,
                "has_flex": reply.flex is not None,
                "flex": flex_dict,
                "success": True,
            }
        )
    except Exception as e:
        logger.exception("Test error: %s", e)
        return jsonify(
            {
                "original": text,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "success": False,
            }
        ), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    logger.info("啟動 LINE Bot Server 在 port %s (debug=%s)", port, debug)
    logger.info("Webhook URL: %s/webhook", SERVER_BASE_URL)
    app.run(host="0.0.0.0", port=port, debug=debug)
