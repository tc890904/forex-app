# Telegram Bot 設定（與 LINE 同一 Render 服務）

## 根因說明（為何曾「串好卻沒反應」）

舊版 `/webhook/telegram` **只把結果 JSON 回給 Telegram**，沒有呼叫 `sendMessage`。
已修復：伺服器會主動呼叫 Bot API。

## Render 環境變數

| Key | 必要 | 說明 |
|-----|------|------|
| `TELEGRAM_BOT_TOKEN` | 是 | BotFather Token |
| `SERVER_BASE_URL` | 建議 | `https://forex-app-fxi5.onrender.com` |
| `TELEGRAM_WEBHOOK_SECRET` | 建議 | 隨機字串，驗證 webhook 來源 |
| `TELEGRAM_ADMIN_KEY` | 建議 | 保護 `/telegram/set_webhook` |
| `TELEGRAM_WEBHOOK_PATH` | 否 | 預設 `/webhook/telegram` |

## 設定 Webhook

```bash
curl -X POST "https://forex-app-fxi5.onrender.com/telegram/set_webhook" \
  -H "Content-Type: application/json" \
  -d '{}'
```

若有設 `TELEGRAM_ADMIN_KEY`：

```bash
curl -X POST "https://forex-app-fxi5.onrender.com/telegram/set_webhook" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: 你的密鑰" \
  -d '{}'
```

檢查：

```bash
curl "https://forex-app-fxi5.onrender.com/health"
curl "https://forex-app-fxi5.onrender.com/telegram/webhook_info"
```

## UX

- HTML 匯率卡 + K 線圖 + Inline 按鈕
- `/start`、底部快捷鍵盤
- 群組預設忽略（需指令／@mention／回覆）
- HTML 發送失敗會自動 fallback 純文字
