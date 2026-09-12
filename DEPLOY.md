# Deploy Guide - Forex App

## 步驟一：初始化 Git Repository

```bash
cd /Users/a000/Downloads/forex_app
git init
git add .
git commit -m "Initial commit: Forex App with LINE Bot support"
```

## 步驟二：創建 GitHub Repository

1. 前往 https://github.com/new
2. Repository name: `forex-app`
3. 選擇 Public 或 Private
4. 不要勾選 "Initialize this repository with a README"
5. 點擊 Create repository

## 步驟三：推送代碼到 GitHub

```bash
git remote add origin https://github.com/YOUR_USERNAME/forex-app.git
git branch -M main
git push -u origin main
```

## 步驟四：部署到 Render

1. 登入 https://render.com
2. 點擊 **New** → **Web Service**
3. 選擇剛才建立的 GitHub repository
4. 設定如下：
   - **Name**: `forex-line-bot`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r line_bot/requirements.txt`
   - **Start Command**: `python line_bot/server.py`
   - **Instance Type**: `Free`
5. 在 **Environment Variables** 加入：
   - `LINE_CHANNEL_ACCESS_TOKEN`: `t/OS62lcL0egB4KgzOiqZR2N5ac0JTfWVWKQVGHQwG5sVOPSyDmemNyhFzaVf++9Kkk3Yefn3mMto6gaq4jumE1xYdSGxNaiN+R1CXDVEq73YxNB6cy31yRDenfgSon4yKKTmUMghk70fLnD0lSnFgdB04t89/1O/w1cDnyilFU=`
   - `LINE_CHANNEL_SECRET`: `3e97eecf5087595874c51eca8fc4b4eb`
6. 點擊 **Create Web Service**

## 步驟五：取得 Webhook URL

部署完成後，Render 會提供一個 URL，格式為：
```
https://forex-line-bot-xxxx.onrender.com
```

將此 URL 加上 `/webhook` 後貼到 LINE Developers Console：
```
https://forex-line-bot-xxxx.onrender.com/webhook
```

## 測試

```bash
# 本地測試
curl -X POST http://localhost:8080/test \
  -H "Content-Type: application/json" \
  -d '{"text": "USD"}'

# 測試 webhook endpoint
curl -X POST https://your-app.onrender.com/webhook \
  -H "Content-Type: application/json" \
  -d '{"type": "message", "message": {"text": "USD"}}'
```
