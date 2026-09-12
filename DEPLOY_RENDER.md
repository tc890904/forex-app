# LINE Bot 外匯行情機器人 - Render 部署指南

## 1. 推送到 GitHub

```bash
cd /path/to/forex_app
git add .
git commit -m "Fix LINE Bot v3 reply and Render config"
git push
```

## 2. 部署到 Render

1. 開啟 https://render.com → **New** → **Web Service**
2. 連接 GitHub repository
3. 建議設定：

| 設定 | 值 |
|------|-----|
| Name | `forex-line-bot` |
| Runtime | `Python 3` |
| Build Command | `pip install -r line_bot/requirements.txt` |
| Start Command | `gunicorn line_bot.server:app --bind 0.0.0.0:$PORT --timeout 120 --workers 1 --threads 4` |
| Health Check Path | `/health` |

也可直接使用 repo 根目錄的 `render.yaml`（Blueprint）。

4. **Environment** 新增（值從 LINE Developers Console 複製，勿寫進程式碼）：

| Name | Value |
|------|-------|
| `LINE_CHANNEL_ACCESS_TOKEN` | （Channel access token） |
| `LINE_CHANNEL_SECRET` | （Channel secret） |
| `SERVER_BASE_URL` | `https://你的服務.onrender.com`（建議手動設，確保圖卡 HTTPS） |

5. Create Web Service，等待部署完成。

## 3. 設定 LINE Webhook

1. LINE Developers Console → Messaging API
2. Webhook URL：`https://你的服務.onrender.com/webhook`
3. 啟用 **Use webhook**
4. 點 **Verify** 應成功
5. 建議關閉會搶答的 Auto-reply / 歡迎訊息（可選）

## 4. 驗證

```bash
# 健康檢查（也可喚醒 Free 休眠）
curl https://你的服務.onrender.com/health

# 業務邏輯測試（需在 Render 設 ENABLE_TEST_ENDPOINT=1）
curl -X POST https://你的服務.onrender.com/test \
  -H "Content-Type: application/json" \
  -d '{"text":"說明"}'
```

在 LINE 傳送：`說明`、`USD`、`匯率`。

## 注意

- Free 方案約 15 分鐘無流量會休眠；喚醒可能 30+ 秒，首則訊息可能失敗，先打 `/health` 再測。
- Token / Secret 只放 Render Environment，不要提交到 git。
