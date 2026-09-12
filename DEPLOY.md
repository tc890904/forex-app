# Deploy Guide - Forex LINE Bot

## GitHub

```bash
cd /path/to/forex_app
git add .
git commit -m "Prepare LINE Bot for Render"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/forex-app.git
git push -u origin main
```

## Render

1. https://render.com → New → Web Service
2. 連接 repository
3. 設定：

| 項目 | 值 |
|------|-----|
| Build | `pip install -r line_bot/requirements.txt` |
| Start | `gunicorn line_bot.server:app --bind 0.0.0.0:$PORT --timeout 120 --workers 1 --threads 4` |
| Health Check | `/health` |

4. Environment（從 LINE Console 填入，勿寫進 repo）：

- `LINE_CHANNEL_ACCESS_TOKEN`
- `LINE_CHANNEL_SECRET`
- `SERVER_BASE_URL` = `https://你的服務.onrender.com`

5. LINE Webhook URL：`https://你的服務.onrender.com/webhook`

詳細步驟見 [`DEPLOY_RENDER.md`](./DEPLOY_RENDER.md)。
