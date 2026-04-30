# RP-Hub 后端镜像：用于部署 FastAPI 服务
FROM python:3.11-slim

WORKDIR /app

# 安装运行依赖
COPY requirements.txt /app/requirements.txt
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip install --no-cache-dir -r /app/requirements.txt

# 复制应用代码
COPY app /app/app

# 暴露服务端口
EXPOSE 8000

# 启动 FastAPI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
