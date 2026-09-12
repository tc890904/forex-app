# 部署流程

## 1. 建立 GitHub 儲存庫

請手動操作：

```bash
# 在專案根目錄執行
cd /Users/a000/Downloads/forex_app

# 建立 .gitignore（已排除 .env）
echo ".env" >> .gitignore

# 初始化 git（若尚未初始化）
git init
git add .
git commit -m "Initial commit: Forex App + LINE Bot"
```

然後在 [GitHub.com](https://github.com/new) 建立新儲存庫，複製 push 指令：

```bash
git remote add origin https://github.com/YOUR_USERNAME/forex-app.git
git branch -M main
git push -u origin main
```

---

## 2. 取得 Webhook URL

### 方法 A：使用 ngrok（本地測試）

```bash
# 安裝 ngrok
brew install ngrok

# 啟動 ngrok（會建立 HTTPS tunnel）
ngrok http 8080

# 複製 ngrok 提供的 HTTPS URL，例如：
# https://abc123.ngrok.io
```

然後在 LINE Developers Console 設定：
- Webhook URL: `https://abc123.ngrok.io/webhook`
- 啟用 Webhook 使用

### 方法 B：使用 Render/Railway（正式部署）

**Render.com**（免費方案）：
1. 註冊 https://render.com
2. 建立新 Web Service
3. 選擇 GitHub 儲存庫
4. 設定環境變數：
   - `LINE_CHANNEL_ACCESS_TOKEN`
   - `LINE_CHANNEL_SECRET`
5. 啟動後取得 URL：`https://your-bot.onrender.com`

---

## 3. 驗證 Bot 運作

```bash
# 測試本地 API
curl -X POST http://localhost:8080/test \
  -H "Content-Type: application/json" \
  -d '{"text": "USD"}'

# 應該回覆匯率資訊
```

---

## 4. 設定 LINE Developers Console

1. 進入 [LINE Developers Console](https://developers.line.biz/console/)
2. 選擇您的 Channel
3. 進入 **Messaging settings**
4. 啟用 **Use webhook**
5. 輸入 Webhook URL
6. 儲存設定

現在可以在 LINE 中測試 Bot 了！
