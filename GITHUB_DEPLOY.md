# GitHub + Render 部署指南

完整步驟請見 [`DEPLOY_RENDER.md`](./DEPLOY_RENDER.md)。

重點：

1. 推送程式到 GitHub
2. Render Web Service：Build / Start 使用 `line_bot` 路徑（見 `render.yaml`）
3. 在 Render 設定 `LINE_CHANNEL_ACCESS_TOKEN`、`LINE_CHANNEL_SECRET`、`SERVER_BASE_URL`
4. LINE Console Webhook 設為 `https://<service>.onrender.com/webhook` 並 Verify

**請勿把 Channel Token / Secret 寫進程式或 Markdown。**
