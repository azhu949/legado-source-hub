FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 系统依赖（lxml 编译）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libxml2-dev libxslt1-dev nodejs \
    && rm -rf /var/lib/apt/lists/*

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码
COPY . .

# 数据目录
RUN mkdir -p /app/data/sources

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info", "--access-log"]
