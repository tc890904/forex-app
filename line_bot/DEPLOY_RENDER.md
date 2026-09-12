# LINE Bot 外匯行情機器人 - Render 部署指南

## 步驟 1: 推送代碼到 GitHub

```bash
cd /Users/a000/Downloads/forex_app
git init
git add .
git commit -m "Initial commit: Forex App + LINE Bot"
git branch -M main

# 在 https://github.com 建立新儲存庫
git remote add origin https://github.com/YOUR_USERNAME/forex-app.git
git push -u origin main
```

## 步驟 2: 部署到 Render

1. 前往 https://render.com 註冊/登入
2. 點擊 **New** → **Web Service**
3. 選擇剛才建立的 GitHub 儲存庫
4. 使用以下設定：
   - **Name**: `forex-line-bot`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r line_bot/requirements.txt`
   - **Start Command**: `gunicorn line_bot.server:app --bind 0.0.0.0:$PORT`
   - **Instance Type**: `Free`
5. 新增環境變數：
   | Name | Value |
   |------|-------|
   | LINE_CHANNEL_ACCESS_TOKEN | t/OS62lcL0egB4KgzOiqZR2N5ac0JTfWVWKQVGHQwG5sVOPSyDmemNyhFzaVf++9Kkk3Yefn3mMto6gaq4jumE1xYdSGxNaiN+R1CXDVEq73YxNB6cy31yRDenfgSon4yKKTmUMghk70fLnD0lSnFgdB04t89/1O/w1cDnyilFU= |
   | LINE_CHANNEL_SECRET | 3e97eecf5087595874c51eca8fc4b4eb |
6. 點擊 **Create Web Service**

## 步驟 3: 設定 LINE Webhook

部署完成後（約 2-5 分鐘），Render 會提供一個 URL，格式為：
```
https://forex-line-bot.onrender.com
```

在 LINE Developers Console 設定：
1. 進入您的 Channel
2. **Messaging settings**
3. 啟用 **Use webhook**
4. 輸入 Webhook URL: `https://forex-line-bot.onrender.com/webhook`
5. 點擊 **Save**

## 測試 Bot

在 LINE 中發送：
- `USD` - 查詢美元匯率
- `匯率` - 查看所有主要貨幣
- `說明` - 查看幫助

---

**注意**: Render 免費方案在 15 分鐘無流量時會自動休眠，首次訪問需要等待約 30 秒冷啟動。