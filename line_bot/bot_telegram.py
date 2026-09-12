"""
Telegram Bot Handler — FOREX DESK

整合現有 bot_core 的 handle_query 邏輯。
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
from typing import Optional

from telegram import Update, constants
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot_core import BotReply, handle_query, schedule_daily_warm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [telegram] %(message)s",
)
logger = logging.getLogger(__name__)

# Telegram 每則訊息字數限制
MAX_TEXT_LEN = 4096


def _truncate(text: str) -> str:
    """截斷過長文字，保留結尾。"""
    if len(text) <= MAX_TEXT_LEN:
        return text
    return text[: MAX_TEXT_LEN - 30] + "\n\n…（已截斷）"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理 /start 指令。"""
    welcome = (
        "🌐 FOREX DESK 外匯分析\n\n"
        "直接輸入幣別代碼查詢匯率：\n"
        "• USD → 美元/台幣\n"
        "• JPY → 日圓/台幣\n"
        "• EUR → 歐元/台幣\n\n"
        "輸入「說明」查看所有指令。"
    )
    await update.effective_message.reply_text(
        welcome,
        parse_mode=constants.ParseMode.MARKDOWN,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理 /help 指令。"""
    reply = handle_query("說明")
    if isinstance(reply, BotReply):
        await update.effective_message.reply_text(
            _truncate(reply.text_fallback or reply.alt_text),
            parse_mode=constants.ParseMode.MARKDOWN,
        )
    else:
        await update.effective_message.reply_text(str(reply))


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理一般文字訊息。"""
    user_id = str(update.effective_user.id)
    text = update.effective_message.text.strip()
    
    logger.info("Telegram 收到: %s (user=%s)", text, user_id)

    try:
        reply = handle_query(text, user_id=user_id)
    except Exception as exc:
        logger.exception("handle_query 失敗")
        await update.effective_message.reply_text("系統錯誤，請稍後再試。")
        return

    if not isinstance(reply, BotReply):
        await update.effective_message.reply_text(str(reply))
        return

    # 發送文字內容
    text_out = _truncate(reply.text_fallback or reply.alt_text or "(無內容)")
    sent = await update.effective_message.reply_text(
        text_out,
        parse_mode=constants.ParseMode.MARKDOWN,
    )

    # 若有 K 線圖則附加
    if reply.chart_bytes and len(reply.chart_bytes) > 0:
        try:
            buf = io.BytesIO(reply.chart_bytes)
            buf.name = f"chart_{reply.last_code or 'USD'}.png"
            await sent.reply_photo(
                photo=buf,
                caption=f"📊 {reply.alt_text}",
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        except Exception:
            logger.exception("發送 K 線圖失敗")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """全域錯誤處理。"""
    logger.error("Telegram 錯誤: %s", context.error, exc_info=context.error)
    if update and hasattr(update, "effective_message"):
        try:
            await update.effective_message.reply_text("系統異常，請稍後再試。")
        except Exception:
            pass


def create_telegram_app(token: Optional[str] = None) -> Application:
    """建立並回傳 Telegram Application。"""
    token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN 未設定")

    # 啟動時預熱資料
    try:
        schedule_daily_warm()
    except Exception:
        logger.exception("預熱失敗")

    app = Application.builder().token(token).build()

    # 註冊 handler
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    return app


def run_telegram_bot(token: Optional[str] = None, poll_timeout: int = 30) -> None:
    """以 polling 模式啟動（適合本機測試）。"""
    app = create_telegram_app(token)
    logger.info("Telegram bot 啟動中...")
    app.run_polling(timeout=poll_timeout, drop_pending_updates=True)


if __name__ == "__main__":
    run_telegram_bot()
