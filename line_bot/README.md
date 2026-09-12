# LINE Bot 外匯查詢機器人

透過 LINE 查詢台灣銀行牌告匯率與簡易技術分析。

## 本機運行

```bash
cd line_bot
cp .env.example .env   # 填入 LINE token / secret
pip install -r requirements.txt
ENABLE_TEST_ENDPOINT=1 python server.py
```

```bash
curl -X POST http://localhost:8080/test \
  -H "Content-Type: application/json" \
  -d '{"text":"USD"}'
```

## 部署

見 [`DEPLOY_RENDER.md`](./DEPLOY_RENDER.md) 或根目錄 `render.yaml`。

## 端點

| 路徑 | 說明 |
|------|------|
| `POST /webhook` | LINE webhook |
| `GET /health` | 健康檢查 |
| `POST /test` | 除錯（需 `ENABLE_TEST_ENDPOINT=1`） |

## 指令

- `USD` / `美元`：匯率 + 圖卡
- `匯率`：主要貨幣速覽
- `說明`：幫助
