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
        parse_mode: Optional[str] = "HTML",
        reply_to: Optional[int] = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if reply_to:
            payload["reply_to_message_id"] = reply_to
        result = self.call("sendMessage", payload)
        # HTML 失敗時 fallback 純文字
        if not result.get("ok") and parse_mode:
            logger.warning("sendMessage HTML 失敗，改送純文字")
            import re

            plain = re.sub(r"<[^>]+>", "", text)
            return self.send_message(
                chat_id, plain, reply_markup=reply_markup, parse_mode=None, reply_to=reply_to
            )
        return result

    def send_photo(
        self,
        chat_id: str | int,
        photo_bytes: bytes,
        caption: str = "",
        reply_markup: Optional[dict] = None,
        parse_mode: Optional[str] = "HTML",
    ) -> dict:
        data: dict[str, Any] = {
            "chat_id": str(chat_id),
            "caption": (caption or "")[:1024],
        }
        if parse_mode:
            data["parse_mode"] = parse_mode
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        files = {"photo": ("chart.png", photo_bytes, "image/png")}
        result = self.call("sendPhoto", data, files=files)
        if not result.get("ok") and parse_mode:
            import re

            plain = re.sub(r"<[^>]+>", "", caption or "")
            data2 = {
                "chat_id": str(chat_id),
                "caption": plain[:1024],
            }
            if reply_markup:
                data2["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
            return self.call("sendPhoto", data2, files=files)
        return result

    def answer_callback(self, callback_query_id: str, text: str = "") -> dict:
        return self.call(
            "answerCallbackQuery",
            {"callback_query_id": callback_query_id, "text": text[:200]},
        )

    def send_chat_action(self, chat_id: str | int, action: str = "typing") -> dict:
        return self.call("sendChatAction", {"chat_id": chat_id, "action": action})

    def deliver(self, chat_id: str | int, payload: dict) -> None:
        """依 tg_ui.build_telegram_payload 結果發送；檢查回傳並記錄。"""
        markup = payload.get("reply_markup")
        parse_mode = payload.get("parse_mode", "HTML")
        text = payload.get("text") or "(無內容)"

        if payload.get("reply_keyboard"):
            r = self.send_message(
                chat_id,
                text,
                reply_markup=payload["reply_keyboard"],
                parse_mode=parse_mode,
            )
        else:
            r = self.send_message(
                chat_id,
                text,
                reply_markup=markup,
                parse_mode=parse_mode,
            )
        if not r.get("ok"):
            logger.error("文字訊息送出失敗 chat=%s: %s", chat_id, r)

        photo = payload.get("photo_bytes")
        if photo:
            pr = self.send_photo(
                chat_id,
                photo,
                caption=payload.get("photo_caption") or "",
                reply_markup=markup if not payload.get("reply_keyboard") else None,
                parse_mode=parse_mode,
            )
            if not pr.get("ok"):
                logger.error("圖片送出失敗 chat=%s: %s", chat_id, pr)
