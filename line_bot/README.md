# LINE Bot 外匯查詢機器人

這是一個整合 LINE Bot 的外匯行情查詢系統，讓用戶可以透過 LINE 即時查詢匯率與技術分析。

## 功能

- **即時匯率查詢**：支援 19 種貨幣（USD、JPY、EUR、GBP 等）
- **技術指標分析**：RSI、MACD、MA20/MA50 趨勢
- **關鍵字查詢**：支援代碼（USD）或中文名稱（美元）
- **快速指令**：`/rates` 查看所有主要貨幣、`/help` 查看說明

## 部署方式

### 方式一：Render 部署（推薦）

請查看 `DEPLOY_RENDER.md` 文件獲取詳細部署指引。

### 方式二：本地運行

```bash
cd line_bot
pip install -r requirements.txt
python server.py
```

## 環境變數

```bash
LINE_CHANNEL_ACCESS_TOKEN=your_token_here
LINE_CHANNEL_SECRET=your_secret_here
PORT=8080
```

## API 端點

- `POST /webhook` - LINE webhook endpoint
- `GET /health` - 健康檢查
- `POST /test` - 測試 endpoint（不需簽章）

## 使用方式

在 LINE 中發送：
- `USD` 或 `美元` - 查詢美元匯率
- `JPY` 或 `日圓` - 查詢日元匯率
- `匯率` - 查看所有主要貨幣
- `說明` - 查看幫助
