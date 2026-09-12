# LINE Bot 外匯行情機器人 - Render 部署指南

請見專案根目錄 [`DEPLOY_RENDER.md`](../DEPLOY_RENDER.md)。

快速摘要：

- Build: `pip install -r line_bot/requirements.txt`
- Start: `gunicorn line_bot.server:app --bind 0.0.0.0:$PORT --timeout 120 --workers 1 --threads 4`
- Env: `LINE_CHANNEL_ACCESS_TOKEN`、`LINE_CHANNEL_SECRET`、`SERVER_BASE_URL`
- Webhook: `https://<your-service>.onrender.com/webhook`
