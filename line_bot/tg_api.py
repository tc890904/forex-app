"""
Telegram Bot API 發送層（同步 requests，適合 Flask / gunicorn）。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"


class TelegramSender:
    def __init__(self, token: str, timeout: float = 25.0):
        self.token = (token or "").strip()
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def _url(self, method: str) -> str:
        return f"{API_BASE}/bot{self.token}/{method}"

    def call(self, method: str, payload: Optional[dict] = None, files: Any = None) -> dict:
        if not self.enabled:
            logger.error("TELEGRAM_BOT_TOKEN 未設定，無法呼叫 %s", method)
            return {"ok": False, "description": "token missing"}
        try:
            if files:
                r = requests.post(
                    self._url(method),
                    data=payload or {},
                    files=files,
                    timeout=self.timeout,
                )
            else:
                r = requests.post(
                    self._url(method),
                    json=payload or {},
                    timeout=self.timeout,
                )
            data = r.json()
            if not data.get("ok"):
                logger.error("Telegram %s 失敗: %s", method, data)
            return data
        except Exception:
            logger.exception("Telegram %s 例外", method)
            return {"ok": False, "description": "request failed"}

    def send_message(
        self,
        chat_id: str | int,
        text: str,
        reply_markup: Optional[dict] = None,
        parse_mode: str = "HTML",
        reply_to: Optional[int] = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if reply_to:
            payload["reply_to_message_id"] = reply_to
        return self.call("sendMessage", payload)

    def send_photo(
        self,
        chat_id: str | int,
        photo_bytes: bytes,
        caption: str = "",
        reply_markup: Optional[dict] = None,
        parse_mode: str = "HTML",
    ) -> dict:
        data: dict[str, Any] = {
            "chat_id": str(chat_id),
            "caption": (caption or "")[:1024],
            "parse_mode": parse_mode,
        }
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        files = {"photo": ("chart.png", photo_bytes, "image/png")}
        return self.call("sendPhoto", data, files=files)

    def answer_callback(self, callback_query_id: str, text: str = "") -> dict:
        return self.call(
            "answerCallbackQuery",
            {"callback_query_id": callback_query_id, "text": text[:200]},
        )

    def send_chat_action(self, chat_id: str | int, action: str = "typing") -> dict:
        return self.call("sendChatAction", {"chat_id": chat_id, "action": action})

    def deliver(self, chat_id: str | int, payload: dict) -> None:
        """依 tg_ui.build_telegram_payload 結果發送。"""
        # 先發文字（含 inline keyboard）
        markup = payload.get("reply_markup")
        # 歡迎時改用 reply keyboard（並可再補 inline）
        if payload.get("reply_keyboard"):
            self.send_message(
                chat_id,
                payload["text"],
                reply_markup=payload["reply_keyboard"],
                parse_mode=payload.get("parse_mode", "HTML"),
            )
            # 再補一則快捷 inline（可選，避免洗版：改為同則僅 reply keyboard）
        else:
            self.send_message(
                chat_id,
                payload["text"],
                reply_markup=markup,
                parse_mode=payload.get("parse_mode", "HTML"),
            )

        photo = payload.get("photo_bytes")
        if photo:
            # 圖片附帶精簡 caption + 同一組 inline（方便操作）
            self.send_photo(
                chat_id,
                photo,
                caption=payload.get("photo_caption") or "",
                reply_markup=markup if not payload.get("reply_keyboard") else None,
                parse_mode=payload.get("parse_mode", "HTML"),
            )
