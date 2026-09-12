"""
Telegram Webhook Server

與 LINE Bot 共享同一 Flask app，不同 route。
Render: PORT 由環境決定；telegram webhook 與 LINE /webhook 共存。
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request

_BOT_DIR = Path(__file__).resolve().parent
load_dotenv(_BOT_DIR / ".env")
load_dotenv()

sys.path.insert(0, str(_BOT_DIR))

from bot_core import BotReply, handle_query, schedule_daily_warm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [tg-webhook] %(message)s",
)
logger = logging.getLogger(__name__)

TELEGRAM_WEBHOOK_PATH = os.getenv("TELEGRAM_WEBHOOK_PATH", "/webhook/telegram")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or ""
MAX_TEXT_LENGTH = 4000

if not TELEGRAM_BOT_TOKEN:
    logger.warning("TELEGRAM_BOT_TOKEN 未設定 — Telegram webhook 將無法運作")

app = Flask(__name__)


def _truncate(text: str) -> str:
    if len(text) <= MAX_TEXT_LENGTH:
        return text
    return text[: MAX_TEXT_LENGTH - 50] + "\n\n…（已截斷）"


@app.route(TELEGRAM_WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    """Telegram webhook endpoint。"""
    if not request.is_json:
        return jsonify({"error": "expected json"}), 400

    update_dict = request.get_json(silent=True)
    if not update_dict:
        return jsonify({"error": "empty body"}), 400

    try:
        # 簡易解析：直接從 JSON 提取訊息內容
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

        # 執行 bot core
        reply = handle_query(text, user_id=user_id)
        if not isinstance(reply, BotReply):
            reply = BotReply(
                alt_text=text,
                flex=None,
                text_fallback=str(reply),
            )

        # 準備回覆
        text_out = _truncate(reply.text_fallback or reply.alt_text or "(無內容)")

        # 準備 K 線圖片（若有）
        photo_data = None
        if reply.chart_bytes:
            import base64

            photo_data = base64.b64encode(reply.chart_bytes).decode("utf-8")

        # 回應格式：Telegram bot API 的 send_message/send_photo
        result = {
            "update_id": update_id,
            "chat_id": chat_id,
            "text": text_out,
        }
        if photo_data:
            result["photo"] = photo_data

        return jsonify(result), 200

    except Exception as exc:
        logger.exception("Telegram webhook 處理失敗")
        return jsonify({"error": str(exc)}), 500


@app.route("/health", methods=["GET"])
def health():
    ready = bool(TELEGRAM_BOT_TOKEN)
    return jsonify(
        {
            "service": "forex-telegram-bot",
            "ready": ready,
            "token_set": bool(TELEGRAM_BOT_TOKEN),
            "webhook_path": TELEGRAM_WEBHOOK_PATH,
            "note": "此 webhook 需要自架 Telegram bot server 或使用 long polling",
        }
    ), (200 if ready else 503)


@app.route("/", methods=["GET"])
def index():
    return jsonify(
        {
            "service": "forex-telegram-bot",
            "webhook": TELEGRAM_WEBHOOK_PATH,
            "health": "/health",
            "note": "此伺服器同時支持 LINE 與 Telegram，請確認 render.yaml 配置多個 service",
        }
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8081"))
    try:
        schedule_daily_warm()
    except Exception:
        logger.exception("預熱失敗")
    app.run(host="0.0.0.0", port=port, debug=False)
