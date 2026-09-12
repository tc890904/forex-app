"""
LINE Bot Webhook Server - Fixed QuickReply

使用 Flask 建立 webhook endpoint，接收 LINE 訊息並回傳。
"""

import os
import sys
import logging
import traceback
import uuid
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

# 載入 .env 環境變數
load_dotenv()

# 添加當前目錄到 Python 路徑
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, request, jsonify, send_from_directory

# 使用 LINE Bot SDK v3
try:
    from linebot.v3 import WebhookHandler
    from linebot.v3.exceptions import InvalidSignatureError
    from linebot.v3.webhooks import MessageEvent
    from linebot.v3.messaging import ImageMessage, TextMessage
    from linebot.models import QuickReply, QuickReplyButton, MessageAction
    from linebot import LineBotApi
    print("✅ LINE SDK v3 imports successful")
except Exception as e:
    print(f"❌ LINE SDK import error: {e}")
    traceback.print_exc()
    sys.exit(1)

from bot_core import handle_query

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static')

# 建立圖片儲存目錄
IMAGE_DIR = Path(__file__).parent / "static" / "images"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

# LINE Bot 設定（從環境變數讀取）
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    print("⚠️ WARNING: LINE_CHANNEL_ACCESS_TOKEN or LINE_CHANNEL_SECRET not set!")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 快速回覆按鈕定義
QUICK_REPLY_ITEMS = [
    QuickReplyButton(
        action=MessageAction(
            label="💵 USD",
            text="USD"
        )
    ),
    QuickReplyButton(
        action=MessageAction(
            label="💴 JPY",
            text="JPY"
        )
    ),
    QuickReplyButton(
        action=MessageAction(
            label="💶 EUR",
            text="EUR"
        )
    ),
    QuickReplyButton(
        action=MessageAction(
            label="💷 GBP",
            text="GBP"
        )
    ),
    QuickReplyButton(
        action=MessageAction(
            label="📊 匯率",
            text="匯率"
        )
    ),
    QuickReplyButton(
        action=MessageAction(
            label="❓ 說明",
            text="說明"
        )
    ),
]
QUICK_REPLY = QuickReply(items=QUICK_REPLY_ITEMS)

# 伺服器基礎 URL（從環境變數讀取）
SERVER_BASE_URL = os.getenv("SERVER_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8080")


def save_image_to_disk(image_bytes: bytes, filename: str = None) -> str:
    """將圖片保存到 static/images 目錄，並返回可訪問的 URL。"""
    if filename is None:
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"
    
    filepath = IMAGE_DIR / filename
    with open(filepath, "wb") as f:
        f.write(image_bytes)
    
    # 返回可訪問的 URL
    return f"{SERVER_BASE_URL}/static/images/{filename}"


@app.route('/static/images/<filename>')
def serve_image(filename):
    """提供圖片文件。"""
    return send_from_directory(IMAGE_DIR, filename)


@handler.add(MessageEvent)
def handle_message(event):
    """處理文字訊息。"""
    try:
        user_text = event.message.text
        logger.info(f"收到訊息: {user_text}")

        # 處理查詢，回傳 (文字, 圖片資料)
        result = handle_query(user_text)
        
        # handle_query 返回 tuple (text, image_data)
        if isinstance(result, tuple):
            reply_text = result[0]
            image_data = result[1] if len(result) > 1 else None
        else:
            reply_text = result
            image_data = None

        # 準備要發送的訊息列表
        messages = []
        
        # 如果有圖片，先保存並發送圖片
        if image_data:
            try:
                image_url = save_image_to_disk(image_data)
                logger.info(f"圖片已保存: {image_url}")
                messages.append(ImageMessage(
                    original_content_url=image_url,
                    preview_image_url=image_url
                ))
            except Exception as e:
                logger.error(f"保存图片時出錯: {e}", exc_info=True)
        
        # 添加文字訊息（不包含 quick_reply，因為 TextMessage 不支援）
        messages.append(TextMessage(text=reply_text))

        # 發送訊息
        line_bot_api.reply_message(
            event.reply_token,
            messages
        )
        logger.info(f"已回覆成功")
        
    except Exception as e:
        logger.error(f"處理訊息時出錯: {e}", exc_info=True)
        try:
            error_msg = f"⚠️ 錯誤: {str(e)[:100]}"
            line_bot_api.reply_message(
                event.reply_token,
                [TextMessage(text=error_msg)]
            )
        except:
            pass


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
    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

    return jsonify({"status": "ok"}), 200


@app.route("/health", methods=["GET"])
def health():
    """健康檢查 endpoint。"""
    return jsonify({
        "status": "healthy", 
        "service": "forex-line-bot",
        "token_set": bool(LINE_CHANNEL_ACCESS_TOKEN),
        "secret_set": bool(LINE_CHANNEL_SECRET),
        "images_dir": str(IMAGE_DIR),
    })


@app.route("/test", methods=["POST"])
def test():
    """測試 endpoint（不需簽章）。"""
    data = request.get_json()
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' field"}), 400

    text = data["text"]
    try:
        result = handle_query(text)
        if isinstance(result, tuple):
            reply_text = result[0]
            image_data = result[1] if len(result) > 1 else None
        else:
            reply_text = result
            image_data = None
        
        # 如果有圖片，保存並返回 URL
        image_url = None
        if image_data:
            image_url = save_image_to_disk(image_data)
        
        return jsonify({
            "original": text,
            "reply": reply_text,
            "image_url": image_url,
            "has_image": image_data is not None,
            "success": True,
        })
    except Exception as e:
        logger.error(f"Test error: {e}", exc_info=True)
        return jsonify({
            "original": text,
            "error": str(e),
            "success": False,
        }), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    logger.info(f"啟動 LINE Bot Server 在 port {port}")
    logger.info(f"Webhook URL: {SERVER_BASE_URL}/webhook")
    logger.info(f"Health Check: {SERVER_BASE_URL}/health")
    logger.info(f"Test API:     POST {SERVER_BASE_URL}/test")
    logger.info(f"Images URL:   {SERVER_BASE_URL}/static/images/")
    app.run(host="0.0.0.0", port=port, debug=True)
