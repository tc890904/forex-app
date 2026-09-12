# Telegram Bot 設定（與 LINE 同一 Render 服務）

## 根因說明（為何「串好卻沒反應」）

舊版 `/webhook/telegram` **只把結果 JSON 回給 Telegram 伺服器**，
沒有呼叫 `sendMessage` / `sendPhoto`。
Telegram **不會**把 webhook 的 HTTP body 顯示給使用者，所以看起來完全沒回覆。

已修復：伺服器會主動呼叫 Bot API 發送訊息與 K 線圖。

## Render 環境變數

| Key | Value |
|-----|--------|
| `TELEGRAM_BOT_TOKEN` | BotFather 給的 Token |
| `SERVER_BASE_URL` | `https://你的服務.onrender.com`（建議明確設定）|

LINE 變數不用改。Build / Start Command 與 LINE 相同。

## 設定 Webhook（部署後必做一次）

把下面網址的 Token、服務網域換成你的：

```bash
curl -X POST "https://你的服務.onrender.com/telegram/set_webhook" \
  -H "Content-Type: application/json" \
  -d '{}'
```

或：

```bash
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://你的服務.onrender.com/webhook/telegram"
```

檢查：

```bash
curl "https://你的服務.onrender.com/telegram/webhook_info"
curl "https://你的服務.onrender.com/health"
```

`health` 應看到 `"telegram_token_set": true`。

## 本機測試（polling）

```bash
export TELEGRAM_BOT_TOKEN=你的Token
cd line_bot && python bot_telegram.py
```

（polling 會自動 deleteWebhook，勿與 Render webhook 同時開。）

## UX

- HTML 結構化匯率卡 + K 線圖
- Inline 按鈕（詳情／停損／回測／幣別）
- `/start`、底部快速鍵盤
- 貼圖／圖片 → 歡迎訊息
