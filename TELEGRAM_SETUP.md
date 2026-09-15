# Telegram 推播說明

## 能不能自動推播？

**可以**，條件如下：

| 功能 | 行為 | 條件 |
|------|------|------|
| 每日匯率 | 台北 **09:00–09:02** 自動私訊 | 先輸入「訂閱」；服務需在此時段醒著 |
| 價格觸發 | 約每 **2 分鐘**檢查 | 先「監視 USD > 32」；觸發後 30 分鐘內不重複 |

### 重要限制（Render Free）
- 服務休眠時 **09:00 不會推** → 建議用外部 cron 每 10–15 分鐘打一次 `/health` 保活
- 訂閱會寫入 `line_bot/data/subscriptions.json`（重啟後盡量保留；磁碟仍可能被清）

## 指令

- `訂閱` / `取消訂閱`
- `我的訂閱`
- `推送測試`（立即預覽與正式推播相同內容）
- `監視 USD > 32` / `取消監視 USD > 32`

## 檢查狀態

```bash
curl https://forex-app-fxi5.onrender.com/telegram/push_status
```

應看到 `threads_started: true`、`subscribers_daily` 等欄位。
