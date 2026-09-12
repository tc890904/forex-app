# Forex App - 智慧外匯行情與動態風控系統

基于 Streamlit 的外匯行情分析應用，整合 FinMind API 提供即時匯率查詢、技術指標分析與風險管理工具。

## 功能特性

- 📊 **匯率總覽**：19種貨幣即時匯率顯示
- 🔍 **單一貨幣分析**：K線圖 + 布林通道 + MA線
- 📡 **技術指標**：RSI、MACD、移動平均線交叉訊號
- 🛡️ **風險管理**：ATR動態停損、凱利公式、槓桿風險評估
- 🧪 **回測系統**：MA交叉策略回測分析
- 🧠 **情緒分析**：基於技術指標的綜合情緒評分

## 技術棧

- Python 3.11
- Streamlit
- Plotly
- Pandas
- NumPy
- FinMind API（台灣銀行牌告匯率）

## 本地運行

```bash
# 建立虛擬環境
python3 -m venv venv
source venv/bin/activate

# 安裝依賴
pip install -r requirements.txt

# 啟動應用
streamlit run forex_app/app.py
```

訪問 http://localhost:8501

## 部署到 Render

1. 將代碼推送到 GitHub
2. 登入 [Render](https://render.com)
3. 點擊 New → Web Service
4. 選擇 repository
5. 設定構建參數：
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `streamlit run forex_app/app.py --server.port $PORT --server.headless true`
6. 新增環境變數（如有需要）
7. 點擊 Create Web Service

## 目錄結構

```
forex_app/
├── app.py                 # 主入口
├── config.py              # 配置常數
├── data.py                # FinMind API 封裝
├── indicators.py          # 技術指標計算
├── risk_calc.py           # 風險計算模組
├── backtest.py            # 回測引擎
├── sentiment.py           # 情緒分析
└── views/
    ├── __init__.py
    ├── overview.py        # 匯率總覽頁
    ├── analysis.py        # 單一分析頁
    ├── signals.py         # 訊號頁
    ├── risk.py            # 風險頁
    └── research.py        # 研究頁
```

## 支援貨幣

USD、EUR、GBP、JPY、CHF、AUD、CAD、SGD、HKD、NZD、SEK、ZAR、THB、PHP、IDR、KRW、VND、MYR、CNY

## 免責聲明

本系統所提供之匯率資訊、技術指標、買賣訊號及風控試算結果僅供參考，不構成任何形式之投資建議或交易要約。外匯交易涉及高槓桿操作，可能產生超過原始投入本金之損失，投資人應充分了解相關風險並依自身財務狀況審慎評估。
