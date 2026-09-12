"""
LINE Bot Webhook Server - Simple Version

使用 Flask 建立 webhook endpoint，接收 LINE 訊息並回傳。
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# 載入 .env 環境變數
load_dotenv()

# 添加當前目錄到 Python 路徑（Render 部署需要）
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, request, jsonify

# 使用 LINE Bot SDK v3
from linebot.v3 import WebhookHandler, SignatureValidator
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import TextMessageEvent
from linebot.v3.models import TextMessage, TextSendMessage, QuickReply, QuickReplyButton, MessageAction
from linebot import LineBotApi

from bot_core import handle_query

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# LINE Bot 設定（從環境變數讀取）
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


@handler.add(TextMessageEvent, pattern=".*")
def handle_message(event):
    """處理文字訊息。"""
    user_text = event.message.text
    logger.info(f"收到訊息: {user_text}")

    # 處理查詢
    reply_text = handle_query(user_text)

    # 建立快速回覆按鈕
    quick_reply = QuickReply(
        items=[
            QuickReplyButton(action=MessageAction(label="說明", text="說明")),
            QuickReplyButton(action=MessageAction(label="匯率", text="匯率")),
            QuickReplyButton(action=MessageAction(label="USD", text="USD")),
            QuickReplyButton(action=MessageAction(label="JPY", text="JPY")),
        ]
    )

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text, quickReply=quick_reply)
    )


@app.route("/webhook", methods=["POST"])
def webhook():
    """LINE webhook endpoint。"""
    signature = request.headers["X-Line-Signature"]

    # 驗證簽章
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature")
        return jsonify({"error": "Invalid signature"}), 400

    return jsonify({"status": "ok"}), 200


@app.route("/health", methods=["GET"])
def health():
    """健康檢查 endpoint。"""
    return jsonify({"status": "healthy", "service": "forex-line-bot"})


@app.route("/test", methods=["POST"])
def test():
    """測試 endpoint（不需簽章）。"""
    data = request.get_json()
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' field"}), 400

    text = data["text"]
    reply_text = handle_query(text)

    return jsonify({"original": text, "reply": reply_text})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    logger.info(f"啟動 LINE Bot Server 在 port {port}")
    app.run(host="0.0.0.0", port=port, debug=True)
