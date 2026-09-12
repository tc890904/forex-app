FROM python:3.11-slim

WORKDIR /app

# 複製需求文件
COPY requirements.txt .

# 安裝依賴
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用代碼
COPY . .

# 暴露端口
EXPOSE 8080

# 啟動命令（使用 gunicorn 生產環境）
CMD ["gunicorn", "server:app", "--bind", "0.0.0.0:8080", "--timeout", "120"]
