# GitHub + Render 部署指南

## 步驟 1: 推送代碼到 GitHub

### 1.1 初始化 Git (已完成)
```bash
cd /Users/a000/Downloads/forex_app
git init
git add .
git status  # 確認要提交的檔案
```

### 1.2 建立首次提交
```bash
git commit -m "Initial commit: Forex App + LINE Bot"
git branch -M main
```

### 1.3 在 GitHub 建立儲存庫
1. 前往 https://github.com/new
2. 建立儲存庫（名稱建議：`forex-app`）
3. 不要勾選 "Initialize this repository with a README"
4. 點擊 **Create repository**

### 1.4 推送代碼
複製以下指令執行：
```bash
git remote add origin https://github.com/YOUR_USERNAME/forex-app.git
git push -u origin main
```

---

## 步驟 2: 部署到 Render

### 2.1 註冊 Render
前往 https://render.com 註冊/登入

### 2.2 建立 Web Service
1. 點擊 **New** → **Web Service**
2. 選擇剛才建立的 GitHub 儲存庫
3. 使用以下設定：

| 設定項 | 值 |
|--------|-----|
| Name | `forex-line-bot` |
| Environment | `Python 3` |
| Build Command | `pip install -r line_bot/requirements.txt` |
| Start Command | `gunicorn line_bot.server:app --bind 0.0.0.0:$PORT` |
| Instance Type | `Free` |

### 2.3 新增環境變數
在 Render 儀表板中，進入 Settings → Environment Variables，新增：

| Name | Value |
|------|-------|
| LINE_CHANNEL_ACCESS_TOKEN | `t/OS62lcL0egB4KgzOiqZR2N5ac0JTfWVWKQVGHQwG5sVOPSyDmemNyhFzaVf++9Kkk3Yefn3mMto6gaq4jumE1xYdSGxNaiN+R1CXDVEq73YxNB6cy31yRDenfgSon4yKKTmUMghk70fLnD0lSnFgdB04t89/1O/w1cDnyilFU=` |
| LINE_CHANNEL_SECRET | `3e97eecf5087595874c51eca8fc4b4eb` |

### 2.4 部署
點擊 **Create Web Service**，等待約 2-5 分鐘部署完成。

---

## 步驟 3: 設定 LINE Webhook

1. 部署完成後，Render 會提供 URL：`https://forex-line-bot.onrender.com`
2. 前往 LINE Developers Console
3. 進入 **Messaging settings**
4. 啟用 **Use webhook**
5. 輸入 Webhook URL: `https://forex-line-bot.onrender.com/webhook`
6. 點擊 **Save**

---

## 測試 Bot

在 LINE 中發送：
- `USD` - 查詢美元匯率
- `JPY` - 查詢日元匯率
- `匯率` - 查看所有主要貨幣
- `說明` - 查看幫助

---

## 注意事項

- Render 免費方案在 15 分鐘無流量時會自動休眠
- 首次訪問需要等待約 30 秒冷啟動
- URL 格式：`https://forex-line-bot.onrender.com`（您的實際 URL 可能不同）
