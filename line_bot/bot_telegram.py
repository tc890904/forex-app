#!/usr/bin/env python3
"""Telegram Bot — FOREX DESK（本機 polling；正式環境用 webhook）"""
from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from bot_core import schedule_daily_warm
from tg_api import TelegramSender
from tg_ui import build_telegram_payload, home_inline, normalize_telegram_text
from bot_core import BotReply, handle_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [tg] %(message)s")
logger = logging.getLogger(__name__)


def process(sender: TelegramSender, chat_id: int, user_id: str, text: str) -> None:
    norm = normalize_telegram_text(text)
    sender.send_chat_action(chat_id, "typing")
    try:
        reply = handle_query(norm, user_id=f"tg:{user_id}")
    except Exception:
        logger.exception("query failed")
        sender.send_message(chat_id, "系統錯誤，請稍後再試。", reply_markup=home_inline())
        return
    if not isinstance(reply, BotReply):
        reply = BotReply(alt_text="訊息", flex=None, text_fallback=str(reply))
    sender.deliver(chat_id, build_telegram_payload(reply))


def main() -> None:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        logger.error("請設定 TELEGRAM_BOT_TOKEN")
        sys.exit(1)

    # polling 前先清掉 webhook，避免衝突
    sender = TelegramSender(token)
    info = sender.call("deleteWebhook", {"drop_pending_updates": True})
    logger.info("deleteWebhook: %s", info)

    try:
        schedule_daily_warm()
    except Exception:
        logger.exception("預熱失敗")

    offset = 0
    logger.info("Telegram polling 啟動…")
    while True:
        updates = sender.call(
            "getUpdates",
            {"timeout": 30, "offset": offset, "allowed_updates": ["message", "callback_query"]},
        )
        if not updates.get("ok"):
            logger.error("getUpdates 失敗: %s", updates)
            continue
        for upd in updates.get("result") or []:
            offset = max(offset, int(upd.get("update_id", 0)) + 1)
            if upd.get("callback_query"):
                cb = upd["callback_query"]
                sender.answer_callback(cb["id"], "查詢中…")
                chat_id = cb["message"]["chat"]["id"]
                uid = str(cb["from"]["id"])
                process(sender, chat_id, uid, cb.get("data") or "開始")
                continue
            msg = upd.get("message") or {}
            if not msg:
                continue
            chat_id = msg["chat"]["id"]
            uid = str((msg.get("from") or {}).get("id", "unknown"))
            text = (msg.get("text") or "").strip() or "開始"
            process(sender, chat_id, uid, text)


if __name__ == "__main__":
    main()
