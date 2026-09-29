# ============================================================
# AI Agent助手 - Dockerfile
# ============================================================
# 构建: docker build -t ai-agent .
# 运行: docker run --gpus all -p 8000:8000 -v $(pwd)/data:/app/data ai-agent
# ============================================================

FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖文件（利用Docker缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 创建数据目录
RUN mkdir -p data faiss_memory faiss_docs logs

# 暴露端口
EXPOSE 8000 7860

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# 默认启动API服务
CMD ["python", "main.py", "serve", "--host", "0.0.0.0", "--port", "8000"]
