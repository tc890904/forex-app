"""
LINE Bot Webhook Server

純 LINE Bot SDK v3：WebhookHandler + MessagingApi。
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

# 優先載入 line_bot/.env，再載入 cwd .env（本機開發用）
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
    MessageAction,
    MessagingApi,
    QuickReply,
    QuickReplyItem,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from bot_core import handle_query

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# LINE 文字訊息上限
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

QUICK_REPLY = QuickReply(
    items=[
        QuickReplyItem(action=MessageAction(label="USD", text="USD")),
        QuickReplyItem(action=MessageAction(label="JPY", text="JPY")),
        QuickReplyItem(action=MessageAction(label="EUR", text="EUR")),
        QuickReplyItem(action=MessageAction(label="GBP", text="GBP")),
        QuickReplyItem(action=MessageAction(label="匯率", text="匯率")),
        QuickReplyItem(action=MessageAction(label="說明", text="說明")),
    ]
)

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
    """將圖片寫入 static/images，回傳對外可存取的 HTTPS/HTTP URL。"""
    if filename is None:
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"

    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError("invalid image filename")

    filepath = IMAGE_DIR / filename
    with open(filepath, "wb") as f:
        f.write(image_bytes)

    return f"{SERVER_BASE_URL}/static/images/{filename}"


def _reply(reply_token: str, messages: list) -> None:
    """以 MessagingApi v3 回覆訊息。"""
    with ApiClient(configuration) as api_client:
        messaging_api = MessagingApi(api_client)
        messaging_api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=messages)
        )


@app.route("/static/images/<path:filename>")
def serve_image(filename: str):
    """提供圖卡檔案；阻擋路徑穿越。"""
    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename:
        return jsonify({"error": "invalid filename"}), 400
    return send_from_directory(IMAGE_DIR, safe_name)


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event: MessageEvent) -> None:
    """處理文字訊息並回覆。"""
    try:
        user_text = event.message.text
        logger.info("收到訊息: %s", user_text)

        result = handle_query(user_text)
        if isinstance(result, tuple):
            reply_text = result[0]
            image_data = result[1] if len(result) > 1 else None
        else:
            reply_text = str(result)
            image_data = None

        reply_text = _truncate_text(reply_text or "（無內容）")
        messages: list = []

        if image_data:
            try:
                image_url = save_image_to_disk(image_data)
                logger.info("圖片已保存: %s", image_url)
                # LINE 要求圖片 URL 必須是 HTTPS 公開網址
                if image_url.startswith("https://"):
                    messages.append(
                        ImageMessage(
                            original_content_url=image_url,
                            preview_image_url=image_url,
                        )
                    )
                else:
                    logger.warning(
                        "略過圖片（非 HTTPS URL，LINE 無法抓取）: %s", image_url
                    )
            except Exception:
                logger.exception("保存圖片時出錯")

        # QuickReply 掛在最後一則文字訊息
        messages.append(TextMessage(text=reply_text, quick_reply=QUICK_REPLY))

        _reply(event.reply_token, messages)
        logger.info("已回覆成功")

    except Exception as exc:
        logger.exception("處理訊息時出錯: %s", exc)
        try:
            _reply(
                event.reply_token,
                [TextMessage(text=f"⚠️ 暫時無法處理，請稍後再試。")],
            )
        except Exception:
            logger.exception("錯誤回覆也失敗")


@app.route("/webhook", methods=["POST"])
def webhook():
    """LINE webhook endpoint。"""
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
        # 仍回 200，避免 LINE 無限重試；細節已寫入 log
        return jsonify({"status": "ok", "note": "handler error logged"}), 200

    return jsonify({"status": "ok"}), 200


@app.route("/health", methods=["GET"])
def health():
    """健康檢查（Render / 冷啟動喚醒用）。"""
    return jsonify(
        {
            "status": "healthy",
            "service": "forex-line-bot",
            "token_set": bool(LINE_CHANNEL_ACCESS_TOKEN),
            "secret_set": bool(LINE_CHANNEL_SECRET),
            "server_base_url": SERVER_BASE_URL,
            "images_dir": str(IMAGE_DIR),
        }
    )


@app.route("/", methods=["GET"])
def index():
    """根路徑，方便確認服務存活。"""
    return jsonify(
        {
            "service": "forex-line-bot",
            "webhook": "/webhook",
            "health": "/health",
        }
    )


def _test_endpoint_enabled() -> bool:
    """Render 上預設關閉；本機或明確開啟時可用。"""
    if os.getenv("ENABLE_TEST_ENDPOINT", "0") == "1":
        return True
    return not bool(os.getenv("RENDER"))


@app.route("/test", methods=["POST"])
def test():
    """測試 endpoint（Render 預設關閉；設 ENABLE_TEST_ENDPOINT=1 開啟）。"""
    if not _test_endpoint_enabled():
        return jsonify({"error": "disabled"}), 404

    data = request.get_json(silent=True)
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' field"}), 400

    text = data["text"]
    try:
        result = handle_query(text)
        if isinstance(result, tuple):
            reply_text = result[0]
            image_data = result[1] if len(result) > 1 else None
        else:
            reply_text = str(result)
            image_data = None

        image_url = None
        if image_data:
            image_url = save_image_to_disk(image_data)

        return jsonify(
            {
                "original": text,
                "reply": reply_text,
                "image_url": image_url,
                "has_image": image_data is not None,
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
    logger.info("Health Check: %s/health", SERVER_BASE_URL)
    app.run(host="0.0.0.0", port=port, debug=debug)
