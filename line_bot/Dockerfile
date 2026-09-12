FROM python:3.11-slim

WORKDIR /app

# 以 repo 根目錄為 build context 時：
# docker build -f line_bot/Dockerfile .
COPY line_bot/requirements.txt /app/line_bot/requirements.txt
RUN pip install --no-cache-dir -r /app/line_bot/requirements.txt

COPY line_bot /app/line_bot

ENV PORT=8080
EXPOSE 8080

CMD ["gunicorn", "line_bot.server:app", "--bind", "0.0.0.0:8080", "--timeout", "120", "--workers", "1", "--threads", "4"]
