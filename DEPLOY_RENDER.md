# LINE Bot 外匯行情機器人

## 快速部署到 Render (免費)

### 步驟 1: 推送代碼到 GitHub

```bash
cd /Users/a000/Downloads/forex_app
git init
git add .
git commit -m "Initial commit: Forex App + LINE Bot"
git branch -M main

# 在 GitHub 建立新儲存庫，然後執行：
git remote add origin https://github.com/YOUR_USERNAME/forex-app.git
git push -u origin main
```

### 步驟 2: 部署到 Render

1. 註冊 Render: https://render.com
2. 點擊 **New** → **Web Service**
3. 選擇剛才建立的 GitHub 儲存庫
4. 使用以下設定：
   - **Name**: `forex-line-bot`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r line_bot/requirements.txt`
   - **Start Command**: `gunicorn line_bot.server:app --bind 0.0.0.0:$PORT`
   - **Instance Type**: `Free`
5. 新增環境變數：
   - `LINE_CHANNEL_ACCESS_TOKEN` = `t/OS62lcL0egB4KgzOiqZR2N5ac0JTfWVWKQVGHQwG5sVOPSyDmemNyhFzaVf++9Kkk3Yefn3mMto6gaq4jumE1xYdSGxNaiN+R1CXDVEq73YxNB6cy31yRDenfgSon4yKKTmUMghk70fLnD0lSnFgdB04t89/1O/w1cDnyilFU=`
   - `LINE_CHANNEL_SECRET` = `3e97eecf5087595874c51eca8fc4b4eb`
6. 點擊 **Create Web Service**

### 步驟 3: 設定 LINE Webhook

部署完成後，Render 會提供一個 URL，例如：
```
https://forex-line-bot.onrender.com
```

在 LINE Developers Console 設定：
- Webhook URL: `https://forex-line-bot.onrender.com/webhook`
- 啟用 Webhook 使用

---

## 本地測試

```bash
cd /Users/a000/Downloads/forex_app/line_bot
../venv/bin/python server.py
```

測試 Bot：
```bash
curl -X POST http://localhost:8080/test \
  -H "Content-Type: application/json" \
  -d '{"text": "USD"}'
```

---

## 功能說明

| 指令 | 功能 |
|------|------|
| `USD`、`美元` | 查詢美元匯率與技術分析 |
| `JPY`、`日圓` | 查詢日元匯率與技術分析 |
| `匯率` | 查看所有主要貨幣匯率 |
| `說明` | 查看幫助 |